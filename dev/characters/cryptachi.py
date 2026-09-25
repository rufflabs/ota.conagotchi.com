from characters.base import Character, RARITY_NORMAL


class Cryptachi(Character):
    id          = "cryptachi"
    name        = "Cryptachi"
    rarity      = RARITY_NORMAL
    level_color = (90, 235, 120)
    bg_color    = (12, 42, 24)
    work_name   = "Encrypt"
    work_label  = "Crypt"
    work_desc   = "Spin up some ciphers and encrypt all the things!"
    states      = {
        "idle": [
            "img/cryptachi/character.bin",
        ],
    }
    prim_body   = (135, 230, 160)
    prim_eye    = ( 20,  45,  30)
    prim_shine  = (255, 255, 255)
    prim_smile  = ( 55, 150,  90)
    prim_cheek  = (145, 225, 170)
