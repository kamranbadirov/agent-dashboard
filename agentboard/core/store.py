import json
from datetime import datetime, timezone

from .config import DISMISSED_FILE, TITLES_FILE
from .sessions import live_sessions


def load_dismissed():
    try:
        return json.loads(DISMISSED_FILE.read_text())
    except Exception:
        return {}


def dismiss_session(session_id):
    if session_id in live_sessions():
        return False, "Close the agent before removing it."
    dismissed = load_dismissed()
    dismissed[session_id] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    DISMISSED_FILE.write_text(json.dumps(dismissed))
    return True, "Removed."


def load_titles():
    try:
        return json.loads(TITLES_FILE.read_text())
    except Exception:
        return {}


def rename_session(session_id, title):
    title = " ".join((title or "").split())[:120]
    titles = load_titles()
    if title:
        titles[session_id] = title
    else:
        titles.pop(session_id, None)
    TITLES_FILE.write_text(json.dumps(titles))
    return True, "Renamed." if title else "Title reset."
