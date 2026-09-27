"""Vendor Badge stamping screen.

Only reachable when Vendor Badge mode is enabled (Settings -> Debug -> Vendor
Mode), which adds a "Ven" button to the pet ring. The screen lists the vendors
configured in ``config.VENDOR_STAMPS``; highlight one and press START to begin
broadcasting that vendor's stamp over Bluetooth only (a user decision: no cable
or IR for stamps). Any nearby badge listening for stamps (trade_session,
STAMPS) collects it. Broadcasting is
continuous so one vendor can stamp a line of attendees; press START again (or
SELECT) to stop. The wire protocol is the shared OZS1 stamp packet built by
``stamp_manager.make_sync_payload`` — identical to the one trade_session sends.
"""
import random
import time

from buttons import BOOT, LEFT, RIGHT, SELECT, START
import ui
from screen_manager import Screen


_BROADCAST_MIN_MS = 400        # beacon the stamp roughly this often while stamping
_BROADCAST_JITTER_MS = 400


class VendorScreen(Screen):
    """Pick a vendor and continuously broadcast its stamp over Bluetooth."""

    def __init__(self) -> None:
        self._vendors = _load_vendors()
        self._sel = 0
        self._message = ""
        self._stamping = False
        self._ble = None
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
            self._schedule_broadcast(time.ticks_ms(), 60)
            self._message = "STAMPING"
        else:
            self._message = "BT N/A"
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
        if vendor is None or self._ble is None:
            return
        import stamp_manager
        try:
            self._ble.send(stamp_manager.make_sync_payload(vendor[0], vendor[1]))
        except Exception:
            pass

    def _drain_links(self) -> None:
        # Vendors only transmit; draining keeps the scan queue from filling.
        if self._ble is not None:
            while self._ble.available():
                self._ble.read()

    # ── Transport ───────────────────────────────────────────────────────────────

    def _open_links(self) -> bool:
        if self._ble is None:
            try:
                from link import BleLink
                self._ble = BleLink()
            except Exception:
                self._ble = None
        return self._ble is not None

    def _close_links(self) -> None:
        if self._ble is not None:
            try:
                self._ble.deinit()
            except Exception:
                pass
        self._ble = None

    # ── Drawing ─────────────────────────────────────────────────────────────────

    def _draw(self, display) -> None:
        ui.screen(display, "VENDOR")

        vendor = self._selected()
        if vendor is None:
            ui.card(display, ("NO VENDORS", "SET config"))
        else:
            ui.card(display, (vendor[1].upper(), "STAMP"))

        if self._message:
            status = self._message
        elif self._stamping:
            status = "VIA " + self._active_transport
        elif vendor is not None:
            status = "START TO STAMP"
        else:
            status = ""
        ui.status(display, status, 156, "success" if self._stamping else "muted")

        if vendor is not None and not self._stamping:
            ui.pager(display, self._sel, len(self._vendors))

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
