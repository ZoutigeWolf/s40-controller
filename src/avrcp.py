from pydbus import SystemBus

class AVRCPClient:
    def __init__(self):
        self.bus = SystemBus()
        self.manager = self.bus.get("org.bluez", "/")
        self.player = self._discover_player()

    def _discover_player(self):
        objects = self.manager.GetManagedObjects()
        for path, interfaces in objects.items():
            if "org.bluez.MediaPlayer1" in interfaces:
                return self.bus.get("org.bluez", path)
        return None

    def get_current(self):
        self.player = self._discover_player()

        if self.player is None:
            return None

        return {
            "status": self.player.Status,
            "track": self.player.Track,
            "position": self.player.Position
        }
