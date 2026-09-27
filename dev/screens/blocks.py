"""Blocks: a falling-block line-clearing game.

Controls: LEFT / RIGHT move (hold to repeat), SELECT rotates, holding START
makes the piece fall fast, BOOT exits. Clearing lines scores points and every
ten lines raises the level, which makes pieces fall faster.

The rules live in BlocksGame, which knows nothing about the display, so they
can be tested on the host. BlocksScreen draws it: the 10x20 well in the
middle of the round display, the next piece on the left and the score on the
right. It repaints only the cells that change, except after a line clear.
"""
import random
import time

import gc9a01py as gc9a01
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen
from led_flash import LedFlash
import game_scores
import ui

GAME_ID = "blocks"   # game_scores key: best = highest score in one game

COLS = 10
ROWS = 20

# Pieces: (box size, cells in the spawn rotation). Rotation turns the cells
# clockwise inside their box.
_SHAPES = (
    (4, ((0, 1), (1, 1), (2, 1), (3, 1))),   # I
    (2, ((0, 0), (1, 0), (0, 1), (1, 1))),   # O
    (3, ((1, 0), (0, 1), (1, 1), (2, 1))),   # T
    (3, ((1, 0), (2, 0), (0, 1), (1, 1))),   # S
    (3, ((0, 0), (1, 0), (1, 1), (2, 1))),   # Z
    (3, ((0, 0), (0, 1), (1, 1), (2, 1))),   # J
    (3, ((2, 0), (0, 1), (1, 1), (2, 1))),   # L
)
# Sideways nudges tried, in order, when a rotation does not fit where it is.
_KICKS = (0, -1, 1, -2, 2)

_LINE_POINTS = (0, 40, 100, 300, 1200)   # per clear of 0-4 lines, times level+1
_LINES_PER_LEVEL = 10
_FALL_MS = 800           # level 0 gravity: one row per this many ms
_FALL_STEP_MS = 70       # each level falls this much faster
_MIN_FALL_MS = 90
_SOFT_MS = 45            # START held
_DAS_MS = 200            # LEFT/RIGHT held: first repeat after this long
_REPEAT_MS = 70          # then one move per this long
_FRAME_MS = 20
_CLEAR_FLASH = ((40, 40, 40), 160)   # (rgb, ms): white on a line clear
_TETRA_FLASH = ((0, 45, 55), 400)    # four lines at once: longer, in I blue


def _rotate(size, cells):
    return tuple((size - 1 - y, x) for x, y in cells)


def _rotations(size, cells):
    out = [cells]
    if size > 2:                       # the O piece does not turn
        for _ in range(3):
            out.append(_rotate(size, out[-1]))
    return tuple(out)


_ROTATIONS = tuple(_rotations(size, cells) for size, cells in _SHAPES)


def fall_ms(level):
    return max(_MIN_FALL_MS, _FALL_MS - level * _FALL_STEP_MS)


class BlocksGame:
    """The well, the falling piece, and the score. `rng(n)` returns 0..n-1."""

    def __init__(self, rng=None):
        self._rng = rng or (lambda n: random.getrandbits(8) % n)
        self.grid = [[0] * COLS for _ in range(ROWS)]   # 0 empty, else kind+1
        self.score = 0
        self.lines = 0
        self.level = 0
        self.over = False
        self._bag = []
        self.next_kind = self._draw_kind()
        self.kind = 0
        self.rot = 0
        self.x = 0
        self.y = 0
        self.spawn()

    # ── pieces ───────────────────────────────────────────────────────────────

    def _draw_kind(self):
        """Seven-piece bag: every piece once before any repeats."""
        if not self._bag:
            self._bag = list(range(len(_SHAPES)))
        return self._bag.pop(self._rng(len(self._bag)))

    def cells(self, kind=None, rot=None, x=None, y=None):
        """The falling piece's cells as (col, row) in the well."""
        kind = self.kind if kind is None else kind
        rot = self.rot if rot is None else rot
        x = self.x if x is None else x
        y = self.y if y is None else y
        return [(x + cx, y + cy) for cx, cy in _ROTATIONS[kind][rot]]

    def fits(self, cells):
        for col, row in cells:
            if col < 0 or col >= COLS or row >= ROWS:
                return False
            if row >= 0 and self.grid[row][col]:
                return False
        return True

    def spawn(self):
        """Bring in the next piece at the top. Sets `over` if it cannot fit."""
        self.kind = self.next_kind
        self.next_kind = self._draw_kind()
        self.rot = 0
        size = _SHAPES[self.kind][0]
        self.x = (COLS - size) // 2
        self.y = -1 if self.kind == 0 else 0     # the I piece sits in row 1
        if not self.fits(self.cells()):
            self.over = True

    # ── moves (each returns True when the piece moved) ───────────────────────

    def move(self, dx):
        if self.over or not self.fits(self.cells(x=self.x + dx)):
            return False
        self.x += dx
        return True

    def rotate(self):
        turns = len(_ROTATIONS[self.kind])
        rot = (self.rot + 1) % turns
        if self.over or rot == self.rot:
            return False
        for dx in _KICKS:
            if self.fits(self.cells(rot=rot, x=self.x + dx)):
                self.rot, self.x = rot, self.x + dx
                return True
        return False

    def step(self, soft=False):
        """Drop one row. Returns None when the piece fell, otherwise the number
        of lines cleared by locking it (0-4). Soft drops score a point a row."""
        if self.over:
            return None
        if self.fits(self.cells(y=self.y + 1)):
            self.y += 1
            if soft:
                self.score += 1
            return None
        return self._lock()

    def _lock(self):
        for col, row in self.cells():
            if row < 0:                  # locked above the top: the well is full
                self.over = True
                return 0
            self.grid[row][col] = self.kind + 1
        full = [r for r in range(ROWS) if all(self.grid[r])]
        for r in full:
            del self.grid[r]
            self.grid.insert(0, [0] * COLS)
        if full:
            self.score += _LINE_POINTS[len(full)] * (self.level + 1)
            self.lines += len(full)
            self.level = self.lines // _LINES_PER_LEVEL
        self.spawn()
        return len(full)


# ── Screen ───────────────────────────────────────────────────────────────────

_CELL = 9                         # 8px block and a 1px gap
_WELL_X = (240 - COLS * _CELL) // 2
_WELL_Y = 30
_WELL_W = COLS * _CELL
_WELL_H = ROWS * _CELL

_LEFT_X = 44                      # centre of the left panel (next, level)
_RIGHT_X = 194                    # centre of the right panel (score, lines)
_NEXT_CELL = 7
_NEXT_Y = 98

_BG = gc9a01.color565(8, 11, 14)
_WELL_BG = gc9a01.color565(12, 16, 22)
_EDGE = gc9a01.color565(140, 150, 160)
_TEXT = gc9a01.WHITE
_MUTED = gc9a01.color565(140, 150, 160)
_WARN = gc9a01.color565(215, 95, 80)
# Piece colours are game identity, not themed.
_COLOURS = (
    gc9a01.color565(40, 200, 230),    # I
    gc9a01.color565(240, 210, 40),    # O
    gc9a01.color565(170, 80, 220),    # T
    gc9a01.color565(70, 200, 90),     # S
    gc9a01.color565(230, 60, 70),     # Z
    gc9a01.color565(50, 100, 230),    # J
    gc9a01.color565(240, 140, 40),    # L
)

_STATE_INTRO = "intro"
_STATE_RUNNING = "running"
_STATE_OVER = "over"
# After game over, buttons wait this long: SELECT rotates and START drops, so
# a press already on its way must not leave or restart.
_OVER_LOCK_MS = 600


def _sync_theme() -> None:
    """Theme the neutral chrome only; the piece colours are game identity."""
    global _BG, _TEXT, _MUTED, _WARN, _EDGE
    import theme
    t = theme.get()
    _BG, _TEXT, _MUTED, _WARN, _EDGE = t.bg, t.text, t.muted, t.danger, t.muted


class BlocksScreen(Screen):

    def __init__(self) -> None:
        self._state = _STATE_INTRO
        self._game = None
        self._best = 0
        self._fall_at = 0
        self._held = None          # LEFT or RIGHT while it auto-repeats
        self._repeat_at = 0
        self._shown = None         # side-panel values last drawn
        self._over_at = 0
        self._flash = LedFlash()
        self._leds = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def enter(self, display, leds, mgr) -> None:
        self._leds = leds
        _sync_theme()
        random.seed(time.ticks_ms())
        self._best = game_scores.get(GAME_ID, "best")
        self._state = _STATE_INTRO
        _draw_intro(display, self._best, game_scores.get(GAME_ID, "last", None))
        leds.rgb_off()

    async def exit(self, display, leds, mgr) -> None:
        if self._state == _STATE_RUNNING:     # leaving mid-game still counts
            game_scores.end_run(GAME_ID, self._game.score)
        leds.rgb_off()

    def next_update_ms(self) -> int:
        return _FRAME_MS

    async def update(self, display, leds, mgr) -> None:
        self._flash.tick(leds)
        if self._state != _STATE_RUNNING:
            return
        now = time.ticks_ms()
        buttons = getattr(mgr, "_buttons", None)
        if self._held is not None:
            if buttons is None or not buttons.pressed(self._held):
                self._held = None
            elif time.ticks_diff(now, self._repeat_at) >= 0:
                self._repeat_at = time.ticks_add(now, _REPEAT_MS)
                self._act(display, mgr, lambda g: g.move(-1 if self._held == LEFT else 1))
        if time.ticks_diff(now, self._fall_at) >= 0:
            soft = buttons is not None and buttons.pressed(START)
            self._fall(display, mgr, soft)

    # ── input ────────────────────────────────────────────────────────────────

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT:
            mgr.pop()
            return
        display = mgr._display
        if self._state == _STATE_OVER:
            if time.ticks_diff(time.ticks_ms(), self._over_at) < _OVER_LOCK_MS:
                return
            if btn == START:
                self._start(display)
            elif btn == SELECT:
                mgr.pop()
            return
        if self._state != _STATE_RUNNING:
            if btn == START:
                self._start(display)
            return
        if btn in (LEFT, RIGHT):
            self._held = btn
            self._repeat_at = time.ticks_add(time.ticks_ms(), _DAS_MS)
            self._act(display, mgr, lambda g: g.move(-1 if btn == LEFT else 1))
        elif btn == SELECT:
            self._act(display, mgr, lambda g: g.rotate())
        elif btn == START:
            self._fall(display, mgr, True)     # at once, then fast while held

    # ── play ─────────────────────────────────────────────────────────────────

    def _start(self, display) -> None:
        self._game = BlocksGame()
        self._state = _STATE_RUNNING
        self._held = None
        self._shown = None
        game_scores.count_play(GAME_ID)
        self._fall_at = time.ticks_add(time.ticks_ms(), fall_ms(0))
        self._draw_all(display)

    def _act(self, display, mgr, change) -> None:
        """Apply a move or rotation, repainting only the piece."""
        g = self._game
        before = g.cells()
        if change(g):
            _paint_piece(display, before, g.cells(), g.kind)

    def _fall(self, display, mgr, soft) -> None:
        g = self._game
        before = g.cells()
        placed = g.kind
        cleared = g.step(soft)
        interval = _SOFT_MS if soft else fall_ms(g.level)
        self._fall_at = time.ticks_add(time.ticks_ms(), interval)
        if cleared is None:                    # it fell one row
            _paint_piece(display, before, g.cells(), g.kind)
            if soft:
                self._draw_panels(display)
            return
        if g.over:
            self._game_over(display)
            return
        if cleared:
            if self._leds is not None:
                self._flash.start(self._leds, *(_TETRA_FLASH if cleared == 4
                                                 else _CLEAR_FLASH))
            _award_happiness(mgr)
            self._draw_well(display)
        else:
            _paint_cells(display, before, _COLOURS[placed])   # now part of the stack
        _paint_cells(display, g.cells(), _COLOURS[g.kind])
        self._draw_panels(display)

    def _game_over(self, display) -> None:
        self._state = _STATE_OVER
        self._over_at = time.ticks_ms()
        g = self._game
        game_scores.end_run(GAME_ID, g.score)
        self._best = max(self._best, g.score)
        self._draw_all(display, piece=False)
        y = _WELL_Y + _WELL_H // 2 - 24
        ui.center_text(display, "GAME OVER", y, _WARN, _WELL_BG)
        ui.center_text(display, "START", y + 18, _TEXT, _WELL_BG)
        ui.center_text(display, "RETRY", y + 28, _TEXT, _WELL_BG)
        ui.center_text(display, "SEL", y + 44, _TEXT, _WELL_BG)
        ui.center_text(display, "EXIT", y + 54, _TEXT, _WELL_BG)

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_all(self, display, piece=True) -> None:
        ui.clear(display)
        display.rect(_WELL_X - 1, _WELL_Y - 1, _WELL_W + 1, _WELL_H + 1, _EDGE)
        self._draw_well(display)
        if piece:
            _paint_cells(display, self._game.cells(), _COLOURS[self._game.kind])
        self._shown = None
        self._draw_panels(display)

    def _draw_well(self, display) -> None:
        grid = self._game.grid
        for row in range(ROWS):
            for col in range(COLS):
                v = grid[row][col]
                _cell(display, col, row, _COLOURS[v - 1] if v else _WELL_BG)

    def _draw_panels(self, display) -> None:
        """Next piece and level on the left, score and lines on the right.
        Each value is repainted only when it changed."""
        g = self._game
        shown = (g.next_kind, g.level, g.score, g.lines, self._best)
        old = self._shown or (None,) * len(shown)
        if self._shown is None:
            _label(display, "NEXT", _LEFT_X, 84)
            _label(display, "LEVEL", _LEFT_X, 138)
            _label(display, "SCORE", _RIGHT_X, 80)
            _label(display, "LINES", _RIGHT_X, 112)
            _label(display, "BEST", _RIGHT_X, 144)
        if shown[0] != old[0]:
            _draw_next(display, g.next_kind)
        if shown[1] != old[1]:
            _value(display, g.level, _LEFT_X, 150)
        if shown[2] != old[2]:
            _value(display, g.score, _RIGHT_X, 92)
        if shown[3] != old[3]:
            _value(display, g.lines, _RIGHT_X, 124)
        if shown[2] != old[2] or shown[4] != old[4]:
            _value(display, max(self._best, g.score), _RIGHT_X, 156)
        self._shown = shown


def _cell(display, col, row, colour) -> None:
    if row < 0:
        return                      # above the well: not drawn
    display.fill_rect(_WELL_X + col * _CELL, _WELL_Y + row * _CELL,
                      _CELL - 1, _CELL - 1, colour)


def _paint_cells(display, cells, colour) -> None:
    for col, row in cells:
        _cell(display, col, row, colour)


def _paint_piece(display, before, after, kind) -> None:
    """Erase the cells the piece left, then draw it where it is now."""
    for c in before:
        if c not in after:
            _cell(display, c[0], c[1], _WELL_BG)
    _paint_cells(display, after, _COLOURS[kind])


_PANEL_W = 48                        # widest side-panel value: 6 characters
_PANEL_MAX = 999999


def _label(display, text, cx, y) -> None:
    ui.text(display, text, cx - len(text) * 4, y, _MUTED, _BG)


def _value(display, n, cx, y) -> None:
    """A side-panel number, repainted in place; shown as at most 999999."""
    display.fill_rect(cx - _PANEL_W // 2, y, _PANEL_W, 8, _BG)
    text = str(min(n, _PANEL_MAX))
    ui.text(display, text, cx - len(text) * 4, y, _TEXT, _BG)


def _draw_next(display, kind) -> None:
    box = 4 * _NEXT_CELL
    x0 = _LEFT_X - box // 2
    display.fill_rect(x0, _NEXT_Y, box, box, _BG)
    size, cells = _SHAPES[kind]
    # Centre the piece's own width and height in the box.
    w = max(c[0] for c in cells) + 1
    h = max(c[1] for c in cells) - min(c[1] for c in cells) + 1
    top = min(c[1] for c in cells)
    ox = x0 + (box - w * _NEXT_CELL) // 2
    oy = _NEXT_Y + (box - h * _NEXT_CELL) // 2
    for cx, cy in cells:
        display.fill_rect(ox + cx * _NEXT_CELL, oy + (cy - top) * _NEXT_CELL,
                          _NEXT_CELL - 1, _NEXT_CELL - 1, _COLOURS[kind])


def _draw_intro(display, best, last) -> None:
    ui.game_intro(
        display, "BLOCKS",
        ("FILL ROWS TO CLEAR", "",
         ("L R = MOVE", "muted"), ("SEL = ROTATE", "muted"),
         ("HOLD ST = FAST", "muted"), "",
         ("BOOT = EXIT", "danger")),
        large_lines=("FILL ROWS", ("L R=MOVE", "muted"), ("SEL=TURN", "muted"),
                     ("ST=FAST", "muted"), ("BOOT=EXIT", "danger")),
        best=best, last=last)


def _award_happiness(mgr) -> None:
    try:
        for screen in reversed(mgr._stack):
            pet = getattr(screen, "_pet", None)
            if pet is not None:
                pet.add_happiness(1)
                return
    except Exception:
        pass
