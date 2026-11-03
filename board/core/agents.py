import os
import shlex
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import ptyhost, rexpane
from .cache import JsonFile
from .config import AGENT_COMMAND, AGENTS_FILE, CHAT_DIR, TERMINALS_DIR
from .root import read_env
from .sessions import close_session, live_sessions, pid_alive

MOVE_WAIT_SECONDS = 10

BACKGROUND, TERMINAL = "background", "terminal"
TERMINAL_APPS = {
    "Terminal": "/System/Applications/Utilities/Terminal.app",
    "iTerm": "/Applications/iTerm.app",
    "Ghostty": "/Applications/Ghostty.app",
}

_registry = JsonFile(AGENTS_FILE, {})


def registry():
    """Every agent this board started, by session ID."""
    return _registry.data


def installed_terminals():
    return [name for name, path in TERMINAL_APPS.items() if os.path.exists(path)]


def record_for(session_id):
    """The record of any agent this board started, wherever it runs, or None."""
    return _registry.data.get(session_id)


def board_agent(session_id):
    record = record_for(session_id)
    return record if record and (record["where"] == BACKGROUND or record.get("tmux")) else None


def agent_argv(record, resume):
    if resume:
        return [AGENT_COMMAND, "--resume", record["sessionId"]]
    argv = [AGENT_COMMAND, "--session-id", record["sessionId"]]
    return argv + [record["prompt"]] if record["prompt"] else argv


def launch_in_terminal(key, cwd, argv, app):
    TERMINALS_DIR.mkdir(parents=True, exist_ok=True)
    script = TERMINALS_DIR / f"{key}.command"
    script.write_text(f"#!/bin/sh\ncd {shlex.quote(cwd)} && exec {shlex.join(argv)}\n")
    script.chmod(0o755)
    return subprocess.run(["open", "-a", app, str(script)], capture_output=True, text=True)


def open_elsewhere(record):
    key = record["sessionId"]
    if rexpane.available():
        return rexpane.open_tab(key, record["title"])
    try:
        result = launch_in_terminal(key, record["cwd"], ptyhost.attach_argv(key), record.get("terminalApp") or "Terminal")
    except OSError as e:
        return False, f"Could not open the terminal: {e}"
    return result.returncode == 0, result.stderr.strip() or "Could not open the terminal."


def start_agent(cwd, prompt, where, terminal_app=None, title="Agent", prs=None):
    if not os.path.isdir(cwd):
        return False, f"Cannot start the agent: {cwd} does not exist.", None
    if where not in (BACKGROUND, TERMINAL):
        return False, "Unknown place to run the agent.", None
    record = {
        "sessionId": str(uuid.uuid4()), "cwd": str(cwd), "prompt": prompt, "where": where, "title": title,
        "branch": read_env(Path(cwd) / ".worktree.env").get("BRANCH"), "prs": prs or [], "createdAt": datetime.now(timezone.utc).isoformat(),
        "tmux": True, "terminalApp": terminal_app,
    }
    ok, message = ptyhost.spawn(record["sessionId"], agent_argv(record, resume=False), record["cwd"])
    if not ok:
        return False, message, None
    _registry.change(lambda data: data.__setitem__(record["sessionId"], record))
    if where == TERMINAL:
        ok, message = open_elsewhere(record)
        if not ok:
            return True, f"The agent started in the board, but {message[0].lower() + message[1:]}", record
    return True, "Agent started.", record


def start_chat():
    if not CHAT_DIR.is_dir():
        return False, f"No folder at {CHAT_DIR}. Set CHAT_DIR or ROOT_REPO.", None
    return start_agent(str(CHAT_DIR), None, BACKGROUND, title="Chat")


def adopt_agent(session_id, cwd, title):
    if not cwd or not os.path.isdir(cwd):
        return False, "This session's folder no longer exists, so it cannot resume."
    record = {
        "sessionId": session_id, "cwd": str(cwd), "prompt": None, "where": BACKGROUND, "title": title,
        "branch": read_env(Path(cwd) / ".worktree.env").get("BRANCH"), "prs": [], "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    _registry.change(lambda data: data.__setitem__(session_id, record))
    return resume_agent(session_id)


def move_into_board(session_id, cwd, title):
    meta = live_sessions().get(session_id)
    if meta and meta.get("status") == "busy":
        return False, "It is working right now. Try again when it is idle."
    ok, message = close_session(session_id)
    if not ok:
        return False, message
    pid = (meta or {}).get("pid")
    deadline = time.time() + MOVE_WAIT_SECONDS
    while pid and pid_alive(pid):
        if time.time() > deadline:
            return False, "The old session did not stop, so it was not moved."
        time.sleep(0.2)
    return adopt_agent(session_id, cwd, title)


def resume_agent(session_id):
    record = board_agent(session_id)
    if not record:
        return False, "This agent was not started by the board."
    return ptyhost.spawn(session_id, agent_argv(record, resume=True), record["cwd"])
