"""Collection -> Trade: choose a Chi to send, then trade it with a nearby badge.

    TRADE        collected Chi's; START picks the one to offer
    TRADING      this badge's ID and nearby badges (IDs, signal strength).
                 SEND opens a send window; the other badge must SEND too
                 before it closes, on whichever link reaches it
    TRADE DONE   what was sent and received (the new Chi is collected, not
                 made active)

The exchange itself is trade_session.TradeSession. Bluetooth and IR are used
only when enabled in Settings; the LINK cable is always used. With both off
the screen says so, since only a cable trade can then happen.
"""
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen

WIRELESS_HINT = "Enable IR or BT for wireless trades"

_PICK = "pick"
_TRADING = "trading"
_DONE = "done"

# Trading view layout.
_SEND_Y = 42
_ID_Y = 56
_NEAR_Y = 84          # first nearby-badge meter
_NEAR_ROW_H = 28
_NEAR_TOP = 72        # band repainted when the nearby list changes
_NEAR_BOTTOM = 162
_PROMPT_Y = 170
_NEAR_REFRESH_MS = 700

# Bluetooth signal shown as a bar: this range maps to empty..full.
_RSSI_FLOOR = -95
_RSSI_FULL = -45


class TradeScreen(Screen):

    def __init__(self) -> None:
        self._view = _PICK
        self._sel = 0
        self._top = 0
        self._chars = ()
        self._active = ""
        self._session = None
        self._frame = None          # what the trading view last drew
        self._near = None           # the nearby list last drawn
        self._near_next = 0
        self._title = ui.Marquee()
        self._row = ui.Marquee()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        self._refresh(select_active=True)
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        self._stop()

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)
        if self._view == _PICK:
            ui.tick_list(display, self._rows(), self._sel, self._top, self._row)
            return
        if self._view != _TRADING or self._session is None:
            return
        self._session.poll()
        if self._session.done:
            self._view = _DONE
            self._refresh()
            self._draw(display)
        elif self._trading_frame() != self._frame:
            self._draw(display)
        else:
            import time
            now = time.ticks_ms()
            if time.ticks_diff(now, self._near_next) >= 0:
                self._near_next = time.ticks_add(now, _NEAR_REFRESH_MS)
                if _near_key(self._session.nearby()) != self._near:
                    self._draw_nearby(display)

    # ── Input ────────────────────────────────────────────────────────────────

    def handle_button(self, btn: str, mgr) -> None:
        back = btn == BOOT or btn == SELECT
        if self._view == _PICK:
            if back:
                mgr.pop()
            elif btn == LEFT or btn == RIGHT:
                count = len(self._chars)
                self._sel = (self._sel + (1 if btn == RIGHT else -1)) % count
                self._top = ui.clamp_scroll(self._sel, self._top, count)
                self._draw(mgr._display)
            elif btn == START:
                self._begin(mgr._display)
        elif self._view == _TRADING:
            if back:
                self._stop()
                self._view = _PICK
                self._draw(mgr._display)
            elif btn == START:
                self._session.send()      # offer, and accept theirs, for a while
                self._draw(mgr._display)
        elif back or btn == START:        # TRADE DONE -> pick again
            self._view = _PICK
            self._draw(mgr._display)

    def _begin(self, display) -> None:
        from settings_state import BadgeSettings
        from trade_session import TradeSession
        settings = BadgeSettings()
        self._session = TradeSession(send_id=self._chars[self._sel].id,
                                     ble=settings.bluetooth_enabled,
                                     ir=settings.ir_enabled)
        self._view = _TRADING
        if not self._session.start():      # announce only; SEND offers
            self._session.message = "LINK N/A"
        self._draw(display)

    def _stop(self) -> None:
        if self._session is not None:
            self._session.stop()

    # ── State ────────────────────────────────────────────────────────────────

    def _refresh(self, select_active=False) -> None:
        import character_manager
        self._chars = tuple(character_manager.get_unlocked())
        self._active = character_manager.get_active().id
        if select_active:
            for i, char in enumerate(self._chars):
                if char.id == self._active:
                    self._sel = i
        self._sel = min(self._sel, len(self._chars) - 1)
        self._top = ui.window_top(self._sel, len(self._chars))

    def _rows(self):
        return [(c.name, "ACTIVE") if c.id == self._active else c.name
                for c in self._chars]

    def _trading_frame(self):
        s = self._session
        return (s.message, s.running, s.window_left(), s.sent_once)

    # ── Drawing ──────────────────────────────────────────────────────────────

    def _draw(self, display) -> None:
        if self._view == _PICK:
            ui.screen(display, "TRADE", marquee=self._title)
            ui.list_view(display, self._rows(), self._sel, self._top,
                         marquee=self._row)
            ui.message(display, "Pick a Chi to send", "muted")
            ui.controls(display, "NEXT")
        elif self._view == _TRADING:
            self._draw_trading(display)
        else:
            self._draw_done(display)

    def _draw_trading(self, display) -> None:
        from trade_session import my_badge, short_id
        s = self._session
        self._frame = self._trading_frame()
        ui.screen(display, "TRADING", marquee=self._title)
        ui.status(display, "SEND " + _chi_name(s.send_id).upper(), _SEND_Y)
        ui.status(display, "ID %s  %s" % (short_id(my_badge()), s.transports()),
                  _ID_Y, "muted")
        self._draw_nearby(display)
        if s.message:
            lines = ((s.message, "accent"),)
        elif s.window_open():
            lines = (("SENDING %ds" % s.window_left(), "success"),
                     ("BRING BADGES CLOSE" if s.use_ble else "OTHER BADGE: SEND",
                      "muted"))
        elif s.sent_once:
            lines = (("NO REPLY", "warning"), ("START TO SEND AGAIN", "muted"))
        elif not s.wireless:
            lines = (("Enable IR or BT for", "warning"), ("wireless trades", "warning"))
        else:
            lines = (("START TO SEND", "muted"),)
        ui.text_lines(display, lines, _PROMPT_Y - (6 if len(lines) > 1 else 0),
                      line_h=14)
        ui.controls(display, "SEND")

    def _draw_nearby(self, display) -> None:
        """Nearby badges: short ID, signal bar and dB (or LINK/IR). Repainted
        on its own as signals change, so the rest of the screen stays still."""
        s = self._session
        near = s.nearby()
        self._near = _near_key(near)
        ui.clear_band(display, _NEAR_TOP, _NEAR_BOTTOM - _NEAR_TOP)
        if not near:
            ui.status(display, "NO BADGES NEARBY", 104, "muted")
            if s.use_ble:
                ui.status(display, "Keep screen open", 122, "muted")
            return
        ui.meter_list(display, [_meter(row, s.rssi_min()) for row in near], None,
                      _NEAR_Y, _NEAR_ROW_H)

    def _draw_done(self, display) -> None:
        s = self._session
        sent, recv, new = s.result if s.result else ("", "", False)
        ui.screen(display, "TRADE DONE", marquee=self._title)
        ui.card(display, (("SENT " + sent.upper(), "muted"), ("GOT", "muted"),
                 (recv.upper(), "text"),
                 ("NEW!" if new else "ALREADY HAD", "success" if new else "muted")),
                y=62, h=92, w=184)
        ui.status(display, "VIA " + s.transport, 166, "muted")
        ui.controls(display, "OK")


def _meter(row, rssi_min):
    """A nearby badge as a meter row: bar and colour from its signal."""
    badge, rssi, via = row
    if rssi is None:                           # cable or IR: no strength
        return (badge, 100, "success", via)
    pct = (rssi - _RSSI_FLOOR) * 100 // (_RSSI_FULL - _RSSI_FLOOR)
    if rssi >= rssi_min:
        kind = "success"                       # close enough to trade
    elif rssi >= rssi_min - 15:
        kind = "warning"
    else:
        kind = "danger"
    return (badge, pct, kind, "%ddB" % rssi)


def _near_key(near):
    """What changed enough to repaint: ids, links, and signal in 3 dB steps."""
    return tuple((b, via, None if r is None else r // 3) for b, r, via in near)


def _chi_name(cid: str) -> str:
    import character_manager
    cls = character_manager.find(cid)
    return cls.name if cls is not None else cid
