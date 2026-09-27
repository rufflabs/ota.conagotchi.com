"""Splash / boot logo screen.

Shows a splash image chosen by ``splash_manager`` (a persisted selection, the
special max-level screen, or a random regular splash), then auto-advances to
ConagotchiScreen.  The splash stays up for a guaranteed viewable period
(``_HOLD_MS``) even if boot finished sooner — button presses do NOT cut it
short.  If no splash art is present, a themed text fallback is drawn.

The art itself is bespoke (a full-screen blit); only the fallback goes through
the ui framework.
"""
from screen_manager import Screen
from image_utils import blit_image
import time

_HOLD_MS      = 3500                          # guaranteed on-screen time (3–5 s)


class SplashScreen(Screen):

    async def enter(self, display, leds, mgr) -> None:
        self._start = time.ticks_ms()
        self._advanced = False
        draw_boot_image(display)

    async def update(self, display, leds, mgr) -> None:
        if not self._advanced and time.ticks_diff(time.ticks_ms(), self._start) >= _HOLD_MS:
            self._advance(mgr)

    def handle_button(self, btn: str, mgr) -> None:
        # Intentionally ignored: the splash holds for the full viewable period.
        pass

    def _advance(self, mgr) -> None:
        if self._advanced:
            return
        self._advanced = True
        mgr.switch_to(_mode_screen())


def draw_boot_image(display) -> None:
    """Draw the boot splash art, or the colour-fill fallback if it is missing.

    Shared with Blinky mode, which shows the same image as its backdrop."""
    path = None
    try:
        import splash_manager
        path = splash_manager.resolve_boot()
    except Exception:
        path = None
    try:
        if path:
            blit_image(display, path)
        else:
            _draw_fallback(display)
    except OSError:
        _draw_fallback(display)


def _draw_fallback(display) -> None:
    """Text-only boot screen for a badge with no splash art, in the theme."""
    import ui
    ui.clear(display)
    ui.text_lines(display, ("OzSec 2026", ("Conagotchi", "accent")), 105,
                  line_h=15)


def _mode_screen():
    """The screen for the saved badge mode, defaulting to the pet app.

    A badge left in Blinky comes back up in Blinky. Any failure reading settings
    falls back to Conagotchi rather than stranding the badge on an LED screen."""
    try:
        from settings_state import BadgeSettings, MODE_BLINKY
        if BadgeSettings().badge_mode == MODE_BLINKY:
            from screens.blinky import BlinkyScreen
            return BlinkyScreen()
    except Exception as e:
        print("badge mode fallback:", e)
    from screens.conagotchi import ConagotchiScreen
    return ConagotchiScreen()
