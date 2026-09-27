"""Settings -> Update: manual file-level OTA update screen.

Shows the current OTA version, lets the user START a check, connects WiFi,
streams changed files (progress bar), verifies sha256, commits, and reboots.
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
from buttons import BOOT, SELECT, START
from screen_manager import Screen

_STATE_IDLE = "idle"
_STATE_RUNNING = "running"
_STATE_DONE = "done"
_STATE_ERROR = "error"
_STATE_NO_WIFI = "no_wifi"   # needs the user to join a network first

_REBOOT_DELAY_MS = 2500

_BAR_W = 180
_BAR_Y = 118
_BAR_H = 16

# Rows repainted on their own during a running update (8px font cells).
_STATUS_Y = 86
_PCT_Y = _BAR_Y + _BAR_H + 8
_TEXT_H = 8


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

    def handle_button(self, btn, mgr):
        if self._state == _STATE_RUNNING:
            return  # ignore input mid-update (except it can't be cancelled safely)
        if btn in (SELECT, BOOT):
            mgr.pop()
            return
        if btn == START and self._state in (_STATE_IDLE, _STATE_ERROR,
                                            _STATE_DONE, _STATE_NO_WIFI):
            self._start()

    # ── update task ──────────────────────────────────────────────────────────

    def _start(self):
        import asyncio
        self._state = _STATE_RUNNING
        self._status = "Starting"
        self._progress = None
        self._result = None
        self._error = ""
        self._reboot_at = None
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        # Note the radio state before we touch it: an update must not leave
        # Wi-Fi powered up afterwards, draining the battery. Constructing Wifi()
        # itself deactivates the radio, so this has to be sampled first.
        radio_was_on = _radio_active()
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
            updater = ota.OTAUpdater(manifest)
            res = await updater.run(progress=self._on_progress,
                                    status=self._on_status)
            self._result = res
            self._state = _STATE_DONE
            if res["updated"]:
                self._status = "Updated v%d" % res["version"]
                self._reboot_at = time.ticks_add(time.ticks_ms(), _REBOOT_DELAY_MS)
            elif res["reason"] == "up-to-date":
                self._status = "Up to date (v%d)" % res["version"]
            else:
                self._status = "Current (v%d)" % res["version"]
        except Exception as e:  # network / checksum / filesystem
            self._fail(str(e) or e.__class__.__name__)
        finally:
            # Only power the radio down if it was off when we started, so a
            # badge the user deliberately left on Wi-Fi stays on.
            if not radio_was_on:
                _radio_off()

    def _fail(self, msg):
        self._state = _STATE_ERROR
        self._error = msg
        self._status = ""

    def _no_wifi(self, msg):
        """Send the user to Settings -> Wi-Fi instead of showing a bare error."""
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
        channel = _channel()
        label = "Version %d" % ota.local_version()
        if channel:
            label += "  " + channel.upper()
        ui.status(display, label, 40)

        if self._state == _STATE_IDLE:
            ui.paragraph(display, "Check for the latest badge software.", 96,
                         kind="text")
            ui.controls(display, "CHECK")
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
            ui.paragraph(display, "Open Settings > Wi-Fi to join a network, "
                         "then try again.", 106)
            ui.controls(display, "RETRY")
        elif self._state == _STATE_ERROR:
            ui.status(display, "Update failed", 88, "danger")
            ui.text_lines(display, [(l, "muted") for l in
                                    ui.wrap_text(self._error)[:3]],
                          112, line_h=16)
            ui.controls(display, "RETRY")

    def _draw_status(self, display):
        """Repaint just the status row (cleared first: the text is centred, so
        a shorter message would otherwise leave the old one's tails behind)."""
        display.fill_rect(0, _STATUS_Y, 240, _TEXT_H, theme.get().bg)
        ui.status(display, self._status, _STATUS_Y, "accent")

    def _draw_bar(self, display):
        """Repaint just the progress bar and its percentage. ui.progress_bar
        paints only the newly filled slice while the bar grows, so it never
        blinks; it repaints whole on the first draw or when it shrinks."""
        pct = self._pct()
        self._last_fill = ui.progress_bar(display, _BAR_Y, pct, h=_BAR_H,
                                          w=_BAR_W, prev=self._last_fill)
        display.fill_rect(0, _PCT_Y, 240, _TEXT_H, theme.get().bg)
        ui.status(display, "%d%%" % pct, _PCT_Y)
