from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import agents
from .assets import repo_images
from .classify import action_reasons, classify
from .config import AUTO_CLOSE_MERGED, STARTING_GRACE_SECONDS
from .github import fetch_pr, my_open_prs, reviewed_prs
from .sessions import auto_close_merged, find_transcript, live_sessions, recent_ended
from .store import load_dismissed, load_titles
from .transcript import parse_transcript, tickets_in


def starting_agents(known):
    """Agents the board started that have no transcript or session file. A new one would otherwise
    be missing until it has written; one that never wrote stays as an ended tile until dismissed."""
    now = datetime.now(timezone.utc)
    out = []
    for sid, record in list(agents.registry().items()):
        if sid in known:
            continue
        started = datetime.fromisoformat(record["createdAt"])
        starting = (now - started).total_seconds() <= STARTING_GRACE_SECONDS
        out.append(
            {
                "sessionId": sid, "name": None, "pid": None, "alive": False, "busy": starting, "status": "working" if starting else "ended",
                "reasons": [], "title": record["title"], "tickets": [], "summary": None, "lastAssistant": None,
                "lastUserPrompt": record.get("prompt"), "pendingTool": None, "pendingQuestion": None,
                "lastActivity": record["createdAt"], "cwd": record["cwd"], "gitBranch": record.get("branch"),
                "remoteUrl": None, "resumeCmd": f"claude --resume {sid}", "prs": [],
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
    sessions = [
        s for s in sessions
        if s["alive"] or (s.get("lastActivity") or "") > dismissed.get(s["sessionId"], "")
    ]
    sessions.sort(key=lambda s: s.get("lastActivity") or "", reverse=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sessions": sessions,
        "repoImages": {repo: f"/assets/{f.name}" for repo, f in repo_images().items()},
    }
