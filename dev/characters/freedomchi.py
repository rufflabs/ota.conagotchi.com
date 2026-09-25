from characters.base import Character, RARITY_NORMAL


class Freedomchi(Character):
    id          = "freedomchi"
    name        = "Freedomchi"
    rarity      = RARITY_NORMAL
    starter     = False
    level_color = (245, 205, 75)
    bg_color    = (7, 18, 38)
    work_name   = "Advocate"
    work_label  = "Free"
    work_desc   = "Rally the community and advocate for freedom!"
    char_x      = 80
    char_y      = 96
    char_w      = 80
    char_h      = 80
    anim_ms     = 320
    blink_every = 12
    states      = {
        "idle": [
            "img/freedomchi/character.bin",
        ],
    }
    prim_body   = (128, 76, 36)
    prim_eye    = ( 28, 18, 15)
    prim_shine  = (255, 255, 255)
    prim_smile  = (230, 178, 65)
    prim_cheek  = (246, 238, 214)
