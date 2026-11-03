import json
import os
import shutil
import subprocess
import threading
import time

from . import ptyhost

AGENT, TERM = "agent", "term"
LAYOUT = {AGENT: ("right", "62"), TERM: ("below", "40")}
CLIENT_WAIT_SECONDS = 3
_panes = {AGENT: {"block": None, "tty": None}, TERM: {"block": None, "tty": None}}
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


def pane_open(name=AGENT):
    pane = _panes[name]
    return bool(pane["block"]) and pane["tty"] in ptyhost.clients() and pane["block"] in blocks()


def focus_pane(name=AGENT):
    rex("focus", "-s", os.environ["REX_SESSION"], _panes[name]["block"])


def anchor_for(name):
    """The agent pane sits right of the board. The terminal sits below the agent pane, or below the board."""
    if name == TERM and pane_open(AGENT):
        return _panes[AGENT]["block"]
    return os.environ["REX_BLOCK"]


def open_pane(key, focus, name=AGENT):
    split, ratio = LAYOUT[name]
    before = ptyhost.clients()
    result = rex("split", "-s", os.environ["REX_SESSION"], "-b", anchor_for(name), f"--split={split}",
                 "--ratio", ratio, "--label", name, f"--focus={'true' if focus else 'false'}", "--json",
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
            _panes[name].update(block=block, tty=new.pop())
            return True, ""
        time.sleep(0.1)
    _panes[name].update(block=block, tty=None)
    return False, "The pane opened, but tmux did not attach in it."


def close_pane():
    """Close the board's Rex panes. Only their tmux attach ends; the programs keep running in tmux."""
    with _lock:
        found = blocks()
        for pane in _panes.values():
            block = pane["block"]
            pane.update(block=None, tty=None)
            if block and block in found:
                rex("block", "close", "-s", os.environ["REX_SESSION"], block)


def open_tab(key, title):
    result = rex("window", "new", "-s", os.environ["REX_SESSION"], title[:40], "--json", "--", *ptyhost.attach_argv(key))
    return result.returncode == 0, result.stderr.strip() or "Rex could not open a tab."


def show(key, focus=False, open_new=True, name=AGENT):
    """Show the tmux session `key` in one of the board's Rex panes. With open_new False,
    only switch a pane that is already open."""
    with _lock:
        ptyhost.release_size(key)
        if pane_open(name):
            if not ptyhost.switch_client(_panes[name]["tty"], key):
                return False, "tmux could not switch the pane."
            if focus:
                focus_pane(name)
            return True, ""
        if not open_new:
            return True, ""
        return open_pane(key, focus, name)
