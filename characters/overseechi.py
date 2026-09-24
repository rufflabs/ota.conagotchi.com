from characters.base import Character, RARITY_NORMAL


class Overseechi(Character):
    id          = "overseechi"
    name        = "Overseechi"
    rarity      = RARITY_NORMAL
    level_color = (245, 95, 120)
    bg_color    = (48, 14, 24)
    work_name   = "Audit"
    work_label  = "Audit"
    work_desc   = "Time to audit the logs and controls!"
    states      = {
        "idle": [
            "img/overseechi/character.bin",
        ],
    }
    prim_body   = (235, 145, 165)
    prim_eye    = ( 55,  20,  32)
    prim_shine  = (255, 255, 255)
    prim_smile  = (170,  55,  80)
    prim_cheek  = (230, 125, 145)
