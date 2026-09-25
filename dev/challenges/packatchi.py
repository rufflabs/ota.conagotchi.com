"""Packatchi's unique challenges — a vendor-stamp collection ladder."""
from challenges.criteria import CollectStampsChallenge


class PackatchiStamps1(CollectStampsChallenge):
    id          = "packatchi_stamps_1"
    name        = "Packet Rat I"
    description = "Collect 5 stamps"
    character   = "packatchi"
    target      = 5


class PackatchiStamps2(CollectStampsChallenge):
    id          = "packatchi_stamps_2"
    name        = "Packet Rat II"
    description = "Collect 10 stamps"
    character   = "packatchi"
    target      = 10


class PackatchiStamps3(CollectStampsChallenge):
    id          = "packatchi_stamps_3"
    name        = "Packet Rat III"
    description = "Collect 15 stamps"
    character   = "packatchi"
    target      = 15
