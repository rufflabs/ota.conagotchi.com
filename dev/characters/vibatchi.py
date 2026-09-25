from characters.base import Character, RARITY_NORMAL


class Vibatchi(Character):
    id          = "vibatchi"
    name        = "Vibatchi"
    rarity      = RARITY_NORMAL
    level_color = (150, 120, 255)
    bg_color    = (28, 20, 45)
    work_name   = "Vibe Code"
    work_label  = "Vibe"
    work_desc   = "Crack the knuckles and vibe code a while!"
    states      = {
        "idle": [
            "img/vibatchi/character.bin",
        ],
    }
    prim_body   = (190, 170, 245)
    prim_eye    = ( 35,  28,  55)
    prim_shine  = (255, 255, 255)
    prim_smile  = (150,  85, 170)
    prim_cheek  = (220, 150, 220)
