"""On-screen keyboard logic: the grid keyboard and T9 multi-tap.

Both editors share one small interface so the text input screen can drive
either without knowing which it has:

    value            the text so far
    key              selected key index;  key_count()
    mode             current page / case mode;  cycle_mode()
    label(i)         what to draw on key i
    move(delta)      LEFT / RIGHT
    tap(now)         START; returns True when `value` changed
    action()         DEL / CLR / OK for the selected special key, else None
    expire(now)      commit a cycling T9 character; True when state changed
    pending          True while the last character is still cycling (T9 only)

No drawing here, so both run on the host under unittest. The screen that draws
them is screens/text_input.py.
"""
import time

MAX_LEN = 32
DEL = "DEL"
SPC = "SPC"
CLR = "CLR"   # empty the field
OK = "OK"     # submit; the screen acts on it, the editor never types it
_ACTIONS = (DEL, CLR, OK)

KEYBOARD_GRID = "grid"
KEYBOARD_T9 = "t9"
KEYBOARDS = (KEYBOARD_GRID, KEYBOARD_T9)


def make(kind, value="", max_len=MAX_LEN):
    """The editor for keyboard `kind`, falling back to T9 (the default)."""
    if kind == KEYBOARD_GRID:
        return GridEditor(value, max_len)
    return T9Editor(value, max_len)


# ── Grid ─────────────────────────────────────────────────────────────────────

GRID_PAGES = ("ABC", "abc", "SYM")
_GRID_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789-_.@#!?$%&*+/=",
)


def _clear(editor):
    editor.commit()
    if not editor.value:
        return False
    editor.value = ""
    return True


class GridEditor:
    """One key per character, three pages. Space, delete, clear and OK end
    every page."""

    kind = KEYBOARD_GRID
    pending = False

    def __init__(self, value="", max_len=MAX_LEN):
        self.value = value
        self.max_len = max_len
        self.key = 0
        self._page = 0

    @property
    def mode(self):
        return GRID_PAGES[self._page]

    _TAIL = (SPC, DEL, CLR, OK)

    def key_count(self):
        return len(_GRID_CHARS[self._page]) + len(self._TAIL)

    def label(self, idx):
        chars = _GRID_CHARS[self._page]
        if idx < len(chars):
            return chars[idx]
        return self._TAIL[idx - len(chars)]

    def action(self):
        ch = self.label(self.key)
        return ch if ch in _ACTIONS else None

    def commit(self):
        pass

    def move(self, delta):
        self.key = (self.key + delta) % self.key_count()

    def cycle_mode(self):
        self._page = (self._page + 1) % len(GRID_PAGES)
        self.key = 0

    def expire(self, now=None):
        return False

    def tap(self, now=None):
        ch = self.label(self.key)
        if ch == OK:
            return False
        if ch == CLR:
            return _clear(self)
        if ch == DEL:
            if not self.value:
                return False
            self.value = self.value[:-1]
            return True
        if len(self.value) >= self.max_len:
            return False
        self.value += " " if ch == SPC else ch
        return True


# ── T9 ───────────────────────────────────────────────────────────────────────

TAP_TIMEOUT_MS = 1000

# Case modes, cycled by SELECT. "123" types the key's digit on a single tap.
T9_MODES = ("abc", "ABC", "123")

# (digit, characters cycled by repeated taps). Letters are stored lower case and
# upper-cased in ABC mode; the digit is always the last stop in the cycle, so a
# number is reachable without leaving letter mode.
T9_KEYS = (
    ("1", ".,?!-_@1"),
    ("2", "abc2"),
    ("3", "def3"),
    ("4", "ghi4"),
    ("5", "jkl5"),
    ("6", "mno6"),
    ("7", "pqrs7"),
    ("8", "tuv8"),
    ("9", "wxyz9"),
    ("*", "*#$%&+/=:;'\"()"),
    ("0", " 0"),
    ("#", DEL),
    ("", CLR),
    ("", OK),
)


def t9_chars(idx, mode):
    """The characters T9 key `idx` cycles through in `mode`."""
    digit, chars = T9_KEYS[idx]
    if chars in _ACTIONS:
        return chars
    if mode == "123":
        return digit
    if mode == "ABC":
        return chars.upper()
    return chars


class T9Editor:
    """Phone-keypad multi-tap. Tapping the same key again inside TAP_TIMEOUT_MS
    replaces the character just typed with the next one on that key; waiting, or
    moving to another key, commits it."""

    kind = KEYBOARD_T9

    def __init__(self, value="", max_len=MAX_LEN):
        self.value = value
        self.max_len = max_len
        self.key = 1          # start on "2 abc", the most-used key
        self.mode = T9_MODES[0]
        self.pending = False  # last char is still cycling on self._tap_key
        self._tap_key = -1
        self._tap_n = 0
        self._tap_ms = 0

    def key_count(self):
        return len(T9_KEYS)

    def label(self, idx):
        """Short on-key label: the digit plus a preview of what it types."""
        digit, chars = T9_KEYS[idx]
        if chars == DEL:
            return "# DEL"
        if chars in _ACTIONS:
            return chars
        if digit == "0":
            return "0 SPC"
        if digit == "*":
            return "* SYM"
        if self.mode == "123":
            return digit
        return digit + " " + t9_chars(idx, self.mode)[:-1][:4]

    def action(self):
        chars = t9_chars(self.key, self.mode)
        return chars if chars in _ACTIONS else None

    def commit(self):
        self.pending = False
        self._tap_key = -1

    def expire(self, now=None):
        if not self.pending:
            return False
        if now is None:
            now = time.ticks_ms()
        if time.ticks_diff(now, self._tap_ms) >= TAP_TIMEOUT_MS:
            self.commit()
            return True
        return False

    def move(self, delta):
        self.commit()
        self.key = (self.key + delta) % len(T9_KEYS)

    def cycle_mode(self):
        self.commit()
        self.mode = T9_MODES[(T9_MODES.index(self.mode) + 1) % len(T9_MODES)]

    def tap(self, now=None):
        if now is None:
            now = time.ticks_ms()
        chars = t9_chars(self.key, self.mode)
        if chars == OK:
            self.commit()
            return False
        if chars == CLR:
            return _clear(self)
        if chars == DEL:
            self.commit()
            if not self.value:
                return False
            self.value = self.value[:-1]
            return True

        again = (self.pending and self._tap_key == self.key
                 and time.ticks_diff(now, self._tap_ms) < TAP_TIMEOUT_MS)
        if again:
            self._tap_n = (self._tap_n + 1) % len(chars)
            self.value = self.value[:-1] + chars[self._tap_n]
            self._tap_ms = now
            return True

        self.commit()
        if len(self.value) >= self.max_len:
            return False
        self.value += chars[0]
        if len(chars) > 1:
            self.pending = True
            self._tap_key = self.key
            self._tap_n = 0
            self._tap_ms = now
        return True
