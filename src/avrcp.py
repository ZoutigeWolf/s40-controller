from pydbus import SystemBus

class AVRCPClient:
    def __init__(self):
        self.bus = SystemBus()
        self.manager = self.bus.get("org.bluez", "/")
        self.player = self._discover_player()
        if self.player is None:
            raise RuntimeError("No AVRCP device connected.")

    def _discover_player(self):
        objects = self.manager.GetManagedObjects()
        for path, interfaces in objects.items():
            if "org.bluez.MediaPlayer1" in interfaces:
                return self.bus.get("org.bluez", path)
        return None

    def play(self):
        self.player.Play()

    def pause(self):
        self.player.Pause()

    def next(self):
        self.player.Next()

    def previous(self):
        self.player.Previous()

    def set_volume(self, value: int):
        self.player.Volume = max(0, min(127, value))

    def get_current(self):
        return {
            "status": self.player.PlaybackStatus,
            "volume": self.player.Volume,
            "track": self.player.Track
        }

    def get_track_title(self):
        return self.player.Track.get("Title", "")

    def get_artist(self):
        return self.player.Track.get("Artist", "")

    def get_album(self):
        return self.player.Track.get("Album", "")
