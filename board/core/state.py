from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import agents, ptyhost
from .assets import repo_images
from .classify import action_reasons, classify, is_review_agent
from .config import AUTO_CLOSE_MERGED, STARTING_GRACE_SECONDS
from .github import fetch_pr, my_open_prs, reviewed_prs
from .sessions import auto_close_merged, find_transcript, live_sessions, recent_ended
from .root import platform_branch, platform_of
from .store import load_dismissed, load_titles
from .transcript import parse_transcript, tickets_in


def session_tickets(found, prs, cwd, branch=None, created=()):
    own_branches = {b for b in (branch, platform_branch(cwd)) if b}
    out = tickets_in(platform_branch(cwd) or "") + list(found)
    for p in prs:
        if p["key"] in created or p.get("branch") in own_branches:
            out += tickets_in(p.get("title") or "")
    return list(dict.fromkeys(out))[:4]


def is_work(sid, info, prs, cwd):
    if sid in agents.registry():
        return True
    branches = {b for b in (info.get("gitBranch"), platform_branch(cwd)) if b} if platform_of(cwd) else set()
    if any(tickets_in(b) for b in branches):
        return True
    created = set(info.get("createdPrs") or [])
    if any(p["key"] in created or p.get("branch") in branches for p in prs):
        return True
    if prs and "review" in (info.get("title") or "").lower() and is_review_agent(info, prs):
        return True
    first = (info.get("firstPrompt") or "").strip()
    return first.startswith("/") and bool(tickets_in(first))


def reviewed_ticket(prs):
    firsts = [tickets_in(p.get("title") or "")[:1] for p in prs]
    found = {t for f in firsts for t in f}
    return list(found) if prs and all(firsts) and len(found) == 1 else []


def starting_agents(known):
    """Agents the board started that have no transcript or session file. A new one would otherwise
    be missing until it has written. One that exited before it wrote does not show."""
    now = datetime.now(timezone.utc)
    pending = [(sid, record) for sid, record in list(agents.registry().items()) if sid not in known]
    running = {s["key"] for s in ptyhost.sessions() if not s["dead"]} if pending and ptyhost.available() else None
    out = []
    for sid, record in pending:
        if running is not None and record.get("tmux") and sid not in running and not find_transcript(sid):
            continue
        started = datetime.fromisoformat(record["createdAt"])
        starting = (now - started).total_seconds() <= STARTING_GRACE_SECONDS
        alive = running is not None and sid in running
        status = "working" if starting else "your_move" if alive else "ended"
        out.append(
            {
                "sessionId": sid, "name": None, "pid": None, "alive": alive, "busy": starting, "status": status,
                "reasons": ["no prompt yet"] if alive and not starting else [], "title": record["title"],
                "tickets": session_tickets(tickets_in(f"{record['title']} {record.get('prompt') or ''}"), [], record["cwd"]),
                "summary": None, "lastAssistant": None,
                "lastUserPrompt": record.get("prompt"), "pendingTool": None, "pendingQuestion": None,
                "lastActivity": record["createdAt"], "cwd": record["cwd"], "gitBranch": record.get("branch"),
                "remoteUrl": None, "resumeCmd": f"claude --resume {sid}", "prs": [], "work": True,
            }
        )
    return out


def build_state():
    live = live_sessions()
    entries = []
    for sid, meta in live.items():
        path = find_transcript(sid)
        entries.append((sid, path, meta, True))
    for sid, path in recent_ended(set(live)):
        entries.append((sid, path, None, False))
    seen = {sid for sid, *_ in entries}
    for sid in agents.registry():
        if sid not in seen:
            entries.append((sid, find_transcript(sid), None, False))

    parsed = []
    for sid, path, meta, alive in entries:
        if not path or not path.exists():
            continue
        try:
            info = parse_transcript(path)
        except Exception as e:
            info = {"title": None, "error": str(e), "tickets": [], "prs": []}
        if not alive and not info["tickets"] and not info["prs"] and sid not in agents.registry():
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
        waiting = (meta or {}).get("status") == "waiting"
        info["waitingFor"] = (meta or {}).get("waitingFor") if waiting else None
        status, reasons = classify((meta or {}).get("status"), alive, info, prs)
        tickets = session_tickets(info["tickets"], prs, info.get("cwd") or (meta or {}).get("cwd"),
                                  info.get("gitBranch"), set(info.get("createdPrs") or []))
        if not tickets and "review" in (info.get("title") or "").lower() and is_review_agent(info, prs):
            tickets = reviewed_ticket(prs)
        sessions.append(
            {
                "sessionId": sid,
                "name": (meta or {}).get("name"),
                "pid": (meta or {}).get("pid"),
                "alive": alive,
                "busy": (meta or {}).get("status") == "busy",
                "status": status,
                "reasons": reasons,
                "title": info.get("title") or (info.get("firstPrompt") or "")[:80]
                         or (agents.registry().get(sid) or {}).get("title") or sid[:8],
                "tickets": tickets,
                "summary": info.get("summary"),
                "lastAssistant": (info.get("lastAssistant") or "")[-600:],
                "lastUserPrompt": info.get("lastUserPrompt"),
                "pendingTool": info.get("pendingTool"),
                "pendingQuestion": info.get("pendingQuestion"),
                "waitingFor": info["waitingFor"],
                "waitingSince": (meta or {}).get("statusUpdatedAt") if waiting else None,
                "lastActivity": info.get("lastActivity"),
                "cwd": info.get("cwd") or (meta or {}).get("cwd"),
                "gitBranch": info.get("gitBranch"),
                "remoteUrl": f"https://claude.ai/code/{meta['bridgeSessionId']}" if meta and meta.get("bridgeSessionId") else None,
                "resumeCmd": f"claude --resume {sid}",
                "prs": prs,
                "work": is_work(sid, info, prs, info.get("cwd") or (meta or {}).get("cwd")),
            }
        )
    sessions += starting_agents({s["sessionId"] for s in sessions})
    titles = load_titles()
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
                "work": True,
            }
        )
    for s in sessions:
        s["autoTitle"] = s["title"]
        s["customTitle"] = titles.get(s["sessionId"])
        if s["customTitle"]:
            s["title"] = s["customTitle"]
    if AUTO_CLOSE_MERGED:
        auto_close_merged(sessions)
    dismissed = load_dismissed()
    for s in sessions:
        s["dismissed"] = not s["alive"] and (s.get("lastActivity") or "") <= dismissed.get(s["sessionId"], "")
    sessions.sort(key=lambda s: s.get("lastActivity") or "", reverse=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sessions": sessions,
        "repoImages": {repo: f"/assets/{f.name}" for repo, f in repo_images().items()},
    }
