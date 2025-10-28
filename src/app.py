import os
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from camilladsp import CamillaClient, CamillaError
from contextlib import asynccontextmanager
import asyncio
import serial_asyncio

load_dotenv()

camilla = CamillaClient(os.getenv("CAMILLA_HOST"), int(os.getenv("CAMILLA_PORT")))
camilla.connect()

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200

power_state = False

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(read_serial())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
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

async def read_serial():
    reader, _ = await serial_asyncio.open_serial_connection(
        url=SERIAL_PORT, baudrate=BAUD_RATE
    )
    while True:
        line = await reader.readline()
        if not line:
            continue
        event = line.decode().strip()
        await handle_event(event)

@app.get("/power")
async def power():
    return power_state


@app.get("/config")
async def get_config():
    return camilla.config.active()


@app.post("/config")
async def get_config(config: dict):
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