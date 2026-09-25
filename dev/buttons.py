import asyncio
from machine import Pin
import time
from config import (
    PIN_BTN_BOOT, PIN_BTN_START, PIN_BTN_SELECT,
    PIN_BTN_RIGHT, PIN_BTN_LEFT, DEBOUNCE_MS,
)

BOOT   = "BOOT"
START  = "START"
SELECT = "SELECT"
RIGHT  = "RIGHT"
LEFT   = "LEFT"

_PINS = {
    BOOT:   PIN_BTN_BOOT,
    START:  PIN_BTN_START,
    SELECT: PIN_BTN_SELECT,
    RIGHT:  PIN_BTN_RIGHT,
    LEFT:   PIN_BTN_LEFT,
}

_BUF_MAX = 8


class Buttons:
    def __init__(self):
        self._pins = {
            name: Pin(pin, Pin.IN, Pin.PULL_UP)
            for name, pin in _PINS.items()
        }
        self._last_ms = {name: 0 for name in _PINS}
        self._down = {name: False for name in _PINS}  # debounced press state
        self._enabled = {name: True for name in _PINS}
        self._buf = []

        for name, pin in self._pins.items():
            pin.irq(
                trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
                handler=lambda p, n=name: self._isr(n),
            )

    def _isr(self, name):
        """Debounced press/release state machine (buttons are active-low).

        A press is queued once, on a confirmed released→pressed transition, and
        another press is not accepted until the button is seen released again —
        so a single physical press can never enqueue twice, even with contact
        chatter or a glitchy release mid-press. Edges within DEBOUNCE_MS of the
        last confirmed transition are treated as bounce and ignored on both the
        press and the release. Triggered on both edges so releases are observed;
        the live pin level gives the true current state.
        """
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ms[name]) < DEBOUNCE_MS:
            return  # inside the debounce window — bounce, ignore
        pressed = self._pins[name].value() == 0
        if pressed == self._down[name]:
            return  # no confirmed change (e.g. bounce that already settled back)
        self._down[name] = pressed
        self._last_ms[name] = now
        if pressed and len(self._buf) < _BUF_MAX:
            self._buf.append(name)

    def clear(self) -> None:
        """Discard all queued events. Call after screen transitions to prevent
        the triggering press from being re-delivered to the incoming screen."""
        self._buf.clear()

    async def get(self):
        """Wait for and return the next button name."""
        while not self._buf:
            await asyncio.sleep_ms(10)
        return self._buf.pop(0)

    def pressed(self, name):
        """Return True if the enabled button is currently held down."""
        return self._enabled.get(name, True) and self.raw_pressed(name)

    def raw_pressed(self, name):
        """Return True if the physical button is currently held down."""
        return self._pins[name].value() == 0

    def enabled(self, name):
        """Return True if button events should be routed to normal screens."""
        return self._enabled.get(name, True)

    def set_enabled(self, name, enabled):
        """Enable or disable app-level handling for one button."""
        if name in self._enabled:
            self._enabled[name] = bool(enabled)
            if not enabled:
                self._buf = [btn for btn in self._buf if btn != name]

    def set_enabled_map(self, enabled):
        """Enable or disable app-level handling for several buttons."""
        for name, value in enabled.items():
            self.set_enabled(name, value)
