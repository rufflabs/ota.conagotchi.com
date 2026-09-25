"""
Screen manager and Screen base class.

Navigation model
────────────────
  mgr.push(screen)      – overlay a new screen on the stack (e.g. open a menu)
  mgr.pop()             – return to the screen beneath (e.g. dismiss a menu)
  mgr.switch_to(screen) – replace the entire stack (e.g. go to a new top-level view)

Screens call push/pop/switch_to synchronously from handle_button(); the manager
queues the transition and executes it during the next update() tick.
"""
import gc


class Screen:
    """Base class — override the methods you need."""

    async def enter(self, display, leds, mgr) -> None:
        """First activation: draw initial state."""

    async def exit(self, display, leds, mgr) -> None:
        """Being destroyed (switch_to or final pop)."""

    async def pause(self, display, leds, mgr) -> None:
        """Another screen was pushed on top; stop animations."""

    async def resume(self, display, leds, mgr) -> None:
        """Back on top after a pop — redraw. Defaults to re-running enter()."""
        await self.enter(display, leds, mgr)

    async def update(self, display, leds, mgr) -> None:
        """Called every ~33 ms. Drive animations and timed transitions here."""

    def next_update_ms(self) -> int:
        """Default update interval; timed animation screens may wake earlier."""
        return 33

    def handle_button(self, btn: str, mgr) -> None:
        """Respond to a button press. Call mgr.push/pop/switch_to to navigate."""


class ScreenManager:
    """Owns the screen stack and routes events."""

    def __init__(self, display, leds, buttons) -> None:
        self._display = display
        self._leds    = leds
        self._buttons = buttons
        self._stack   = []
        self._pending = None   # ("push"|"pop"|"switch", screen_or_None)
        self._busy    = False

    # ── Startup ───────────────────────────────────────────────────────────────

    async def boot(self, screen: Screen) -> None:
        """Load the very first screen. Call once before starting the event loops."""
        self._stack.append(screen)
        await screen.enter(self._display, self._leds, self)

    # ── Synchronous transition requests (called from handle_button) ───────────

    def push(self, screen: Screen) -> None:
        self._pending = ("push", screen)

    def pop(self) -> None:
        self._pending = ("pop", None)

    def switch_to(self, screen: Screen) -> None:
        self._pending = ("switch", screen)

    # ── Event routing (called from the async loops in main.py) ───────────────

    def handle_button(self, btn: str) -> None:
        """Forward a button event to the active screen (ignored during transitions)."""
        if self._current is not None and not self._busy:
            if not self._buttons.enabled(btn):
                if not getattr(self._current, "accepts_disabled_buttons", False):
                    return
            self._pending = None
            self._current.handle_button(btn, self)

    async def update(self) -> None:
        """Tick the active screen, then execute any queued transition."""
        if self._current is not None and self._pending is None:
            await self._current.update(self._display, self._leds, self)
        await self._flush()

    def next_update_ms(self) -> int:
        delay = self._current.next_update_ms() if self._current else 33
        return max(1, min(33, delay))

    # ── Internal ──────────────────────────────────────────────────────────────

    @property
    def _current(self):
        return self._stack[-1] if self._stack else None

    async def _flush(self) -> None:
        if self._pending is None:
            return
        action, screen = self._pending
        self._pending = None
        self._busy = True
        try:
            if action == "push":
                await self._do_push(screen)
            elif action == "pop":
                await self._do_pop()
            elif action == "switch":
                await self._do_switch(screen)
        finally:
            self._busy = False
        self._buttons.clear()  # discard events queued during the transition
        gc.collect()

    async def _do_push(self, screen: Screen) -> None:
        if self._current:
            await self._current.pause(self._display, self._leds, self)
        self._stack.append(screen)
        await screen.enter(self._display, self._leds, self)

    async def _do_pop(self) -> None:
        if not self._stack:
            return
        await self._stack[-1].exit(self._display, self._leds, self)
        self._stack.pop()
        if self._current:
            await self._current.resume(self._display, self._leds, self)

    async def _do_switch(self, screen: Screen) -> None:
        for s in reversed(self._stack):
            await s.exit(self._display, self._leds, self)
        self._stack.clear()
        self._stack.append(screen)
        await screen.enter(self._display, self._leds, self)
