"""Vendor Badge stamping screen.

Only reachable when Vendor Badge mode is enabled (Settings -> Debug -> Vendor
Mode), which adds a "Ven" button to the pet ring. The screen lists the vendors
configured in ``config.VENDOR_STAMPS``; highlight one and press START to begin
broadcasting that vendor's stamp over BT, the LINK cable, and IR. Any nearby
badge in listen mode (OzConBase -> Stamps -> START) collects it. Broadcasting is
continuous so one vendor can stamp a line of attendees; press START again (or
SELECT) to stop. The wire protocol is the shared OZS1 stamp packet built by
``stamp_manager.make_sync_payload`` — identical to the one OzConBase sends.
"""
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
    global _BG, _PANEL, _SEL, _TEXT, _MUTED, _OK
    import theme
    t = theme.get()
    _BG, _PANEL, _SEL = t.bg, t.surface, t.sel
    _TEXT, _MUTED, _OK = t.text, t.muted, t.success


_BROADCAST_MIN_MS = 400        # beacon the stamp roughly this often while stamping
_BROADCAST_JITTER_MS = 400
_LINK_TIMEOUT_MS = 3000        # treat the cable as connected if a peer frame
                               # arrived on it within this window.


class VendorScreen(Screen):
    """Pick a vendor and continuously broadcast its stamp over LINK/IR."""

    def __init__(self) -> None:
        self._vendors = _load_vendors()
        self._sel = 0
        self._message = ""
        self._stamping = False
        self._ble = None
        self._wired = None
        self._ir = None
        self._link_seen = None
        self._active_transport = "BT"
        self._next_broadcast = 0

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        self._close_links()

    async def update(self, display, leds, mgr) -> None:
        if not self._stamping:
            return
        now = time.ticks_ms()
        self._drain_links()
        if time.ticks_diff(now, self._next_broadcast) >= 0:
            self._broadcast()
            self._schedule_broadcast(now)
            self._draw(display)   # refresh the LINK/IR transport label

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            if self._stamping:
                self._stop()
                self._message = "STAMP OFF"
                self._draw(mgr._display)
            else:
                mgr.pop()
        elif btn == LEFT:
            self._move(-1, mgr._display)
        elif btn == RIGHT:
            self._move(1, mgr._display)
        elif btn == START:
            self._toggle(mgr._display)

    # ── Selection ───────────────────────────────────────────────────────────────

    def _move(self, delta: int, display) -> None:
        if self._stamping or not self._vendors:
            return
        self._sel = (self._sel + delta) % len(self._vendors)
        self._message = ""
        self._draw(display)

    def _selected(self):
        if not self._vendors:
            return None
        return self._vendors[self._sel]

    # ── Stamping ────────────────────────────────────────────────────────────────

    def _toggle(self, display) -> None:
        if self._stamping:
            self._stop()
            self._message = "STAMP OFF"
        elif self._selected() is None:
            self._message = "NO VENDORS"
        elif self._open_links():
            self._stamping = True
            self._link_seen = None
            self._active_transport = "IR"
            self._schedule_broadcast(time.ticks_ms(), 60)
            self._message = "STAMPING"
        else:
            self._message = "LINK N/A"
        self._draw(display)

    def _stop(self) -> None:
        self._close_links()
        self._stamping = False

    def _schedule_broadcast(self, now: int, first_delay: int = None) -> None:
        if first_delay is None:
            first_delay = _BROADCAST_MIN_MS + random.randint(0, _BROADCAST_JITTER_MS)
        self._next_broadcast = time.ticks_add(now, first_delay)

    def _broadcast(self) -> None:
        vendor = self._selected()
        if vendor is None:
            return
        import stamp_manager
        payload = stamp_manager.make_sync_payload(vendor[0], vendor[1])
        # Constantly beacon on every transport so any nearby badge in listen
        # mode collects the stamp. BT advertising is continuous once armed.
        if self._ble is not None:
            self._safe_send(self._ble, payload)
        if self._wired is not None:
            self._safe_send(self._wired, payload)
        if not self._link_present() and self._ir is not None:
            self._safe_send(self._ir, payload)
        self._active_transport = "BT"

    def _safe_send(self, link, payload) -> None:
        try:
            link.send(payload)
        except Exception:
            pass

    def _drain_links(self) -> None:
        # Vendors only transmit, but draining RX keeps the buffers from growing
        # and lets us detect a connected cable peer for the transport label.
        if self._ble is not None:
            while self._ble.available():
                self._ble.read()
        if self._wired is not None:
            for _ in range(4):
                if not self._wired.available():
                    break
                if self._wired.read():
                    self._link_seen = time.ticks_ms()
        if self._ir is not None:
            for _ in range(3):
                if not self._ir.available():
                    break
                self._ir.read()

    def _link_present(self) -> bool:
        if self._link_seen is None:
            return False
        return time.ticks_diff(time.ticks_ms(), self._link_seen) < _LINK_TIMEOUT_MS

    # ── Transports ──────────────────────────────────────────────────────────────

    def _open_links(self) -> bool:
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
        self._wired = None
        self._ir = None
        self._link_seen = None

    # ── Drawing ─────────────────────────────────────────────────────────────────

    def _draw(self, display) -> None:
        _sync_theme()
        display.fill(_BG)
        display.fill_rect(0, 0, 240, 36, _PANEL)
        _center_text(display, "VENDOR", 14, _TEXT, _PANEL)

        vendor = self._selected()
        display.fill_rect(36, 72, 168, 64, _SEL)
        display.rect(36, 72, 168, 64, gc9a01.WHITE)
        if vendor is None:
            _center_text(display, "NO VENDORS", 96, _TEXT, _SEL)
            _center_text(display, "SET config", 116, _MUTED, _SEL)
        else:
            _center_text(display, _clip(vendor[1].upper(), 18), 88, _TEXT, _SEL)
            _center_text(display, "STAMP", 112, _MUTED, _SEL)

        if self._message:
            status = self._message
        elif self._stamping:
            status = "VIA " + self._active_transport
        elif vendor is not None:
            status = "START TO STAMP"
        else:
            status = ""
        _center_text(display, _clip(status, 22), 156, _OK if self._stamping else _MUTED, _BG)

        if vendor is not None and len(self._vendors) > 1 and not self._stamping:
            _draw_position(display, self._sel, len(self._vendors))

        ui.controls(display, "STAMP" if not self._stamping else "STOP")


def _load_vendors():
    try:
        import config
        out = []
        for entry in getattr(config, "VENDOR_STAMPS", ()):
            try:
                out.append((str(entry[0]), str(entry[1])))
            except (IndexError, TypeError):
                continue
        return tuple(out)
    except Exception:
        return ()


def _draw_position(display, selected: int, total_items: int) -> None:
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
