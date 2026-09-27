"""Badge-to-badge multiplayer: the lobby, invites and the link, for any game.

A two-player game subclasses LobbySession and adds only its own rules, then
opens screens.lobby.LobbyScreen with it: the lobby lists players, handles
invites and hands over to the game's match screen once two badges link.
Changes here reach every multiplayer game.

    class ChessSession(LobbySession):
        GAME = "C"                      # one letter, unique per game
        def payload(self):              # what this badge tells its opponent
            return "e2e4"               #   (at most PAYLOAD_MAX characters)
        def on_payload(self, text):     # what the opponent last told us
            ...
        def reset_match(self):          # a new opponent (or none)
            ...
        def note(self):                 # optional: shown to others in the lobby
            return "ELO"                #   (at most NOTE_MAX characters)
        def describe(self, badge, via, requested, invited):
            ...                         # optional: a lobby row's value text

The links are badge_radio.BadgeRadio: the LINK cable always, Bluetooth and
IR when enabled in Settings (Bluetooth only accepts close badges; IR is used
only while no cable peer is seen). Every packet is one beacon, repeated:

    OZG<game>:<sender>:<to>:<payload>

    game     the game's letter, so each game's lobby lists only its players
    sender   the last six hex digits of the sender's badge id (the part that
             differs between badges)
    to       the invited or linked opponent's six digits, or ------ while
             just in the lobby
    payload  the game's state for its opponent while linked; in the lobby,
             NOTE_MARK and the badge's note (e.g. the Chi a trade offers)

A Bluetooth advert carries 26 bytes. The radio keeps TAG_LEN (3) of them for
its signature (see badge_radio), which leaves PAYLOAD_MAX (4) for the payload:
a game's payload never starts with NOTE_MARK, and a note is NOTE_MAX (3). The
mark keeps the two apart even at the moment two badges link, when one side
already sends match data and the other still sends its note.

Pairing is chosen by the players, on every transport alike (so a badge on
the cable can still play someone over Bluetooth). Every badge in the lobby
beacons, so each lists the others (players()). Inviting one addresses it;
the two are linked once each has invited the other, and an invite not
returned within INVITE_MS lapses. A linked pair ignores other badges, and
leaving a match (or going quiet for LOST_MS) returns both to the lobby.
"""
import random
import time

from badge_radio import TAG_LEN, BadgeRadio, remember

ANYONE = "------"
_ADVERT_MAX = 26                 # what one Bluetooth advert carries for us
PAYLOAD_MAX = _ADVERT_MAX - TAG_LEN - len("OZGx:123456:123456:")
NOTE_MARK = "~"
NOTE_MAX = PAYLOAD_MAX - len(NOTE_MARK)

_BEACON_MS = 300          # beacon interval, plus jitter
_BEACON_JITTER_MS = 150
INVITE_MS = 20000         # an invite not returned within this lapses
LOST_MS = 6000            # a linked opponent silent this long is gone
NEARBY_MS = 4000          # a lobby badge silent this long drops off the list
_LINK_TIMEOUT_MS = 3000   # a lobby badge counts as on the cable this long


def wire_id(badge: str) -> str:
    """The six hex digits that identify a badge on the air."""
    return badge[-6:].upper() if badge else ANYONE


def short_id(badge: str) -> str:
    """The four hex digits a player sees ("YOU ARE D4FC")."""
    return badge[-4:].upper() if badge else "----"


def pack(game, me, to, payload="") -> bytes:
    if len(payload) > PAYLOAD_MAX or ":" in payload:
        raise ValueError("lobby payload too long")
    return "OZG{}:{}:{}:{}".format(game, wire_id(me), to, payload).encode()


def parse(packet: bytes):
    """(game, sender, to, payload), or None."""
    if not packet.startswith(b"OZG") or len(packet) < 5:
        return None
    try:
        head, sender, to, payload = packet.decode().split(":")
    except Exception:
        return None
    if len(head) != 4 or len(sender) != 6 or len(to) != 6:
        return None
    return head[3], sender.upper(), to.upper(), payload


class LobbySession:
    """The lobby and link for one game. Subclasses set GAME and override
    payload(), on_payload() and reset_match()."""

    GAME = "?"
    # START's label in the lobby: on a badge that requested us, on the badge
    # this one invited, and on any other badge.
    VERBS = ("PLAY", "CANCEL", "INVITE")

    def __init__(self, ble=True, ir=True, me=None, links=None, key=False) -> None:
        self.radio = BadgeRadio(ble, ir, links, key=key)
        self.me = wire_id(me if me is not None else _my_badge())
        self.running = False
        self.peer = None          # six-digit id of the badge invited or linked
        self.linked = False       # both badges address each other
        self.lapsed = None        # a badge whose invite just lapsed, to say so
        self.lost = False         # a linked opponent just went away
        self._peer_since = 0
        self._peer_seen = 0
        self._next_beacon = 0
        # id -> (last wireless via or None, invites us, ticks heard on any
        #        link, ticks heard on the cable or None, lobby note)
        self._lobby = {}

    # ── for the game to override ─────────────────────────────────────────────

    def payload(self) -> str:
        """This badge's state for its opponent, sent while linked."""
        return ""

    def on_payload(self, text: str) -> None:
        """The linked opponent's latest payload."""

    def reset_match(self) -> None:
        """A new opponent, or none: forget the match state."""

    def note(self) -> str:
        """Shown to other badges while in the lobby (at most NOTE_MAX)."""
        return ""

    def describe(self, badge, via, requested, invited):
        """A lobby row's value and how it is drawn: a theme colour name for
        the value, or "highlight" for the whole row (the theme's hl_fg on
        hl_bg) when the row needs attention."""
        if requested:
            return ("REQUESTED", "highlight")
        if invited:
            return ("INVITED", "accent")
        return (via, "muted")

    def note_of(self, badge) -> str:
        """The note `badge` last sent in the lobby, or ""."""
        entry = self._lobby.get(badge)
        return entry[4] if entry else ""

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open the links and join the lobby. False when none could open."""
        if self.running:
            return True
        if not self.radio.start():
            return False
        self.running = True
        self._drop_peer()
        self._next_beacon = time.ticks_ms()
        return True

    def stop(self) -> None:
        self.radio.stop()
        self.running = False
        self.linked = False

    def poll(self) -> None:
        """Call from the screen's update(): read, time out, beacon."""
        if not self.running:
            return
        now = time.ticks_ms()
        for packet, via in self.radio.read():
            self.handle_packet(packet, via)
        if self.peer is not None:
            if self.linked and time.ticks_diff(now, self._peer_seen) >= LOST_MS:
                self._drop_peer(lost=True)
            elif (not self.linked
                  and time.ticks_diff(now, self._peer_since) >= INVITE_MS):
                self.lapsed = self.peer
                self._drop_peer()
        if time.ticks_diff(now, self._next_beacon) >= 0:
            self._beacon()
            self.beacon_soon(_BEACON_MS + random.randint(0, _BEACON_JITTER_MS))

    def beacon_soon(self, ms=0) -> None:
        """Send the next beacon in `ms` (0: straight away, e.g. after a move)."""
        self._next_beacon = time.ticks_add(time.ticks_ms(), ms)

    # ── the lobby ────────────────────────────────────────────────────────────

    def players(self):
        """Badges in range with this game open, as (id, via, invites us),
        heard within NEARBY_MS, in a stable order: those inviting us first."""
        now = time.ticks_ms()
        rows = []
        for b, (air, wants, seen, cable, note) in self._lobby.items():
            if time.ticks_diff(now, seen) >= NEARBY_MS:
                continue
            # LINK only while the cable itself is carrying them.
            on_cable = (cable is not None
                        and time.ticks_diff(now, cable) < _LINK_TIMEOUT_MS)
            rows.append((b, "LINK" if on_cable or air is None else air, wants))
        rows.sort(key=lambda r: (not r[2], r[0]))
        return rows

    def invite(self, badge) -> None:
        """Invite `badge` (replacing any invite); linked once it invites us."""
        if self.linked or badge == self.me:
            return
        self._drop_peer()
        self.peer = badge
        self._peer_since = self._peer_seen = time.ticks_ms()
        self.lapsed = None
        self.beacon_soon()

    def leave(self) -> None:
        """Cancel an invite, or leave a match, and go back to the lobby."""
        self._drop_peer()
        self.beacon_soon()

    def transports(self) -> str:
        return self.radio.transports()

    # ── packets ──────────────────────────────────────────────────────────────

    def handle_packet(self, packet: bytes, via: str = "LINK") -> None:
        parsed = parse(packet)
        if parsed is None:
            return
        game, sender, to, payload = parsed
        if game != self.GAME or sender == self.me:
            return
        now = time.ticks_ms()
        old = self._lobby.get(sender)
        air, cable, note = (old[0], old[3], old[4]) if old else (None, None, "")
        if via == "LINK":
            cable = now
        else:
            air = via
        is_note = payload.startswith(NOTE_MARK)
        if is_note:
            note = payload[len(NOTE_MARK):len(NOTE_MARK) + NOTE_MAX]
        # At most MAX_REMEMBERED players, so made-up senders cannot fill memory.
        remember(self._lobby, sender, (air, to == self.me, now, cable, note),
                 age=lambda v: v[2])
        if sender != self.peer:
            return
        self._peer_seen = now
        if to != self.me:
            if self.linked:                      # they left the match
                self._drop_peer(lost=True)
            return                               # an invite not returned yet
        if not self.linked:
            self.linked = True
            self.lost = False
        if payload and not is_note:
            self.on_payload(payload)

    def _drop_peer(self, lost=False) -> None:
        self.peer = None
        self.linked = False
        self.lost = lost
        self.reset_match()

    def _beacon(self) -> None:
        to = self.peer if self.peer else ANYONE
        if self.linked:
            payload = self.payload()
        else:
            note = self.note()[:NOTE_MAX]
            payload = NOTE_MARK + note if note else ""
        self.radio.send(pack(self.GAME, self.me, to, payload))


def _my_badge() -> str:
    try:
        import badge_id
        return badge_id.badge_id()
    except Exception:
        return ""
