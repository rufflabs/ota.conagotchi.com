"""Vibatchi's unique challenges."""
from challenges.criteria import TwoWayTradeChallenge, TradeWithPeersChallenge


class VibatchiGoodVibes(TwoWayTradeChallenge):
    id          = "vibatchi_good_vibes"
    name        = "Good Vibes"
    description = "Send and receive a character in a trade."
    character   = "vibatchi"


class VibatchiJamSession(TradeWithPeersChallenge):
    id          = "vibatchi_jam_session"
    name        = "Jam Session"
    description = "Trade with 5 different badges to assemble the band."
    character   = "vibatchi"
    target      = 5
