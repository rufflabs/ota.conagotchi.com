"""The badge-to-badge links as one radio: send to all, read from all.

Opens the LINK cable always, and Bluetooth and IR when asked (the trade's
transports), and treats them as one channel: send() goes out on each, and
read() hands back every packet with the link it came over. IR is skipped
while a cable peer is being heard, as in trades.

Used by every badge-to-badge feature: trade_session (Chi trades),
stamp_session (vendor stamps, Bluetooth only), lobby_session (two-player
games) and blat_session (chat). Bluetooth drops adverts weaker than
`rssi_min` (default config.BLE_RSSI_MIN, about a meter or two); chat passes a
lower value to hear the whole room.

Signing: when the badge holds the shared key file (KEY_FILE, provisioned like
challenge_flags.json and never published), every packet sent gets a TAG_LEN
byte tag (truncated HMAC-SHA256 of the packet) appended, and read() drops any
packet whose tag is missing or wrong, then strips the tag. Without the file,
packets go out and are accepted unsigned. Senders keep TAG_LEN bytes free in
every packet either way, so the formats do not change when a key is added.
A tag shows a packet came from a badge with the key; it does not stop a
recorded packet being played back.

Everything heard is untrusted: tables keyed by what other badges claim use
remember(), which keeps at most MAX_REMEMBERED entries, so a flood of made-up
senders cannot exhaust memory.
"""
import hashlib
import time

KEY_FILE = "radio_key.txt"
TAG_LEN = 3
MAX_REMEMBERED = 100
_BLOCK = 64                # SHA-256 block size, for HMAC
_pads = {}                 # key -> (inner pad, outer pad), worked out once

_LINK_TIMEOUT_MS = 3000   # the cable counts as connected this long after a frame
_READ_LIMITS = (("BT", 6), ("LINK", 4), ("IR", 3))   # packets per read() per link


class BadgeRadio:

    def __init__(self, ble=True, ir=True, links=None, rssi_min=None,
                 key=False, wired=True) -> None:
        self.use_ble = ble
        self.use_wired = wired
        self.use_ir = ir
        self.rssi_min = rssi_min
        self._links = links       # (ble, wired, ir); None = open the real ones
        self._link_seen = None
        # key: bytes to sign with, None for unsigned, False = the key file.
        self.key = load_key() if key is False else key

    def start(self) -> bool:
        """Open the links. False when none could open."""
        if self._links is None:
            check = None
            if self.key:
                key = self.key
                check = lambda packet: verified(key, packet)
            self._links = _open_links(self.use_ble, self.use_wired, self.use_ir,
                                      self.rssi_min, check)
        return any(self._links)

    @property
    def ble(self):
        """The Bluetooth link (for its `heard` / `vendors` signal tables), or None."""
        return self._links[0] if self._links else None

    @property
    def ir(self):
        return self._links[2] if self._links else None

    def stop_advertising(self) -> None:
        """Take this badge's Bluetooth advert off the air (still listening)."""
        if self.ble is not None:
            try:
                self.ble.stop_advertising()
            except Exception:
                pass

    def drain(self) -> None:
        """Throw away everything waiting, e.g. replies from before a new press."""
        while self.read():
            pass

    def stop(self) -> None:
        for link in self._links or ():
            if link is not None:
                try:
                    link.deinit()
                except Exception:
                    pass
        self._links = None

    def send(self, payload: bytes) -> bool:
        """Out on Bluetooth and the cable, and IR while no cable peer is seen.
        Over Bluetooth this replaces the badge's advert until the next send.
        True when at least one link took it."""
        if not self._links:
            return False
        if self.key:
            payload = payload + tag(self.key, payload)
        ble, wired, ir = self._links
        sent = False
        for link in (ble, wired):
            if link is not None:
                sent = _safe_send(link, payload) or sent
        if ir is not None and not self.link_present():
            sent = _safe_send(ir, payload) or sent
        return sent

    def read(self):
        """Packets waiting, as a list of (packet, via)."""
        out = []
        if not self._links:
            return out
        for link, (via, limit) in zip(self._links, _READ_LIMITS):
            if link is None:
                continue
            for _ in range(limit):
                if not link.available():
                    break
                packet = link.read()
                if not packet:
                    continue
                if via == "LINK":
                    self._link_seen = time.ticks_ms()
                if self.key:
                    packet = verified(self.key, packet)
                    if packet is None:
                        continue            # not from a badge with the key
                out.append((packet, via))
        return out

    def link_present(self) -> bool:
        return (self._link_seen is not None
                and time.ticks_diff(time.ticks_ms(), self._link_seen) < _LINK_TIMEOUT_MS)

    def transports(self) -> str:
        names = []
        if self.use_ble:
            names.append("BT")
        names.append("LINK")
        if self.use_ir:
            names.append("IR")
        return " ".join(names)


def load_key():
    """The shared radio key from KEY_FILE (hex), or None when there is no
    usable file: then packets are sent and accepted unsigned."""
    try:
        with open(KEY_FILE) as f:
            text = f.read().strip()
    except OSError:
        return None
    try:
        key = bytes.fromhex(text)
    except (ValueError, AttributeError):
        key = _unhex(text)
    if key is None or len(key) < 16:
        print("badge_radio: ignoring an unusable", KEY_FILE)
        return None
    return key


def _unhex(text):
    """bytes.fromhex for ports without it; None when `text` is not hex."""
    try:
        return bytes(int(text[i:i + 2], 16) for i in range(0, len(text), 2)) \
            if len(text) % 2 == 0 else None
    except ValueError:
        return None


def tag(key: bytes, data: bytes) -> bytes:
    """The first TAG_LEN bytes of HMAC-SHA256(key, data)."""
    pads = _pads.get(key)
    if pads is None:
        k = hashlib.sha256(key).digest() if len(key) > _BLOCK else key
        k = k + bytes(_BLOCK - len(k))
        pads = _pads[key] = (bytes(b ^ 0x36 for b in k), bytes(b ^ 0x5C for b in k))
    inner = hashlib.sha256(pads[0] + data).digest()
    return hashlib.sha256(pads[1] + inner).digest()[:TAG_LEN]


def verified(key: bytes, packet: bytes):
    """`packet` without its tag if the tag is right for `key`, else None."""
    if len(packet) <= TAG_LEN:
        return None
    body = packet[:-TAG_LEN]
    return body if tag(key, body) == packet[-TAG_LEN:] else None


def remember(table: dict, key, value, age=lambda v: v[-1]) -> None:
    """table[key] = value, keeping at most MAX_REMEMBERED entries: a new key
    in a full table replaces the entry whose age(value) (a ticks_ms time,
    the last element by default) is oldest."""
    if key not in table and len(table) >= MAX_REMEMBERED:
        oldest = None
        for k, v in table.items():
            if oldest is None or time.ticks_diff(age(v), age(table[oldest])) < 0:
                oldest = k
        del table[oldest]
    table[key] = value


def _safe_send(link, payload) -> bool:
    try:
        link.send(payload)
        return True
    except Exception:
        return False


def _open_links(use_ble, use_wired, use_ir, rssi_min=None, check=None):
    ble = wired = ir = None
    if use_ble:
        try:
            from link import BleLink
            ble = BleLink(rssi_min=rssi_min, check=check)
        except Exception:
            ble = None
    if use_wired:
        try:
            from link import WiredLink
            wired = WiredLink()
        except Exception:
            wired = None
    if use_ir:
        try:
            from link import IrLink
            ir = IrLink()
        except Exception:
            ir = None
    return (ble, wired, ir)
