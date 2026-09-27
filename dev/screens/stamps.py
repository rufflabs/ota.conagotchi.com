"""Collection -> Stamps: collect vendor stamps, and (vendor badges) stamp others.

    STAMPS        My Stamps / Collect Stamps / Vendor Stamp (Vendor Mode only)
    MY STAMPS     collected vendor IDs, each with the badge that stamped it
    COLLECT       listens for vendors nearby and collects their stamps
    VENDOR        this badge's vendor ID, Start Stamping, and who was stamped
    STAMPING      the vendor ID; START stamps the badge held close (one per
                  press, 10 s to reply), with the result and a running total
    STAMPED       every attendee badge this vendor stamped: full badge ID and
                  stamp number, newest first

Stamping is Bluetooth only (stamp_session.py) and follows Settings ->
Bluetooth: with it off, the screens say so instead of listening.
"""
import ui
from buttons import BOOT, SELECT, START
from screen_manager import Screen
from menu import ListScreen

BT_HINT = "Turn on Bluetooth in Settings to use stamps"
COLLECT_HINT = "Visit vendors to collect their stamps!"
STAMPED_HINT = "No badges stamped yet"

_REFRESH_MS = 700


def _bluetooth_on() -> bool:
    try:
        from settings_state import BadgeSettings
        return BadgeSettings().bluetooth_enabled
    except Exception:
        return False


def _short(badge: str) -> str:
    from trade_session import short_id
    return short_id(badge)


class StampsMenuScreen(ListScreen):
    title = "STAMPS"

    def rows(self):
        import stamp_manager
        rows = [("My Stamps", str(stamp_manager.count()), "mine"),
                ("Collect Stamps", None, "collect")]
        try:
            from settings_state import BadgeSettings
            vendor = BadgeSettings().vendor_mode_enabled
        except Exception:
            vendor = False
        if vendor:
            rows.append(("Vendor Stamp", stamp_manager.vendor_id() or "SET", "vendor"))
        return rows

    def activate(self, mgr) -> None:
        key = self.menu.key
        if key == "mine":
            mgr.push(MyStampsScreen())
        elif key == "collect":
            mgr.push(CollectScreen())
        else:
            mgr.push(VendorScreen())


class MyStampsScreen(ListScreen):
    title = "MY STAMPS"

    def rows(self):
        import stamp_manager
        stamps = stamp_manager.all_stamps()
        if not stamps:
            return [COLLECT_HINT]
        return [(vid, _short(badge)) for vid, badge in stamps]

    def confirm(self):
        return None


class StampedListScreen(ListScreen):
    """Every badge this vendor has stamped: the full badge ID, and its stamp
    number on the right (#1 = first stamped), newest first."""

    title = "STAMPED"
    message_kind = "muted"

    def rows(self):
        import stamp_manager
        badges = stamp_manager.stamped()
        n = len(badges)
        self.message = ("%d BADGE%s" % (n, "" if n == 1 else "S")) if n else ""
        if not badges:
            return [STAMPED_HINT]
        return [(badges[i].upper(), "#%d" % (i + 1)) for i in range(n - 1, -1, -1)]

    def confirm(self):
        return None


class VendorScreen(ListScreen):
    """Vendor ID, Start Stamping, and the stamped list."""

    title = "VENDOR"

    def rows(self):
        import stamp_manager
        return [("Vendor ID", stamp_manager.vendor_id() or "SET", "id"),
                ("Start Stamping", None, "start"),
                ("Stamped Badges", str(len(stamp_manager.stamped())), "stamped")]

    def confirm(self):
        return {"id": "EDIT", "start": "START", "stamped": "VIEW"}[self.menu.key]

    def activate(self, mgr) -> None:
        import stamp_manager
        self.message = ""
        key = self.menu.key
        if key == "id":
            from screens.text_input import TextInputScreen
            mgr.push(TextInputScreen("VENDOR ID", stamp_manager.vendor_id(),
                                     on_done=self._save_id,
                                     max_len=stamp_manager.VENDOR_ID_LEN))
        elif key == "start":
            if not stamp_manager.vendor_id():
                self.message = "SET AN ID FIRST"
            elif not _bluetooth_on():
                self.message = "TURN ON BLUETOOTH"
            else:
                mgr.push(StampingScreen(stamp_manager.vendor_id()))
                return
            self.draw(mgr._display)
        else:
            mgr.push(StampedListScreen())

    def _save_id(self, text) -> None:
        import stamp_manager
        vid = stamp_manager.set_vendor_id(text)
        self.message = ("ID " + vid) if vid else "ID CLEARED"


class _LiveScreen(Screen):
    """A Bluetooth session screen. The frame is drawn once; after that only the
    lines that change are repainted in place (no clear), so nothing blinks."""

    title = ""

    def __init__(self) -> None:
        self._session = None
        self._frame = None
        self._next = 0
        self._title = ui.Marquee()

    def _make(self):
        return None

    async def enter(self, display, leds, mgr) -> None:
        if _bluetooth_on():
            self._session = self._make()
            if not self._session.start():
                self._session = None
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        if self._session is not None:
            self._session.stop()

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)
        if self._session is None:
            return
        import time
        self._session.poll()
        now = time.ticks_ms()
        if time.ticks_diff(now, self._next) >= 0:
            self._next = time.ticks_add(now, _REFRESH_MS)
            if self._state() != self._frame:
                self._frame = self._state()
                self._paint(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn in (BOOT, SELECT):
            mgr.pop()

    def _state(self):
        return None

    def _draw(self, display) -> None:
        """The whole screen: static parts, then the live parts."""
        self._frame = self._state()
        ui.screen(display, self.title, marquee=self._title)
        if self._session is None:
            text = BT_HINT if not _bluetooth_on() else "BLUETOOTH N/A"
            if ui.list_scale() == 2:
                ui.scaled_lines(display, [(line, "warning")
                                          for line in ui.wrap_text(text.upper(), 10)])
            else:
                ui.paragraph(display, text, 92, kind="warning")
        else:
            self._draw_static(display)
            self._reset_live()
            self._paint(display)
        ui.controls(display)

    def _draw_static(self, display) -> None:
        pass

    def _reset_live(self) -> None:
        pass

    def _paint(self, display) -> None:
        pass


class CollectScreen(_LiveScreen):
    """Listen for vendors and collect their stamps. Follows Text Size: in
    large mode the text is 2x, two vendors fit, and the prompt is shorter."""

    title = "COLLECT"
    _NEAR_Y = {1: 84, 2: 88}
    _NEAR_H = {1: 28, 2: 36}
    _NEAR_ROWS = {1: 3, 2: 2}
    _NEAR_TOP = {1: 72, 2: 70}
    _NEAR_BOTTOM = {1: 162, 2: 162}
    _STATUS_Y = {1: 170, 2: 170}

    def _make(self):
        from stamp_session import StampCollector
        return StampCollector()

    def _near_rows(self):
        rows = self._NEAR_ROWS[ui.list_scale()]
        return [_meter((vid, rssi, "BT"), _stamp_rssi_min())
                for vid, rssi in self._session.nearby()[:rows]]

    def _state(self):
        s = self._session
        if s is None:
            return None
        import stamp_manager
        near = tuple((r[0], r[3]) for r in self._near_rows())
        return (s.last, near, stamp_manager.count())

    def _reset_live(self) -> None:
        self._near_keys = None

    def _paint(self, display) -> None:
        import stamp_manager
        s = self._session
        k = ui.list_scale()
        ui.status_row(display, "%d STAMPS" % stamp_manager.count(), 44, "muted", k)
        self._near_keys = ui.meters_in_place(
            display, self._near_rows(), self._near_keys, self._NEAR_Y[k],
            self._NEAR_H[k], empty="NO VENDORS NEARBY" if k == 1 else "NO VENDORS",
            empty_y=110, top=self._NEAR_TOP[k], bottom=self._NEAR_BOTTOM[k], scale=k)
        near = s.nearby()
        # (normal text, large text, colour); large lines fit 10 characters.
        if s.last is None and near:
            if near[0][1] >= _stamp_rssi_min():
                line = ("HOLD STILL...", "HOLD STILL", "accent")
            else:
                line = ("MOVE CLOSER", "GET CLOSER", "warning")
        elif s.last is None:
            line = ("LISTENING...", "LISTENING", "muted")
        elif s.last[1]:
            line = ("GOT " + s.last[0] + "!",) * 2 + ("success",)
        else:
            line = ("HAVE " + s.last[0],) * 2 + ("muted",)
        ui.status_row(display, line[k - 1], self._STATUS_Y[k], line[2], k)


class StampingScreen(_LiveScreen):
    """A vendor badge: START stamps the badge held close, one per press."""

    title = "STAMPING"

    def __init__(self, vendor_id: str) -> None:
        super().__init__()
        self._vendor_id = vendor_id

    def _make(self):
        from stamp_session import StampBeacon
        return StampBeacon(self._vendor_id)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == START and self._session is not None:
            self._session.stamp()
            self._frame = self._state()
            self._paint(mgr._display)
        else:
            super().handle_button(btn, mgr)

    def _state(self):
        s = self._session
        if s is None:
            return None
        return (s.total, s.window_left(), s.result, len(s.nearby()))

    def _draw_static(self, display) -> None:
        if ui.list_scale() == 2:
            ui.scaled_lines(display, (("VENDOR", "muted"), (self._vendor_id, "accent")))
        else:
            ui.card(display, (("VENDOR ID", "muted"), (self._vendor_id, "text")))

    def _paint(self, display) -> None:
        s = self._session
        k = ui.list_scale()
        # (normal text, large text); large lines fit about 12 characters here.
        if s.stamping():
            line, kind = ("STAMPING %ds" % s.window_left(),
                          "STAMP %ds" % s.window_left()), "success"
        elif s.result is None:
            line, kind = ("START TO STAMP", "PRESS STAMP"), "muted"
        elif not s.result[0]:
            line, kind = ("NO BADGE - TRY AGAIN", "NO BADGE"), "warning"
        elif s.result[1]:
            line, kind = ("STAMPED " + _short(s.result[0]),) * 2, "success"
        else:
            line, kind = ("ALREADY HAD " + _short(s.result[0]),
                          "HAD " + _short(s.result[0])), "muted"
        if k == 2:
            ui.status_row(display, line[1], 100, kind, 2)
            ui.status_row(display, "TOTAL %d" % s.total, 126, "muted", 2)
            ui.status_row(display, "+%d NEW" % s.session_count, 146, "muted", 2)
            ui.status_row(display, "NEAR %d" % len(s.nearby()), 166, "muted", 2)
            return
        ui.status_row(display, line[0], 146, kind)
        ui.status_row(display, "TOTAL %d  (+%d)" % (s.total, s.session_count), 162,
                      "muted")
        ui.status_row(display, "NEARBY: %d" % len(s.nearby()), 178, "muted")

    def _draw(self, display) -> None:
        super()._draw(display)
        if self._session is not None:
            ui.controls(display, "STAMP")


# Bluetooth signal shown as a bar: this range maps to empty..full.
_RSSI_FLOOR = -95
_RSSI_FULL = -45


def _meter(row, rssi_min):
    """A nearby vendor as a meter row: bar and colour from its signal."""
    badge, rssi, via = row
    if rssi is None:                           # no signal strength reported
        return (badge, 100, "success", via)
    pct = (rssi - _RSSI_FLOOR) * 100 // (_RSSI_FULL - _RSSI_FLOOR)
    if rssi >= rssi_min:
        kind = "success"                       # close enough to collect
    elif rssi >= rssi_min - 15:
        kind = "warning"
    else:
        kind = "danger"
    return (badge, pct, kind, "%ddB" % rssi)


def _stamp_rssi_min():
    """Stamps' proximity threshold, so a green bar means close enough."""
    from stamp_session import STAMP_RSSI_MIN
    return STAMP_RSSI_MIN
