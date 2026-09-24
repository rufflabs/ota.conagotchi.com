"""Snake game screen."""
import random
import time

import gc9a01py as gc9a01

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from image_utils import draw_text
from screen_manager import Screen


_BG = gc9a01.color565(8, 11, 14)
_PANEL = gc9a01.color565(20, 24, 30)
_GRID_BG = gc9a01.color565(12, 18, 22)
_GRID_LINE = gc9a01.color565(28, 38, 44)
_TEXT = gc9a01.WHITE
_MUTED = gc9a01.color565(145, 155, 170)
_FOOD = gc9a01.color565(235, 70, 82)
_BODY = gc9a01.color565(44, 138, 110)
_HEAD_EYE = gc9a01.color565(8, 11, 14)
_WARN = gc9a01.color565(215, 95, 80)


def _sync_theme() -> None:
    """Theme the neutral chrome only; the snake/food colours are game identity."""
    global _BG, _PANEL, _TEXT, _MUTED, _WARN
    import theme
    t = theme.get()
    _BG, _PANEL, _TEXT = t.bg, t.surface, t.text
    _MUTED, _WARN = t.muted, t.danger

_GRID = 13
_CELL = 12
_BOARD = _GRID * _CELL
_BOARD_X = (240 - _BOARD) // 2
_BOARD_Y = 42
_STEP_MS = 320
_SCORE_PANEL_Y = 203
_SCORE_Y = 207
_BEST_Y = 220

_STATE_INSTRUCTIONS = "instructions"
_STATE_RUNNING = "running"
_STATE_GAME_OVER = "game_over"

_UP = (0, -1)
_DOWN = (0, 1)
_LEFT = (-1, 0)
_RIGHT = (1, 0)
_BTN_UP = LEFT
_BTN_DOWN = SELECT
_BTN_LEFT = START
_BTN_RIGHT = RIGHT


class SnakeScreen(Screen):
    """A compact Snake game for the round badge display."""

    def __init__(self) -> None:
        self._state = _STATE_INSTRUCTIONS
        self._snake = []
        self._food = (0, 0)
        self._direction = _RIGHT
        self._next_direction = _RIGHT
        self._deadline = 0
        self._score = 0
        self._best = 0
        self._head_color = gc9a01.color565(90, 210, 160)

    async def enter(self, display, leds, mgr) -> None:
        _sync_theme()
        random.seed(time.ticks_ms())
        self._state = _STATE_INSTRUCTIONS
        self._draw_instructions(display)
        leds.rgb_off()

    async def exit(self, display, leds, mgr) -> None:
        leds.rgb_off()

    async def update(self, display, leds, mgr) -> None:
        if self._state != _STATE_RUNNING:
            return
        if time.ticks_diff(time.ticks_ms(), self._deadline) < 0:
            return
        self._tick(display, mgr)
        self._deadline = time.ticks_add(time.ticks_ms(), _STEP_MS)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT:
            mgr.pop()
            return

        if self._state == _STATE_INSTRUCTIONS:
            if btn == START:
                self._start(mgr._display)
            else:
                self._set_direction(btn)
            return

        if self._state == _STATE_GAME_OVER:
            if btn == START:
                self._start(mgr._display)
            return

        self._set_direction(btn)

    def _start(self, display) -> None:
        center = _GRID // 2
        self._snake = [(center, center), (center - 1, center), (center - 2, center)]
        self._direction = _RIGHT
        self._next_direction = _RIGHT
        self._score = 0
        self._spawn_food()
        self._state = _STATE_RUNNING
        self._deadline = time.ticks_add(time.ticks_ms(), _STEP_MS)
        self._draw_game(display)

    def _set_direction(self, btn: str) -> None:
        new_direction = None
        if btn == _BTN_UP:
            new_direction = _UP
        elif btn == _BTN_DOWN:
            new_direction = _DOWN
        elif btn == _BTN_LEFT:
            new_direction = _LEFT
        elif btn == _BTN_RIGHT:
            new_direction = _RIGHT
        if new_direction is None:
            return
        if not _opposite(new_direction, self._direction):
            self._next_direction = new_direction

    def _tick(self, display, mgr) -> None:
        self._direction = self._next_direction
        old_head = self._snake[0]
        head_x, head_y = self._snake[0]
        dx, dy = self._direction
        new_head = (head_x + dx, head_y + dy)
        ate = new_head == self._food

        if self._hits_wall(new_head) or self._hits_self(new_head, ate):
            self._game_over(display)
            return

        self._snake.insert(0, new_head)
        if ate:
            self._score += 1
            _award_happiness(mgr)
            self._best = max(self._best, self._score)
            self._spawn_food()
            self._draw_score(display)
        else:
            _clear_cell(display, self._snake.pop())
        _draw_cell(display, old_head, _BODY)
        _draw_head(display, new_head, self._head_color)
        if ate:
            _draw_cell(display, self._food, _FOOD)

    def _hits_wall(self, pos: tuple) -> bool:
        x, y = pos
        return x < 0 or x >= _GRID or y < 0 or y >= _GRID

    def _hits_self(self, pos: tuple, ate: bool) -> bool:
        limit = len(self._snake) if ate else len(self._snake) - 1
        for idx in range(limit):
            if self._snake[idx] == pos:
                return True
        return False

    def _spawn_food(self) -> None:
        while True:
            pos = (random.getrandbits(8) % _GRID, random.getrandbits(8) % _GRID)
            if pos not in self._snake:
                self._food = pos
                return

    def _game_over(self, display) -> None:
        self._state = _STATE_GAME_OVER
        self._draw_game(display)
        _center_text(display, "GAME OVER", 92, _WARN, _GRID_BG)
        _center_text(display, "START RETRY", 112, _TEXT, _GRID_BG)

    def _draw_instructions(self, display) -> None:
        display.fill(_BG)
        display.fill_rect(0, 0, 240, 36, _PANEL)
        display.fill_rect(0, 211, 240, 29, _PANEL)
        _center_text(display, "SNAKE", 14, _TEXT, _PANEL)
        _center_text(display, "EAT FOOD", 48, _TEXT, _BG)
        _center_text(display, "DONT HIT WALLS", 66, _MUTED, _BG)
        _center_text(display, "CONTROLS", 94, _TEXT, _BG)
        _center_text(display, "UP = L", 114, _MUTED, _BG)
        _center_text(display, "DOWN = SELECT", 132, _MUTED, _BG)
        _center_text(display, "LEFT = START", 150, _MUTED, _BG)
        _center_text(display, "RIGHT = R", 168, _MUTED, _BG)
        _center_text(display, "BOOT = EXIT", 190, _WARN, _BG)
        _center_text(display, "START TO PLAY", 219, _TEXT, _PANEL)

    def _draw_game(self, display) -> None:
        self._draw_static_game(display)
        _draw_cell(display, self._food, _FOOD)
        for idx in range(len(self._snake) - 1, 0, -1):
            _draw_cell(display, self._snake[idx], _BODY)
        if self._snake:
            _draw_head(display, self._snake[0], self._head_color)

    def _draw_static_game(self, display) -> None:
        display.fill(_BG)
        display.fill_rect(0, 0, 240, 36, _PANEL)
        _center_text(display, "SNAKE", 12, _TEXT, _PANEL)
        self._draw_score(display)

        display.fill_rect(_BOARD_X, _BOARD_Y, _BOARD, _BOARD, _GRID_BG)
        display.rect(_BOARD_X - 1, _BOARD_Y - 1, _BOARD + 2, _BOARD + 2, _MUTED)
        for idx in range(_GRID + 1):
            x = _BOARD_X + idx * _CELL
            y = _BOARD_Y + idx * _CELL
            display.vline(x, _BOARD_Y, _BOARD, _GRID_LINE)
            display.hline(_BOARD_X, y, _BOARD, _GRID_LINE)

    def _draw_score(self, display) -> None:
        # The round bezel narrows the footer; keep each complete label centered.
        display.fill_rect(0, _SCORE_PANEL_Y, 240, 240 - _SCORE_PANEL_Y, _PANEL)
        _center_text(display, "SCORE %d" % self._score, _SCORE_Y, _MUTED, _PANEL)
        _center_text(display, "BEST %d" % self._best, _BEST_Y, _MUTED, _PANEL)


def _draw_cell(display, pos: tuple, color: int) -> None:
    x, y = pos
    px = _BOARD_X + x * _CELL + 1
    py = _BOARD_Y + y * _CELL + 1
    display.fill_rect(px, py, _CELL - 1, _CELL - 1, color)


def _opposite(first: tuple, second: tuple) -> bool:
    return first[0] + second[0] == 0 and first[1] + second[1] == 0


def _clear_cell(display, pos: tuple) -> None:
    _draw_cell(display, pos, _GRID_BG)


def _draw_head(display, pos: tuple, color: int) -> None:
    _draw_cell(display, pos, color)
    x, y = pos
    px = _BOARD_X + x * _CELL + 1
    py = _BOARD_Y + y * _CELL + 1
    display.fill_rect(px + 3, py + 3, 2, 2, _HEAD_EYE)
    display.fill_rect(px + 7, py + 3, 2, 2, _HEAD_EYE)


def _center_text(display, text: str, y: int, fg: int, bg: int) -> None:
    x = (240 - len(text) * 8) // 2
    draw_text(display, text, x, y, fg, bg)


def _award_happiness(mgr) -> None:
    try:
        for screen in reversed(mgr._stack):
            pet = getattr(screen, "_pet", None)
            if pet is not None:
                pet.add_happiness(1)
                return
    except Exception:
        pass
