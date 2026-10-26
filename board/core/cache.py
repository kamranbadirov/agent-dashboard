import atexit
import json
import os
import threading

from .config import JSON_WRITE_DELAY_SECONDS, TERMINAL_LOG_FLUSH_SECONDS


class RingBuffer:
    """Keeps the newest `limit` bytes. `end` counts every byte ever written, so a
    reader remembers where it stopped and asks only for what came after."""

    def __init__(self, limit):
        self.limit = limit
        self.data = bytearray()
        self.end = 0
        self.lock = threading.Lock()

    def write(self, chunk):
        with self.lock:
            self.data += chunk
            self.end += len(chunk)
            if len(self.data) > self.limit:
                del self.data[: len(self.data) - self.limit]

    def read_since(self, offset):
        with self.lock:
            start = self.end - len(self.data)
            return bytes(self.data[max(0, offset - start):]), self.end


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


class BatchedAppender:
    """Appends bytes to a file in batches instead of once per chunk."""

    def __init__(self, path, interval=TERMINAL_LOG_FLUSH_SECONDS):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(path, "ab")
        self.interval = interval
        self.pending = bytearray()
        self.lock = threading.Lock()
        self.timer = None

    def write(self, chunk):
        with self.lock:
            self.pending += chunk
            if self.timer is None and not self.file.closed:
                self.timer = threading.Timer(self.interval, self.flush)
                self.timer.daemon = True
                self.timer.start()

    def flush(self):
        with self.lock:
            self.timer = None
            if self.pending and not self.file.closed:
                self.file.write(self.pending)
                self.file.flush()
                self.pending.clear()

    def close(self):
        self.flush()
        with self.lock:
            self.file.close()
