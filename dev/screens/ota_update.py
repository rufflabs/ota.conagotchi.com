"""Settings -> System -> Update: manual file-level OTA update screen.

Shows the current OTA version, lets the user START a check, connects WiFi and
compares files. When there is an update it shows the new version, the
download size and the release notes the manifest carries, in a scrolling
window (LEFT/RIGHT); START installs (streams changed files with a progress
bar, verifies sha256, commits, reboots) and SELECT cancels. Every page follows
Settings -> Badge -> Text Size: in large mode the text is 2x, with shorter
wording where only 10 characters fit.
The download runs as an asyncio task so the UI stays responsive; the task only
mutates instance state, and update() redraws the regions that changed. Progress
callbacks repaint the bar and percentage alone -- the frame is never cleared
mid-update, which would flash the screen on every callback.

Security: this is a MANUAL, user-triggered update only (no auto-check). Files
are integrity-checked but not signed — the configured host is trusted.
"""
import time

import theme
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen

_STATE_IDLE = "idle"
_STATE_RUNNING = "running"
_STATE_DONE = "done"
_STATE_ERROR = "error"
_STATE_NO_WIFI = "no_wifi"   # needs the user to join a network first
_STATE_READY = "ready"       # an update was found: notes shown, START installs

_REBOOT_DELAY_MS = 2500

_BAR_W = 180
_BAR_Y = 118
_BAR_H = 16

# Rows repainted on their own during a running update (8px font cells).
_STATUS_Y = 86
_PCT_Y = _BAR_Y + _BAR_H + 8
_TEXT_H = 8

# Release notes window (per menu text size: 1 normal, 2 large).
_NEW_Y = 58
_SIZE_Y = 74
_NOTES_Y = 92
_NOTES_ROWS = {1: 5, 2: 3}
_NOTES_LINE_H = {1: 16, 2: 22}
_NOTES_WIDTH = {1: 20, 2: 10}


def _radio_active():
    """True if the station interface is currently powered up."""
    try:
        import network
        return bool(network.WLAN(network.STA_IF).active())
    except Exception:
        return False


def _radio_off():
    """Power the station interface down, ignoring an idle-disconnect error."""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        try:
            wlan.disconnect()
        except Exception:
            pass
        wlan.active(False)
    except Exception:
        pass


def _channel():
    """The badge's selected OTA channel."""
    try:
        from settings_state import BadgeSettings
        return BadgeSettings().ota_channel
    except Exception:
        try:
            from config import OTA_CHANNEL
            return OTA_CHANNEL
        except Exception:
            return ""


def _manifest_url():
    """Manifest URL for the selected channel, or "" when OTA is unconfigured."""
    try:
        import ota
        from config import OTA_BASE_URL
        return ota.manifest_url(OTA_BASE_URL, _channel())
    except Exception:
        return ""


def _credentials():
    """The user's saved Wi-Fi credentials, falling back to the config defaults."""
    ssid = password = ""
    try:
        from settings_state import BadgeSettings
        saved = BadgeSettings()
        ssid, password = saved.ssid, saved.password
    except Exception:
        pass
    if not ssid or not password:
        try:
            from config import WIFI_PASSWORD, WIFI_SSID
            ssid = ssid or WIFI_SSID
            password = password or WIFI_PASSWORD
        except Exception:
            pass
    return ssid, password


class OTAUpdateScreen(Screen):
    def __init__(self):
        self._state = _STATE_IDLE
        self._status = ""
        self._progress = None      # (done_bytes, total_bytes)
        self._result = None        # dict from OTAUpdater.run()
        self._error = ""
        self._reboot_at = None
        self._task = None
        # Per-region redraw bookkeeping: the frame (background, title, static
        # labels) is painted only when the state changes, while the status line
        # and progress bar repaint themselves. Without this the screen cleared
        # on every progress callback and visibly flashed.
        self._last_frame = None
        self._last_status = None
        self._last_pct = None
        self._last_fill = None
        self._updater = None       # kept from the check for the install
        self._checked = None       # OTAUpdater.check() result
        self._radio_was_on = None  # Wi-Fi state before the first check
        self._top = 0              # first release-notes line shown

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr):
        self._invalidate()
        self._draw(display)

    async def update(self, display, leds, mgr):
        if (self._state == _STATE_DONE and self._reboot_at is not None
                and time.ticks_diff(time.ticks_ms(), self._reboot_at) >= 0):
            import machine
            machine.reset()
        self._draw(display)

    async def exit(self, display, leds, mgr):
        self._release_radio()      # e.g. backing out of the release notes

    def handle_button(self, btn, mgr):
        if self._state == _STATE_RUNNING:
            return  # ignore input mid-update (except it can't be cancelled safely)
        if self._state == _STATE_READY:
            if btn in (LEFT, RIGHT):
                rows = _NOTES_ROWS[ui.list_scale()]
                last = max(0, len(self._note_lines()) - rows)
                top = self._top + (rows - 1) * (1 if btn == RIGHT else -1)
                top = max(0, min(last, top))
                if top != self._top:
                    self._top = top
                    self._draw_notes(mgr._display)
                return
            if btn == START:
                self._start_install()
                return
        if btn in (SELECT, BOOT):
            mgr.pop()
            return
        if btn == START and self._state in (_STATE_IDLE, _STATE_ERROR,
                                            _STATE_DONE, _STATE_NO_WIFI):
            self._start()

    # ── update task ──────────────────────────────────────────────────────────

    def _start(self):
        """START on the first page: check for an update (nothing installed)."""
        import asyncio
        self._state = _STATE_RUNNING
        self._status = "Starting"
        self._progress = None
        self._result = None
        self._checked = None
        self._error = ""
        self._reboot_at = None
        self._task = asyncio.create_task(self._run())

    def _start_install(self):
        """START on the release notes: install what the check found."""
        import asyncio
        self._state = _STATE_RUNNING
        self._status = "Starting"
        self._progress = None
        self._task = asyncio.create_task(self._install())

    def _release_radio(self):
        """Power Wi-Fi down again if it was off before the first check."""
        if self._radio_was_on is False:
            _radio_off()
        self._radio_was_on = None

    def _note_lines(self):
        """The release notes wrapped for the window, as (text, kind)."""
        width = _NOTES_WIDTH[ui.list_scale()]
        out = []
        for note in (self._checked or {}).get("notes", []):
            if note.startswith("## "):
                if out:
                    out.append(("", "text"))
                out += [(l, "accent") for l in ui.wrap_text(note[3:].upper(), width)]
            elif note:
                out += [(l, "text") for l in ui.wrap_text(note, width)]
        return out

    async def _run(self):
        # Note the radio state before we touch it: an update must not leave
        # Wi-Fi powered up afterwards, draining the battery. Constructing Wifi()
        # itself deactivates the radio, so this has to be sampled first.
        if self._radio_was_on is None:
            self._radio_was_on = _radio_active()
        keep_radio = False
        try:
            manifest = _manifest_url()
            if not manifest:
                self._fail("No update URL set")
                return

            ssid, password = _credentials()
            if not ssid or not password:
                self._no_wifi("Wi-Fi not set up")
                return

            self._status = "Connecting WiFi"
            from wifi import Wifi
            wifi = Wifi()
            ok = await wifi.connect(ssid, password)
            if not ok:
                self._no_wifi("Can't join " + ssid[:16])
                return

            import ota
            self._updater = ota.OTAUpdater(manifest)
            checked = self._updater.check(status=self._on_status)
            if checked["available"]:
                # Show the notes and wait for START; Wi-Fi stays up meanwhile.
                self._checked = checked
                self._top = 0
                self._state = _STATE_READY
                keep_radio = True
                return
            self._result = {"updated": False, "reason": checked["reason"],
                            "version": checked["version"], "count": 0}
            self._state = _STATE_DONE
            if checked["reason"] == "up-to-date":
                self._status = "Up to date (v%d)" % checked["version"]
            else:
                self._status = "Current (v%d)" % checked["version"]
        except Exception as e:  # network / checksum / filesystem
            self._fail(str(e) or e.__class__.__name__)
        finally:
            # Only power the radio down if it was off when we started, so a
            # badge the user deliberately left on Wi-Fi stays on.
            if not keep_radio:
                self._release_radio()

    async def _install(self):
        try:
            res = await self._updater.install(self._checked, progress=self._on_progress,
                                              status=self._on_status)
            self._result = res
            self._state = _STATE_DONE
            self._status = "Updated v%d" % res["version"]
            self._reboot_at = time.ticks_add(time.ticks_ms(), _REBOOT_DELAY_MS)
        except Exception as e:  # network / checksum / filesystem
            self._fail(str(e) or e.__class__.__name__)
        finally:
            self._release_radio()

    def _fail(self, msg):
        self._state = _STATE_ERROR
        self._error = msg
        self._status = ""

    def _no_wifi(self, msg):
        """Send the user to Settings -> Wireless -> Wi-Fi instead of showing a bare error."""
        self._state = _STATE_NO_WIFI
        self._status = msg
        self._error = ""

    def _on_progress(self, done, total):
        self._progress = (done, total)

    def _on_status(self, msg):
        self._status = msg

    # ── drawing ──────────────────────────────────────────────────────────────

    def _invalidate(self):
        """Force a full repaint on the next draw."""
        self._last_frame = None
        self._last_status = None
        self._last_pct = None
        self._last_fill = None

    def _pct(self):
        if not self._progress:
            return 0
        done, total = self._progress
        if not total:
            return 0
        return min(100, done * 100 // total)

    def _draw(self, display):
        """Repaint only what changed.

        The frame is keyed on state (and, outside a running update, on the
        status/error text, which is static there). While an update runs the
        status line and progress bar are repainted individually, so a progress
        callback never clears the screen."""
        frame = (self._state, self._error,
                 None if self._state == _STATE_RUNNING else self._status)
        if frame != self._last_frame:
            self._last_frame = frame
            self._last_status = None
            self._last_pct = None
            self._last_fill = None
            self._draw_frame(display)

        if self._state != _STATE_RUNNING:
            return

        if self._status != self._last_status:
            self._last_status = self._status
            self._draw_status(display)

        pct = self._pct()
        if pct != self._last_pct:
            self._last_pct = pct
            self._draw_bar(display)

    def _draw_frame(self, display):
        """Full-screen paint: background, title, and whatever is static for
        the current state. The running state's status line and bar are left to
        _draw_status/_draw_bar, which run straight after."""
        import ota
        ui.screen(display, "UPDATE")
        if ui.list_scale() == 2:
            self._draw_frame_large(display, ota.local_version())
            return
        channel = _channel()
        label = "Version %d" % ota.local_version()
        if channel:
            label += "  " + channel.upper()
        ui.status(display, label, 40)

        if self._state == _STATE_IDLE:
            ui.paragraph(display, "Check for the latest badge software.", 96,
                         kind="text")
            ui.controls(display, "CHECK")
        elif self._state == _STATE_READY:
            c = self._checked
            big = ui.list_scale() == 2
            ui.status(display, ("NEW v%d" if big else "UPDATE TO v%d") % c["version"],
                      _NEW_Y, "success", 2 if big else 1)
            ui.status(display, "%d FILES, %d KB" % (c["count"], (c["bytes"] + 1023) // 1024),
                      _SIZE_Y + (6 if big else 0), "muted")
            self._draw_notes(display)
            ui.controls(display, "INSTALL")
        elif self._state == _STATE_RUNNING:
            ui.status(display, "Do not power off", 168, "muted")
        elif self._state == _STATE_DONE:
            updated = bool(self._result and self._result.get("updated"))
            ui.status(display, self._status, 96,
                      "success" if updated else "muted")
            if updated:
                ui.status(display, "Rebooting...", 120)
            else:
                ui.controls(display, "AGAIN")
        elif self._state == _STATE_NO_WIFI:
            ui.status(display, self._status, 78, "warning")
            ui.paragraph(display, "Open Settings > Wireless > Wi-Fi to join a network, "
                         "then try again.", 106)
            ui.controls(display, "RETRY")
        elif self._state == _STATE_ERROR:
            ui.status(display, "Update failed", 88, "danger")
            ui.text_lines(display, [(l, "muted") for l in
                                    ui.wrap_text(self._error)[:3]],
                          112, line_h=16)
            ui.controls(display, "RETRY")

    def _draw_frame_large(self, display, version):
        """_draw_frame in large text: 2x lines of at most 10 characters."""
        channel = _channel()
        ui.status(display, ("v%d %s" % (version, channel.upper())).strip(), 42,
                  "text", 2)
        st = self._state
        if st == _STATE_IDLE:
            ui.scaled_lines(display, ("CHECK FOR", "THE LATEST", "SOFTWARE"), 80)
            ui.controls(display, "CHECK")
        elif st == _STATE_READY:
            c = self._checked
            ui.status(display, "NEW v%d" % c["version"], 62, "success", 2)
            ui.status(display, "%d KB" % ((c["bytes"] + 1023) // 1024), 82, "muted", 2)
            self._draw_notes(display)
            ui.controls(display, "INSTALL")
        elif st == _STATE_RUNNING:
            ui.status(display, "KEEP IT ON", 170, "muted", 2)
        elif st == _STATE_DONE:
            res = self._result or {}
            if res.get("updated"):
                head, kind = "UPDATED", "success"
            elif res.get("reason") == "up-to-date":
                head, kind = "UP TO DATE", "muted"
            else:
                head, kind = "CURRENT", "muted"
            ui.scaled_lines(display, ((head, kind), "v%d" % res.get("version", version)), 80)
            if res.get("updated"):
                ui.status(display, "REBOOTING", 130, "text", 2)
            else:
                ui.controls(display, "AGAIN")
        elif st == _STATE_NO_WIFI:
            ui.scaled_lines(display, (("NO WI-FI", "warning"), "",
                                      ("SETTINGS >", "muted"), ("WIRELESS >", "muted"),
                                      ("WI-FI", "muted")), 72)
            ui.controls(display, "RETRY")
        elif st == _STATE_ERROR:
            ui.scaled_lines(display, [("FAILED", "danger"), ""] +
                            [(l, "muted") for l in ui.wrap_text(self._error, 10)[:4]], 72)
            ui.controls(display, "RETRY")

    def _draw_notes(self, display):
        """The release notes window alone, so scrolling does not blink."""
        k = ui.list_scale()
        rows, line_h = _NOTES_ROWS[k], _NOTES_LINE_H[k]
        y0 = _NOTES_Y + (12 if k == 2 else 0)
        lines = self._note_lines()
        ui.clear_band(display, y0 - 2, rows * line_h + 2)
        if not lines:
            ui.status(display, "NO RELEASE NOTES", y0 + line_h, "muted")
            return
        for i, (text, kind) in enumerate(lines[self._top:self._top + rows]):
            ui.status(display, text, y0 + i * line_h, kind, k)
        ui.scrollbar(display, self._top, rows, len(lines), y0, y0 + rows * line_h)

    def _draw_status(self, display):
        """Repaint just the status row (cleared first: the text is centred, so
        a shorter message would otherwise leave the old one's tails behind)."""
        if ui.list_scale() == 2:
            ui.status_row(display, _short_status(self._status), _STATUS_Y, "accent", 2)
            return
        display.fill_rect(0, _STATUS_Y, 240, _TEXT_H, theme.get().bg)
        ui.status(display, self._status, _STATUS_Y, "accent")

    def _draw_bar(self, display):
        """Repaint just the progress bar and its percentage. ui.progress_bar
        paints only the newly filled slice while the bar grows, so it never
        blinks; it repaints whole on the first draw or when it shrinks."""
        pct = self._pct()
        self._last_fill = ui.progress_bar(display, _BAR_Y, pct, h=_BAR_H,
                                          w=_BAR_W, prev=self._last_fill)
        if ui.list_scale() == 2:
            ui.status_row(display, "%d%%" % pct, _PCT_Y, "text", 2)
            return
        display.fill_rect(0, _PCT_Y, 240, _TEXT_H, theme.get().bg)
        ui.status(display, "%d%%" % pct, _PCT_Y)


def _short_status(status):
    """A running update's status line in 10 characters, for large text."""
    for start, short in (("Get ", "LOADING"), ("Connecting", "WI-FI..."),
                         ("Fetching", "CHECKING"), ("Comparing", "CHECKING"),
                         ("Installing", "INSTALLING"), ("Starting", "STARTING")):
        if status.startswith(start):
            return short
    return status.upper()[:10]
