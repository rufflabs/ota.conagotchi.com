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


def fit_chars(y):
    """How many 8px characters fit inside the round bezel on the row at `y`.

    The display is a 240x240 circle, so a row's usable width depends on how far
    it is from the centre. Text drawn with draw_text occupies y..y+7, and the
    worse of those two edges decides the budget. Capped at 20, which is the
    widest any row should be.
    """
    worst = 0.0
    for edge in (y, y + 7):
        worst = max(worst, abs(119.5 - edge))
    if worst >= 114:
        return 0
    half = (114.0 * 114.0 - worst * worst) ** 0.5
    return max(1, min(20, int(half * 2) // 8))


# The Settings screen's title chrome, which is the badge standard: a filled
# panel across the top with the heading centred on it. Kept as explicit numbers
# rather than theme metrics so every screen matches Settings exactly; if Settings
# changes these, change them here too.
TITLE_PANEL_H = 36
TITLE_TEXT_Y = 14
HINT_TEXT_Y = 24


def title_bar(display, title, hint=None, offset=0):
    """Top panel with a centred heading, in the Settings style.

    The panel sits near the top of the round display, so only about ten
    characters fit on that row. Longer headings scroll horizontally instead of
    being drawn past the edge of the glass: pass a rising `offset` (see
    needs_scroll) from the screen's update() tick.
    """
    th = _t()
    display.fill_rect(0, 0, 240, TITLE_PANEL_H, th.surface)
    width = fit_chars(TITLE_TEXT_Y)
    center_text(display, scroll_window(title, offset, width), TITLE_TEXT_Y,
                th.text, th.surface)
    if hint:
        center_text(display, hint[:fit_chars(HINT_TEXT_Y)], HINT_TEXT_Y,
                    th.muted, th.surface)


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


def screen(display, title, hint=None, offset=0):
    """Clear + draw the title bar in one call (common screen preamble)."""
    clear(display)
    title_bar(display, title, hint, offset)


# Bottom control strip: fixed Y (independent of footer_h) so the text lands
# where the round display is wide enough, in every theme.
_CTRL_TOP = 196
_CTRL_Y   = 201


def _strip(display, th):
    """Paint the bottom strip and return the background colour used on it."""
    if th.chrome == "frame":
        display.fill_rect(0, _CTRL_TOP, 240, 1, th.muted)
        display.fill_rect(0, _CTRL_TOP + 1, 240, 240 - _CTRL_TOP - 1, th.bg)
        return th.bg
    display.fill_rect(0, _CTRL_TOP, 240, 240 - _CTRL_TOP, th.surface)
    return th.surface


def bottom_line(display, text):
    """One centred, muted line in the bottom strip, for screens whose footer is
    a message rather than the standard Back/confirm pair."""
    th = _t()
    bg = _strip(display, th)
    center_text(display, text[:fit_chars(_CTRL_Y)], _CTRL_Y, th.muted, bg)


def controls(display, confirm=None):
    """Bottom control strip: BACK on the left, the confirm verb on the right.

    The two words sit at the edges of the row's usable width, which puts them
    under the physical buttons they describe - SELECT (and BOOT) on the left is
    always Back, START on the right is always the confirm. Because each word is
    anchored to its own side, the alignment holds whatever the verb is.

    Pass the verb (e.g. "OK", "RUN", "OPEN"); omit it for a back-only screen.
    """
    th = _t()
    bg = _strip(display, th)
    width = fit_chars(_CTRL_Y)
    left = (240 - width * _CHAR_W) // 2
    draw_text(display, "BACK", left, _CTRL_Y, th.muted, bg)
    if confirm:
        verb = confirm[:max(1, width - 6)]   # always leave room for BACK + a gap
        right = left + (width - len(verb)) * _CHAR_W
        draw_text(display, verb, right, _CTRL_Y, th.muted, bg)


def window_top(selected, count, visible=None):
    """Scroll offset that centres `selected` in a `visible`-row window.

    Stateless: the window is derived from the selection alone, so a caller that
    only tracks an index gets a stable view. Use clamp_scroll() instead when the
    caller keeps its own `top` and wants the window to move as little as
    possible.
    """
    if visible is None:
        visible = _t().rows_visible
    if count <= visible:
        return 0
    return max(0, min(selected - visible // 2, count - visible))


# ── Lists ───────────────────────────────────────────────────────────────────

class Header:
    """A non-selectable section heading inside a list_view.

    Lets one flat list carry grouped content - e.g. shared challenges, then a
    heading per unlocked character - instead of splitting the content across
    separate screens. Callers must skip Header rows when moving the selection;
    see is_selectable().
    """

    __slots__ = ("label",)

    def __init__(self, label):
        self.label = label


def is_selectable(item):
    """False for section headings, so navigation can step over them."""
    return not isinstance(item, Header)


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
        y = th.row_top + (i - top) * th.row_h
        if isinstance(item, Header):
            # Muted and never highlighted, so a group reads as a divider rather
            # than another choice. Indented to where a row's label glyphs
            # actually start: marker themes prefix entries with "> " or two
            # spaces, so the heading has to clear that too, or it sits left of
            # the entries it introduces.
            head_x = th.text_inset + (2 * _CHAR_W if marker else 0)
            draw_text(display, item.label[:fit_chars(y + 3)].upper(),
                      head_x, y + 3, th.muted, th.bg)
            continue
        label, value = (item[0], item[1]) if isinstance(item, tuple) else (item, None)
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


def scroll_window(text, offset, width, gap="   "):
    """A `width`-character window into `text`, wrapping round via `gap`.

    Returns `text` unchanged when it already fits, so a caller can use this
    unconditionally and only animate when `needs_scroll` says so.
    """
    if len(text) <= width:
        return text
    loop = text + gap
    start = offset % len(loop)
    return (loop + loop)[start:start + width]


def needs_scroll(text, y=None):
    """True when `text` is too wide for the bezel at `y` (default: the title row).

    Screens use this to decide whether to run a marquee at all, so a short
    heading stays perfectly still."""
    return len(text) > fit_chars(TITLE_TEXT_Y if y is None else y)


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
