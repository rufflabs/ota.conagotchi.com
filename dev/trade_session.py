"""One badge-to-badge Chi trade, with no drawing. (Vendor stamps are
stamp_session.py.)

A Chi trade is a two-player lobby game (lobby_session.LobbySession, game "T"),
so it gets the shared lobby's links, signing, caps and screen:

  In the lobby  every badge with Trade open is listed with the Chi it offers
                (its lobby note: the Chi's three-letter tag, see
                characters.base.Character.tag). A player requests a trade
                with one badge; the trade starts once both have requested
                each other, so both people agree to it.
  Linked        each badge sends <its Chi tag><got yours: 0 or 1>. A badge
                collects the other's Chi the first time it arrives, and the
                trade is complete once each has confirmed receiving the
                other's; it keeps sending for COMPLETE_LINGER_MS so the other
                side sees the last confirmation too.

A received Chi is collected, not made active. Progress for challenges
(peer_manager): the partner is recorded as a unique peer (by the lobby's
six-digit id), the two-way flags are set, and a completed trade is counted
once.
"""
import time

from lobby_session import LobbySession, short_id  # noqa: F401 (re-exported)

COMPLETE_LINGER_MS = 1500   # keep confirming after completing, then finish


def tag_of(cid: str) -> str:
    """The Chi's three-letter tag, e.g. "VIB"."""
    import character_manager
    cls = character_manager.find(cid)
    return getattr(cls, "tag", "") if cls is not None else ""


def chi_for_tag(tag: str):
    """The Character class with this tag, or None."""
    from characters import CHARACTERS
    for cls in CHARACTERS:
        if getattr(cls, "tag", "") == tag:
            return cls
    return None


class TradeSession(LobbySession):
    """Trade state for one Trade screen. `send_id` is the Chi this badge offers."""

    GAME = "T"
    VERBS = ("ACCEPT", "CANCEL", "REQUEST")

    def __init__(self, send_id="", ble=True, ir=True, me=None, links=None,
                 key=False) -> None:
        self.send_id = send_id
        self._tag = tag_of(send_id)
        self.received = None      # the Character class received, once it arrives
        self.newly = False        # it was new to this badge
        self.confirmed = False    # the partner confirmed receiving ours
        self.done = False         # both sides confirmed; the trade is over
        self.result = None        # (sent name, received name, newly collected)
        self.message = ""
        self._done_at = None
        self._counted = False
        super().__init__(ble, ir, me, links, key)

    @property
    def wireless(self) -> bool:
        return self.radio.use_ble or self.radio.use_ir

    # ── LobbySession hooks ───────────────────────────────────────────────────

    def note(self) -> str:
        return self._tag

    def describe(self, badge, via, requested, invited):
        """The Chi a badge offers: highlighted when it has requested this
        badge, in the accent when this badge has requested it."""
        cls = chi_for_tag(self.note_of(badge))
        offer = cls.name.upper() if cls is not None else "?"
        if requested:
            return (offer, "highlight")
        if invited:
            return (offer, "accent")
        return (offer, "text")

    def payload(self) -> str:
        return self._tag + ("1" if self.received is not None else "0")

    def on_payload(self, text: str) -> None:
        if self.done or len(text) < 4:
            return
        if self.received is None:
            self._receive(text[:3])
        if text[3] == "1" and not self.confirmed:
            self.confirmed = True
            try:
                import peer_manager
                peer_manager.mark_sent()      # they have ours: the sent half
            except Exception:
                pass
        self._check_done()

    def reset_match(self) -> None:
        """A new partner, or none: ready for the next trade. (The trade
        screen keeps its own copy of a finished trade's result.)"""
        self.received = None
        self.newly = False
        self.confirmed = False
        self.done = False
        self.result = None
        self.message = ""
        self._done_at = None
        self._counted = False

    # ── the exchange ─────────────────────────────────────────────────────────

    def poll(self) -> None:
        super().poll()
        if (self._done_at is not None and not self.done
                and time.ticks_diff(time.ticks_ms(), self._done_at) >= 0):
            self.done = True

    def _receive(self, tag: str) -> None:
        cls = chi_for_tag(tag)
        if cls is None:
            self.message = "UNKNOWN CHI"
            return
        import character_manager
        try:
            import peer_manager
            peer_manager.mark_received()
            if self.peer:
                peer_manager.record(self.peer)
        except Exception:
            pass
        self.newly = character_manager.unlock(cls.id)
        if self.newly:
            try:
                import pet_state
                pet_state.create_fresh(cls)
            except Exception:
                pass
        self.received = cls
        self.message = "GOT " + cls.name.upper()
        self.beacon_soon()                     # confirm at once

    def _check_done(self) -> None:
        if self.received is None or not self.confirmed or self._done_at is not None:
            return
        if not self._counted:
            self._counted = True
            try:
                import peer_manager
                peer_manager.record_completed_trade()
            except Exception:
                pass
        self.result = (_chi_name(self.send_id), self.received.name, self.newly)
        self._done_at = time.ticks_add(time.ticks_ms(), COMPLETE_LINGER_MS)


def _chi_name(cid: str) -> str:
    import character_manager
    cls = character_manager.find(cid)
    return cls.name if cls is not None else cid


def my_badge() -> str:
    try:
        import badge_id
        return badge_id.badge_id()
    except Exception:
        return ""
