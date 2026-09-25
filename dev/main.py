import asyncio
import gc

import display as disp
from buttons import Buttons
from leds import Leds
from screen_manager import ScreenManager
from settings_state import BadgeSettings
from screens.splash import SplashScreen


async def main():
    print("Badge booting...")

    # Finish any OTA file-commit that was interrupted by a power loss before the
    # app touches those files. No-op unless data/ota_pending exists.
    try:
        import ota
        if ota.resume_if_pending():
            print("OTA: recovered interrupted update")
    except Exception as e:
        print("OTA resume skipped:", e)

    display = disp.init()
    buttons = Buttons()
    leds    = Leds()
    settings = BadgeSettings()
    settings.apply_radios()

    import fps_counter
    fps_counter.set_enabled(settings.fps_enabled)   # restore persisted overlay state
    # Note: navigation buttons are never disabled app-wide anymore (the button
    # test is a timed live check, not a per-button toggle), so nothing to apply.

    gc.collect()
    print(f"Free RAM: {gc.mem_free()} bytes")

    mgr = ScreenManager(display, leds, buttons)
    await mgr.boot(SplashScreen())

    async def button_loop():
        while True:
            btn = await buttons.get()
            mgr.handle_button(btn)

    async def update_loop():
        while True:
            await mgr.update()
            fps_counter.draw(display)    # top-center overlay, only when enabled
            await asyncio.sleep_ms(mgr.next_update_ms())

    print("Badge ready.")
    await asyncio.gather(button_loop(), update_loop())


asyncio.run(main())
