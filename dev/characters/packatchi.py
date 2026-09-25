from characters.base import Character, RARITY_NORMAL


class Packatchi(Character):
    id          = "packatchi"
    name        = "Packatchi"
    rarity      = RARITY_NORMAL
    level_color = (245, 160, 80)
    bg_color    = (45, 28, 15)
    work_name   = "Capture Packets"
    work_label  = "Pcap"
    work_desc   = "Fire up the sniffer and capture some packets!"
    states      = {
        "idle": [
            "img/packatchi/character.bin",
        ],
    }
    prim_body   = (235, 185, 125)
    prim_eye    = ( 50,  35,  25)
    prim_shine  = (255, 255, 255)
    prim_smile  = (180,  80,  60)
    prim_cheek  = (225, 140, 110)
