r"""BLE advertisement (de)coding for badge-to-badge trading.

The trade payloads used over LINK/IR are short text frames like
`OZC1:<char_id>:<badge_id>` / `OZS1:<...>`. BLE legacy advertising only allows
31 bytes total, and `OZC1:freedomchi:aca704316650` (~28 bytes) plus AD framing
overflows that. So this module compacts a trade payload into a manufacturer-
specific AD structure and reverses it exactly on receipt — the trade layer keeps
dealing purely in the original text payloads and never sees the compaction.

Advertisement layout (one AD structure, whole 31-byte budget ours):

    [len][0xFF][CID_lo][CID_hi][kind][ ...compact body... ]
     |    |     \_________/      |
     |    |      company id      1 = char, 2 = stamp, 0 = raw
     |    manufacturer-specific AD type
     total bytes after this length byte

Char body:  [kind=1][clen][char_id ascii][blen][badge_id ascii]
Stamp body: [kind=2][ stamp text bytes ]   (round-tripped verbatim)
Raw body:   [kind=0][ payload bytes ]      (fallback for anything else)

This is pure logic (no `bluetooth` import) so it is host-testable. `BleLink`
in `link.py` calls `encode_adv` / `decode_adv`; the IRQ constants live here too.
"""

# MicroPython bluetooth.BLE().irq() event codes we care about.
IRQ_SCAN_RESULT = 5
IRQ_SCAN_DONE = 6

# Our manufacturer "company id" — an arbitrary 2-byte marker used to recognise
# OzSec badge adverts and ignore everything else in the air.
_CID = b"\x4f\x5a"   # 'OZ'

_KIND_RAW = 0
_KIND_CHAR = 1
_KIND_STAMP = 2

_PREFIX_CHAR = b"OZC1:"
_PREFIX_STAMP = b"OZS1:"

# Total adv_data budget is 31 bytes = [len][type] + manufacturer bytes, so the
# manufacturer bytes (CID + body) must fit in 29.
_MAX_MFG = 29


def _lp(b: bytes) -> bytes:
    """1-byte length-prefixed bytes."""
    return bytes([len(b)]) + b


def encode_adv(payload: bytes):
    """Compact a trade payload into a full adv_data buffer, or None if it will
    not fit in a legacy advertisement."""
    if payload.startswith(_PREFIX_CHAR):
        rest = payload[len(_PREFIX_CHAR):]
        parts = rest.split(b":")
        char = parts[0]
        badge = parts[1] if len(parts) > 1 else b""
        body = bytes([_KIND_CHAR]) + _lp(char) + _lp(badge)
    elif payload.startswith(_PREFIX_STAMP):
        body = bytes([_KIND_STAMP]) + payload[len(_PREFIX_STAMP):]
    else:
        body = bytes([_KIND_RAW]) + payload

    mfg = _CID + body
    if len(mfg) > _MAX_MFG:
        return None
    return bytes([len(mfg) + 1, 0xFF]) + mfg


def decode_adv(adv: bytes):
    """Extract and reconstruct a trade payload from a raw adv_data buffer, or
    None if it is not one of ours."""
    i = 0
    n = len(adv)
    while i + 1 < n:
        ln = adv[i]
        if ln == 0:
            break
        typ = adv[i + 1]
        field = adv[i + 2:i + 1 + ln]   # bytes after the AD type
        if typ == 0xFF and field[:2] == _CID:
            return _decode_body(field[2:])
        i += ln + 1
    return None


def _decode_body(data: bytes):
    if not data:
        return None
    kind = data[0]
    p = data[1:]
    if kind == _KIND_CHAR:
        try:
            cl = p[0]
            char = p[1:1 + cl]
            q = p[1 + cl:]
            bl = q[0]
            badge = q[1:1 + bl]
        except IndexError:
            return None
        return _PREFIX_CHAR + char + b":" + badge
    if kind == _KIND_STAMP:
        return _PREFIX_STAMP + p
    if kind == _KIND_RAW:
        return p
    return None
