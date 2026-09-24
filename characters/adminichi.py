from characters.base import Character, RARITY_NORMAL


class Adminichi(Character):
    id          = "adminichi"
    name        = "Adminichi"
    rarity      = RARITY_NORMAL
    level_color = (90, 180, 255)
    bg_color    = (12, 30, 48)
    work_name   = "Administer"
    work_label  = "Admin"
    work_desc   = "Patch the servers and keep the fleet healthy!"
    states      = {
        "idle": [
            "img/adminichi/character.bin",
        ],
    }
    prim_body   = (145, 205, 235)
    prim_eye    = ( 20,  35,  55)
    prim_shine  = (255, 255, 255)
    prim_smile  = ( 70, 105, 170)
    prim_cheek  = (150, 190, 230)
