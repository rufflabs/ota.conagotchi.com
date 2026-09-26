import asyncio
import network
from config import WIFI_SSID, WIFI_PASSWORD, WIFI_TIMEOUT_S


class Wifi:
    def __init__(self):
        # Leave the radio as it is: powering it off here dropped a badge that
        # was already connected (a needless deauth) before connect() rejoined.
        self._wlan = network.WLAN(network.STA_IF)

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

        from settings_state import limit_reconnects, stop_connecting
        limit_reconnects(self._wlan)
        self._wlan.connect(ssid, password)
        for _ in range(WIFI_TIMEOUT_S * 10):
            if self._wlan.isconnected():
                print("WiFi connected:", self._wlan.ifconfig())
                return True
            if self._wlan.status() == getattr(network, "STAT_WRONG_PASSWORD", None):
                break
            await asyncio.sleep_ms(100)

        # Cancel, or the driver keeps retrying (and drawing deauths) after we
        # have reported failure.
        stop_connecting(self._wlan)
        print("WiFi connect failed:", ssid)
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
