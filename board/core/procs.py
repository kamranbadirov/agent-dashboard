import os
import re

from . import ptyhost

PREFIX = "proc-"
TITLES = {"run": "Dev servers", "backend": "Shared backend", "fix": "Fix"}
UNSAFE_RE = re.compile(r"[^A-Za-z0-9_-]")


def key_for(kind, name):
    return f"{PREFIX}{kind}-{UNSAFE_RE.sub('-', name)}"


def title_of(key):
    kind, _, name = key[len(PREFIX):].partition("-")
    return f"{TITLES.get(kind, kind)} · {name}" if name else TITLES.get(kind, kind)


def start(kind, name, argv, cwd, env=None):
    """Run a program such as make run in a board tmux session, so its prompts and output stay in the board.
    A live one is reused, and a finished one is replaced."""
    key = key_for(kind, name)
    found = next((p for p in listed() if p["key"] == key), None)
    if found and not found["dead"]:
        return True, "Already running.", key
    if found:
        ptyhost.kill(key)
    if not os.path.isdir(cwd):
        return False, f"{cwd} does not exist.", key
    ok, message = ptyhost.spawn(key, argv, cwd, env=env, keep=True)
    return ok, "Started." if ok else message, key


def start_dev_servers(platform):
    return start("run", os.path.basename(platform), ["make", "run"], platform)


def listed():
    return [dict(p, title=title_of(p["key"])) for p in ptyhost.sessions() if p["key"].startswith(PREFIX)]


def stop(key):
    return (True, "Stopped.") if ptyhost.kill(key) else (False, "It was not running.")
