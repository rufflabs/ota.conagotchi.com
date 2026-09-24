"""Simon-style memory game screen."""
import random
import time

import gc9a01py as gc9a01
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from image_utils import draw_text
from screen_manager import Screen


_BG = gc9a01.color565(9, 11, 16)
_PANEL = gc9a01.color565(20, 22, 28)
_TEXT = gc9a01.WHITE
_TEXT_DARK = gc9a01.color565(15, 15, 15)
_MUTED = gc9a01.color565(140, 150, 160)
_BACK_BG = gc9a01.color565(255, 205, 30)


def _sync_theme() -> None:
    """Theme the neutral chrome only; the Simon pad colours are game identity."""
    global _BG, _PANEL, _MUTED, _TEXT
    import theme
    t = theme.get()
    _BG, _PANEL, _MUTED, _TEXT = t.bg, t.surface, t.muted, t.text

_BAR_Y = 38
_BAR_H = 170
_BAR_W = 42
_BAR_X = (16, 68, 120, 172)

_WATCH_DELAY_MS = 700
_FLASH_MS = 430
_GAP_MS = 140
_HIT_MS = 170
_SPEED_STEP_MS = 18
_MIN_FLASH_MS = 180
_MIN_GAP_MS = 70
_MIN_HIT_MS = 90
_ROUND_CLEAR_MS = 650
_FAIL_MS = 1300

_LED_SCALE = 0.1

_STATE_READY = "ready"
_STATE_INSTRUCTIONS = "instructions"
_STATE_SHOW_ON = "show_on"
_STATE_SHOW_GAP = "show_gap"
_STATE_INPUT = "input"
_STATE_HIT = "hit"
_STATE_ROUND_CLEAR = "round_clear"
_STATE_FAIL = "fail"


# Button order follows the physical board order from left to right.
_PAD_BUTTONS = (LEFT, SELECT, START, RIGHT)
_PAD_LABELS = ("L", "SEL", "ST", "R")
_PAD_DIM = (
    gc9a01.color565(0, 110, 48),
    gc9a01.color565(190, 158, 0),
    gc9a01.color565(5, 76, 145),
    gc9a01.color565(150, 16, 24),
)
_PAD_LIT = (
    gc9a01.color565(0, 220, 92),
    gc9a01.color565(255, 232, 24),
    gc9a01.color565(28, 150, 255),
    gc9a01.color565(255, 54, 64),
)
_PAD_LED = ((0, 80, 18), (90, 70, 0), (0, 20, 90), (90, 0, 0))
_PAD_FG = (_TEXT, _TEXT_DARK, _TEXT, _TEXT)


class SimonScreen(Screen):
    """A classic watch-and-repeat colour pattern game."""

    def __init__(self) -> None:
        self._pattern = []
        self._best = 0
        self._state = _STATE_INSTRUCTIONS
        self._show_idx = 0
        self._input_idx = 0
        self._lit_idx = -1
        self._deadline = 0

    async def enter(self, display, leds, mgr) -> None:
        _sync_theme()
        random.seed(time.ticks_ms())
        self._pattern = []
        self._state = _STATE_INSTRUCTIONS
        self._show_idx = 0
        self._input_idx = 0
        self._lit_idx = -1
        self._deadline = 0
        _draw_instructions(display)
        leds.rgb_off()

    async def exit(self, display, leds, mgr) -> None:
        leds.rgb_off()

    async def update(self, display, leds, mgr) -> None:
        if not _due(self._deadline):
            return

        if self._state == _STATE_READY:
            self._start_next_round(display, leds)
        elif self._state == _STATE_SHOW_ON:
            _draw_bar(display, self._lit_idx, False)
            leds.rgb_off()
            self._show_idx += 1
            if self._show_idx >= len(self._pattern):
                self._state = _STATE_INPUT
                self._input_idx = 0
                _draw_status(display, "ROUND %d" % len(self._pattern), "REPEAT")
            else:
                self._state = _STATE_SHOW_GAP
                self._deadline = _after(_round_gap_ms(len(self._pattern)))
        elif self._state == _STATE_SHOW_GAP:
            self._flash_show_pad(display, leds)
        elif self._state == _STATE_HIT:
            _draw_bar(display, self._lit_idx, False)
            leds.rgb_off()
            if self._input_idx >= len(self._pattern):
                _award_happiness(mgr)
                self._best = max(self._best, len(self._pattern))
                self._state = _STATE_ROUND_CLEAR
                self._deadline = _after(_ROUND_CLEAR_MS)
                _draw_status(display, "ROUND %d" % len(self._pattern), "GOOD")
            else:
                self._state = _STATE_INPUT
                _draw_status(display, "ROUND %d" % len(self._pattern), "REPEAT")
        elif self._state == _STATE_ROUND_CLEAR:
            self._start_next_round(display, leds)
        elif self._state == _STATE_FAIL:
            self._pattern = []
            _draw_board(display)
            _draw_status(display, "SIMON", "WATCH")
            self._state = _STATE_READY
            self._deadline = _after(_WATCH_DELAY_MS)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT:
            mgr.pop()
            return

        if self._state == _STATE_INSTRUCTIONS:
            if btn == START:
                self._start_next_round(mgr._display, mgr._leds)
            return

        if self._state != _STATE_INPUT:
            return

        pad_idx = _pad_for_button(btn)
        if pad_idx < 0:
            return

        self._handle_player_pad(pad_idx, mgr._display, mgr._leds)

    def _start_next_round(self, display, leds) -> None:
        self._pattern.append(random.getrandbits(2))
        self._show_idx = 0
        self._input_idx = 0
        self._state = _STATE_SHOW_ON
        _draw_board(display)
        _draw_status(display, "ROUND %d" % len(self._pattern), "WATCH")
        self._flash_show_pad(display, leds)

    def _flash_show_pad(self, display, leds) -> None:
        self._lit_idx = self._pattern[self._show_idx]
        _draw_bar(display, self._lit_idx, True)
        _set_rgb(leds, self._lit_idx)
        self._state = _STATE_SHOW_ON
        self._deadline = _after(_round_flash_ms(len(self._pattern)))

    def _handle_player_pad(self, pad_idx: int, display, leds) -> None:
        expected = self._pattern[self._input_idx]
        if pad_idx != expected:
            self._fail(display, leds, pad_idx)
            return

        self._lit_idx = pad_idx
        self._input_idx += 1
        _draw_bar(display, pad_idx, True)
        _set_rgb(leds, pad_idx)
        self._state = _STATE_HIT
        self._deadline = _after(_round_hit_ms(len(self._pattern)))

    def _fail(self, display, leds, pad_idx: int) -> None:
        self._lit_idx = pad_idx
        _draw_bar(display, pad_idx, True)
        _draw_status(display, "MISS", "BEST %d" % self._best)
        display.line(78, 78, 162, 162, gc9a01.WHITE)
        display.line(162, 78, 78, 162, gc9a01.WHITE)
        _fill_rgb(leds, (90, 0, 0))
        leds.rgb_show()
        self._state = _STATE_FAIL
        self._deadline = _after(_FAIL_MS)


def _after(ms: int) -> int:
    return time.ticks_add(time.ticks_ms(), ms)


def _due(deadline: int) -> bool:
    return time.ticks_diff(time.ticks_ms(), deadline) >= 0


def _round_speed_bonus(round_num: int) -> int:
    return max(0, round_num - 1) * _SPEED_STEP_MS


def _round_flash_ms(round_num: int) -> int:
    return max(_MIN_FLASH_MS, _FLASH_MS - _round_speed_bonus(round_num))


def _round_gap_ms(round_num: int) -> int:
    return max(_MIN_GAP_MS, _GAP_MS - (_round_speed_bonus(round_num) // 2))


def _round_hit_ms(round_num: int) -> int:
    return max(_MIN_HIT_MS, _HIT_MS - (_round_speed_bonus(round_num) // 3))


def _draw_board(display) -> None:
    display.fill(_BG)
    display.fill_rect(0, 0, 240, 33, _PANEL)
    display.fill_rect(0, 211, 240, 29, _PANEL)
    for idx in range(4):
        _draw_bar(display, idx, False)


def _draw_instructions(display) -> None:
    display.fill(_BG)
    display.fill_rect(0, 0, 240, 36, _PANEL)
    display.fill_rect(0, 211, 240, 29, _PANEL)
    _center_text(display, "SIMON", 14, _TEXT, _PANEL)
    _center_text(display, "WATCH COLORS", 62, _TEXT, _BG)
    _center_text(display, "REPEAT PATTERN", 82, _MUTED, _BG)
    _center_text(display, "USE BUTTONS:", 112, _TEXT, _BG)
    _center_text(display, "L SEL ST R", 132, _MUTED, _BG)
    display.fill_rect(36, 158, 168, 22, _BACK_BG)
    display.rect(36, 158, 168, 22, gc9a01.WHITE)
    _center_text(display, "BOOT EXITS GAME", 165, _TEXT_DARK, _BACK_BG)
    _center_text(display, "START TO PLAY", 219, _TEXT, _PANEL)


def _draw_status(display, top: str, bottom: str) -> None:
    display.fill_rect(0, 0, 240, 33, _PANEL)
    display.fill_rect(0, 211, 240, 29, _PANEL)
    _center_text(display, top, 12, _TEXT, _PANEL)
    draw_text(display, bottom, 230 - len(bottom) * 8, 219, _MUTED, _PANEL)


def _draw_bar(display, idx: int, lit: bool) -> None:
    x = _BAR_X[idx]
    color = _PAD_LIT[idx] if lit else _PAD_DIM[idx]
    display.fill_rect(x, _BAR_Y, _BAR_W, _BAR_H, color)
    display.rect(x, _BAR_Y, _BAR_W, _BAR_H, gc9a01.WHITE if lit else _BG)
    label = _PAD_LABELS[idx]
    lx = x + (_BAR_W - len(label) * 8) // 2
    draw_text(display, label, lx, _BAR_Y + _BAR_H - 20, _PAD_FG[idx], color)


def _center_text(display, text: str, y: int, fg: int, bg: int) -> None:
    x = (240 - len(text) * 8) // 2
    draw_text(display, text, x, y, fg, bg)


def _set_rgb(leds, idx: int) -> None:
    r, g, b = _scale_rgb(_PAD_LED[idx])
    leds.rgb_fill(r, g, b)
    leds.rgb_show()


def _fill_rgb(leds, color: tuple) -> None:
    r, g, b = _scale_rgb(color)
    leds.rgb_fill(r, g, b)


def _scale_rgb(color: tuple) -> tuple:
    return (
        int(color[0] * _LED_SCALE),
        int(color[1] * _LED_SCALE),
        int(color[2] * _LED_SCALE),
    )


def _pad_for_button(btn: str) -> int:
    for idx in range(4):
        if btn == _PAD_BUTTONS[idx]:
            return idx
    return -1


def _award_happiness(mgr) -> None:
    try:
        for screen in reversed(mgr._stack):
            pet = getattr(screen, "_pet", None)
            if pet is not None:
                pet.add_happiness(1)
                return
    except Exception:
        pass
