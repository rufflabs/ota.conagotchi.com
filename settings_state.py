"""Persistent badge settings."""
import os
import time

from config import WIFI_PASSWORD, WIFI_SSID


_SAVE_DIR = "data"
_SAVE_FILE = _SAVE_DIR + "/settings.txt"
_BLE = None


class BadgeSettings:
    def __init__(self) -> None:
        self.wifi_enabled = False
        self.bluetooth_enabled = False
        self.ssid = WIFI_SSID
        self.password = WIFI_PASSWORD
        self.trusted_bssid = ""
        self.debug_enabled = False
        self.debug_led_cycle_enabled = False
        self.vendor_mode_enabled = False
        self.fps_enabled = False
        self.load()

    def load(self) -> None:
        try:
            with open(_SAVE_FILE) as f:
                for line in f:
                    key, _, value = line.strip().partition("=")
                    if key == "wifi_enabled":
                        self.wifi_enabled = value == "1"
                    elif key == "bluetooth_enabled":
                        self.bluetooth_enabled = value == "1"
                    elif key == "ssid":
                        self.ssid = value or WIFI_SSID
                    elif key == "password":
                        self.password = value or WIFI_PASSWORD
                    elif key == "trusted_bssid":
                        self.trusted_bssid = value
                    elif key == "debug_enabled":
                        self.debug_enabled = value == "1"
                    elif key == "debug_led_cycle_enabled":
                        self.debug_led_cycle_enabled = value == "1"
                    elif key == "vendor_mode_enabled":
                        self.vendor_mode_enabled = value == "1"
                    elif key == "fps_enabled":
                        self.fps_enabled = value == "1"
        except OSError:
            pass

    def save(self) -> None:
        _ensure_dir()
        with open(_SAVE_FILE, "w") as f:
            f.write("wifi_enabled={}\n".format(1 if self.wifi_enabled else 0))
            f.write("bluetooth_enabled={}\n".format(1 if self.bluetooth_enabled else 0))
            f.write("ssid={}\n".format(self.ssid))
            f.write("password={}\n".format(self.password))
            f.write("trusted_bssid={}\n".format(self.trusted_bssid))
            f.write("debug_enabled={}\n".format(1 if self.debug_enabled else 0))
            f.write("debug_led_cycle_enabled={}\n".format(1 if self.debug_led_cycle_enabled else 0))
            f.write("vendor_mode_enabled={}\n".format(1 if self.vendor_mode_enabled else 0))
            f.write("fps_enabled={}\n".format(1 if self.fps_enabled else 0))

    def reset_ssid(self) -> None:
        self.ssid = WIFI_SSID
        self.save()

    def reset_network(self) -> None:
        self.wifi_enabled = False
        self.ssid = WIFI_SSID
        self.password = WIFI_PASSWORD
        self.trusted_bssid = ""
        self.save()

    def forget_network(self) -> None:
        self.wifi_enabled = False
        self.trusted_bssid = ""
        self.save()

    def apply_radios(self) -> tuple:
        """Apply saved radio settings and return actual (wifi, bluetooth) states."""
        changed = False
        wifi_actual = set_wifi_enabled(self.wifi_enabled)
        if wifi_actual is not None and wifi_actual != self.wifi_enabled:
            self.wifi_enabled = wifi_actual
            changed = True

        bluetooth_actual = set_bluetooth_enabled(self.bluetooth_enabled)
        if bluetooth_actual is not None and bluetooth_actual != self.bluetooth_enabled:
            self.bluetooth_enabled = bluetooth_actual
            changed = True

        if changed:
            self.save()
        return wifi_actual, bluetooth_actual


def set_wifi_enabled(enable: bool):
    """Turn the Wi-Fi radio on/off, returning the actual active state or None."""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if enable:
            wlan.active(True)
        else:
            if wlan.active():
                try:
                    wlan.disconnect()
                except Exception:
                    pass
            wlan.active(False)
        return bool(wlan.active())
    except Exception:
        return None


def connect_saved_wifi(ssid: str, password: str, trusted_bssid: str = "") -> tuple:
    """Connect only to a saved, non-open AP. Returns (connected, code, bssid)."""
    if not ssid or not password:
        return False, "LOGIN", ""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        ap, code = _find_saved_ap(wlan, ssid, trusted_bssid)
        if ap is None:
            return False, code, trusted_bssid
        bssid, authmode = ap
        try:
            wlan.disconnect()
        except Exception:
            pass
        wlan.connect(ssid, password, bssid=bssid)
        deadline = _ticks_add(_ticks_ms(), 6000)
        while _ticks_diff(deadline, _ticks_ms()) > 0:
            if wlan.isconnected():
                return True, "CONNECTED", _bssid_hex(bssid)
            _sleep_ms(100)
        return False, "TIMEOUT", _bssid_hex(bssid)
    except Exception:
        return False, "ERROR", trusted_bssid


def scan_wifi_networks(limit: int = 8) -> list:
    """Return visible secured Wi-Fi networks sorted strongest first."""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        found = {}
        for item in wlan.scan():
            ssid = _ssid_text(item[0])
            if not ssid:
                continue
            authmode = int(item[4])
            if authmode <= 1:
                continue
            rssi = int(item[3])
            bssid = _bssid_hex(item[1])
            if ssid not in found or rssi > found[ssid][1]:
                found[ssid] = (ssid, rssi, bssid)
        networks = list(found.values())
        networks.sort(key=lambda row: row[1], reverse=True)
        return networks[:limit]
    except Exception:
        return []


def _net_check_config() -> tuple:
    """(url, expect, timeout_s) from config, with defaults if the keys are absent."""
    try:
        import config
        return (
            getattr(config, "NET_CHECK_URL", ""),
            getattr(config, "NET_CHECK_EXPECT", "success"),
            int(getattr(config, "NET_CHECK_TIMEOUT_S", 5)),
        )
    except Exception:
        return "", "success", 5


def _http_get(url: str, timeout_s: int):
    """GET a URL, tolerating a bundled `requests` with no timeout kwarg."""
    import requests
    try:
        return requests.get(url, timeout=timeout_s)
    except TypeError:
        return requests.get(url)


def check_connectivity(url: str = "", expect=None, timeout_s: int = 0) -> tuple:
    """Probe a plain-HTTP endpoint to tell real reachability from a captive portal.

    Returns (ok, code, detail). `ok` is True only when the endpoint answers 200
    with the expected body; `code` is a short token for the settings display.
    A 200 carrying the wrong body, or a redirect, means a portal is intercepting.
    """
    cfg_url, cfg_expect, cfg_timeout = _net_check_config()
    url = url or cfg_url
    expect = cfg_expect if expect is None else expect
    timeout_s = timeout_s or cfg_timeout
    if not url:
        return False, "NO URL", ""

    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if not wlan.active() or not wlan.isconnected():
            return False, "NO LINK", ""
    except Exception:
        return False, "NO LINK", ""

    status = None
    body = ""
    detail = ""
    resp = None
    try:
        resp = _http_get(url, timeout_s)
        status = int(resp.status_code)
        body = resp.text or ""
    except Exception as exc:
        detail = _err_token(exc)
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    if status is None:
        return False, "NO REPLY", detail
    if status in (301, 302, 303, 307, 308):
        return False, "PORTAL", str(status)
    if status != 200:
        return False, "HTTP %d" % status, ""
    want = expect.strip().lower()
    if not want or body.strip().lower().startswith(want):
        return True, "ONLINE", ""
    return False, "PORTAL", ""


def _err_token(exc) -> str:
    """Short, display-safe name for an exception."""
    name = type(exc).__name__
    return name[:12] if name else "ERR"


def set_bluetooth_enabled(enable: bool):
    """Turn BLE on/off, returning the actual active state or None."""
    global _BLE
    try:
        import bluetooth
        if _BLE is None:
            _BLE = bluetooth.BLE()
        _BLE.active(enable)
        if enable:
            configure_bluetooth_security()
        return bool(_BLE.active())
    except Exception:
        return None


def configure_bluetooth_security() -> str:
    """Enable BLE and request LE Secure Connections with bonding + MITM."""
    global _BLE
    try:
        import bluetooth
        if _BLE is None:
            _BLE = bluetooth.BLE()
        _BLE.active(True)
        try:
            _BLE.config(bond=True, mitm=True, le_secure=True, io=1)
            return "SECURE"
        except Exception:
            try:
                _BLE.config(bond=True, mitm=True, io=1)
                return "LIMITED"
            except Exception:
                return "LIMITED"
    except Exception:
        return "N/A"


def forget_bluetooth_devices() -> bool:
    """Clear app-level Bluetooth trust for now by disabling the BLE radio."""
    return set_bluetooth_enabled(False) is False


def _ensure_dir() -> None:
    try:
        os.mkdir(_SAVE_DIR)
    except OSError:
        pass


def _find_saved_ap(wlan, ssid: str, trusted_bssid: str) -> tuple:
    candidates = []
    try:
        for item in wlan.scan():
            name = _ssid_text(item[0])
            if name == ssid:
                candidates.append(item)
    except Exception:
        return None, "SCAN ERR"
    if not candidates:
        return None, "NO AP"

    if trusted_bssid:
        trusted = trusted_bssid.lower()
        for item in candidates:
            if _bssid_hex(item[1]) == trusted:
                authmode = int(item[4])
                if authmode == 0:
                    return None, "OPEN"
                if authmode == 1:
                    return None, "WEAK"
                return (item[1], authmode), "OK"
        return None, "AP CHANGED"

    best = None
    for item in candidates:
        authmode = int(item[4])
        if authmode <= 1:
            continue
        if best is None or int(item[3]) > int(best[3]):
            best = item
    if best is None:
        return None, "OPEN"
    return (best[1], int(best[4])), "OK"


def _ssid_text(raw) -> str:
    try:
        if isinstance(raw, bytes):
            return raw.decode()
    except Exception:
        pass
    return str(raw)


def _bssid_hex(raw) -> str:
    try:
        import ubinascii
    except ImportError:
        import binascii as ubinascii
    try:
        return ubinascii.hexlify(raw).decode().lower()
    except Exception:
        return ""


def _ticks_ms() -> int:
    try:
        return time.ticks_ms()
    except AttributeError:
        return int(time.time() * 1000)


def _ticks_add(ticks: int, delta: int) -> int:
    try:
        return time.ticks_add(ticks, delta)
    except AttributeError:
        return ticks + delta


def _ticks_diff(end: int, start: int) -> int:
    try:
        return time.ticks_diff(end, start)
    except AttributeError:
        return end - start


def _sleep_ms(ms: int) -> None:
    try:
        time.sleep_ms(ms)
    except AttributeError:
        time.sleep(ms / 1000)
