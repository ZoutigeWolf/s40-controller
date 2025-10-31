import os
from dotenv import load_dotenv
from fastapi import FastAPI, Response, Depends
from camilladsp import CamillaClient, CamillaError
from contextlib import asynccontextmanager
import asyncio
import serial_asyncio
from serial import SerialException

from avrcp import AVRCPClient

load_dotenv()

camilla = CamillaClient(os.getenv("CAMILLA_HOST"), int(os.getenv("CAMILLA_PORT")))
camilla.connect()

avrcp = AVRCPClient()

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200

power_state = False

class SerialConnection:
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.reader = None
        self.writer = None

    async def init(self) -> bool:
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(
                url=self.port, baudrate=self.baudrate
            )

            return True

        except SerialException:
            self.reader = None
            self.writer = None

            return False

    async def send(self, msg: str):
        if self.writer is None:
            res = await self.init()
            if not res:
                return

        self.writer.write((msg + "\n").encode())
        await self.writer.drain()

    async def read_line(self) -> str:
        if self.reader is None:
            res = await self.init()

            if not res:
                return ""

        return await self.reader.readline().decode()


serial_conn = SerialConnection(SERIAL_PORT, BAUD_RATE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await serial_conn.init()

    serial_task = asyncio.create_task(read_serial(serial_conn))
    avrcp_task = asyncio.create_task(send_avrcp_periodically(serial_conn))

    try:
        yield
    finally:
        serial_task.cancel()
        avrcp_task.cancel()
        try:
            await serial_task
        except asyncio.CancelledError:
            pass
        try:
            await avrcp_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)

async def handle_event(event: str):
    global power_state

    if event == "VOLUME_UP":
        volume = camilla.volume.main_volume() + 1
        camilla.volume.set_main_volume(0 if volume > 0 else volume)

    elif event == "VOLUME_DOWN":
        volume = camilla.volume.main_volume() - 1
        camilla.volume.set_main_volume(-50 if volume < -50 else volume)

    elif event == "MUTE":
        muted = camilla.volume.main_mute()
        camilla.volume.set_main_mute(not muted)

    elif event == "POWER_ON":
        power_state = True

    elif event == "POWER_OFF":
        power_state = False

    else:
        print(f"Unknown event: {event}")

async def read_serial(serial: SerialConnection):
    while True:
        line = await serial.read_line()
        if not line:
            continue

        event = line.strip()

        await handle_event(event)

async def send_avrcp_periodically(serial: SerialConnection):
    while True:
        try:
            track = avrcp.get_current()
            if track:
                title = track.get("Title", "")
                artist = track.get("Artist", "")
                duration = track.get("Duration", 0)
                position = track.get("Position", 0)

                await serial.send(f"SET_TRACK;TITLE;{title}")
                await serial.send(f"SET_TRACK;ARTIST;{artist}")
                await serial.send(f"SET_TRACK;DURATION;{duration}")
                await serial.send(f"SET_TRACK;ELAPSED;{position}")

        except Exception as e:
            print("AVRCP error:", e)

        await asyncio.sleep(0.5)

@app.get("/now-playing")
async def now_playing():
    return avrcp.get_current()


@app.get("/power")
async def power():
    return power_state


@app.get("/config")
async def get_config():
    return camilla.config.active()


@app.post("/config")
async def set_config(config: dict):
    try:
        config = camilla.config.validate(config)
        camilla.config.set_active(config)
        return config
    except CamillaError:
        return Response(status_code=400)


@app.get("/devices")
async def get_devices():
    types = camilla.general.supported_device_types()
    return {
        "capture": {t: [d[0] for d in camilla.general.list_capture_devices(t)] for t in types[1]},
        "playback": {t: [d[0] for d in camilla.general.list_capture_devices(t)] for t in types[0]}
    }


# -------------------------------
# Example: send serial message anywhere via dependency
# -------------------------------
async def send_example(msg: str, serial: SerialConnection = Depends(lambda: serial_conn)):
    await serial.send(msg)