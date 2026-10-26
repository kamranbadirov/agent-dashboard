import os
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import ptyhost
from .cache import JsonFile
from .config import AGENT_COMMAND, AGENTS_FILE, TERMINALS_DIR
from .root import read_env

BACKGROUND, CMUX, TERMINAL = "background", "cmux", "terminal"
TERMINAL_APPS = {
    "Terminal": "/System/Applications/Utilities/Terminal.app",
    "iTerm": "/Applications/iTerm.app",
    "Ghostty": "/Applications/Ghostty.app",
}

_registry = JsonFile(AGENTS_FILE, {})


def installed_terminals():
    return [name for name, path in TERMINAL_APPS.items() if os.path.exists(path)]


def record_for(session_id):
    """The record of any agent this board started, wherever it runs, or None."""
    return _registry.data.get(session_id)


def board_agent(session_id):
    """The record of an agent this board started in its own terminal, or None."""
    record = record_for(session_id)
    return record if record and record["where"] == BACKGROUND else None


def agent_argv(record, resume):
    if resume:
        return [AGENT_COMMAND, "--resume", record["sessionId"]]
    argv = [AGENT_COMMAND, "--session-id", record["sessionId"]]
    return argv + [record["prompt"]] if record["prompt"] else argv


def launch_in_cmux(name, cwd, argv):
    command = ["cmux", "new-workspace", "--name", name, "--cwd", cwd, "--command", shlex.join(argv)]
    return subprocess.run(command, capture_output=True, text=True)


def launch_in_terminal(key, cwd, argv, app):
    TERMINALS_DIR.mkdir(parents=True, exist_ok=True)
    script = TERMINALS_DIR / f"{key}.command"
    script.write_text(f"#!/bin/sh\ncd {shlex.quote(cwd)} && exec {shlex.join(argv)}\n")
    script.chmod(0o755)
    return subprocess.run(["open", "-a", app, str(script)], capture_output=True, text=True)


def launch_elsewhere(key, name, cwd, argv, where, app):
    if where == CMUX:
        return launch_in_cmux(name, cwd, argv)
    return launch_in_terminal(key, cwd, argv, app or "Terminal")


def run_dev_servers(platform, where, app):
    """`make run` in the platform. It needs a real terminal, so a board agent's owner gets cmux or a terminal app."""
    place = where if where in (CMUX, TERMINAL) else (CMUX if os.path.exists("/Applications/cmux.app") else TERMINAL)
    result = launch_elsewhere(f"run-{os.path.basename(platform)}", f"{os.path.basename(platform)} servers", platform,
                              ["make", "run"], place, app)
    return result.returncode == 0, result.stderr.strip() or "Started."


def bring_forward(where, app):
    name = "cmux" if where == CMUX else app
    subprocess.run(["open", "-a", name], capture_output=True)


def start_agent(cwd, prompt, where, terminal_app=None, title="Agent", prs=None):
    if not os.path.isdir(cwd):
        return False, f"Cannot start the agent: {cwd} does not exist.", None
    record = {
        "sessionId": str(uuid.uuid4()), "cwd": str(cwd), "prompt": prompt, "where": where, "title": title,
        "branch": read_env(Path(cwd) / ".worktree.env").get("BRANCH"), "prs": prs or [], "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    argv = agent_argv(record, resume=False)
    if where == BACKGROUND:
        ptyhost.spawn(record["sessionId"], argv, record["cwd"])
    elif where in (CMUX, TERMINAL):
        result = launch_elsewhere(record["sessionId"], record["title"], record["cwd"], argv, where, terminal_app)
    else:
        return False, "Unknown place to run the agent.", None
    if where != BACKGROUND and result.returncode != 0:
        return False, result.stderr.strip() or "Could not open the terminal.", None
    _registry.change(lambda data: data.__setitem__(record["sessionId"], record))
    return True, "Agent started.", record


def resume_agent(session_id):
    record = board_agent(session_id)
    if not record:
        return None
    return ptyhost.spawn(session_id, agent_argv(record, resume=True), record["cwd"])
