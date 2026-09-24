"""Read the separately provisioned challenge-ID/flag table; no challenge logic."""
import json

_FLAG_FILE = "challenge_flags.json"
_MAX_FLAG_LENGTH = 64


def get_flag(challenge_id):
    """Return a configured flag, or None for missing/invalid configuration.

    This is only a lookup. Player completion is checked by challenge_manager.
    Keep decoding here so a future encrypted format need not change quests.
    """
    try:
        with open(_FLAG_FILE) as f:
            rows = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    flags = {}
    used = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "flag"}:
            return None
        cid, flag = row["id"], row["flag"]
        if (not isinstance(cid, str) or not cid or len(cid) > 64
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in cid)
                or cid in flags or not isinstance(flag, str)):
            return None
        # Empty entries reserve stable IDs without inventing production flags.
        if flag:
            if (not 3 <= len(flag) <= _MAX_FLAG_LENGTH
                    or flag[0] != "{" or flag[-1] != "}"
                    or any(not 33 <= ord(c) <= 126 or c in "{}"
                           for c in flag[1:-1])
                    or flag in used):
                return None
            used.add(flag)
        flags[cid] = flag
    return flags.get(challenge_id) or None
