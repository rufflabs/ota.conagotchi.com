"""Runtime FPS overlay for the main update loop.

A small live flag (independent of the persisted `fps_enabled` setting) plus a
per-frame draw. The update loop calls draw() every frame; it renders a compact
FPS number in the top-center of the display, on top of whatever the current
screen drew, only while enabled.

Why a module-level flag instead of reading BadgeSettings: SettingsScreen owns its
own BadgeSettings instance, so its toggle can't reach the loop's instance in
memory. Instead main seeds this flag from the persisted setting on boot, and the
Settings toggle calls set_enabled() so the change takes effect immediately. The
persisted `fps_enabled` remains the source of truth across reboots.
"""
import time

from image_utils import draw_text

_FG = 0x07E0          # green (RGB565 big-endian, same encoding as gc9a01 consts)
_BG = 0x0000          # black cell behind the digits so it reads over any art
_Y = 2                # top-center
_WINDOW_MS = 500      # averaging window — stable reading, still responsive

_enabled = False
_frames = 0
_win_start = 0
_value = 0


def set_enabled(on: bool) -> None:
    """Enable/disable the overlay and reset the averaging window."""
    global _enabled, _frames, _win_start, _value
    _enabled = bool(on)
    _frames = 0
    _win_start = time.ticks_ms()
    _value = 0


def enabled() -> bool:
    return _enabled


def draw(display) -> None:
    """Call once per frame from the update loop. Draws the overlay when enabled;
    a no-op otherwise (the screen underneath repaints the region on next redraw)."""
    global _frames, _win_start, _value
    if not _enabled:
        return
    _frames += 1
    now = time.ticks_ms()
    elapsed = time.ticks_diff(now, _win_start)
    if elapsed >= _WINDOW_MS:
        _value = _frames * 1000 // elapsed
        _frames = 0
        _win_start = now
    s = "%d" % _value
    draw_text(display, s, (240 - len(s) * 8) // 2, _Y, _FG, _BG)
