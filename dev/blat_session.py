"""BLAT ("Bluetooth At"): a room chat between badges, with no drawing.

Every badge in BLAT beacons its profile, and a message goes out to everyone
in range as numbered pieces that each badge puts back together. The links are
badge_radio.BadgeRadio (Bluetooth, the LINK cable, IR), heard across the room
rather than only close by, and signed when the badge has the radio key.

Packets (each also carries badge_radio's TAG_LEN signature bytes):

    OZN<sender><tag><level><name>          profile, every PROFILE_MS
    OZM<sender><seq><part><count><text>    one piece of a message

    sender   last six hex digits of the badge id
    tag      the active Chi's three letters (ADM, VIB, ...)
    level    that Chi's level, two digits
    name     the display name, up to 8 characters ("" = the badge id)
    seq      message number, one base-36 digit (repeats after 36 messages)
    part     this piece's index and count, base-36 digits
    text     up to PIECE_TEXT characters of the message

A message is at most MAX_TEXT printable ASCII characters. Each piece is sent
for SLOT_MS, and the whole set REPEATS times, so a badge that misses a piece
the first time gets it later.

Everything received is untrusted and bounded: at most MAX_REMEMBERED people
and recently seen messages, MAX_PARTIAL half-received ones, MAX_LOG messages
kept, one message per RECV_GAP_MS from a sender and at most RECV_BURST
messages per RECV_WINDOW_MS from everyone (so made-up senders cannot flood
the log either). Messages are kept in memory only, never saved.
"""
import random
import time

from badge_radio import TAG_LEN, BadgeRadio, remember

PROFILE = b"OZN"
PIECE = b"OZM"
_ADVERT_MAX = 26
PIECE_TEXT = _ADVERT_MAX - TAG_LEN - len(PIECE) - 6 - 3    # 11
MAX_TEXT = 100
NAME_MAX = 8
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"

RSSI_MIN = -100          # hear the whole room, not just the next badge
SLOT_MS = 150            # each piece (or profile) stays on the air this long
REPEATS = 3              # times the whole set of pieces is sent
PROFILE_MS = 2000        # profile beacon interval
SEND_GAP_MS = 5000       # this badge: one message per this long
RECV_GAP_MS = 3000       # one message per sender per this long
RECV_WINDOW_MS = 10000   # and at most RECV_BURST from everyone per window
RECV_BURST = 8
PEOPLE_MS = 60000        # people drop off the list after this long unheard
PARTIAL_MS = 15000       # a message still missing pieces is dropped after this
MAX_PARTIAL = 32
MAX_LOG = 40


def short_id(badge: str) -> str:
    return badge[-4:].upper() if badge else "----"


def printable(text: str) -> str:
    return "".join(c for c in text if 32 <= ord(c) <= 126)


def pack_profile(me, tag, level, name) -> bytes:
    level = max(0, min(99, int(level)))
    tag = (printable(tag).upper() + "???")[:3]
    return PROFILE + ("%s%s%02d%s" % (me, tag, level, printable(name)[:NAME_MAX])).encode()


def pieces(me, seq, text):
    """The packets carrying one message."""
    text = printable(text)[:MAX_TEXT]
    chunks = [text[i:i + PIECE_TEXT] for i in range(0, len(text), PIECE_TEXT)] or [""]
    n = len(chunks)
    return [PIECE + ("%s%s%s%s%s" % (me, _DIGITS[seq % 36], _DIGITS[i], _DIGITS[n],
                                     chunk)).encode()
            for i, chunk in enumerate(chunks)]


def parse(packet: bytes):
    """("profile", sender, tag, level, name) or ("piece", sender, seq, part,
    count, text), or None for anything malformed."""
    try:
        text = packet.decode()
    except Exception:
        return None
    if printable(text) != text:
        return None
    kind, body = text[:3], text[3:]
    sender = body[:6].upper()
    if len(sender) != 6 or any(c not in "0123456789ABCDEF" for c in sender):
        return None
    if kind == "OZN":
        if len(body) < 11 or not body[9:11].isdigit():
            return None
        return ("profile", sender, body[6:9], int(body[9:11]), body[11:11 + NAME_MAX])
    if kind == "OZM":
        if len(body) < 9:
            return None
        seq, part, count = (_DIGITS.find(c) for c in body[6:9].lower())
        if min(seq, part, count) < 0 or not 0 <= part < count <= _max_pieces():
            return None
        return ("piece", sender, seq, part, count, body[9:9 + PIECE_TEXT])
    return None


def _max_pieces():
    return (MAX_TEXT + PIECE_TEXT - 1) // PIECE_TEXT


class BlatSession:

    def __init__(self, name="", tag="CHI", level=0, ble=True, ir=True, me=None,
                 links=None, key=False) -> None:
        self.radio = BadgeRadio(ble, ir, links, rssi_min=RSSI_MIN, key=key)
        self.me = (me if me is not None else _my_badge())[-6:].upper()
        self.running = False
        self.messages = []        # (name, tag, level, text, mine), newest last
        self.version = 0          # bumps with every new message
        self.unread = 0
        self._people = {}         # sender -> (name, tag, level, ticks heard)
        self._partial = {}        # (sender, seq) -> (count, {part: text}, ticks)
        self._seen = {}           # (sender, seq) -> ticks completed
        self._last_from = {}      # sender -> ticks of its last message
        self._recent = []         # ticks of messages accepted in the window
        self._seq = random.getrandbits(8) % 36   # so a reboot does not repeat one
        self._out = []            # packets still to send, in order
        self._next_slot = 0
        self._next_profile = 0
        self._last_send = None
        self.set_profile(name, tag, level)

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if not self.running:
            self.running = self.radio.start()
            self._next_slot = self._next_profile = time.ticks_ms()
        return self.running

    def stop(self) -> None:
        self.radio.stop()
        self.running = False

    def poll(self) -> None:
        """Call from the screen's update(): read, expire, and send the next
        piece or profile when its slot comes round."""
        if not self.running:
            return
        now = time.ticks_ms()
        for packet, via in self.radio.read():
            self.handle_packet(packet, now)
        for key in [k for k, v in self._partial.items()
                    if time.ticks_diff(now, v[2]) >= PARTIAL_MS]:
            del self._partial[key]
        if time.ticks_diff(now, self._next_slot) < 0:
            return
        self._next_slot = time.ticks_add(now, SLOT_MS)
        if self._out and time.ticks_diff(now, self._next_profile) < 0:
            self.radio.send(self._out.pop(0))
        else:
            self.radio.send(self._profile)
            self._next_profile = time.ticks_add(now, PROFILE_MS)

    # ── this badge ───────────────────────────────────────────────────────────

    def set_profile(self, name, tag, level) -> None:
        self.name = printable(name)[:NAME_MAX] or short_id(self.me)
        self.tag = (printable(tag).upper() + "???")[:3]
        self.level = max(0, min(99, int(level)))
        self._profile = pack_profile(self.me, self.tag, self.level,
                                     "" if self.name == short_id(self.me) else self.name)
        self._next_profile = time.ticks_ms()

    def wait_ms(self) -> int:
        """How long until this badge may send again (0: now)."""
        if self._last_send is None:
            return 0
        return max(0, SEND_GAP_MS - time.ticks_diff(time.ticks_ms(), self._last_send))

    @property
    def sending(self) -> bool:
        return bool(self._out)

    def send(self, text) -> bool:
        """Queue a message for everyone in range. False when it is empty or
        this badge sent one less than SEND_GAP_MS ago."""
        text = printable(text).strip()[:MAX_TEXT]
        if not text or self.wait_ms() > 0:
            return False
        self._last_send = time.ticks_ms()
        packets = pieces(self.me, self._seq, text)
        self._seq = (self._seq + 1) % 36
        self._out = packets * REPEATS
        self._next_slot = time.ticks_ms()
        self._log(self.name, self.tag, self.level, text, True)
        return True

    # ── others ───────────────────────────────────────────────────────────────

    def people(self):
        """Badges heard within PEOPLE_MS as (id, name, tag, level), by name."""
        now = time.ticks_ms()
        rows = [(b, p[0], p[1], p[2]) for b, p in self._people.items()
                if time.ticks_diff(now, p[3]) < PEOPLE_MS]
        rows.sort(key=lambda r: r[1].upper())
        return rows

    def handle_packet(self, packet: bytes, now=None) -> None:
        now = time.ticks_ms() if now is None else now
        parsed = parse(packet)
        if parsed is None or parsed[1] == self.me:
            return
        if parsed[0] == "profile":
            _, sender, tag, level, name = parsed
            remember(self._people, sender, (name or short_id(sender), tag, level, now))
            return
        _, sender, seq, part, count, text = parsed
        key = (sender, seq)
        if key in self._seen and time.ticks_diff(now, self._seen[key]) < PEOPLE_MS:
            return                                   # a repeat of one we have
        got = self._partial.get(key)
        if got is None or got[0] != count:
            got = (count, {}, now)
        got[1][part] = text
        if len(got[1]) < count:
            remember(self._partial, key, got, age=lambda v: v[2])
            while len(self._partial) > MAX_PARTIAL:
                oldest = min(self._partial, key=lambda k: self._partial[k][2])
                del self._partial[oldest]
            return
        self._partial.pop(key, None)
        remember(self._seen, key, now, age=lambda v: v)
        if not self._accept(sender, now):
            return
        message = "".join(got[1][i] for i in range(count))
        profile = self._people.get(sender)
        if profile is None:
            self._log(short_id(sender), None, None, message, False)
        else:
            self._log(profile[0], profile[1], profile[2], message, False)

    def _accept(self, sender, now) -> bool:
        """Rate limits: per sender, and for everyone together."""
        last = self._last_from.get(sender)
        if last is not None and time.ticks_diff(now, last) < RECV_GAP_MS:
            return False
        self._recent = [t for t in self._recent
                        if time.ticks_diff(now, t) < RECV_WINDOW_MS]
        if len(self._recent) >= RECV_BURST:
            return False
        self._recent.append(now)
        remember(self._last_from, sender, now, age=lambda v: v)
        return True

    def _log(self, name, tag, level, text, mine) -> None:
        self.messages.append((name, tag, level, text, mine))
        del self.messages[:-MAX_LOG]
        self.version += 1
        if not mine:
            self.unread += 1


def line(message, clean=None) -> str:
    """A message as shown: "Ruff ADM3: Hi!", or "D4E6: Hi!" before the
    sender's profile has arrived. `clean` filters the name and text."""
    name, tag, level, text, mine = message
    if clean is not None:
        name, text = clean(name), clean(text)
    if tag is None:
        return "%s: %s" % (name, text)
    return "%s %s%d: %s" % (name, tag, level, text)


def _my_badge() -> str:
    try:
        import badge_id
        return badge_id.badge_id()
    except Exception:
        return ""
