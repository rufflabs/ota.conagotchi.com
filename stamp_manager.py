"""Persistent vendor IR stamp collection."""

import os

_STAMP_FILE = "data/stamps.txt"
_MAX_ID = 14
_MAX_NAME = 28

# Badge-to-badge stamp packet protocol.
#
# A stamp is broadcast as a framed link packet (link._make_frame adds the
# OZ/len/checksum envelope) whose payload is:
#
#     SYNC_PREFIX + "<id>:<name>"      e.g.  b"OZS1:vendor1:Vendor 1"
#
# Both the vendor (Vendor screen) and the trade UI (OzConBase Stamps) build the
# payload with make_sync_payload() and parse it with parse_sync_payload().
# collect() is idempotent, so a vendor may broadcast continuously and stamp any
# receiving badge without double-counting. Keep SYNC_PREFIX in sync with the
# receiver in screens/ozconbase.py (_STAMP_SYNC_PREFIX).
SYNC_PREFIX = b"OZS1:"


def all_stamps():
    """Return collected stamps as (id, name) tuples in collection order."""
    return tuple(_load_stamps())


def count() -> int:
    return len(_load_stamps())


def collect(stamp_id: str, name: str) -> bool:
    """Store a vendor stamp. Returns True only when newly collected."""
    stamp_id = _clean_id(stamp_id)
    name = _clean_name(name)
    if not stamp_id:
        return False

    stamps = _load_stamps()
    for existing_id, existing_name in stamps:
        if existing_id == stamp_id:
            if name and existing_name != name:
                _save_stamps(_replace_name(stamps, stamp_id, name))
            return False

    stamps.append((stamp_id, name or stamp_id))
    _save_stamps(stamps)
    return True


def vendor_stamp():
    """Return this badge's configured vendor stamp, or None for attendees."""
    try:
        import config
        stamp_id = _clean_id(getattr(config, "VENDOR_STAMP_ID", ""))
        name = _clean_name(getattr(config, "VENDOR_STAMP_NAME", ""))
    except Exception:
        return None
    if not stamp_id:
        return None
    return stamp_id, name or stamp_id


def pack(stamp_id: str, name: str) -> str:
    """Return a compact packet body for IR transmission."""
    return "{}:{}".format(_clean_id(stamp_id), _clean_name(name))


def unpack(text: str):
    """Parse an IR packet body into (id, name), or None if invalid."""
    if ":" in text:
        stamp_id, name = text.split(":", 1)
    else:
        stamp_id, name = text, text
    stamp_id = _clean_id(stamp_id)
    name = _clean_name(name)
    if not stamp_id:
        return None
    return stamp_id, name or stamp_id


def make_sync_payload(stamp_id: str, name: str) -> bytes:
    """Build a framed stamp packet payload (SYNC_PREFIX + id:name)."""
    return SYNC_PREFIX + pack(stamp_id, name).encode()


def parse_sync_payload(payload: bytes):
    """Parse a received stamp packet payload into (id, name), or None."""
    if not payload.startswith(SYNC_PREFIX):
        return None
    try:
        text = payload[len(SYNC_PREFIX):].decode()
    except Exception:
        return None
    return unpack(text)


def _load_stamps() -> list:
    stamps = []
    try:
        with open(_STAMP_FILE) as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                parsed = unpack(text)
                if parsed is None:
                    continue
                stamp_id, name = parsed
                if not _has_stamp(stamps, stamp_id):
                    stamps.append((stamp_id, name))
    except OSError:
        pass
    return stamps


def _save_stamps(stamps) -> None:
    _ensure_dir()
    with open(_STAMP_FILE, "w") as f:
        for stamp_id, name in stamps:
            stamp_id = _clean_id(stamp_id)
            name = _clean_name(name)
            if stamp_id:
                f.write(pack(stamp_id, name) + "\n")


def _replace_name(stamps, stamp_id: str, name: str) -> list:
    out = []
    for existing_id, existing_name in stamps:
        if existing_id == stamp_id:
            out.append((existing_id, name))
        else:
            out.append((existing_id, existing_name))
    return out


def _has_stamp(stamps, stamp_id: str) -> bool:
    for existing_id, _name in stamps:
        if existing_id == stamp_id:
            return True
    return False


def _clean_id(text: str) -> str:
    out = []
    for ch in str(text).strip().lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in "-_":
            out.append(ch)
        if len(out) >= _MAX_ID:
            break
    return "".join(out)


def _clean_name(text: str) -> str:
    out = []
    for ch in str(text).strip():
        if ch == "|" or ch == ":":
            continue
        if 32 <= ord(ch) <= 126:
            out.append(ch)
        if len(out) >= _MAX_NAME:
            break
    return "".join(out)


def _ensure_dir() -> None:
    try:
        os.mkdir("data")
    except OSError:
        pass
