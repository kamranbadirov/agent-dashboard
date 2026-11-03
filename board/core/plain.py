import json
import re
import subprocess
import threading
import time

from .cache import JsonFile
from .config import INFER_MODEL, PLAIN_FILE, PLAIN_RECHECK_SECONDS
from .root import root_dir

JSON_RE = re.compile(r"\{.*\}", re.S)
FIELDS = ("big_picture", "what", "why", "done_when")
TOOLS = "mcp__claude_ai_Linear__get_issue,mcp__claude_ai_Linear__get_project"
PROMPT = (
    "Read Linear ticket {ticket} with get_issue. If it belongs to a project, read the project with get_project.\n"
    "{known}"
    "Explain the ticket to a person who is new to software, who switches between many tasks and needs to "
    "remember this one fast. Use short sentences and everyday words. Do not use jargon, code names, file names, "
    "or acronyms. When a product name is needed, say what it is in a few words.\n"
    "Reply with only one JSON object and no other text:\n"
    '{{"updated_at": "the ticket\'s updatedAt from Linear", '
    '"big_picture": "one or two sentences: the goal of the parent project, or of the ticket when it has no project", '
    '"what": "one or two sentences: the change, as a user would notice it", '
    '"why": "one or two sentences: the problem it solves, and for whom", '
    '"done_when": "one sentence: what is true when the work is finished"}}'
)
KNOWN = ('The text you wrote before was for updatedAt "{updated_at}". If the ticket\'s updatedAt is still the same, '
         'reply with only {{"unchanged": true}}.\n')

_cache = JsonFile(PLAIN_FILE, {})
_busy = set()
_errors = {}
_lock = threading.Lock()


def cached(ticket):
    with _lock:
        return _cache.data.get(ticket), _errors.get(ticket), ticket in _busy


def is_due(ticket):
    entry, _, busy = cached(ticket)
    return not busy and (not entry or time.time() - entry.get("checkedAt", 0) > PLAIN_RECHECK_SECONDS)


def ask_claude(ticket, entry):
    known = KNOWN.format(updated_at=entry["updatedAt"]) if entry and entry.get("updatedAt") else ""
    out = subprocess.run(
        ["claude", "-p", PROMPT.format(ticket=ticket, known=known), "--model", INFER_MODEL, "--output-format", "json",
         "--no-session-persistence", "--allowedTools", TOOLS],
        cwd=root_dir(), capture_output=True, text=True, timeout=180,
    )
    reply = json.loads(out.stdout)
    if reply.get("is_error"):
        raise RuntimeError(reply.get("result") or "Claude could not read the ticket.")
    return json.loads(JSON_RE.search(reply["result"]).group(0))


def refresh(ticket, force=False):
    with _lock:
        if ticket in _busy:
            return False
        _busy.add(ticket)
        _errors.pop(ticket, None)
        entry = _cache.data.get(ticket)
    try:
        answer = ask_claude(ticket, None if force else entry)
        now = time.time()
        if answer.get("unchanged") and entry:
            _cache.change(lambda data: data[ticket].update(checkedAt=now))
        else:
            text = {field: str(answer.get(field) or "").strip() for field in FIELDS}
            fresh = {"text": text, "updatedAt": answer.get("updated_at"), "checkedAt": now}
            _cache.change(lambda data: data.__setitem__(ticket, fresh))
    except Exception as e:
        with _lock:
            _errors[ticket] = str(e)[:160] or "Could not read the ticket."
    finally:
        with _lock:
            _busy.discard(ticket)
    return True


def where_it_stands(session):
    recap = (session or {}).get("summary") or ""
    sentences = re.split(r"(?<=[.!?])\s+", recap.strip())
    return " ".join(sentences[:2]).strip()
