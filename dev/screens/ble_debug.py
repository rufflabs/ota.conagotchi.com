"""Debug -> Hardware -> Bluetooth: a BLE beacon send/receive RSSI tool.

Two modes for tuning proximity (BLE_RSSI_MIN) and sanity-checking the radio:

  Send    — START toggles a continuous "debug beacon" advertisement on/off.
  Receive — scans for those debug beacons and shows the live RSSI (latest,
            strongest, weakest, count) so you can see how signal strength
            changes with distance and pick a gate value.

Uses `bluetooth.BLE()` directly (not BleLink) so it can report the RAW RSSI of
every beacon regardless of the trade gate, and it reuses `ble.encode_adv` /
`decode_adv` for the beacon format. Only one screen drives the radio at a time,
so sharing the BLE singleton with the trade path is fine.
"""
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from menu import Menu
from screen_manager import Screen
import ble

# Distinct payload so the receiver only lists our debug beacons, not trade
# adverts (which encode_adv/decode_adv would also round-trip).
_DEBUG_BEACON = b"OZDBG"

_MENU = "menu"
_SEND = "send"
_RECV = "recv"
_ROWS = ("Send", "Receive")


class BleDebugScreen(Screen):
    def __init__(self):
        self._view = _MENU
        self._menu = Menu([(label, None, i) for i, label in enumerate(_ROWS)])
        self._radio = None
        self._advertising = False
        self._scanning = False
        self._latest = None
        self._best = None      # strongest (highest) rssi seen
        self._worst = None     # weakest (lowest) rssi seen
        self._count = 0
        self._last_draw = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr):
        self._last_draw = None
        self._draw(display)

    async def exit(self, display, leds, mgr):
        self._stop_all()

    async def update(self, display, leds, mgr):
        self._draw(display)
        if self._view == _MENU:
            self._menu.tick(display)

    def handle_button(self, btn, mgr):
        if self._view == _MENU:
            if btn in (BOOT, SELECT):
                self._stop_all()
                mgr.pop()
            elif btn == LEFT or btn == RIGHT:
                self._menu.step(mgr._display, 1 if btn == RIGHT else -1)
                self._last_draw = self._snapshot()   # repainted in place
            elif btn == START:
                self._open(_SEND if self._menu.key == 0 else _RECV)
            return
        # Send / Receive modes: SEL/BOOT returns to the menu.
        if btn in (BOOT, SELECT):
            self._to_menu()
            return
        if self._view == _SEND and btn == START:
            self._toggle_advertise()
        elif self._view == _RECV and btn == START:
            self._reset_readings()

    # ── radio control ────────────────────────────────────────────────────────

    def _radio_on(self):
        if self._radio is None:
            import bluetooth
            self._radio = bluetooth.BLE()
        self._radio.active(True)

    def _open(self, view):
        self._view = view
        self._last_draw = None
        self._radio_on()
        if view == _RECV:
            self._reset_readings()
            self._start_scan()

    def _to_menu(self):
        self._stop_all()
        self._view = _MENU
        self._last_draw = None

    def _toggle_advertise(self):
        self._radio_on()
        if self._advertising:
            self._stop_advertise()
        else:
            from config import BLE_ADV_INTERVAL_US
            adv = ble.encode_adv(_DEBUG_BEACON)
            self._radio.gap_advertise(BLE_ADV_INTERVAL_US, adv_data=adv,
                                      connectable=False)
            self._advertising = True
        self._last_draw = None

    def _stop_advertise(self):
        if self._radio is not None and self._advertising:
            try:
                self._radio.gap_advertise(None)
            except Exception:
                pass
        self._advertising = False

    def _start_scan(self):
        self._radio.irq(self._irq)
        try:
            self._radio.gap_scan(0, 30000, 30000, False)
        except Exception:
            pass
        self._scanning = True

    def _stop_scan(self):
        if self._radio is not None and self._scanning:
            try:
                self._radio.gap_scan(None)
            except Exception:
                pass
            try:
                self._radio.irq(None)
            except Exception:
                pass
        self._scanning = False

    def _stop_all(self):
        self._stop_advertise()
        self._stop_scan()

    def _irq(self, event, data):
        if event != ble.IRQ_SCAN_RESULT:
            return
        addr_type, addr, adv_type, rssi, adv_data = data
        if ble.decode_adv(bytes(adv_data)) != _DEBUG_BEACON:
            return
        self._count += 1
        self._latest = rssi
        if self._best is None or rssi > self._best:
            self._best = rssi
        if self._worst is None or rssi < self._worst:
            self._worst = rssi

    def _reset_readings(self):
        self._latest = self._best = self._worst = None
        self._count = 0
        self._last_draw = None

    # ── drawing ──────────────────────────────────────────────────────────────

    def _snapshot(self):
        return (self._view, self._menu.sel, self._advertising, self._count,
                self._latest, self._best, self._worst)

    def _draw(self, display):
        """The frame is redrawn only when the view or the menu changes; live
        readings repaint their own lines, so Receive does not blink."""
        snap = self._snapshot()
        if snap == self._last_draw:
            return
        frame_changed = self._last_draw is None or self._last_draw[:3] != snap[:3]
        self._last_draw = snap
        if self._view == _MENU:
            if frame_changed:
                ui.screen(display, "BLUETOOTH")
                self._menu.draw(display)
                ui.controls(display, "OPEN")
        elif self._view == _SEND:
            if frame_changed:
                ui.screen(display, "BLE SEND")
                on = self._advertising
                ui.status(display, "BEACON " + ("ON" if on else "OFF"), 92,
                          "success" if on else "muted")
                ui.status(display, "debug beacon", 116, "muted")
                ui.controls(display, "STOP" if on else "SEND")
        elif self._view == _RECV:
            if frame_changed:
                ui.screen(display, "BLE RECEIVE")
                ui.controls(display, "CLEAR")
            self._paint_readings(display)

    def _paint_readings(self, display):
        if self._latest is None:
            ui.status_row(display, "listening...", 78, "accent")
            ui.status_row(display, "", 112, "muted")
        else:
            ui.status_row(display, "%d dBm" % self._latest, 78, "accent")
            ui.status_row(display, "strong %d  weak %d" % (self._best, self._worst),
                          112, "muted")
        try:
            from config import BLE_RSSI_MIN
            gate = BLE_RSSI_MIN
        except Exception:
            gate = None
        line = "rx %d" % self._count
        if gate is not None:
            line += "   gate %d" % gate
        ui.status_row(display, line, 150, "muted")
