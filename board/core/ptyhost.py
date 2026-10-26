import fcntl
import os
import pty
import struct
import subprocess
import termios
import threading

from .cache import BatchedAppender, RingBuffer
from .config import TERMINAL_BUFFER_BYTES, TERMINALS_DIR

READ_BYTES = 65536
_sessions = {}


def log_path(key):
    return TERMINALS_DIR / f"{key}.log"


def make_controlling_tty():
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


class PtySession:
    """One program running in a pseudo-terminal. Output is kept in memory for the live view
    and appended to a log file, so it can be shown again after the board restarts."""

    def __init__(self, key, argv, cwd, rows=30, cols=100):
        self.key = key
        self.closed = False  # the master end is closed once the program has exited
        self.buffer = RingBuffer(TERMINAL_BUFFER_BYTES)
        self.master, slave = pty.openpty()
        self.resize(rows, cols)
        env = {**os.environ, "TERM": "xterm-256color", "COLUMNS": str(cols), "LINES": str(rows)}
        self.process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, preexec_fn=make_controlling_tty,
        )
        os.close(slave)
        self.log = BatchedAppender(log_path(key))
        threading.Thread(target=self.pump, daemon=True).start()

    def pump(self):
        while True:
            try:
                chunk = os.read(self.master, READ_BYTES)
            except OSError:
                break
            if not chunk:
                break
            self.buffer.write(chunk)
            self.log.write(chunk)
        self.process.wait()
        self.log.close()
        self.closed = True
        os.close(self.master)

    @property
    def alive(self):
        return self.process.poll() is None

    def write(self, data):
        if self.alive and not self.closed:
            try:
                os.write(self.master, data)
            except OSError:
                pass

    def resize(self, rows, cols):
        if self.closed:
            return
        try:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass  # the program exited and the pump closed the master just now

    def stop(self):
        if self.alive:
            self.process.terminate()


def spawn(key, argv, cwd):
    session = PtySession(key, argv, cwd)
    _sessions[key] = session
    return session


def get(key):
    return _sessions.get(key)


def history(key):
    try:
        with open(log_path(key), "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TERMINAL_BUFFER_BYTES))
            return f.read()
    except OSError:
        return b""
