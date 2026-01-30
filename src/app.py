import math
import os
import psycopg2
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from camilladsp import CamillaClient, CamillaError
from contextlib import asynccontextmanager
import asyncio

from avrcp import AVRCPClient
from serial_connection import SerialConnection
from gps import UbloxGPS

load_dotenv()

camilla = CamillaClient(os.getenv("CAMILLA_HOST"), int(os.getenv("CAMILLA_PORT")))
camilla.connect()

avrcp = AVRCPClient()

serial_conn = SerialConnection("/dev/ttyUSB0", 115200)
db_conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST"),
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
)

ublox_gps = UbloxGPS("/dev/ttyACM0")

power_state = False

async def read_serial(serial: SerialConnection):
    while True:
        line = await serial.read_line()
        if not line:
            await asyncio.sleep(0.1)
            continue
        event = line.strip()
        await handle_event(serial, event)


async def send_avrcp_periodically(serial: SerialConnection):
    while True:
        try:
            data = avrcp.get_current()

            if data is None:
                continue

            title = data["track"].get("Title", "")
            artist = data["track"].get("Artist", "")
            duration = data["track"].get("Duration", 0)
            position = data.get("position", 0)

            await serial.send(f"SET_TRACK;TITLE;{title}")
            await serial.send(f"SET_TRACK;ARTIST;{artist}")
            await serial.send(f"SET_TRACK;DURATION;{duration}")
            await serial.send(f"SET_TRACK;ELAPSED;{position}")

        except Exception as e:
            print("AVRCP error:", e)

        finally:
            await asyncio.sleep(1)


async def update_gps(serial: SerialConnection, db, gps: UbloxGPS):
    last_speed = 0
    while True:
        try:
            data = await gps.update()

            if data is None:
                continue

            timestamp = data["timestamp"]
            speed = math.floor(data["speed"])
            lat = data["lat"]
            lon = data["lon"]
            course = data["course"]

            await serial.send(f"SET_GPS;SPEED;{speed}")
            await serial.send(f"SET_GPS;POSITION;{lat},{lon}")
            await serial.send(f"SET_GPS;COURSE;{course}")

            if speed == last_speed == 0:
                continue

            cur = db.cursor()

            cur.execute(
                """
                INSERT INTO gps (timestamp, position, speed)
                VALUES (%s, ST_SetSRID(ST_Point(%s::double precision, %s::double precision), 4326), %s)
                """, [timestamp, lon, lat, speed]
            )

            db.commit()

            last_speed = speed

        except Exception as e:
            print("GPS error:", e)

        finally:
            await asyncio.sleep(0.2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = []
    try:
        tasks.append(asyncio.create_task(read_serial(serial_conn)))
        tasks.append(asyncio.create_task(send_avrcp_periodically(serial_conn)))
        tasks.append(asyncio.create_task(update_gps(serial_conn, db_conn, ublox_gps)))
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(lifespan=lifespan)

async def handle_event(serial: SerialConnection, event: str):
    global power_state

    if event == "VOLUME":
        volume = camilla.volume.main_volume()
        await serial.send(f"VOLUME;{volume}")

    if event == "VOLUME_UP":
        volume = math.floor(camilla.volume.main_volume() + 1)
        volume = 0 if volume > 0 else volume
        camilla.volume.set_main_volume(volume)
        await serial.send(f"VOLUME;{camilla.volume.main_volume()}")

    elif event == "VOLUME_DOWN":
        volume = math.floor(camilla.volume.main_volume() - 1)
        volume = -100 if volume < -100 else volume
        camilla.volume.set_main_volume(volume)
        await serial.send(f"VOLUME;{camilla.volume.main_volume()}")

    elif event == "MUTE":
        muted = not camilla.volume.main_mute()
        camilla.volume.set_main_mute(muted)
        await serial.send(f"MUTE;{'ON' if muted else 'OFF'}")

    elif event == "FRONT_BASS_UP":
        volume = math.floor(camilla.volume.volume(1) + 1)
        volume = 0 if volume > 0 else volume
        camilla.volume.set_volume(1, volume)

    elif event == "FRONT_BASS_DOWN":
        volume = math.floor(camilla.volume.volume(1) - 1)
        volume = -50 if volume < -50 else volume
        camilla.volume.set_volume(1, volume)

    elif event == "FRONT_BASS_MUTE":
        camilla.volume.set_mute(1, not camilla.volume.mute(1))

    elif event == "REAR_BASS_UP":
        config = camilla.config.active()

        try:
            gain = config["filters"]["Rear Bass"]["parameters"]["gain"]
            gain = math.floor(gain + 1)
            gain = 24 if gain > 24 else gain
            config["filters"]["Rear Bass"]["parameters"]["gain"] = gain

            path = camilla.config.file_path()

            if path is None:
                camilla.config.set_active(config)

            else:
                with open(path, "w") as f:
                    f.write(yaml.dump(config))

                camilla.general.reload()

        except (KeyError, TypeError):
            pass

    elif event == "REAR_BASS_DOWN":
        config = camilla.config.active()

        try:
            gain = config["filters"]["Rear Bass"]["parameters"]["gain"]
            gain = math.floor(gain - 1)
            gain = -24 if gain < -24 else gain
            config["filters"]["Rear Bass"]["parameters"]["gain"] = gain

            path = camilla.config.file_path()

            if path is None:
                camilla.config.set_active(config)

            else:
                with open(path, "w") as f:
                    f.write(yaml.dump(config))

                camilla.general.reload()

        except (KeyError, TypeError):
            pass

    elif event == "REAR_BASS_RESET":
        config = camilla.config.active()

        try:
            config["filters"]["Rear Bass"]["parameters"]["gain"] = 0

            path = camilla.config.file_path()

            if path is None:
                camilla.config.set_active(config)

            else:
                with open(path, "w") as f:
                    f.write(yaml.dump(config))

                camilla.general.reload()

        except (KeyError, TypeError):
            pass

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
