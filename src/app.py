import os
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from camilladsp import CamillaClient, CamillaError
from contextlib import asynccontextmanager
import asyncio

from avrcp import AVRCPClient
from serial_connection import SerialConnection

load_dotenv()

camilla = CamillaClient(os.getenv("CAMILLA_HOST"), int(os.getenv("CAMILLA_PORT")))
camilla.connect()
avrcp = AVRCPClient()
serial_conn = SerialConnection("/dev/ttyUSB0", 115200)

power_state = False

async def read_serial(serial: SerialConnection):
    while True:
        line = await serial.read_line()
        if not line:
            await asyncio.sleep(0.1)
            continue
        event = line.strip()
        await handle_event(event)


async def send_avrcp_periodically(serial: SerialConnection):
    while True:
        try:
            data = avrcp.get_current()
            if data:
                title = data["track"].get("Title", "")
                artist = data["track"].get("Artist", "")
                duration = data["track"].get("Duration", 0)
                position = data.get("position", 0)

                print(title)
                print(artist)
                print(duration)
                print(position)

                await serial.send(f"SET_TRACK;TITLE;{title}")
                await serial.send(f"SET_TRACK;ARTIST;{artist}")
                await serial.send(f"SET_TRACK;DURATION;{duration}")
                await serial.send(f"SET_TRACK;ELAPSED;{position}")

        except Exception as e:
            print("AVRCP error:", e)

        await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = []
    try:
        # Start background tasks without blocking startup
        tasks.append(asyncio.create_task(read_serial(serial_conn)))
        tasks.append(asyncio.create_task(send_avrcp_periodically(serial_conn)))
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

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
        cfg = camilla.config.validate(config)
        camilla.config.set_active(cfg)
        return cfg
    except CamillaError:
        return Response(status_code=400)

@app.get("/devices")
async def get_devices():
    types = camilla.general.supported_device_types()
    return {
        "capture": {t: [d[0] for d in camilla.general.list_capture_devices(t)] for t in types[1]},
        "playback": {t: [d[0] for d in camilla.general.list_capture_devices(t)] for t in types[0]}
    }