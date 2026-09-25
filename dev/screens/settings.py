"""Badge settings submenu screen."""
import time

import gc9a01py as gc9a01

import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from config import NUM_RGB_LEDS, WIFI_PASSWORD, WIFI_SSID
from image_utils import draw_text
from pet_state import MAX_EXPERIENCE, MAX_LEVEL, PetState
from screen_manager import Screen
from settings_state import (
    BadgeSettings,
    check_connectivity,
    connect_saved_wifi,
    scan_wifi_networks,
    set_wifi_enabled,
)


# Defaults; refreshed from the active theme by _sync_theme() before each draw.
_BG = gc9a01.color565(10, 13, 20)
_PANEL = gc9a01.color565(22, 27, 36)
_SEL = gc9a01.color565(28, 98, 132)
_WARN = gc9a01.color565(170, 58, 48)
_TEXT = gc9a01.WHITE
_MUTED = gc9a01.color565(145, 155, 170)
_OK = gc9a01.color565(80, 210, 120)
_OFF = gc9a01.color565(215, 95, 80)


def _sync_theme() -> None:
    """Pull this screen's palette from the active theme (colors only; the
    Settings layout keeps its own bespoke chrome for now)."""
    global _BG, _PANEL, _SEL, _WARN, _TEXT, _MUTED, _OK, _OFF
    import theme
    t = theme.get()
    _BG, _PANEL, _SEL, _WARN = t.bg, t.surface, t.sel, t.warning
    _TEXT, _MUTED, _OK, _OFF = t.text, t.muted, t.success, t.danger

_VIEW_MENU = "menu"
_VIEW_WIFI = "wifi"
_VIEW_WIFI_SCAN = "wifi_scan"
_VIEW_TEXT = "text"
_VIEW_CREDITS = "credits"
_VIEW_DEBUG = "debug"
_VIEW_BUTTONS = "buttons"          # duration picker
_VIEW_BUTTON_LIVE = "button_live"  # live per-button test
_VIEW_LEDS = "leds"
_VIEW_LEVEL = "level"
_VIEW_EXP = "exp"
_VIEW_RESOURCES = "resources"
_VIEW_CHARACTER = "character"
_VIEW_SPLASH = "splash"
_VIEW_RESET = "reset"

_DEBUG_UNLOCK_PRESSES = 5   # BOOT presses in Credits to unlock the Debug menu
_FLASH_MS = 900             # how long the "DEBUG" unlock flash stays on screen

_DBG_ENABLE = 0
_DBG_BUTTONS = 1
_DBG_LEDS = 2
_DBG_LEVEL = 3
_DBG_EXP = 4
_DBG_RESOURCES = 5
_DBG_CHARACTER = 6
_DBG_VENDOR = 7
_DBG_SPLASH = 8
_DBG_BLUETOOTH = 9
_DBG_FPS = 10
_DBG_OTA_CHANNEL = 11
_DBG_COUNT = 12
_DBG_ROW_Y0 = 40
_DBG_ROW_DY = 22   # tight enough that the last row clears the status bar (y=170)

_EXP_STEP = 100
_REDRAW_MS = 180
_WIFI_RADIO = 0
_WIFI_SCAN = 1
_WIFI_CONNECT = 2
_WIFI_CHECK = 3
_WIFI_SSID = 4
_WIFI_PASSWORD = 5
_WIFI_FORGET = 6
_WIFI_COUNT = 7
_BTN_DURATIONS = (5, 10, 15, 30)   # seconds offered by the button-test picker
_LED_ALERT = 0
_LED_RAFFLE = 1
_LED_RGB_START = 2
_LED_ALL_OFF = NUM_RGB_LEDS + 2
_LED_EXIT = NUM_RGB_LEDS + 3
_LED_COUNT = NUM_RGB_LEDS + 4
_KEY_COLS = 6
_KEY_W = 32
_KEY_H = 20
_KEY_GAP = 4
_KEY_X = (240 - (_KEY_COLS * _KEY_W + (_KEY_COLS - 1) * _KEY_GAP)) // 2
_KEY_Y = 72

_CHAR_PAGE_NAMES = ("ABC", "abc", "SYM")
_CHAR_PAGE_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789-_.@#!?$%&*+/=",
)
_LED_TEST_COLORS = (
    (25, 0, 0),
    (25, 18, 0),
    (0, 22, 0),
    (0, 10, 25),
    (18, 0, 25),
)
_BTN_LIVE = (
    (LEFT, "LEFT"),
    (SELECT, "SELECT"),
    (START, "START"),
    (RIGHT, "RIGHT"),
    (BOOT, "BOOT"),
)

# Pet Resources debug editor: (display label, PetState attribute). The Work row's
# label is replaced with the active character's work_name at draw time. Order
# mirrors the pet stats menu.
_RESOURCE_DEFS = (
    ("Happiness", "happiness"),
    ("Hydration", "thirst"),
    ("Snackiness", "hunger"),
    ("Work", "work"),
)


class SettingsScreen(Screen):
    """Settings launcher and simple badge toggles."""

    accepts_disabled_buttons = True

    def __init__(self) -> None:
        self._settings = BadgeSettings()
        self._sel = 0
        self._debug_sel = 0
        self._button_sel = 0            # duration-picker selection
        self._button_dur = 0            # chosen test duration (seconds)
        self._button_test_end = 0       # ticks_ms deadline for the live test
        self._button_tested = set()     # buttons pressed during this live test
        self._button_live_sig = None    # last-drawn live-test signature
        self._led_sel = 0
        self._led_states = [False] * (NUM_RGB_LEDS + 2)
        self._led_con = None            # ConagotchiScreen driven for live pet LEDs
        self._view = _VIEW_MENU
        self._message = ""
        self._last_button = ""
        self._last_debug_redraw = 0
        self._pet = None
        self._edit_value = 0
        self._resource_sel = 0          # Pet Resources editor selection
        self._wifi_sel = 0
        self._wifi_network_sel = 0
        self._wifi_networks = ()
        self._text_target = "ssid"
        self._text_value = ""
        self._char_page = 0
        self._char_idx = 0
        self._character_sel = 0
        self._characters = ()
        self._active_char_id = ""
        self._splash_sel = 0
        self._splash_options = ()
        self._credits_boot = 0          # BOOT-press counter for the Debug unlock
        self._debug_flash_until = 0     # ticks_ms deadline for the unlock flash
        self._menu_top = 0              # main-menu scroll offset

    async def enter(self, display, leds, mgr) -> None:
        self._pet = _load_pet(mgr)
        self._draw(display, mgr)

    async def exit(self, display, leds, mgr) -> None:
        if self._view == _VIEW_LEDS or self._settings.debug_led_cycle_enabled:
            self._leds_all_off(leds)

    async def resume(self, display, leds, mgr) -> None:
        self._view = _VIEW_MENU
        self._pet = _load_pet(mgr)
        self._draw(display, mgr)

    async def update(self, display, leds, mgr) -> None:
        if self._debug_flash_until and \
                time.ticks_diff(time.ticks_ms(), self._debug_flash_until) >= 0:
            self._debug_flash_until = 0
            self._draw(display, mgr)
        if self._view == _VIEW_BUTTON_LIVE:
            self._update_button_live(display, mgr)
        # Keep the pet's level/XP LEDs live after a Level/EXP save: the pet
        # screen's own loop is paused while we're on top, so drive its LED
        # animation here (only in the editor/debug views — the LED test owns
        # the strip in _VIEW_LEDS).
        if self._led_con is not None and \
                self._view in (_VIEW_DEBUG, _VIEW_LEVEL, _VIEW_EXP):
            self._led_con._update_leds(leds, time.ticks_ms())

    def handle_button(self, btn: str, mgr) -> None:
        self._last_button = btn

        if self._view == _VIEW_DEBUG:
            self._handle_debug_button(btn, mgr)
        elif self._view == _VIEW_BUTTONS:
            self._handle_button_test_button(btn, mgr)
        elif self._view == _VIEW_BUTTON_LIVE:
            self._handle_button_live(btn, mgr)
        elif self._view == _VIEW_LEDS:
            self._handle_led_test_button(btn, mgr)
        elif self._view == _VIEW_LEVEL or self._view == _VIEW_EXP:
            self._handle_editor_button(btn, mgr)
        elif self._view == _VIEW_RESOURCES:
            self._handle_resources_button(btn, mgr)
        elif self._view == _VIEW_CHARACTER:
            self._handle_character_button(btn, mgr)
        elif self._view == _VIEW_SPLASH:
            self._handle_splash_button(btn, mgr)
        elif self._view == _VIEW_RESET:
            self._handle_reset_button(btn, mgr)
        elif self._view == _VIEW_WIFI:
            self._handle_wifi_button(btn, mgr)
        elif self._view == _VIEW_WIFI_SCAN:
            self._handle_wifi_scan_button(btn, mgr)
        elif self._view == _VIEW_TEXT:
            self._handle_text_button(btn, mgr)
        elif self._view == _VIEW_CREDITS:
            self._handle_credits_button(btn, mgr)
        elif self._view != _VIEW_MENU:
            self._handle_page_button(btn, mgr)
        else:
            self._handle_menu_button(btn, mgr)

    def _handle_menu_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == LEFT:
            self._move(-1, mgr._display)
        elif btn == RIGHT:
            self._move(1, mgr._display)
        elif btn == START:
            self._activate_selected(mgr)

    def _handle_page_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_MENU
            self._draw(mgr._display, mgr)

    def _handle_credits_button(self, btn: str, mgr) -> None:
        # Secret: BOOT x5 while on the Credits screen unlocks the Debug menu.
        # BOOT is repurposed here, so SELECT is the way back out.
        if btn == BOOT:
            self._credits_boot += 1
            if self._credits_boot >= _DEBUG_UNLOCK_PRESSES:
                self._credits_boot = 0
                self._enable_debug(mgr._display)
        elif btn == SELECT:
            self._credits_boot = 0
            self._view = _VIEW_MENU
            self._draw(mgr._display, mgr)

    def _enable_debug(self, display) -> None:
        if not self._settings.debug_enabled:
            self._settings.debug_enabled = True
            self._settings.save()
        self._debug_flash_until = time.ticks_ms() + _FLASH_MS
        _draw_flash(display, "DEBUG")

    def _handle_wifi_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_MENU
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._wifi_sel = (self._wifi_sel - 1) % _WIFI_COUNT
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == RIGHT:
            self._wifi_sel = (self._wifi_sel + 1) % _WIFI_COUNT
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == START:
            if self._wifi_sel == _WIFI_RADIO:
                self._toggle_wifi()
                self._draw(mgr._display, mgr)
            elif self._wifi_sel == _WIFI_SCAN:
                self._scan_wifi(mgr)
            elif self._wifi_sel == _WIFI_CONNECT:
                self._connect_wifi()
                self._draw(mgr._display, mgr)
            elif self._wifi_sel == _WIFI_CHECK:
                self._check_connectivity(mgr)
            elif self._wifi_sel == _WIFI_SSID:
                self._open_text_editor("ssid", self._settings.ssid, mgr._display, mgr)
            elif self._wifi_sel == _WIFI_PASSWORD:
                self._open_text_editor("password", self._settings.password, mgr._display, mgr)
            elif self._wifi_sel == _WIFI_FORGET:
                set_wifi_enabled(False)
                self._settings.forget_network()
                self._message = "TRUST CLEARED"
                self._draw(mgr._display, mgr)

    def _handle_wifi_scan_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_WIFI
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_wifi_network(-1, mgr._display)
        elif btn == RIGHT:
            self._move_wifi_network(1, mgr._display)
        elif btn == START:
            if not self._wifi_networks:
                self._view = _VIEW_WIFI
                self._message = "NO NETWORKS"
                self._draw(mgr._display, mgr)
                return
            ssid = self._wifi_networks[self._wifi_network_sel][0]
            if ssid == WIFI_SSID:
                self._settings.password = WIFI_PASSWORD
            elif ssid != self._settings.ssid:
                self._settings.password = ""
            self._settings.ssid = ssid
            self._settings.trusted_bssid = ""
            self._settings.wifi_enabled = False
            self._settings.save()
            set_wifi_enabled(False)
            self._wifi_sel = _WIFI_PASSWORD
            self._view = _VIEW_WIFI
            self._message = "SSID SAVED"
            self._draw(mgr._display, mgr)

    def _handle_text_button(self, btn: str, mgr) -> None:
        if btn == BOOT:
            self._save_text_editor()
            self._view = _VIEW_WIFI
            self._message = "SAVED"
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_text_cursor(-1, mgr._display)
        elif btn == RIGHT:
            self._move_text_cursor(1, mgr._display)
        elif btn == SELECT:
            self._char_page = (self._char_page + 1) % len(_CHAR_PAGE_NAMES)
            self._char_idx = 0
            self._draw(mgr._display, mgr)
        elif btn == START:
            selected = _char_at(self._char_page, self._char_idx)
            if selected == "DEL":
                self._text_value = self._text_value[:-1]
            elif selected == "SPC" and len(self._text_value) < 32:
                self._text_value += " "
            elif len(self._text_value) < 32:
                self._text_value += selected
            _draw_text_value(mgr._display, self._text_target, self._text_value)

    def _move_text_cursor(self, delta: int, display) -> None:
        old_idx = self._char_idx
        self._char_idx = (self._char_idx + delta) % _char_count(self._char_page)
        if self._char_idx == old_idx:
            return
        _draw_keyboard_key(display, self._char_page, old_idx, False)
        _draw_keyboard_key(display, self._char_page, self._char_idx, True)
        _draw_text_action_hint(display, _char_at(self._char_page, self._char_idx))

    def _move_wifi_network(self, delta: int, display) -> None:
        if not self._wifi_networks:
            return
        self._wifi_network_sel = (self._wifi_network_sel + delta) % len(self._wifi_networks)
        _draw_wifi_scan_page(display, self._wifi_networks, self._wifi_network_sel)

    def _handle_debug_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_MENU
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_debug_cursor(-1, mgr)
        elif btn == RIGHT:
            self._move_debug_cursor(1, mgr)
        elif btn == START:
            self._activate_debug(mgr)

    def _handle_button_test_button(self, btn: str, mgr) -> None:
        # Duration picker: choose how long the live test runs.
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_DEBUG
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._button_sel = (self._button_sel - 1) % len(_BTN_DURATIONS)
            self._draw(mgr._display, mgr)
        elif btn == RIGHT:
            self._button_sel = (self._button_sel + 1) % len(_BTN_DURATIONS)
            self._draw(mgr._display, mgr)
        elif btn == START:
            self._start_button_live(mgr)

    def _start_button_live(self, mgr) -> None:
        self._button_dur = _BTN_DURATIONS[self._button_sel]
        self._button_test_end = time.ticks_add(time.ticks_ms(), self._button_dur * 1000)
        self._button_tested = set()
        self._button_live_sig = None
        self._view = _VIEW_BUTTON_LIVE
        _draw_button_live(mgr._display, (), self._button_tested, self._button_dur)

    def _handle_button_live(self, btn: str, mgr) -> None:
        # Every press is part of the test — mark it, never navigate. The test
        # ends only when the timer runs out (handled in update()).
        self._button_tested.add(btn)

    def _update_button_live(self, display, mgr) -> None:
        remaining = time.ticks_diff(self._button_test_end, time.ticks_ms())
        if remaining <= 0:
            self._view = _VIEW_BUTTONS      # timer up -> back to the picker
            self._draw(display, mgr)
            return
        held = tuple(name for name, _label in _BTN_LIVE
                     if mgr._buttons.raw_pressed(name))
        for name in held:
            self._button_tested.add(name)
        secs = remaining // 1000 + 1
        sig = (secs, held, frozenset(self._button_tested))
        if sig != self._button_live_sig:
            self._button_live_sig = sig
            _draw_button_live(display, held, self._button_tested, secs)

    def _handle_led_test_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._leds_all_off(mgr._leds)
            self._view = _VIEW_DEBUG
            self._message = "LEDS OFF"
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_led_cursor(-1, mgr)
        elif btn == RIGHT:
            self._move_led_cursor(1, mgr)
        elif btn == START:
            if self._led_sel == _LED_EXIT:
                self._leds_all_off(mgr._leds)
                self._view = _VIEW_DEBUG
                self._message = "LEDS OFF"
                self._draw(mgr._display, mgr)
            elif self._led_sel == _LED_ALL_OFF:
                self._leds_all_off(mgr._leds)
                self._message = "ALL OFF"
                self._draw(mgr._display, mgr)
            else:
                self._led_states[self._led_sel] = not self._led_states[self._led_sel]
                self._apply_led_tests(mgr._leds)
                self._message = _led_label(self._led_sel).upper() + " " + (
                    "ON" if self._led_states[self._led_sel] else "OFF"
                )
                self._redraw_led_current(mgr)

    def _move_led_cursor(self, delta: int, mgr) -> None:
        old_idx = self._led_sel
        self._led_sel = (self._led_sel + delta) % _LED_COUNT
        self._message = ""
        if self._led_sel == old_idx:
            return
        self._draw(mgr._display, mgr)

    def _move_debug_cursor(self, delta: int, mgr) -> None:
        self._debug_sel = (self._debug_sel + delta) % _DBG_COUNT
        self._message = ""
        self._draw(mgr._display, mgr)   # full redraw so the scroll window updates

    def _handle_editor_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_DEBUG
            self._message = "CANCELLED"
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._adjust_editor(-1, mgr._display, mgr)
        elif btn == RIGHT:
            self._adjust_editor(1, mgr._display, mgr)
        elif btn == START:
            self._save_editor(mgr)

    def _handle_resources_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_DEBUG
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_resource_cursor(-1, mgr)
        elif btn == RIGHT:
            self._move_resource_cursor(1, mgr)
        elif btn == START:
            self._toggle_resource(mgr)

    def _move_resource_cursor(self, delta: int, mgr) -> None:
        self._resource_sel = (self._resource_sel + delta) % len(_RESOURCE_DEFS)
        self._message = ""
        self._draw(mgr._display, mgr)

    def _toggle_resource(self, mgr) -> None:
        """Forcibly drain (->0) or fill (->100) the selected resource. Toggles
        based on the current value: anything above empty drains, empty fills."""
        label, attr = _RESOURCE_DEFS[self._resource_sel]
        if attr == "work":
            label = getattr(self._pet, "work_name", "Work")
        drain = getattr(self._pet, attr, 0) > 0
        setattr(self._pet, attr, 0.0 if drain else 100.0)
        self._pet.save()
        # Reflect the change on the red Alert LED immediately via the pet screen
        # beneath us (it shares our _pet instance).
        con = self._con_screen(mgr)
        if con is not None:
            con._update_alert(mgr._leds)
        self._message = ("DRAINED " if drain else "FILLED ") + _clip(label.upper(), 12)
        self._draw(mgr._display, mgr)

    def _handle_character_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_DEBUG
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_character_cursor(-1, mgr)
        elif btn == RIGHT:
            self._move_character_cursor(1, mgr)
        elif btn == START:
            self._apply_character(mgr)

    def _move_character_cursor(self, delta: int, mgr) -> None:
        if not self._characters:
            return
        self._character_sel = (self._character_sel + delta) % len(self._characters)
        self._message = ""
        self._draw(mgr._display, mgr)

    def _open_character_picker(self, mgr) -> None:
        # Drop any button events still queued from the press that opened this
        # picker (START both opens and confirms here). Without this, a second
        # queued/chattered START is delivered straight to the picker and
        # immediately applies the pre-selected (active) character.
        mgr._buttons.clear()
        import character_manager
        self._characters = character_manager.all_characters()
        active = character_manager.get_active()
        self._active_char_id = active.id
        self._character_sel = 0
        for idx, cls in enumerate(self._characters):
            if cls.id == active.id:
                self._character_sel = idx
                break
        self._view = _VIEW_CHARACTER
        self._message = ""
        self._draw(mgr._display, mgr)

    def _apply_character(self, mgr) -> None:
        if not self._characters:
            return
        cls = self._characters[self._character_sel]
        import character_manager
        character_manager.save(cls)   # persist active + unlock the chosen character
        from screens.conagotchi import ConagotchiScreen
        mgr.switch_to(ConagotchiScreen())

    def _open_splash_picker(self, mgr) -> None:
        # Drop queued events so the opening START isn't re-delivered as a confirm.
        mgr._buttons.clear()
        import splash_manager
        # Row 0 is "Random" (auto / no stored selection); the rest are the
        # available splash images (regular pool then special pool).
        self._splash_options = [""] + splash_manager.all_names()
        current = splash_manager.get_selected()
        self._splash_sel = 0
        for idx, name in enumerate(self._splash_options):
            if name == current:
                self._splash_sel = idx
                break
        self._view = _VIEW_SPLASH
        self._message = ""
        self._draw(mgr._display, mgr)

    def _handle_splash_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_DEBUG
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == LEFT:
            self._move_splash_cursor(-1, mgr)
        elif btn == RIGHT:
            self._move_splash_cursor(1, mgr)
        elif btn == START:
            self._apply_splash(mgr)

    def _move_splash_cursor(self, delta: int, mgr) -> None:
        if not self._splash_options:
            return
        self._splash_sel = (self._splash_sel + delta) % len(self._splash_options)
        self._message = ""
        self._draw(mgr._display, mgr)

    def _apply_splash(self, mgr) -> None:
        if not self._splash_options:
            return
        name = self._splash_options[self._splash_sel]
        import splash_manager
        splash_manager.set_selected(name)   # "" = random/auto each boot
        self._message = "AUTO" if not name else splash_manager.label_for(name)
        self._draw(mgr._display, mgr)

    def _handle_reset_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._view = _VIEW_MENU
            self._message = ""
            self._draw(mgr._display, mgr)
        elif btn == START:
            self._perform_factory_reset(mgr)

    def _perform_factory_reset(self, mgr) -> None:
        _draw_reset_progress(mgr._display)
        try:
            import factory_reset
            factory_reset.wipe()
        except Exception:
            pass
        import machine
        time.sleep_ms(700)
        machine.reset()

    def _move(self, delta: int, display) -> None:
        count = len(_main_menu_items(self._settings))
        self._sel = (self._sel + delta) % count
        self._menu_top = ui.clamp_scroll(self._sel, self._menu_top, count)
        self._message = ""
        self._draw(display, None)

    def _activate_selected(self, mgr) -> None:
        items = _main_menu_items(self._settings)
        if self._sel >= len(items):
            self._sel = len(items) - 1
        action = items[self._sel][2]
        if action == "badge_mode":
            self._toggle_badge_mode(mgr)
            return
        if action == "wifi":
            self._view = _VIEW_WIFI
        elif action == "credits":
            self._credits_boot = 0
            self._view = _VIEW_CREDITS
        elif action == "debug":
            self._view = _VIEW_DEBUG
            self._message = "DEBUG TOOLS"
        elif action == "theme":
            from screens.theme_menu import ThemeMenuScreen
            mgr.push(ThemeMenuScreen())
            return
        elif action == "update":
            from screens.ota_update import OTAUpdateScreen
            mgr.push(OTAUpdateScreen())
            return
        elif action == "reset":
            self._view = _VIEW_RESET
            self._message = ""
        self._draw(mgr._display, mgr)

    def _cycle_ota_channel(self, mgr) -> None:
        """Move to the next channel and forget the recorded OTA version.

        Channel version counters are independent, so the new channel may be on a
        lower number. Without clearing, the badge would refuse it as a downgrade
        and silently never update."""
        from settings_state import ota_channels
        channels = ota_channels()
        try:
            nxt = channels[(channels.index(self._settings.ota_channel) + 1) % len(channels)]
        except ValueError:
            nxt = channels[0]
        if nxt == self._settings.ota_channel:
            self._message = "CHANNEL " + nxt.upper()
            self._redraw_debug_current(mgr)
            return
        self._settings.ota_channel = nxt
        self._settings.save()
        cleared = False
        try:
            import ota
            cleared = ota.clear_version()
        except Exception:
            pass
        self._message = nxt.upper() + (" - VER CLEARED" if cleared else " - NO VER")
        self._redraw_debug_current(mgr)

    def _activate_debug(self, mgr) -> None:
        if self._debug_sel == _DBG_OTA_CHANNEL:
            self._cycle_ota_channel(mgr)
        elif self._debug_sel == _DBG_ENABLE:
            self._settings.debug_enabled = not self._settings.debug_enabled
            self._settings.save()
            if not self._settings.debug_enabled:
                # Turned Debug off -> leave the now-hidden menu.
                self._view = _VIEW_MENU
                self._sel = 0
                self._message = ""
                self._draw(mgr._display, mgr)
            else:
                self._message = "DEBUG " + _on_off(self._settings.debug_enabled)
                self._redraw_debug_current(mgr)
        elif self._debug_sel == _DBG_BUTTONS:
            self._button_sel = 0
            self._view = _VIEW_BUTTONS
            self._message = ""
            self._draw(mgr._display, mgr)
        elif self._debug_sel == _DBG_LEDS:
            self._settings.debug_led_cycle_enabled = False
            self._settings.save()
            self._led_con = None   # LED test owns the strip; stop pet-LED driving
            self._led_sel = 0
            self._leds_all_off(mgr._leds)
            self._view = _VIEW_LEDS
            self._message = "LED TESTS"
            self._draw(mgr._display, mgr)
        elif self._debug_sel == _DBG_LEVEL:
            self._edit_value = int(self._pet.level)
            self._view = _VIEW_LEVEL
            self._draw(mgr._display, mgr)
        elif self._debug_sel == _DBG_EXP:
            self._edit_value = int(self._pet.total_experience)
            self._view = _VIEW_EXP
            self._draw(mgr._display, mgr)
        elif self._debug_sel == _DBG_RESOURCES:
            self._resource_sel = 0
            self._view = _VIEW_RESOURCES
            self._message = ""
            self._draw(mgr._display, mgr)
        elif self._debug_sel == _DBG_CHARACTER:
            self._open_character_picker(mgr)
        elif self._debug_sel == _DBG_VENDOR:
            self._settings.vendor_mode_enabled = not self._settings.vendor_mode_enabled
            self._settings.save()
            self._message = "VENDOR " + _on_off(self._settings.vendor_mode_enabled)
            self._redraw_debug_current(mgr)
        elif self._debug_sel == _DBG_SPLASH:
            self._open_splash_picker(mgr)
        elif self._debug_sel == _DBG_BLUETOOTH:
            from screens.ble_debug import BleDebugScreen
            mgr.push(BleDebugScreen())
            return
        elif self._debug_sel == _DBG_FPS:
            self._settings.fps_enabled = not self._settings.fps_enabled
            self._settings.save()
            import fps_counter
            fps_counter.set_enabled(self._settings.fps_enabled)   # live effect
            self._message = "FPS " + _on_off(self._settings.fps_enabled)
            self._redraw_debug_current(mgr)

    def _redraw_debug_current(self, mgr) -> None:
        self._draw(mgr._display, mgr)

    def _redraw_led_current(self, mgr) -> None:
        self._draw(mgr._display, mgr)

    def _adjust_editor(self, delta: int, display, mgr) -> None:
        if self._view == _VIEW_LEVEL:
            self._edit_value = max(0, min(MAX_LEVEL, self._edit_value + delta))
        else:
            self._edit_value = max(0, min(MAX_EXPERIENCE, self._edit_value + delta * _EXP_STEP))
        self._draw(display, mgr)

    def _save_editor(self, mgr) -> None:
        if self._view == _VIEW_LEVEL:
            self._pet.set_level(self._edit_value)
            self._message = "LEVEL SAVED"
        else:
            self._pet.set_progress(self._edit_value)
            self._message = "EXP SAVED"
        self._apply_pet_leds(mgr)   # light the new level/XP (and level-up) now
        self._view = _VIEW_DEBUG
        self._draw(mgr._display, mgr)

    def _apply_pet_leds(self, mgr) -> None:
        """Show the just-saved level/XP on the RGB LEDs immediately by driving
        the ConagotchiScreen beneath us (it shares our `_pet`)."""
        con = self._con_screen(mgr)
        if con is None:
            return
        con.refresh_leds(mgr._leds)
        self._led_con = con   # keep ticking the animation from update()

    def _con_screen(self, mgr):
        from screens.conagotchi import ConagotchiScreen
        for screen in reversed(mgr._stack):
            if isinstance(screen, ConagotchiScreen):
                return screen
        return None

    def _open_text_editor(self, target: str, value: str, display, mgr) -> None:
        self._text_target = target
        self._text_value = value
        self._char_page = 0
        self._char_idx = 0
        self._view = _VIEW_TEXT
        self._draw(display, mgr)

    def _save_text_editor(self) -> None:
        if self._text_target == "ssid":
            self._settings.ssid = self._text_value
        else:
            self._settings.password = self._text_value
        self._settings.save()

    def _toggle_badge_mode(self, mgr) -> None:
        """Cycle the badge mode. Choosing Blinky enters it straight away.

        Blinky replaces the whole UI rather than sitting on the stack, so this
        uses switch_to; BlinkyScreen clears the saved mode on exit so a badge
        cannot get stuck in it across reboots."""
        from settings_state import BADGE_MODES, MODE_BLINKY
        modes = BADGE_MODES
        try:
            nxt = modes[(modes.index(self._settings.badge_mode) + 1) % len(modes)]
        except ValueError:
            nxt = modes[0]
        self._settings.badge_mode = nxt
        self._settings.save()
        if nxt == MODE_BLINKY:
            from screens.blinky import BlinkyScreen
            mgr.switch_to(BlinkyScreen())
            return
        self._message = "MODE " + nxt.upper()
        self._draw(mgr._display, mgr)

    def _toggle_wifi(self) -> None:
        enable = not self._settings.wifi_enabled
        actual = set_wifi_enabled(enable)
        if actual is None:
            self._message = "WIFI N/A"
            return
        self._settings.wifi_enabled = actual
        self._settings.save()
        if actual == enable:
            self._message = "WIFI " + _on_off(actual)
        else:
            self._message = "WIFI ERR"

    def _scan_wifi(self, mgr) -> None:
        self._message = "SCANNING"
        self._draw(mgr._display, mgr)
        self._wifi_networks = tuple(scan_wifi_networks())
        self._wifi_network_sel = 0
        if self._wifi_networks:
            self._view = _VIEW_WIFI_SCAN
            self._message = ""
        else:
            self._message = "NO NETWORKS"
        self._draw(mgr._display, mgr)

    def _connect_wifi(self) -> None:
        connected, code, bssid = connect_saved_wifi(
            self._settings.ssid, self._settings.password, self._settings.trusted_bssid
        )
        self._settings.wifi_enabled = True
        if connected and bssid:
            self._settings.trusted_bssid = bssid
        self._settings.save()
        if connected:
            self._message = "CONNECTED"
        elif code == "OPEN":
            self._message = "OPEN BLOCK"
        elif code == "WEAK":
            self._message = "WEAK BLOCK"
        else:
            self._message = code

    def _check_connectivity(self, mgr) -> None:
        self._message = "CHECKING"
        self._draw(mgr._display, mgr)
        ok, code, detail = check_connectivity()
        if ok:
            self._message = "ONLINE"
        elif detail:
            self._message = code + " " + detail
        else:
            self._message = code
        self._draw(mgr._display, mgr)

    def _apply_led_tests(self, leds) -> None:
        leds.set_alert(self._led_states[_LED_ALERT])
        leds.set_raffle(self._led_states[_LED_RAFFLE])
        for idx in range(NUM_RGB_LEDS):
            state_idx = _LED_RGB_START + idx
            color = _LED_TEST_COLORS[idx % len(_LED_TEST_COLORS)]
            leds.rgb[idx] = color if self._led_states[state_idx] else (0, 0, 0)
        leds.rgb.write()

    def _leds_all_off(self, leds) -> None:
        for idx in range(len(self._led_states)):
            self._led_states[idx] = False
        leds.all_off()

    def _draw(self, display, mgr) -> None:
        _sync_theme()
        if self._view == _VIEW_WIFI:
            _draw_wifi_page(display, self._settings, self._wifi_sel, self._message)
        elif self._view == _VIEW_WIFI_SCAN:
            _draw_wifi_scan_page(display, self._wifi_networks, self._wifi_network_sel)
        elif self._view == _VIEW_TEXT:
            _draw_text_editor(display, self._text_target, self._text_value,
                              self._char_page, self._char_idx)
        elif self._view == _VIEW_CREDITS:
            _draw_credits_page(display)
        elif self._view == _VIEW_DEBUG:
            _draw_debug_page(display, self._settings, self._pet, self._debug_sel,
                             self._message, "")
        elif self._view == _VIEW_BUTTONS:
            _draw_button_test_page(display, self._button_sel)
        elif self._view == _VIEW_BUTTON_LIVE:
            _draw_button_live(display, (), self._button_tested, self._button_dur)
        elif self._view == _VIEW_LEDS:
            _draw_led_test_page(display, self._led_states, self._led_sel, self._message)
        elif self._view == _VIEW_LEVEL:
            _draw_editor_page(display, "LEVEL", str(self._edit_value), "0-{}".format(MAX_LEVEL))
        elif self._view == _VIEW_EXP:
            _draw_editor_page(display, "EXP", str(self._edit_value), "0-{}".format(MAX_EXPERIENCE))
        elif self._view == _VIEW_RESOURCES:
            _draw_resources_page(display, self._pet, self._resource_sel, self._message)
        elif self._view == _VIEW_CHARACTER:
            _draw_character_page(display, self._characters, self._character_sel,
                                 self._active_char_id)
        elif self._view == _VIEW_SPLASH:
            _draw_splash_page(display, self._splash_options, self._splash_sel,
                              self._message)
        elif self._view == _VIEW_RESET:
            _draw_reset_page(display)
        else:
            count = len(_main_menu_items(self._settings))
            if self._sel >= count:
                self._sel = count - 1
            self._menu_top = ui.clamp_scroll(self._sel, self._menu_top, count)
            _draw_menu(display, self._settings, self._sel, self._menu_top)


def _load_pet(mgr):
    try:
        for screen in reversed(mgr._stack):
            pet = getattr(screen, "_pet", None)
            if pet is not None:
                return pet
    except Exception:
        pass
    import character_manager
    return PetState(character_manager.get_active())


def _main_menu_items(settings: BadgeSettings):
    """Top-level Settings rows as (label, value, action).

    The Debug menu is hidden until unlocked (settings.debug_enabled), which is
    turned on by the BOOT x5 combo on the Credits screen."""
    import theme
    items = [
        ("Wi-Fi", _on_off(settings.wifi_enabled), "wifi"),
        ("Badge Mode", _badge_mode_label(settings), "badge_mode"),
        ("Credits", "VIEW", "credits"),
    ]
    if settings.debug_enabled:
        items.append(("Debug", "VIEW", "debug"))
    items.append(("Theme", theme.name().upper(), "theme"))
    from config import OTA_BASE_URL
    if OTA_BASE_URL:
        items.append(("Update", _ota_version_label(), "update"))
    items.append(("Factory Reset", "CLEAR", "reset"))
    return items


def _ota_version_label() -> str:
    """Installed OTA version for the Settings row, so a badge can be identified
    at a glance without entering the Update screen."""
    try:
        import ota
        return "V%d" % ota.local_version()
    except Exception:
        return "VIEW"


def _badge_mode_label(settings: BadgeSettings) -> str:
    """CONAGOTCHI or BLINKY, clipped to the width the row value allows."""
    return _clip(settings.badge_mode.upper(), 12) if settings.badge_mode else "-"


def _row_value_fg(value: str) -> int:
    if value == "ON" or value == "ACTIVE":
        return _OK
    if value == "OFF":
        return _OFF
    return _MUTED




def _draw_list_page(display, title, items, selected, confirm=None,
                    message=None, empty=None, value_fg=_row_value_fg) -> None:
    """Standard Settings list page: title bar + windowed ui.list_view + controls.

    Scrolls automatically when the list outgrows the screen; the window is
    derived from `selected`, so nav handlers just update the index and redraw.
    """
    import theme
    ui.screen(display, title)
    if not items:
        ui.center_text(display, empty or "NONE", 104, _WARN, _BG)
    else:
        top = ui.window_top(selected, len(items), theme.get().rows_visible)
        ui.list_view(display, items, selected, top, value_fg=value_fg)
    if message:
        ui.center_text(display, _clip(message, 22), 180, _OK, _BG)
    ui.controls(display, confirm)


def _draw_menu(display, settings: BadgeSettings, selected: int, top: int) -> None:
    ui.screen(display, "SETTINGS")
    ui.list_view(display, _main_menu_items(settings), selected, top,
                 value_fg=_row_value_fg)
    ui.controls(display, "OK")




def _draw_debug_page(display, settings: BadgeSettings, pet: PetState,
                     selected: int, message: str, button_status: str) -> None:
    ui.screen(display, "DEBUG")

    import theme
    items = _debug_rows(settings, pet)
    top = ui.window_top(selected, len(items), theme.get().rows_visible)
    ui.list_view(display, items, selected, top, value_fg=_row_value_fg)

    _draw_debug_status(display, settings, message, button_status)

    ui.controls(display, "OK")


def _debug_rows(settings: BadgeSettings, pet: PetState):
    return (
        ("Debug", _on_off(settings.debug_enabled)),
        ("Buttons", "TEST"),
        ("LED Test", "VIEW"),
        ("Level", str(int(pet.level))),
        ("EXP", str(int(pet.total_experience))),
        ("Pet Resources", "VIEW"),
        ("Character", _clip(pet.name.upper(), 10)),
        ("Vendor Mode", _on_off(settings.vendor_mode_enabled)),
        ("Splash", _splash_value()),
        ("Bluetooth", "VIEW"),
        ("FPS", _on_off(settings.fps_enabled)),
        ("Update Channel", settings.ota_channel.upper() or "-"),
    )


def _splash_value() -> str:
    """Debug-row value for the Splash item: the current selection's label, or
    AUTO when no explicit splash is stored (random each boot)."""
    try:
        import splash_manager
        sel = splash_manager.get_selected()
        return splash_manager.label_for(sel) if sel else "AUTO"
    except Exception:
        return "AUTO"


def _draw_debug_status(display, settings: BadgeSettings, message: str, button_status: str) -> None:
    display.fill_rect(0, 170, 240, 28, _BG)
    if message:
        ui.center_text(display, message, 174, _MUTED, _BG)


def _draw_button_test_page(display, selected: int) -> None:
    """Duration picker for the live button test."""
    items = ["{} SECONDS".format(d) for d in _BTN_DURATIONS]
    _draw_list_page(display, "BUTTON TEST", items, selected, confirm="TEST")


def _draw_button_live(display, held, tested, secs: int) -> None:
    """Live per-button test: each button lights green while held and keeps a
    checkmark once it has been pressed."""
    ui.screen(display, "BUTTON TEST")
    ui.center_text(display, "{}s   TESTED {}/{}".format(secs, len(tested), len(_BTN_LIVE)),
                 46, _MUTED, _BG)

    y0 = 74
    dy = 26
    for i, (name, label) in enumerate(_BTN_LIVE):
        y = y0 + i * dy
        is_held = name in held
        if is_held:
            display.fill_rect(36, y - 4, 168, 22, _OK)
            draw_text(display, label, 48, y, _BG, _OK)
        else:
            draw_text(display, label, 48, y, _TEXT, _BG)
        # tested indicator: filled green box (done) vs muted outline (pending)
        bx, by = 178, y - 3
        if name in tested:
            display.fill_rect(bx, by, 16, 16, _OK)
        else:
            display.rect(bx, by, 16, 16, _MUTED)

    ui.bottom_line(display, "TESTING...")


def _draw_led_test_page(display, states, selected: int, message: str) -> None:
    ui.screen(display, "LED TESTS")
    display.fill_rect(0, 211, 240, 29, _PANEL)

    rows = _led_test_rows(states)
    total = len(rows)
    start = max(0, min(selected - 2, max(0, total - 6)))
    visible = rows[start:start + 6]
    y = 42
    for idx, row in enumerate(visible):
        real_idx = start + idx
        _draw_row(display, y + idx * 24, row[0], row[1], real_idx == selected)

    if message:
        ui.center_text(display, _clip(message, 22), 186, _MUTED, _BG)

    ui.controls(display, "OK")


def _led_test_rows(states):
    rows = []
    for idx in range(_LED_COUNT):
        if idx == _LED_ALL_OFF:
            rows.append(("All Off", "CLEAR"))
        elif idx == _LED_EXIT:
            rows.append(("Exit", "BACK"))
        else:
            rows.append((_led_label(idx), "ON" if states[idx] else "OFF"))
    return tuple(rows)


def _led_label(idx: int) -> str:
    if idx == _LED_ALERT:
        return "Alert"
    if idx == _LED_RAFFLE:
        return "Raffle"
    if _LED_RGB_START <= idx < _LED_RGB_START + NUM_RGB_LEDS:
        return "RGB {}".format(idx - _LED_RGB_START + 1)
    if idx == _LED_ALL_OFF:
        return "All Off"
    return "Exit"


def _draw_editor_page(display, title: str, value: str, bounds: str) -> None:
    ui.screen(display, title)
    display.fill_rect(0, 211, 240, 29, _PANEL)
    ui.center_text(display, "LEFT / RIGHT", 72, _MUTED, _BG)
    ui.center_text(display, "ADJUST VALUE", 92, _MUTED, _BG)
    display.fill_rect(60, 122, 120, 30, _SEL)
    display.rect(60, 122, 120, 30, _TEXT)
    ui.center_text(display, value, 133, _TEXT, _SEL)
    ui.center_text(display, bounds, 168, _MUTED, _BG)
    ui.controls(display, "SAVE")


def _draw_reset_page(display) -> None:
    ui.screen(display, "FACTORY RESET")
    display.fill_rect(0, 211, 240, 29, _PANEL)
    ui.center_text(display, "ERASE ALL DATA?", 66, _WARN, _BG)
    ui.center_text(display, "Character, stamps,", 96, _MUTED, _BG)
    ui.center_text(display, "pet state & settings", 114, _MUTED, _BG)
    ui.center_text(display, "will be wiped and the", 132, _MUTED, _BG)
    ui.center_text(display, "badge will reboot.", 150, _MUTED, _BG)
    ui.center_text(display, "THIS CANNOT BE UNDONE", 176, _WARN, _BG)
    ui.controls(display, "WIPE")


def _draw_reset_progress(display) -> None:
    display.fill(_BG)
    ui.center_text(display, "RESETTING", 104, _WARN, _BG)
    ui.center_text(display, "REBOOTING...", 128, _MUTED, _BG)


def _resource_rows(pet):
    """(label, "NN%") rows for the Pet Resources editor; Work uses work_name."""
    rows = []
    for label, attr in _RESOURCE_DEFS:
        if attr == "work":
            label = _clip(getattr(pet, "work_name", "Work"), 12)
        val = int(max(0, min(100, getattr(pet, attr, 0))))
        rows.append((label, "{}%".format(val)))
    return tuple(rows)


def _resource_value_fg(value: str) -> int:
    """Colour the % value red when at/below the low-resource alert threshold."""
    try:
        import pet_state
        return _OFF if int(value.rstrip("%")) <= pet_state.LOW_THRESHOLD else _OK
    except (ValueError, ImportError):
        return _MUTED


def _draw_resources_page(display, pet, selected: int, message: str) -> None:
    import theme
    rows = _resource_rows(pet)
    ui.screen(display, "PET RESOURCES")
    top = ui.window_top(selected, len(rows), theme.get().rows_visible)
    ui.list_view(display, rows, selected, top, value_fg=_resource_value_fg)
    if message:
        ui.center_text(display, _clip(message, 22), 174, _MUTED, _BG)
    # START drains a non-empty resource, fills an empty one.
    empty = rows[selected][1] == "0%"
    ui.controls(display, "FILL" if empty else "DRAIN")


def _draw_character_page(display, characters, selected: int, active_id: str) -> None:
    items = [(_clip(c.name, 14), "ACTIVE" if c.id == active_id else "SET")
             for c in characters]
    _draw_list_page(display, "CHARACTER", items, selected,
                    confirm="SET", empty="NONE FOUND")


def _draw_splash_page(display, options, selected: int, message: str) -> None:
    import splash_manager
    current = splash_manager.get_selected()
    items = []
    for name in options:
        if not name:
            label, tag = "Random", "AUTO"
        else:
            label = splash_manager.label_for(name)
            tag = "SPECIAL" if splash_manager.is_special(name) else "SET"
        if name == current:
            tag = "ACTIVE"
        items.append((_clip(label, 14), tag))
    _draw_list_page(display, "SPLASH", items, selected,
                    confirm="SET", message=message, empty="NONE FOUND")


def _draw_row(display, y: int, label: str, value: str, selected: bool) -> None:
    bg = _SEL if selected else _BG
    fg = _TEXT
    val_fg = _OK if value == "ON" else (_OFF if value == "OFF" else _MUTED)
    # Inset into a centered band so text clears the round bezel on every row.
    display.fill_rect(28, y - 5, 184, 22, bg)
    if selected:
        display.rect(28, y - 5, 184, 22, _TEXT)
    draw_text(display, label, 36, y, fg, bg)
    draw_text(display, value, 204 - len(value) * 8, y, val_fg, bg)


def _draw_wifi_page(display, settings: BadgeSettings, selected: int, message: str) -> None:
    rows = [
        ("Radio", _on_off(settings.wifi_enabled)),
        ("Scan Networks", "FIND"),
        ("Connect", "SAVED" if settings.ssid and settings.password else "ADD"),
        ("Net Check", "TEST"),
        ("SSID", _clip(settings.ssid, 12) if settings.ssid else "<empty>"),
        ("Password", _mask(settings.password)),
        ("Untrust AP", "CLEAR"),
    ]
    _draw_list_page(display, "WI-FI", rows, selected, confirm="OK", message=message)


def _draw_wifi_scan_page(display, networks, selected: int) -> None:
    items = [(_clip(n[0], 14), "{}dB".format(n[1])) for n in networks]
    _draw_list_page(display, "SELECT NETWORK", items, selected,
                    confirm="USE", empty="NO NETWORKS")


def _draw_text_editor(display, target: str, value: str, page_idx: int, char_idx: int) -> None:
    ui.clear(display)
    display.fill_rect(0, 0, 240, 36, _PANEL)
    display.fill_rect(0, 211, 240, 29, _PANEL)

    title = "EDIT SSID" if target == "ssid" else "EDIT PASS"
    page_name = _CHAR_PAGE_NAMES[page_idx]
    selected = _char_at(page_idx, char_idx)

    ui.center_text(display, title, 14, _TEXT, _PANEL)
    _draw_text_value(display, target, value)
    ui.center_text(display, page_name, 58, _MUTED, _BG)
    _draw_keyboard(display, page_idx, char_idx)
    _draw_text_action_hint(display, selected)

    draw_text(display, "SELECT PAGE", 8, 219, _MUTED, _PANEL)
    draw_text(display, "BOOT SAVE", 160, 219, _MUTED, _PANEL)


def _draw_keyboard(display, page_idx: int, selected: int) -> None:
    for idx in range(_char_count(page_idx)):
        _draw_keyboard_key(display, page_idx, idx, idx == selected)


def _draw_keyboard_key(display, page_idx: int, idx: int, selected: bool) -> None:
    ch = _char_at(page_idx, idx)
    row = idx // _KEY_COLS
    col = idx % _KEY_COLS
    x = _KEY_X + col * (_KEY_W + _KEY_GAP)
    y = _KEY_Y + row * (_KEY_H + _KEY_GAP)
    label_x = x + (_KEY_W - len(ch) * 8) // 2
    label_y = y + (_KEY_H - 8) // 2
    if selected:
        display.fill_rect(x, y, _KEY_W, _KEY_H, _SEL)
        display.rect(x, y, _KEY_W, _KEY_H, gc9a01.WHITE)
        draw_text(display, ch, label_x, label_y, _TEXT, _SEL)
    else:
        display.fill_rect(x, y, _KEY_W, _KEY_H, _BG)
        display.rect(x, y, _KEY_W, _KEY_H, _PANEL)
        draw_text(display, ch, label_x, label_y, _MUTED, _BG)


def _char_count(page_idx: int) -> int:
    return len(_CHAR_PAGE_CHARS[page_idx]) + 2


def _char_at(page_idx: int, idx: int) -> str:
    chars = _CHAR_PAGE_CHARS[page_idx]
    if idx < len(chars):
        return chars[idx]
    if idx == len(chars):
        return "SPC"
    return "DEL"


def _draw_text_value(display, target: str, value: str) -> None:
    shown = _clip(value, 20) if target == "ssid" else _mask(value)
    display.fill_rect(0, 40, 240, 16, _BG)
    ui.center_text(display, shown or "_", 46, _TEXT, _BG)


def _draw_text_action_hint(display, selected: str) -> None:
    display.fill_rect(0, 186, 240, 18, _BG)
    if selected == "DEL":
        ui.center_text(display, "START DELETES", 190, _MUTED, _BG)
    elif selected == "SPC":
        ui.center_text(display, "START SPACE", 190, _MUTED, _BG)
    else:
        ui.center_text(display, "START ADDS", 190, _MUTED, _BG)


def _draw_credits_page(display) -> None:
    ui.screen(display, "CREDITS")
    ui.center_text(display, "OzSec 2026", 56, _TEXT, _BG)
    ui.center_text(display, "Conagotchi", 76, _MUTED, _BG)
    ui.center_text(display, "Contributors:", 108, _TEXT, _BG)
    ui.center_text(display, "rufflabs", 130, _MUTED, _BG)
    ui.center_text(display, "baum", 150, _MUTED, _BG)
    ui.center_text(display, "Claude and Codex", 170, _MUTED, _BG)
    ui.controls(display)


def _draw_flash(display, text: str) -> None:
    """Brief full-width banner (e.g. the DEBUG unlock confirmation)."""
    display.fill_rect(0, 92, 240, 56, _SEL)
    display.rect(0, 92, 240, 56, _TEXT)
    ui.center_text(display, text, 116, _TEXT, _SEL)




def _on_off(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + ">"


def _mask(text: str) -> str:
    if not text:
        return "<empty>"
    if len(text) <= 10:
        return "*" * len(text)
    return "*" * 9 + ">"
