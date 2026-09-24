"""Adminichi's unique challenges."""
from challenges.criteria import ConnectWifiChallenge


class AdminichiUplink(ConnectWifiChallenge):
    id          = "adminichi_uplink"
    name        = "Uplink"
    description = "Connect to WiFi"
    character   = "adminichi"
