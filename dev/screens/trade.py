"""Collection -> Trade: choose a Chi to offer, then trade it with a badge
chosen from the trade lobby.

    TRADE        collected Chi's; START picks the one to offer
    TRADE lobby  the shared multiplayer lobby (screens/lobby.py): every badge
                 with Trade open, and the Chi it offers, green when it has
                 requested a trade with this badge. START requests a trade
                 (or accepts one, or cancels this badge's request); the trade
                 starts once both badges have requested each other
    TRADING      the exchange (TradeExchangeScreen), then what was sent and
                 received (the new Chi is collected, not made active)

The exchange itself is trade_session.TradeSession. Bluetooth and IR are used
only when enabled in Settings; the LINK cable is always used. Every view
follows Settings -> Badge -> Text Size.
"""
import ui
from buttons import BOOT, SELECT, START
from menu import ListScreen
from screen_manager import Screen


class TradeScreen(ListScreen):
    """Pick the Chi to offer; START opens the trade lobby with it."""

    title = "TRADE"
    message_kind = "muted"

    def __init__(self) -> None:
        super().__init__()
        self._first = True

    def rows(self):
        import character_manager
        active = character_manager.get_active().id
        chars = tuple(character_manager.get_unlocked())
        if self._first:
            self._first = False
            for i, char in enumerate(chars):
                if char.id == active:
                    self.menu.sel = i
        self.message = "Pick a Chi to send"
        return [(c.name, "ACTIVE" if c.id == active else None, c.id) for c in chars]

    def confirm(self):
        return "NEXT"

    def activate(self, mgr) -> None:
        from screens.lobby import LobbyScreen
        from trade_session import TradeSession
        send_id = self.menu.key
        mgr.push(LobbyScreen(
            "TRADE",
            lambda ble, ir: TradeSession(send_id=send_id, ble=ble, ir=ir),
            lambda session: TradeExchangeScreen(session),
            hint=("OPEN TRADE ON", "ANOTHER BADGE")))


class TradeExchangeScreen(Screen):
    """Two badges have agreed: exchange the Chi's, then show the result. The
    lobby owns the session; this screen polls it and pops back when done."""

    def __init__(self, session) -> None:
        self.session = session
        self.result = None           # kept, in case the partner leaves at once
        self._shown = None
        self._leaving = False

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def update(self, display, leds, mgr) -> None:
        s = self.session
        if self._leaving or self.result is not None:
            return
        s.poll()
        if s.result is not None:     # both Chi's exchanged
            self.result = s.result
            self._draw(display)
        elif not s.linked:
            self._leaving = True
            mgr.pop()                # the lobby says LINK LOST
        elif s.message != self._shown:
            self._draw(display)

    def handle_button(self, btn, mgr) -> None:
        if btn in (SELECT, BOOT) or (btn == START and self.result is not None):
            if self.session.linked:
                self.session.leave()
            self._leaving = True
            mgr.pop()

    def _draw(self, display) -> None:
        from trade_session import short_id
        s = self.session
        big = ui.list_scale() == 2
        self._shown = s.message
        if self.result is None:
            ui.screen(display, "TRADING")
            mine = _chi_name(s.send_id).upper()
            status = (s.message, "accent") if s.message else ("TRADING...", "muted")
            ui.scaled_lines(display, (("WITH " + short_id(s.peer or ""), "muted"), "",
                                      ("SENDING", "muted"), mine, "",
                                      status))
            ui.controls(display)
            return
        sent, recv, new = self.result
        ui.screen(display, "TRADE DONE")
        if big:
            ui.scaled_lines(display, (("SENT", "muted"), sent.upper(),
                                      ("GOT", "muted"), (recv.upper(), "accent"),
                                      ("NEW!", "success") if new else ("HAD IT", "muted")))
        else:
            ui.card(display, (("SENT " + sent.upper(), "muted"), ("GOT", "muted"),
                              (recv.upper(), "text"),
                              ("NEW!" if new else "ALREADY HAD", "success" if new else "muted")),
                    y=62, h=92, w=184)
            ui.status(display, "WITH " + short_id(s.peer or ""), 166, "muted")
        ui.controls(display, "OK")


def _chi_name(cid: str) -> str:
    import character_manager
    cls = character_manager.find(cid)
    return cls.name if cls is not None else cid
