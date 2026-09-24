"""Main Conagotchi idle / pet screen.

Layout (240×240 round display, centre 120,120, radius 120)
───────────────────────────────────────────────────────────
  Background   img/{character}/background.bin  (full 240×240) or solid colour fallback
  Character    img/{character}/character.bin   sprite at the character bounding box

Ring menu
─────────
  Menu items sit at fixed positions around the circle edge, always visible.
  Items are ordered clockwise from 12 o'clock so LEFT/RIGHT feel natural:

      top (12) → right (2) → bottom-right (4) → bottom (6)
               → bottom-left (8) → left (10) → …

  LEFT / RIGHT   — move selection around the ring
  START          — activate selected item:
                     "screen:X"  →  mgr.push() the matching sub-menu screen
  SELECT         — go back (noop at root; submenus call mgr.pop() themselves)

  Each item has three sprite states (optional; primitive fallback when absent):
    img/btn_{id}_unsel.bin   unselected
    img/btn_{id}_sel.bin     selected / highlighted
    img/btn_{id}_press.bin   pressed (shown for _PRESS_MS before activation)

  The ring redraws only on button presses; it persists over the character
  animation because animation ticks only touch the character bounding box.

Challenge overlay
─────────────────
  An active inline challenge (set via challenge_manager) runs alongside the pet.
  While a challenge is active it owns ALL button input.  Returning a truthy
  value from on_button() signals the challenge wants to exit.
  SELECT is always passed to the challenge so it can implement its own back action.

Character animation
───────────────────
  Animation state mirrors pet.action ("idle", "eating", "drinking", …).
  Each state maps to a frame list in the Character class; unknown states fall
  back to the idle frame list.  A primitive fallback is drawn when no sprite
  files exist.

TODO: action menu on START for feed / drink / play / sleep
TODO: periodic pet state saves
"""
import time
import gc9a01py as gc9a01
from screen_manager import Screen
from image_utils import (blit_image, blit_sprite, blit_sprite_keyed,
                         load_bg_framebuf, restore_from_bg, draw_text)
from anim import SpriteAnim
from buttons import SELECT, START, LEFT, RIGHT
from pet_state import MAX_LEVEL, PetState
from leds import hue_to_rgb

# ── Ring menu button table ────────────────────────────────────────────────────
# Columns: id | x | y | w | h | label | action
#
#   id      — sprite filename stem: img/btn_{id}_{state}.bin
#   x, y    — top-left pixel in 240×240 display space
#   w, h    — pixel dimensions (must match sprite files)
#   label   — primitive fallback text
#   action  — pet action id  OR  "screen:<id>" to push a sub-menu screen
#
# Items are ordered clockwise from the default Pet selection.
# Artist asset markers (btn_paw, btn_controller, etc.) map to these menu ids in
# assets/menu_buttons/menu_button_map.json.
_MB_ID     = 0
_MB_X      = 1
_MB_Y      = 2
_MB_W      = 3
_MB_H      = 4
_MB_LABEL  = 5
_MB_ACTION = 6

_MENU_BTNS = (
    #  id             x    y    w    h   label    action
    # Top-level navigation only. Care actions live under the Pet menu.
    ("pet",          161,  20,  44,  44, "Pet",   "screen:pet"),         # btn_paw
    ("ozconbase",    159, 174,  44,  44, "Base",  "screen:ozconbase"),   # btn_bag
    ("settings",      38, 176,  44,  44, "Set",   "screen:settings"),    # btn_gear
    ("games",         37,  20,  44,  44, "Games", "screen:games"),       # btn_controller
    ("challenges",    99,   0,  44,  44, "Chal",  "screen:challenges"),  # btn_laptop
)

# Extra ring button shown only when Vendor Badge mode is enabled
# (Settings -> Debug -> Vendor Mode). Slotted into the gap between Settings
# (~10–11 o'clock) and Pet (12 o'clock) so the clockwise cycle flows
# settings -> vendor -> pet.
_VENDOR_BTN = ("vendor", 56, 23, 48, 16, "Ven", "screen:vendor")

_PRESS_MS  = 150   # ms to show pressed state before activating
_CHALLENGE_CHECK_MS = 1500   # how often to re-check challenge completion

# Primitive button colours (used when sprite files are absent)
_COL_UNSEL = gc9a01.color565( 50,  50,  70)
_COL_SEL   = gc9a01.color565( 30,  80, 160)
_COL_PRESS = gc9a01.color565(220, 180,  40)

_BOB = (0, 1, 2, 1)   # breathing bob offsets for primitive character fallback

# ── LED layout (adjust indices to match physical wiring) ─────────────────────
_LEFT_LEDS   = (3, 2, 1, 0)   # bottom→top, left side
_RIGHT_LEDS  = (4, 5, 6, 7)   # bottom→top, right side
_CHASE_ORDER = _LEFT_LEDS + _RIGHT_LEDS

_LED_BRIGHTNESS = 0.04   # 0.0-1.0; scale all RGB output

def _dim(color: tuple) -> tuple:
    b = _LED_BRIGHTNESS
    return (int(color[0] * b), int(color[1] * b), int(color[2] * b))

_LEDA_NORMAL  = 0
_LEDA_LEVELUP = 1
_LEDA_L5_RAIN = 2

# Right-side progress color indexed by number of lit LEDs (0–4)
_PROG_COLORS = (
    (  0,   0,   0),   # 0 — off
    (255,   0,   0),   # 1 — red
    (255, 200,   0),   # 2 — yellow
    (  0, 220,   0),   # 3 — green
    (  0, 220,   0),   # 4 — green (100% triggers level-up celebration)
)
_XP_LED_STEP = 0.20

_LU_WASH_MS  = 1000   # rainbow wash phase duration
_LU_CHASE_MS = 1000   # color chase phase duration (125 ms/LED × 8)


# ── Screen class ──────────────────────────────────────────────────────────────

class ConagotchiScreen(Screen):

    def __init__(self) -> None:
        import character_manager

        char = character_manager.get_active()

        self._char        = char
        self._bg_path     = char.bg_path()
        self._bg_color    = gc9a01.color565(*char.bg_color)
        self._blink_every = char.blink_every
        self._prim = (
            gc9a01.color565(*char.prim_body),
            gc9a01.color565(*char.prim_eye),
            gc9a01.color565(*char.prim_shine),
            gc9a01.color565(*char.prim_smile),
            gc9a01.color565(*char.prim_cheek),
        )

        self._anims      = {}   # state -> SpriteAnim, created lazily
        self._anim_state = "idle"
        self._reaction = None
        self._pending_reaction = None
        self._was_resource_low = False

        self._pet        = PetState(char)
        self._challenge_ms   = 0   # last challenge auto-check time (ticks_ms)

        self._has_bg         = False
        self._bg_fb          = None   # full-screen bg framebuf for keyed buttons
        self._menu           = self._build_menu()
        self._menu_sel       = 0
        self._pressing       = False
        self._press_at       = 0
        self._last_ms        = 0
        self._led_state      = (-1, -1)   # (level, lit_right) — forces redraw on enter
        self._prev_level     = self._pet.level   # set after load; prevents boot animation
        self._led_anim       = _LEDA_L5_RAIN if self._pet.level >= 5 else _LEDA_NORMAL
        self._led_anim_start = 0
        self._alert_on       = None   # red Alert LED cache; None forces a write

    async def enter(self, display, leds, mgr) -> None:
        self._has_bg, self._bg_fb = _load_bg(display, self._bg_path, self._bg_color)
        # Rebuild the ring in case Vendor Mode was toggled in Settings.
        self._menu     = self._build_menu()
        if self._menu_sel >= len(self._menu):
            self._menu_sel = 0
        self._pressing = False
        self._last_ms  = time.ticks_ms()
        # Force a full LED redraw: a pushed screen (e.g. the Settings LED test)
        # may have driven the strip directly, so the cached state is stale.
        self._led_state = (-1, -1)
        self._alert_on  = None   # a pushed screen may have toggled the Alert LED
        # Import/check challenge metadata before the first animation clock starts.
        if self._pet.is_idle():
            self._check_challenges(time.ticks_ms(), self._pet)
        anim = self._sync_anim()
        anim.reset()
        anim.draw_current(display, self._bg_path if self._has_bg else None, self._bg_fb)
        if not anim.has_sprites:
            _draw_char_primitive(display, anim.x, anim.y,
                                 frame=0, blink=False, prim=self._prim)
        self._draw_ring(display)
        self._update_leds(leds, self._last_ms)
        self._update_alert(leds)
        self._sync_max_level_splash()

    async def update(self, display, leds, mgr) -> None:
        now = time.ticks_ms()
        dt  = time.ticks_diff(now, self._last_ms)
        self._last_ms = now
        bg  = self._bg_path if self._has_bg else None

        # ── Game state ────────────────────────────────────────────────────────
        anim = self._sync_anim()
        action_complete = True
        if (self._pet.action in self._char.action_durations
                and self._char.state_frames(self._pet.action)):
            # Rendering and menu redraws can outlast the nominal action timer.
            action_complete = (anim.cycle_complete
                               or (anim.started and not anim.has_sprites))
        self._pet.tick(dt, action_complete=action_complete)
        if self._pet.level > self._prev_level:
            self._prev_level = self._pet.level
            self._trigger_levelup(now)
        self._update_leds(leds, now)
        self._update_alert(leds)

        # ── Deferred press → activation ───────────────────────────────────────
        if self._pressing:
            if time.ticks_diff(now, self._press_at) >= _PRESS_MS:
                self._pressing = False
                self._do_activate(display, mgr)
            return

        # ── Character animation ───────────────────────────────────────────────
        anim = self._sync_anim()
        advanced = anim.tick(display, bg, time.ticks_ms(), self._bg_fb)
        if advanced:
            if not anim.has_sprites:
                f     = anim.frame_idx
                tc    = anim.tick_count
                blink = (f == 3) or (tc % self._blink_every == 0)
                if not self._has_bg:
                    display.fill_rect(anim.x, anim.y, anim.w, anim.h, self._bg_color)
                _draw_char_primitive(display, anim.x, anim.y, f, blink, self._prim)
            if self._pet.is_idle() and self._anim_state == "idle":
                self._check_challenges(time.ticks_ms(), self._pet)

    def next_update_ms(self) -> int:
        anim = self._anims.get(self._anim_state)
        if anim and anim.cycle_complete and not self._pet.is_idle():
            return 0
        return min(33, anim.next_frame_ms()) if anim else 33

    def handle_button(self, btn: str, mgr) -> None:
        if self._pressing:
            return

        if btn == LEFT:
            self._nav_ring(mgr._display, -1)
        elif btn == RIGHT:
            self._nav_ring(mgr._display, +1)
        elif btn == START:
            _draw_btn(mgr._display, self._menu[self._menu_sel], "press")
            self._pressing = True
            self._press_at = time.ticks_ms()
        elif btn == SELECT:
            pass  # root screen — submenus handle SELECT → mgr.pop() themselves

    # ── Challenge auto-tracking ─────────────────────────────────────────────────────

    def _check_challenges(self, now: int, pet) -> None:
        """Mark any satisfied challenge complete and apply its reward.

        Every challenge belonging to an unlocked character is tracked automatically
        (there is no per-challenge activation).  Throttled to keep the filesystem /
        network reads out of the animation hot path.  A reward that raises the
        level is picked up by the level-up check on the next tick.
        """
        if time.ticks_diff(now, self._challenge_ms) < _CHALLENGE_CHECK_MS:
            return
        self._challenge_ms = now
        import character_manager
        import challenge_manager
        from challenges import CHALLENGES

        completed = challenge_manager.get_completed()
        unlocked = {char.id for char in character_manager.get_unlocked()}
        for cls in CHALLENGES:
            if cls.id in completed:
                continue
            char = cls.character
            if char and char not in unlocked:
                continue
            try:
                met = cls.is_met()
            except Exception:
                met = False
            if met:
                cls().on_complete(pet)
                challenge_manager.mark_complete(cls.id)

    # ── LED helpers ───────────────────────────────────────────────────────────

    def _update_alert(self, leds) -> None:
        """Light the red Alert LED while any care resource is low, clearing it
        only once every resource is back above the threshold. Cached so the GPIO
        is written only on a change."""
        low = self._pet.any_resource_low()
        if low and not self._was_resource_low:
            self._queue_reaction("sad")
        self._was_resource_low = low
        if low != self._alert_on:
            self._alert_on = low
            leds.set_alert(low)

    def _trigger_levelup(self, now: int) -> None:
        self._led_anim       = _LEDA_LEVELUP
        self._led_anim_start = now
        self._queue_reaction("cheer")

    def refresh_leds(self, leds, now: int = None) -> None:
        """Re-evaluate the LED display for the current pet state and render it
        immediately, playing the level-up animation if the level rose since the
        last refresh. Safe to call from another screen (e.g. the debug XP/Level
        editors) so LED feedback appears the moment a value is saved, instead of
        only after returning to the pet screen. Drive the animation afterward by
        ticking `_update_leds` each frame."""
        if now is None:
            now = time.ticks_ms()
        lvl = self._pet.level
        if lvl > self._prev_level:
            self._trigger_levelup(now)
        elif self._led_anim != _LEDA_LEVELUP:
            self._led_anim  = _LEDA_L5_RAIN if lvl >= 5 else _LEDA_NORMAL
            self._led_state = (-1, -1)   # force a fresh normal/L5 render
        self._prev_level = lvl
        self._sync_max_level_splash()
        self._update_leds(leds, now)

    def _sync_max_level_splash(self) -> None:
        """When the pet is at max level, switch the boot splash to the special
        screen. Idempotent (splash_manager only writes on change), so it's safe
        to call from enter and on every LED refresh."""
        if self._pet.level < MAX_LEVEL:
            return
        try:
            import splash_manager
            splash_manager.mark_max_level()
        except Exception:
            pass

    def _update_leds(self, leds, now: int) -> None:
        if self._led_anim == _LEDA_LEVELUP:
            elapsed = time.ticks_diff(now, self._led_anim_start)
            if elapsed >= _LU_WASH_MS + _LU_CHASE_MS:
                self._led_anim  = _LEDA_L5_RAIN if self._pet.level >= 5 else _LEDA_NORMAL
                self._led_state = (-1, -1)   # force normal redraw on next tick
            else:
                self._anim_levelup(leds, elapsed)
        elif self._led_anim == _LEDA_L5_RAIN:
            self._anim_l5_rainbow(leds, now)
        else:
            self._show_normal_leds(leds)

    def _show_normal_leds(self, leds) -> None:
        lit_right = _xp_led_count(self._pet.xp_progress())
        state     = (self._pet.level, lit_right)
        if state == self._led_state:
            return
        self._led_state = state
        char_color = self._pet.level_color
        lit_left   = min(self._pet.level, len(_LEFT_LEDS))
        for i, idx in enumerate(_LEFT_LEDS):
            leds.rgb[idx] = _dim(char_color) if i < lit_left else (0, 0, 0)
        prog_color = _PROG_COLORS[lit_right]
        for i, idx in enumerate(_RIGHT_LEDS):
            leds.rgb[idx] = _dim(prog_color) if i < lit_right else (0, 0, 0)
        leds.rgb.write()

    def _anim_levelup(self, leds, elapsed: int) -> None:
        if elapsed < _LU_WASH_MS:
            hue_base = elapsed / _LU_WASH_MS
            for i, idx in enumerate(_CHASE_ORDER):
                leds.rgb[idx] = _dim(hue_to_rgb((hue_base + i / 8.0) % 1.0))
        else:
            chase_elapsed = elapsed - _LU_WASH_MS
            step = min(chase_elapsed * len(_CHASE_ORDER) // _LU_CHASE_MS,
                       len(_CHASE_ORDER) - 1)
            for i, idx in enumerate(_CHASE_ORDER):
                leds.rgb[idx] = _dim(hue_to_rgb(i / 8.0)) if i == step else (0, 0, 0)
        leds.rgb.write()

    def _anim_l5_rainbow(self, leds, now: int) -> None:
        hue_base = (now % 2000) / 2000.0
        for i, idx in enumerate(_CHASE_ORDER):
            leds.rgb[idx] = _dim(hue_to_rgb((hue_base + i / 8.0) % 1.0))
        leds.rgb.write()

    # ── Ring helpers ──────────────────────────────────────────────────────────

    def _build_menu(self):
        """Ring items for this badge, with Vendor appended in vendor mode."""
        menu = []
        for b in _MENU_BTNS:
            menu.append(b)
        try:
            from settings_state import BadgeSettings
            if BadgeSettings().vendor_mode_enabled:
                menu.append(_VENDOR_BTN)
        except Exception:
            pass
        return tuple(menu)

    def _btn_bg(self):
        """(bg_fb, bg_path, bg_color) for color-keyed ring buttons. bg_fb (a
        RAM framebuf) is the fast path; bg_path is the file fallback; bg_color is
        the solid fallback."""
        return (self._bg_fb,
                self._bg_path if self._has_bg else None,
                self._bg_color)

    def _nav_ring(self, display, direction: int) -> None:
        prev = self._menu_sel
        self._menu_sel = (self._menu_sel + direction) % len(self._menu)
        bg = self._btn_bg()
        _draw_btn(display, self._menu[prev], "unsel", *bg)
        _draw_btn(display, self._menu[self._menu_sel], "sel", *bg)

    def _draw_ring(self, display) -> None:
        """Draw all ring items; called on enter/resume."""
        bg = self._btn_bg()
        for i, b in enumerate(self._menu):
            _draw_btn(display, b, "sel" if i == self._menu_sel else "unsel", *bg)

    # ── Activation ────────────────────────────────────────────────────────────

    def _do_activate(self, display, mgr) -> None:
        btn    = self._menu[self._menu_sel]
        action = btn[_MB_ACTION]
        _draw_btn(display, btn, "sel", *self._btn_bg())   # restore highlight after press

        if action.startswith("screen:"):
            screen_id = action[7:]
            if screen_id == "challenges":
                from screens.challenge_menu import ChallengeMenuScreen
                mgr.push(ChallengeMenuScreen())
            elif screen_id == "pet":
                from screens.pet_menu import PetMenuScreen
                mgr.push(PetMenuScreen(self._pet))
            elif screen_id == "games":
                from screens.games_menu import GamesMenuScreen
                mgr.push(GamesMenuScreen())
            elif screen_id == "ozconbase":
                from screens.ozconbase import OzConBaseScreen
                mgr.push(OzConBaseScreen())
            elif screen_id == "settings":
                from screens.settings import SettingsScreen
                mgr.push(SettingsScreen())
            elif screen_id == "vendor":
                from screens.vendor import VendorScreen
                mgr.push(VendorScreen())
        else:
            self._pet.begin_action(action)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _queue_reaction(self, state: str) -> None:
        if self._char.state_frames(state):
            if self._pending_reaction != "cheer":
                self._pending_reaction = state

    def _sync_anim(self) -> SpriteAnim:
        """Return the SpriteAnim for the current pet action, creating/resetting as needed."""
        state = self._pet.action
        if state == "idle":
            if self._reaction is not None:
                reaction = self._anims.get(self._reaction)
                if reaction and (reaction.cycle_complete
                                 or (reaction.started and not reaction.has_sprites)):
                    self._reaction = None
            if self._reaction is None and self._pending_reaction is not None:
                self._reaction = self._pending_reaction
                self._pending_reaction = None
                if self._reaction in self._anims:
                    self._anims[self._reaction].reset()
            state = self._reaction or state
        if state not in self._anims:
            anim_state = state
            frames = self._char.state_frames(anim_state)
            if not frames:
                anim_state = "idle"
                frames = self._char.state_frames(anim_state)
            self._anims[state] = SpriteAnim(
                frames,
                x=self._char.char_x, y=self._char.char_y,
                w=self._char.char_w, h=self._char.char_h,
                ms_per_frame=self._char.anim_ms,
                mode=self._char.state_mode(anim_state),
                frame_ms=self._char.state_frame_durations(anim_state),
                pre_composited=self._char.state_uses_precomposited(anim_state),
            )
        if state != self._anim_state:
            self._anim_state = state
            self._anims[state].reset()
        return self._anims[state]


# ── Ring drawing helpers ──────────────────────────────────────────────────────

def _draw_btn(display, b, state: str, bg_fb=None, bg_path=None,
              bg_color: int = 0x0000) -> None:
    """Blit sprite for a ring button tuple; primitive fallback when the sprite
    file is absent.

    Sprites are drawn color-keyed (magenta = transparent) over the character
    background so button art can be non-rectangular and the background shows
    through. Opaque sprites (no magenta) render identically through this path.
    bg_fb (RAM framebuf) / bg_path / bg_color supply what shows through the
    transparent pixels, fastest first."""
    try:
        blit_sprite_keyed(display, "img/btn_{0}_{1}.bin".format(b[_MB_ID], state),
                          b[_MB_X], b[_MB_Y], b[_MB_W], b[_MB_H],
                          bg_path=bg_path, bg_color=bg_color, bg_fb=bg_fb)
    except OSError:
        color = _COL_SEL if state == "sel" else (_COL_PRESS if state == "press" else _COL_UNSEL)
        display.fill_rect(b[_MB_X], b[_MB_Y], b[_MB_W], b[_MB_H], color)
        lx = b[_MB_X] + (b[_MB_W] - len(b[_MB_LABEL]) * 8) // 2
        ly = b[_MB_Y] + (b[_MB_H] - 8) // 2
        draw_text(display, b[_MB_LABEL], lx, ly, gc9a01.WHITE, color)


def _xp_led_count(progress: float) -> int:
    """Light EXP LEDs at 20%, 40%, 60%, and 80% toward next level."""
    lit = int((max(0.0, min(1.0, progress)) + 0.000001) / _XP_LED_STEP)
    return min(lit, len(_RIGHT_LEDS))


# ── Background loading ────────────────────────────────────────────────────────

def _load_bg(display, bg_path: str, bg_color: int):
    """Paint the character background and return (has_bg, bg_fb).

    bg_fb is a full-screen framebuf kept in RAM (PSRAM) so ring buttons can
    composite their transparent art from RAM instead of re-reading the file per
    button. Falls back to a streaming paint (bg_fb=None) if RAM is tight, or a
    solid fill if the file is missing."""
    try:
        fb, buf = load_bg_framebuf(bg_path)
    except MemoryError:
        fb = None
    if fb is not None:
        display.blit_buffer(buf, 0, 0, 240, 240)
        return True, fb
    # No framebuf (missing file or low heap): stream to the display, else fill.
    try:
        blit_image(display, bg_path)
        return True, None
    except OSError:
        display.fill(bg_color)
        return False, None


# ── Primitive character fallback ──────────────────────────────────────────────

def _draw_char_primitive(display, bx: int, by: int, frame: int,
                         blink: bool, prim: tuple) -> None:
    """Fallback character drawn with fill_rects when sprite files are absent.
    Fits within the 80×80 bounding box.  frame 0-3: breathing bob.  blink: eyes closed."""
    col_body, col_eye, col_shine, col_smile, col_cheek = prim
    bob = _BOB[frame % 4]
    ox  = bx
    oy  = by + bob

    # Body (egg shape)
    display.fill_rect(ox + 22, oy +  6, 36, 56, col_body)
    display.fill_rect(ox + 16, oy + 14, 48, 40, col_body)
    display.fill_rect(ox + 19, oy +  9, 42, 50, col_body)

    # Eyes
    eye_y = oy + 20
    if blink:
        display.fill_rect(ox + 22, eye_y + 4, 12, 3, col_eye)
        display.fill_rect(ox + 46, eye_y + 4, 12, 3, col_eye)
    else:
        display.fill_rect(ox + 22, eye_y,     12, 11, col_eye)
        display.fill_rect(ox + 46, eye_y,     12, 11, col_eye)
        display.fill_rect(ox + 24, eye_y + 2,  4,  4, col_shine)
        display.fill_rect(ox + 48, eye_y + 2,  4,  4, col_shine)

    # Cheeks
    display.fill_rect(ox + 14, oy + 33, 10, 5, col_cheek)
    display.fill_rect(ox + 56, oy + 33, 10, 5, col_cheek)

    # Smile
    display.fill_rect(ox + 26, oy + 40,  3, 3, col_smile)
    display.fill_rect(ox + 29, oy + 42, 10, 3, col_smile)
    display.fill_rect(ox + 39, oy + 40,  3, 3, col_smile)

    # Feet
    display.fill_rect(ox + 20, oy + 60, 16, 10, col_body)
    display.fill_rect(ox + 44, oy + 60, 16, 10, col_body)
