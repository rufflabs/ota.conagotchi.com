"""Reusable, theme-driven UI widgets for the 240x240 round display.

Every widget reads colors, metrics, and chrome style from the active `theme`,
so screens compose these instead of hand-rolling `fill_rect` / `draw_text` with
local constants.  Restyling — including layout spacing and the whole chrome look
(filled panels vs terminal separator lines, highlight bar vs `>` cursor) —
happens entirely in `theme.py`.

Layout note: the display is a circle (centre 120,120, r 120).  Bars span the
full width but their *text* is centred, and list rows are inset by
`theme.text_inset`, so content stays clear of the bezel on the outer rows.

Typical screen:

    import ui
    ui.screen(display, "CHALLENGES", hint="START OPEN  SEL BACK")
    ui.list_view(display, labels, sel, top)
    ui.footer(display, detail_text)
"""
from image_utils import draw_text
import theme

_CHAR_W = 8   # framebuf 8x8 font


def _t():
    return theme.get()


# ── Text ────────────────────────────────────────────────────────────────────

def center_text(display, text, y, fg=None, bg=None):
    """Draw horizontally-centred text.  Colors default to text-on-bg."""
    th = _t()
    fg = th.text if fg is None else fg
    bg = th.bg if bg is None else bg
    x = (240 - len(text) * _CHAR_W) // 2
    draw_text(display, text, x, y, fg, bg)


def text(display, s, x, y, fg=None, bg=None):
    """Draw left-aligned text with theme defaults."""
    th = _t()
    draw_text(display, s, x, y, th.text if fg is None else fg,
              th.bg if bg is None else bg)


# ── Structure ───────────────────────────────────────────────────────────────

def clear(display):
    """Fill the screen with the theme background."""
    display.fill(_t().bg)


def title_bar(display, title, hint=None):
    """Top bar: filled panel ("bar" chrome) or separator line ("frame" chrome)."""
    th = _t()
    if th.chrome == "frame":
        center_text(display, title, (th.title_h - 8) // 2 - 2, th.accent, th.bg)
        display.fill_rect(0, th.title_h - 2, 240, 1, th.muted)
        if hint and th.title_h >= 34:
            center_text(display, hint, th.title_h - 12, th.muted, th.bg)
    else:
        display.fill_rect(0, 0, 240, th.title_h, th.surface)
        center_text(display, title, 8, th.text, th.surface)
        if hint:
            center_text(display, hint, 24, th.muted, th.surface)


def footer(display, s):
    """Bottom bar with centred muted text (filled panel or separator line)."""
    th = _t()
    y0 = 240 - th.footer_h
    if th.chrome == "frame":
        display.fill_rect(0, y0, 240, 1, th.muted)
        center_text(display, s, y0 + (th.footer_h - 8) // 2 + 2, th.muted, th.bg)
    else:
        display.fill_rect(0, y0, 240, th.footer_h, th.surface)
        center_text(display, s, y0 + (th.footer_h - 8) // 2, th.muted, th.surface)


def screen(display, title, hint=None):
    """Clear + draw the title bar in one call (common screen preamble)."""
    clear(display)
    title_bar(display, title, hint)


# Bottom control strip: fixed Y (independent of footer_h) so the text lands
# where the round display is wide enough, in every theme.
_CTRL_TOP = 196
_CTRL_Y   = 201


def controls(display, confirm=None):
    """Standardized bottom instruction line.

    Convention (badge-wide): SELECT — and BOOT — are always Back; START is
    always the confirm / primary action.  Pass the confirm verb (e.g. "OPEN",
    "PLAY", "APPLY"); omit it for a back-only screen.
    """
    th = _t()
    # SELECT is the physical left button, START the right — match that order.
    line = ("SEL BACK  START " + confirm) if confirm else "SEL BACK"
    if th.chrome == "frame":
        display.fill_rect(0, _CTRL_TOP, 240, 1, th.muted)
        center_text(display, line, _CTRL_Y, th.muted, th.bg)
    else:
        display.fill_rect(0, _CTRL_TOP, 240, 240 - _CTRL_TOP, th.surface)
        center_text(display, line, _CTRL_Y, th.muted, th.surface)


# ── Lists ───────────────────────────────────────────────────────────────────

def list_view(display, items, sel, top, value_fg=None):
    """Draw the visible window of a vertical list with the theme's selection style.

    items    — full list; each item is either a label string or a
               (label, value) tuple (value is drawn right-aligned).  Extra tuple
               fields are ignored, so (label, value, action) rows work too.
    sel      — selected index; top — first visible index (caller owns scroll).
    value_fg — optional value -> color fn (e.g. ON green / OFF red); defaults muted.

    Uses theme.rows_visible / row_top / row_h / text_inset / row_pad_x and the
    theme's `select` style ("fill" highlight bar or "marker" `>` cursor).
    Draws a page indicator when the list overflows the visible window.
    """
    th = _t()
    marker = (th.select == "marker")
    end = min(len(items), top + th.rows_visible)
    for i in range(top, end):
        item = items[i]
        label, value = (item[0], item[1]) if isinstance(item, tuple) else (item, None)
        y = th.row_top + (i - top) * th.row_h
        selected = (i == sel)
        if not marker and selected:
            display.fill_rect(th.row_pad_x, y - 2, 240 - 2 * th.row_pad_x,
                              th.row_h, th.sel)
            row_bg = th.sel
        else:
            row_bg = th.bg
        # right-aligned value, and the label budget to its left
        if value is not None:
            vx = 240 - th.text_inset - len(value) * 8
            avail = max(1, (vx - th.text_inset) // 8 - 1)
        else:
            vx = None
            avail = 22
        prefix = ("> " if selected else "  ") if marker else ""
        fg = (th.accent if selected else th.text) if marker else th.text
        draw_text(display, (prefix + label)[:avail], th.text_inset, y + 3, fg, row_bg)
        if value is not None:
            draw_text(display, value, vx, y + 3,
                      value_fg(value) if value_fg else th.muted, row_bg)


def clamp_scroll(sel, top, count):
    """Return an updated `top` so `sel` stays within the visible window."""
    rows = _t().rows_visible
    if sel < top:
        return sel
    if sel >= top + rows:
        return sel - rows + 1
    return min(top, max(0, count - rows))


# ── Scrollable text ──────────────────────────────────────────────────────────

def wrap(text, width):
    """Greedy word-wrap `text` into a list of lines of at most `width` chars."""
    lines = []
    cur = ""
    for w in text.split(" "):
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def scroll_max(count, visible):
    """Largest valid scroll offset for `count` lines showing `visible` at once."""
    return max(0, count - visible)


def text_view(display, lines, top, y, visible, line_h=18):
    """Draw a scrollable window of pre-wrapped `lines` starting at index `top`.

    Shows up to `visible` centred lines from `y`, with a small ^ / v marker when
    there is more text above / below.  The caller owns `top` (clamp it with
    scroll_max()).
    """
    th = _t()
    end = min(len(lines), top + visible)
    for i in range(top, end):
        center_text(display, lines[i], y + (i - top) * line_h, th.text, th.bg)
    if top > 0:
        center_text(display, "^", y - 12, th.muted, th.bg)
    if end < len(lines):
        center_text(display, "v", y + visible * line_h, th.muted, th.bg)


# ── Status ──────────────────────────────────────────────────────────────────

def status(display, s, y, kind="text"):
    """Centred status text coloured by semantic kind.

    kind — one of the theme color tokens: success / warning / danger / accent /
    muted / text.
    """
    color = getattr(_t(), kind, _t().text)
    center_text(display, s, y, color, _t().bg)
