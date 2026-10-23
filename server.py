#!/usr/bin/env python3
import fcntl
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
SESSIONS_DIR = HOME / ".claude" / "sessions"
PROJECTS_DIR = HOME / ".claude" / "projects"
HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "7777"))
ENDED_LOOKBACK_HOURS = int(os.environ.get("ENDED_LOOKBACK_HOURS", "72"))
STALE_HOURS = int(os.environ.get("STALE_HOURS", "24"))
AUTO_CLOSE_MERGED = os.environ.get("AUTO_CLOSE_MERGED", "1") != "0"
DISMISSED_FILE = HERE / "dismissed.json"
PR_CACHE_SECONDS = 90
WATCH_SECONDS = int(os.environ.get("WATCH_SECONDS", "60"))
NOTIFIED_FILE = HOME / ".claude" / "agent-dashboard-notified.json"
TAIL_BYTES = 600_000

TICKET_RE = re.compile(r"\b([A-Z]{2,6}-\d{1,5})\b")
PR_RE = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
TICKET_DENY_PREFIXES = ("UTF-", "ISO-", "SHA-", "AES-", "HTTP-", "ASD-", "RFC-", "PEP-", "TLS-")
TICKET_DENYLIST = {"DAT-107"}
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)

_pr_cache = {}
_pr_lock = threading.Lock()


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


def read_tail(path):
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()
        data = f.read()
    out = []
    for line in data.splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def read_head(path, limit=60):
    out = []
    with open(path, "rb") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def text_of(message):
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def tickets_in(text):
    text = REMINDER_RE.sub("", text or "")
    return [
        t for t in TICKET_RE.findall(text)
        if t not in TICKET_DENYLIST and not t.startswith(TICKET_DENY_PREFIXES)
    ]


def conversation_prs(path):
    prs = {}
    with open(path, "rb") as f:
        for line in f:
            if b"/pull/" not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("type") not in ("user", "assistant") or rec.get("isMeta"):
                continue
            for owner, repo, num in PR_RE.findall(REMINDER_RE.sub("", text_of(rec.get("message")))):
                prs[f"{owner}/{repo}#{num}"] = (owner, repo, int(num))
    return prs


def parse_transcript(path):
    head = read_head(path)
    tail = read_tail(path)
    info = {
        "title": None,
        "summary": None,
        "lastAssistant": None,
        "lastUserPrompt": None,
        "firstPrompt": None,
        "lastActivity": None,
        "cwd": None,
        "gitBranch": None,
        "pendingTool": None,
        "tickets": [],
        "prs": [],
    }

    for rec in head:
        if rec.get("type") == "user" and not rec.get("isMeta"):
            t = text_of(rec.get("message"))
            if t and not t.startswith("<"):
                info["firstPrompt"] = t[:300]
                break

    prs = conversation_prs(path)
    pending = {}
    for rec in tail:
        rtype = rec.get("type")
        if rtype == "custom-title":
            info["title"] = rec.get("customTitle")
            info["_custom"] = True
        elif rtype == "ai-title" and not info.get("_custom"):
            info["title"] = rec.get("aiTitle")
        elif rtype == "system" and rec.get("subtype") == "away_summary":
            info["summary"] = re.sub(r"\s*\(disable recaps in /config\)\s*$", "", rec.get("content") or "")
        if rec.get("timestamp") and rtype in ("user", "assistant"):
            info["lastActivity"] = rec["timestamp"]
        if rec.get("cwd"):
            info["cwd"] = rec["cwd"]
        if rec.get("gitBranch") and rec["gitBranch"] != "HEAD":
            info["gitBranch"] = rec["gitBranch"]

        msg = rec.get("message") or {}
        if rtype == "assistant":
            t = text_of(msg)
            if t.strip():
                info["lastAssistant"] = t
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    pending[block.get("id")] = block
        elif rtype == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        pending.pop(block.get("tool_use_id"), None)
            if not rec.get("isMeta"):
                t = text_of(msg)
                if t and not t.startswith("<"):
                    info["lastUserPrompt"] = t[:300]
                    pending.clear()

    if pending:
        last = list(pending.values())[-1]
        info["pendingTool"] = last.get("name")
        if last.get("name") == "AskUserQuestion":
            qs = (last.get("input") or {}).get("questions") or []
            if qs:
                info["pendingQuestion"] = qs[0].get("question")

    priority = []
    for src in (info["title"], info["gitBranch"], info["firstPrompt"]):
        for t in tickets_in(src or ""):
            if t not in priority:
                priority.append(t)
    info["tickets"] = priority[:4]
    info["prs"] = list(prs.values())
    info.pop("_custom", None)
    return info


def gh_json(args):
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=25
        )
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


PR_QUERY = """
query($owner:String!,$repo:String!,$num:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$num){
      number title url state isDraft reviewDecision headRefName updatedAt
      author{login}
      comments(last:30){nodes{author{login} createdAt}}
      reviews(last:30){nodes{author{login} state submittedAt commit{oid}}}
      reviewThreads(first:100){nodes{isResolved isOutdated comments(first:1){nodes{author{login}}}}}
      commits(last:1){nodes{commit{oid committedDate statusCheckRollup{state}}}}
      history: commits(last:50){nodes{commit{oid committedDate author{user{login}}}}}
    }
  }
}
"""


def commits_since_review(pr, author, viewer):
    mine = [
        r for r in (pr.get("reviews") or {}).get("nodes") or []
        if (r.get("author") or {}).get("login") == viewer
        and r.get("state") in ("CHANGES_REQUESTED", "COMMENTED", "APPROVED")
        and r.get("commit")
    ]
    if not mine:
        return None, []
    last_review = max(mine, key=lambda r: r.get("submittedAt") or "")
    base = last_review["commit"]["oid"]
    history = [n.get("commit") or {} for n in (pr.get("history") or {}).get("nodes") or []]
    oids = [c.get("oid") for c in history]
    if base in oids:
        newer = history[oids.index(base) + 1:]
    else:
        newer = [c for c in history if (c.get("committedDate") or "") > (last_review.get("submittedAt") or "")]
    if author != viewer:
        newer = [c for c in newer if ((c.get("author") or {}).get("user") or {}).get("login") != viewer]
    return base, newer


def fetch_pr(owner, repo, num, stamp=None):
    key = f"{owner}/{repo}#{num}"
    now = time.time()
    with _pr_lock:
        cached = _pr_cache.get(key)
        if cached and (now - cached[0] < PR_CACHE_SECONDS or (stamp and cached[2] == stamp)):
            return cached[1]
    data = gh_json(
        [
            "api", "graphql",
            "-f", f"query={PR_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"num={num}",
        ]
    )
    pr = (((data or {}).get("data") or {}).get("repository") or {}).get("pullRequest")
    result = None
    if pr:
        me = (pr.get("author") or {}).get("login")
        last_commit = ((pr.get("commits") or {}).get("nodes") or [{}])[-1].get("commit") or {}
        pushed_at = last_commit.get("committedDate") or ""
        bots = lambda login: (login or "").endswith("[bot]") or login in ("github-actions", "linear", "linear-code")
        unresolved = [
            th for th in (pr.get("reviewThreads") or {}).get("nodes") or []
            if not th.get("isResolved") and not th.get("isOutdated")
        ]
        new_comments = [
            c for c in (pr.get("comments") or {}).get("nodes") or []
            if (c.get("author") or {}).get("login") not in (me,) and not bots((c.get("author") or {}).get("login"))
            and c.get("createdAt", "") > pushed_at
        ]
        reviews = [
            r for r in (pr.get("reviews") or {}).get("nodes") or []
            if (r.get("author") or {}).get("login") != me and r.get("state") in ("CHANGES_REQUESTED", "COMMENTED", "APPROVED")
        ]
        base, newer = commits_since_review(pr, me, my_login())
        head = last_commit.get("oid")
        result = {
            "key": key,
            "author": me,
            "repo": repo,
            "number": pr["number"],
            "title": pr["title"],
            "url": pr["url"],
            "state": pr["state"],
            "isDraft": pr["isDraft"],
            "reviewDecision": pr.get("reviewDecision"),
            "branch": pr.get("headRefName"),
            "unresolvedThreads": len(unresolved),
            "newComments": len(new_comments),
            "reviewers": sorted({(r.get("author") or {}).get("login") for r in reviews}),
            "checks": (last_commit.get("statusCheckRollup") or {}).get("state"),
            "updatedAt": pr.get("updatedAt"),
            "headOid": head,
            "commitsSinceReview": len(newer),
            "sinceReviewUrl": f"{pr['url']}/files/{base}..{head}" if newer and base and head else None,
        }
    with _pr_lock:
        _pr_cache[key] = (now, result, stamp)
    return result


def my_open_prs():
    key = "__mine__"
    now = time.time()
    with _pr_lock:
        cached = _pr_cache.get(key)
        if cached and now - cached[0] < PR_CACHE_SECONDS:
            return cached[1]
    data = gh_json(
        [
            "search", "prs", "--author=@me", "--owner=pheedloop", "--state=open",
            "--limit", "60", "--json", "number,title,repository,url",
        ]
    ) or []
    with _pr_lock:
        _pr_cache[key] = (now, data, None)
    return data


def reviewed_prs():
    key = "__reviewed__"
    now = time.time()
    with _pr_lock:
        cached = _pr_cache.get(key)
        if cached and now - cached[0] < PR_CACHE_SECONDS:
            return cached[1]
    data = gh_json(
        [
            "search", "prs", "--reviewed-by=@me", "--owner=pheedloop", "--state=open",
            "--limit", "40", "--json", "number,title,repository,url,author,updatedAt",
        ]
    ) or []
    data = [pr for pr in data if (pr.get("author") or {}).get("login") != my_login()]
    with _pr_lock:
        _pr_cache[key] = (now, data, None)
    return data


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


_me = None


def my_login():
    global _me
    if _me is None:
        try:
            _me = subprocess.run(
                ["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, timeout=15
            ).stdout.strip()
        except Exception:
            _me = ""
    return _me


def action_reasons(info, prs, sess_status):
    reasons = []
    if info.get("pendingTool") and sess_status != "busy":
        if info.get("pendingQuestion"):
            reasons.append("answer question")
        else:
            reasons.append(f"approve {info['pendingTool']}")
    for p in prs:
        if p["state"] != "OPEN":
            continue
        ref = f"{p['repo']}#{p['number']}"
        if p.get("author") != my_login():
            n = p.get("commitsSinceReview")
            if n:
                reasons.append(f"{n} new commit{'s' if n > 1 else ''} on {ref} since your review")
            continue
        talk = p["unresolvedThreads"] + p["newComments"]
        if talk:
            reasons.append(f"{talk} comment{'s' if talk > 1 else ''} on {ref}")
        if p["reviewDecision"] == "CHANGES_REQUESTED":
            reasons.append(f"changes requested on {ref}")
        if p["checks"] in ("FAILURE", "ERROR"):
            reasons.append(f"checks failing on {ref}")
        if p["reviewDecision"] == "APPROVED" and not p["isDraft"]:
            reasons.append(f"merge {ref}")
        if p["isDraft"] and not talk:
            reasons.append(f"mark {ref} ready")
    return reasons


def is_review_agent(info, prs):
    mine = [p for p in prs if p.get("author") == my_login()]
    if mine:
        return False
    return bool(prs) or "review" in (info.get("title") or "").lower()


def classify(sess_status, alive, info, prs):
    reasons = action_reasons(info, prs, sess_status)
    last = info.get("lastActivity")
    stale = not last or (
        datetime.now(timezone.utc) - datetime.fromisoformat(last.replace("Z", "+00:00"))
    ).total_seconds() > STALE_HOURS * 3600
    if prs and all(p["state"] in ("MERGED", "CLOSED") for p in prs):
        return "done", reasons
    if alive and sess_status == "busy":
        return "working", reasons
    if reasons:
        return "your_move", reasons
    if is_review_agent(info, prs):
        if not alive or stale:
            return "ended", reasons
        return "reviewing", ["review agent idle"]
    if any(p["state"] == "OPEN" for p in prs):
        return "in_review", ["waiting on reviewers"]
    if not alive or stale:
        return "ended", reasons
    return "your_move", ["agent finished"]


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


def load_dismissed():
    try:
        return json.loads(DISMISSED_FILE.read_text())
    except Exception:
        return {}


def dismiss_session(session_id):
    if session_id in live_sessions():
        return False, "Close the agent before removing it."
    dismissed = load_dismissed()
    dismissed[session_id] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    DISMISSED_FILE.write_text(json.dumps(dismissed))
    return True, "Removed."


def build_state():
    live = live_sessions()
    entries = []
    for sid, meta in live.items():
        path = find_transcript(sid)
        entries.append((sid, path, meta, True))
    for sid, path in recent_ended(set(live)):
        entries.append((sid, path, None, False))

    parsed = []
    for sid, path, meta, alive in entries:
        if not path or not path.exists():
            continue
        try:
            info = parse_transcript(path)
        except Exception as e:
            info = {"title": None, "error": str(e), "tickets": [], "prs": []}
        if not alive and not info["tickets"] and not info["prs"]:
            continue
        if not alive and not info.get("lastActivity"):
            continue
        parsed.append((sid, path, meta, alive, info))

    mine = my_open_prs()
    want = {}
    for _, _, _, _, info in parsed:
        for owner, repo, num in info["prs"]:
            want[f"{owner}/{repo}#{num}"] = (owner, repo, num)
        for t in info["tickets"]:
            for pr in mine:
                if t in (pr.get("title") or ""):
                    repo = pr["repository"]["nameWithOwner"]
                    owner, name = repo.split("/")
                    want[f"{repo}#{pr['number']}"] = (owner, name, pr["number"])

    reviewed = reviewed_prs()
    stamps = {}
    for pr in reviewed:
        repo = pr["repository"]["nameWithOwner"]
        owner, name = repo.split("/")
        k = f"{repo}#{pr['number']}"
        want.setdefault(k, (owner, name, pr["number"]))
        stamps[k] = pr.get("updatedAt")

    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = dict(zip(want, pool.map(lambda k: fetch_pr(*want[k], stamp=stamps.get(k)), want)))

    sessions = []
    for sid, path, meta, alive, info in parsed:
        prs = []
        keys = [f"{o}/{r}#{n}" for o, r, n in info["prs"]]
        for t in info["tickets"]:
            for pr in mine:
                if t in (pr.get("title") or ""):
                    keys.append(f"{pr['repository']['nameWithOwner']}#{pr['number']}")
        for k in dict.fromkeys(keys):
            if fetched.get(k):
                prs.append(fetched[k])
        status, reasons = classify((meta or {}).get("status"), alive, info, prs)
        sessions.append(
            {
                "sessionId": sid,
                "name": (meta or {}).get("name"),
                "pid": (meta or {}).get("pid"),
                "alive": alive,
                "busy": (meta or {}).get("status") == "busy",
                "status": status,
                "reasons": reasons,
                "title": info.get("title") or (info.get("firstPrompt") or "")[:80] or sid[:8],
                "tickets": info["tickets"],
                "summary": info.get("summary"),
                "lastAssistant": (info.get("lastAssistant") or "")[-600:],
                "lastUserPrompt": info.get("lastUserPrompt"),
                "pendingTool": info.get("pendingTool"),
                "pendingQuestion": info.get("pendingQuestion"),
                "lastActivity": info.get("lastActivity"),
                "cwd": info.get("cwd") or (meta or {}).get("cwd"),
                "gitBranch": info.get("gitBranch"),
                "remoteUrl": f"https://claude.ai/code/{meta['bridgeSessionId']}" if meta and meta.get("bridgeSessionId") else None,
                "resumeCmd": f"claude --resume {sid}",
                "prs": prs,
            }
        )
    linked = {p["key"] for s in sessions for p in s["prs"]}
    for pr in reviewed:
        k = f"{pr['repository']['nameWithOwner']}#{pr['number']}"
        p = fetched.get(k)
        if k in linked or not p or not p.get("commitsSinceReview"):
            continue
        sessions.append(
            {
                "sessionId": f"pr:{k}",
                "name": None,
                "pid": None,
                "alive": False,
                "status": "your_move",
                "reasons": action_reasons({}, [p], None),
                "title": p["title"],
                "tickets": tickets_in(p["title"])[:2],
                "summary": None,
                "lastAssistant": None,
                "lastUserPrompt": None,
                "pendingTool": None,
                "pendingQuestion": None,
                "lastActivity": p.get("updatedAt"),
                "cwd": None,
                "gitBranch": p.get("branch"),
                "remoteUrl": None,
                "resumeCmd": None,
                "prs": [p],
            }
        )
    if AUTO_CLOSE_MERGED:
        auto_close_merged(sessions)
    dismissed = load_dismissed()
    sessions = [
        s for s in sessions
        if s["alive"] or (s.get("lastActivity") or "") > dismissed.get(s["sessionId"], "")
    ]
    sessions.sort(key=lambda s: s.get("lastActivity") or "", reverse=True)
    return {"generatedAt": datetime.now(timezone.utc).isoformat(), "sessions": sessions}


def send_notification(title, message, url, group):
    if shutil.which("terminal-notifier"):
        subprocess.run(
            ["terminal-notifier", "-title", title, "-message", message, "-open", url,
             "-group", group, "-sound", "default"],
            capture_output=True, timeout=10,
        )
    else:
        script = f"display notification {json.dumps(message)} with title {json.dumps(title)} sound name \"default\""
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)


def notify_new_commits(state):
    due = {}
    for s in state["sessions"]:
        for p in s["prs"]:
            if p["state"] == "OPEN" and p.get("author") != my_login() and p.get("commitsSinceReview"):
                due[f"{p['key']}@{p['headOid']}"] = p
    NOTIFIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTIFIED_FILE, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        raw = f.read()
        try:
            seen = set(json.loads(raw)) if raw else None
        except Exception:
            seen = set()
        fresh = [] if seen is None else [p for k, p in due.items() if k not in seen]
        f.seek(0)
        f.truncate()
        json.dump(sorted((seen or set()) | set(due)), f)
    for p in fresh:
        n = p["commitsSinceReview"]
        send_notification(
            f"{p['repo']}#{p['number']}: {n} new commit{'s' if n > 1 else ''}",
            f"{p['author']} pushed since your review. {p['title']}",
            p.get("sinceReviewUrl") or p["url"],
            p["key"],
        )


def watch():
    while True:
        try:
            notify_new_commits(build_state())
        except Exception as e:
            print(f"watch failed: {e}", file=sys.stderr)
        time.sleep(WATCH_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            try:
                body = json.dumps(build_state()).encode()
                self._send(200, body, "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        host = self.headers.get("Host", "").split(":")[0]
        json_body = self.headers.get("Content-Type", "").startswith("application/json")
        actions = {"/api/close": close_session, "/api/dismiss": dismiss_session}
        if self.path not in actions:
            self._send(404, b"not found", "text/plain")
        elif host not in ("localhost", "127.0.0.1") or not json_body:
            self._send(403, b"forbidden", "text/plain")
        else:
            try:
                size = int(self.headers.get("Content-Length", 0))
                session_id = json.loads(self.rfile.read(size)).get("sessionId", "")
            except Exception:
                self._send(400, json.dumps({"ok": False, "message": "Bad request."}).encode(), "application/json")
                return
            ok, message = actions[self.path](session_id)
            self._send(200 if ok else 409, json.dumps({"ok": ok, "message": message}).encode(), "application/json")


def main():
    if "--tui" in sys.argv:
        venv_python = HERE / ".venv" / "bin" / "python"
        os.execv(str(venv_python), [str(venv_python), str(HERE / "board.py")])
    if "--json" in sys.argv:
        print(json.dumps(build_state(), indent=2))
        return
    threading.Thread(target=watch, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Agent dashboard on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
