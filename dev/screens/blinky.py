"""Blinky mode: a slow colour fade across the RGB LEDs, over the boot art.

A "just look nice on a lanyard" mode for when nobody is playing with the pet.
Selected from Settings -> Badge Mode, persisted, and honoured at boot, so a badge
left in Blinky comes back up in Blinky. The display shows the boot splash image.

Each LED breathes on its own period, so they drift in and out of step and the
strip reads as random rather than as one block pulsing together. The periods are
deliberately unequal and not simple multiples of each other, which makes the
combined pattern take a very long time to repeat while staying a pure function of
elapsed time - no RNG, no stored state, and testable.

The two indicator LEDs (red alert, green raffle) are deliberately left off: they
carry meaning elsewhere in the app, and blinking them here would look like the
pet needs attention.

Brightness deliberately stays in the same range as the pet screen, which runs at
0.04 (see conagotchi._LED_BRIGHTNESS). Eight WS2812s at full output is both
unpleasant to look at and a real battery draw.
"""
import math
import time

from buttons import BOOT, SELECT, START
from config import NUM_RGB_LEDS
from leds import hue_to_rgb
from screen_manager import Screen

_HUE_PERIOD_MS = 24000   # one full trip around the colour wheel
_FADE_BASE_MS = 2600     # LED 0's breath
_FADE_STEP_MS = 430      # each LED breathes a little slower than the one before
_HUE_SPREAD = 0.37       # hue offset per LED, so they are not all the same colour
_PHASE_OFFSET_MS = 610   # stagger the starting phases, so entry is not a uniform dim
_PEAK_BRIGHTNESS = 0.05  # cf. conagotchi._LED_BRIGHTNESS = 0.04
_FLOOR_BRIGHTNESS = 0.004  # never fully dark, so it reads as a fade not a flash
_FRAME_MS = 33

_TAU = 6.283185307179586


class BlinkyScreen(Screen):
    """Static display, animated LEDs. The screen is drawn once on entry and the
    update tick only touches the LED strip, so there is nothing to flicker."""

    def __init__(self):
        self._t0 = time.ticks_ms()
        self._last = None   # last written frame, to skip redundant strip writes

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        self._t0 = time.ticks_ms()
        self._last = None
        leds.set_alert(False)
        leds.set_raffle(False)
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        leds.all_off()

    async def pause(self, display, leds, mgr) -> None:
        leds.rgb_off()

    async def resume(self, display, leds, mgr) -> None:
        await self.enter(display, leds, mgr)

    def next_update_ms(self) -> int:
        return _FRAME_MS

    async def update(self, display, leds, mgr) -> None:
        frame = self.frame_at(time.ticks_diff(time.ticks_ms(), self._t0))
        if frame != self._last:
            self._last = frame
            for i in range(len(frame)):
                r, g, b = frame[i]
                leds.rgb_set(i, r, g, b)
            leds.rgb_show()

    # ── animation ────────────────────────────────────────────────────────────

    @staticmethod
    def fade_period_ms(index):
        """This LED's breath length. Unequal per LED, which is what desynchronises
        the strip."""
        return _FADE_BASE_MS + index * _FADE_STEP_MS

    @staticmethod
    def colour_for(index, elapsed_ms):
        """The (r, g, b) LED `index` should show `elapsed_ms` into the animation.

        Hue drifts on one shared slow cycle, offset per LED, while brightness
        follows a raised cosine on that LED's own period. Pure function of index
        and elapsed time, which is what makes it testable off-hardware."""
        if elapsed_ms < 0:
            elapsed_ms = 0
        period = BlinkyScreen.fade_period_ms(index)
        # Offset as well as varied periods: without this every LED would sit at
        # the floor together at t=0, so entering Blinky would start with a
        # uniform dim before the strip drifted apart.
        phase = ((elapsed_ms + index * _PHASE_OFFSET_MS) % period) / period
        level = (1.0 - math.cos(phase * _TAU)) / 2.0      # 0 -> 1 -> 0
        scale = _FLOOR_BRIGHTNESS + (_PEAK_BRIGHTNESS - _FLOOR_BRIGHTNESS) * level
        hue = ((elapsed_ms % _HUE_PERIOD_MS) / _HUE_PERIOD_MS
               + index * _HUE_SPREAD) % 1.0
        r, g, b = hue_to_rgb(hue)
        return (int(r * scale), int(g * scale), int(b * scale))

    @classmethod
    def frame_at(cls, elapsed_ms):
        """Colours for the whole strip at a point in time."""
        return tuple(cls.colour_for(i, elapsed_ms) for i in range(NUM_RGB_LEDS))

    # ── input ────────────────────────────────────────────────────────────────

    def handle_button(self, btn, mgr) -> None:
        """Any of the three obvious buttons leaves Blinky.

        Leaving also clears the saved mode. Without that the badge would bounce
        straight back into Blinky on the next boot, which would look like it was
        stuck."""
        if btn in (SELECT, BOOT, START):
            _set_mode("conagotchi")
            from screens.conagotchi import ConagotchiScreen
            mgr.switch_to(ConagotchiScreen())

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw(self, display) -> None:
        """Show the boot art as a static backdrop; only the LEDs animate.

        Imported lazily: splash imports this module from _mode_screen(), and
        keeping both directions lazy avoids any import-order surprise."""
        from screens.splash import draw_boot_image
        draw_boot_image(display)


def _set_mode(mode):
    """Persist the badge mode, ignoring a filesystem that will not cooperate."""
    try:
        from settings_state import BadgeSettings
        s = BadgeSettings()
        s.badge_mode = mode
        s.save()
        return True
    except Exception:
        return False
