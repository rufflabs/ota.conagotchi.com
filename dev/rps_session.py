"""Rock Paper Scissors rounds between two linked badges, with no drawing.

The lobby, invites and links come from lobby_session.LobbySession; this adds
only the rounds. The payload each badge sends its opponent is three
characters:

    <round><choice><previous choice>

    round     0-9, counting up (mod 10) with each round of a match
    choice    R, P or S once thrown in this round, else ?
    previous  the choice thrown in the round before, else -

A round resolves when this badge holds both choices for the same round. The
previous-choice field means a player who resolves and presses AGAIN at once
still delivers their throw to an opponent who had not heard it yet. Choices
travel in the clear: the badge only shows the opponent's throw once both are
in.
"""
from lobby_session import LobbySession, short_id  # noqa: F401 (re-exported)

CHOICES = "RPS"
_BEATS = {"R": "S", "P": "R", "S": "P"}

WIN, LOSE, DRAW = "win", "lose", "draw"


def outcome(mine, theirs):
    """WIN, LOSE or DRAW for this badge."""
    if mine == theirs:
        return DRAW
    return WIN if _BEATS[mine] == theirs else LOSE


class RpsSession(LobbySession):

    GAME = "R"

    def __init__(self, *args, **kwargs) -> None:
        self.round = 0
        self.mine = None          # this round's throw
        self._prev = None         # last round's throw
        self._theirs = {}         # round -> the opponent's throw
        super().__init__(*args, **kwargs)

    # ── LobbySession hooks ───────────────────────────────────────────────────

    def payload(self) -> str:
        return "%d%s%s" % (self.round % 10, self.mine or "?", self._prev or "-")

    def on_payload(self, text: str) -> None:
        try:
            rnd, choice, prev = int(text[0]), text[1], text[2]
        except (ValueError, IndexError):
            return
        # Only this round and the next are kept, so a throw repeated from an
        # old round can never be read as one ten rounds later.
        now_r, next_r = self.round % 10, (self.round + 1) % 10
        if choice in CHOICES and rnd in (now_r, next_r):
            self._theirs[rnd] = choice
        if prev in CHOICES and (rnd - 1) % 10 == now_r:
            self._theirs.setdefault(now_r, prev)

    def reset_match(self) -> None:
        self.round = 0
        self.mine = None
        self._prev = None
        self._theirs = {}

    # ── the match ────────────────────────────────────────────────────────────

    def choose(self, choice) -> None:
        """Throw for this round (once)."""
        if self.linked and self.mine is None and choice in CHOICES:
            self.mine = choice
            self.beacon_soon()                   # tell them straight away

    @property
    def theirs(self):
        """The opponent's throw this round, once known."""
        return self._theirs.get(self.round % 10)

    def result(self):
        """WIN / LOSE / DRAW once both have thrown this round, else None."""
        if self.mine is None or self.theirs is None:
            return None
        return outcome(self.mine, self.theirs)

    def next_round(self) -> None:
        """After a result: play again with the same opponent."""
        if self.result() is None:
            return
        self._prev = self.mine
        self.mine = None
        self.round += 1
        keep = self._theirs.get(self.round % 10)
        self._theirs = {} if keep is None else {self.round % 10: keep}
        self.beacon_soon()
