"""Vendor stamps: what an attendee collected, and what a vendor stamped.

A vendor ID is four characters, A-Z and 0-9, padded on the left with zeros
("1A" -> "001A"). Stamping is two-way over Bluetooth (stamp_session.py):

    vendor    beacons  OZS1:<vendor id>:<vendor badge id>
    attendee  collects it, then replies OZA1:<vendor id>:<attendee badge id>
    vendor    records the attendee's badge id from the reply

Files (all under data/, cleared by factory reset):
    stamps.txt    attendee: one "<vendor id>:<vendor badge id>" per stamp
    vendor.txt    vendor: this badge's vendor ID
    stamped.txt   vendor: one attendee badge id per line
"""
import os

VENDOR_ID_LEN = 4
STAMP_PREFIX = b"OZS1:"
ACK_PREFIX = b"OZA1:"

_STAMP_FILE = "data/stamps.txt"
_VENDOR_FILE = "data/vendor.txt"
_STAMPED_FILE = "data/stamped.txt"
_MAX_BADGE = 16


# ── Vendor IDs ───────────────────────────────────────────────────────────────

def normalize_vendor_id(text) -> str:
    """Upper-case letters/digits only, at most four, zero-padded on the left.
    Returns "" when nothing usable remains."""
    out = []
    for ch in str(text).strip().upper():
        if ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            out.append(ch)
    vid = "".join(out)[:VENDOR_ID_LEN]
    if not vid:
        return ""
    return "0" * (VENDOR_ID_LEN - len(vid)) + vid


def _clean_badge(text) -> str:
    out = []
    for ch in str(text).strip().lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
    return "".join(out)[:_MAX_BADGE]


# ── Packets ──────────────────────────────────────────────────────────────────

def stamp_payload(vendor_id: str, badge: str) -> bytes:
    """What a vendor beacons."""
    return STAMP_PREFIX + "{}:{}".format(vendor_id, badge).encode()


def ack_payload(vendor_id: str, badge: str) -> bytes:
    """An attendee's reply after collecting a stamp."""
    return ACK_PREFIX + "{}:{}".format(vendor_id, badge).encode()


def parse(payload: bytes, prefix: bytes):
    """(vendor id, badge id) from a stamp or ack packet, or None."""
    if not payload.startswith(prefix):
        return None
    try:
        text = payload[len(prefix):].decode()
    except Exception:
        return None
    vid, _, badge = text.partition(":")
    vid = normalize_vendor_id(vid)
    badge = _clean_badge(badge)
    if not vid or not badge:
        return None
    return vid, badge


# ── Attendee: collected stamps ───────────────────────────────────────────────

def all_stamps():
    """Collected stamps as (vendor id, stamping badge id), oldest first."""
    return tuple(_load_pairs(_STAMP_FILE))


def count() -> int:
    return len(_load_pairs(_STAMP_FILE))


def has(vendor_id: str) -> bool:
    vid = normalize_vendor_id(vendor_id)
    return any(v == vid for v, _ in _load_pairs(_STAMP_FILE))


def collect(vendor_id: str, badge: str) -> bool:
    """Store a vendor's stamp. Returns True only when newly collected; one
    stamp per vendor ID, whichever of its badges stamped first."""
    vid = normalize_vendor_id(vendor_id)
    badge = _clean_badge(badge)
    if not vid:
        return False
    stamps = _load_pairs(_STAMP_FILE)
    if any(v == vid for v, _ in stamps):
        return False
    stamps.append((vid, badge))
    _save_lines(_STAMP_FILE, ["{}:{}".format(v, b) for v, b in stamps])
    return True


# ── Vendor: this badge's ID and who it stamped ───────────────────────────────

def vendor_id() -> str:
    """This badge's vendor ID, or "" when none is set."""
    try:
        with open(_VENDOR_FILE) as f:
            return normalize_vendor_id(f.read())
    except OSError:
        return ""


def set_vendor_id(text) -> str:
    """Save a vendor ID (normalized); returns what was saved ("" clears it)."""
    vid = normalize_vendor_id(text)
    _save_lines(_VENDOR_FILE, [vid] if vid else [])
    return vid


def stamped():
    """Attendee badge ids this vendor has stamped, oldest first."""
    out = []
    try:
        with open(_STAMPED_FILE) as f:
            for line in f:
                badge = _clean_badge(line)
                if badge and badge not in out:
                    out.append(badge)
    except OSError:
        pass
    return out


def record_stamped(badge: str) -> bool:
    """Note an attendee badge that acknowledged our stamp. True when new."""
    badge = _clean_badge(badge)
    if not badge:
        return False
    seen = stamped()
    if badge in seen:
        return False
    _ensure_dir()
    with open(_STAMPED_FILE, "a") as f:
        f.write(badge + "\n")
    return True


def clear() -> int:
    """Forget collected stamps and the vendor's stamped log (debug). The vendor
    ID is kept. Returns how many entries were removed."""
    removed = count() + len(stamped())
    for path in (_STAMP_FILE, _STAMPED_FILE):
        try:
            os.remove(path)
        except OSError:
            pass
    return removed


# ── Files ────────────────────────────────────────────────────────────────────

def _load_pairs(path):
    pairs = []
    try:
        with open(path) as f:
            for line in f:
                vid, _, badge = line.strip().partition(":")
                vid = normalize_vendor_id(vid)
                if vid and len(vid) == VENDOR_ID_LEN and not any(v == vid for v, _ in pairs):
                    pairs.append((vid, _clean_badge(badge)))
    except OSError:
        pass
    return pairs


def _save_lines(path, lines) -> None:
    _ensure_dir()
    with open(path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def _ensure_dir() -> None:
    try:
        os.mkdir("data")
    except OSError:
        pass
