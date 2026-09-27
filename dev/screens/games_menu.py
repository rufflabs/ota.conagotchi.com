"""Games submenu screen."""
from menu import ListScreen


# Add future games here, then handle their id in activate().
_GAME_ITEMS = (
    ("Simon", "simon"),
    ("Snake", "snake"),
)


class GamesMenuScreen(ListScreen):
    """A themed launcher for badge games."""

    title = "GAMES"
    empty = "NO GAMES"

    def rows(self):
        return [(label, None, key) for label, key in _GAME_ITEMS]

    def confirm(self):
        return "PLAY"

    def activate(self, mgr) -> None:
        key = self.menu.key
        if key == "simon":
            from screens.simon import SimonScreen
            mgr.push(SimonScreen())
        elif key == "snake":
            from screens.snake import SnakeScreen
            mgr.push(SnakeScreen())
