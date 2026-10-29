import json
import re
import subprocess

from ..config import INFER_MODEL
from ..root import root_dir

TYPES = ("feat", "fix", "chore", "refactor")
SUMMARY_RE = re.compile(r"[^a-z0-9]+")
JSON_RE = re.compile(r"\{.*\}", re.S)
PROMPT = (
    "Read Linear ticket {ticket} with the Linear tools. Reply with only one JSON object and no other text: "
    '{{"type": "feat, fix, chore or refactor", '
    '"summary": "2 to 5 lowercase words joined by dashes", '
    '"backend": "isolated if the work changes pikachu models or migrations or needs its own data, else shared", '
    '"mobile": "yes if it changes ProjectGo or OnSite, else no", '
    '"why": "one short sentence on the backend and mobile choice"}}'
)


def ask_claude(ticket):
    out = subprocess.run(
        ["claude", "-p", PROMPT.format(ticket=ticket), "--model", INFER_MODEL, "--output-format", "json",
         "--no-session-persistence", "--allowedTools", "mcp__claude_ai_Linear__get_issue"],
        cwd=root_dir(), capture_output=True, text=True, timeout=120,
    )
    reply = json.loads(out.stdout)
    if reply.get("is_error"):
        raise RuntimeError(reply.get("result") or "Claude could not read the ticket.")
    return json.loads(JSON_RE.search(reply["result"]).group(0))


def infer(ticket):
    try:
        guess = ask_claude(ticket)
    except Exception as e:
        return {"branch": ticket, "backend": "shared", "mobile": "no",
                "why": f"I could not read the ticket ({str(e)[:80]}), so these are the defaults."}
    kind = guess.get("type") if guess.get("type") in TYPES else "feat"
    summary = SUMMARY_RE.sub("-", str(guess.get("summary") or "").lower()).strip("-")
    return {
        "branch": f"{ticket}/{kind}/{summary}" if summary else ticket,
        "backend": "isolated" if guess.get("backend") == "isolated" else "shared",
        "mobile": "yes" if guess.get("mobile") == "yes" else "no",
        "why": str(guess.get("why") or ""),
    }
