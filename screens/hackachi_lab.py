"""Four-button lab console, using the badge's existing UI and screen stack."""
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen


def _wrap(text):
    # Evidence paths and flag tokens must not run into the circular bezel.
    lines = []
    for paragraph in text.split("\n"):
        for line in ui.wrap(paragraph, 20):
            lines.extend(line[i:i + 20] for i in range(0, len(line), 20))
        if not paragraph:
            lines.append("")
    return lines or [""]


class HackachiLabScreen(Screen):
    def __init__(self, challenge_cls):
        self._cls = challenge_cls
        self._lab = None
        self._view = "root"
        self._sel = 0
        self._scroll = 0
        self._lines = []
        self._return = "root"
        self._return_sel = 0
        self._field = None
        self._choice = 0
        self._locked = False

    async def enter(self, display, leds, mgr):
        import character_manager
        import challenge_manager
        self._locked = not character_manager.is_unlocked(self._cls.character)
        if self._locked:
            message = "Collect Hackachi to access these labs."
        elif (self._cls.prerequisite
              and not challenge_manager.is_completed(self._cls.prerequisite)):
            self._locked = True
            message = "Complete the previous Hackachi lab first."
        if self._locked:
            self._text(message)
        else:
            from hackachi_lab import LabSession
            self._lab = LabSession(self._cls.id)
            if self._lab.state["solved"]:
                self._finish(mgr)
            else:
                self._view = "root"
        self._draw(display)

    def _items(self):
        if self._view == "root":
            return [("brief", "Briefing"), ("evidence", "Inspect target"),
                    ("fields", "Build request"), ("actions", "Run action"),
                    ("notebook", "Evidence notebook"), ("hint", "Hint")]
        if self._view == "evidence":
            return [(key, name) for key, name, _ in self._lab.spec["evidence"]]
        if self._view == "fields":
            return [(key, name) for key, name, _ in self._lab.spec["fields"]]
        if self._view == "actions":
            return self._lab.spec["actions"]
        return []

    def _text(self, text):
        self._return, self._return_sel = self._view, self._sel
        self._view = "text"
        self._lines = _wrap(text)
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
            message = "LAB SOLVED\n\nReturn to your pet to record completion."
        self._text(message)
        self._view = "complete"

    def handle_button(self, btn, mgr):
        if self._locked:
            if btn in (SELECT, BOOT, START):
                mgr.pop()
            return
        if self._view in ("text", "complete"):
            limit = max(0, len(self._lines) - 5)
            if btn in (LEFT, RIGHT):
                self._scroll = max(0, min(limit, self._scroll + (1 if btn == RIGHT else -1)))
            elif btn in (SELECT, BOOT, START):
                if self._view == "complete":
                    mgr.pop()
                    return
                self._view, self._sel = self._return, self._return_sel
        elif self._view == "field":
            options = self._field[2]
            if btn in (LEFT, RIGHT):
                self._choice = (self._choice + (1 if btn == RIGHT else -1)) % len(options)
            elif btn == START:
                try:
                    self._lab.set_value(self._field[0], options[self._choice])
                    self._view = "fields"
                except OSError:
                    self._text("Save failed. Your previous choice is unchanged. Retry after checking storage.")
            elif btn in (SELECT, BOOT):
                self._view = "fields"
        elif btn in (SELECT, BOOT):
            if self._view == "root":
                mgr.pop()
                return
            self._view, self._sel = "root", 0
        elif btn in (LEFT, RIGHT):
            self._sel = (self._sel + (1 if btn == RIGHT else -1)) % len(self._items())
        elif btn == START:
            key = self._items()[self._sel][0]
            try:
                if self._view == "root":
                    if key == "brief":
                        self._text(self._lab.spec["brief"])
                    elif key == "notebook":
                        self._text(self._lab.notebook())
                    elif key == "hint":
                        self._text(self._lab.hint())
                    else:
                        self._view, self._sel = key, 0
                elif self._view == "evidence":
                    self._text(self._lab.inspect(key))
                elif self._view == "fields":
                    self._field = next(f for f in self._lab.spec["fields"] if f[0] == key)
                    self._choice = self._field[2].index(self._lab.state["values"][key])
                    self._view = "field"
                elif self._view == "actions":
                    result = self._lab.act(key)
                    if self._lab.state["solved"]:
                        self._finish(mgr)
                    else:
                        self._text(result)
            except OSError:
                self._text("Save failed. Progress was not confirmed. Retry after checking storage.")
        self._draw(mgr._display)

    def _draw(self, display):
        ui.clear(display)
        ui.status(display, self._cls.name[:20], 40, "accent")
        if self._view in ("text", "complete"):
            ui.text_view(display, self._lines, self._scroll, 72, 5, line_h=20)
            total = max(1, len(self._lines) - 4)
            ui.status(display, "%d/%d" % (self._scroll + 1, total), 180, "muted")
            footer = "BACK"
        elif self._view == "field":
            ui.status(display, self._field[1][:20], 84, "muted")
            value = self._field[2][self._choice]
            ui.status(display, value, 112, "text")
            ui.status(display, "%d/%d" % (self._choice + 1, len(self._field[2])), 160, "muted")
            footer = "BACK    APPLY"
        else:
            items = self._items()
            top = max(0, self._sel - 3)
            for row, (_, name) in enumerate(items[top:top + 4]):
                selected = top + row == self._sel
                ui.status(display, (("> " if selected else "  ") + name)[:22],
                          76 + row * 24, "accent" if selected else "text")
            ui.status(display, "%d/%d" % (self._sel + 1, len(items)), 180, "muted")
            footer = "BACK    " + ("RUN" if self._view == "actions" else "OPEN")
        ui.status(display, footer, 204, "muted")
