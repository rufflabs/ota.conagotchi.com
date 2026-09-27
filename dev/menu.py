"""Lists: the one implementation every list on the badge uses.

`ui` draws; this module owns how a list *behaves*: which row is selected, the
scroll window, stepping over section headings, a scrolling selected row, the
message line and the Back/confirm controls. Every list screen gets every list
feature from here, so Settings, Collection, Challenges and the rest cannot
drift apart again.

    Menu        one list's state and behaviour. A screen with several views
                (e.g. Trade's pick view) keeps a Menu and routes buttons to it.
    ListScreen  a complete list screen built on Menu. Subclass it and supply
                rows(); override activate() for START.

Rows are what ui.list_view draws: "label", (label, value), or ui.Header(label)
for a non-selectable heading. Extra tuple fields are ignored by the drawing,
so (label, value, key) rows can carry what START should act on.
"""
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen


class Menu:
    """Selection, scroll window and row scrolling for one list. The window
    moves a page at a time (ui.page_top), so most moves repaint two rows and
    only crossing to another page repaints the whole list area."""

    def __init__(self, rows=(), value_fg=None) -> None:
        self.rows = []
        self.sel = 0
        self.top = 0
        self.value_fg = value_fg
        self.marquee = ui.Marquee()
        self.set_rows(rows)

    def set_rows(self, rows, select=None) -> None:
        """Replace the rows, keeping the selection where it can. `select` is
        a row index to select instead."""
        self.rows = list(rows)
        if select is not None:
            self.sel = select
        count = len(self.rows)
        if not count:
            self.sel = self.top = 0
            return
        self.sel = max(0, min(self.sel, count - 1))
        if not ui.is_selectable(self.rows[self.sel]):
            self.sel = self._step(self.sel, 1)
        self.top = ui.page_top(self.sel, count)

    def _step(self, index, delta):
        count = len(self.rows)
        for _ in range(count):
            index = (index + delta) % count
            if ui.is_selectable(self.rows[index]):
                return index
        return self.sel

    def move(self, delta) -> bool:
        """Move the selection, skipping headings. Returns True if it moved."""
        if not self.rows:
            return False
        old = self.sel
        self.sel = self._step(self.sel, delta)
        self.top = ui.page_top(self.sel, len(self.rows))
        return self.sel != old

    @property
    def item(self):
        """The selected row, or None for an empty list."""
        return self.rows[self.sel] if self.rows else None

    @property
    def key(self):
        """The selected row's third field (its key), else its label."""
        row = self.item
        if isinstance(row, tuple):
            return row[2] if len(row) > 2 else row[0]
        return row

    def draw(self, display) -> None:
        ui.list_view(display, self.rows, self.sel, self.top,
                     value_fg=self.value_fg, marquee=self.marquee)

    def step(self, display, delta) -> bool:
        """Move and repaint only what changed (two rows, or the rows area and
        scrollbar when the window scrolls). Returns True if it moved."""
        old_sel, old_top = self.sel, self.top
        if not self.move(delta):
            return False
        ui.repaint_list(display, self.rows, self.sel, self.top, old_sel, old_top,
                        self.value_fg, self.marquee)
        return True

    def tick(self, display) -> bool:
        """Call from update(): scrolls a too-long selected label in place."""
        return ui.tick_list(display, self.rows, self.sel, self.top,
                            self.marquee, self.value_fg)


class ListScreen(Screen):
    """A titled list with a message line and Back/confirm controls.

    Subclasses set `title` and implement rows(); optionally confirm(),
    activate(mgr) for START, back(mgr) for SELECT/BOOT, and empty (the line
    shown when there are no rows). `self.message` is shown above the controls
    and cleared on every move. Rows are rebuilt on enter/resume and by
    reload(), never per update tick (building them may read save files).
    """

    title = ""
    empty = "NOTHING HERE"
    value_fg = None
    message_kind = "accent"
    accepts_disabled_buttons = True

    def __init__(self) -> None:
        self.menu = Menu(value_fg=self.value_fg)
        self.message = ""
        self._title_marquee = ui.Marquee()

    # ── subclass hooks ───────────────────────────────────────────────────────

    def rows(self):
        return []

    def confirm(self):
        """The verb shown for START on the selected row (None hides it)."""
        return "OPEN"

    def activate(self, mgr) -> None:
        pass

    def back(self, mgr) -> None:
        mgr.pop()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        self.reload()
        self.draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self.reload()
        self.draw(display)

    async def update(self, display, leds, mgr) -> None:
        self._title_marquee.tick(display)
        self.menu.tick(display)

    def reload(self) -> None:
        self.menu.set_rows(self.rows())

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self.back(mgr)
        elif btn == LEFT or btn == RIGHT:
            display = mgr._display
            verb = self.confirm() if self.menu.rows else None
            if self.menu.step(display, 1 if btn == RIGHT else -1):
                if self.message:
                    self.message = ""
                    ui.status_row(display, "", ui.MESSAGE_Y)
                new_verb = self.confirm()
                if new_verb != verb:
                    ui.controls(display, new_verb)
        elif btn == START and self.menu.rows:
            self.activate(mgr)

    def redraw(self, mgr) -> None:
        """Rebuild the rows and repaint (after START changed something)."""
        self.reload()
        self.draw(mgr._display)

    def draw(self, display) -> None:
        ui.screen(display, self.title, marquee=self._title_marquee)
        if self.menu.rows:
            self.menu.draw(display)
        else:
            ui.status(display, self.empty, 104, "muted")
        ui.message(display, self.message, self.message_kind)
        ui.controls(display, self.confirm() if self.menu.rows else None)
