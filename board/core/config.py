import os
import re
from pathlib import Path

HOME = Path.home()
SESSIONS_DIR = HOME / ".claude" / "sessions"
PROJECTS_DIR = HOME / ".claude" / "projects"
ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "board" / "assets"
PORT = int(os.environ.get("PORT", "7777"))
ENDED_LOOKBACK_HOURS = int(os.environ.get("ENDED_LOOKBACK_HOURS", "72"))
STARTING_GRACE_SECONDS = int(os.environ.get("STARTING_GRACE_SECONDS", "300"))
STALE_HOURS = int(os.environ.get("STALE_HOURS", "24"))
AUTO_CLOSE_MERGED = os.environ.get("AUTO_CLOSE_MERGED", "1") != "0"
DISMISSED_FILE = ROOT / "dismissed.json"
TITLES_FILE = ROOT / "titles.json"
PR_CACHE_SECONDS = 300
WATCH_SECONDS = int(os.environ.get("WATCH_SECONDS", "60"))
NOTIFIED_FILE = HOME / ".claude" / "agent-dashboard-notified.json"
TAIL_BYTES = 600_000

GITHUB_ORG = "pheedloop"
ROOT_REPO = Path(os.environ.get("ROOT_REPO", HOME / "Documents" / "root"))
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
