import asyncio
import time

from machine import UART, Pin
from config import (
    PIN_LINK_TX, PIN_LINK_RX, LINK_BAUD,
    PIN_IR_TX, PIN_IR_RX, IR_FREQ_HZ,
)

try:
    from esp32 import RMT
except ImportError:
    RMT = None


_IR_MAGIC = b"OZ"
_IR_MAX_PAYLOAD = 48
_IR_CLOCK_DIV = 80          # 1 us RMT pulse units from the ESP32 80 MHz clock.
_IR_RMT_CHANNEL = 0
_IR_DUTY_PERCENT = 50       # Stronger TX carrier for the narrow side-looking IR LED.

_LEADER_MARK_US = 2400
_LEADER_SPACE_US = 1200
_BIT_MARK_US = 560
_ZERO_SPACE_US = 560
_ONE_SPACE_US = 1680
_TRAILER_MARK_US = 560
_RX_IDLE_MS = 20
_RX_MAX_PULSES = 900
_RX_MARK_LEVEL = 0          # TSOP-style receivers idle high and pull low on mark.
_RX_SPACE_LEVEL = 1


_WIRED_RX_CAP = 256         # trim the RX buffer if it grows past this many bytes.


class WiredLink:
    """Badge-to-badge communication over the LINK connector (UART).

    Packets are framed identically to :class:`IrLink` (``_make_frame``) so the
    two transports are interchangeable: ``send`` takes a raw payload and frames
    it, while ``available``/``read`` return whole decoded payloads. This lets
    OzConBase drive a trade over either link with the same code.
    """

    def __init__(self):
        self._uart = UART(
            1,
            baudrate=LINK_BAUD,
            tx=Pin(PIN_LINK_TX),
            rx=Pin(PIN_LINK_RX),
        )
        self._rx_buf = b""
        self._rx_packets = []

    def send(self, data: bytes):
        """Frame and transmit one packet payload."""
        self._uart.write(_make_frame(bytes(data)))

    def available(self) -> int:
        """Return the number of complete packets queued for reading."""
        self._pump()
        return len(self._rx_packets)

    def read(self, n: int = -1) -> bytes:
        """Return the next complete packet payload, or b"" if none is ready."""
        self._pump()
        if not self._rx_packets:
            return b""
        data = self._rx_packets.pop(0)
        if n is not None and n >= 0:
            return data[:n]
        return data

    async def read_line(self) -> str:
        """Read packets until a newline-terminated text payload arrives."""
        buf = b""
        while True:
            pkt = self.read()
            if pkt:
                idx = pkt.find(b"\n")
                if idx >= 0:
                    buf += pkt[:idx]
                    return buf.decode()
                buf += pkt
            else:
                await asyncio.sleep_ms(10)

    def deinit(self) -> None:
        """Release the UART."""
        try:
            self._uart.deinit()
        except Exception:
            pass

    def _pump(self) -> None:
        data = self._uart.read()
        if not data:
            return
        self._rx_buf += data
        packets, self._rx_buf = _scan_frames(self._rx_buf)
        if len(self._rx_buf) > _WIRED_RX_CAP:
            self._rx_buf = self._rx_buf[-(_WIRED_RX_CAP // 4):]
        if packets:
            self._rx_packets.extend(packets)


class IrLink:
    """Badge-to-badge IR packet link.

    The transmitter uses ESP32 RMT with a 38 kHz carrier. The receiver uses edge
    timing from the demodulated IR receiver output because MicroPython's RMT
    receive path is not available on ESP32.
    """

    def __init__(self):
        if RMT is None:
            raise RuntimeError("ESP32 RMT is not available")

        self._tx = RMT(
            _IR_RMT_CHANNEL,
            pin=_make_ir_tx_pin(),
            clock_div=_IR_CLOCK_DIV,
            idle_level=0,
            tx_carrier=(IR_FREQ_HZ, _IR_DUTY_PERCENT, 1),
        )
        self._rx = Pin(PIN_IR_RX, Pin.IN, Pin.PULL_UP)
        self._rx_levels = bytearray(_RX_MAX_PULSES)
        self._rx_durations = [0] * _RX_MAX_PULSES
        self._rx_count = 0
        self._rx_overflow = False
        self._rx_packets = []
        self._last_level = self._rx.value()
        self._last_edge_us = time.ticks_us()
        self._last_edge_ms = time.ticks_ms()
        self._enable_rx_irq()

    def send(self, data: bytes):
        """Transmit one framed IR packet."""
        payload = bytes(data)
        frame = _make_frame(payload)
        pulses = _encode_frame(frame)

        self._disable_rx_irq()
        try:
            self._reset_capture()
            self._tx.write_pulses(pulses, 1)
            self._tx.wait_done(timeout=250)
            self._reset_capture()
        finally:
            self._enable_rx_irq()

    def available(self) -> int:
        """Return the number of received packets queued for reading."""
        self._decode_if_idle()
        return len(self._rx_packets)

    def read(self, n: int = -1) -> bytes:
        """Return the next complete IR packet payload, or b"" if none is ready."""
        self._decode_if_idle()
        if not self._rx_packets:
            return b""
        data = self._rx_packets.pop(0)
        if n is not None and n >= 0:
            return data[:n]
        return data

    async def read_line(self) -> str:
        """Read packets until a newline-terminated text payload arrives."""
        buf = b""
        while True:
            pkt = self.read()
            if pkt:
                idx = pkt.find(b"\n")
                if idx >= 0:
                    buf += pkt[:idx]
                    return buf.decode()
                buf += pkt
            else:
                await asyncio.sleep_ms(10)

    def deinit(self) -> None:
        """Release IR resources."""
        self._disable_rx_irq()
        try:
            self._tx.deinit()
        except Exception:
            pass

    def _enable_rx_irq(self) -> None:
        self._rx.irq(
            trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
            handler=self._on_rx_edge,
        )

    def _disable_rx_irq(self) -> None:
        self._rx.irq(handler=None)

    def _reset_capture(self) -> None:
        self._rx_count = 0
        self._rx_overflow = False
        self._last_level = self._rx.value()
        self._last_edge_us = time.ticks_us()
        self._last_edge_ms = time.ticks_ms()

    def _on_rx_edge(self, pin) -> None:
        now_us = time.ticks_us()
        duration = time.ticks_diff(now_us, self._last_edge_us)
        level = self._last_level
        self._last_edge_us = now_us
        self._last_edge_ms = time.ticks_ms()
        self._last_level = pin.value()

        idx = self._rx_count
        if idx < _RX_MAX_PULSES:
            self._rx_levels[idx] = level
            self._rx_durations[idx] = duration
            self._rx_count = idx + 1
        else:
            self._rx_overflow = True

    def _decode_if_idle(self) -> None:
        if self._rx_count == 0:
            return
        if time.ticks_diff(time.ticks_ms(), self._last_edge_ms) < _RX_IDLE_MS:
            return

        self._disable_rx_irq()
        try:
            count = self._rx_count
            overflow = self._rx_overflow
            levels = bytes(self._rx_levels[:count])
            durations = self._rx_durations[:count]
            self._reset_capture()
        finally:
            self._enable_rx_irq()

        if overflow:
            return
        packet = _decode_pulses(levels, durations)
        if packet is not None:
            self._rx_packets.append(packet)


def _make_ir_tx_pin():
    try:
        return Pin(PIN_IR_TX, Pin.OUT, drive=Pin.DRIVE_3)
    except (AttributeError, TypeError):
        return Pin(PIN_IR_TX, Pin.OUT)


def _make_frame(payload: bytes) -> bytes:
    if len(payload) > _IR_MAX_PAYLOAD:
        raise ValueError("IR payload too large")
    body = _IR_MAGIC + bytes((len(payload),)) + payload
    return body + bytes((_checksum(body),))


def _checksum(data: bytes) -> int:
    total = 0
    for b in data:
        total = (total + b) & 0xFF
    return total


def _encode_frame(frame: bytes) -> tuple:
    pulses = [_LEADER_MARK_US, _LEADER_SPACE_US]
    for b in frame:
        for bit in range(7, -1, -1):
            pulses.append(_BIT_MARK_US)
            if b & (1 << bit):
                pulses.append(_ONE_SPACE_US)
            else:
                pulses.append(_ZERO_SPACE_US)
    pulses.append(_TRAILER_MARK_US)
    return tuple(pulses)


def _decode_pulses(levels: bytes, durations: list):
    count = min(len(levels), len(durations))
    start = _find_leader(levels, durations, count)
    if start < 0:
        return None

    idx = start + 2
    byte_value = 0
    bit_count = 0
    out = bytearray()
    expected_len = None

    while idx + 1 < count:
        mark_level = levels[idx]
        mark_us = durations[idx]
        space_level = levels[idx + 1]
        space_us = durations[idx + 1]
        if mark_level != _RX_MARK_LEVEL or not _near(mark_us, _BIT_MARK_US):
            break
        if space_level != _RX_SPACE_LEVEL:
            break

        if _near(space_us, _ZERO_SPACE_US):
            bit = 0
        elif _near(space_us, _ONE_SPACE_US):
            bit = 1
        else:
            break

        byte_value = (byte_value << 1) | bit
        bit_count += 1
        if bit_count == 8:
            out.append(byte_value)
            byte_value = 0
            bit_count = 0
            if len(out) == 3:
                expected_len = 4 + out[2]
                if expected_len > _IR_MAX_PAYLOAD + 4:
                    return None
            if expected_len is not None and len(out) >= expected_len:
                return _decode_frame(bytes(out[:expected_len]))
        idx += 2
    return None


def _find_leader(levels: bytes, durations: list, count: int) -> int:
    for idx in range(0, count - 1):
        if levels[idx] != _RX_MARK_LEVEL or levels[idx + 1] != _RX_SPACE_LEVEL:
            continue
        if _near(durations[idx], _LEADER_MARK_US) and _near(durations[idx + 1], _LEADER_SPACE_US):
            return idx
    return -1


def _scan_frames(buf: bytes):
    """Extract complete framed packets from a byte stream.

    Returns (payloads, remaining) where remaining holds the trailing bytes that
    do not yet form a whole frame (kept for the next read).
    """
    packets = []
    i = 0
    n = len(buf)
    while True:
        start = buf.find(_IR_MAGIC, i)
        if start < 0:
            # No full magic left. Retain only a trailing byte that could be the
            # first half of a magic split across the next read; drop the rest.
            if n > i and buf[n - 1:n] == _IR_MAGIC[:1]:
                i = n - 1
            else:
                i = n
            break
        if start + 3 > n:
            i = start
            break
        length = buf[start + 2]
        if length > _IR_MAX_PAYLOAD:
            i = start + 1          # bogus length — resync past this magic byte.
            continue
        end = start + 4 + length   # magic(2) + len(1) + payload + checksum(1)
        if end > n:
            i = start
            break
        frame = buf[start:end]
        if _checksum(frame[:-1]) == frame[-1]:
            packets.append(bytes(frame[3:-1]))
            i = end
        else:
            i = start + 1          # bad checksum — resync.
    return packets, buf[i:]


def _decode_frame(frame: bytes):
    if len(frame) < 4:
        return None
    if frame[0:2] != _IR_MAGIC:
        return None
    payload_len = frame[2]
    if len(frame) != payload_len + 4:
        return None
    if _checksum(frame[:-1]) != frame[-1]:
        return None
    return frame[3:-1]


def _near(actual: int, target: int) -> bool:
    tolerance = max(300, target // 3)
    return target - tolerance <= actual <= target + tolerance


# ── BLE badge-to-badge link ───────────────────────────────────────────────────

class BleLink:
    """Connectionless badge-to-badge link over BLE advertising.

    Same interface as WiredLink / IrLink (send / available / read / deinit), so
    it drops into the trade code as another transport. `send(payload)` beacons
    the (compacted) trade payload as a manufacturer-specific advertisement;
    scanning runs continuously and decoded peer payloads are queued for read().
    Adverts weaker than `rssi_min` are dropped so only nearby badges register.

    Advertising is NOT started until the first send(); call stop_advertising()
    to go quiet (used to close the pairing window) while still scanning.
    """

    def __init__(self, rssi_min=None, adv_interval_us=None):
        import bluetooth
        import ble as _ble
        from config import BLE_RSSI_MIN, BLE_ADV_INTERVAL_US

        self._ble_mod = _ble
        self._rssi_min = BLE_RSSI_MIN if rssi_min is None else rssi_min
        self._interval = BLE_ADV_INTERVAL_US if adv_interval_us is None else adv_interval_us
        self._queue = []
        self._advertising = False

        # Power on the BLE radio before any scan/advertise. There is no user
        # Bluetooth toggle anymore and apply_radios() leaves BT off at boot, so
        # the trade owns turning the radio on. active(True) is synchronous on
        # ESP32; guard it so we never scan/advertise on a cold radio.
        self._radio = bluetooth.BLE()
        self._radio.active(True)
        for _ in range(50):
            if self._radio.active():
                break
            time.sleep_ms(10)
        self._radio.irq(self._irq)
        # Continuous passive scan (duration 0 = indefinite).
        try:
            self._radio.gap_scan(0, 30000, 30000, False)
        except Exception:
            pass

    def _irq(self, event, data):
        if event != self._ble_mod.IRQ_SCAN_RESULT:
            return
        addr_type, addr, adv_type, rssi, adv_data = data
        if rssi < self._rssi_min:
            return
        payload = self._ble_mod.decode_adv(bytes(adv_data))
        if payload is not None and len(self._queue) < 16:
            self._queue.append(payload)

    def send(self, data: bytes):
        """Beacon one trade payload; ignored if it will not fit an advert."""
        adv = self._ble_mod.encode_adv(bytes(data))
        if adv is None:
            return
        self._radio.gap_advertise(self._interval, adv_data=adv, connectable=False)
        self._advertising = True

    def stop_advertising(self) -> None:
        try:
            self._radio.gap_advertise(None)
        except Exception:
            pass
        self._advertising = False

    def available(self) -> int:
        return len(self._queue)

    def read(self, n: int = -1) -> bytes:
        if not self._queue:
            return b""
        data = self._queue.pop(0)
        if n is not None and n >= 0:
            return data[:n]
        return data

    def deinit(self) -> None:
        self.stop_advertising()
        try:
            self._radio.gap_scan(None)
        except Exception:
            pass
        try:
            self._radio.irq(None)
        except Exception:
            pass
        # Power the BLE radio back down when the trade ends (the trade owns the
        # radio; there is no user Bluetooth toggle keeping it on).
        try:
            self._radio.active(False)
        except Exception:
            pass
