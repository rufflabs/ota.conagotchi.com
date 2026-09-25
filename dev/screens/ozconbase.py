"""OzConBase collected-character selector and IR sync screen."""
import random
import time

import gc9a01py as gc9a01

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from image_utils import draw_text
import ui
from screen_manager import Screen


# Defaults; refreshed from the active theme by _sync_theme() before each draw.
_BG = gc9a01.color565(10, 13, 20)
_PANEL = gc9a01.color565(22, 27, 36)
_SEL = gc9a01.color565(28, 98, 132)
_TEXT = gc9a01.WHITE
_MUTED = gc9a01.color565(145, 155, 170)
_OK = gc9a01.color565(80, 210, 120)


def _sync_theme() -> None:
    """Pull this screen's palette from the active theme (colors only)."""
    global _BG, _PANEL, _SEL, _TEXT, _MUTED, _OK
    import theme
    t = theme.get()
    _BG, _PANEL, _SEL = t.bg, t.surface, t.sel
    _TEXT, _MUTED, _OK = t.text, t.muted, t.success

_CHAR_SYNC_PREFIX = b"OZC1:"
_STAMP_SYNC_PREFIX = b"OZS1:"
_BROADCAST_MIN_MS = 800
_BROADCAST_JITTER_MS = 900
_LINK_TIMEOUT_MS = 3000        # treat the cable as connected if a peer frame
                               # arrived on it within this window.
_COMPLETE_LINGER_MS = 1200     # keep beaconing this long after a trade lands so
                               # the peer also receives ours, then stop and show
                               # the confirmation screen.
_VIEW_CHARS = "chars"
_VIEW_CONFIRM = "confirm"
_VIEW_STAMPS = "stamps"
_SYNC_CHARS = "chars"
_SYNC_STAMPS = "stamps"


class OzConBaseScreen(Screen):
    """Menu for collected characters, with IR character exchange."""

    def __init__(self) -> None:
        self._sel = 0
        self._chars = ()
        self._stamps = ()
        self._total_chars = 0
        self._active_id = ""
        self._view = _VIEW_CHARS
        self._stamp_sel = 0
        self._message = ""
        self._syncing = False
        self._sync_kind = _SYNC_CHARS
        self._ble = None            # BleLink, the default/preferred transport
        self._ble_window_end = 0    # ticks_ms; BT trades only while this is open
        self._wired = None          # WiredLink (LINK cable), fallback when present
        self._ir = None             # IrLink, fallback when no cable peer is seen
        self._link_seen = None      # ticks_ms of the last valid LINK frame
        self._active_transport = "BT"
        self._next_broadcast = 0
        self._completing = False    # a trade landed; lingering before we stop
        self._complete_at = 0
        self._confirm_kind = _SYNC_CHARS
        self._trade_sent = ""       # what this badge broadcast
        self._trade_recv = ""       # what this badge received
        self._trade_new = False     # was the received item newly collected
        self._session_sent = False
        self._trade_counted = False
        self._refresh()

    async def enter(self, display, leds, mgr) -> None:
        self._refresh()
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._refresh()
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        self._close_links()

    async def update(self, display, leds, mgr) -> None:
        if not self._syncing:
            return
        now = time.ticks_ms()
        self._poll_links(display)
        if self._completing:
            if time.ticks_diff(now, self._complete_at) >= 0:
                self._finish_complete(display)
                return
        if time.ticks_diff(now, self._next_broadcast) >= 0:
            self._broadcast(display)
            self._schedule_broadcast(now)

    def handle_button(self, btn: str, mgr) -> None:
        if self._view == _VIEW_CONFIRM:
            self._handle_confirm_button(btn, mgr)
            return
        if self._view == _VIEW_STAMPS:
            self._handle_stamp_button(btn, mgr)
            return

        if btn == BOOT or btn == SELECT:
            if self._syncing:
                # Backing out is the only way to stop the LINK/IR beacons.
                self._close_links()
                self._message = "SYNC OFF"
                self._draw(mgr._display)
            else:
                mgr.pop()
        elif btn == LEFT:
            self._move(-1, mgr._display)
        elif btn == RIGHT:
            self._move(1, mgr._display)
        elif btn == START:
            if self._is_char_sync_selected():
                self._start_sync(mgr._display, _SYNC_CHARS)
            elif self._is_stamp_card_selected():
                self._view = _VIEW_STAMPS
                self._message = ""
                self._draw(mgr._display)
            else:
                self._activate_selected(mgr)

    def _refresh(self) -> None:
        import character_manager
        import stamp_manager
        self._chars = character_manager.get_unlocked()
        self._stamps = stamp_manager.all_stamps()
        self._total_chars = len(character_manager.all_characters())
        self._active_id = character_manager.get_active().id
        max_sel = len(self._chars) + 1
        if self._sel > max_sel:
            self._sel = max_sel
        max_stamp_sel = len(self._stamps)
        if self._stamp_sel > max_stamp_sel:
            self._stamp_sel = max_stamp_sel

    def _item_count(self) -> int:
        return len(self._chars) + 2

    def _is_char_sync_selected(self) -> bool:
        return self._sel == len(self._chars)

    def _is_stamp_card_selected(self) -> bool:
        return self._sel > len(self._chars)

    def _is_stamp_sync_selected(self) -> bool:
        return self._stamp_sel >= len(self._stamps)

    def _draw(self, display) -> None:
        _sync_theme()
        if self._view == _VIEW_CONFIRM:
            _draw_confirm(display, self._confirm_kind, self._trade_sent,
                          self._trade_recv, self._trade_new,
                          self._active_transport)
        elif self._view == _VIEW_STAMPS:
            _draw_stamps(display, self._stamps, self._stamp_sel,
                         self._message, self._is_syncing(_SYNC_STAMPS),
                         self._vendor_stamp(), self._active_transport)
        else:
            _draw_base(display, self._chars, self._sel, self._active_id,
                       self._message, self._is_syncing(_SYNC_CHARS),
                       self._total_chars, len(self._stamps),
                       self._active_transport,
                       self._wired is not None or self._ir is not None)

    def _move(self, delta: int, display) -> None:
        count = self._item_count()
        if count <= 1:
            return
        self._sel = (self._sel + delta) % count
        self._message = ""
        self._draw(display)

    def _move_stamp(self, delta: int, display) -> None:
        count = len(self._stamps) + 1
        if count <= 1:
            return
        self._stamp_sel = (self._stamp_sel + delta) % count
        self._message = ""
        self._draw(display)

    def _activate_selected(self, mgr) -> None:
        if not self._chars:
            self._message = "NONE FOUND"
            self._draw(mgr._display)
            return

        char = self._chars[self._sel]
        if char.id == self._active_id:
            self._message = "ALREADY ACTIVE"
            self._draw(mgr._display)
            return

        import character_manager
        if character_manager.set_active(char.id) is None:
            self._message = "LOCKED"
            self._draw(mgr._display)
            return

        from screens.conagotchi import ConagotchiScreen
        mgr.switch_to(ConagotchiScreen())

    def _handle_stamp_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            if self._is_syncing(_SYNC_STAMPS):
                self._close_links()
                self._message = "STAMP OFF"
            else:
                self._view = _VIEW_CHARS
                self._message = ""
            self._draw(mgr._display)
        elif btn == LEFT:
            self._move_stamp(-1, mgr._display)
        elif btn == RIGHT:
            self._move_stamp(1, mgr._display)
        elif btn == START and self._is_stamp_sync_selected():
            self._start_sync(mgr._display, _SYNC_STAMPS)

    def _start_sync(self, display, kind: str) -> None:
        """First press starts sync: LINK/IR beacon continuously until you back
        out (SELECT/BOOT). If already syncing, re-arm the BT "press together"
        window for another simultaneous-press attempt — LINK/IR keep beaconing
        throughout, and the prompt stays PRESS TOGETHER."""
        now = time.ticks_ms()
        if not self._syncing:
            if not self._open_links():
                self._message = "LINK N/A"
                self._draw(display)
                return
            self._syncing = True
            self._completing = False
            self._sync_kind = kind
            self._link_seen = None
            self._session_sent = False
            self._trade_counted = False
        # (Re)open the BT simultaneity window and re-advertise our payload.
        if self._ble is not None:
            while self._ble.available():
                self._ble.read()   # discard stale adverts before the window
            self._ble_window_end = time.ticks_add(now, self._ble_window_ms())
        else:
            self._ble_window_end = 0
        self._active_transport = "BT" if self._ble is not None else "IR"
        self._schedule_broadcast(now, 60)
        if kind == _SYNC_STAMPS and self._vendor_stamp() is None:
            self._message = "RECEIVING"
        else:
            self._message = "PRESS TOGETHER"
        self._draw(display)

    def _is_syncing(self, kind: str) -> bool:
        return self._syncing and self._sync_kind == kind

    def _schedule_broadcast(self, now: int, first_delay: int = None) -> None:
        if first_delay is None:
            first_delay = _BROADCAST_MIN_MS + random.randint(0, _BROADCAST_JITTER_MS)
        self._next_broadcast = time.ticks_add(now, first_delay)

    def _open_links(self) -> bool:
        """Open all transports. BT is the default/preferred path (gated by the
        simultaneity window); the LINK cable is used whenever a peer is seen on
        it, and IR is the last fallback. Returns True if at least one opened."""
        if self._ble is None:
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
        if self._ir is None:
            try:
                from link import IrLink
                self._ir = IrLink()
            except Exception:
                self._ir = None
        return (self._ble is not None or self._wired is not None
                or self._ir is not None)

    def _close_links(self) -> None:
        for link in (self._ble, self._wired, self._ir):
            if link is not None:
                try:
                    link.deinit()
                except Exception:
                    pass
        self._ble = None
        self._ble_window_end = 0
        self._wired = None
        self._ir = None
        self._link_seen = None
        self._syncing = False
        self._completing = False

    def _ble_window_open(self) -> bool:
        return time.ticks_diff(self._ble_window_end, time.ticks_ms()) > 0

    def _ble_window_ms(self) -> int:
        try:
            from config import BLE_WINDOW_MS
            return BLE_WINDOW_MS
        except Exception:
            return 1000

    def _link_present(self) -> bool:
        if self._link_seen is None:
            return False
        return time.ticks_diff(time.ticks_ms(), self._link_seen) < _LINK_TIMEOUT_MS

    def _broadcast(self, display) -> None:
        payload = self._sync_payload()
        if payload is None:
            return
        # BT is the default path: beacon only while the simultaneity window is
        # open, and go quiet once it closes (LINK/IR carry on as fallback).
        ble_open = self._ble is not None and self._ble_window_open()
        sent = False
        if ble_open:
            sent = self._safe_send(self._ble, payload) or sent
        elif self._ble is not None and self._ble._advertising:
            self._ble.stop_advertising()
        # Always beacon over the cable; it doubles as the presence heartbeat.
        if self._wired is not None:
            sent = self._safe_send(self._wired, payload) or sent
        # Only fall back to IR while no cable peer is present.
        if not self._link_present() and self._ir is not None:
            sent = self._safe_send(self._ir, payload) or sent
        if ble_open:
            self._active_transport = "BT"
        elif self._link_present():
            self._active_transport = "LINK"
        else:
            self._active_transport = "IR"
        # Broadcasting our character counts as the "sent" half of a trade.
        if self._sync_kind == _SYNC_CHARS and sent:
            try:
                import peer_manager
                peer_manager.mark_sent()
                self._session_sent = True
                self._record_completed_trade()
            except Exception:
                pass

    def _sync_payload(self):
        if self._sync_kind == _SYNC_STAMPS:
            vendor = self._vendor_stamp()
            if vendor is None:
                return None
            import stamp_manager
            stamp_id, name = vendor
            return _STAMP_SYNC_PREFIX + stamp_manager.pack(stamp_id, name).encode()
        return _pack_char(self._active_id, _my_badge())

    def _safe_send(self, link, payload) -> bool:
        try:
            link.send(payload)
            return True
        except Exception:
            return False

    def _vendor_stamp(self):
        try:
            import stamp_manager
            return stamp_manager.vendor_stamp()
        except Exception:
            return None

    def _poll_links(self, display) -> None:
        if self._ble is not None:
            for _ in range(6):
                if not self._ble.available():
                    break
                packet = self._ble.read()
                if not packet:
                    continue
                is_stamp = packet.startswith(_STAMP_SYNC_PREFIX)
                if self._sync_kind == _SYNC_STAMPS:
                    # Stamp listen mode: collect a stamp whenever heard (a vendor
                    # beacons constantly, no simultaneity window). Ignore char
                    # adverts from nearby traders.
                    if is_stamp:
                        self._active_transport = "BT"
                        self._handle_packet(packet, display)
                else:
                    # Char trade: strict simultaneity — accept a peer char only
                    # while our own window is open. Ignore stray stamp beacons.
                    if (not is_stamp) and self._ble_window_open():
                        self._active_transport = "BT"
                        self._handle_packet(packet, display)
        if self._wired is not None:
            for _ in range(4):
                if not self._wired.available():
                    break
                packet = self._wired.read()
                if packet:
                    self._link_seen = time.ticks_ms()
                    self._active_transport = "LINK"
                    self._handle_packet(packet, display)
        if self._ir is not None:
            for _ in range(3):
                if not self._ir.available():
                    break
                packet = self._ir.read()
                if packet:
                    self._handle_packet(packet, display)

    def _handle_packet(self, packet: bytes, display) -> None:
        if not self._syncing or self._completing:
            return
        if packet.startswith(_STAMP_SYNC_PREFIX):
            self._handle_stamp_packet(packet, display)
            return
        parsed = _parse_char(packet)
        if parsed is None:
            return
        cid, peer = parsed
        if self._sync_kind != _SYNC_CHARS or (peer and peer == _my_badge()):
            return

        import character_manager
        cls = character_manager.find(cid)
        if cls is None:
            self._message = "UNKNOWN CHAR"
            self._draw(display)
            return
        # Receiving a character is the "received" half of a trade, and counts
        # this as meeting a distinct attendee for the peer-trade challenges —
        # whether or not their character was newly collected.
        try:
            import peer_manager
            peer_manager.mark_received()
            if peer and peer != _my_badge():
                peer_manager.record(peer)
        except Exception:
            pass
        sent_name = self._active_name()
        # Quests stay local: unlocking a new chi exposes its registered quests.
        # An already-unlocked chi keeps the same quests and completion records.
        newly = character_manager.unlock(cid)
        if newly:
            try:
                import pet_state
                pet_state.create_fresh(cls)
            except Exception:
                pass
        if character_manager.set_active(cid) is None:
            self._message = "LOCKED"
            self._draw(display)
            return
        self._begin_complete(_SYNC_CHARS, sent_name, cls.name, newly, display)

    def _handle_stamp_packet(self, packet: bytes, display) -> None:
        try:
            text = packet[len(_STAMP_SYNC_PREFIX):].decode()
        except Exception:
            return
        import stamp_manager
        parsed = stamp_manager.unpack(text)
        if parsed is None:
            return
        stamp_id, name = parsed
        newly = stamp_manager.collect(stamp_id, name)
        if newly:
            self._refresh()
        self._begin_complete(_SYNC_STAMPS, "", name, newly, display)

    def _active_name(self) -> str:
        import character_manager
        cls = character_manager.find(self._active_id)
        return cls.name if cls is not None else self._active_id

    def _begin_complete(self, kind: str, sent: str, recv: str, new: bool,
                        display) -> None:
        # First landed packet wins; ignore repeats while we linger.
        if self._completing:
            return
        self._completing = True
        self._confirm_kind = kind
        self._trade_sent = sent
        self._trade_recv = recv
        self._trade_new = new
        self._record_completed_trade()
        now = time.ticks_ms()
        self._complete_at = time.ticks_add(now, _COMPLETE_LINGER_MS)
        self._next_broadcast = now      # re-send ours right away so the peer
                                        # also completes before we stop.
        # Keep the BT beacon alive through the linger so the peer converges too,
        # even if the trade landed near the end of the pairing window.
        if self._ble is not None:
            self._ble_window_end = self._complete_at
        self._message = "GOT " + _clip(recv.upper(), 12)
        self._draw(display)

    def _record_completed_trade(self) -> None:
        if (self._completing and self._confirm_kind == _SYNC_CHARS
                and self._session_sent and not self._trade_counted):
            try:
                import peer_manager
                peer_manager.record_completed_trade()
                self._trade_counted = True
            except OSError:
                pass

    def _finish_complete(self, display) -> None:
        # Stop transmitting/receiving and show the confirmation screen.
        self._close_links()
        self._completing = False
        self._refresh()
        self._view = _VIEW_CONFIRM
        self._draw(display)

    def _handle_confirm_button(self, btn: str, mgr) -> None:
        self._refresh()
        self._view = _VIEW_STAMPS if self._confirm_kind == _SYNC_STAMPS else _VIEW_CHARS
        self._message = ""
        self._draw(mgr._display)


def _draw_confirm(display, kind, sent: str, recv: str, new: bool,
                  transport: str) -> None:
    display.fill(_BG)
    display.fill_rect(0, 0, 240, 36, _PANEL)
    is_stamp = kind == _SYNC_STAMPS
    _center_text(display, "STAMP DONE" if is_stamp else "TRADE DONE", 14,
                 _TEXT, _PANEL)

    display.fill_rect(28, 62, 184, 92, _SEL)
    display.rect(28, 62, 184, 92, gc9a01.WHITE)
    if is_stamp:
        _center_text(display, "RECEIVED", 80, _MUTED, _SEL)
        _center_text(display, _clip(recv.upper(), 18), 102, _TEXT, _SEL)
        _center_text(display, "NEW STAMP" if new else "ALREADY HAD", 128,
                     _OK if new else _MUTED, _SEL)
    else:
        _center_text(display, "SENT " + _clip(sent.upper(), 12), 74, _MUTED, _SEL)
        _center_text(display, "GOT", 98, _MUTED, _SEL)
        _center_text(display, _clip(recv.upper(), 18), 116, _TEXT, _SEL)
        _center_text(display, "NEW!" if new else "ALREADY HAD", 138,
                     _OK if new else _MUTED, _SEL)

    _center_text(display, "VIA " + transport, 166, _MUTED, _BG)
    ui.controls(display, "OK")


def _draw_base(display, chars, selected: int, active_id: str,
               message: str, syncing: bool, total_chars: int,
               stamp_count: int, transport: str, link_active: bool = False) -> None:
    display.fill(_BG)
    display.fill_rect(0, 0, 240, 36, _PANEL)
    _center_text(display, "OZCONBASE", 14, _TEXT, _PANEL)

    if selected == len(chars):
        _draw_sync_item(display, len(chars), total_chars, selected,
                        len(chars) + 2, message, syncing, transport, link_active)
    elif selected > len(chars):
        _draw_stamp_card_item(display, stamp_count, selected,
                              len(chars) + 2, message)
    else:
        _draw_char_item(display, chars[selected], selected, len(chars) + 2,
                        active_id, message)

    if selected == len(chars):
        ui.controls(display, "SYNC")
    elif selected > len(chars):
        ui.controls(display, "VIEW")
    else:
        ui.controls(display, "USE")


def _draw_char_item(display, char, selected: int, total_items: int,
                    active_id: str, message: str) -> None:
    display.fill_rect(36, 72, 168, 64, _SEL)
    display.rect(36, 72, 168, 64, gc9a01.WHITE)
    _center_text(display, _clip(char.name.upper(), 18), 88, _TEXT, _SEL)
    _center_text(display, char.rarity.upper(), 112, _MUTED, _SEL)

    if char.id == active_id:
        status = "ACTIVE"
        color = _OK
    elif message:
        status = message
        color = _MUTED
    else:
        status = "START ACTIVATE"
        color = _MUTED
    _center_text(display, _clip(status, 22), 156, color, _BG)
    _draw_position(display, selected, total_items)


def _draw_sync_item(display, collected: int, total_chars: int, selected: int,
                    total_items: int, message: str, syncing: bool,
                    transport: str, link_active: bool = False) -> None:
    display.fill_rect(36, 72, 168, 64, _SEL)
    display.rect(36, 72, 168, 64, gc9a01.WHITE)
    _center_text(display, "TRADE", 88, _TEXT, _SEL)
    count = "{}/{} COLLECTED".format(collected, total_chars)
    _center_text(display, count, 112, _MUTED, _SEL)

    if syncing:
        # Line 1 stays PRESS TOGETHER (or a transient GOT/x message); it returns
        # to PRESS TOGETHER after each BT window. Line 2 shows once LINK/IR are
        # beaconing, which continues until you back out.
        _center_text(display, _clip(message or "PRESS TOGETHER", 22), 148, _OK, _BG)
        if link_active:
            _center_text(display, "LINK/IR ACTIVE", 166, _MUTED, _BG)
    else:
        _center_text(display, _clip(message or "START TO SHARE", 22), 156, _MUTED, _BG)
    _draw_position(display, selected, total_items)


def _draw_stamp_card_item(display, stamp_count: int, selected: int,
                          total_items: int, message: str) -> None:
    display.fill_rect(36, 72, 168, 64, _SEL)
    display.rect(36, 72, 168, 64, gc9a01.WHITE)
    _center_text(display, "STAMP CARD", 88, _TEXT, _SEL)
    count = "{} STAMP{}".format(stamp_count, "" if stamp_count == 1 else "S")
    _center_text(display, count, 112, _MUTED, _SEL)
    status = message or "START TO VIEW"
    _center_text(display, _clip(status, 22), 156, _MUTED, _BG)
    _draw_position(display, selected, total_items)


def _draw_stamps(display, stamps, selected: int, message: str,
                 syncing: bool, vendor_stamp, transport: str) -> None:
    display.fill(_BG)
    display.fill_rect(0, 0, 240, 36, _PANEL)
    _center_text(display, "STAMPS", 14, _TEXT, _PANEL)

    total_items = len(stamps) + 1
    if selected >= len(stamps):
        _draw_stamp_sync_item(display, len(stamps), selected, total_items,
                              message, syncing, vendor_stamp, transport)
    else:
        _draw_stamp_item(display, stamps[selected], selected, total_items,
                         message)

    if selected >= len(stamps):
        ui.controls(display, "SYNC")
    else:
        ui.controls(display)


def _draw_stamp_item(display, stamp, selected: int, total_items: int,
                     message: str) -> None:
    _stamp_id, name = stamp
    display.fill_rect(36, 72, 168, 64, _SEL)
    display.rect(36, 72, 168, 64, gc9a01.WHITE)
    _center_text(display, _clip(name.upper(), 18), 88, _TEXT, _SEL)
    _center_text(display, "VENDOR STAMP", 112, _MUTED, _SEL)
    _center_text(display, _clip(message or "COLLECTED", 22), 156, _OK, _BG)
    _draw_position(display, selected, total_items)


def _draw_stamp_sync_item(display, collected: int, selected: int,
                          total_items: int, message: str, syncing: bool,
                          vendor_stamp, transport: str) -> None:
    display.fill_rect(36, 72, 168, 64, _SEL)
    display.rect(36, 72, 168, 64, gc9a01.WHITE)
    _center_text(display, "STAMP", 88, _TEXT, _SEL)
    if vendor_stamp is None:
        subtitle = "{} COLLECTED".format(collected)
    else:
        subtitle = "SEND " + _clip(vendor_stamp[1].upper(), 12)
    _center_text(display, _clip(subtitle, 18), 112, _MUTED, _SEL)

    if message:
        status = message
    elif syncing:
        status = "VIA " + transport
    elif vendor_stamp is None:
        status = "START TO RECEIVE"
    else:
        status = "START TO SEND"
    _center_text(display, _clip(status, 22), 156, _OK if syncing else _MUTED, _BG)
    _draw_position(display, selected, total_items)


def _draw_position(display, selected: int, total_items: int) -> None:
    if total_items <= 1:
        return
    draw_text(display, "<", 20, 112, _MUTED, _BG)
    draw_text(display, ">", 212, 112, _MUTED, _BG)
    _center_text(display, "%d/%d" % (selected + 1, total_items), 184, _MUTED, _BG)




def _center_text(display, text: str, y: int, fg: int, bg: int) -> None:
    x = (240 - len(text) * 8) // 2
    draw_text(display, text, x, y, fg, bg)


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + ">"


# ── Character trade payload ───────────────────────────────────────────────────
# Wire format: OZC1:<char_id>:<sender_badge_id>
# Chi quests unlock from the receiver's registry; no quest completion or
# progress is sent. Newly available quests must be completed by the receiver.
# The sender badge id lets the receiver count *unique* peers for the
# "trade with N attendees" challenges (peer_manager). All event badges run the
# same firmware, so the extra field is always present.

def _my_badge() -> str:
    try:
        import badge_id
        return badge_id.badge_id()
    except Exception:
        return ""


def _pack_char(char_id: str, badge: str) -> bytes:
    return _CHAR_SYNC_PREFIX + "{}:{}".format(char_id, badge).encode()


def _parse_char(packet: bytes):
    """Return (char_id, sender_badge_id) or None. sender id is "" if absent."""
    if not packet.startswith(_CHAR_SYNC_PREFIX):
        return None
    try:
        body = packet[len(_CHAR_SYNC_PREFIX):].decode()
    except Exception:
        return None
    parts = body.split(":")
    return parts[0], (parts[1] if len(parts) > 1 else "")
