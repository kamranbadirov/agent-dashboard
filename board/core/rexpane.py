import json
import os
import shutil
import subprocess
import threading
import time

from . import ptyhost

LABEL = "agent"
RATIO = "62"
CLIENT_WAIT_SECONDS = 3
_pane = {"block": None, "tty": None}
_lock = threading.Lock()


def available():
    return bool(os.environ.get("REX_SESSION") and os.environ.get("REX_BLOCK") and shutil.which("rex"))


def rex(*args):
    try:
        return subprocess.run(["rex", *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def blocks():
    result = rex("block", "ls", "-s", os.environ["REX_SESSION"], "--json")
    if result.returncode != 0:
        return set()
    try:
        return {b["block_id"] for b in json.loads(result.stdout).get("blocks", [])}
    except (ValueError, AttributeError):
        return set()


def pane_open():
    return bool(_pane["block"]) and _pane["tty"] in ptyhost.clients() and _pane["block"] in blocks()


def focus_pane():
    rex("focus", "-s", os.environ["REX_SESSION"], _pane["block"])


def open_pane(key, focus):
    before = ptyhost.clients()
    result = rex("split", "-s", os.environ["REX_SESSION"], "-b", os.environ["REX_BLOCK"], "--split=right",
                 "--ratio", RATIO, "--label", LABEL, f"--focus={'true' if focus else 'false'}", "--json",
                 "--", *ptyhost.attach_argv(key))
    if result.returncode != 0:
        return False, result.stderr.strip() or "Rex could not open a pane."
    try:
        block = json.loads(result.stdout)["block_ids"][0]
    except (ValueError, KeyError, IndexError):
        return False, "Rex opened a pane but did not say which one."
    deadline = time.time() + CLIENT_WAIT_SECONDS
    while time.time() < deadline:
        new = ptyhost.clients() - before
        if new:
            _pane.update(block=block, tty=new.pop())
            return True, ""
        time.sleep(0.1)
    _pane.update(block=block, tty=None)
    return False, "The pane opened, but tmux did not attach in it."


def open_tab(key, title):
    result = rex("window", "new", "-s", os.environ["REX_SESSION"], title[:40], "--json", "--", *ptyhost.attach_argv(key))
    return result.returncode == 0, result.stderr.strip() or "Rex could not open a tab."


def show(key, focus=False, open_new=True):
    """Show the tmux session `key` in the Rex pane beside the board. With open_new False,
    only switch a pane that is already open."""
    with _lock:
        ptyhost.release_size(key)
        if pane_open():
            if not ptyhost.switch_client(_pane["tty"], key):
                return False, "tmux could not switch the pane to this agent."
            if focus:
                focus_pane()
            return True, ""
        if not open_new:
            return True, ""
        return open_pane(key, focus)
