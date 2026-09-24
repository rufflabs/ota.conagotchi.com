"""
Sprite-based animation helper for the GC9A01 display.

Usage
─────
  anim = SpriteAnim(
      frames       = ["img/idle_0.bin", "img/idle_1.bin", "img/idle_2.bin"],
      x=70, y=52, w=100, h=115,
      ms_per_frame = 300,
      frame_ms     = (300, 450, 300),  # optional per-frame timing
      mode         = "pingpong",   # or "loop" / "once"
      pre_composited = True,        # False for magenta-keyed transparent sprites
  )

  # In enter() / resume():
  anim.draw_current(display, bg_path)

  # In update():
  if anim.tick(display, bg_path, time.ticks_ms()):
      if not anim.has_sprites:
          # draw your primitive fallback here, using anim.frame_idx
          pass

Frame files may be raw RGB565 or indexed I8S1 (see tools/convert_image.py).
bg_path is the full 240×240 background file used to erase the previous frame before
drawing the next one.  Pass None if no background file exists.
"""
import time
from image_utils import blit_sprite, blit_sprite_keyed, restore_from_bg, preload_sprites


class SpriteAnim:
    """Cycles through a list of sprite files."""

    def __init__(self, frames, x: int, y: int, w: int, h: int,
                 ms_per_frame: int = 300, mode: str = "pingpong",
                 pre_composited: bool = True, frame_ms=None) -> None:
        self._frames = frames
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self._ms              = ms_per_frame
        self._frame_ms        = tuple(frame_ms or ())
        self._mode            = mode
        self._pre_composited  = pre_composited  # sprites already contain bg pixels
        self._region = None if pre_composited else bytearray(w * h * 2)
        self._idx             = 0
        self._dir             = 1
        self._last_ms         = 0
        self.frame_idx        = 0   # current frame index (read-only for callers)
        self.tick_count       = 0   # total frames advanced since reset
        self.has_sprites      = False   # True after first successful sprite blit
        self.started          = False
        self.cycle_complete   = False  # last frame has received its full duration
        if self._frame_ms and len(self._frame_ms) != len(self._frames):
            raise ValueError("frame_ms must have one duration per frame")

    # ── Public API ────────────────────────────────────────────────────────────

    def draw_current(self, display, bg_path: str = None, bg_fb=None) -> None:
        """Draw the current frame immediately (call from enter / resume)."""
        if not self.started and not self._pre_composited:
            preload_sprites(self._frames)
        self._draw(display, bg_path, bg_fb)
        self._last_ms = time.ticks_ms()
        self.started = True

    def tick(self, display, bg_path: str = None, now: int = None, bg_fb=None) -> bool:
        """
        Advance and draw if the frame interval has elapsed.

        Returns True if the frame advanced (caller should draw fallback if
        not has_sprites).  bg_path is the full-screen background file used
        to restore the sprite region before drawing the next frame; pass None
        if only a solid-colour fallback is available.
        """
        if now is None:
            now = time.ticks_ms()
        if not self.started:
            self.draw_current(display, bg_path, bg_fb)
            return True
        if self._mode == "once" and self.cycle_complete:
            return False
        if time.ticks_diff(now, self._last_ms) < self._current_ms():
            return False
        if self._idx == len(self._frames) - 1:
            self.cycle_complete = True
            if self._mode == "once":
                return False
        # Keep the JSON timeline, rather than adding draw/poll cost to every frame.
        self._last_ms = time.ticks_add(self._last_ms, self._current_ms())
        self._advance()
        self._draw(display, bg_path, bg_fb)
        return True

    def next_frame_ms(self) -> int:
        """Time until the next deadline, for the screen's adaptive wake-up."""
        if not self.started or (self._mode == "once" and self.cycle_complete):
            return 0
        return max(0, self._current_ms() - time.ticks_diff(time.ticks_ms(), self._last_ms))

    def reset(self) -> None:
        """Return to frame 0 and clear the tick counter."""
        self._idx       = 0
        self._dir       = 1
        self.frame_idx  = 0
        self.tick_count = 0
        self._last_ms   = 0
        self.started = False
        self.cycle_complete = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _advance(self) -> None:
        n = len(self._frames)
        if n <= 1:
            self.tick_count += 1
            return
        if self._mode == "loop":
            self._idx = (self._idx + 1) % n
        elif self._mode == "once":
            if self._idx < n - 1:
                self._idx += 1
        else:  # pingpong
            self._idx += self._dir
            if self._idx >= n - 1:
                self._dir = -1
            elif self._idx <= 0:
                self._dir = 1
        self.frame_idx  = self._idx
        self.tick_count += 1

    def _current_ms(self) -> int:
        if self._frame_ms:
            return int(self._frame_ms[self._idx])
        return self._ms

    def _draw(self, display, bg_path: str, bg_fb=None) -> None:
        if self._pre_composited:
            # Sprite already contains the background pixels — blit directly.
            # This avoids the restore→blit flash caused by briefly showing a
            # bare background between frames.  Only restore if the sprite file
            # is missing so the primitive fallback has a clean surface to draw on.
            try:
                blit_sprite(display, self._frames[self._idx],
                            self.x, self.y, self.w, self.h)
                self.has_sprites = True
                return
            except OSError:
                self.has_sprites = False
        else:
            # Color-keyed sprites carry magenta transparent pixels. The keyed
            # blitter restores background pixels only where the sprite is clear.
            try:
                blit_sprite_keyed(display, self._frames[self._idx],
                                  self.x, self.y, self.w, self.h,
                                  bg_path=bg_path, bg_fb=bg_fb, region=self._region)
                self.has_sprites = True
                return
            except OSError:
                self.has_sprites = False

        # Sprite missing — restore background so the primitive fallback has a
        # clean surface (the caller draws the primitive after this returns).
        if bg_path is not None:
            try:
                restore_from_bg(display, bg_path, self.x, self.y, self.w, self.h)
            except OSError:
                pass
