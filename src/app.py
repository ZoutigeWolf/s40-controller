import os
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from camilladsp import CamillaClient, CamillaError

load_dotenv()

app = FastAPI()

camilla = CamillaClient(os.getenv("CAMILLA_HOST"), int(os.getenv("CAMILLA_PORT")))
camilla.connect()

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


@app.post("/control/volume-up")
async def control_volume_up():
    volume = camilla.volume.main_volume()
    camilla.volume.set_main_volume(volume + 1)


@app.post("/control/volume-down")
async def control_volume_down():
    volume = camilla.volume.main_volume()
    camilla.volume.set_main_volume(volume - 1)


@app.post("/control/mute")
async def control_mute():
    mute = camilla.volume.main_mute()
    camilla.volume.set_main_mute(not mute)
