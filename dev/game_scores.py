"""Saved game stats, for high scores and for challenges measured from play.

Every game gets its own set of named values, so a new game can keep whatever
it needs (a fastest time, levels cleared, a streak) without new plumbing.

Persistence: data/games.txt (one value per line, cleared by factory reset and
by Debug -> Clear Challenges)

    snake.best=14
    snake.last=9
    snake.plays=6
    snake.beaten=2
    simon.best=9

Values are integers or short strings. The shared helpers use these keys:

    plays    runs started              count_play()
    last     the latest run's score    end_run()
    best     a game's high score       end_run() / record_score() (default key)
    beaten   runs that beat an earlier record, on any key those kept

A game with a different kind of record passes its own key, and says whether
lower is better:

    game_scores.record_score("maze", secs, key="fastest", lower_is_better=True)

Writes happen only when a value changes. Games record a run once, when it
ends, rather than on every point, to keep flash writes down.
"""
import os

_FILE = "data/games.txt"

_cache = None   # {game: {key: value}}, loaded on first use


# ── Reading ──────────────────────────────────────────────────────────────────

def get(game: str, key: str, default=0):
    """One saved value, or `default` when the game has never stored it."""
    return _data().get(game, {}).get(key, default)


def stats(game: str) -> dict:
    """A copy of everything saved for one game."""
    return dict(_data().get(game, {}))


def games() -> list:
    """Every game that has saved anything, in file order."""
    return list(_data())


def total(key: str) -> int:
    """`key` summed over every game (integer values only), e.g. total("beaten")."""
    n = 0
    for values in _data().values():
        v = values.get(key)
        if isinstance(v, int):
            n += v
    return n


# ── Writing ──────────────────────────────────────────────────────────────────

def put(game: str, key: str, value) -> None:
    """Save one value. Nothing is written when it is unchanged."""
    _check(game, key, value)
    values = _data().setdefault(game, {})
    if values.get(key) != value:
        values[key] = value
        _save()


def add(game: str, key: str, amount: int = 1) -> int:
    """Add to an integer counter and return its new value."""
    value = get(game, key) + amount
    put(game, key, value)
    return value


def count_play(game: str) -> int:
    """Count a run started. Returns the new play count."""
    return add(game, "plays")


def record_score(game: str, score: int, key: str = "best",
                 lower_is_better: bool = False) -> bool:
    """Keep `score` if it is a new record for `key`; return True when it is.

    A score that improves on an earlier record also counts one "beaten" for
    the game, which the "beat your high score" challenge reads. A game's first
    record is not a beaten one; nor is a best of 0, which is no score at all.
    """
    _check(game, key, score)
    if not _improve(_data().setdefault(game, {}), key, score, lower_is_better):
        return False
    _save()
    return True


def end_run(game: str, score: int, key: str = "best",
            lower_is_better: bool = False) -> bool:
    """A run has ended: save its score as `last`, and as `key` when it is a
    record (see record_score). One write at most. Returns True for a record."""
    _check(game, key, score)
    values = _data().setdefault(game, {})
    changed = values.get("last") != score
    values["last"] = score
    record = _improve(values, key, score, lower_is_better)
    if changed or record:
        _save()
    return record


def clear() -> None:
    """Forget every game's stats (Debug -> Clear Challenges)."""
    global _cache
    _cache = {}
    try:
        os.remove(_FILE)
    except OSError:
        pass


# ── Internal ─────────────────────────────────────────────────────────────────

def _check(game, key, value) -> None:
    """Names are stored as `game.key=`, so neither may contain '.', '=' or a
    line break; string values may not contain a line break."""
    for name in (game, key):
        if not name or "." in name or "=" in name or "\n" in name:
            raise ValueError("bad game stat name: %r" % (name,))
    if isinstance(value, str) and "\n" in value:
        raise ValueError("game stat values are one line")


def _improve(values: dict, key: str, score, lower_is_better: bool) -> bool:
    """Store `score` under `key` in one game's values if it is a record, and
    count a "beaten" when it improves on an earlier one. Does not save."""
    old = values.get(key)
    if old is None or (old == 0 and not lower_is_better):   # no record yet
        if score <= 0 and not lower_is_better:
            return False
        beaten = False
    else:
        if not (score < old if lower_is_better else score > old):
            return False
        beaten = True
    values[key] = score
    if beaten:
        values["beaten"] = values.get("beaten", 0) + 1
    return True


def _parse(text: str):
    digits = text[1:] if text[:1] == "-" else text
    return int(text) if digits.isdigit() else text


def _data() -> dict:
    global _cache
    if _cache is None:
        _cache = {}
        try:
            with open(_FILE) as f:
                for line in f:
                    name, sep, value = line.strip().partition("=")
                    game, dot, key = name.partition(".")
                    if sep and dot and game and key:
                        _cache.setdefault(game, {})[key] = _parse(value)
        except OSError:
            pass
    return _cache


def _save() -> None:
    try:
        os.mkdir("data")
    except OSError:
        pass
    try:
        with open(_FILE, "w") as f:
            for game, values in _cache.items():
                for key, value in values.items():
                    f.write("{}.{}={}\n".format(game, key, value))
    except OSError as e:
        print("game_scores: save failed:", e)
