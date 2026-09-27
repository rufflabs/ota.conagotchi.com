"""The multiplayer lobby every two-player game shares.

    mgr.push(LobbyScreen("2 PLAYERS", RpsSession,
                         lambda session: RpsScreen(BADGE, session)))

`make_session(ble=..., ir=...)` builds the game's LobbySession (with the
Bluetooth and IR settings); `make_match(session)` builds the game's match
screen, which is pushed once two badges link. The match screen calls
session.poll() from its update(), and when it is done (the player backs out,
or the link drops) calls session.leave() if still linked and pops back here.

The list shows every badge in range with the same game open: its short id,
and a value the game chooses (session.describe): by default REQUESTED,
highlighted in the theme's highlight colours, when it has requested this
badge; INVITED when this badge has invited it; or how it is heard (LINK, BT,
IR). Chi trading shows the Chi each badge offers instead, marked the same
way. START invites the selected badge, accepts its request, or cancels this
badge's own invite (its labels are session.VERBS). The line below, at the
menu text size, says which id this badge is so players can find each other,
that a request arrived, or that an invite lapsed or the link was lost. With
Bluetooth off in Settings, an empty lobby says so, since only a badge on the
cable can then be found. SELECT / BOOT leave the game.
"""
import time

import ui
from buttons import LEFT, RIGHT
from lobby_session import short_id
from menu import ListScreen

_NOTICE_MS = 3000     # "D504 NO ANSWER" / "LINK LOST" show this long


class LobbyScreen(ListScreen):

    def __init__(self, title, make_session, make_match,
                 hint=("OPEN THIS GAME ON", "ANOTHER BADGE")) -> None:
        super().__init__()
        self.title = title
        self._make_session = make_session
        self._make_match = make_match
        self.session = None
        self._no_link = False
        self._notice = None           # (text, kind, until)
        self._shown = None            # (rows, confirm, message) as drawn
        self._in_match = False        # the match screen is open over us
        self._hint = hint             # the empty lobby's last two lines
        self._requests = set()        # badges requesting us, as last seen

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        if self.session is None:
            from settings_state import BadgeSettings
            s = BadgeSettings()
            self.session = self._make_session(ble=s.bluetooth_enabled,
                                              ir=s.ir_enabled)
            self._no_link = not self.session.start()
        await super().enter(display, leds, mgr)

    async def resume(self, display, leds, mgr) -> None:
        """Back from a match: make sure it is over, and say if it dropped."""
        self._in_match = False
        s = self.session
        if s.linked:
            s.leave()
        if s.lost:
            self._say(("LINK LOST", "LINK LOST"), "danger")
            s.lost = False
        await super().resume(display, leds, mgr)

    async def exit(self, display, leds, mgr) -> None:
        if self.session is not None:
            self.session.stop()

    async def update(self, display, leds, mgr) -> None:
        await super().update(display, leds, mgr)
        s = self.session
        if s is None or self._no_link or self._in_match:
            return
        s.poll()
        if s.linked:
            self._in_match = True           # push once; resume() clears it
            mgr.push(self._make_match(s))
            return
        if s.lapsed is not None:
            self._say((short_id(s.lapsed) + " NO ANSWER", "NO ANSWER"), "danger")
            s.lapsed = None
        requests = set(b for b, via, wants in s.players() if wants)
        new = requests - self._requests
        if new:
            who = short_id(sorted(new)[0])
            self._say((who + " REQUESTED", who + " ASKED"), "success")
        self._requests = requests
        self._refresh(display)

    # ── the list ─────────────────────────────────────────────────────────────

    def rows(self):
        s = self.session
        if s is None or self._no_link:
            return []
        rows = []
        for badge, via, wants in s.players():
            value, kind = s.describe(badge, via, wants, badge == s.peer)
            rows.append((short_id(badge), value, badge, kind))
        return rows

    def confirm(self):
        s = self.session
        row = self.menu.item
        if row is None or s is None:
            return None
        badge = row[2]
        if badge == s.peer:
            return s.VERBS[1]
        if any(b == badge and wants for b, via, wants in s.players()):
            return s.VERBS[0]
        return s.VERBS[2]

    def activate(self, mgr) -> None:
        s = self.session
        badge = self.menu.key
        if s.peer == badge:
            s.leave()                     # START on this badge's invite cancels it
        else:
            s.invite(badge)
        self._refresh(mgr._display)

    def handle_button(self, btn: str, mgr) -> None:
        super().handle_button(btn, mgr)
        if btn in (LEFT, RIGHT):          # the list cleared the message line
            self._refresh(mgr._display, force=True)

    # ── drawing ──────────────────────────────────────────────────────────────

    def _say(self, texts, kind) -> None:
        """A notice for the message line: (normal text, large text), since
        only 10 characters fit there at 2x."""
        self._notice = (texts, kind, time.ticks_add(time.ticks_ms(), _NOTICE_MS))

    def _message(self):
        """(text, colour) for the message line, at the menu text size."""
        big = ui.list_scale() == 2
        n = self._notice
        if n is not None and time.ticks_diff(n[2], time.ticks_ms()) > 0:
            return (n[0][1] if big else n[0][0], n[1])
        if self._no_link:
            return ("NO LINK", "danger")
        me = short_id(self.session.me)
        return (("YOU " if big else "YOU ARE ") + me, "accent")

    def draw(self, display) -> None:
        self.reload()                     # a full repaint shows who is here now
        self.message, self.message_kind = self._message()
        ui.screen(display, self.title, marquee=self._title_marquee)
        self._draw_list(display)
        ui.status_row(display, self.message, ui.MESSAGE_Y, self.message_kind,
                      ui.list_scale())
        ui.controls(display, self.confirm())
        self._shown = (self.menu.rows, self.confirm(), (self.message, self.message_kind))

    def _draw_list(self, display) -> None:
        if self.menu.rows:
            self.menu.draw(display)
            return
        big = ui.list_scale() == 2
        if self._no_link:
            rows = (("NOTHING TO", "muted"), ("PLAY OVER", "muted"))
        elif not self.session.radio.use_ble:
            # Easy to miss: badges ship with Bluetooth off, and then only a
            # badge on the cable can be found.
            if big:
                rows = ("SEARCHING", "", ("BT IS OFF", "warning"),
                        ("SETTINGS >", "muted"), ("WIRELESS", "muted"))
            else:
                rows = ("LOOKING FOR", "PLAYERS...", "", ("BLUETOOTH IS OFF", "warning"),
                        ("CABLE ONLY. TURN IT", "muted"), ("ON IN SETTINGS >", "muted"),
                        ("WIRELESS", "muted"))
        elif big:
            rows = ("SEARCHING", (self.session.transports(), "muted"))
        else:
            rows = ("LOOKING FOR", "PLAYERS...", "", (self.session.transports(), "muted"),
                    "", (self._hint[0], "muted"), (self._hint[1], "muted"))
        ui.scaled_lines(display, rows)

    def _refresh(self, display, force=False) -> None:
        """Repaint only what changed: the list area when someone arrives,
        leaves or invites, the message line, and the START verb."""
        rows = self.rows()
        old = self._shown or (None, None, None)
        if rows != old[0]:
            keep = self.menu.key if self.menu.rows else None
            keys = [r[2] for r in rows]
            self.menu.set_rows(rows, select=keys.index(keep) if keep in keys else None)
            ui.clear_band(display, ui.TITLE_PANEL_H, ui.MESSAGE_Y - ui.TITLE_PANEL_H - 2)
            self._draw_list(display)
        message = self._message()
        if force or message != old[2]:
            ui.status_row(display, message[0], ui.MESSAGE_Y, message[1],
                          ui.list_scale())
        confirm = self.confirm()
        if force or rows != old[0] or confirm != old[1]:
            ui.controls(display, confirm)
        self._shown = (rows, confirm, message)
