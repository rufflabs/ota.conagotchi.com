"""Collection: the bag button's menu (it replaced the OzConBase screen).

    COLLECTION
      Chi's    collected characters; START makes one active
      Items    coming soon
      Trade    choose a Chi and trade it (screens/trade.py)
      Stamps   coming soon

Built entirely from the shared ui widgets. Making a Chi active does not leave
the list; the pet screen underneath is rebuilt when Collection is closed, so it
shows the new character.
"""
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen

# Last row of the Chi list while any character is still locked.
COLLECT_HINT = "Trade Chi's with others to collect them all!"

_MENU = (
    ("Chi's", "chis"),
    ("Items", "items"),
    ("Trade", "trade"),
    ("Stamps", "stamps"),
)


class _ListScreen(Screen):
    """A titled list with BACK/confirm controls; subclasses supply the rows.

    Rows are built by _items() only on enter/resume/_reload, never per update
    tick, because building them can read save files."""

    title = ""

    def __init__(self) -> None:
        self._sel = 0
        self._top = 0
        self._rows = ()
        self._title = ui.Marquee()
        self._row = ui.Marquee()

    def _reload(self) -> None:
        self._rows = self._items()
        if self._rows:
            self._sel = min(self._sel, len(self._rows) - 1)
            self._top = ui.clamp_scroll(self._sel, self._top, len(self._rows))

    def _items(self):
        return ()

    def _confirm(self):
        return "OPEN"

    async def enter(self, display, leds, mgr) -> None:
        self._reload()
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._reload()
        self._draw(display)

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)
        ui.tick_list(display, self._rows, self._sel, self._top, self._row)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._back(mgr)
        elif btn == LEFT or btn == RIGHT:
            count = len(self._rows)
            if count:
                self._sel = (self._sel + (1 if btn == RIGHT else -1)) % count
                self._top = ui.clamp_scroll(self._sel, self._top, count)
                self._draw(mgr._display)
        elif btn == START:
            self._activate(mgr)

    def _back(self, mgr) -> None:
        mgr.pop()

    def _activate(self, mgr) -> None:
        pass

    def _draw(self, display) -> None:
        ui.screen(display, self.title, marquee=self._title)
        ui.list_view(display, self._rows, self._sel, self._top, marquee=self._row)
        ui.controls(display, self._confirm())


class CollectionScreen(_ListScreen):
    """Top-level Collection menu."""

    title = "COLLECTION"

    def __init__(self) -> None:
        super().__init__()
        import character_manager
        self._entry_char = character_manager.get_active().id

    def _items(self):
        import character_manager
        chis = "%d/%d" % (len(character_manager.get_unlocked()),
                          len(character_manager.all_characters()))
        return [(label, chis) if key == "chis" else label for label, key in _MENU]

    def _activate(self, mgr) -> None:
        key = _MENU[self._sel][1]
        if key == "chis":
            mgr.push(ChiListScreen())
        elif key == "trade":
            from screens.trade import TradeScreen
            mgr.push(TradeScreen())
        else:
            mgr.push(ComingSoonScreen(_MENU[self._sel][0].upper()))

    def _back(self, mgr) -> None:
        # A different Chi was made active: rebuild the pet screen so it shows
        # the new character rather than popping back to the old one.
        import character_manager
        if character_manager.get_active().id != self._entry_char:
            from screens.conagotchi import ConagotchiScreen
            mgr.switch_to(ConagotchiScreen())
        else:
            mgr.pop()


class ChiListScreen(_ListScreen):
    """Collected characters, the active one marked ACTIVE (green)."""

    title = "CHI'S"

    def __init__(self) -> None:
        super().__init__()
        self._refresh()
        for i, char in enumerate(self._chars):
            if char.id == self._active:
                self._sel = i
        self._top = ui.window_top(self._sel, len(self._chars) + 1)

    def _refresh(self) -> None:
        import character_manager
        self._chars = tuple(character_manager.get_unlocked())
        self._active = character_manager.get_active().id
        self._complete = len(self._chars) >= len(character_manager.all_characters())

    def _items(self):
        rows = [(c.name, "ACTIVE") if c.id == self._active else c.name
                for c in self._chars]
        if not self._complete:
            rows.append(COLLECT_HINT)
        return rows

    def _selected_char(self):
        return self._chars[self._sel] if self._sel < len(self._chars) else None

    def _confirm(self):
        char = self._selected_char()
        return "USE" if char is not None and char.id != self._active else None

    def _activate(self, mgr) -> None:
        char = self._selected_char()
        if char is None or char.id == self._active:
            return
        import character_manager
        if character_manager.set_active(char.id) is not None:
            self._refresh()
            self._reload()
            self._draw(mgr._display)


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
