import fcntl
import json
import shutil
import subprocess

from .config import NEEDS_YOU_FILE, NOTIFIED_FILE, NOTIFY_NEEDS_YOU
from .github import my_login


def send_notification(title, message, url, group):
    if shutil.which("terminal-notifier"):
        subprocess.run(
            ["terminal-notifier", "-title", title, "-message", message, *(["-open", url] if url else []),
             "-group", group, "-sound", "default"],
            capture_output=True, timeout=10,
        )
    else:
        script = f"display notification {json.dumps(message)} with title {json.dumps(title)} sound name \"default\""
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)


def unseen(path, due):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        raw = f.read()
        try:
            seen = set(json.loads(raw)) if raw else None
        except Exception:
            seen = set()
        fresh = [] if seen is None else [v for k, v in due.items() if k not in seen]
        f.seek(0)
        f.truncate()
        json.dump(sorted((seen or set()) | set(due)), f)
    return fresh


def notify_new_commits(state):
    due = {}
    for s in state["sessions"]:
        for p in s["prs"]:
            if p["state"] == "OPEN" and p.get("author") != my_login() and p.get("commitsSinceReview"):
                due[f"{p['key']}@{p['headOid']}"] = p
    for p in unseen(NOTIFIED_FILE, due):
        n = p["commitsSinceReview"]
        send_notification(
            f"{p['repo']}#{p['number']}: {n} new commit{'s' if n > 1 else ''}",
            f"{p['author']} pushed since your review. {p['title']}",
            p.get("sinceReviewUrl") or p["url"],
            p["key"],
        )


def notify_needs_you(state):
    if not NOTIFY_NEEDS_YOU:
        return
    due = {}
    for s in state["sessions"]:
        if s.get("alive") and not s.get("busy") and s.get("pendingTool"):
            due[f"{s['sessionId']}@{s.get('lastActivity')}"] = s
    for s in unseen(NEEDS_YOU_FILE, due):
        what = "has a question for you" if s.get("pendingQuestion") else f"waits for you to approve {s['pendingTool']}"
        send_notification(s["title"], f"The agent {what}.", s.get("remoteUrl"), s["sessionId"])
