"""Pet care submenu with Happiness, Hydration, Snackiness, and Work actions.

The list view shows each resource as a compact bar. START begins the selected
care action and returns to the pet screen so the matching animation can play.
"""
import ui

from buttons import BOOT, LEFT, RIGHT, SELECT, START
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
        ui.screen(display, "PET")
        rows = [(label, _stat_value(self._pet, attr), token)
                for label, attr, token, _action, _verb in self._items]
        ui.meter_list(display, rows, self._sel, _ROW_TOP, _ROW_H)
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


def _stat_value(pet, attr: str) -> int:
    return int(max(0, min(100, getattr(pet, attr, 0))))
