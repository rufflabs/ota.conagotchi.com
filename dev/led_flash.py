"""A short flash of the RGB LEDs that does not block the game loop.

    flash = LedFlash()
    flash.start(leds, (0, 40, 0), 150)   # in reaction to something
    flash.tick(leds)                      # from every update(): turns it off

Only the RGB strip is touched; the red alert and green raffle LEDs keep their
meaning elsewhere.
"""
import time


class LedFlash:
    def __init__(self):
        self._until = None

    def start(self, leds, rgb, ms) -> None:
        leds.rgb_fill(*rgb)
        leds.rgb_show()
        self._until = time.ticks_add(time.ticks_ms(), ms)

    def tick(self, leds) -> None:
        if self._until is not None and time.ticks_diff(time.ticks_ms(), self._until) >= 0:
            self._until = None
            leds.rgb_off()

    @property
    def active(self) -> bool:
        return self._until is not None
