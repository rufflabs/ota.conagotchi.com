"""Splash / boot logo screen.

Shows a splash image chosen by ``splash_manager`` (a persisted selection, the
special max-level screen, or a random regular splash), then auto-advances to
ConagotchiScreen.  The splash stays up for a guaranteed viewable period
(``_HOLD_MS``) even if boot finished sooner — button presses do NOT cut it
short.  If no splash art is present, a colour-fill fallback with text is drawn.
"""
import gc9a01py as gc9a01
from screen_manager import Screen
from image_utils import blit_image, draw_text
import time

_HOLD_MS      = 3500                          # guaranteed on-screen time (3–5 s)
_BG_COLOR     = gc9a01.color565(10, 20, 40)   # dark navy fallback


class SplashScreen(Screen):

    async def enter(self, display, leds, mgr) -> None:
        self._start = time.ticks_ms()
        self._advanced = False
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
        from screens.conagotchi import ConagotchiScreen
        mgr.switch_to(ConagotchiScreen())


def _draw_fallback(display) -> None:
    display.fill(_BG_COLOR)
    # Centre "OzSec 2026" (10 chars × 8px = 80px wide) at x=80, y=105
    draw_text(display, "OzSec 2026",  80, 105, gc9a01.WHITE,  _BG_COLOR)
    draw_text(display, "Conagotchi",  80, 120, gc9a01.YELLOW, _BG_COLOR)
