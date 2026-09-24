"""Free the Data is shared; the legacy chi-specific definition is inactive."""
from challenges.criteria import CompletedTradesChallenge, TradeWithPeersChallenge


class FreedomchiFreeData(CompletedTradesChallenge):
    id          = "freedomchi_free_data"
    name        = "Free the Data"
    description = "Send and receive five characters in trade."
    character   = ""
    target      = 5


class FreedomchiSpreadTheWord(TradeWithPeersChallenge):
    id          = "freedomchi_spread_the_word"
    name        = "Spread the Word"
    description = "Share the movement: trade with 5 different badges."
    character   = "freedomchi"
    target      = 5
