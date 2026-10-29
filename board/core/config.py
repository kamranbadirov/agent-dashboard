import os
import re
from pathlib import Path

HOME = Path.home()
SESSIONS_DIR = HOME / ".claude" / "sessions"
PROJECTS_DIR = HOME / ".claude" / "projects"
ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "board" / "assets"
ENDED_LOOKBACK_HOURS = int(os.environ.get("ENDED_LOOKBACK_HOURS", "72"))
STARTING_GRACE_SECONDS = int(os.environ.get("STARTING_GRACE_SECONDS", "300"))
STALE_HOURS = int(os.environ.get("STALE_HOURS", "24"))
AUTO_CLOSE_MERGED = os.environ.get("AUTO_CLOSE_MERGED", "1") != "0"
DISMISSED_FILE = ROOT / "dismissed.json"
TITLES_FILE = ROOT / "titles.json"
PR_CACHE_SECONDS = 300
NOTIFIED_FILE = HOME / ".claude" / "agent-dashboard-notified.json"
NEEDS_YOU_FILE = HOME / ".claude" / "agent-dashboard-needs-you.json"
NOTIFY_NEEDS_YOU = os.environ.get("NOTIFY_NEEDS_YOU", "1") != "0"
TAIL_BYTES = 600_000

GITHUB_ORG = "pheedloop"


def find_root_repo():
    if os.environ.get("ROOT_REPO"):
        return Path(os.environ["ROOT_REPO"])
    if (ROOT.parent / "scripts" / "new.sh").is_file():
        return ROOT.parent
    return HOME / "Documents" / "root"


ROOT_REPO = find_root_repo()
AGENT_COMMAND = os.environ.get("AGENT_COMMAND", "claude")
AGENTS_FILE = ROOT / "agents.json"
TERMINALS_DIR = ROOT / "terminals"
TERMINAL_BUFFER_BYTES = 256_000
TERMINAL_LOG_FLUSH_SECONDS = 2
JSON_WRITE_DELAY_SECONDS = 0.5

TICKET_RE = re.compile(r"\b([A-Z]{2,6}-\d{1,5})\b")
PR_RE = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
TICKET_DENY_PREFIXES = ("UTF-", "ISO-", "SHA-", "AES-", "HTTP-", "ASD-", "RFC-", "PEP-", "TLS-")
TICKET_DENYLIST = {"DAT-107"}
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
