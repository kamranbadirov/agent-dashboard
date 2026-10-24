import glob
import json
import os
import signal
import time
from pathlib import Path

from .config import ENDED_LOOKBACK_HOURS, PROJECTS_DIR, SESSIONS_DIR


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def find_transcript(session_id):
    hits = glob.glob(str(PROJECTS_DIR / "*" / f"{session_id}.jsonl"))
    return Path(hits[0]) if hits else None


def live_sessions():
    out = {}
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if not pid_alive(d.get("pid", -1)):
            continue
        out[d["sessionId"]] = d
    return out


def recent_ended(live_ids):
    cutoff = time.time() - ENDED_LOOKBACK_HOURS * 3600
    out = []
    for p in PROJECTS_DIR.glob("*/*.jsonl"):
        sid = p.stem
        if sid in live_ids:
            continue
        try:
            if p.stat().st_mtime < cutoff:
                continue
        except FileNotFoundError:
            continue
        out.append((sid, p))
    return out


def close_session(session_id):
    meta = live_sessions().get(session_id)
    if not meta:
        return False, "That agent is not running."
    pid = meta["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True, "Already closed."
    except PermissionError:
        return False, "Not allowed to close that process."
    for _ in range(20):
        if not pid_alive(pid):
            return True, "Closed."
        time.sleep(0.1)
    return True, "Close requested; the agent is still shutting down."


def auto_close_merged(sessions):
    for s in sessions:
        if s["alive"] and not s["busy"] and s["status"] == "done":
            ok, _ = close_session(s["sessionId"])
            if ok:
                s["alive"] = False
