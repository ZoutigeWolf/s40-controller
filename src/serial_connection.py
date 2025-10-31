import asyncio
import serial_asyncio
from serial.serialutil import SerialException


class SerialConnection:
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.reader = None
        self.writer = None
        self.available = False
        self._last_attempt = 0

    async def init(self):
        now = asyncio.get_event_loop().time()
        if self.available:
            return True
        # Limit retry to 1 second
        if now - self._last_attempt < 1:
            return False
        self._last_attempt = now
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(
                url=self.port, baudrate=self.baudrate
            )
            self.available = True
            print(f"[Serial] Connected to {self.port}")
            return True
        except (SerialException, FileNotFoundError):
            self.available = False
            print(f"[Serial] Not available: {self.port}")
            return False

    async def send(self, msg: str):
        if not self.available:
            await self.init()
            if not self.available:
                return
        try:
            self.writer.write((msg + "\n").encode())
            await self.writer.drain()
        except Exception as e:
            print(f"[Serial] Send error: {e}")
            self.available = False

    async def read_line(self) -> str:
        if not self.available:
            await self.init()
            if not self.available:
                await asyncio.sleep(1)  # wait 1s before next retry
                return ""
        try:
            line = await asyncio.wait_for(self.reader.readline(), timeout=0.5)
            return line.decode()
        except asyncio.TimeoutError:
            return ""
        except Exception as e:
            print(f"[Serial] Read error: {e}")
            self.available = False
            return ""