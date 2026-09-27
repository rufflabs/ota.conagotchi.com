"""BLAT ("Bluetooth At"): chat with every badge in range.

BlatScreen is BLAT's home, a list: Chat (with the unread count), Name (what
others see; the badge id until one is set), People (who is in range, with
their Chi and level) and Filter (hide profanity in what others send, on by
default). It owns the BlatSession for as long as BLAT is open, so messages
keep arriving on every page, including while typing.

BlatChatScreen shows the conversation, newest at the bottom, each message as
"Ruff ADM3: Hi!" (the name is the short badge id when none is set). LEFT and
RIGHT scroll, START writes a message, SELECT / BOOT go back. The text follows
the menu text size.

Messages are kept in memory only, and nothing a badge receives is trusted:
see blat_session.
"""
import ui
from blat_session import MAX_TEXT, BlatSession, line, short_id
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from menu import ListScreen
from screen_manager import Screen
from screens.text_input import TextInputScreen

_TOP = ui.TITLE_PANEL_H + 6       # first chat line
_LINE_H = {1: 16, 2: 20}
_ROWS = {1: 8, 2: 6}              # chat lines that fit above the message line
_WIDTH = {1: 20, 2: 10}           # characters per chat line on the round glass


def _settings():
    from settings_state import BadgeSettings
    return BadgeSettings()


def _filter(settings):
    if not settings.blat_filter:
        return None
    import profanity
    return profanity.clean


def _profile(mgr):
    """(tag, level) of the active Chi, from the pet screen when it is open."""
    try:
        import character_manager
        tag = character_manager.get_active().tag
    except Exception:
        tag = "CHI"
    level = 0
    try:
        for screen in reversed(mgr._stack):
            pet = getattr(screen, "_pet", None)
            if pet is not None:
                level = pet.level
                break
    except Exception:
        pass
    return tag, level


class BlatScreen(ListScreen):

    title = "BLAT"

    def __init__(self) -> None:
        super().__init__()
        self.session = None
        self.settings = None

    async def enter(self, display, leds, mgr) -> None:
        if self.session is None:
            self.settings = _settings()
            tag, level = _profile(mgr)
            self.session = BlatSession(self.settings.display_name, tag, level,
                                       ble=self.settings.bluetooth_enabled,
                                       ir=self.settings.ir_enabled)
            if not self.session.start():
                self.message = "NO LINK"
            elif not self.settings.bluetooth_enabled:
                self.message = "BLUETOOTH IS OFF"
        await super().enter(display, leds, mgr)

    async def exit(self, display, leds, mgr) -> None:
        if self.session is not None:
            self.session.stop()

    async def update(self, display, leds, mgr) -> None:
        await super().update(display, leds, mgr)
        self.session.poll()
        rows = self.rows()
        if rows != self.menu.rows:            # unread or people count changed
            self.menu.set_rows(rows)
            self.menu.draw(display)

    def rows(self):
        s, st = self.session, self.settings
        if s is None:
            return []
        return [
            ("Chat", "%d NEW" % s.unread if s.unread else None, "chat"),
            ("Name", s.name, "name"),
            ("People", str(len(s.people())), "people"),
            ("Filter", "ON" if st.blat_filter else "OFF", "filter"),
        ]

    def confirm(self):
        return {"name": "EDIT", "filter": "TOGGLE"}.get(self.menu.key, "OPEN")

    def activate(self, mgr) -> None:
        key = self.menu.key
        s, st = self.session, self.settings
        if key == "chat":
            mgr.push(BlatChatScreen(self))
        elif key == "people":
            mgr.push(BlatPeopleScreen(s))
        elif key == "name":
            mgr.push(_PollingInput(s, "NAME", st.display_name or "",
                                   on_done=self._set_name, max_len=8))
        elif key == "filter":
            st.blat_filter = not st.blat_filter
            st.save()
            self.message = "FILTER " + ("ON" if st.blat_filter else "OFF")
            self.redraw(mgr)

    def _set_name(self, value) -> None:
        from settings_state import clean_name
        st, s = self.settings, self.session
        st.display_name = clean_name(value)
        st.save()
        s.set_profile(st.display_name, s.tag, s.level)
        self.message = "NAME " + s.name


class _PollingInput(TextInputScreen):
    """The shared keyboard, keeping BLAT listening while the player types."""

    def __init__(self, session, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._session = session

    async def update(self, display, leds, mgr) -> None:
        self._session.poll()
        await super().update(display, leds, mgr)


class BlatPeopleScreen(ListScreen):
    """Who is in range: name, and their Chi and level."""

    title = "PEOPLE"
    empty = "NO ONE IN RANGE"

    def __init__(self, session) -> None:
        super().__init__()
        self.session = session

    def rows(self):
        clean = _filter(_settings())
        rows = []
        for badge, name, tag, level in self.session.people():
            rows.append((clean(name) if clean else name, "%s%d" % (tag, level), badge))
        return rows

    def confirm(self):
        return None

    async def update(self, display, leds, mgr) -> None:
        await super().update(display, leds, mgr)
        self.session.poll()
        rows = self.rows()
        if rows != self.menu.rows:
            self.menu.set_rows(rows)
            self.draw(display)


class BlatChatScreen(Screen):

    def __init__(self, home) -> None:
        self.home = home
        self.session = home.session
        self._top = None             # first line shown; None = follow the newest
        self._shown = None           # (version, top, scale, filter) as drawn
        self._status = None

    async def enter(self, display, leds, mgr) -> None:
        self.session.unread = 0
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self.session.unread = 0
        self._shown = None
        self._draw(display)

    async def update(self, display, leds, mgr) -> None:
        s = self.session
        s.poll()
        if (s.version, self._top) != (self._shown or (None, None))[:2]:
            s.unread = 0
            self._draw_log(display)
        self._draw_status(display)

    def handle_button(self, btn, mgr) -> None:
        display = mgr._display
        if btn in (SELECT, BOOT):
            mgr.pop()
        elif btn in (LEFT, RIGHT):
            lines = self._lines()
            rows = _ROWS[ui.list_scale()]
            last = max(0, len(lines) - rows)
            top = last if self._top is None else self._top
            top = max(0, min(last, top + (rows - 1) * (1 if btn == RIGHT else -1)))
            self._top = None if top >= last else top
            self._draw_log(display)
        elif btn == START:
            wait = self.session.wait_ms()
            if wait:
                self._status = ("WAIT %dS" % ((wait + 999) // 1000), "warning")
                self._draw_status(display, force=True)
            else:
                mgr.push(_PollingInput(self.session, "MESSAGE", "",
                                       on_done=self._send, max_len=MAX_TEXT))

    def _send(self, text) -> None:
        if self.session.send(text):
            self._top = None                  # jump to the newest

    # ── drawing ──────────────────────────────────────────────────────────────

    def _lines(self):
        """Every message wrapped to the chat width, as (text, kind)."""
        scale = ui.list_scale()
        clean = _filter(self.home.settings)
        out = []
        for m in self.session.messages:
            kind = "accent" if m[4] else "text"
            for part in ui.wrap_text(line(m, None if m[4] else clean), _WIDTH[scale]):
                out.append((part, kind))
        return out

    def _draw(self, display) -> None:
        ui.screen(display, "BLAT")
        self._shown = None
        self._draw_log(display)
        self._draw_status(display, force=True)
        ui.controls(display, "WRITE")

    def _draw_log(self, display) -> None:
        scale = ui.list_scale()
        rows, line_h = _ROWS[scale], _LINE_H[scale]
        lines = self._lines()
        last = max(0, len(lines) - rows)
        top = last if self._top is None else min(self._top, last)
        ui.clear_band(display, ui.TITLE_PANEL_H, ui.MESSAGE_Y - ui.TITLE_PANEL_H - 2)
        if not lines:
            ui.scaled_lines(display, (("NO MESSAGES", "muted"), ("YET", "muted"), "",
                                      ("START TO", "muted"), ("WRITE ONE", "muted")))
        for i, (text, kind) in enumerate(lines[top:top + rows]):
            ui.status(display, text, _TOP + i * line_h, kind, scale)
        if len(lines) > rows:
            ui.scrollbar(display, top, rows, len(lines), _TOP, _TOP + rows * line_h)
        self._shown = (self.session.version, self._top)

    def _draw_status(self, display, force=False) -> None:
        s = self.session
        if self._status is not None and s.wait_ms():
            status = self._status             # the answer to the START just pressed
        elif s.sending:
            status = ("SENDING...", "muted")
        else:
            n = len(s.people())
            status = ("%d IN RANGE" % n if n else "NO ONE IN RANGE", "muted")
        if force or status != getattr(self, "_status_drawn", None):
            ui.status_row(display, status[0], ui.MESSAGE_Y, status[1])
            self._status_drawn = status
