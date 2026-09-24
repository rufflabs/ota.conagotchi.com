import asyncio
import network
from config import WIFI_SSID, WIFI_PASSWORD, WIFI_TIMEOUT_S


class Wifi:
    def __init__(self):
        self._wlan = network.WLAN(network.STA_IF)
        self._wlan.active(False)

    async def connect(self, ssid=None, password=None) -> bool:
        """Attempt to connect; return True on success.

        ssid/password default to the config values, but callers should pass the
        user's saved credentials (BadgeSettings) so a badge joined to a
        different network than the shipped default still connects."""
        ssid = ssid or WIFI_SSID
        password = password or WIFI_PASSWORD
        self._wlan.active(True)
        if self._wlan.isconnected():
            return True

        self._wlan.connect(ssid, password)
        for _ in range(WIFI_TIMEOUT_S * 10):
            if self._wlan.isconnected():
                print("WiFi connected:", self._wlan.ifconfig())
                return True
            await asyncio.sleep_ms(100)

        print("WiFi connect timeout:", ssid)
        return False

    def disconnect(self):
        """Drop the link and power the radio down (safe to call when idle)."""
        try:
            self._wlan.disconnect()
        except Exception:
            pass  # not associated; powering down is all that matters
        self._wlan.active(False)

    @property
    def connected(self) -> bool:
        return self._wlan.isconnected()

    @property
    def ip(self) -> str:
        return self._wlan.ifconfig()[0] if self.connected else ""
