"""Shared Base Quests; legacy Cryptachi IDs preserve existing completions."""
from challenges.criteria import CompletedTradesChallenge, TradeWithPeersChallenge


class CryptachiKeyExchange(CompletedTradesChallenge):
    id          = "cryptachi_key_exchange"
    name        = "Key Exchange"
    description = "Send and receive three characters in trade."
    character   = ""
    target      = 3


class CryptachiWebOfTrust(TradeWithPeersChallenge):
    id          = "cryptachi_web_of_trust"
    name        = "Web of Trust"
    description = "Sign enough keys: trade with 7 different attendees."
    character   = ""
    target      = 7
