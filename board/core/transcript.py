import json
import re

from .config import PR_RE, REMINDER_RE, TAIL_BYTES, TICKET_DENY_PREFIXES, TICKET_DENYLIST, TICKET_RE

TICKET_BYTES_RE = re.compile(TICKET_RE.pattern.encode())
WORK_TICKET_RES = (
    re.compile(r"\b([A-Z]{2,6}-\d{1,5})/(?:feat|fix|chore|refactor|task|hotfix|bug)/"),
    re.compile(r"^\s*(?i:(?:please |now |let'?s |can you )?(?:/\S+|implement|build|fix|review|work on|pick up|start|continue)\s+(?:on |the )?(?:ticket )?)([A-Z]{2,6}-\d{1,5})\b"),
)


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


def prompt_ticket(path):
    found = None
    with open(path, "rb") as f:
        for line in f:
            if b'"type":"user"' not in line or not TICKET_BYTES_RE.search(line):
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("isMeta"):
                continue
            text = text_of(rec.get("message"))
            if text.startswith("<"):
                continue
            text = REMINDER_RE.sub("", text)
            tickets = [m for r in WORK_TICKET_RES for m in r.findall(text) if tickets_in(m)]
            if tickets:
                found = tickets[-1]
    return found


def is_pr_create(block):
    name = block.get("name") or ""
    command = str((block.get("input") or {}).get("command") or "")
    return name.endswith("create_pull_request") or (name == "Bash" and "gh pr create" in command)


def result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content or [] if isinstance(part, dict))


def created_prs(path):
    creating, out = set(), set()
    with open(path, "rb") as f:
        for line in f:
            if b"gh pr create" not in line and b"create_pull_request" not in line and b"/pull/" not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            content = (rec.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and is_pr_create(block):
                    creating.add(block.get("id"))
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in creating:
                    out.update(f"{o}/{r}#{n}" for o, r, n in PR_RE.findall(result_text(block)))
    return sorted(out)


def parse_transcript(path):
    head = read_head(path)
    tail = read_tail(path)
    info = {
        "title": None,
        "summary": None,
        "lastAssistant": None,
        "lastUserPrompt": None,
        "lastPromptAt": None,
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
                    info["lastPromptAt"] = rec.get("timestamp")
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
    if not priority:
        priority = [t for t in [prompt_ticket(path)] if t]
    info["tickets"] = priority[:4]
    info["prs"] = list(prs.values())
    info["createdPrs"] = created_prs(path)
    info.pop("_custom", None)
    return info
