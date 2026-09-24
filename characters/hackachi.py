from characters.base import Character, RARITY_NORMAL


def _frames(name: str, count: int):
    return ["img/hackachi/{}_{}.bin".format(name, i) for i in range(count)]


_IDLE_MS = (900, 800)
_CHEER_MS = (180, 400, 155, 200, 160, 400)
_SAD_MS = (300, 400, 300, 200, 180)
_CHILL_MS = (900, 900, 900, 700, 900, 600)
_SNACK_MS = (280, 250, 300, 700, 200, 230, 200, 600)
_DRINK_MS = (280, 250, 250, 415, 300, 325, 325, 250)
_KEYED_STATES = ("idle", "cheer", "sad", "chill", "snack", "hydrate", "work")


class Hackachi(Character):
    id          = "hackachi"
    name        = "Hackachi"
    rarity      = RARITY_NORMAL
    level_color = (100, 220, 180)   # mint teal
    bg_color    = (15, 35, 25)
    work_name   = "Hack"
    work_label  = "Hack"
    work_desc   = "Pop a shell and hack the planet!"
    char_x      = 83
    char_y      = 90
    char_w      = 80
    char_h      = 80
    anim_ms     = 300
    blink_every = 10
    states      = {
        "idle": _frames("idle", 2),
        "cheer": _frames("cheer", 6),
        "sad": _frames("sad", 5),
        "chill": _frames("chill", 6),
        "snack": _frames("snack", 8),
        "hydrate": _frames("drink", 8),
        "work": _frames("cheer", 6),
    }
    state_modes = {
        "idle": "pingpong",
        "cheer": "once",
        "sad": "once",
        "chill": "loop",
        "snack": "once",
        "hydrate": "once",
        "work": "once",
    }
    state_frame_ms = {
        "idle": _IDLE_MS,
        "cheer": _CHEER_MS,
        "sad": _SAD_MS,
        "chill": _CHILL_MS,
        "snack": _SNACK_MS,
        "hydrate": _DRINK_MS,
        "work": _CHEER_MS,
    }
    state_pre_composited = {
        state: False for state in _KEYED_STATES
    }
    action_durations = {
        "snack": sum(_SNACK_MS),
        "hydrate": sum(_DRINK_MS),
        "chill": sum(_CHILL_MS),
        "work": sum(_CHEER_MS),
    }
    prim_body   = (230, 210, 175)
    prim_eye    = ( 40,  30,  50)
    prim_shine  = (255, 255, 255)
    prim_smile  = (190,  80,  80)
    prim_cheek  = (230, 150, 150)
