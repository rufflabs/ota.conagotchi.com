"""Shared Base Quests and an inactive legacy Hackachi quest."""
from challenges.criteria import (TwoWayTradeChallenge, ConnectWifiChallenge,
                                 TradeWithPeersChallenge)


class HackachiFirstContact(TwoWayTradeChallenge):
    id          = "hackachi_first_contact"
    name        = "First Contact"
    description = "Send and receive a character in a trade."
    character   = ""


class HackachiJackIn(ConnectWifiChallenge):
    id          = "hackachi_jack_in"
    name        = "Jack In"
    description = "Connect to WiFi"
    character   = ""


class HackachiLateralMovement(TradeWithPeersChallenge):
    id          = "hackachi_lateral_movement"
    name        = "Lateral Movement"
    description = "Pivot across the con: trade with 10 different badges."
    character   = "hackachi"
    target      = 10
