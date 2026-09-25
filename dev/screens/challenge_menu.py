"""Challenge screens.

ChallengeMenuScreen is a single scrolling list: the shared quests first, then a
section heading per unlocked character followed by that character's quests. A
character with no unlocked quests contributes no heading. START opens the
selected quest; SELECT / BOOT leaves.

ChallengeDetailScreen — full description, the character that provided the challenge,
and a colour-coded status (COMPLETE / IN PROGRESS (n/m) / NOT COMPLETE).

Challenges are completed automatically by ConagotchiScreen as their criteria are
met (see challenges/base.py); these screens are read-only views of that state.

All drawing goes through the theme-driven `ui` widgets, so the look follows the
active theme with no local colors here.
"""
import time

import ui

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen


def _grouped_challenges():
    """Rows for the flat challenge list: shared quests, then per-character groups.

    Returns a list mixing ui.Header section headings with challenge classes, in
    display order. Characters the badge has not unlocked are omitted entirely,
    heading included, so the list only ever shows reachable content.
    """
    import character_manager
    from challenges import CHALLENGES

    shared = []
    by_character = []          # [(char_id, [cls, ...])], first-seen order
    index = {}
    for cls in CHALLENGES:
        char_id = getattr(cls, "character", "")
        if not char_id:
            shared.append(cls)
            continue
        if not character_manager.is_unlocked(char_id):
            continue
        if char_id not in index:
            index[char_id] = len(by_character)
            by_character.append((char_id, []))
        by_character[index[char_id]][1].append(cls)

    rows = list(shared)
    for char_id, items in by_character:
        if not items:
            continue
        char = character_manager.find(char_id)
        rows.append(ui.Header(char.name if char is not None else char_id))
        rows.extend(items)
    return rows


class ChallengeMenuScreen(Screen):
    """One scrolling list of every reachable challenge, grouped by character."""

    def __init__(self) -> None:
        self._sel = 0
        self._top = 0
        self._rows = []

    async def enter(self, display, leds, mgr) -> None:
        self._rows = _grouped_challenges()
        self._sel = self._first_selectable() if not self._valid_sel() else self._sel
        self._top = ui.clamp_scroll(self._sel, self._top, len(self._rows))
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        await self.enter(display, leds, mgr)

    # ── selection, stepping over headings ────────────────────────────────────

    def _valid_sel(self):
        return (0 <= self._sel < len(self._rows)
                and ui.is_selectable(self._rows[self._sel]))

    def _first_selectable(self):
        for i, row in enumerate(self._rows):
            if ui.is_selectable(row):
                return i
        return 0

    def _move(self, delta, display):
        count = len(self._rows)
        if not count:
            return
        index = self._sel
        for _ in range(count):
            index = (index + delta) % count
            if ui.is_selectable(self._rows[index]):
                self._sel = index
                break
        self._top = ui.clamp_scroll(self._sel, self._top, count)
        self._draw(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT:
            self._move(-1, mgr._display)
        elif btn == RIGHT:
            self._move(1, mgr._display)
        elif btn == START:
            self._open(mgr)

    def _open(self, mgr):
        if not self._valid_sel():
            return
        cls = self._rows[self._sel]
        import challenge_manager
        if (getattr(cls, "interactive", False)
                and not challenge_manager.is_completed(cls.id)):
            from screens.lab import LabScreen
            mgr.push(LabScreen(cls))
        else:
            mgr.push(ChallengeDetailScreen(cls))

    def _draw(self, display) -> None:
        ui.screen(display, "CHALLENGES")
        if not self._rows:
            ui.status(display, "NO QUESTS YET", 104, "muted")
            ui.controls(display)
            return
        items = [row if isinstance(row, ui.Header) else row.name
                 for row in self._rows]
        ui.list_view(display, items, self._sel, self._top)
        ui.controls(display, "OPEN")


_SOURCE_Y = 54
_TITLE_STEP_MS = 320


class ChallengeDetailScreen(Screen):
    """Description/status, or the configured flag for a completed challenge.

    The description scrolls with LEFT/RIGHT when it is longer than the visible
    window; SELECT/BOOT/START return to the challenge list.
    """

    _VISIBLE = 3   # description lines shown at once

    def __init__(self, challenge_cls) -> None:
        self._cls = challenge_cls
        self._lines = ui.wrap(challenge_cls.description, 24)
        self._scroll = 0
        self._title_off = 0
        self._title_next = 0

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    def handle_button(self, btn: str, mgr) -> None:
        top = ui.scroll_max(len(self._lines), self._VISIBLE)
        if btn == LEFT and self._scroll > 0:
            self._scroll -= 1
            self._draw(mgr._display)
        elif btn == RIGHT and self._scroll < top:
            self._scroll += 1
            self._draw(mgr._display)
        else:   # SELECT / BOOT / START -> back to the list
            mgr.pop()

    async def update(self, display, leds, mgr) -> None:
        """Advance the title marquee only when the name does not fit the bezel."""
        if not ui.needs_scroll(self._cls.name):
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._title_next) < 0:
            return
        self._title_next = time.ticks_add(now, _TITLE_STEP_MS)
        self._title_off += 1
        ui.title_bar(display, self._cls.name, offset=self._title_off)

    def _draw(self, display) -> None:
        import character_manager
        import challenge_manager
        cls = self._cls

        # Same chrome as Settings. Quest names are often longer than the ten
        # characters that fit on the title row, so the heading scrolls rather
        # than being drawn past the edge of the glass.
        ui.screen(display, cls.name, offset=self._title_off)

        char_id = getattr(cls, "character", "")
        if char_id:
            char = character_manager.find(char_id)
            src = "FROM " + (char.name if char is not None else "Chi")
        else:
            src = "BASE QUESTS"
        ui.status(display, src[:ui.fit_chars(_SOURCE_Y)], _SOURCE_Y, "muted")

        flag = challenge_manager.get_completed_flag(cls.id)
        if flag:
            # Hard-wrap tokens without dropping characters or adding whitespace.
            self._lines = [flag[i:i + 20] for i in range(0, len(flag), 20)]
        else:
            self._lines = ui.wrap(cls.description, 24)
            if getattr(cls, "interactive", False) and challenge_manager.is_completed(cls.id):
                self._lines = ["Flag not configured."]
        self._scroll = min(self._scroll, ui.scroll_max(len(self._lines), self._VISIBLE))
        ui.text_view(display, self._lines, self._scroll, 84, self._VISIBLE)

        if challenge_manager.is_completed(cls.id):
            ui.status(display, "COMPLETE", 168, "success")
        else:
            prog = cls.progress()
            if prog is not None:
                ui.status(display, "IN PROGRESS", 160, "warning")
                ui.status(display, "(%d/%d)" % prog, 178, "warning")
            else:
                ui.status(display, "NOT COMPLETE", 168, "danger")

        ui.controls(display)
