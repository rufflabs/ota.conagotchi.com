"""Shared on-screen text entry, pushed by any screen that needs a typed string.

    from screens.text_input import TextInputScreen
    mgr.push(TextInputScreen("EDIT SSID", current, on_done=save_fn))

`on_done(value)` is called when the user confirms - the OK key, or BOOT as a
shortcut - then the screen pops itself. SELECT turns the page (grid) or cycles
case (T9); LEFT/RIGHT move between keys; START types the selected key. The CLR
key empties the field.

The layout follows Settings -> Keyboard: a T9 phone keypad (the default) or
the classic grid (see keyboards.py for the editing rules). Chrome comes from `ui` and colours
from the theme, and every key is placed by key_rect() so the bounds test can
prove the whole keyboard sits inside the round bezel.
"""
import time

import keyboards
import theme
import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen

VALUE_Y = 42   # the typed text, just below the title panel

# (columns, key width, key height, gap, first row y) per keyboard. Sized so the
# outer key corners clear the round glass: see tools/test_text_input.py.
_GEOMETRY = {
    keyboards.KEYBOARD_GRID: (6, 28, 22, 3, 58),
    keyboards.KEYBOARD_T9:   (3, 58, 23, 3, 56),
}
_T9_GRID_KEYS = 12   # the phone pad; CLR and OK share a wide row beneath it


def key_rect(kind, idx):
    """(x, y, w, h) of key `idx` on keyboard `kind`."""
    cols, w, h, gap, y0 = _GEOMETRY[kind]
    span = cols * w + (cols - 1) * gap
    x0 = (240 - span) // 2
    if kind == keyboards.KEYBOARD_T9 and idx >= _T9_GRID_KEYS:
        # Two half-width keys spanning the pad, under the bottom row.
        # The second takes the remainder, so the row ends flush with the pad.
        half = (span - gap) // 2
        col = idx - _T9_GRID_KEYS
        width = half if col == 0 else span - half - gap
        return (x0 + col * (half + gap), y0 + (_T9_GRID_KEYS // cols) * (h + gap),
                width, h)
    row, col = divmod(idx, cols)
    return x0 + col * (w + gap), y0 + row * (h + gap), w, h


def shown_value(value, secret, pending, width):
    """The value as drawn: masked if `secret` (except a T9 character still
    cycling, which has to be visible to be chosen), with a cursor, keeping the
    end in view once it no longer fits."""
    if secret:
        tail = value[-1:] if pending else ""
        value = "*" * (len(value) - len(tail)) + tail
    s = value + "_"
    if len(s) > width:
        s = "<" + s[-(width - 1):]
    return s


def _mode_hint(editor):
    return ("T9 " if editor.kind == keyboards.KEYBOARD_T9 else "") + editor.mode


def _footer(editor):
    verb = "CASE" if editor.kind == keyboards.KEYBOARD_T9 else "PAGE"
    return "SEL:" + verb + " BOOT:OK"


class TextInputScreen(Screen):

    def __init__(self, title, value="", on_done=None, secret=False,
                 max_len=keyboards.MAX_LEN, kind=None):
        if kind is None:
            try:
                from settings_state import BadgeSettings
                kind = BadgeSettings().keyboard
            except Exception:
                kind = keyboards.KEYBOARD_T9
        self._title = title
        self._secret = secret
        self._on_done = on_done
        self.editor = keyboards.make(kind, value, max_len)

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def update(self, display, leds, mgr) -> None:
        if self.editor.expire(time.ticks_ms()):
            self._draw_value(display)

    # ── input ────────────────────────────────────────────────────────────────

    def handle_button(self, btn, mgr) -> None:
        display = mgr._display
        ed = self.editor
        if btn == BOOT or (btn == START and ed.action() == keyboards.OK):
            ed.commit()
            if self._on_done is not None:
                self._on_done(ed.value)
            mgr.pop()
        elif btn == LEFT or btn == RIGHT:
            old = ed.key
            was_pending = ed.pending
            ed.move(-1 if btn == LEFT else 1)
            self._draw_key(display, old)
            self._draw_key(display, ed.key)
            if was_pending:
                self._draw_value(display)
        elif btn == SELECT:
            ed.cycle_mode()
            self._draw(display)
        elif btn == START:
            if ed.tap(time.ticks_ms()):
                self._draw_value(display)

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw(self, display) -> None:
        ui.screen(display, self._title, hint=_mode_hint(self.editor))
        self._draw_value(display)
        for i in range(self.editor.key_count()):
            self._draw_key(display, i)
        ui.bottom_line(display, _footer(self.editor))

    def _draw_value(self, display) -> None:
        th = theme.get()
        width = ui.fit_chars(VALUE_Y)
        display.fill_rect(0, VALUE_Y - 4, 240, 16, th.bg)
        ui.center_text(display,
                       shown_value(self.editor.value, self._secret,
                                   self.editor.pending, width),
                       VALUE_Y, th.text, th.bg)

    def _draw_key(self, display, idx) -> None:
        th = theme.get()
        x, y, w, h = key_rect(self.editor.kind, idx)
        label = self.editor.label(idx)
        if idx == self.editor.key:
            fill, edge, fg = th.sel, th.accent, th.text
        else:
            fill, edge, fg = th.bg, th.muted, th.muted
        display.fill_rect(x, y, w, h, fill)
        display.rect(x, y, w, h, edge)
        ui.text(display, label, x + (w - len(label) * 8) // 2,
                y + (h - 8) // 2, fg, fill)
