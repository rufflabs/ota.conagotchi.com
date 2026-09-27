"""Vendor stamping over Bluetooth, with no drawing. Two roles:

StampBeacon     a vendor badge. Quiet until the vendor presses STAMP
                (stamp()): then it advertises OZS1:<vendor id>:<its badge id>
                for up to STAMP_WINDOW_MS. A badge not yet stamped always wins
                the press: its reply is logged and closes the window at once.
                Badges already stamped (people still at the booth) cannot take
                a press; if only they reply, it ends as "already had" after
                REPEAT_GRACE_MS. One press, one new stamp.
StampCollector  an attendee badge. Collects a vendor's stamp once it has
                heard STAMP_HITS of its beacons in a row at STAMP_RSSI_MIN or
                stronger (badges held close), then replies OZA1:<vendor id>:
                <its badge id> for REPLY_MS, renewed each time that vendor is
                heard, so the vendor can log who it stamped.

Bluetooth only: no cable or IR (user decision), through badge_radio.BadgeRadio,
so stamps are signed when the badge holds the radio key and a forged beacon
or reply is ignored. A screen owns one, calls
start(), poll() from update(), and stop() on exit. The reply is best effort: an
attendee who leaves within a second may keep the stamp without the vendor
logging it.
"""
import time

import stamp_manager
from badge_radio import BadgeRadio, remember

# Proximity for stamps, stricter than trades (config.BLE_RSSI_MIN): two badges
# side by side read about -39 to -46 dB. Higher (less negative) = closer.
# Measure with Settings -> Debug -> Hardware -> Bluetooth -> Receive.
STAMP_RSSI_MIN = -48
STAMP_HITS = 3         # strong beacons in a row needed, so one lucky packet
HIT_GAP_MS = 1500      # ...from across the room is not enough
REPLY_MS = 3000        # keep replying this long after last hearing the vendor
STAMP_WINDOW_MS = 10000  # how long one vendor STAMP press broadcasts
REPEAT_GRACE_MS = 3000   # wait this long for a new badge before settling for
                         # an already-stamped one
NEARBY_MS = 4000       # a badge or vendor drops off the nearby list after this


class _BleSession:
    def __init__(self, links=None, key=False) -> None:
        # links / key: fakes for tests; by default Bluetooth and the key file.
        self.radio = BadgeRadio(ble=True, ir=False, wired=False, links=links, key=key)
        self.running = False

    @property
    def _ble(self):
        """The Bluetooth link, for its `heard` / `vendors` signal tables."""
        return self.radio.ble

    def start(self) -> bool:
        self.running = self.radio.start() and self.radio.ble is not None
        return self.running

    def stop(self) -> None:
        self.radio.stop()
        self.running = False

    def _packets(self):
        """Verified packets waiting (forged or unsigned ones are dropped
        when the badge holds the radio key)."""
        for packet, via in self.radio.read():
            yield packet

    def _fresh(self, table):
        """(key, rssi) heard recently, strongest first."""
        now = time.ticks_ms()
        rows = [(k, v[0]) for k, v in list(table.items())
                if time.ticks_diff(now, v[1]) < NEARBY_MS]
        rows.sort(key=lambda r: -r[1])
        return rows


class StampBeacon(_BleSession):
    """A vendor badge: each STAMP press stamps the one badge held close."""

    def __init__(self, vendor_id: str, links=None, key=False) -> None:
        super().__init__(links, key)
        self.vendor_id = stamp_manager.normalize_vendor_id(vendor_id)
        self.session_count = 0       # badges newly logged since start()
        self.recent = []             # latest replying badge ids, newest first
        self.total = len(stamp_manager.stamped())
        self.result = None           # last press: (badge id, newly logged), or
                                     # ("", False) when nobody replied in time
        self._window_end = None
        self._repeat = None

    def start(self) -> bool:
        """Open Bluetooth and listen; nothing is broadcast until stamp()."""
        return bool(self.vendor_id) and super().start()

    def stamp(self) -> bool:
        """The vendor pressed STAMP: broadcast for up to STAMP_WINDOW_MS."""
        if self._ble is None:
            return False
        from trade_session import my_badge
        self.radio.drain()           # replies from before this press do not count
        self.result = None
        self._repeat = None          # (badge, ticks) first already-stamped reply
        self._window_end = time.ticks_add(time.ticks_ms(), STAMP_WINDOW_MS)
        self.radio.send(stamp_manager.stamp_payload(self.vendor_id, my_badge()))
        return True

    def stamping(self) -> bool:
        return (self._window_end is not None
                and time.ticks_diff(self._window_end, time.ticks_ms()) > 0)

    def window_left(self) -> int:
        """Whole seconds left in this press's window (0 when not stamping)."""
        if not self.stamping():
            return 0
        return (time.ticks_diff(self._window_end, time.ticks_ms()) + 999) // 1000

    def _close(self, result) -> None:
        self._window_end = None
        self.result = result
        self.radio.stop_advertising()

    def poll(self) -> None:
        if self._window_end is None:
            for _ in self._packets():
                pass                 # not stamping: drain, count nothing
            return
        now = time.ticks_ms()
        for packet in self._packets():
            parsed = stamp_manager.parse(packet, stamp_manager.ACK_PREFIX)
            if parsed is None or parsed[0] != self.vendor_id:
                continue
            badge = parsed[1]
            if stamp_manager.record_stamped(badge):
                # A new badge always wins the press.
                self.session_count += 1
                self.total += 1
                if badge in self.recent:
                    self.recent.remove(badge)
                self.recent.insert(0, badge)
                del self.recent[5:]
                self._close((badge, True))
                return
            if self._repeat is None:
                self._repeat = (badge, now)   # already stamped: keep waiting
        if (self._repeat is not None
                and time.ticks_diff(now, self._repeat[1]) >= REPEAT_GRACE_MS):
            self._close((self._repeat[0], False))
        elif not self.stamping():
            self._close(("", False))          # nobody new replied in time

    def nearby(self):
        """Badges heard nearby, as (badge id, rssi), strongest first."""
        if self._ble is None:
            return []
        return self._fresh(self._ble.heard)


class StampCollector(_BleSession):
    """An attendee badge listening for vendor stamps."""

    def __init__(self, links=None, key=False) -> None:
        super().__init__(links, key)
        self.last = None             # (vendor id, newly collected) or None
        self._have = set(v for v, _ in stamp_manager.all_stamps())
        self._hits = {}              # vendor id -> (strong beacons in a row, ticks)
        self._reply_vendor = ""
        self._reply_until = None

    def poll(self) -> None:
        now = time.ticks_ms()
        for packet in self._packets():
            parsed = stamp_manager.parse(packet, stamp_manager.STAMP_PREFIX)
            if parsed is None:
                continue
            vid, vendor_badge = parsed
            if not self._close_enough(vid, now):
                continue
            newly = vid not in self._have and stamp_manager.collect(vid, vendor_badge)
            self._have.add(vid)
            if newly or self.last is None or self.last[0] != vid:
                self.last = (vid, newly)
            self._reply(vid, now)
        if (self._reply_until is not None
                and time.ticks_diff(now, self._reply_until) >= 0):
            self._reply_until = None
            self._reply_vendor = ""
            self.radio.stop_advertising()

    def _close_enough(self, vid: str, now: int) -> bool:
        """True once STAMP_HITS strong beacons from this vendor have arrived,
        each within HIT_GAP_MS of the last. A weak one starts the count over."""
        rssi = self.rssi(vid)
        count, seen = self._hits.get(vid, (0, now))
        if rssi is None or rssi < STAMP_RSSI_MIN:
            remember(self._hits, vid, (0, now))      # capped: vendor ids are claims
            return False
        if count and time.ticks_diff(now, seen) > HIT_GAP_MS:
            count = 0
        count += 1
        remember(self._hits, vid, (count, now))
        return count >= STAMP_HITS

    def rssi(self, vid: str):
        """The latest signal from this vendor, or None if not heard."""
        if self._ble is None or vid not in self._ble.vendors:
            return None
        return self._ble.vendors[vid][0]

    def _reply(self, vid: str, now: int) -> None:
        self._reply_until = time.ticks_add(now, REPLY_MS)
        if vid != self._reply_vendor and self._ble is not None:
            from trade_session import my_badge
            self._reply_vendor = vid
            self.radio.send(stamp_manager.ack_payload(vid, my_badge()))

    def nearby(self):
        """Vendors heard nearby, as (vendor id, rssi), strongest first."""
        if self._ble is None:
            return []
        return self._fresh(self._ble.vendors)
