"""One badge-to-badge Chi trade, with no drawing. (Vendor stamps are
stamp_session.py.)

A screen owns a TradeSession, calls start() when its trade view opens,
poll() from its update() tick, and reads the session's state to draw. The Trade
screen (screens/trade.py) uses it for Chi's.

A Chi trade is two-sided on every transport:
  start()  opens the links and announces this badge with a presence packet
           (OZP1:<badge>) that offers nothing, so neighbours can list it.
  send()   opens a SEND_WINDOW_MS window: the badge offers its Chi and accepts
           a peer's offer, only while its own window is open. So a trade
           happens only when both people press SEND within the window.
When one badge receives, it keeps offering for COMPLETE_LINGER_MS so the other
(whose window is also open) receives too.

Transports, all sharing one packet format:
  LINK cable  always used.
  Bluetooth   when enabled in Settings. Adverts weaker than BLE_RSSI_MIN are
              not accepted, so the badges must be close.
  IR          when enabled in Settings, and only while no cable peer is seen.

Wire format for a Chi: OZC1:<char_id>:<sender_badge_id>. The receiver unlocks
the Chi from its own registry; no quest completion or progress is sent. The
sender id lets the receiver count unique peers for the "trade with N
attendees" quests. A trade counts as completed once per session, when this
badge has both sent and received. A received Chi is collected, not made active.
"""
import random
import time

CHAR_PREFIX = b"OZC1:"
PRESENCE_PREFIX = b"OZP1:"

SEND_WINDOW_MS = 10000      # how long SEND offers and accepts a Chi
_BROADCAST_MIN_MS = 800     # presence beacon interval (plus jitter)
_BROADCAST_JITTER_MS = 900
_OFFER_MIN_MS = 250         # offer interval while the window is open
_OFFER_JITTER_MS = 200
_LINK_TIMEOUT_MS = 3000     # the cable counts as connected this long after a frame
NEARBY_MS = 4000            # a badge drops off the nearby list after this long
COMPLETE_LINGER_MS = 1200   # keep beaconing after a trade lands so the peer
                            # also receives ours, then stop


class TradeSession:
    """Trade state for one screen. `send_id` is the Chi to send."""

    def __init__(self, send_id="", ble=True, ir=True) -> None:
        self.send_id = send_id
        self.use_ble = ble
        self.use_ir = ir
        self.running = False      # links open and beaconing
        self.completing = False   # a packet landed; lingering before we stop
        self.done = False         # finished; `result` holds what happened
        self.result = None        # (sent_name, received_name, newly_collected)
        self.message = ""         # transient status ("UNKNOWN CHI", "GOT X")
        self.transport = "LINK"   # how the last packet went or came
        self._ble = None
        self._wired = None
        self._ir = None
        self._window_end = None   # ticks_ms the send window closes, or None
        self._link_seen = None
        self._next_broadcast = 0
        self._complete_at = 0
        self._session_sent = False
        self._trade_counted = False
        self._peers = {}          # badge id -> (via, ticks) heard over LINK/IR

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @property
    def wireless(self) -> bool:
        """True when Bluetooth or IR may be used, not just the cable."""
        return self.use_ble or self.use_ir

    def start(self) -> bool:
        """Open the links and start announcing this badge (no offer yet).
        Returns False when no transport could be opened."""
        if self.running:
            return True
        if not self._open_links():
            return False
        self.running = True
        self.completing = False
        self.done = False
        self.result = None
        self.message = ""
        self._window_end = None
        self._link_seen = None
        self._session_sent = False
        self._trade_counted = False
        self.transport = "BT" if self._ble is not None else self._fallback()
        self._schedule_broadcast(time.ticks_ms(), 60)
        return True

    def send(self) -> bool:
        """Open (or restart) the send window: offer our Chi and accept one."""
        if not self.running and not self.start():
            return False
        if self.completing:
            return True
        now = time.ticks_ms()
        if self._ble is not None:
            while self._ble.available():
                self._ble.read()      # discard adverts from before the window
        self._window_end = time.ticks_add(now, SEND_WINDOW_MS)
        self.message = ""
        self._next_broadcast = now    # offer straight away
        return True

    def stop(self) -> None:
        """Close every link. Safe to call at any time."""
        for link in (self._ble, self._wired, self._ir):
            if link is not None:
                try:
                    link.deinit()
                except Exception:
                    pass
        self._ble = None
        self._wired = None
        self._ir = None
        self._window_end = None
        self._link_seen = None
        self.running = False
        self.completing = False

    def poll(self) -> None:
        """Call from the screen's update(): read links, beacon, finish."""
        if not self.running:
            return
        now = time.ticks_ms()
        self._poll_links()
        if self.completing:
            if time.ticks_diff(now, self._complete_at) >= 0:
                self.stop()
                self.done = True
                return
        if time.ticks_diff(now, self._next_broadcast) >= 0:
            self._broadcast()
            self._schedule_broadcast(now)

    def window_open(self) -> bool:
        """True while the send window is open."""
        return (self._window_end is not None
                and time.ticks_diff(self._window_end, time.ticks_ms()) > 0)

    def window_left(self) -> int:
        """Whole seconds left in the send window (0 when closed)."""
        if not self.window_open():
            return 0
        return (time.ticks_diff(self._window_end, time.ticks_ms()) + 999) // 1000

    @property
    def sent_once(self) -> bool:
        """True once SEND has been pressed in this session."""
        return self._window_end is not None

    def link_present(self) -> bool:
        if self._link_seen is None:
            return False
        return time.ticks_diff(time.ticks_ms(), self._link_seen) < _LINK_TIMEOUT_MS

    def nearby(self, limit=3):
        """Badges heard recently, strongest first, as (short id, rssi, via).
        rssi is None for the cable and IR, which report no signal strength."""
        now = time.ticks_ms()
        me = my_badge()
        found = {}
        if self._ble is not None:
            for badge, (rssi, seen) in list(self._ble.heard.items()):
                if badge != me and time.ticks_diff(now, seen) < NEARBY_MS:
                    found[badge] = (rssi, "BT")
        for badge, (via, seen) in self._peers.items():
            if badge != me and time.ticks_diff(now, seen) < NEARBY_MS:
                found[badge] = (None, via)      # cable/IR beat a BT reading
        rows = [(short_id(b), rssi, via) for b, (rssi, via) in found.items()]
        rows.sort(key=lambda r: 0 if r[1] is None else -r[1] + 1)
        return rows[:limit]

    def rssi_min(self):
        """The Bluetooth signal strength a trade needs (config BLE_RSSI_MIN)."""
        try:
            from config import BLE_RSSI_MIN
            return BLE_RSSI_MIN
        except Exception:
            return -55

    def transports(self) -> str:
        """The links in use, e.g. "BT LINK IR", for the status line."""
        names = []
        if self._ble is not None or (not self.running and self.use_ble):
            names.append("BT")
        names.append("LINK")
        if self._ir is not None or (not self.running and self.use_ir):
            names.append("IR")
        return " ".join(names)

    # ── Transports ───────────────────────────────────────────────────────────

    def _open_links(self) -> bool:
        if self.use_ble and self._ble is None:
            try:
                from link import BleLink
                self._ble = BleLink()
            except Exception:
                self._ble = None
        if self._wired is None:
            try:
                from link import WiredLink
                self._wired = WiredLink()
            except Exception:
                self._wired = None
        if self.use_ir and self._ir is None:
            try:
                from link import IrLink
                self._ir = IrLink()
            except Exception:
                self._ir = None
        return (self._ble is not None or self._wired is not None
                or self._ir is not None)

    def _fallback(self) -> str:
        if self._ir is not None and not self.link_present():
            return "IR"
        return "LINK"

    def _schedule_broadcast(self, now: int, first_delay: int = None) -> None:
        if first_delay is None:
            if self._offering():
                first_delay = _OFFER_MIN_MS + random.randint(0, _OFFER_JITTER_MS)
            else:
                first_delay = _BROADCAST_MIN_MS + random.randint(0, _BROADCAST_JITTER_MS)
        self._next_broadcast = time.ticks_add(now, first_delay)

    def _offering(self) -> bool:
        """True while this badge should offer, not just announce itself."""
        return self.window_open()

    def _broadcast(self) -> None:
        offering = self._offering()
        if offering:
            payload = pack_char(self.send_id, my_badge())
        else:
            # Outside the send window: say we are here, offering nothing.
            payload = PRESENCE_PREFIX + my_badge().encode()
        sent = False
        if self._ble is not None:
            sent = _safe_send(self._ble, payload) or sent
        # The cable always carries it.
        if self._wired is not None:
            sent = _safe_send(self._wired, payload) or sent
        # IR only while no cable peer is present.
        if not self.link_present() and self._ir is not None:
            sent = _safe_send(self._ir, payload) or sent
        if not self.completing:          # keep the link the trade came over
            self.transport = "BT" if self._ble is not None else self._fallback()
        # Offering our Chi is the "sent" half of a trade.
        if offering and sent:
            try:
                import peer_manager
                peer_manager.mark_sent()
                self._session_sent = True
                self._record_completed_trade()
            except Exception:
                pass

    def _poll_links(self) -> None:
        if self._ble is not None:
            for _ in range(6):
                if not self._ble.available():
                    break
                packet = self._ble.read()
                if not packet:
                    continue
                # handle_packet ignores presence beacons, stamps, and Chi
                # offers outside our own send window.
                self.handle_packet(packet, "BT")
        if self._wired is not None:
            for _ in range(4):
                if not self._wired.available():
                    break
                packet = self._wired.read()
                if packet:
                    self._link_seen = time.ticks_ms()
                    self._note_peer(packet, "LINK")
                    self.handle_packet(packet, "LINK")
        if self._ir is not None:
            for _ in range(3):
                if not self._ir.available():
                    break
                packet = self._ir.read()
                if packet:
                    self._note_peer(packet, "IR")
                    self.handle_packet(packet, "IR")

    def _note_peer(self, packet: bytes, via: str) -> None:
        badge = sender(packet)
        if badge:
            self._peers[badge] = (via, time.ticks_ms())

    # ── Packets ──────────────────────────────────────────────────────────────

    def handle_packet(self, packet: bytes, via: str = None) -> None:
        if not self.running or self.completing:
            return
        parsed = parse_char(packet)
        if parsed is None:
            return
        cid, peer = parsed
        if peer and peer == my_badge():
            return
        # Only while our own send window is open: both sides must press SEND.
        if not self.window_open():
            return
        if via:
            self.transport = via

        import character_manager
        cls = character_manager.find(cid)
        if cls is None:
            self.message = "UNKNOWN CHI"
            return
        # Receiving is the "received" half, and meets a distinct attendee for
        # the peer-trade quests whether or not the Chi was new.
        try:
            import peer_manager
            peer_manager.mark_received()
            if peer and peer != my_badge():
                peer_manager.record(peer)
        except Exception:
            pass
        # Collected, not made active. Quests stay local: a newly collected Chi
        # exposes its own quests.
        newly = character_manager.unlock(cid)
        if newly:
            try:
                import pet_state
                pet_state.create_fresh(cls)
            except Exception:
                pass
        self._begin_complete(_chi_name(self.send_id), cls.name, newly)

    def _begin_complete(self, sent: str, recv: str, new: bool) -> None:
        if self.completing:        # first landed packet wins
            return
        self.completing = True
        self.result = (sent, recv, new)
        self._record_completed_trade()
        now = time.ticks_ms()
        self._complete_at = time.ticks_add(now, COMPLETE_LINGER_MS)
        self._next_broadcast = now   # re-send ours now so the peer completes
        # Keep offering through the linger so the peer converges, even if the
        # trade landed near the end of our send window.
        self._window_end = self._complete_at
        self.message = "GOT " + recv.upper()

    def _record_completed_trade(self) -> None:
        if (self.completing and self._session_sent
                and not self._trade_counted):
            try:
                import peer_manager
                peer_manager.record_completed_trade()
                self._trade_counted = True
            except OSError:
                pass


def _safe_send(link, payload) -> bool:
    try:
        link.send(payload)
        return True
    except Exception:
        return False


def _chi_name(cid: str) -> str:
    import character_manager
    cls = character_manager.find(cid)
    return cls.name if cls is not None else cid


def sender(packet: bytes) -> str:
    """The sending badge's id in a Chi offer or presence packet, else ""."""
    if packet.startswith(PRESENCE_PREFIX):
        try:
            return packet[len(PRESENCE_PREFIX):].decode()
        except Exception:
            return ""
    parsed = parse_char(packet)
    return parsed[1] if parsed is not None else ""


def short_id(badge: str) -> str:
    """The last four hex digits of a badge id, as shown on screen."""
    return badge[-4:].upper() if badge else "----"


def my_badge() -> str:
    try:
        import badge_id
        return badge_id.badge_id()
    except Exception:
        return ""


def pack_char(char_id: str, badge: str) -> bytes:
    return CHAR_PREFIX + "{}:{}".format(char_id, badge).encode()


def parse_char(packet: bytes):
    """Return (char_id, sender_badge_id) or None. The sender id is "" if absent."""
    if not packet.startswith(CHAR_PREFIX):
        return None
    try:
        body = packet[len(CHAR_PREFIX):].decode()
    except Exception:
        return None
    parts = body.split(":")
    return parts[0], (parts[1] if len(parts) > 1 else "")
