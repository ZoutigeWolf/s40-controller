import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from camilladsp import CamillaClient

from avrcp import AVRCPClient

load_dotenv()

app = FastAPI()

camilla = CamillaClient(os.getenv("CAMILLA_HOST"), int(os.getenv("CAMILLA_PORT")))
camilla.connect()

avrcp = AVRCPClient()


def handle_status() -> list[str]:
    track_title = avrcp.get_track_title()
    track_artist = avrcp.get_artist()
    volume = camilla.volume.main_volume()
    bass = camilla.config.active()["filters"]["Bass"]["parameters"]["gain"]
    return [track_title, track_artist, volume, bass]

def handle_set_volume(cmd: list[str]) -> list[str]:
    try:
        volume = float(cmd[1])
    except ValueError:
        return ["ERROR", "Volume must be a float"]

    if volume > 0:
        volume = 0

    if volume < -50:
        volume = -50

    camilla.volume.set_main_volume(volume)

    return ["OK"]


def handle_set_bass(cmd: list[str]) -> list[str]:
    try:
        bass = float(cmd[1])
    except ValueError:
        return ["ERROR", "Bass must be a float"]

    if bass > 12:
        bass = 12

    if bass < -12:
        bass = -12

    config = camilla.config.active()
    config["filters"]["Bass"]["parameters"]["gain"] = bass
    camilla.config.set_active(config)


    return ["OK"]

def parse_message(msg: str) -> str:
    cmd = msg.split(";")
    match cmd[0].upper():
        case "CONFIG":
            with open("config.json", "w") as f:
                json.dump(camilla.config.active(), f, indent=4)

            res = ["OK"]
        case "STATUS":
            res = handle_status()

        case "SET_VOLUME":
            res = handle_set_volume(cmd)

        case "SET_BASS":
            res = handle_set_bass(cmd)

        case _:
            res = ["ERROR", "Unknown command"]

    return ";".join([str(x) for x in res])


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        msg = await ws.receive_text()
        res = parse_message(msg)
        await ws.send_text(res)
