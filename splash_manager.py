"""Boot splash selection + persistence.

Splash images live under ``img/splash/``:

* ``img/splash/*.bin``          — the *regular* pool, one of which is chosen at
                                  random on boot when no explicit selection is
                                  stored.
* ``img/splash/special/*.bin``  — *special* screens (e.g. the max-level cloud
                                  splash) that are only shown when selected.

The chosen splash is persisted to ``data/splash.txt`` as a ``selected=<name>``
line, where ``<name>`` is relative to ``img/splash/`` — e.g. ``logo.bin`` or
``special/clouds.bin``.  A blank/absent selection means "auto": a regular
splash is picked fresh on every boot.  ``data/`` is wiped by Factory Reset, so
the selection resets with everything else — the firmware uses no ESP32 NVS.
"""
import os
import random

_DIR         = "img/splash"
_SPECIAL_SUB = "special"
_SPECIAL_DIR = _DIR + "/" + _SPECIAL_SUB
_SAVE_DIR    = "data"
_SAVE_FILE   = _SAVE_DIR + "/splash.txt"


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _is_bin(name):
    return name.endswith(".bin")


def regular_names():
    """Regular splash names — top-level ``*.bin`` under ``img/splash/``."""
    return [n for n in _listdir(_DIR) if _is_bin(n)]


def special_names():
    """Special splash names, each prefixed ``special/`` so it is a distinct
    selection key from any regular splash of the same base name."""
    return [_SPECIAL_SUB + "/" + n for n in _listdir(_SPECIAL_DIR) if _is_bin(n)]


def all_names():
    """Every selectable splash: the regular pool followed by the special pool."""
    return regular_names() + special_names()


def is_special(name):
    return name.startswith(_SPECIAL_SUB + "/")


def path_for(name):
    """Full ``img/...`` path for a selection name."""
    return _DIR + "/" + name


def label_for(name):
    """Human label for a selection name (for the debug picker)."""
    base = name
    if is_special(base):
        base = base[len(_SPECIAL_SUB) + 1:]
    if base.endswith(".bin"):
        base = base[:-4]
    return base.replace("_", " ").upper()


def _exists(name):
    try:
        os.stat(path_for(name))
        return True
    except OSError:
        return False


def get_selected():
    """Persisted selection name, or ``""`` for auto/random."""
    try:
        with open(_SAVE_FILE) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "selected":
                    return value
    except OSError:
        pass
    return ""


def set_selected(name):
    """Persist the splash selection (``""`` = auto/random each boot)."""
    _ensure_dir()
    with open(_SAVE_FILE, "w") as f:
        f.write("selected={}\n".format(name or ""))


def default_special():
    """First available special splash name, or ``""`` if none exist."""
    specials = special_names()
    return specials[0] if specials else ""


def mark_max_level():
    """Switch the boot splash to the special screen because a character reached
    max level.  Idempotent: only writes when the selection actually changes, so
    repeated calls don't wear the flash.  Returns True if it changed."""
    special = default_special()
    if special and get_selected() != special:
        set_selected(special)
        return True
    return False


def resolve_boot():
    """Return the ``img/...`` path to show on boot, or ``None`` if no splash art
    is present.

    Honours the persisted selection when it points at a real file; otherwise
    falls back to a random regular splash (the "auto" behaviour).  If no regular
    splashes exist, falls back to any special one.
    """
    sel = get_selected()
    if sel and _exists(sel):
        return path_for(sel)
    regulars = regular_names()
    if regulars:
        return path_for(regulars[random.randint(0, len(regulars) - 1)])
    specials = special_names()
    if specials:
        return path_for(specials[0])
    return None


def _ensure_dir():
    try:
        os.mkdir(_SAVE_DIR)
    except OSError:
        pass
