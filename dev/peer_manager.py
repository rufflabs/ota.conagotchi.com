"""Persistent badge-to-badge trade progress.

Three things, fed by OzConBase during a character sync and wiped by Factory
Reset:

1. **Unique peers** — the set of peer hardware badge ids this badge has traded
   with (`record()` / `count()` / `all_peers()`), persisted in data/peers.txt.
   A peer is identified by its badge id (badge_id.badge_id()), carried in the
   char-trade payload. Storing the set keeps it idempotent: trading with the
   same person again never inflates the total. Drives the "trade with N
   attendees" challenges.

2. **Two-way trade flags** — whether this badge has broadcast its own character
   (`mark_sent`) and received one (`mark_received`), persisted in
   data/trade_flags.txt. `traded_both_ways()` is True once both have happened,
   so "trade a character" completes only on a real exchange — not a debug
   character override or a starter reroll (which would bump the unlocked count
   without any radio trade). This is broadcast-only, so send and receive are not
   guaranteed to involve the *same* peer.

3. Completed character exchanges, saved in data/trade_count.txt. OzConBase
   records at most one per sync session after both a successful send and receipt.
   Repeated characters/peers count; repeated packets in one session do not.
"""
import os

_PEER_FILE = "data/peers.txt"
_FLAG_FILE = "data/trade_flags.txt"
_TRADE_FILE = "data/trade_count.txt"
_SENT = "sent"
_RECV = "recv"
_MAX_ID = 24


def all_peers():
    """Return the recorded peer ids in first-seen order."""
    return tuple(_load())


def count() -> int:
    return len(_load())


def record(peer_id: str) -> bool:
    """Record a peer badge id. Returns True only when newly seen."""
    peer_id = _clean(peer_id)
    if not peer_id:
        return False
    peers = _load()
    if peer_id in peers:
        return False
    peers.append(peer_id)
    _save(peers)
    return True


# ── Two-way trade flags ───────────────────────────────────────────────────────

def mark_sent() -> bool:
    """Note that this badge has broadcast its own character. Returns True if
    newly set (idempotent — only the first call touches flash)."""
    _initialize_trade_count()
    return _set_flag(_SENT)


def mark_received() -> bool:
    """Note that this badge has received a character over the link."""
    _initialize_trade_count()
    return _set_flag(_RECV)


def has_sent() -> bool:
    return _SENT in _load_flags()


def has_received() -> bool:
    return _RECV in _load_flags()


def traded_both_ways() -> bool:
    """True once this badge has both sent and received a character."""
    flags = _load_flags()
    return _SENT in flags and _RECV in flags


def trade_count() -> int:
    """Total exchanges; old boolean-only saves prove at most one exchange."""
    try:
        with open(_TRADE_FILE) as f:
            return max(0, int(f.read().strip()))
    except (OSError, ValueError):
        return 1 if traded_both_ways() else 0


def _initialize_trade_count() -> None:
    # Freeze the legacy baseline before this session changes either flag.
    try:
        with open(_TRADE_FILE):
            return
    except OSError:
        _save_trade_count(trade_count())


def record_completed_trade() -> None:
    """Called once by OzConBase per completed character sync, not per packet."""
    _save_trade_count(trade_count() + 1)


def _save_trade_count(value: int) -> None:
    _ensure_dir()
    with open(_TRADE_FILE, "w") as f:
        f.write(str(value) + "\n")


def _load_flags() -> set:
    flags = set()
    try:
        with open(_FLAG_FILE) as f:
            for line in f:
                text = line.strip()
                if text:
                    flags.add(text)
    except OSError:
        pass
    return flags


def _set_flag(name: str) -> bool:
    flags = _load_flags()
    if name in flags:
        return False
    flags.add(name)
    _ensure_dir()
    with open(_FLAG_FILE, "w") as f:
        for flag in flags:
            f.write(flag + "\n")
    return True


# ── Unique peers ──────────────────────────────────────────────────────────────

def _load() -> list:
    peers = []
    try:
        with open(_PEER_FILE) as f:
            for line in f:
                pid = _clean(line.strip())
                if pid and pid not in peers:
                    peers.append(pid)
    except OSError:
        pass
    return peers


def _save(peers) -> None:
    _ensure_dir()
    with open(_PEER_FILE, "w") as f:
        for pid in peers:
            pid = _clean(pid)
            if pid:
                f.write(pid + "\n")


def _clean(text: str) -> str:
    out = []
    for ch in str(text).strip().lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in "-_":
            out.append(ch)
        if len(out) >= _MAX_ID:
            break
    return "".join(out)


def _ensure_dir() -> None:
    try:
        os.mkdir("data")
    except OSError:
        pass
