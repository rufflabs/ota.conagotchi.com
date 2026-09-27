"""Manages the active challenge selection and completion tracking.

Persistence: data/challenges.txt  (key=value, one per line)

Format:
    active=challenge_id      # omitted or empty if none selected
    done=completed_id_1      # one line per completed challenge
    done=completed_id_2
    …
"""

import os
from challenges import CHALLENGES

_STATE_FILE = "data/challenges.txt"


def get_active():
    """Return an instance of the active Challenge, or None if none selected."""
    cid = _load().get("active")
    if not cid:
        return None
    for cls in CHALLENGES:
        if cls.id == cid:
            return cls()
    return None


def get_active_id() -> str:
    """Return the active challenge id, or "" if none.

    Lighter than get_active(): reads the id without constructing the Challenge,
    so callers can detect a change of active challenge without resetting a
    live challenge's baseline state.
    """
    return _load().get("active", "")


def set_active(challenge_id) -> None:
    """Set the active challenge by ID.  Pass None to clear."""
    data = _load()
    data["active"] = challenge_id or ""
    _save(data)


def get_completed() -> list:
    """Return the list of completed challenge IDs."""
    return _load().get("completed", [])


def is_completed(challenge_id: str) -> bool:
    """Return True if the given challenge has been completed."""
    return challenge_id in _load().get("completed", [])


def get_completed_flag(challenge_id: str):
    """Reveal only a registered, available CTF quest's locally earned flag.
    A badge-only challenge (is_ctf False) never shows one, even if the table
    happens to have a row for it."""
    cls = next((c for c in CHALLENGES if c.id == challenge_id), None)
    if cls is None or not getattr(cls, "is_ctf", False) or not is_completed(challenge_id):
        return None
    if cls.character:
        import character_manager
        if not character_manager.is_unlocked(cls.character):
            return None
    import challenge_flags
    return challenge_flags.get_flag(challenge_id)


def mark_complete(challenge_id: str) -> None:
    """Record a challenge as completed and clear it as the active challenge."""
    data = _load()
    if challenge_id not in data["completed"]:
        data["completed"].append(challenge_id)
    if data.get("active") == challenge_id:
        data["active"] = ""
    _save(data)


# ── Internal ──────────────────────────────────────────────────────────────────

def reset_progress() -> int:
    """Forget every challenge's progress (debug): completions, lab progress,
    and the trade history and game stats the quests are measured from.
    Stamps, characters and pet state are untouched. Returns the number of
    files removed."""
    import os
    import game_scores
    import peer_manager
    game_scores.clear()        # its file and its in-memory copy
    paths = [_STATE_FILE, peer_manager._PEER_FILE, peer_manager._FLAG_FILE,
             peer_manager._TRADE_FILE]
    try:
        paths += ["data/" + n for n in os.listdir("data")
                  if n.startswith("lab_") and n.endswith(".json")]
    except OSError:
        pass
    removed = 0
    for path in paths:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


def _load() -> dict:
    result = {"active": "", "completed": []}
    try:
        with open(_STATE_FILE) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k == "active":
                    result["active"] = v
                elif k == "done" and v:
                    result["completed"].append(v)
    except OSError:
        pass
    return result


def _save(data: dict) -> None:
    try:
        os.mkdir("data")
    except OSError:
        pass
    with open(_STATE_FILE, "w") as f:
        f.write("active={}\n".format(data.get("active") or ""))
        for cid in data.get("completed", []):
            f.write("done={}\n".format(cid))
