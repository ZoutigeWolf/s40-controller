import struct
from micropyGPS import MicropyGPS
from datetime import datetime

from serial_connection import SerialConnection


class UbloxGPS(SerialConnection):
    def __init__(self, port: str, baudrate: int = 9600, refresh_rate: int = 5, timeout: float = 1):
        super().__init__(port, baudrate)
        self.timeout = timeout
        self.refresh_rate = refresh_rate
        self.gps = MicropyGPS(location_formatting="dd")

        self.set_update_rate(self.refresh_rate)
        self.set_automotive_mode()
        self.set_constellations()
        self.enable_sbas()
        self.save_to_eeprom()

    def _checksum(self, msg):
        ck_a = 0
        ck_b = 0
        for b in msg:
            ck_a = (ck_a + b) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        return bytes([ck_a, ck_b])

    def _send_ubx(self, msg_class, msg_id, payload):
        length = struct.pack("<H", len(payload))
        header = b"\xb5\x62" + bytes([msg_class, msg_id]) + length + payload
        checksum = self._checksum(bytes([msg_class, msg_id]) + length + payload)
        self.send(header + checksum)

    def set_update_rate(self, rate_hz):
        measRate = int(1000 / rate_hz)
        payload = struct.pack("<HHH", measRate, 1, 0)
        self._send_ubx(0x06, 0x08, payload)

    def set_automotive_mode(self):
        payload = struct.pack("<HBB27s", 1, 4, 0, b"\x00" * 27)
        self._send_ubx(0x06, 0x24, payload)

    def set_constellations(self):
        payload = bytearray(
            [
                0, 1, 0, 0,   # GPS
                2, 1, 0, 0,   # Galileo
                6, 1, 0, 0,   # GLONASS
                1, 1, 0, 0    # SBAS
            ]
        )
        self._send_ubx(0x06, 0x3E, payload)

    def enable_sbas(self):
        payload = struct.pack("<BBBBBBBBBBBB", 1, 1, 0, 12, 0, 0, 0, 3, 0, 0, 0, 0)
        self._send_ubx(0x06, 0x16, payload)

    def save_to_eeprom(self):
        payload = struct.pack("<BBBBBBBB", 0xFF, 0xFF, 0, 0, 0, 0, 0, 0)
        self._send_ubx(0x06, 0x09, payload)

    async def update(self):
        """
        Call this at 5Hz.
        Reads characters from serial, updates micropyGPS,
        and returns a dict with data when a full sentence is parsed.
        """

        c = await self.read_line()

        if not c:
            return None

        self.gps.update(c)

        # Only return when valid fix & full sentence parsed
        if self.gps.fix_type <= 1:
            return None

        # Build structured event
        lat = round(self.gps.latitude[0], 6)
        lon = round(self.gps.longitude[0], 6)
        speed = self.gps.speed[2]       # km/h
        alt = self.gps.altitude
        course = self.gps.compass_direction()

        ts = self.gps.timestamp
        dt = self.gps.date

        timestamp = datetime(dt[2], dt[1], dt[0], ts[0], ts[1], int(ts[2]))

        return {
            "timestamp": timestamp,
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "speed": speed,
            "course": course,
            "fix_type": self.gps.fix_type,
            "sats": self.gps.satellites_in_use,
            "hdop": self.gps.hdop,
        }
