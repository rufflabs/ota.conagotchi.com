"""Games submenu screen."""
from menu import ListScreen


# Add future games here, then handle their id in activate().
_GAME_ITEMS = (
    ("Simon", "simon"),
    ("Snake", "snake"),
    ("Blocks", "blocks"),
    ("Rock Paper Scissors", "rps"),
    ("BLAT", "blat"),                 # chat; here until it has a better home
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
        elif key == "blocks":
            from screens.blocks import BlocksScreen
            mgr.push(BlocksScreen())
        elif key == "rps":
            from screens.rps import RpsModeScreen
            mgr.push(RpsModeScreen())
        elif key == "blat":
            from screens.blat import BlatScreen
            mgr.push(BlatScreen())
