from datetime import datetime, timezone

from rich.text import Text

from ..core.config import GITHUB_ORG
from ..core.transcript import tickets_in
from .theme import BLUE, GREEN, INK, LINE, MUTED, RED

LOG_TAIL = 12


def job_session(job):
    """A running or failed setup job, shaped like an agent so the board can show it as a tile."""
    failed = job.state == "failed"
    return {
        "sessionId": f"job:{job.id}", "name": None, "pid": None, "alive": False, "busy": False,
        "status": "your_move" if failed else "setting_up",
        "reasons": ["setup failed"] if failed else [],
        "title": job.label, "tickets": [], "prs": [], "summary": None, "lastAssistant": None,
        "lastUserPrompt": None, "pendingTool": None,
        "pendingQuestion": job.error if failed else job.current_step,
        "lastActivity": datetime.fromtimestamp(job.started, timezone.utc).isoformat(),
        "cwd": None, "gitBranch": None, "remoteUrl": None, "resumeCmd": None, "job": job,
    }


def job_text(job):
    text = Text()
    text.append("Steps\n", style=f"bold {INK}")
    for i, step in enumerate(job.steps):
        last = i == len(job.steps) - 1
        if job.state == "running" and last:
            text.append("  ◌ ", style=INK)
        elif job.state == "failed" and last:
            text.append("  ✕ ", style=RED)
        else:
            text.append("  ✓ ", style=GREEN)
        text.append(step + "\n", style=INK)
    text.append("\nOutput\n", style=f"bold {INK}")
    for line in list(job.log)[-LOG_TAIL:]:
        text.append(line + "\n", style=MUTED)
    return text


def progress_bar(fraction, width):
    filled = round(max(0, min(1, fraction)) * width)
    bar = Text("━" * filled, style=BLUE)
    bar.append("━" * (width - filled), style=LINE)
    return bar


PLACES = {"background": "in the board", "terminal": "in a terminal"}


def pr_stub(pr):
    """A PR known only from the wizard's answers: enough for its repo logo and link, until GitHub is asked."""
    repo, number = pr["repo"], pr["number"]
    return {"key": f"{GITHUB_ORG}/{repo}#{number}", "repo": repo, "number": number, "state": "OPEN", "isDraft": False,
            "title": f"PR {number}", "branch": "", "author": "", "unresolvedThreads": 0, "newComments": 0,
            "reviewDecision": None, "checks": None, "commitsSinceReview": 0,
            "url": f"https://github.com/{GITHUB_ORG}/{repo}/pull/{number}"}


def with_agent_record(session, record):
    """A new agent has no transcript yet, so its tile would show only a session ID. Fill in what the
    board knows from starting it: the name typed in the wizard, the ticket, the branch and where it runs."""
    session = dict(session)
    if not session.get("customTitle"):
        session["title"] = record["title"]
    session["tickets"] = session["tickets"] or list(dict.fromkeys(tickets_in(f"{record['title']} {record['prompt']}")))[:2]
    session["gitBranch"] = session.get("gitBranch") or record.get("branch")
    session["name"] = session.get("name") or PLACES.get(record["where"])
    known = {(p["repo"], p["number"]) for p in session["prs"]}
    session["prs"] = session["prs"] + [pr_stub(p) for p in record.get("prs", []) if (p["repo"], p["number"]) not in known]
    return session
