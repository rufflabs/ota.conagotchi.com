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
    when a Chi trade completes (trade_session), so this only advances when you
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


# ── Games (game_scores) ──────────────────────────────────────────────────────

class PlayGameChallenge(Challenge):
    """Met once `game` has been played `target` times (a run started)."""
    game = ""
    target = 1

    @classmethod
    def is_met(cls) -> bool:
        import game_scores
        return game_scores.get(cls.game, "plays") >= cls.target

    @classmethod
    def progress(cls):
        if cls.target <= 1:
            return None
        import game_scores
        return (min(game_scores.get(cls.game, "plays"), cls.target), cls.target)


class GameScoreChallenge(Challenge):
    """Met once `game`'s saved record for `key` reaches `target` (multi-step).

    The score is whatever the game records: rounds cleared in Simon, food
    eaten in Snake."""
    game = ""
    key = "best"
    target = 10

    @classmethod
    def is_met(cls) -> bool:
        import game_scores
        return game_scores.get(cls.game, cls.key) >= cls.target

    @classmethod
    def progress(cls):
        import game_scores
        return (min(game_scores.get(cls.game, cls.key), cls.target), cls.target)


class BeatHighScoreChallenge(Challenge):
    """Met once any game's run has beaten that game's earlier high score. A
    first score is not a beaten one, so this needs at least two runs."""
    target = 1

    @classmethod
    def is_met(cls) -> bool:
        import game_scores
        return game_scores.total("beaten") >= cls.target


class PlayAnyGameChallenge(Challenge):
    """Met once any game has been played `target` times in total."""
    target = 1

    @classmethod
    def is_met(cls) -> bool:
        import game_scores
        return game_scores.total("plays") >= cls.target


# ── Meta ─────────────────────────────────────────────────────────────────────

class MetaChallenge(Challenge):
    """Met once other challenges are complete: every id in `requires`, and at
    least one id in `requires_any` when that is set.

    The usual shape is a CTF meta challenge (is_ctf = True) over badge-only
    parts: the parts give no flag, and this one gives the flag once they are
    all done. List it after its parts in the registry, so a sweep that
    completes the last part completes this too."""
    requires = ()
    requires_any = ()

    @classmethod
    def is_met(cls) -> bool:
        import challenge_manager
        done = challenge_manager.is_completed
        if not all(done(cid) for cid in cls.requires):
            return False
        return not cls.requires_any or any(done(cid) for cid in cls.requires_any)

    @classmethod
    def progress(cls):
        import challenge_manager
        parts = list(cls.requires) + ([cls.requires_any] if cls.requires_any else [])
        if len(parts) < 2:
            return None
        done = 0
        for part in parts:
            ids = part if isinstance(part, tuple) else (part,)
            if any(challenge_manager.is_completed(cid) for cid in ids):
                done += 1
        return (done, len(parts))
