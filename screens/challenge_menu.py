"""Challenge screens.

ChallengeMenuScreen selects Base Quests or Chi Quests. ChallengeListScreen lists
universal quests or quests belonging to unlocked characters, respectively.
START opens the selected quest; SELECT / BOOT returns one screen.

ChallengeDetailScreen — full description, the character that provided the challenge,
and a colour-coded status (COMPLETE / IN PROGRESS (n/m) / NOT COMPLETE).

Challenges are completed automatically by ConagotchiScreen as their criteria are
met (see challenges/base.py); these screens are read-only views of that state.

All drawing goes through the theme-driven `ui` widgets, so the look follows the
active theme with no local colors here.
"""
import ui

from buttons import BOOT, LEFT, RIGHT, SELECT, START
from screen_manager import Screen


def _unlocked_challenges(character_specific=False):
    """Return registered quests in this category, respecting chi unlocks."""
    import character_manager
    from challenges import CHALLENGES
    out = []
    for cls in CHALLENGES:
        char_id = getattr(cls, "character", "")
        if bool(char_id) != character_specific:
            continue
        if char_id and not character_manager.is_unlocked(char_id):
            continue
        out.append(cls)
    return out


class ChallengeMenuScreen(Screen):
    """Choose the shared or chi-specific quest category."""

    def __init__(self) -> None:
        self._sel = 0

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        self._draw(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT or btn == RIGHT:
            self._sel = (self._sel + (1 if btn == RIGHT else -1)) % 2
            self._draw(mgr._display)
        elif btn == START:
            mgr.push(ChallengeListScreen(character_specific=self._sel == 1))

    def _draw(self, display) -> None:
        ui.screen(display, "CHALLENGES")
        ui.list_view(display, ["Base Quests", "Chi Quests"], self._sel, 0)
        ui.controls(display, "OPEN")


class ChallengeListScreen(Screen):
    """Scrollable list within one quest category."""

    def __init__(self, character_specific=False) -> None:
        self._character_specific = character_specific
        self._sel = 0
        self._top = 0
        self._items = []

    async def enter(self, display, leds, mgr) -> None:
        self._items = _unlocked_challenges(self._character_specific)
        if self._sel >= len(self._items):
            self._sel = max(0, len(self._items) - 1)
        self._top = ui.clamp_scroll(self._sel, self._top, len(self._items))
        self._draw(display)

    async def resume(self, display, leds, mgr) -> None:
        await self.enter(display, leds, mgr)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT:
            self._move(-1, mgr._display)
        elif btn == RIGHT:
            self._move(1, mgr._display)
        elif btn == START:
            if self._items:
                cls = self._items[self._sel]
                import challenge_manager
                if getattr(cls, "interactive", False) and not challenge_manager.is_completed(cls.id):
                    from screens.hackachi_lab import HackachiLabScreen
                    mgr.push(HackachiLabScreen(cls))
                else:
                    mgr.push(ChallengeDetailScreen(cls))

    def _move(self, delta: int, display) -> None:
        if not self._items:
            return
        self._sel = (self._sel + delta) % len(self._items)
        self._top = ui.clamp_scroll(self._sel, self._top, len(self._items))
        self._draw(display)

    def _draw(self, display) -> None:
        ui.screen(display, "CHI QUESTS" if self._character_specific else "BASE QUESTS")
        if not self._items:
            ui.status(display, "NO QUESTS YET", 104, "muted")
            ui.controls(display)
            return
        ui.list_view(display, [c.name for c in self._items], self._sel, self._top)
        ui.controls(display, "OPEN")


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

    def _draw(self, display) -> None:
        import character_manager
        import challenge_manager
        cls = self._cls

        if getattr(cls, "interactive", False):
            ui.clear(display)
            ui.status(display, cls.name[:20], 40, "accent")
        else:
            ui.screen(display, cls.name[:24])

        char_id = getattr(cls, "character", "")
        if char_id:
            char = character_manager.find(char_id)
            src = "FROM " + (char.name if char is not None else "Chi")
        else:
            src = "BASE QUESTS"
        ui.status(display, src[:26], 54, "muted")

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
