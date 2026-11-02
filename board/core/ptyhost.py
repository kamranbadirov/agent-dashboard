import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .config import TERMINALS_DIR

SOCKET = "agent-board"
CONFIG = Path(__file__).with_name("tmux.conf")
MISSING = "tmux is not installed. Run brew install tmux, then start the board again."
_size = [45, 160]
_sizes = {}


def available():
    return shutil.which("tmux") is not None


def tmux_argv(*args):
    return ["tmux", "-L", SOCKET, "-f", str(CONFIG), *args]


def outside_tmux():
    return {k: v for k, v in os.environ.items() if k != "TMUX"}


def tmux(*args):
    return subprocess.run(tmux_argv(*args), capture_output=True, text=True, env=outside_tmux())


def log_path(key):
    return TERMINALS_DIR / f"{key}.log"


def set_size(rows, cols):
    _size[:] = [rows, cols]


def spawn(key, argv, cwd, env=None, keep=False):
    if not available():
        return False, MISSING
    rows, cols = _size
    env_args = [arg for name, value in (env or {}).items() for arg in ("-e", f"{name}={value}")]
    keep_args = [";", "set-option", "-p", "-t", f"={key}:", "remain-on-exit", "on"] if keep else []
    result = tmux("new-session", "-d", "-s", key, "-x", str(cols), "-y", str(rows), "-c", str(cwd), *env_args,
                  "--", *argv, *keep_args)
    if result.returncode != 0:
        return False, result.stderr.strip() or "Could not start the agent in tmux."
    _sizes[key] = (rows, cols)
    TERMINALS_DIR.mkdir(parents=True, exist_ok=True)
    tmux("pipe-pane", "-o", "-t", f"={key}:", f"cat >> {shlex.quote(str(log_path(key)))}")
    return True, "Agent started."


def kill(key):
    return tmux("kill-session", "-t", f"={key}").returncode == 0


def sessions():
    """Every tmux session on the board's socket: name, whether its program exited, its exit code, when it started."""
    result = tmux("list-sessions", "-F", "#{session_name}\t#{pane_dead}\t#{pane_dead_status}\t#{session_created}")
    if result.returncode != 0:
        return []
    out = []
    for line in result.stdout.splitlines():
        name, dead, status, created = (line.split("\t") + ["", "", "", ""])[:4]
        out.append({"key": name, "dead": dead == "1", "exitCode": int(status) if status.isdigit() else None,
                    "created": int(created) if created.isdigit() else 0})
    return out


def alive(key):
    return available() and tmux("has-session", "-t", f"={key}").returncode == 0


def resize(key, rows, cols):
    if _sizes.get(key) == (rows, cols):
        return
    if tmux("resize-window", "-t", f"={key}:", "-x", str(cols), "-y", str(rows)).returncode == 0:
        _sizes[key] = (rows, cols)


def capture(key, rows, cols):
    if not available():
        return None
    resize(key, rows, cols)
    result = tmux("capture-pane", "-p", "-e", "-t", f"={key}:")
    return result.stdout.rstrip("\n") if result.returncode == 0 else None


def send_text(key, text):
    tmux("send-keys", "-t", f"={key}:", "-l", text)


def release_size(key):
    tmux("set-option", "-w", "-u", "-t", f"={key}:", "window-size")
    _sizes.pop(key, None)


def attach_argv(key):
    return tmux_argv("attach-session", "-t", f"={key}")


def attach(key):
    release_size(key)
    return subprocess.run(attach_argv(key), env=outside_tmux()).returncode


def clients():
    result = tmux("list-clients", "-F", "#{client_tty}")
    return set(result.stdout.split()) if result.returncode == 0 else set()


def switch_client(tty, key):
    release_size(key)
    return tmux("switch-client", "-c", tty, "-t", f"={key}").returncode == 0
