import os
import re

from . import ptyhost
from .root import platform_branch, root_dir
from .transcript import tickets_in

PREFIX = "proc-"
TITLES = {"run": "Dev servers", "backend": "Shared backend", "fix": "Fix", "term": "Terminal"}
TERM = "term"
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


def start_terminal(cwd):
    """A login shell in board tmux, in cwd. One for each folder; a live one is reused."""
    path = os.path.abspath(cwd)
    name = f"{os.path.basename(os.path.dirname(path))}-{os.path.basename(path)}"
    return start(TERM, name, [os.environ.get("SHELL") or "/bin/zsh", "-l"], path)


def is_terminal(key):
    return key.startswith(key_for(TERM, ""))


def tickets_of(key):
    kind, _, name = key[len(PREFIX):].partition("-")
    if kind != "run":
        return []
    try:
        return tickets_in(platform_branch(root_dir().parent / name) or "")
    except Exception:
        return []


def listed():
    return [dict(p, title=title_of(p["key"]), tickets=tickets_of(p["key"]))
            for p in ptyhost.sessions() if p["key"].startswith(PREFIX)]


def stop(key):
    return (True, "Stopped.") if ptyhost.kill(key) else (False, "It was not running.")
