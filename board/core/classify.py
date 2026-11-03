from datetime import datetime, timezone

from .config import STALE_HOURS
from .github import my_login


def action_reasons(info, prs, sess_status):
    reasons = []
    if info.get("pendingTool") and sess_status != "busy":
        if info.get("pendingQuestion"):
            reasons.append("answer question")
        else:
            reasons.append(f"approve {info['pendingTool']}")
    elif sess_status == "waiting":
        reasons.append(info.get("waitingFor") or "input needed")
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


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def asked_after_close(info, prs):
    asked = parse_time(info.get("lastPromptAt"))
    closed = [parse_time(p.get("closedAt")) for p in prs]
    return bool(asked) and all(closed) and asked > max(closed)


def classify(sess_status, alive, info, prs):
    reasons = action_reasons(info, prs, sess_status)
    last = info.get("lastActivity")
    stale = not last or (datetime.now(timezone.utc) - parse_time(last)).total_seconds() > STALE_HOURS * 3600
    if prs and all(p["state"] in ("MERGED", "CLOSED") for p in prs) and not asked_after_close(info, prs):
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
