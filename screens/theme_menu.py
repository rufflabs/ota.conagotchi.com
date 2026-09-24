"""Theme picker — select and persist the active UI theme.

LEFT/RIGHT move the selection; START applies the highlighted theme (persisted to
data/theme.txt) and redraws immediately so the new look previews live; SELECT /
BOOT returns.  The active theme is marked with `*`.
"""
import ui
import theme

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen


class ThemeMenuScreen(Screen):

    def __init__(self) -> None:
        self._names = theme.available()
        active = theme.name()
        self._sel = self._names.index(active) if active in self._names else 0

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT:
            self._sel = (self._sel - 1) % len(self._names)
            self._draw(mgr._display)
        elif btn == RIGHT:
            self._sel = (self._sel + 1) % len(self._names)
            self._draw(mgr._display)
        elif btn == START:
            theme.set_active(self._names[self._sel])   # persists + live preview
            self._draw(mgr._display)

    def _draw(self, display) -> None:
        active = theme.name()
        ui.screen(display, "THEME")
        labels = [("* " if n == active else "  ") + n.upper() for n in self._names]
        ui.list_view(display, labels, self._sel, 0)
        ui.controls(display, "APPLY")
