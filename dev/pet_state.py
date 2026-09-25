"""Pet needs and desires state model.

Vital stats (hunger, thirst, energy) live on a 0–100 scale where 100 is fully
satisfied.  Stats decay toward 0 while the badge is running.  Actions
temporarily change the pet's animation state, restore stats, and award XP
when they finish.

Experience and levelling
────────────────────────
  Levels run 0–5 (six levels total, starting at 0).

  experience       — spendable currency; can be gained and spent
  total_experience — lifetime XP earned; never decreases; drives level-up
  level            — derived from total_experience via _LEVEL_XP thresholds

  gain_xp(n)    → adds n to both values, recalculates level, saves,
                  returns True if the pet levelled up
  spend_xp(n)   → deducts n from experience only (total/level unchanged);
                  returns False if insufficient
  xp_progress() → fraction (0.0–1.0) of the way to the next level;
                  returns 1.0 at max level

Persistence: data/char_{id}.txt  (key=value, one per line)
Each character keeps its own file so switching characters preserves all states.
No elapsed-time correction across power cycles until RTC/NTP is added.
"""

import os

_SAVE_DIR = "data"

# ── Level thresholds ──────────────────────────────────────────────────────────
# _LEVEL_XP[i] = total XP required to reach level i.  Six levels: 0–5.
_LEVEL_XP = (0, 100, 300, 600, 1000, 1500)
MAX_LEVEL = len(_LEVEL_XP) - 1
MAX_EXPERIENCE = _LEVEL_XP[-1]


def level_threshold(level: int) -> int:
    level = max(0, min(MAX_LEVEL, int(level)))
    return _LEVEL_XP[level]

# ── Care resources ────────────────────────────────────────────────────────────
# The player-facing resources that must be kept topped up.  Each has a refill
# action in the Pet menu.  "work" is per-character flavoured (see
# Character.work_name / work_label) but mechanically identical to the others.
RESOURCE_ATTRS = ("hunger", "thirst", "happiness", "work")

# When any resource drops to/below this the badge lights the red Alert LED; it
# only clears once every resource is back above the threshold.
LOW_THRESHOLD = 15.0

# ── Decay rates (units per second) ───────────────────────────────────────────
_HUNGER_DECAY    = 0.014   # ~2 h to empty
_THIRST_DECAY    = 0.028   # ~1 h to empty
_HAPPINESS_DECAY = 0.011   # ~2.5 h to empty
_WORK_DECAY      = 0.019   # ~1.5 h to empty
_ENERGY_DECAY    = 0.003   # ~9 h to empty while awake
_ENERGY_RESTORE  = 0.050   # recovery rate during "sleeping"

# ── Action table ──────────────────────────────────────────────────────────────
# action_id: (duration_ms, {stat: delta on completion}, xp_awarded)
_REFILL = 40   # how much a care action restores
_ACTIONS = {
    # Care actions surfaced in the Pet menu — each tops up one resource.
    "snack":    (2500, {"hunger":    _REFILL},  4),
    "hydrate":  (2000, {"thirst":    _REFILL},  3),
    "chill":    (3000, {"happiness": _REFILL},  5),
    "work":     (3500, {"work":      _REFILL},  8),
    # Legacy / animation-only actions.
    "eating":   (3000, {"hunger":  40},  5),
    "drinking": (2000, {"thirst":  40},  3),
    "playing":  (4000, {"energy": -10}, 20),
    "sleeping": (6000, {"energy":  50},  0),
    "petting":  (2000, {},              10),
}
# Actions whose stat delta applies the instant they start (immediate feedback)
# rather than on completion.
_IMMEDIATE_STAT_ACTIONS = ("snack", "hydrate", "chill", "work", "eating", "drinking")


def _calc_level(total_xp: float) -> int:
    """Return the level (0–5) for the given lifetime XP."""
    level = 0
    for i in range(len(_LEVEL_XP)):
        if total_xp >= _LEVEL_XP[i]:
            level = i
        else:
            break
    return level


class PetState:

    def __init__(self, char) -> None:
        """
        char — the active Character class (not an instance).
        Provides defaults for name, rarity, and level_color.
        id determines the save file path.
        """
        self._save_file = "{}/char_{}.txt".format(_SAVE_DIR, char.id)

        # Identity — name and level_color can be changed by the player
        self.name        = char.name
        self.rarity      = char.rarity
        self.level_color = char.level_color   # (r, g, b)

        # Per-character "work" flavour (mechanically a normal resource).
        self.work_name   = getattr(char, "work_name", "Work")
        self.work_label  = getattr(char, "work_label", self.work_name)
        self.work_desc   = getattr(char, "work_desc", "")
        self.action_durations = getattr(char, "action_durations", {})

        # Progression — a fresh character starts at level 0 with no XP.
        self.level            = 0
        self.experience       = 0
        self.total_experience = 0

        # Vital stats
        self.hunger = 80.0
        self.thirst = 80.0
        self.energy = 90.0
        self.happiness = 80.0
        self.work = 80.0

        # Action state
        self.action          = "idle"
        self._action_ms_left = 0

        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def tick(self, dt_ms: int, action_complete: bool = True) -> None:
        """Advance state; an animated action may wait for its last frame."""
        dt_s = dt_ms / 1000.0

        if self.action != "idle":
            self._action_ms_left = max(0, self._action_ms_left - dt_ms)
            if self._action_ms_left == 0 and action_complete:
                self._finish_action()

        self.hunger    = max(0.0, self.hunger    - _HUNGER_DECAY    * dt_s)
        self.thirst    = max(0.0, self.thirst    - _THIRST_DECAY    * dt_s)
        self.happiness = max(0.0, self.happiness - _HAPPINESS_DECAY * dt_s)
        self.work      = max(0.0, self.work      - _WORK_DECAY      * dt_s)
        if self.action == "sleeping":
            self.energy = min(100.0, self.energy + _ENERGY_RESTORE * dt_s)
        else:
            self.energy = max(0.0, self.energy - _ENERGY_DECAY * dt_s)

    def begin_action(self, action: str) -> bool:
        """Start an action.  Returns False if unknown or already busy."""
        if action not in _ACTIONS or self.action != "idle":
            return False
        self.action          = action
        self._action_ms_left = self.action_durations.get(action, _ACTIONS[action][0])
        if action in _IMMEDIATE_STAT_ACTIONS:
            self._apply_deltas(_ACTIONS[action][1])
            self.save()
        return True

    def is_idle(self) -> bool:
        return self.action == "idle"

    def gain_xp(self, amount: int) -> bool:
        """Award XP (e.g. from a challenge).  Returns True if the pet levelled up.

        Increments both experience and total_experience, recalculates level, saves.
        """
        self.experience       += amount
        self.total_experience += amount
        new_level   = _calc_level(self.total_experience)
        levelled_up = new_level > self.level
        self.level  = new_level
        self.save()
        return levelled_up

    def add_happiness(self, amount: int = 1) -> bool:
        """Increase happiness by amount, clamped to 100. Returns True if changed."""
        before = self.happiness
        self.happiness = max(0.0, min(100.0, self.happiness + amount))
        changed = self.happiness != before
        if changed:
            self.save()
        return changed

    def add_food(self, amount: int = 1) -> bool:
        """Increase the user-facing Food stat. Internally this is hunger."""
        before = self.hunger
        self.hunger = max(0.0, min(100.0, self.hunger + amount))
        changed = self.hunger != before
        if changed:
            self.save()
        return changed

    def add_thirst(self, amount: int = 1) -> bool:
        """Increase thirst, clamped to 100. Returns True if changed."""
        before = self.thirst
        self.thirst = max(0.0, min(100.0, self.thirst + amount))
        changed = self.thirst != before
        if changed:
            self.save()
        return changed

    def add_work(self, amount: int = 1) -> bool:
        """Increase the Work resource, clamped to 100. Returns True if changed."""
        before = self.work
        self.work = max(0.0, min(100.0, self.work + amount))
        changed = self.work != before
        if changed:
            self.save()
        return changed

    def any_resource_low(self) -> bool:
        """True while any care resource is at/below LOW_THRESHOLD.

        Drives the red Alert LED: it stays True until *every* resource is back
        above the threshold.
        """
        return any(getattr(self, attr) <= LOW_THRESHOLD for attr in RESOURCE_ATTRS)

    def spend_xp(self, amount: int) -> bool:
        """Spend experience (currency).  Returns False if insufficient.

        Only experience is reduced; total_experience and level are unaffected.
        """
        if self.experience < amount:
            return False
        self.experience -= amount
        self.save()
        return True

    def set_progress(self, total_xp: int) -> None:
        """Set XP directly. Intended for debug tooling."""
        total_xp = max(0, min(MAX_EXPERIENCE, int(total_xp)))
        self.experience = total_xp
        self.total_experience = total_xp
        self.level = _calc_level(total_xp)
        self.save()

    def set_level(self, level: int) -> None:
        """Set level directly by moving XP to that level threshold."""
        self.set_progress(level_threshold(level))

    def xp_progress(self) -> float:
        """Fraction of the way to the next level (0.0–1.0).  Returns 1.0 at max level."""
        max_level = len(_LEVEL_XP) - 1
        if self.level >= max_level:
            return 1.0
        current = _LEVEL_XP[self.level]
        nxt     = _LEVEL_XP[self.level + 1]
        return (self.total_experience - current) / (nxt - current)

    def save(self) -> None:
        _ensure_dir()
        with open(self._save_file, "w") as f:
            f.write("name={}\n".format(self.name))
            f.write("rarity={}\n".format(self.rarity))
            f.write("level_color={},{},{}\n".format(*self.level_color))
            f.write("level={}\n".format(self.level))
            f.write("experience={}\n".format(self.experience))
            f.write("total_experience={}\n".format(self.total_experience))
            f.write("hunger={}\n".format(self.hunger))
            f.write("thirst={}\n".format(self.thirst))
            f.write("energy={}\n".format(self.energy))
            f.write("happiness={}\n".format(self.happiness))
            f.write("work={}\n".format(self.work))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _finish_action(self) -> None:
        entry = _ACTIONS.get(self.action)
        if entry:
            _, deltas, xp = entry
            if self.action not in _IMMEDIATE_STAT_ACTIONS:
                self._apply_deltas(deltas)
            if xp > 0:
                self.experience       += xp
                self.total_experience += xp
                self.level = _calc_level(self.total_experience)
        self.action          = "idle"
        self._action_ms_left = 0
        self.save()

    def _apply_deltas(self, deltas) -> None:
        for stat, delta in deltas.items():
            v = getattr(self, stat, 0.0) + delta
            setattr(self, stat, max(0.0, min(100.0, float(v))))

    def _load(self) -> None:
        try:
            with open(self._save_file) as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if   k == "name":             self.name             = v
                    elif k == "rarity":           self.rarity           = v
                    elif k == "level_color":
                        parts = v.split(",")
                        self.level_color = (int(parts[0]), int(parts[1]), int(parts[2]))
                    elif k == "level":            self.level            = int(v)
                    elif k == "experience":       self.experience       = float(v)
                    elif k == "total_experience": self.total_experience = float(v)
                    elif k == "hunger":           self.hunger           = float(v)
                    elif k == "thirst":           self.thirst           = float(v)
                    elif k == "energy":           self.energy           = float(v)
                    elif k == "happiness":        self.happiness        = float(v)
                    elif k == "work":             self.work             = float(v)
        except (OSError, ValueError):
            pass


def _ensure_dir() -> None:
    try:
        os.mkdir(_SAVE_DIR)
    except OSError:
        pass


def reset_saved(char) -> None:
    """Remove saved pet progress for a character so it starts from defaults."""
    try:
        os.remove("{}/char_{}.txt".format(_SAVE_DIR, char.id))
    except OSError:
        pass


def create_fresh(char) -> None:
    """Persist a fresh local pet state for a newly collected character."""
    reset_saved(char)
    PetState(char).save()
