"""Pet care submenu with Happiness, Hydration, Snackiness, and Work actions.

The list view shows each resource as a compact bar. START begins the selected
care action and returns to the pet screen so the matching animation can play.
"""
import ui
import theme

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from image_utils import draw_text
from screen_manager import Screen


# (label, pet attribute, theme color token, pet action, START verb)
# The Work row's label and START verb come from the active character at runtime.
_STAT_ITEMS = (
    ("Happiness", "happiness", "warning", "chill", "CHILL"),
    ("Hydration", "thirst", "accent", "hydrate", "WATER"),
    ("Snackiness", "hunger", "success", "snack", "SNACK"),
    ("Work", "work", "danger", "work", "WORK"),
)

# Compact rows so all four resource bars fit above the control strip (y=196)
# on the round display.
_ROW_TOP = 48
_ROW_H   = 36

class PetMenuScreen(Screen):
    """Shows care stats; START runs the selected care action."""

    def __init__(self, pet) -> None:
        self._pet = pet
        self._sel = 0
        self._message = ""
        # Per-character label + START verb for the Work row.
        work_name = getattr(pet, "work_name", "Work")
        work_label = getattr(pet, "work_label", work_name)
        self._items = tuple(
            (work_name, item[1], item[2], item[3], work_label.upper())
            if item[1] == "work" else item
            for item in _STAT_ITEMS
        )

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT:
            self._sel = (self._sel - 1) % len(self._items)
            self._message = ""
            self._draw(mgr._display)
        elif btn == RIGHT:
            self._sel = (self._sel + 1) % len(self._items)
            self._message = ""
            self._draw(mgr._display)
        elif btn == START:
            self._apply_selected(mgr)

    # ── Drawing ──────────────────────────────────────────────────────────────

    def _draw(self, display) -> None:
        self._draw_list(display)

    def _draw_list(self, display) -> None:
        th = theme.get()
        ui.screen(display, "PET")
        for idx, item in enumerate(self._items):
            label, attr, token, _action, _verb = item
            _draw_stat_bar(display, label, _stat_value(self._pet, attr),
                           _ROW_TOP + idx * _ROW_H, getattr(th, token),
                           idx == self._sel, th)
        if self._message:
            ui.status(display, self._message, 176, "warning")
        ui.controls(display, self._items[self._sel][4])

    def _apply_selected(self, mgr) -> None:
        action = self._items[self._sel][3]
        if self._pet.begin_action(action):
            mgr.pop()
            return
        self._message = "BUSY"
        self._draw(mgr._display)


def _draw_stat_bar(display, label: str, value: int, y: int,
                   color: int, selected: bool, th) -> None:
    value = max(0, min(100, int(value)))
    bg = th.sel if selected else th.bg
    if selected:
        display.fill_rect(20, y - 6, 200, 26, th.sel)
        display.rect(20, y - 6, 200, 26, th.accent)
    draw_text(display, label, 32, y, th.text, bg)
    draw_text(display, "{}%".format(value), 184, y, th.muted, bg)
    bar_x = 32
    bar_y = y + 11
    bar_w = 176
    bar_h = 6
    fill_w = (bar_w - 2) * value // 100
    display.rect(bar_x, bar_y, bar_w, bar_h, th.muted)
    display.fill_rect(bar_x + 1, bar_y + 1, bar_w - 2, bar_h - 2, th.surface)
    if fill_w > 0:
        display.fill_rect(bar_x + 1, bar_y + 1, fill_w, bar_h - 2, color)


def _stat_value(pet, attr: str) -> int:
    return int(max(0, min(100, getattr(pet, attr, 0))))
