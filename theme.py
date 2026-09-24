"""Centralized, swappable UI theme.

A theme bundles three things, all keyed by *meaning* so the whole badge
restyles from one place:

  colors   — semantic tokens (bg, surface, text, accent, success, …)
  metrics  — layout sizing (bar heights, row spacing, insets)
  style    — chrome switches that change *how* widgets draw, not just their
             color: `chrome` ("bar" filled panels vs "frame" terminal look),
             `select` ("fill" highlight bar vs "marker" `>` cursor)

Because metrics and style are per-theme, a theme can change spacing and the
whole look — e.g. the `terminal` theme uses tight rows, separator-line chrome,
and a `>` cursor for a DOS/console feel.

Runtime-swappable: `available()` lists names, `set_active(name)` switches and
persists to `data/theme.txt`, `get()` returns the live theme.  Colors are
converted to gc9a01 565 values once, when a theme is activated.

Add a theme → add an entry to `_THEMES` (only `colors` is required; `metrics`
and `style` fall back to the base defaults).  Add a color token → add it to
every palette and to `_COLOR_KEYS`.
"""
import os
import gc9a01py as gc9a01

_THEME_FILE = "data/theme.txt"
_DEFAULT = "dark"

# Semantic color tokens every palette must define.
_COLOR_KEYS = (
    "bg",        # screen background
    "surface",   # panels / bars / selection base
    "sel",       # selected-row highlight (fill chrome)
    "text",      # primary text
    "muted",     # secondary / hint text / separators
    "accent",    # emphasis / active marker / cursor
    "success",   # positive status (complete, on)
    "warning",   # in-progress / caution
    "danger",    # negative status (incomplete, destructive)
)

# Layout metrics (px on the 240x240 display).  Per-theme entries override these.
_BASE_METRICS = {
    "title_h":      40,
    "footer_h":     44,
    "row_top":      52,
    "row_h":        22,
    "rows_visible":  5,
    "text_inset":   30,   # keeps outer rows clear of the round bezel
    "row_pad_x":     8,   # selection-highlight horizontal margin
}

# Chrome switches.  Per-theme entries override these.
_BASE_STYLE = {
    "chrome": "bar",     # "bar" = filled title/footer panels; "frame" = lines
    "select": "fill",    # "fill" = highlight bar; "marker" = "> " cursor
}

_THEMES = {
    "dark": {
        "colors": {
            "bg":      ( 10,  13,  20),
            "surface": ( 22,  27,  36),
            "sel":     ( 24, 102, 148),
            "text":    (255, 255, 255),
            "muted":   (145, 155, 170),
            "accent":  ( 90, 160, 240),
            "success": ( 90, 200, 120),
            "warning": (240, 200,  70),
            "danger":  (225,  70,  70),
        },
    },
    "light": {
        "colors": {
            "bg":      (232, 236, 242),
            "surface": (255, 255, 255),
            "sel":     (150, 195, 240),
            "text":    ( 20,  26,  36),
            "muted":   ( 96, 108, 126),
            "accent":  ( 28, 110, 200),
            "success": ( 34, 150,  80),
            "warning": (188, 140,   0),
            "danger":  (200,  50,  50),
        },
    },
    "neon": {
        "colors": {
            "bg":      (  6,   4,  16),
            "surface": ( 26,  10,  46),
            "sel":     (150,  30, 190),
            "text":    (  0, 255, 190),
            "muted":   (140,  90, 190),
            "accent":  (255,   0, 200),
            "success": (  0, 255, 150),
            "warning": (255, 220,   0),
            "danger":  (255,  45,  95),
        },
    },
    # Green-phosphor DOS/terminal look: tight rows, separator-line chrome,
    # a "> " cursor instead of a highlight bar.
    "terminal": {
        "colors": {
            "bg":      (  0,  10,   2),
            "surface": (  0,  24,   8),
            "sel":     (  0,  56,  18),
            "text":    ( 60, 235, 110),
            "muted":   ( 32, 140,  70),
            "accent":  (150, 255, 180),
            "success": ( 70, 245, 120),
            "warning": (240, 220,  60),
            "danger":  (255,  90,  80),
        },
        "metrics": {
            "title_h":      24,
            "footer_h":     22,
            "row_top":      40,
            "row_h":        18,
            "rows_visible":  7,
            "text_inset":   26,
        },
        "style": {
            "chrome": "frame",
            "select": "marker",
        },
    },
}


class Theme:
    """Resolved theme: colors (gc9a01 565 ints), metrics, and style as attrs."""

    def __init__(self, name, spec):
        self.name = name
        colors = spec["colors"]
        for key in _COLOR_KEYS:
            setattr(self, key, gc9a01.color565(*colors[key]))
        metrics = dict(_BASE_METRICS)
        metrics.update(spec.get("metrics", {}))
        for key, val in metrics.items():
            setattr(self, key, val)
        style = dict(_BASE_STYLE)
        style.update(spec.get("style", {}))
        self.chrome = style["chrome"]
        self.select = style["select"]


_active = None


def available():
    """Return the tuple of selectable theme names, in display order."""
    return tuple(_THEMES.keys())


def get():
    """Return the live Theme, loading the persisted choice on first use."""
    if _active is None:
        _load()
    return _active


def name():
    """Return the active theme's name."""
    return get().name


def set_active(theme_name, persist=True):
    """Switch the active theme.  Unknown names fall back to the default."""
    global _active
    if theme_name not in _THEMES:
        theme_name = _DEFAULT
    _active = Theme(theme_name, _THEMES[theme_name])
    if persist:
        _save(theme_name)
    return _active


def cycle(step=1):
    """Switch to the next/previous theme in `available()` order and persist."""
    names = available()
    idx = names.index(get().name) if get().name in names else 0
    return set_active(names[(idx + step) % len(names)])


# ── Persistence ────────────────────────────────────────────────────────────────

def _load():
    chosen = _DEFAULT
    try:
        with open(_THEME_FILE) as f:
            chosen = f.read().strip() or _DEFAULT
    except OSError:
        pass
    set_active(chosen, persist=False)


def _save(theme_name):
    try:
        os.mkdir("data")
    except OSError:
        pass
    with open(_THEME_FILE, "w") as f:
        f.write(theme_name)
