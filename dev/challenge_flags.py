"""Read the separately provisioned challenge-ID/flag table; no challenge logic."""
import json

_FLAG_FILE = "challenge_flags.json"
_MAX_FLAG_LENGTH = 64

# Shown when no flag table is provisioned at all, i.e. a development or test
# badge. Deliberately not a real-looking flag: anyone seeing this should know
# immediately that the badge has no event flags on it. A table that exists but
# is malformed, or an entry left blank, still yields None so that a broken
# production table cannot be mistaken for a test badge.
TEST_FLAG = "{TEST_FLAG}"


def get_flag(challenge_id):
    """Return a configured flag, TEST_FLAG when no table is provisioned, or
    None for an invalid table or an unconfigured entry.

    This is only a lookup, and flags are display-only: player completion is
    checked by challenge_manager, so a placeholder can never unlock anything.
    Keep decoding here so a future encrypted format need not change quests.
    """
    try:
        f = open(_FLAG_FILE)
    except OSError:
        return TEST_FLAG
    try:
        rows = json.load(f)
    except ValueError:
        return None
    finally:
        f.close()
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
