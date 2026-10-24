from datetime import datetime, timezone

from rich.cells import cell_len
from rich.text import Text

from .icons import GITHUB_ICON, NERD, REPO_ICONS
from .theme import AQUA, GRAY, GREEN, INK, MUTED, RED


def ago(ts):
    if not ts:
        return ""
    secs = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def headline(s):
    reasons = s["reasons"]
    if not reasons:
        return "Check the result"
    first = reasons[0]
    if first == "answer question":
        return "Answer a question"
    if first == "agent finished":
        return "Check the result"
    if first.startswith("approve "):
        return f"Approve {first[8:]}"
    return first[0].upper() + first[1:]


def pr_badges(p):
    out = []
    if p["state"] == "MERGED":
        out.append(("merged", GREEN))
    elif p["state"] == "CLOSED":
        out.append(("closed", GRAY))
    if p["isDraft"]:
        out.append(("draft", GRAY))
    if p["state"] == "OPEN":
        if p.get("commitsSinceReview"):
            n = p["commitsSinceReview"]
            out.append((f"{n} new commit{'s' if n > 1 else ''} since your review", AQUA))
        if p["unresolvedThreads"]:
            out.append((f"{p['unresolvedThreads']} unresolved", AQUA))
        if p["newComments"]:
            out.append((f"{p['newComments']} new comments", AQUA))
        if p["reviewDecision"] == "CHANGES_REQUESTED":
            out.append(("changes requested", AQUA))
        if p["reviewDecision"] == "APPROVED":
            out.append(("approved", GREEN))
        if p["checks"] in ("FAILURE", "ERROR"):
            out.append(("checks failing", RED))
        elif p["checks"] == "PENDING":
            out.append(("checks running", MUTED))
        if not out:
            out.append(("in review", GREEN))
    return out


def chips(items, style="on #30363d"):
    t = Text()
    for i, item in enumerate(items):
        if i:
            t.append(" ")
        t.append(f" {item} ", style=f"{INK} {style}")
    return t


def prs_for(s, ticket):
    t = ticket.lower()
    return [p for p in s["prs"] if t in (p.get("title") or "").lower() or t in (p.get("branch") or "").lower()]


def ticket_line(s):
    t = Text()
    links = []
    for i, ticket in enumerate(s["tickets"][:2]):
        if i:
            t.append(" ")
        prs = prs_for(s, ticket)
        start = t.cell_len
        t.append(f" {ticket} ", style=f"{INK} on #30363d")
        if prs and not NERD and not any(REPO_ICONS.get(p["repo"].lower()) for p in prs):
            links.append((start, t.cell_len, prs[0]["url"]))
        for p in prs:
            icon = REPO_ICONS.get(p["repo"].lower()) or (GITHUB_ICON if NERD else None)
            if not icon:
                continue
            t.append(" ")
            links.append((t.cell_len, t.cell_len + cell_len(icon), p["url"]))
            dim = p["state"] in ("MERGED", "CLOSED") and icon == GITHUB_ICON
            t.append(icon, style=GREEN if dim and p["state"] == "MERGED" else MUTED if dim else INK)
    return t, links
