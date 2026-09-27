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

def center_text(display, text, y, fg=None, bg=None, scale=1):
    """Draw horizontally-centred text.  Colors default to text-on-bg."""
    th = _t()
    fg = th.text if fg is None else fg
    bg = th.bg if bg is None else bg
    x = (240 - len(text) * _CHAR_W * scale) // 2
    if scale == 1:
        draw_text(display, text, x, y, fg, bg)
    else:
        draw_text(display, text, x, y, fg, bg, scale)


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


def screen(display, title, hint=None, offset=0, marquee=None):
    """Clear + draw the title bar in one call (common screen preamble).

    Pass the screen's Marquee and a heading too long for the title row scrolls
    (the Marquee supplies the offset; call its tick() from update())."""
    clear(display)
    if marquee is not None:
        offset = marquee.use(title)
    title_bar(display, title, hint, offset)


class Marquee:
    """Scrolls text that is too wide for its space: a heading, or a list row.

    Title: one per screen. Draw with `screen(..., marquee=m)` (or
    `title_bar(..., offset=m.use(title))`), and call `m.tick(display)` from the
    screen's update().
    List row: pass `marquee=m` to list_view and call `tick_list(...)` from
    update(); the selected row's label scrolls when it does not fit.
    Text that fits never moves; changing the text restarts it from its first
    character.
    """

    def __init__(self, step_ms=320):
        self.text = ""
        self.offset = 0
        self.width = None     # None = the title row's width
        self._step = step_ms
        self._next = None

    def use(self, text, width=None):
        """Make `text` the scrolling text and return the offset to draw at.
        `width` is the characters available; omit it for a heading."""
        self.width = width
        if text != self.text:
            self.text = text
            self.reset()
        return self.offset

    def scrolls(self):
        """True when the current text does not fit its space."""
        if self.width is None:
            return needs_scroll(self.text)
        return len(self.text) > self.width

    def due(self):
        """Advance one character when the step time has passed. Returns True
        when it advanced, so the caller repaints; False for text that fits."""
        if not self.scrolls():
            return False
        import time
        now = time.ticks_ms()
        if self._next is None:
            self._next = time.ticks_add(now, self._step)
            return False
        if time.ticks_diff(now, self._next) < 0:
            return False
        self._next = time.ticks_add(now, self._step)
        self.offset += 1
        return True

    def reset(self):
        """Start the heading again from its first character."""
        self.offset = 0
        self._next = None

    def tick(self, display):
        """Advance a heading when due and repaint only the title row.
        Returns True when it repainted."""
        if not self.due():
            return False
        title_bar(display, self.text, offset=self.offset)
        return True


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


# ── List text size ──────────────────────────────────────────────────────────
# Menu rows can be drawn at 2x (Settings -> Badge -> Text Size). Only list rows
# and their headings change; titles, controls and body text keep their size,
# and right-hand values stay at normal size. Large rows are taller, so fewer fit.
_LIST_SCALE = 1
_LARGE_ROWS = (54, 34, 3)     # row_top, row_h, rows_visible at 2x


def set_list_scale(scale) -> None:
    """1 for normal menu text, 2 for large. Applied at boot from settings."""
    global _LIST_SCALE
    _LIST_SCALE = 2 if scale == 2 else 1


def list_scale() -> int:
    return _LIST_SCALE


def list_metrics(scale=None):
    """(row_top, row_h, rows_visible) for the theme and the menu text size."""
    if (scale or _LIST_SCALE) == 2:
        return _LARGE_ROWS
    th = _t()
    return th.row_top, th.row_h, th.rows_visible


def window_top(selected, count, visible=None):
    """Scroll offset that centres `selected` in a `visible`-row window.

    Stateless: the window is derived from the selection alone, so a caller that
    only tracks an index gets a stable view. Use clamp_scroll() instead when the
    caller keeps its own `top` and wants the window to move as little as
    possible.
    """
    if visible is None:
        visible = list_metrics()[2]
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


def state_color(value):
    """Standard colour for a row value: ON/ACTIVE/LINKED success, OFF danger,
    anything else muted. list_view uses it unless given its own value_fg."""
    th = _t()
    if value in ("ON", "ACTIVE", "LINKED"):
        return th.success
    if value == "OFF":
        return th.danger
    return th.muted


def label_width(value=None, scale=None):
    """Characters a row's label may use, beside an optional right-hand value
    (the selection prefix of marker themes included). The value is always
    normal size; the label follows the menu text size."""
    th = _t()
    scale = scale or _LIST_SCALE
    cw = _CHAR_W * scale
    if value is None:
        return (240 - 2 * th.text_inset) // cw
    vx = 240 - th.text_inset - len(value) * _CHAR_W
    if scale == 1:
        return max(1, (vx - th.text_inset) // _CHAR_W - 1)
    return max(1, (vx - th.text_inset - _CHAR_W) // cw)


def row(display, y, label, value=None, selected=False, value_fg=None, fill=None,
        scroll=0, scale=None, clear=False):
    """One list row whose top is `y`, in the theme's style and the menu text
    size (`scale` overrides it; the button test keeps its rows normal size).

    list_view draws its rows with this; call it directly only for a layout
    list_view cannot express, e.g. several rows lit at once (the button test).
    fill   — a theme colour name to highlight the row with instead of the
             selection colour; its text is drawn in the background colour.
    scroll — for a label too long for the row: the selected row shows a window
             starting `scroll` characters in; unselected rows are clipped.
    """
    th = _t()
    scale = scale or _LIST_SCALE
    row_h = list_metrics(scale)[1]
    # Label and value are vertically centred in the row (normal: both at y+3).
    label_y = y + 3 if scale == 1 else y + (row_h - 16) // 2 - 2
    value_y = y + 3 if scale == 1 else y + (row_h - 8) // 2 - 2
    marker = (th.select == "marker")
    lit = selected or fill is not None
    # Narrowed on the outer rows so the bar's corners stay on the glass. The
    # bar never reaches the scrollbar arc, so a row can repaint just this box.
    w = box_width(y - 2, row_h, 240 - 2 * th.row_pad_x)
    if lit and (not marker or fill is not None):
        row_bg = getattr(th, fill) if fill else th.sel
        display.fill_rect((240 - w) // 2, y - 2, w, row_h, row_bg)
    else:
        row_bg = th.bg
        if clear:                 # erase a highlight this row used to have
            display.fill_rect((240 - w) // 2, y - 2, w, row_h, row_bg)
    # right-aligned value, and the label budget to its left
    avail = label_width(value, scale)
    vx = 240 - th.text_inset - len(value) * _CHAR_W if value is not None else None
    prefix = ("> " if selected else "  ") if marker else ""
    # Large text draws the marker at normal size: 16px, one large character.
    width = max(1, avail - (len(prefix) if scale == 1 else len(prefix) // 2))
    if len(label) > width:
        label = scroll_window(label, scroll, width) if selected else clip(label, width)
    if fill:
        fg = th.bg
    else:
        fg = (th.accent if selected else th.text) if marker else th.text
    if scale == 1:
        draw_text(display, prefix + label, th.text_inset, label_y, fg, row_bg)
    else:
        x = th.text_inset
        if prefix:
            draw_text(display, prefix, x, value_y, fg, row_bg)
            x += len(prefix) * _CHAR_W
        draw_text(display, label, x, label_y, fg, row_bg, scale)
    if value is not None:
        vfg = th.bg if fill else (value_fg or state_color)(value)
        draw_text(display, value, vx, value_y, vfg, row_bg)


# Scrollbar: an arc hugging the right edge of the glass beside the list rows.
_BAR_R = 116          # arc radius (the glass is 120; row text stops inside 114)
_BAR_W = 3            # thickness in pixels, drawn outward from _BAR_R
_BAR_MIN = 10         # shortest thumb, in pixels of height


def _arc_x(y):
    """x of the scrollbar arc on row y (right-hand side of the circle)."""
    dy = y + 0.5 - 119.5
    return int(119.5 + (_BAR_R * _BAR_R - dy * dy) ** 0.5)


_ARC_RUNS = {}          # (y0, y1) -> [(x, y, height)], computed once per list


def _arc_runs(y0, y1):
    """The arc between rows y0..y1 as vertical runs sharing an x, so a long arc
    is a handful of rectangles, not one per pixel. Cached: lists reuse a few
    fixed spans, and the square roots are the slow part on the badge."""
    key = (y0, y1)
    runs = _ARC_RUNS.get(key)
    if runs is None:
        runs = []
        y = y0
        while y < y1:
            x = _arc_x(y)
            run = 1
            while y + run < y1 and _arc_x(y + run) == x:
                run += 1
            runs.append((x, y, run))
            y += run
        _ARC_RUNS[key] = runs
    return runs


def scrollbar(display, top, visible, count, y0, y1) -> None:
    """Where the visible window sits in a longer list: a dim track from y0 to
    y1 and a brighter thumb sized to visible/count. Nothing when all fits.
    Each run is drawn once, in its track or thumb colour (no overdraw)."""
    if count <= visible or y1 <= y0:
        return
    th = _t()
    span = y1 - y0
    thumb = max(_BAR_MIN, span * visible // count)
    t0 = y0 + (span - thumb) * top // (count - visible)
    t1 = t0 + thumb
    for x, y, h in _arc_runs(y0, y1):
        end = y + h
        # split the run where it crosses the thumb's edges
        for a, b, color in ((y, min(end, t0), th.heading),
                            (max(y, t0), min(end, t1), th.muted),
                            (max(y, t1), end, th.heading)):
            if b > a:
                display.fill_rect(x, a, _BAR_W, b - a, color)


def list_view(display, items, sel, top, value_fg=None, marquee=None, only=None,
              clear=False):
    """Draw the visible window of a vertical list with the theme's selection style.

    items    — full list; each item is either a label string or a
               (label, value) tuple (value is drawn right-aligned).  Extra tuple
               fields are ignored, so (label, value, action) rows work too.
    sel      — selected index; top — first visible index (caller owns scroll).
    value_fg — optional value -> color fn; defaults to state_color (ON green,
               OFF red, else muted).

    marquee  — a Marquee: the selected row's label scrolls when too long
               (drive it with tick_list from update()).
    only     — redraw just this index, or these indices (used by tick_list
               and repaint_list).
    clear    — erase each drawn row's box first (for repainting in place).

    Uses theme.rows_visible / row_top / row_h / text_inset / row_pad_x and the
    theme's `select` style ("fill" highlight bar or "marker" `>` cursor).
    """
    th = _t()
    marker = (th.select == "marker")
    row_top, row_h, visible = list_metrics()
    scale = _LIST_SCALE
    end = min(len(items), top + visible)
    if only is not None and not isinstance(only, (tuple, list)):
        only = (only,)
    for i in range(top, end):
        if only is not None and i not in only:
            continue
        item = items[i]
        y = row_top + (i - top) * row_h
        if isinstance(item, Header):
            # Styled like the title panel, a shade darker (theme "heading"):
            # a full-width band with the name centred, so a group reads as a
            # divider rather than another choice. Never highlighted.
            display.fill_rect(0, y - 2, 240, row_h, th.heading)
            if scale == 1:
                center_text(display, clip(item.label.upper(), fit_chars(y + 3)),
                            y + 3, th.text, th.heading)
            else:
                ty = y + (row_h - 16) // 2 - 2
                chars = box_width(ty, 16) // (_CHAR_W * scale)
                center_text(display, clip(item.label.upper(), chars), ty,
                            th.text, th.heading, scale)
            continue
        label, value = (item[0], item[1]) if isinstance(item, tuple) else (item, None)
        scroll = 0
        if marquee is not None and i == sel:
            prefix = (2 if scale == 1 else 1) if marker else 0
            scroll = marquee.use(label, label_width(value) - prefix)
        row(display, y, label, value, i == sel, value_fg, scroll=scroll, clear=clear)
    if only is None:
        scrollbar(display, top, visible, len(items), row_top - 2,
                  row_top - 2 + visible * row_h)


def repaint_list(display, items, sel, top, old_sel, old_top, value_fg=None,
                 marquee=None) -> None:
    """After the selection moved, repaint only what changed: the two rows
    whose highlight changed, or, when the window scrolled, the rows area and
    the scrollbar. The title, message line and controls are left alone."""
    if top == old_top:
        list_view(display, items, sel, top, value_fg, marquee,
                  only=(old_sel, sel), clear=True)
        return
    row_top, row_h, visible = list_metrics()
    display.fill_rect(0, row_top - 2, 240, visible * row_h, _t().bg)
    list_view(display, items, sel, top, value_fg, marquee)


def tick_list(display, items, sel, top, marquee, value_fg=None):
    """Call from update(): scrolls the selected row's too-long label, repainting
    only that row. Returns True when it repainted."""
    if not marquee.due():
        return False
    list_view(display, items, sel, top, value_fg, marquee=marquee, only=sel)
    return True


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


def page_top(sel, count, visible=None):
    """First row of the page holding `sel`: lists move a page at a time, so
    the window only changes when the selection leaves the page (pages start
    at 0, visible, 2*visible, ...; the last page may be short)."""
    if visible is None:
        visible = list_metrics()[2]
    if count <= visible:
        return 0
    return (sel // visible) * visible


def clamp_scroll(sel, top, count):
    """Return an updated `top` so `sel` stays within the visible window."""
    rows = list_metrics()[2]
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


def wrap_text(text, width=20):
    """Wrap `text` for display: honours newlines (a blank line stays blank) and
    hard-splits any word longer than `width`, such as a flag token or a file
    path, so nothing runs into the bezel and no character is lost."""
    lines = []
    for paragraph in text.split("\n"):
        for line in wrap(paragraph, width):
            lines.extend(line[i:i + width] for i in range(0, len(line), width))
        if not paragraph:
            lines.append("")
    return lines or [""]


PAGE_Y = 56        # text_page: first line
PAGE_ROWS = 5
PAGE_LINE_H = 20
_PAGE_COUNT_Y = 172


def text_page(display, lines, top, y=PAGE_Y, visible=PAGE_ROWS,
              line_h=PAGE_LINE_H):
    """A scrollable page of body text with its position ("n/m") below.

    `lines` come from wrap_text(); the caller owns `top` (0..scroll_max) and
    moves it with LEFT/RIGHT."""
    text_view(display, lines, top, y, visible, line_h=line_h)
    pages = max(1, len(lines) - (visible - 1))
    status(display, "%d/%d" % (top + 1, pages), _PAGE_COUNT_Y, "muted")


def text_lines(display, lines, y, line_h=18):
    """Centred lines from `y` down, each clipped to the bezel at its own row.

    lines — strings (drawn as text) or (string, kind) with a theme colour name.
    Returns the y just below the last line."""
    for line in lines:
        label, kind = line if isinstance(line, tuple) else (line, "text")
        status(display, label, y, kind)
        y += line_h
    return y


def paragraph(display, text, y, kind="muted", line_h=18, width=20):
    """Word-wrap `text` and draw it centred from `y`. Returns the next y."""
    return text_lines(display, [(l, kind) for l in wrap_text(text, width)],
                      y, line_h)


MESSAGE_Y = 178    # below the list rows of every theme, above the control strip


def message(display, text, kind="accent"):
    """The one-line feedback slot above the control strip ("SAVED", "WIFI ON").
    Draws nothing for an empty message."""
    if text:
        status(display, text, MESSAGE_Y, kind)


# ── Cards and dialogs ────────────────────────────────────────────────────────
# A box on a round screen clips at its corners long before its edges touch the
# bezel, so every bordered box goes through box_width(): the widest centred box
# whose four corners stay inside the same radius-114 margin the bounds tests use.

_BOX_R = 114
_LINE_H = 18      # spacing between text lines inside a card or dialog
_BOX_PAD = 10     # space between a box's edge and its first/last text line
CARD_Y = 72       # the standard single-item card (character, stamp, trade)
CARD_H = 64


def box_width(y, h, want=240):
    """Widest centred box spanning rows y..y+h that fits inside the bezel,
    capped at `want`. Even, so the box sits exactly on the centre line."""
    worst = max(abs(119.5 - y), abs(119.5 - (y + h)))
    if worst >= _BOX_R:
        return 0
    half = (_BOX_R * _BOX_R - worst * worst) ** 0.5
    return min(want, int(half * 2)) & ~1


def clip(s, width):
    """Shorten `s` to `width` characters, marking the cut with '>'."""
    if len(s) <= width:
        return s
    return s[:max(0, width - 1)] + ">"


def _line_color(th, kind):
    return getattr(th, kind, th.text) if kind else th.text


def card(display, lines, y=CARD_Y, h=CARD_H, w=168, edge=None):
    """Bordered panel centred on the screen, with centred text lines inside.

    lines — label strings, or (label, kind) tuples where kind is a theme colour
            name ("text", "muted", "success", ...). Plain strings are drawn in
            `text` for the first line and `muted` for the rest, which is the
            standard name-then-detail card.
    The box is narrowed if its corners would leave the glass, and each line is
    clipped to the box. Returns (x, y, w, h) of the box actually drawn.
    """
    th = _t()
    w = box_width(y, h, w)
    x = (240 - w) // 2
    display.fill_rect(x, y, w, h, th.sel)
    display.rect(x, y, w, h, th.text if edge is None else getattr(th, edge, edge))
    if lines:
        chars = max(1, (w - 8) // _CHAR_W)
        n = len(lines)
        # Spread the lines between the pads, no looser than 24px apart, and
        # centre the block vertically in the box.
        span = h - 2 * _BOX_PAD - 8
        step = min(24, span // (n - 1)) if n > 1 else 0
        top = y + (h - 8 - step * (n - 1)) // 2
        for i, line in enumerate(lines):
            if isinstance(line, tuple):
                label, kind = line
            else:
                label, kind = line, ("text" if i == 0 else "muted")
            center_text(display, clip(label, chars), top + i * step,
                        _line_color(th, kind), th.sel)
    return x, y, w, h


def dialog(display, title, lines=(), kind=None):
    """Modal message box drawn over whatever is already on screen.

    Use for confirmations and short notices (e.g. "DEBUG / UNLOCKED"). It is
    centred on the display, so it has the most width available, and sized to
    its content. The title is primary text and body lines are muted; `kind`
    (a theme colour name) colours the border, since coloured text on the
    selection fill is hard to read in some themes. Callers own dismissal and
    redraw.
    """
    rows = [(title, "text")] + [(s, "muted") for s in lines]
    h = 2 * _BOX_PAD + 8 + (len(rows) - 1) * _LINE_H
    y = 120 - h // 2
    return card(display, rows, y, h, w=200, edge=kind or "text")


def pager(display, selected, count, y=112, count_y=184):
    """Carousel affordance: < > at the sides of row `y` and "n/m" below.

    For screens that show one item at a time and move with LEFT/RIGHT.
    Draws nothing for a single item.
    """
    if count <= 1:
        return
    th = _t()
    # Just inside the glass on this row, so the arrows sit outside the
    # standard card rather than on top of it.
    inset = max(20, (240 - box_width(y, 8)) // 2 + 2)
    draw_text(display, "<", inset, y, th.muted, th.bg)
    draw_text(display, ">", 240 - inset - _CHAR_W, y, th.muted, th.bg)
    center_text(display, "%d/%d" % (selected + 1, count), count_y, th.muted, th.bg)


def value_picker(display, value, hint=None, detail=None):
    """A single value adjusted with LEFT/RIGHT: an optional hint above, the
    value in a card, and a detail line (range, or "n/m") below it."""
    if hint:
        paragraph(display, hint, 72)
    # Sized to the value, so a number sits in a compact box and a long lab
    # option still gets the full width.
    card(display, (value,), y=110, h=34, w=min(200, max(96, len(value) * _CHAR_W + 32)))
    if detail:
        status(display, detail, 160, "muted")


# ── Progress ────────────────────────────────────────────────────────────────

def progress_bar(display, y, pct, h=8, w=180, kind="accent", prev=None,
                 frame=False):
    """Horizontal progress bar centred on the screen, narrowed to the bezel.

    kind  — theme colour name of the filled part; the trough is `surface`.
    frame — draw a muted outline round the trough.
    prev  — the value this returned last time. Pass it back while the bar only
            grows and just the newly filled slice is painted, so a bar updated
            from a progress callback never flickers. None repaints it whole.
    Returns the filled width in pixels.
    """
    th = _t()
    w = box_width(y, h, w)
    x = (240 - w) // 2
    ix, iy, iw, ih = (x + 1, y + 1, w - 2, h - 2) if frame else (x, y, w, h)
    pct = max(0, min(100, int(pct)))
    fill = iw * pct // 100
    color = getattr(th, kind, th.accent)
    if prev is None or fill < prev:
        if frame:
            display.rect(x, y, w, h, th.muted)
        display.fill_rect(ix, iy, iw, ih, th.surface)
        if fill:
            display.fill_rect(ix, iy, fill, ih, color)
    elif fill > prev:
        display.fill_rect(ix + prev, iy, fill - prev, ih, color)
    return fill


def meter_list(display, rows, sel, y=48, row_h=36):
    """Stacked meters: each row a label, a value and a bar beneath.

    rows — (label, pct, kind) or (label, pct, kind, value): kind is the bar's
           theme colour name; value is the right-hand text (default "NN%").
    sel  — index of the boxed row, or None for no selection.
    Every row gets the width of the narrowest one that fits the bezel, so
    the bars line up.
    """
    th = _t()
    box_h = 26
    w = 200
    for i in range(len(rows)):
        w = min(w, box_width(y + i * row_h - 6, box_h, 200))
    x = (240 - w) // 2
    chars = (w - 24) // _CHAR_W
    for i, meter in enumerate(rows):
        label, pct, kind = meter[0], meter[1], meter[2]
        ry = y + i * row_h
        pct = max(0, min(100, int(pct)))
        selected = i == sel
        bg = th.sel if selected else th.bg
        if selected:
            display.fill_rect(x, ry - 6, w, box_h, th.sel)
            display.rect(x, ry - 6, w, box_h, th.accent)
        value = meter[3] if len(meter) > 3 else "%d%%" % pct
        # Both texts are padded to fixed widths, so redrawing a row in place
        # overwrites the previous text completely (see refresh-in-place below).
        value = " " * max(0, 6 - len(value)) + value
        label_w = chars - len(value) - 1
        label = clip(label, label_w)
        draw_text(display, label + " " * (label_w - len(label)), x + 12, ry,
                  th.text, bg)
        draw_text(display, value, x + w - 12 - len(value) * _CHAR_W, ry,
                  th.muted, bg)
        progress_bar(display, ry + 11, pct, h=6, w=w - 24, kind=kind, frame=True)


def status_row(display, s, y, kind="text"):
    """A status line that can be redrawn in place without flicker: the text is
    centred inside a full-width row of spaces, so it overwrites whatever the
    row held before. Use it for lines that change while a screen is open."""
    width = fit_chars(y)
    s = clip(s, width)
    left = (width - len(s)) // 2
    status(display, " " * left + s + " " * (width - len(s) - left), y, kind)


def meters_in_place(display, rows, prev_keys, y, row_h, empty=None, empty_y=None,
                    top=None, bottom=None):
    """Refresh a meter_list that changes while a screen is open, without
    flashing it. Rows are (key, pct, kind, value); when the keys (and so the
    layout) are unchanged the rows are simply redrawn over themselves; only a
    change of rows clears the band from `top` to `bottom` first. `empty` is the
    line shown when there are no rows. Returns the keys drawn, to pass back."""
    keys = tuple(r[0] for r in rows)
    if keys != prev_keys:
        clear_band(display, top, bottom - top)
        if not rows and empty:
            status(display, empty, empty_y, "muted")
    if rows:
        meter_list(display, rows, None, y, row_h)
    return keys


def clear_band(display, y, h):
    """Repaint rows y..y+h with the background, so one region of a screen can
    be redrawn without clearing (and flashing) the whole display."""
    display.fill_rect(0, y, 240, h, _t().bg)


# ── Status ──────────────────────────────────────────────────────────────────

def status(display, s, y, kind="text"):
    """Centred status text coloured by semantic kind, clipped to the bezel.

    kind — one of the theme color tokens: success / warning / danger / accent /
    muted / text.
    """
    color = getattr(_t(), kind, _t().text)
    center_text(display, clip(s, fit_chars(y)), y, color, _t().bg)
