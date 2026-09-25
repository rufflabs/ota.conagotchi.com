"""Games submenu screen."""
import ui

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen


# Add future games here, then handle their id in _launch_selected().
_GAME_ITEMS = (
    ("Simon", "simon"),
    ("Snake", "snake"),
)


class GamesMenuScreen(Screen):
    """A themed launcher for badge games."""

    def __init__(self) -> None:
        self._sel = 0
        self._top = 0

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT:
            self._move(-1, mgr._display)
        elif btn == RIGHT:
            self._move(1, mgr._display)
        elif btn == START:
            self._launch_selected(mgr)

    def _move(self, delta: int, display) -> None:
        self._sel = (self._sel + delta) % len(_GAME_ITEMS)
        self._top = ui.clamp_scroll(self._sel, self._top, len(_GAME_ITEMS))
        self._draw(display)

    def _launch_selected(self, mgr) -> None:
        game_id = _GAME_ITEMS[self._sel][1]
        if game_id == "simon":
            from screens.simon import SimonScreen
            mgr.push(SimonScreen())
        elif game_id == "snake":
            from screens.snake import SnakeScreen
            mgr.push(SnakeScreen())

    def _draw(self, display) -> None:
        ui.screen(display, "GAMES")
        if not _GAME_ITEMS:
            ui.status(display, "NO GAMES", 112, "muted")
            ui.controls(display)
            return
        ui.list_view(display, [g[0] for g in _GAME_ITEMS], self._sel, self._top)
        ui.controls(display, "PLAY")
