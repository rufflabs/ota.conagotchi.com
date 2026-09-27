"""Settings, and the hidden Debug menu.

Every page is its own screen, and every list page is a menu.ListScreen, the
same list every other part of the badge uses: selection, scroll window,
scrolling titles and rows, message line and controls all come from there.

    SettingsScreen      the top level (Wireless, Badge, System, Credits, and
                        Debug once unlocked) and each group:
                        Wireless: Wi-Fi, Bluetooth, IR
                        Badge: Badge Mode, Theme, Keyboard, Text Size
                        System: Update, Factory Reset
    BadgeModeScreen     pick Chi, Blinky or Flashlight
    WifiScreen          radio, scan, connect, net check, SSID/password, ...
    CreditsScreen       BOOT x5 here unlocks Debug
    DebugScreen         the top level, and each group (Chi's, Reset, ...)
    ...                 editors, pickers and tests opened from those

Pages hand results back to the page that opened them through `message`, which
that page shows when it resumes.
"""
import time

import ui
from buttons import BOOT, LEFT, RIGHT, SELECT, START
from config import NUM_RGB_LEDS, WIFI_PASSWORD, WIFI_SSID
from menu import ListScreen
from pet_state import MAX_EXPERIENCE, MAX_LEVEL, PetState
from screen_manager import Screen
from settings_state import (
    BadgeSettings,
    check_connectivity,
    connect_saved_wifi,
    disconnect_wifi,
    scan_wifi_networks,
    set_wifi_enabled,
    wifi_status,
)

# Settings: top-level rows, some of which open a group of related items (the
# same shape as Debug). Debug appears once unlocked; Update only when an OTA
# host is configured.
_SETTINGS_TOP = ("wireless", "badge", "system", "credits", "debug")
_SETTINGS_GROUPS = {
    # key: (row label, page title, items)
    "wireless": ("Wireless", "WIRELESS", ("wifi", "bluetooth", "ir")),
    "badge": ("Badge", "BADGE", ("badge_mode", "theme", "keyboard", "text_size")),
    "system": ("System", "SYSTEM", ("update", "reset")),
}

# How each badge mode is shown (the saved value is unchanged).
_MODE_LABELS = {"conagotchi": "CHI", "blinky": "BLINKY"}
# The Badge Mode picker: (row label, key). Flashlight is a choice, never a
# saved mode, so a reboot cannot come back up with every LED at full white.
_MODE_CHOICES = (("Chi", "conagotchi"), ("Blinky", "blinky"),
                 ("Flashlight", "flashlight"))

_DEBUG_UNLOCK_PRESSES = 5   # BOOT presses in Credits to unlock the Debug menu
_FLASH_MS = 900             # how long the "DEBUG" unlock dialog stays on screen

# Debug menu: top-level rows, some of which open a group of related items.
# "Debug Off" is last so a stray START on entering cannot hit it.
_DEBUG_TOP = ("chis", "reset", "hardware", "system", "vendor", "enable")
_DEBUG_GROUPS = {
    # key: (row label, page title, items)
    "chis": ("Chi's", "CHI'S", ("character", "level", "exp", "resources",
                                "unlock_all", "lock_all")),
    "reset": ("Reset", "RESET", ("clear_stamps", "clear_challenges")),
    "hardware": ("Hardware", "HARDWARE", ("buttons", "leds", "bluetooth", "fps")),
    "system": ("System", "SYSTEM", ("splash", "ota_channel")),
}
_CLEAR_CONFIRM_MS = 3000   # second START must follow within this to clear

_EXP_STEP = 100
_BTN_DURATIONS = (5, 10, 15, 30)   # seconds offered by the button-test picker
_LED_ALERT = 0
_LED_RAFFLE = 1
_LED_RGB_START = 2
_LED_ALL_OFF = NUM_RGB_LEDS + 2
_LED_EXIT = NUM_RGB_LEDS + 3
_LED_COUNT = NUM_RGB_LEDS + 4
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
# label is replaced with the active character's work_name. Order mirrors the
# pet stats menu.
_RESOURCE_DEFS = (
    ("Happiness", "happiness"),
    ("Hydration", "thirst"),
    ("Snackiness", "hunger"),
    ("Work", "work"),
)

# The pet screen whose level/XP LEDs are kept animating after a Level/EXP save:
# its own loop is paused while Settings is on top. Cleared when Settings closes.
_PET_LEDS = None


class _SettingsList(ListScreen):
    """A Settings list page: the badge settings, the pet, and the pet LEDs."""

    confirm_verb = "OK"

    def __init__(self, settings=None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else BadgeSettings()
        self.pet = None

    def confirm(self):
        return self.confirm_verb

    async def enter(self, display, leds, mgr) -> None:
        self.pet = _load_pet(mgr)
        await super().enter(display, leds, mgr)

    async def resume(self, display, leds, mgr) -> None:
        self.pet = _load_pet(mgr)
        await super().resume(display, leds, mgr)

    async def update(self, display, leds, mgr) -> None:
        await super().update(display, leds, mgr)
        if _PET_LEDS is not None:
            _PET_LEDS._update_leds(leds, time.ticks_ms())


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsScreen(_SettingsList):
    """The Settings menu (group None) or one of its groups."""

    def __init__(self, settings=None, group=None, root=None) -> None:
        super().__init__(settings)
        self.group = group
        self.root = root if root is not None else self   # the top-level page
        self.title = "SETTINGS" if group is None else _SETTINGS_GROUPS[group][1]

    def rows(self):
        return _settings_rows(self.settings, self.group)

    def confirm(self):
        return "OPEN" if self.menu.key in _SETTINGS_GROUPS else "OK"

    def back(self, mgr) -> None:
        if self.group is None:          # leaving Settings entirely
            global _PET_LEDS
            _PET_LEDS = None
        mgr.pop()

    def activate(self, mgr) -> None:
        key = self.menu.key
        s = self.settings
        if key in _SETTINGS_GROUPS:
            mgr.push(SettingsScreen(s, key, self.root))
        elif key == "wifi":
            mgr.push(WifiScreen(s))
        elif key == "bluetooth":
            s.bluetooth_enabled = not s.bluetooth_enabled
            s.save()
            self.message = "BT TRADES " + _on_off(s.bluetooth_enabled)
            self.redraw(mgr)
        elif key == "ir":
            s.ir_enabled = not s.ir_enabled
            s.save()
            self.message = "IR TRADES " + _on_off(s.ir_enabled)
            self.redraw(mgr)
        elif key == "badge_mode":
            mgr.push(BadgeModeScreen(s, self))
        elif key == "keyboard":
            from settings_state import KEYBOARDS
            cur = s.keyboard
            s.keyboard = KEYBOARDS[(KEYBOARDS.index(cur) + 1) % len(KEYBOARDS)] \
                if cur in KEYBOARDS else KEYBOARDS[0]
            s.save()
            self.message = "KEYBOARD " + _keyboard_label(s)
            self.redraw(mgr)
        elif key == "text_size":
            from settings_state import TEXT_LARGE, TEXT_NORMAL
            s.text_size = TEXT_NORMAL if s.text_size == TEXT_LARGE else TEXT_LARGE
            s.save()
            ui.set_list_scale(2 if s.text_size == TEXT_LARGE else 1)
            self.message = "TEXT " + s.text_size.upper()
            self.redraw(mgr)               # shows the new size straight away
        elif key == "credits":
            mgr.push(CreditsScreen(s))
        elif key == "debug":
            mgr.push(DebugScreen(s, root=self.root))
        elif key == "theme":
            from screens.theme_menu import ThemeMenuScreen
            mgr.push(ThemeMenuScreen())
        elif key == "update":
            from screens.ota_update import OTAUpdateScreen
            mgr.push(OTAUpdateScreen())
        elif key == "reset":
            mgr.push(FactoryResetScreen())

class BadgeModeScreen(ListScreen):
    """Choose Chi, Blinky or Flashlight. Chi goes back to Badge with the new
    mode shown; Blinky and Flashlight replace the whole UI (switch_to), and
    each returns to the pet when a button leaves it."""

    title = "BADGE MODE"

    def __init__(self, settings, parent=None) -> None:
        super().__init__()
        self.settings = settings
        self.parent = parent
        keys = [key for _, key in _MODE_CHOICES]
        mode = settings.badge_mode
        self.menu.sel = keys.index(mode) if mode in keys else 0

    def rows(self):
        mode = self.settings.badge_mode
        return [(label, "ACTIVE" if key == mode else None, key)
                for label, key in _MODE_CHOICES]

    def confirm(self):
        return "SET"

    def activate(self, mgr) -> None:
        from settings_state import MODE_BLINKY, MODE_CONAGOTCHI
        key = self.menu.key
        s = self.settings
        # Flashlight saves Chi: that is where it returns, and where a reboot lands.
        s.badge_mode = MODE_BLINKY if key == "blinky" else MODE_CONAGOTCHI
        s.save()
        if key == "blinky":
            from screens.blinky import BlinkyScreen
            mgr.switch_to(BlinkyScreen())
        elif key == "flashlight":
            from screens.flashlight import FlashlightScreen
            mgr.switch_to(FlashlightScreen())
        else:
            if self.parent is not None:
                self.parent.message = "MODE " + _MODE_LABELS[s.badge_mode]
            mgr.pop()


# ── Wi-Fi ────────────────────────────────────────────────────────────────────

class WifiScreen(_SettingsList):
    title = "WI-FI"

    def rows(self):
        s = self.settings
        status = wifi_status()
        radio, linked = status if status else (s.wifi_enabled, False)
        if linked:
            connect = "LINKED"
        else:
            connect = "SAVED" if s.ssid and s.password else "ADD"
        return [
            ("Radio", _on_off(radio), "radio"),
            ("Scan Networks", "FIND", "scan"),
            ("Connect", connect, "connect"),
            ("Net Check", "TEST", "check"),
            ("SSID", ui.clip(s.ssid, 12) if s.ssid else "<empty>", "ssid"),
            ("Password", _mask(s.password), "password"),
            ("Disconnect", "DROP", "disconnect"),
            ("Forget Network", "CLEAR", "forget"),
        ]

    def activate(self, mgr) -> None:
        key = self.menu.key
        s = self.settings
        if key == "radio":
            self._toggle_wifi()
        elif key == "scan":
            self._scan(mgr)
            return
        elif key == "connect":
            self._connect()
        elif key == "check":
            self._check(mgr)
        elif key in ("ssid", "password"):
            from screens.text_input import TextInputScreen
            secret = key == "password"
            mgr.push(TextInputScreen("EDIT PASS" if secret else "EDIT SSID",
                                     s.password if secret else s.ssid,
                                     on_done=lambda v: self._save_text(key, v),
                                     secret=secret))
            return
        elif key == "disconnect":
            self.message = "DISCONNECTED" if disconnect_wifi() else "NOT CONNECTED"
        elif key == "forget":
            disconnect_wifi()
            s.forget_network()
            self.message = "FORGOTTEN"
        self.redraw(mgr)

    def _save_text(self, key, value) -> None:
        if key == "ssid":
            self.settings.ssid = value
        else:
            self.settings.password = value
        self.settings.save()
        self.message = "SAVED"

    def picked_network(self, ssid) -> None:
        """A network chosen on the scan page: save it and move to Password."""
        s = self.settings
        if ssid == WIFI_SSID:
            s.password = WIFI_PASSWORD
        elif ssid != s.ssid:
            s.password = ""
        s.ssid = ssid
        s.trusted_bssid = ""
        s.save()
        disconnect_wifi()   # leave the old network; the radio stays on
        self.menu.sel = 5   # Password
        self.message = "SSID SAVED"

    def _toggle_wifi(self) -> None:
        # Toggle what the radio is actually doing: a scan may have powered it
        # up while the saved setting still said off.
        s = self.settings
        status = wifi_status()
        enable = not (status[0] if status else s.wifi_enabled)
        actual = set_wifi_enabled(enable)
        if actual is None:
            self.message = "WIFI N/A"
            return
        s.wifi_enabled = actual
        s.save()
        self.message = ("WIFI " + _on_off(actual)) if actual == enable else "WIFI ERR"

    def _radio_on(self) -> bool:
        """Scanning and connecting need the radio. Turn it on the same way the
        Radio row would, so the page and the saved setting both say ON."""
        actual = set_wifi_enabled(True)
        if not actual:
            self.message = "WIFI N/A" if actual is None else "WIFI ERR"
            return False
        if not self.settings.wifi_enabled:
            self.settings.wifi_enabled = True
            self.settings.save()
        return True

    def _scan(self, mgr) -> None:
        if not self._radio_on():
            self.redraw(mgr)
            return
        self.message = "SCANNING"
        self.draw(mgr._display)
        networks = tuple(scan_wifi_networks())
        if networks:
            self.message = ""
            mgr.push(WifiScanScreen(self, networks))
        else:
            self.message = "NO NETWORKS"
            self.redraw(mgr)

    def _connect(self) -> None:
        if not self._radio_on():
            return
        s = self.settings
        connected, code, bssid = connect_saved_wifi(s.ssid, s.password, s.trusted_bssid)
        s.wifi_enabled = True
        if connected and bssid:
            s.trusted_bssid = bssid
        s.save()
        if connected:
            self.message = "CONNECTED"
        elif code == "OPEN":
            self.message = "OPEN BLOCK"
        elif code == "WEAK":
            self.message = "WEAK BLOCK"
        else:
            self.message = code

    def _check(self, mgr) -> None:
        self.message = "CHECKING"
        self.draw(mgr._display)
        ok, code, detail = check_connectivity()
        if ok:
            self.message = "ONLINE"
        elif detail:
            self.message = code + " " + detail
        else:
            self.message = code


class WifiScanScreen(ListScreen):
    title = "SELECT NETWORK"
    empty = "NO NETWORKS"

    def __init__(self, wifi, networks) -> None:
        super().__init__()
        self._wifi = wifi
        self._networks = networks

    def rows(self):
        return [(ui.clip(n[0], 14), "{}dB".format(n[1]), n[0]) for n in self._networks]

    def confirm(self):
        return "USE"

    def activate(self, mgr) -> None:
        self._wifi.picked_network(self.menu.key)
        mgr.pop()


# ── Credits (and the Debug unlock) ───────────────────────────────────────────

class CreditsScreen(Screen):
    """Credits. Secret: BOOT x5 unlocks the Debug menu; SELECT leaves."""

    accepts_disabled_buttons = True

    def __init__(self, settings) -> None:
        self._settings = settings
        self._boots = 0
        self._flash_until = 0
        self._title = ui.Marquee()

    async def enter(self, display, leds, mgr) -> None:
        _draw_credits_page(display, self._title)

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)
        if self._flash_until and time.ticks_diff(time.ticks_ms(), self._flash_until) >= 0:
            self._flash_until = 0
            _draw_credits_page(display, self._title)

    def handle_button(self, btn: str, mgr) -> None:
        # BOOT is repurposed here, so SELECT is the way back out.
        if btn == BOOT:
            self._boots += 1
            if self._boots >= _DEBUG_UNLOCK_PRESSES:
                self._boots = 0
                if not self._settings.debug_enabled:
                    self._settings.debug_enabled = True
                    self._settings.save()
                self._flash_until = time.ticks_add(time.ticks_ms(), _FLASH_MS)
                ui.dialog(mgr._display, "DEBUG", ("UNLOCKED",), kind="accent")
        elif btn == SELECT:
            mgr.pop()


# ── Debug ────────────────────────────────────────────────────────────────────

class DebugScreen(_SettingsList):
    """The Debug top level (group None) or one of its groups."""

    def __init__(self, settings, group=None, root=None) -> None:
        super().__init__(settings)
        self.group = group
        self.root = root
        self.title = "DEBUG" if group is None else _DEBUG_GROUPS[group][1]
        self._clear_armed = None    # (row key, deadline) awaiting a 2nd START

    def rows(self):
        keys = _DEBUG_TOP if self.group is None else _DEBUG_GROUPS[self.group][2]
        return [_debug_item(key, self.settings, self.pet) for key in keys]

    def confirm(self):
        return "OPEN" if self.menu.key in _DEBUG_GROUPS else "OK"

    def handle_button(self, btn: str, mgr) -> None:
        if btn in (LEFT, RIGHT, BOOT, SELECT):
            self._clear_armed = None
        super().handle_button(btn, mgr)

    def activate(self, mgr) -> None:
        global _PET_LEDS
        key = self.menu.key
        s = self.settings
        if key in _DEBUG_GROUPS:
            mgr.push(DebugScreen(s, key, self.root))
            return
        if key == "enable":
            # Debug Off: hide the menu again (Credits -> BOOT x5 brings it
            # back) and leave it.
            s.debug_enabled = False
            s.save()
            if self.root is not None:
                self.root.message = "DEBUG MENU HIDDEN"
            mgr.pop()
            return
        if key == "vendor":
            s.vendor_mode_enabled = not s.vendor_mode_enabled
            s.save()
            self.message = "VENDOR " + _on_off(s.vendor_mode_enabled)
        elif key == "fps":
            s.fps_enabled = not s.fps_enabled
            s.save()
            import fps_counter
            fps_counter.set_enabled(s.fps_enabled)   # live effect
            self.message = "FPS " + _on_off(s.fps_enabled)
        elif key == "ota_channel":
            self._cycle_ota_channel()
        elif key == "unlock_all":
            import character_manager
            import pet_state
            new = character_manager.unlock_all()
            for cls in new:
                pet_state.create_fresh(cls)   # same start as a Chi from a trade
            self.message = ("UNLOCKED %d CHI'S" % len(new)) if new else "ALL UNLOCKED"
        elif key == "lock_all":
            import character_manager
            locked = character_manager.lock_all_but_active()
            self.message = ("LOCKED %d CHI'S" % locked) if locked else "NONE TO LOCK"
        elif key in ("clear_stamps", "clear_challenges"):
            self._clear(key)
        elif key in ("level", "exp"):
            mgr.push(ValueEditorScreen(key, self.pet, self))
            return
        elif key == "resources":
            mgr.push(ResourcesScreen(s))
            return
        elif key == "character":
            mgr._buttons.clear()   # START both opens and confirms the picker
            mgr.push(ChiSelectScreen())
            return
        elif key == "splash":
            mgr._buttons.clear()
            mgr.push(SplashPickerScreen())
            return
        elif key == "buttons":
            mgr.push(ButtonTestScreen(s))
            return
        elif key == "leds":
            s.debug_led_cycle_enabled = False
            s.save()
            _PET_LEDS = None       # the LED test owns the strip
            mgr.push(LedTestScreen(s, self))
            return
        elif key == "bluetooth":
            from screens.ble_debug import BleDebugScreen
            mgr.push(BleDebugScreen())
            return
        self.redraw(mgr)

    def _clear(self, key: str) -> None:
        """Clear Stamps / Clear Challenges: the first START arms, a second
        START on the same row within _CLEAR_CONFIRM_MS clears."""
        now = time.ticks_ms()
        armed = self._clear_armed
        if armed is None or armed[0] != key or time.ticks_diff(now, armed[1]) > 0:
            self._clear_armed = (key, time.ticks_add(now, _CLEAR_CONFIRM_MS))
            self.message = "START AGAIN TO CLEAR"
            return
        self._clear_armed = None
        if key == "clear_stamps":
            import stamp_manager
            stamp_manager.clear()
            self.message = "STAMPS CLEARED"
        else:
            import challenge_manager
            challenge_manager.reset_progress()
            self.message = "CHALLENGES CLEARED"

    def _cycle_ota_channel(self) -> None:
        """Move to the next channel and forget the recorded OTA version.

        Channel version counters are independent, so the new channel may be on
        a lower number. Without clearing, the badge would refuse it as a
        downgrade and silently never update."""
        from settings_state import ota_channels
        s = self.settings
        channels = ota_channels()
        try:
            nxt = channels[(channels.index(s.ota_channel) + 1) % len(channels)]
        except ValueError:
            nxt = channels[0]
        if nxt == s.ota_channel:
            self.message = "CHANNEL " + nxt.upper()
            return
        s.ota_channel = nxt
        s.save()
        cleared = False
        try:
            import ota
            cleared = ota.clear_version()
        except Exception:
            pass
        self.message = nxt.upper() + (" - VER CLEARED" if cleared else " - NO VER")


class ValueEditorScreen(Screen):
    """Level or EXP: LEFT/RIGHT adjust, START saves, BACK cancels."""

    accepts_disabled_buttons = True

    def __init__(self, kind, pet, opener) -> None:
        self._kind = kind
        self._pet = pet
        self._opener = opener
        self._value = int(pet.level) if kind == "level" else int(pet.total_experience)
        self._title = ui.Marquee()

    async def enter(self, display, leds, mgr) -> None:
        self._draw(display)

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            self._opener.message = "CANCELLED"
            mgr.pop()
        elif btn == LEFT or btn == RIGHT:
            step = 1 if btn == RIGHT else -1
            if self._kind == "level":
                self._value = max(0, min(MAX_LEVEL, self._value + step))
            else:
                self._value = max(0, min(MAX_EXPERIENCE, self._value + step * _EXP_STEP))
            self._draw(mgr._display)
        elif btn == START:
            if self._kind == "level":
                self._pet.set_level(self._value)
                self._opener.message = "LEVEL SAVED"
            else:
                self._pet.set_progress(self._value)
                self._opener.message = "EXP SAVED"
            _light_pet_leds(mgr)   # show the new level/XP (and level-up) now
            mgr.pop()

    def _draw(self, display) -> None:
        if self._kind == "level":
            _draw_editor_page(display, "LEVEL", str(self._value),
                              "0-{}".format(MAX_LEVEL), self._title)
        else:
            _draw_editor_page(display, "EXP", str(self._value),
                              "0-{}".format(MAX_EXPERIENCE), self._title)


class ResourcesScreen(_SettingsList):
    """Pet Resources: START drains a resource, or fills an empty one."""

    title = "PET RESOURCES"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.menu.value_fg = _resource_value_fg

    def rows(self):
        return [(label, value, i) for i, (label, value) in enumerate(_resource_rows(self.pet))]

    def confirm(self):
        return "FILL" if self.menu.item and self.menu.item[1] == "0%" else "DRAIN"

    def activate(self, mgr) -> None:
        label, attr = _RESOURCE_DEFS[self.menu.key]
        if attr == "work":
            label = getattr(self.pet, "work_name", "Work")
        drain = getattr(self.pet, attr, 0) > 0
        setattr(self.pet, attr, 0.0 if drain else 100.0)
        self.pet.save()
        # Reflect the change on the red Alert LED immediately via the pet
        # screen beneath us (it shares this pet).
        con = _con_screen(mgr)
        if con is not None:
            con._update_alert(mgr._leds)
        self.message = ("DRAINED " if drain else "FILLED ") + ui.clip(label.upper(), 12)
        self.redraw(mgr)


class ChiSelectScreen(ListScreen):
    """Pick any Chi to make active (unlocking it); returns to the pet."""

    title = "CHI SELECT"
    empty = "NONE FOUND"

    def __init__(self) -> None:
        super().__init__()
        self._first = True

    def rows(self):
        import character_manager
        active = character_manager.get_active().id
        chars = character_manager.all_characters()
        if self._first:
            self._first = False
            for i, c in enumerate(chars):
                if c.id == active:
                    self.menu.sel = i
        return [(ui.clip(c.name, 14), "ACTIVE" if c.id == active else "SET", c.id)
                for c in chars]

    def confirm(self):
        return "SET"

    def activate(self, mgr) -> None:
        import character_manager
        cls = character_manager.find(self.menu.key)
        if cls is None:
            return
        character_manager.save(cls)   # persist active + unlock the chosen character
        from screens.conagotchi import ConagotchiScreen
        mgr.switch_to(ConagotchiScreen())


class SplashPickerScreen(ListScreen):
    """Choose the boot splash, or Random (a regular one each boot)."""

    title = "SPLASH"
    empty = "NONE FOUND"

    def __init__(self) -> None:
        super().__init__()
        self._first = True

    def rows(self):
        import splash_manager
        options = [""] + splash_manager.all_names()
        current = splash_manager.get_selected()
        rows = []
        for i, name in enumerate(options):
            if not name:
                label, tag = "Random", "AUTO"
            else:
                label = splash_manager.label_for(name)
                tag = "SPECIAL" if splash_manager.is_special(name) else "SET"
            if name == current:
                tag = "ACTIVE"
                if self._first:
                    self.menu.sel = i
            rows.append((ui.clip(label, 14), tag, name))
        self._first = False
        return rows

    def confirm(self):
        return "SET"

    def activate(self, mgr) -> None:
        import splash_manager
        name = self.menu.key
        splash_manager.set_selected(name)   # "" = random/auto each boot
        self.message = "AUTO" if not name else splash_manager.label_for(name)
        self.redraw(mgr)


class ButtonTestScreen(_SettingsList):
    """Choose how long the live button test runs."""

    title = "BUTTON TEST"
    confirm_verb = "TEST"

    def rows(self):
        return [("{} SECONDS".format(d), None, d) for d in _BTN_DURATIONS]

    def activate(self, mgr) -> None:
        mgr.push(ButtonLiveScreen(self.menu.key))


class ButtonLiveScreen(Screen):
    """Each button's row lights while held and reads DONE once pressed. Every
    press is part of the test (nothing navigates); it ends when time runs out."""

    accepts_disabled_buttons = True

    def __init__(self, seconds) -> None:
        self._seconds = seconds
        self._end = 0
        self._tested = set()
        self._sig = None
        self._title = ui.Marquee()

    async def enter(self, display, leds, mgr) -> None:
        self._end = time.ticks_add(time.ticks_ms(), self._seconds * 1000)
        _draw_button_live(display, (), self._tested, self._seconds, self._title)

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)
        remaining = time.ticks_diff(self._end, time.ticks_ms())
        if remaining <= 0:
            mgr.pop()
            return
        held = tuple(name for name, _label in _BTN_LIVE if mgr._buttons.raw_pressed(name))
        for name in held:
            self._tested.add(name)
        secs = remaining // 1000 + 1
        sig = (secs, held, frozenset(self._tested))
        if sig != self._sig:
            self._sig = sig
            _draw_button_live(display, held, self._tested, secs, self._title)

    def handle_button(self, btn: str, mgr) -> None:
        self._tested.add(btn)


class LedTestScreen(_SettingsList):
    """Toggle each LED; the pet's LEDs are paused while this owns the strip."""

    title = "LED TESTS"

    def __init__(self, settings, opener) -> None:
        super().__init__(settings)
        self._opener = opener
        self._states = [False] * (NUM_RGB_LEDS + 2)
        self._leds = None

    async def enter(self, display, leds, mgr) -> None:
        self._leds = leds
        self._all_off()
        self.message = "LED TESTS"
        await super().enter(display, leds, mgr)

    async def exit(self, display, leds, mgr) -> None:
        self._all_off()

    async def update(self, display, leds, mgr) -> None:
        await ListScreen.update(self, display, leds, mgr)   # no pet-LED ticking

    def rows(self):
        return [(label, value, i) for i, (label, value) in enumerate(_led_test_rows(self._states))]

    def back(self, mgr) -> None:
        self._all_off()
        self._opener.message = "LEDS OFF"
        mgr.pop()

    def activate(self, mgr) -> None:
        idx = self.menu.key
        if idx == _LED_EXIT:
            self.back(mgr)
            return
        if idx == _LED_ALL_OFF:
            self._all_off()
            self.message = "ALL OFF"
        else:
            self._states[idx] = not self._states[idx]
            self._apply()
            self.message = _led_label(idx).upper() + " " + _on_off(self._states[idx])
        self.redraw(mgr)

    def _apply(self) -> None:
        leds = self._leds
        leds.set_alert(self._states[_LED_ALERT])
        leds.set_raffle(self._states[_LED_RAFFLE])
        for idx in range(NUM_RGB_LEDS):
            color = _LED_TEST_COLORS[idx % len(_LED_TEST_COLORS)]
            leds.rgb[idx] = color if self._states[_LED_RGB_START + idx] else (0, 0, 0)
        leds.rgb.write()

    def _all_off(self) -> None:
        for idx in range(len(self._states)):
            self._states[idx] = False
        if self._leds is not None:
            self._leds.all_off()


class FactoryResetScreen(Screen):
    accepts_disabled_buttons = True

    def __init__(self) -> None:
        self._title = ui.Marquee()

    async def enter(self, display, leds, mgr) -> None:
        _draw_reset_page(display, self._title)

    async def update(self, display, leds, mgr) -> None:
        self._title.tick(display)

    def handle_button(self, btn: str, mgr) -> None:
        if btn == BOOT or btn == SELECT:
            mgr.pop()
        elif btn == START:
            _draw_reset_progress(mgr._display)
            try:
                import factory_reset
                factory_reset.wipe()
            except Exception:
                pass
            import machine
            time.sleep_ms(700)
            machine.reset()


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def _con_screen(mgr):
    from screens.conagotchi import ConagotchiScreen
    for screen in reversed(mgr._stack):
        if isinstance(screen, ConagotchiScreen):
            return screen
    return None


def _light_pet_leds(mgr) -> None:
    """Show a just-saved level/XP on the RGB LEDs now, by driving the pet
    screen beneath Settings, and keep animating them while Settings is open."""
    global _PET_LEDS
    con = _con_screen(mgr)
    if con is None:
        return
    con.refresh_leds(mgr._leds)
    _PET_LEDS = con


def _settings_rows(settings: BadgeSettings, group=None):
    """Settings rows as (label, value, key): the top level (group None) or
    one group. Debug is hidden until unlocked (Credits -> BOOT x5); Update is
    hidden when no OTA host is configured."""
    keys = _SETTINGS_TOP if group is None else _SETTINGS_GROUPS[group][2]
    rows = []
    for key in keys:
        if key == "debug" and not settings.debug_enabled:
            continue
        if key == "update":
            from config import OTA_BASE_URL
            if not OTA_BASE_URL:
                continue
        rows.append(_settings_item(key, settings))
    return rows


def _settings_item(key: str, settings: BadgeSettings):
    """One Settings row as (label, value, key)."""
    if key in _SETTINGS_GROUPS:
        return (_SETTINGS_GROUPS[key][0], "VIEW", key)
    if key == "wifi":
        return ("Wi-Fi", _wifi_label(settings), key)
    if key == "bluetooth":
        return ("Bluetooth", _on_off(settings.bluetooth_enabled), key)
    if key == "ir":
        return ("IR", _on_off(settings.ir_enabled), key)
    if key == "badge_mode":
        return ("Badge Mode", _badge_mode_label(settings), key)
    if key == "theme":
        import theme
        return ("Theme", theme.name().upper(), key)
    if key == "keyboard":
        return ("Keyboard", _keyboard_label(settings), key)
    if key == "text_size":
        return ("Text Size", getattr(settings, "text_size", "normal").upper(), key)
    if key == "update":
        return ("Update", _ota_version_label(), key)
    if key == "reset":
        return ("Factory Reset", "CLEAR", key)
    if key == "credits":
        return ("Credits", "VIEW", key)
    return ("Debug", "VIEW", key)


def _ota_version_label() -> str:
    """Installed OTA version for the Settings row, so a badge can be identified
    at a glance without entering the Update screen."""
    try:
        import ota
        return "V%d" % ota.local_version()
    except Exception:
        return "VIEW"


def _wifi_label(settings: BadgeSettings) -> str:
    """The radio's real state for the menu row, not just the boot setting."""
    status = wifi_status()
    return _on_off(status[0] if status else settings.wifi_enabled)


def _keyboard_label(settings: BadgeSettings) -> str:
    return "T9" if settings.keyboard == "t9" else "GRID"


def _badge_mode_label(settings: BadgeSettings) -> str:
    """CHI or BLINKY: short enough that "Badge Mode" fits beside it."""
    mode = settings.badge_mode
    return _MODE_LABELS.get(mode, ui.clip(mode.upper(), 8)) if mode else "-"


def _debug_rows(settings: BadgeSettings, pet: PetState, group=None):
    """The rows of the Debug top level (group None) or of one group."""
    keys = _DEBUG_TOP if group is None else _DEBUG_GROUPS[group][2]
    return [_debug_item(key, settings, pet) for key in keys]


def _debug_item(key: str, settings: BadgeSettings, pet: PetState):
    """One Debug row as (label, value, key)."""
    if key in _DEBUG_GROUPS:
        return (_DEBUG_GROUPS[key][0], "VIEW", key)
    labels = {
        "enable": ("Debug Off", None),
        "vendor": ("Vendor Mode", _on_off(settings.vendor_mode_enabled)),
        "level": ("Level", str(int(pet.level))),
        "exp": ("EXP", str(int(pet.total_experience))),
        "resources": ("Pet Resources", "VIEW"),
        "character": ("Chi Select", ui.clip(pet.name.upper(), 10)),
        "lock_all": ("Lock All Chi's", "RUN"),
        "clear_stamps": ("Clear Stamps", "RUN"),
        "clear_challenges": ("Clear Challenges", "RUN"),
        "buttons": ("Buttons", "TEST"),
        "leds": ("LED Test", "VIEW"),
        "bluetooth": ("Bluetooth", "VIEW"),
        "fps": ("FPS", _on_off(settings.fps_enabled)),
        "ota_channel": ("Update Channel", settings.ota_channel.upper() or "-"),
    }
    if key == "unlock_all":
        return ("Unlock All Chi's", _chi_count(), key)
    if key == "splash":
        return ("Splash", _splash_value(), key)
    label, value = labels[key]
    return (label, value, key)


def _chi_count() -> str:
    """Collected/total Chi's, the value beside Unlock All Chi's."""
    import character_manager
    return "%d/%d" % (len(character_manager.get_unlocked()),
                      len(character_manager.all_characters()))


def _splash_value() -> str:
    """Current splash label, or AUTO when none is stored (random each boot)."""
    try:
        import splash_manager
        sel = splash_manager.get_selected()
        return splash_manager.label_for(sel) if sel else "AUTO"
    except Exception:
        return "AUTO"


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


def _resource_rows(pet):
    """(label, "NN%") rows for the Pet Resources editor; Work uses work_name."""
    rows = []
    for label, attr in _RESOURCE_DEFS:
        if attr == "work":
            label = ui.clip(getattr(pet, "work_name", "Work"), 12)
        val = int(max(0, min(100, getattr(pet, attr, 0))))
        rows.append((label, "{}%".format(val)))
    return tuple(rows)


def _resource_value_fg(value: str) -> int:
    """Colour the % value red when at/below the low-resource alert threshold."""
    import theme
    th = theme.get()
    try:
        import pet_state
        return th.danger if int(value.rstrip("%")) <= pet_state.LOW_THRESHOLD else th.success
    except (ValueError, ImportError):
        return th.muted


# ── Pages that are not lists ─────────────────────────────────────────────────

def _draw_credits_page(display, marquee=None) -> None:
    ui.screen(display, "CREDITS", marquee=marquee)
    if ui.list_scale() == 2:
        # Large text: tighter lines, and the last name split to fit the glass.
        ui.text_lines(display, ("OzSec 2026", ("Conagotchi", "muted")), 44,
                      line_h=18, scale=2)
        ui.text_lines(display, ("Contributors:", ("rufflabs", "muted"),
                                ("baum", "muted"), ("Claude and", "muted"),
                                ("Codex", "muted")), 88, line_h=18, scale=2)
    else:
        ui.text_lines(display, ("OzSec 2026", ("Conagotchi", "muted")), 56, line_h=20)
        ui.text_lines(display, ("Contributors:", ("rufflabs", "muted"),
                                ("baum", "muted"), ("Claude and Codex", "muted")),
                      108, line_h=20)
    ui.controls(display)


def _draw_editor_page(display, title: str, value: str, bounds: str, marquee=None) -> None:
    ui.screen(display, title, marquee=marquee)
    ui.value_picker(display, value, hint="LEFT/RIGHT ADJUSTS", detail=bounds)
    ui.controls(display, "SAVE")


def _draw_button_live(display, held, tested, secs: int, marquee=None) -> None:
    """A button's row lights while it is held, and reads DONE once pressed."""
    import theme
    th = theme.get()
    ui.screen(display, "BUTTON TEST", marquee=marquee)
    # Normal-size rows whatever the menu text size: all five buttons must fit.
    for i, (name, label) in enumerate(_BTN_LIVE):
        ui.row(display, th.row_top + i * th.row_h, label,
               "DONE" if name in tested else "-",
               fill="success" if name in held else None,
               value_fg=lambda v: th.success if v == "DONE" else th.muted, scale=1)
    ui.message(display, "{}s  TESTED {}/{}".format(secs, len(tested), len(_BTN_LIVE)),
               "muted")
    ui.bottom_line(display, "TESTING...")


def _draw_reset_page(display, marquee=None) -> None:
    ui.screen(display, "FACTORY RESET", marquee=marquee)
    ui.status(display, "ERASE ALL DATA?", 58, "danger")
    ui.paragraph(display, "Character, stamps, pet state and settings "
                 "will be wiped and the badge will reboot.", 82, line_h=16)
    ui.status(display, "CANNOT BE UNDONE", 172, "danger")
    ui.controls(display, "WIPE")


def _draw_reset_progress(display) -> None:
    ui.clear(display)
    ui.text_lines(display, (("RESETTING", "danger"), ("REBOOTING...", "muted")),
                  104, line_h=24)


def _on_off(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _mask(text: str) -> str:
    if not text:
        return "<empty>"
    if len(text) <= 10:
        return "*" * len(text)
    return "*" * 9 + ">"
