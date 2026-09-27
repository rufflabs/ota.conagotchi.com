"""Flashlight mode: every RGB LED full white, and a white screen.

Chosen from Settings -> Badge -> Badge Mode. Unlike Blinky it is never saved
as the badge mode (choosing it saves Chi): eight WS2812s at full output are a
real battery draw, so a reboot must not come back up with the flashlight on.
Any button returns to the pet.

The two indicator LEDs (red alert, green raffle) are left off, as in Blinky:
they carry meaning elsewhere and are no use as a light.
"""
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen
import ui

_WHITE = (255, 255, 255)   # full output on every channel
_WHITE_565 = 0xFFFF
_BLACK_565 = 0x0000


class FlashlightScreen(Screen):
    """Static screen, static LEDs: both are written once on entry."""

    async def enter(self, display, leds, mgr) -> None:
        leds.set_alert(False)
        leds.set_raffle(False)
        leds.rgb_fill(*_WHITE)
        leds.rgb_show()
        self._draw(display)

    async def exit(self, display, leds, mgr) -> None:
        leds.all_off()

    async def pause(self, display, leds, mgr) -> None:
        leds.rgb_off()

    async def resume(self, display, leds, mgr) -> None:
        await self.enter(display, leds, mgr)

    def handle_button(self, btn, mgr) -> None:
        """Any button turns the light off and goes back to the pet, which is
        already the saved mode."""
        if btn in (SELECT, BOOT, START, LEFT, RIGHT):
            from screens.conagotchi import ConagotchiScreen
            mgr.switch_to(ConagotchiScreen())

    def _draw(self, display) -> None:
        # Deliberately not themed: the screen is part of the light.
        display.fill(_WHITE_565)
        ui.center_text(display, "FLASHLIGHT", 108, _BLACK_565, _WHITE_565)
        ui.center_text(display, "ANY BUTTON EXITS", 124, _BLACK_565, _WHITE_565)
