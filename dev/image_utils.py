"""
Image and text rendering helpers for the GC9A01 display.

Images use raw big-endian RGB565; sprites also support indexed I8S1 storage.

Full-screen files: 240 × 240 × 2 = 115,200 bytes.
Raw sprite files: w × h × 2 bytes (dimensions are known to the caller).
I8S1 sprites: a 10-byte header, RGB565 palette, and w*h byte-sized indices.
Indexed sprites decode before playback and are cached as RGB565 in RAM.

Text rendering piggybacks on MicroPython's framebuf built-in 8×8 font, then
overlays compact OpenDyslexic-style badge glyphs where available. The byte-swap
reconciles framebuf's little-endian storage with the driver's big-endian SPI writes.
"""
import gc
import framebuf
from indexed_sprite import MAGIC as _INDEXED_MAGIC, decode as _decode_indexed

try:
    from open_dyslexic_badge8 import GLYPHS as _OD_GLYPHS
except ImportError:
    _OD_GLYPHS = {}


_FULL_W = 240
_TEXT_W = 8
_TEXT_H = 8

def blit_image(display, path: str) -> None:
    """Stream a raw RGB565 .bin file to the full 240×240 display."""
    try:
        with open(path, "rb") as f:
            buf = f.read()
        display.blit_buffer(buf, 0, 0, _FULL_W, _FULL_W)
        del buf
    except MemoryError:
        # Row-at-a-time fallback if the heap is under pressure.
        with open(path, "rb") as f:
            row_buf = bytearray(_FULL_W * 2)
            for row in range(_FULL_W):
                n = f.readinto(row_buf)
                if not n:
                    break
                display.blit_buffer(row_buf, 0, row, _FULL_W, 1)
    gc.collect()


def blit_sprite(display, path: str, x: int, y: int, w: int, h: int) -> None:
    """
    Blit a small sprite from a raw RGB565 .bin file at position (x, y).

    The file must contain exactly w × h × 2 bytes — no header.
    Raises OSError if the file does not exist (caller can catch to use fallback).
    """
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] == _INDEXED_MAGIC:
        buf = _decode_indexed(buf)
    display.blit_buffer(buf, x, y, w, h)


# Runtime transparency color key: RGB565 magenta, stored big-endian (bytes
# 0xF8, 0x1F) in the .bin files and expected big-endian by the driver. framebuf
# interprets a buffer as little-endian, so the value it must be told to treat as
# transparent is the byte-swapped magenta, 0x1FF8. _swap16() converts any
# big-endian RGB565 value to the little-endian value framebuf uses.
_KEY_BE = 0xF81F


def _swap16(v: int) -> int:
    return ((v & 0xFF) << 8) | (v >> 8)


_KEY_LE = _swap16(_KEY_BE)   # 0x1FF8 — what framebuf sees for a magenta pixel


# Small immutable sprite files are cached by path: opening a file on the FAT
# flash costs ~27 ms, but the blit itself is <1 ms, so re-reading a button sprite
# on every redraw dominates. Cached bytes are read-only (used only as a blit
# source), so sharing them is safe. Bounded to avoid unbounded growth; cleared by
# clear_sprite_cache() (e.g. after an OTA update replaces sprite files).
_sprite_cache = {}
_SPRITE_CACHE_MAX = 64


def _load_sprite(path: str) -> bytearray:
    b = _sprite_cache.get(path)
    if b is None:
        with open(path, "rb") as f:      # raises OSError if absent (not cached)
            b = bytearray(f.read())
        if b[:4] == _INDEXED_MAGIC:
            b = _decode_indexed(b)
        if len(_sprite_cache) >= _SPRITE_CACHE_MAX:
            _sprite_cache.clear()
        _sprite_cache[path] = b
    return b


def clear_sprite_cache() -> None:
    _sprite_cache.clear()


def preload_sprites(paths) -> None:
    """Read a sequence before its clock starts, avoiding mid-animation I/O."""
    for path in paths:
        try:
            _load_sprite(path)
        except OSError:
            pass  # SpriteAnim owns the missing-art fallback.
    gc.collect()


def load_bg_framebuf(bg_path: str):
    """Load a full 240×240 RGB565 background file into a framebuf held in RAM.

    Returns (FrameBuffer, buffer) — the caller keeps both (the buffer is what you
    hand to display.blit_buffer to paint it; the FrameBuffer is what you pass to
    blit_sprite_keyed(bg_fb=…) so button transparency composites from RAM instead
    of re-reading the file per button). Returns (None, None) if the file is
    absent. On the badge the 115 KB buffer lands in PSRAM. Raises MemoryError if
    RAM is exhausted (caller can fall back to the streaming file path).
    """
    try:
        with open(bg_path, "rb") as f:
            buf = bytearray(f.read())
    except OSError:
        return None, None
    return framebuf.FrameBuffer(buf, _FULL_W, _FULL_W, framebuf.RGB565), buf


def blit_sprite_keyed(display, sprite_path: str, x: int, y: int, w: int, h: int,
                      bg_path: str = None, bg_color: int = 0x0000,
                      bg_fb=None, region=None) -> None:
    """
    Blit a color-keyed sprite at (x, y), letting the background show through.

    The sprite file is raw w×h RGB565 (no header). Pixels equal to the key color
    (magenta 0xF81F) are transparent: the underlying background is kept there.
    The background, in priority order, is:
      • bg_fb   — a full-screen framebuf (from load_bg_framebuf); the region is
                  extracted from RAM. FASTEST — use this when drawing many
                  buttons over one background.
      • bg_path — a full 240×240 RGB565 file, read only in the sprite's region.
      • bg_color — a solid fill, when neither of the above is given.

    Compositing uses framebuf's C-speed keyed blit. Peak allocation is the sprite
    (w×h×2) plus the region (w×h×2). Buffers hold big-endian bytes; framebuf
    treats them as little-endian, which is fine because non-key pixels are copied
    byte-for-byte and the key is byte-swapped to match (_KEY_LE).

    Raises OSError if the sprite file does not exist (caller can fall back).
    """
    sprite = _load_sprite(sprite_path)   # cached; ~27 ms file read only once

    if region is None:
        region = bytearray(w * h * 2)
    dst = framebuf.FrameBuffer(region, w, h, framebuf.RGB565)
    if bg_fb is not None:
        dst.blit(bg_fb, -x, -y)       # extract the (x,y,w,h) window from RAM
    elif bg_path is not None:
        mv = memoryview(region)
        row_bytes = w * 2
        with open(bg_path, "rb") as bf:
            for r in range(h):
                bf.seek(((y + r) * _FULL_W + x) * 2)
                bf.readinto(mv[r * row_bytes:(r + 1) * row_bytes])
    else:
        dst.fill(_swap16(bg_color))   # framebuf stores LE; swap so bytes are BE

    src = framebuf.FrameBuffer(sprite, w, h, framebuf.RGB565)
    dst.blit(src, 0, 0, _KEY_LE)
    display.blit_buffer(region, x, y, w, h)


def restore_from_bg(display, bg_path: str, x: int, y: int, w: int, h: int) -> None:
    """
    Re-blit a rectangular region from a full 240×240 background file.

    Seeks to each row's offset so only w×2 bytes are allocated at once — no need
    to load the full background into RAM.  Used to "undo" a sprite drawn over a bg.
    """
    row_buf = bytearray(w * 2)
    with open(bg_path, "rb") as f:
        for row in range(h):
            f.seek(((y + row) * _FULL_W + x) * 2)
            f.readinto(row_buf)
            display.blit_buffer(row_buf, x, y + row, w, 1)


def draw_text(display, text: str, x: int, y: int,
              fg: int = 0xFFFF, bg: int = 0x0000) -> None:
    """
    Draw a string using fixed 8×8 text cells.

    fg / bg are RGB565 big-endian values (same encoding as gc9a01py constants).
    Characters are 8 px wide × 8 px tall.
    """
    w = len(text) * _TEXT_W
    if w <= 0:
        return
    buf = bytearray(w * _TEXT_H * 2)
    fb = framebuf.FrameBuffer(buf, w, _TEXT_H, framebuf.RGB565)
    # framebuf uses little-endian storage; swap bytes so gc9a01 sees correct colours.
    fg_le = ((fg & 0xFF) << 8) | (fg >> 8)
    bg_le = ((bg & 0xFF) << 8) | (bg >> 8)
    fb.fill(bg_le)
    fb.text(text, 0, 0, fg_le)
    _ground_lower_strokes(buf, w, fg, bg)
    _draw_open_dyslexic_glyphs(buf, text, w, fg, bg)
    display.blit_buffer(buf, x, y, w, _TEXT_H)


def _ground_lower_strokes(buf, width: int, fg: int, bg: int) -> None:
    fg_hi = (fg >> 8) & 0xFF
    fg_lo = fg & 0xFF
    bg_hi = (bg >> 8) & 0xFF
    bg_lo = bg & 0xFF
    for y in range(_TEXT_H - 2, 3, -1):
        for x in range(width):
            if _is_pixel(buf, width, x, y, fg_hi, fg_lo):
                if _is_pixel(buf, width, x, y + 1, bg_hi, bg_lo):
                    _put_pixel(buf, width, x, y + 1, fg_hi, fg_lo)


def _draw_open_dyslexic_glyphs(buf, text: str, width: int, fg: int, bg: int) -> None:
    fg_hi = (fg >> 8) & 0xFF
    fg_lo = fg & 0xFF
    bg_hi = (bg >> 8) & 0xFF
    bg_lo = bg & 0xFF
    for char_idx, ch in enumerate(text):
        glyph = _OD_GLYPHS.get(ch)
        if glyph is None:
            continue
        base_x = char_idx * _TEXT_W
        for gy, row in enumerate(glyph):
            for gx in range(_TEXT_W):
                if row & (0x80 >> gx):
                    _put_pixel(buf, width, base_x + gx, gy, fg_hi, fg_lo)
                else:
                    _put_pixel(buf, width, base_x + gx, gy, bg_hi, bg_lo)


def _is_pixel(buf, width: int, x: int, y: int, hi: int, lo: int) -> bool:
    idx = ((y * width) + x) * 2
    return buf[idx] == hi and buf[idx + 1] == lo


def _put_pixel(buf, width: int, x: int, y: int, hi: int, lo: int) -> None:
    idx = ((y * width) + x) * 2
    buf[idx] = hi
    buf[idx + 1] = lo
