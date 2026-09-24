"""Stable per-badge identity derived from the ESP32 hardware id.

Used to tell one physical badge apart from another during badge-to-badge
trades, so the "trade with N different attendees" challenges can count *unique*
peers (see peer_manager). The id is a short lowercase hex string, stable across
reboots and factory resets (it comes from the chip, not from data/).
"""
import machine

_cached = None


def badge_id() -> str:
    """Return this badge's stable hex id (cached after the first call)."""
    global _cached
    if _cached is None:
        try:
            _cached = "".join("{:02x}".format(b) for b in machine.unique_id())
        except Exception:
            _cached = "unknown"
    return _cached
