"""Collection: the bag button's menu (it replaced the OzConBase screen).

    COLLECTION
      Chi's    collected characters; START makes one active
      Items    coming soon
      Trade    choose a Chi and trade it (screens/trade.py)
      Stamps   collect vendor stamps; vendors stamp others (screens/stamps.py)

Lists are menu.ListScreen, like every list on the badge. Making a Chi active
does not leave the list; the pet screen underneath is rebuilt when Collection
is closed, so it shows the new character.
"""
import ui
from buttons import BOOT, SELECT, START
from menu import ListScreen
from screen_manager import Screen

# Last row of the Chi list while any character is still locked.
COLLECT_HINT = "Trade Chi's with others to collect them all!"


class CollectionScreen(ListScreen):
    """Top-level Collection menu."""

    title = "COLLECTION"

    def __init__(self) -> None:
        super().__init__()
        import character_manager
        self._entry_char = character_manager.get_active().id

    def rows(self):
        import character_manager
        chis = "%d/%d" % (len(character_manager.get_unlocked()),
                          len(character_manager.all_characters()))
        return [("Chi's", chis, "chis"), ("Items", None, "items"),
                ("Trade", None, "trade"), ("Stamps", None, "stamps")]

    def activate(self, mgr) -> None:
        key = self.menu.key
        if key == "chis":
            mgr.push(ChiListScreen())
        elif key == "trade":
            from screens.trade import TradeScreen
            mgr.push(TradeScreen())
        elif key == "stamps":
            from screens.stamps import StampsMenuScreen
            mgr.push(StampsMenuScreen())
        else:
            mgr.push(ComingSoonScreen(self.menu.item[0].upper()))

    def back(self, mgr) -> None:
        # A different Chi was made active: rebuild the pet screen so it shows
        # the new character rather than popping back to the old one.
        import character_manager
        if character_manager.get_active().id != self._entry_char:
            from screens.conagotchi import ConagotchiScreen
            mgr.switch_to(ConagotchiScreen())
        else:
            mgr.pop()


class ChiListScreen(ListScreen):
    """Collected characters, the active one marked ACTIVE (green)."""

    title = "CHI'S"

    def __init__(self) -> None:
        super().__init__()
        self._chars = ()
        self._active = ""

    def rows(self):
        import character_manager
        first = not self._chars
        self._chars = tuple(character_manager.get_unlocked())
        self._active = character_manager.get_active().id
        rows = [(c.name, "ACTIVE" if c.id == self._active else None, c.id)
                for c in self._chars]
        if len(self._chars) < len(character_manager.all_characters()):
            rows.append((COLLECT_HINT, None, ""))
        if first:                       # open on the active Chi
            for i, c in enumerate(self._chars):
                if c.id == self._active:
                    self.menu.sel = i
        return rows

    def confirm(self):
        key = self.menu.key
        return "USE" if key and key != self._active else None

    def activate(self, mgr) -> None:
        key = self.menu.key
        if not key or key == self._active:
            return
        import character_manager
        if character_manager.set_active(key) is not None:
            self.redraw(mgr)


class ComingSoonScreen(Screen):
    """Placeholder for a Collection section that is not built yet."""

    def __init__(self, title: str) -> None:
        self._title_text = title
        self._title = ui.Marquee()

    async def enter(self, display, leds, mgr) -> None:
        ui.screen(display, self._title_text, marquee=self._title)
        ui.status(display, "Coming soon!", 112, "accent")
        ui.controls(display)

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn in (BOOT, SELECT, START):
            mgr.pop()
