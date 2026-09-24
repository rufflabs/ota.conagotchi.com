RARITY_NORMAL    = "normal"
RARITY_UNCOMMON  = "uncommon"
RARITY_RARE      = "rare"
RARITY_LEGENDARY = "legendary"

# Relative weights used by character_manager.choose_random()
RARITY_WEIGHTS = {
    RARITY_NORMAL:    60,
    RARITY_UNCOMMON:  25,
    RARITY_RARE:      12,
    RARITY_LEGENDARY:  3,
}


class Character:
    """Base class for all Conagotchi characters.

    Subclass and override the attributes below — no methods need overriding
    unless the character has non-standard behaviour.

    Colour tuples are plain (r, g, b) ints; the screen converts them to
    gc9a01 colour values at load time so this module stays display-agnostic.
    """

    id          = ""
    name        = "Unknown"       # Display name; default for PetState.name
    rarity      = RARITY_NORMAL   # Affects random selection weight on first boot
    starter     = True            # False means unlockable only after collection
    level_color = (100, 200, 150) # RGB for level/XP LEDs; default for PetState.level_color

    # Work resource — each character "works" in its own way.  work_name is the
    # full display name of the activity (e.g. "Vibe Code", "Audit"); work_label
    # is the short (≤6 char) form used on the round-screen ring button;
    # work_desc is the how-to-refill blurb shown in the pet stats detail view.
    # Override per character; all default to a generic "Work".
    work_name   = "Work"
    work_label  = "Work"
    work_desc   = "Get to work and keep your skills sharp!"

    # Fallback solid colour shown when background.bin is absent
    bg_color    = (15, 35, 25)

    # Character sprite bounding box (pixels, 240×240 display space)
    char_x      = 80
    char_y      = 98
    char_w      = 80
    char_h      = 80

    # Animation
    anim_ms     = 300   # fallback ms per frame when state_frame_ms is absent
    blink_every = 10    # primitive-fallback blink cadence (ticks)

    # Animation states: map state name → list of img/ paths
    # The screen resolves the active state; "idle" is always required.
    # A care action plays the state whose name matches the action id while it
    # runs ("snack", "hydrate", "chill", "work"); define any of these to give
    # the character a per-action animation. Any state with no frames (or missing
    # frame files) falls back to the idle animation.
    states = {
        "idle": [],
        # "snack":   ["img/<id>/snack_0.bin", ...],
        # "hydrate": ["img/<id>/hydrate_0.bin", ...],
        # "chill":   ["img/<id>/chill_0.bin", ...],
        # "work":    ["img/<id>/work_0.bin", ...],
    }
    # Optional per-state animation settings.
    state_modes = {
        # "idle": "pingpong",  # also supports "loop" and "once"
    }
    state_frame_ms = {
        # "idle": (300, 450, 300),
    }
    state_pre_composited = {
        # "idle": False,  # False means magenta-keyed transparent sprite files
    }
    action_durations = {
        # "snack": 2500,  # optional per-character action timing override
    }

    # Primitive-fallback palette — drawn when sprite files are absent
    prim_body   = (230, 210, 175)
    prim_eye    = ( 40,  30,  50)
    prim_shine  = (255, 255, 255)
    prim_smile  = (190,  80,  80)
    prim_cheek  = (230, 150, 150)

    @classmethod
    def bg_path(cls):
        return "img/{}/background.bin".format(cls.id)

    @classmethod
    def state_frames(cls, state="idle"):
        return list(cls.states.get(state, []))

    @classmethod
    def state_mode(cls, state="idle"):
        return cls.state_modes.get(state, "pingpong")

    @classmethod
    def state_frame_durations(cls, state="idle"):
        return cls.state_frame_ms.get(state, ())

    @classmethod
    def state_uses_precomposited(cls, state="idle"):
        return cls.state_pre_composited.get(state, True)
