"""Rock Paper Scissors, against the badge or against another badge.

RpsModeScreen opens first: 1 Player (a bot on this badge) or 2 Players
(another badge). 2 Players goes through the shared multiplayer lobby
(screens/lobby.py), which opens RpsScreen once two badges link; the rounds
are rps_session.RpsSession.

RpsScreen: LEFT/RIGHT pick Rock, Paper or Scissors, START throws and then
plays again, SELECT or BOOT goes back (to the lobby in 2 Players). In
2 Players a line under the choices shows the opponent CHOOSING, then READY in
green once they have thrown.

Every round is counted in game_scores under "rps": plays, and wins / losses /
draws for badge-vs-badge rounds (bot_wins / bot_losses / bot_draws against
the bot), so challenges can read either. A 2-player round gives both
players' pets XP, more for a win; the bot gives none. A win also makes the pet
a little happier, as in the other games.
"""
import random
import time

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from led_flash import LedFlash
from menu import ListScreen, Menu
from screen_manager import Screen
import game_scores
import rps_session
from rps_session import DRAW, LOSE, WIN
import ui

GAME_ID = "rps"
BOT, BADGE = "bot", "badge"

_NAMES = {"R": "ROCK", "P": "PAPER", "S": "SCISSORS"}
_CHOICES = (("Rock", None, "R"), ("Paper", None, "P"), ("Scissors", None, "S"))

_XP = {WIN: 15, DRAW: 10, LOSE: 5}   # 2 players, per round
_XP_ROUNDS_PER_OPPONENT = 5          # rounds per opponent that give XP, per boot
_xp_rounds = {}                      # opponent id -> rounds rewarded

_BOT_THINK_MS = 700
_FLASH = {WIN: ((0, 40, 0), 300), LOSE: ((50, 0, 0), 300),
          DRAW: ((30, 30, 30), 200)}

_CHOOSE, _WAIT, _RESULT = "choose", "wait", "result"


def _keys(mode):
    """game_scores keys for a mode's wins, losses and draws."""
    pre = "bot_" if mode == BOT else ""
    return {WIN: pre + "wins", LOSE: pre + "losses", DRAW: pre + "draws"}


def record_line(mode) -> str:
    k = _keys(mode)
    return "W %d  L %d  D %d" % tuple(game_scores.get(GAME_ID, k[r])
                                      for r in (WIN, LOSE, DRAW))


class RpsModeScreen(ListScreen):
    """1 Player (the bot) or 2 Players (another badge), with that mode's
    record below."""

    title = "ROCK PAPER SCISSORS"
    message_kind = "muted"

    def rows(self):
        # Short enough to fit a large-text row in every theme.
        return [("1 Player", None, BOT), ("2 Players", None, BADGE)]

    def confirm(self):
        return "PLAY"

    def reload(self) -> None:
        super().reload()
        self.message = record_line(self.menu.key)

    def handle_button(self, btn: str, mgr) -> None:
        super().handle_button(btn, mgr)
        if btn in (LEFT, RIGHT):          # the list cleared the message line
            self.message = record_line(self.menu.key)
            ui.message(mgr._display, self.message, self.message_kind)

    def activate(self, mgr) -> None:
        if self.menu.key == BOT:
            mgr.push(RpsScreen(BOT))
        else:
            from screens.lobby import LobbyScreen
            mgr.push(LobbyScreen("2 PLAYERS", rps_session.RpsSession,
                                 lambda session: RpsScreen(BADGE, session)))


class RpsScreen(Screen):
    """A match: against the bot, or against the badge `session` is linked to."""

    def __init__(self, mode, session=None) -> None:
        self.mode = mode
        self.menu = Menu(_CHOICES)
        self._state = _CHOOSE
        self._session = session
        self._bot = None             # the bot's throw this round
        self._mine = None
        self._until = 0              # end of the bot's think
        self._outcome = None
        self._xp = 0
        self._flash = LedFlash()
        self._leds = None
        self._ready_shown = None     # opponent-ready line as last drawn
        self._leaving = False        # popped back to the lobby already

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        self._leds = leds
        leds.rgb_off()
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        leds.rgb_off()               # the lobby owns the session and its links

    def next_update_ms(self) -> int:
        return 30

    async def update(self, display, leds, mgr) -> None:
        self._flash.tick(leds)
        if self._state == _CHOOSE:
            self.menu.tick(display)
        if self.mode == BOT:
            if (self._state == _WAIT
                    and time.ticks_diff(time.ticks_ms(), self._until) >= 0):
                self._finish(display, mgr, rps_session.outcome(self._mine, self._bot))
            return
        s = self._session
        if self._leaving:
            return
        s.poll()
        if not s.linked and self._state != _RESULT:
            self._leaving = True
            mgr.pop()                # the lobby says LINK LOST
        elif self._state == _WAIT and s.result() is not None:
            self._finish(display, mgr, s.result())
        elif self._state == _CHOOSE and (s.theirs is not None) != self._ready_shown:
            self._draw_ready(display)

    # ── input ────────────────────────────────────────────────────────────────

    def handle_button(self, btn: str, mgr) -> None:
        display = mgr._display
        if btn in (SELECT, BOOT):
            if self._session is not None:
                self._session.leave()          # both go back to the lobby
            mgr.pop()
        elif self._state == _CHOOSE:
            if btn in (LEFT, RIGHT):
                self.menu.step(display, 1 if btn == RIGHT else -1)
            elif btn == START:
                self._throw(display)
        elif self._state == _RESULT and btn == START:
            self._again(display, mgr)

    def _throw(self, display) -> None:
        self._mine = self.menu.key
        self._state = _WAIT
        if self.mode == BOT:
            self._bot = rps_session.CHOICES[random.getrandbits(8) % 3]
            self._until = time.ticks_add(time.ticks_ms(), _BOT_THINK_MS)
        else:
            self._session.choose(self._mine)
        self._draw(display)

    def _again(self, display, mgr) -> None:
        if self.mode == BADGE:
            s = self._session
            if not s.linked:
                mgr.pop()            # they left after the last round
                return
            s.next_round()
        self._state = _CHOOSE
        self._draw(display)

    def _finish(self, display, mgr, result) -> None:
        """Count the round, reward it, and show it."""
        self._outcome = result
        self._state = _RESULT
        game_scores.count_play(GAME_ID)
        game_scores.add(GAME_ID, _keys(self.mode)[result])
        pet = _pet(mgr)
        self._xp = 0
        if self.mode == BADGE:
            peer = self._session.peer
            if _xp_rounds.get(peer, 0) < _XP_ROUNDS_PER_OPPONENT:
                _xp_rounds[peer] = _xp_rounds.get(peer, 0) + 1
                self._xp = _XP[result]
                if pet is not None:
                    pet.gain_xp(self._xp)
        if result == WIN and pet is not None:
            pet.add_happiness(1)
        if self._leds is not None:
            self._flash.start(self._leds, *_FLASH[result])
        self._draw(display)

    # ── drawing ──────────────────────────────────────────────────────────────

    def _opponent(self) -> str:
        if self.mode == BOT:
            return "BOT"
        s = self._session
        return rps_session.short_id(s.peer) if s is not None and s.peer else "?"

    def _draw(self, display) -> None:
        big = ui.list_scale() == 2
        st = self._state
        ui.screen(display, "VS " + self._opponent())
        if st == _CHOOSE:
            self.menu.draw(display)
            if self.mode == BADGE:
                self._draw_ready(display)
            ui.controls(display, "THROW")
            return
        if st == _WAIT:
            waiting = "THINKING..." if self.mode == BOT else "WAITING FOR"
            rows = ("YOU THREW", (_NAMES[self._mine], "accent"), "",
                    (waiting, "muted"))
            if self.mode == BADGE:
                rows += ((self._opponent(), "muted"),)
            ui.scaled_lines(display, rows)
            ui.controls(display)
            return
        # Result
        mine = self._mine
        theirs = self._bot if self.mode == BOT else self._session.theirs
        head = {WIN: ("YOU WIN", "success"), LOSE: ("YOU LOSE", "danger"),
                DRAW: ("DRAW", "warning")}[self._outcome]
        if self._outcome == DRAW:
            detail = (("BOTH THREW", "muted"), _NAMES[mine])
        else:
            win, lose = (mine, theirs) if self._outcome == WIN else (theirs, mine)
            if big:
                detail = (_NAMES[win], ("BEATS", "muted"), _NAMES[lose])
            else:
                detail = ("%s BEATS %s" % (_NAMES[win], _NAMES[lose]),)
        rows = (head, "") + detail
        if self._xp:
            rows += ("", ("+%d XP" % self._xp, "accent"))
        ui.scaled_lines(display, rows)
        ui.controls(display, "AGAIN")

    def _draw_ready(self, display) -> None:
        """Below the choices: the opponent is still choosing, or (green) has
        thrown. Their throw itself stays hidden until both are in."""
        ready = self._session.theirs is not None
        self._ready_shown = ready
        who = self._opponent()
        ui.status_row(display, who + (" READY" if ready else " CHOOSING"),
                      ui.MESSAGE_Y, "success" if ready else "muted")


def _pet(mgr):
    try:
        for screen in reversed(mgr._stack):
            pet = getattr(screen, "_pet", None)
            if pet is not None:
                return pet
    except Exception:
        pass
    return None
