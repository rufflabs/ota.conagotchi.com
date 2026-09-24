"""Manages active and collected Conagotchi characters.

Persistence:
    data/character.txt   active character id
    data/characters.txt  collected character ids, one per line

Each character's full state is stored separately in data/char_{id}.txt and is
managed by PetState. This module tracks which character is active and which
characters have been collected/unlocked for OzConBase.

Random selection on first boot is weighted by character rarity so that rarer
characters appear less often. The starting character is automatically collected.
"""

import os
import random
from characters import CHARACTERS
from characters.base import RARITY_WEIGHTS

_ACTIVE_FILE = "data/character.txt"
_UNLOCK_FILE = "data/characters.txt"


def all_characters():
    """Return every character class registered in the firmware."""
    return tuple(CHARACTERS)


def find(character_id: str):
    """Return a Character class by id, or None if it is not registered."""
    for cls in CHARACTERS:
        if cls.id == character_id:
            return cls
    return None


def get_active():
    """Return the active Character class, choosing randomly on first boot."""
    try:
        with open(_ACTIVE_FILE) as f:
            cid = f.read().strip()
        cls = find(cid)
        if cls is not None:
            unlock(cls.id)
            return cls
    except OSError:
        pass
    return choose_random()


def get_unlocked():
    """Return collected Character classes in registry order."""
    active = get_active()
    ids = _load_unlocked_ids()
    if active.id not in ids:
        ids.append(active.id)
        _save_unlocked_ids(ids)
    return tuple(cls for cls in CHARACTERS if cls.id in ids)


def is_unlocked(character_id: str) -> bool:
    """Return True if a registered character has been collected."""
    return character_id in _load_unlocked_ids()


def unlock(character_id: str) -> bool:
    """Collect a registered character. Returns True only when newly collected."""
    if find(character_id) is None:
        return False
    ids = _load_unlocked_ids()
    if character_id in ids:
        return False
    ids.append(character_id)
    _save_unlocked_ids(ids)
    return True


def set_active(character_id: str):
    """Activate a collected character by id. Returns the class or None."""
    cls = find(character_id)
    if cls is None or not is_unlocked(character_id):
        return None
    save(cls)
    return cls


def choose_random():
    """Pick a Character class weighted by rarity, persist the choice, return it."""
    candidates = tuple(cls for cls in CHARACTERS if getattr(cls, "starter", True))
    if not candidates:
        candidates = tuple(CHARACTERS)
    total = sum(RARITY_WEIGHTS.get(cls.rarity, RARITY_WEIGHTS["normal"])
                for cls in candidates)
    pick = random.randint(0, total - 1)
    cumulative = 0
    for cls in candidates:
        cumulative += RARITY_WEIGHTS.get(cls.rarity, RARITY_WEIGHTS["normal"])
        if pick < cumulative:
            _save_starting_character(cls)
            return cls
    # Fallback (only reachable if CHARACTERS is empty)
    cls = candidates[-1]
    _save_starting_character(cls)
    return cls


def save(cls) -> None:
    """Persist the active character ID."""
    _ensure_dir()
    with open(_ACTIVE_FILE, "w") as f:
        f.write(cls.id)
    unlock(cls.id)


def _save_starting_character(cls) -> None:
    """Persist the first character and lock all other characters."""
    _ensure_dir()
    with open(_ACTIVE_FILE, "w") as f:
        f.write(cls.id)
    _save_unlocked_ids((cls.id,))


def _load_unlocked_ids() -> list:
    ids = []
    try:
        with open(_UNLOCK_FILE) as f:
            for line in f:
                cid = line.strip()
                if cid and find(cid) is not None and cid not in ids:
                    ids.append(cid)
    except OSError:
        pass
    return ids


def _save_unlocked_ids(ids) -> None:
    _ensure_dir()
    with open(_UNLOCK_FILE, "w") as f:
        for cid in ids:
            if find(cid) is not None:
                f.write(cid + "\n")


def _ensure_dir() -> None:
    try:
        os.mkdir("data")
    except OSError:
        pass
