"""Factory reset: wipe all persisted badge state.

Every bit of badge state that survives a power cycle lives as a plain file
under ``data/`` (active/collected characters, per-character pet state, vendor
stamps, challenge progress, and badge settings). Deleting that directory makes
the badge boot as if brand new: ``character_manager.get_active()`` finds no
saved character and falls through to a fresh weighted random pick.

The badge does not persist BLE bonds or anything else in the ESP32 NVS
partition, so clearing ``data/`` is a complete reset.
"""

import os

_DATA_DIR = "data"


def wipe() -> int:
    """Delete everything under ``data/``. Returns the number of files removed."""
    return _rmtree(_DATA_DIR)


def _rmtree(path: str) -> int:
    removed = 0
    try:
        entries = os.listdir(path)
    except OSError:
        return removed
    for name in entries:
        full = path + "/" + name
        if _is_dir(full):
            removed += _rmtree(full)
            try:
                os.rmdir(full)
            except OSError:
                pass
        else:
            try:
                os.remove(full)
                removed += 1
            except OSError:
                pass
    return removed


def _is_dir(path: str) -> bool:
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False
