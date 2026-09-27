"""Lab console for any campaign, built from the badge's shared UI helpers.

Presentation is standardised across campaigns: the lab's title fills the title
bar, the root menu carries its metadata in the right-hand value column, and every
list is a shared `menu.Menu` (selection, scrolling rows), so labs look and behave
like the rest of the badge instead of a hand-placed layout of their own.

Root menu values are the metadata: difficulty, how much evidence has been read,
and how many hints have been spent. The parameter list shows each field's current
value inline, so the state of a request is visible without opening anything.
"""
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen

class LabScreen(Screen):
    """Drives one lab. `challenge_cls` supplies the id, character and prereq."""

    def __init__(self, challenge_cls):
        self._cls = challenge_cls
        self._lab = None
        self._view = "root"
        from menu import Menu
        self._menu = Menu()           # the shared list behaviour
        self._scroll = 0
        self._lines = []
        self._return = "root"
        self._return_sel = 0
        self._field = None
        self._choice = 0
        self._locked = False
        self._title = getattr(challenge_cls, "name", "LAB")
        self._marquee = ui.Marquee()

    # The list's selection and window live in the shared Menu.
    @property
    def _sel(self):
        return self._menu.sel

    @_sel.setter
    def _sel(self, value):
        self._menu.sel = value

    @property
    def _top(self):
        return self._menu.top

    @_top.setter
    def _top(self, value):
        self._menu.top = value

    def _list_rows(self):
        return [(label, value, key) for key, label, value in self._items()]

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr):
        import character_manager
        import challenge_manager
        message = ""
        self._locked = not character_manager.is_unlocked(self._cls.character)
        if self._locked:
            message = "Collect %s to access these labs." % self._character_name()
        elif (self._cls.prerequisite
              and not challenge_manager.is_completed(self._cls.prerequisite)):
            self._locked = True
            message = "Complete the previous lab first."
        if self._locked:
            self._text(message)
        else:
            from lab_engine import LabSession
            self._lab = LabSession(self._cls.id)
            self._title = self._lab.spec["title"] or self._title
            if self._lab.solved:
                self._finish(mgr)
            else:
                self._view = "root"
        self._draw(display)

    def _character_name(self):
        try:
            import character_manager
            char = character_manager.find(self._cls.character)
            if char is not None:
                return char.name
        except Exception:
            pass
        return "this character"

    async def update(self, display, leds, mgr) -> None:
        self._marquee.tick(display)
        if not self._locked and self._view in ("root", "evidence", "fields", "actions"):
            self._menu.tick(display)      # scroll a too-long selected row

    def _heading(self):
        return self._field[1] if self._view == "field" else self._title

    # ── menu contents ────────────────────────────────────────────────────────

    def _items(self):
        """Rows as (key, label, value); value is None when there is nothing to show."""
        lab = self._lab
        if self._view == "root":
            spec = lab.spec
            seen = len([k for k, _, _ in spec["evidence"] if k in lab.state["seen"]])
            hints = spec["hints"]
            return [
                ("objective", "Objective", spec["difficulty"]),
                ("evidence", "Evidence", "%d/%d" % (seen, len(spec["evidence"]))),
                ("fields", "Parameters", "%d" % len(spec["fields"])),
                ("actions", "Actions", "%d" % len(spec["actions"])),
                ("notebook", "Notebook", "%d" % seen),
                ("hint", "Hint", "%d/%d" % (min(lab.state["hints"], len(hints)),
                                            len(hints))),
            ]
        if self._view == "evidence":
            return [(key, name, "read" if key in lab.state["seen"] else "new")
                    for key, name, _ in lab.spec["evidence"]]
        if self._view == "fields":
            return [(key, name, lab.state["values"][key])
                    for key, name, _ in lab.spec["fields"]]
        if self._view == "actions":
            return [(key, name, None) for key, name in lab.spec["actions"]]
        return []

    def _text(self, text):
        self._marquee.reset()
        self._return, self._return_sel = self._view, self._sel
        self._view = "text"
        self._lines = ui.wrap_text(text)
        self._scroll = 0

    def _finish(self, mgr):
        import challenge_manager
        if not challenge_manager.is_completed(self._cls.id):
            for screen in reversed(mgr._stack):
                pet = getattr(screen, "_pet", None)
                if pet is not None and self._cls.is_met():
                    self._cls().on_complete(pet)
                    challenge_manager.mark_complete(self._cls.id)
                    break
        flag = challenge_manager.get_completed_flag(self._cls.id)
        if challenge_manager.is_completed(self._cls.id):
            message = "COMPLETE\n\n" + (flag or "Flag not configured.")
        else:
            message = "SOLVED\n\nReturn to your pet to record completion."
        self._text(message)
        self._view = "complete"

    # ── input ────────────────────────────────────────────────────────────────

    def handle_button(self, btn, mgr):
        if self._locked:
            if btn in (SELECT, BOOT, START):
                mgr.pop()
            return
        if self._view in ("text", "complete"):
            self._handle_text(btn, mgr)
        elif self._view == "field":
            self._handle_field(btn)
        elif btn in (SELECT, BOOT):
            if self._view == "root":
                mgr.pop()
                return
            self._view, self._sel, self._top = "root", 0, 0
        elif btn in (LEFT, RIGHT):
            # Only the rows that changed are repainted, like every list.
            self._menu.set_rows(self._list_rows())
            self._menu.step(mgr._display, 1 if btn == RIGHT else -1)
            return
        elif btn == START:
            self._activate(mgr)
        self._draw(mgr._display)

    def _handle_text(self, btn, mgr):
        limit = ui.scroll_max(len(self._lines), ui.PAGE_ROWS)
        if btn in (LEFT, RIGHT):
            step = 1 if btn == RIGHT else -1
            self._scroll = max(0, min(limit, self._scroll + step))
        elif btn in (SELECT, BOOT, START):
            if self._view == "complete":
                mgr.pop()
                return
            self._view, self._sel = self._return, self._return_sel
            self._menu.set_rows(self._list_rows())

    def _handle_field(self, btn):
        options = self._field[2]
        if btn in (LEFT, RIGHT):
            step = 1 if btn == RIGHT else -1
            self._choice = (self._choice + step) % len(options)
        elif btn == START:
            try:
                self._lab.set_value(self._field[0], options[self._choice])
                self._view = "fields"
            except OSError:
                self._text("Save failed. Your previous choice is unchanged. "
                           "Retry after checking storage.")
        elif btn in (SELECT, BOOT):
            self._view = "fields"

    def _activate(self, mgr):
        key = self._items()[self._sel][0]
        try:
            if self._view == "root":
                if key == "objective":
                    self._text(self._objective_text())
                elif key == "notebook":
                    self._text(self._lab.notebook())
                elif key == "hint":
                    self._text(self._lab.hint())
                else:
                    self._view, self._sel, self._top = key, 0, 0
            elif self._view == "evidence":
                self._text(self._lab.inspect(key))
            elif self._view == "fields":
                self._field = next(f for f in self._lab.spec["fields"]
                                   if f[0] == key)
                self._choice = self._field[2].index(
                    self._lab.state["values"][key])
                self._view = "field"
            elif self._view == "actions":
                result = self._lab.act(key)
                if self._lab.solved:
                    self._finish(mgr)
                else:
                    self._text(result)
        except OSError:
            self._text("Save failed. Progress was not confirmed. "
                       "Retry after checking storage.")

    def _objective_text(self):
        """Objective plus the standing safety note, so no lab repeats it."""
        spec = self._lab.spec
        return "%s\n\n%s target.\nSimulated: no real systems." % (
            spec["objective"], spec["difficulty"])

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw(self, display):
        """Everything is drawn by the shared ui widgets, so this screen matches
        the rest of the badge. Bounds are covered by
        test_labs.test_all_lab_views_fit_round_screen_and_long_tokens_are_exact."""
        ui.screen(display, self._heading(), marquee=self._marquee)

        if self._locked or self._view in ("text", "complete"):
            ui.text_page(display, self._lines, self._scroll)
            ui.controls(display)
            return

        if self._view == "field":
            options = self._field[2]
            ui.value_picker(display, options[self._choice],
                            detail="%d/%d" % (self._choice + 1, len(options)))
            ui.controls(display, "APPLY")
            return

        self._menu.set_rows(self._list_rows())
        self._menu.draw(display)
        ui.controls(display, "RUN" if self._view == "actions" else "OPEN")
