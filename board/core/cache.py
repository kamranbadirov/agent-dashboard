import atexit
import json
import os
import threading

from .config import JSON_WRITE_DELAY_SECONDS


class JsonFile:
    """A JSON file held in memory. Changes are saved once after a quiet moment, through a
    temp file and a rename, so a crash never leaves half a file."""

    def __init__(self, path, default):
        self.path = path
        self.lock = threading.RLock()
        self.timer = None
        self.dirty = False
        try:
            self.data = json.loads(path.read_text())
        except Exception:
            self.data = default
        atexit.register(self.flush)

    def change(self, fn):
        with self.lock:
            result = fn(self.data)
            self.dirty = True
            if self.timer is None:
                self.timer = threading.Timer(JSON_WRITE_DELAY_SECONDS, self.flush)
                self.timer.daemon = True
                self.timer.start()
            return result

    def flush(self):
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if not self.dirty:
                return
            self.dirty = False
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self.data))
            os.replace(tmp, self.path)

