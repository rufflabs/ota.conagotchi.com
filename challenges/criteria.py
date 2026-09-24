"""Reusable challenge completion criteria.

Concrete, character-tagged challenges (challenges/<character>.py) subclass these and
set id / name / description / character.  Each criterion reports completion from
live badge state via the `is_met()` classmethod, so a challenge only has to say
*what* to watch.  Multi-step criteria also implement `progress()`.
"""
from challenges.base import Challenge


class TradeCharacterChallenge(Challenge):
    """Met once the badge has collected a character beyond its starter.

    Note: this only checks the *received* side (unlocked count), so a debug
    character override also satisfies it. For "a real trade happened" use
    TwoWayTradeChallenge instead.
    """

    @classmethod
    def is_met(cls) -> bool:
        import character_manager
        return len(character_manager.get_unlocked()) > 1


class TwoWayTradeChallenge(Challenge):
    """Met once this badge has both broadcast its own character AND received one
    over LINK/IR — a genuine two-way trade. Broadcast-only, so send and receive
    aren't guaranteed to be with the same peer; a debug unlock or reroll won't
    satisfy it because no character was actually sent/received on the link."""

    @classmethod
    def is_met(cls) -> bool:
        import peer_manager
        return peer_manager.traded_both_ways()


class CompletedTradesChallenge(Challenge):
    """Count completed character exchanges, including repeat peers/characters."""
    target = 1

    @classmethod
    def is_met(cls) -> bool:
        import peer_manager
        return peer_manager.trade_count() >= cls.target

    @classmethod
    def progress(cls):
        import peer_manager
        return (min(peer_manager.trade_count(), cls.target), cls.target)


class CollectStampsChallenge(Challenge):
    """Met once the collected vendor-stamp count reaches `target` (multi-step)."""
    target = 5

    @classmethod
    def is_met(cls) -> bool:
        import stamp_manager
        return stamp_manager.count() >= cls.target

    @classmethod
    def progress(cls):
        import stamp_manager
        return (min(stamp_manager.count(), cls.target), cls.target)


class TradeWithPeersChallenge(Challenge):
    """Met once the badge has traded with `target` distinct peer badges.

    Multi-step. Peers are counted by hardware badge id (peer_manager), recorded
    when a character trade completes in OzConBase, so this only advances when you
    trade with a *new* person — trading repeatedly with the same badge does not.
    """
    target = 5

    @classmethod
    def is_met(cls) -> bool:
        import peer_manager
        return peer_manager.count() >= cls.target

    @classmethod
    def progress(cls):
        import peer_manager
        return (min(peer_manager.count(), cls.target), cls.target)


class ConnectWifiChallenge(Challenge):
    """Met while the badge is connected to WiFi."""

    @classmethod
    def is_met(cls) -> bool:
        try:
            import network
            return bool(network.WLAN(network.STA_IF).isconnected())
        except Exception:
            return False
