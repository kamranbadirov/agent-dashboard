import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Static

from server import build_state, close_session, dismiss_session, notify_new_commits

REFRESH_SECONDS = 20

AQUA = "#2dd4bf"
RED = "#f0525a"
BLUE = "#5b8def"
GREEN = "#3fb950"
GRAY = "#8b949e"
INK = "#e6edf3"
MUTED = "#8b949e"
GITHUB_ICON = "\uf09b"

SECTIONS = [
    ("your_move", "Needs you", AQUA),
    ("working", "Running", RED),
    ("reviewing", "Reviewing PRs", BLUE),
    ("in_review", "Waiting on reviewers", GREEN),
    ("done", "Done", GRAY),
    ("ended", "Inactive", GRAY),
]
COLOR = {k: c for k, _, c in SECTIONS}
NAME = {k: n for k, n, _ in SECTIONS}


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


def nerd_font():
    forced = os.environ.get("NERD_FONT")
    if forced in ("0", "1"):
        return forced == "1"
    if os.environ.get("TERM_PROGRAM") == "ghostty":
        return True
    dirs = [Path.home() / "Library" / "Fonts", Path("/Library/Fonts"),
            Path.home() / ".local" / "share" / "fonts", Path("/usr/share/fonts")]
    return any(next(d.glob("**/*[Nn]erd*"), None) for d in dirs if d.is_dir())


NERD = nerd_font()


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
        if prs and not NERD:
            links.append((start, t.cell_len, prs[0]["url"]))
        if NERD:
            for p in prs:
                t.append(" ")
                links.append((t.cell_len, t.cell_len + 1, p["url"]))
                t.append(GITHUB_ICON, style=GREEN if p["state"] == "MERGED" else MUTED if p["state"] == "CLOSED" else INK)
    return t, links


class AgentTile(Widget, can_focus=True):
    def __init__(self, session):
        super().__init__(classes=f"tile {session['status']}")
        self.session = session
        self.links = []

    def render(self):
        s = self.session
        color = COLOR.get(s["status"], GRAY)
        width = max(10, self.size.width - 2)
        label = headline(s) if s["status"] == "your_move" else NAME.get(s["status"], s["status"])
        refs = " ".join(f"#{p['number']}" for p in s["prs"][:3])
        muted = s["status"] in ("done", "ended")
        top = Text(label, style=f"bold {color}")
        top.truncate(width - 3, overflow="ellipsis")
        top.append(" " * max(1, width - top.cell_len - 1))
        top.append("✕", style=f"bold {INK}")
        lines = [
            top,
            Text(s["title"], style=f"bold {MUTED if muted else INK}"),
            Text(s.get("pendingQuestion") or refs, style=MUTED),
        ]
        when = ago(s["lastActivity"])
        bottom, self.links = ticket_line(s)
        bottom.append(" " * max(1, width - bottom.cell_len - len(when)))
        bottom.append(when, style=MUTED)
        lines.append(bottom)
        for line in lines:
            line.truncate(width, overflow="ellipsis")
        return Text("\n").join(lines)

    def on_click(self, event):
        offset = event.get_content_offset(self)
        if offset and offset.y == 0 and offset.x >= self.size.width - 4:
            self.app.focused_id = self.session["sessionId"]
            self.app.action_close_agent()
        elif offset and offset.y == 3:
            for start, end, url in self.links:
                if start <= offset.x < end:
                    self.app.open_url(url)
                    break


class SectionHeader(Static):
    pass


class CloseButton(Static):
    def on_click(self):
        self.app.action_close_agent()


class Preview(VerticalScroll):
    def compose(self):
        yield CloseButton("✕ Close agent", id="close-btn")
        yield Static(id="preview-body")

    def show(self, s):
        body = self.query_one("#preview-body", Static)
        btn = self.query_one("#close-btn")
        btn.display = bool(s)
        btn.update("✕ Close agent" if s and s["alive"] else "✕ Remove")
        if not s:
            body.update(Text("Nothing selected.", style=MUTED))
            return
        color = COLOR.get(s["status"], GRAY)
        t = Text()
        t.append(f" {NAME.get(s['status'], s['status'])} ", style=f"bold #0d1117 on {color}")
        t.append(f"   {ago(s['lastActivity'])}\n\n", style=MUTED)
        t.append(s["title"] + "\n", style=f"bold {INK}")
        meta = "   ".join(v for v in [s.get("name"), s.get("gitBranch")] if v)
        if meta:
            t.append(meta + "\n", style=MUTED)
        if s["tickets"]:
            t.append("\n")
            t.append_text(chips(s["tickets"]))
            t.append("\n")

        if s["status"] == "your_move":
            t.append("\nWhat you need to do\n", style=f"bold {AQUA}")
            for r in s["reasons"]:
                t.append(f"  {r[0].upper() + r[1:]}\n", style=INK)
            if s.get("pendingQuestion"):
                t.append(f"\n  {s['pendingQuestion']}\n", style=INK)

        if s["prs"]:
            t.append("\nPull requests\n", style=f"bold {INK}")
            for p in s["prs"]:
                t.append(f"  {p['repo']}#{p['number']}  ", style=f"bold {INK}")
                for text, col in pr_badges(p):
                    t.append(f" {text} ", style=f"#0d1117 on {col}")
                    t.append(" ")
                t.append(f"\n  {p['title']}\n", style=MUTED)

        text = s.get("summary")
        if text:
            t.append("\nLatest recap\n", style=f"bold {INK}")
            t.append(text.strip() + "\n", style=INK)
        if s.get("lastAssistant"):
            t.append("\nLast reply\n", style=f"bold {INK}")
            t.append(s["lastAssistant"].strip()[-700:] + "\n", style=MUTED)
        if s.get("cwd"):
            t.append(f"\n{s['cwd']}\n", style=MUTED)
        body.update(t)
        self.scroll_home(animate=False)


class ConfirmClose(ModalScreen):
    BINDINGS = [
        Binding("y,enter", "confirm", "Close"),
        Binding("n,escape", "cancel", "Cancel"),
    ]
    DEFAULT_CSS = f"""
    ConfirmClose {{ align: center middle; }}
    #dialog {{ width: 60; height: auto; padding: 1 2; background: #161b22; border: tall {RED}; }}
    """

    def __init__(self, title):
        super().__init__()
        self.agent_title = title

    def compose(self):
        t = Text()
        t.append("Close this agent?\n\n", style=f"bold {INK}")
        t.append(self.agent_title + "\n\n", style=MUTED)
        t.append("y", style=f"bold {RED}")
        t.append(" close   ", style=MUTED)
        t.append("n", style=f"bold {INK}")
        t.append(" cancel", style=MUTED)
        yield Static(t, id="dialog")

    def action_confirm(self):
        self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)


class Board(App):
    TITLE = "Agents"
    CSS = f"""
    Screen {{ background: #0d1117; }}
    #top {{ height: 3; padding: 1 2 0 2; }}
    #main {{ height: 1fr; }}
    #list {{ width: 3fr; padding: 0 1 0 2; scrollbar-size-vertical: 1; }}
    #preview {{ width: 2fr; min-width: 40; background: #161b22; padding: 1 2; border-left: tall #21262d; }}
    #close-btn {{ width: auto; padding: 0 2; margin: 0 0 1 0; color: {INK}; background: {RED} 35%; }}
    #close-btn:hover {{ background: {RED}; }}
    SectionHeader {{ margin: 1 0 0 0; height: 2; padding: 0 1; }}
    ItemGrid {{ grid-gutter: 1 2; height: auto; margin: 0 0 0 0; }}
    .tile {{ text-wrap: nowrap; height: 6; padding: 0 1; }}
    .tile.your_move {{ background: {AQUA} 10%; border: tall {AQUA} 35%; }}
    .tile.your_move:focus {{ background: {AQUA} 22%; border: tall {AQUA}; }}
    .tile.working {{ background: {RED} 10%; border: tall {RED} 35%; }}
    .tile.working:focus {{ background: {RED} 22%; border: tall {RED}; }}
    .tile.reviewing {{ background: {BLUE} 10%; border: tall {BLUE} 35%; }}
    .tile.reviewing:focus {{ background: {BLUE} 22%; border: tall {BLUE}; }}
    .tile.in_review {{ background: {GREEN} 10%; border: tall {GREEN} 35%; }}
    .tile.in_review:focus {{ background: {GREEN} 22%; border: tall {GREEN}; }}
    .tile.done {{ background: {GRAY} 10%; border: tall {GRAY} 35%; }}
    .tile.done:focus {{ background: {GRAY} 22%; border: tall {GRAY}; }}
    .tile.ended {{ background: {GRAY} 10%; border: tall {GRAY} 35%; }}
    .tile.ended:focus {{ background: {GRAY} 22%; border: tall {GRAY}; }}
    #empty {{ color: {MUTED}; padding: 1 1; }}
    Footer {{ background: #0d1117; }}
    """

    BINDINGS = [
        Binding("down,j,right,l", "move(1)", "Move", show=False),
        Binding("up,k,left,h", "move(-1)", "Move", show=False),
        Binding("enter", "resume", "Resume"),
        Binding("o", "open_session", "Open"),
        Binding("p", "open_pr", "PR"),
        Binding("t", "open_ticket", "Ticket"),
        Binding("x", "close_agent", "Close"),
        Binding("e", "toggle_inactive", "Inactive"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.state = None
        self.signature = None
        self.show_inactive = False
        self.focused_id = None
        self.resume_target = None

    def compose(self) -> ComposeResult:
        yield Static(id="top")
        with Horizontal(id="main"):
            yield VerticalScroll(id="list")
            yield Preview(id="preview")
        yield Footer()

    def on_mount(self):
        self.query_one("#top", Static).update(Text("Agents  loading…", style=f"bold {INK}"))
        self.load()
        self.set_interval(REFRESH_SECONDS, self.load)

    @work(thread=True, exclusive=True)
    def load(self):
        try:
            state = build_state()
            notify_new_commits(state)
        except Exception as e:
            self.call_from_thread(self.notify, str(e), severity="error")
            return
        self.call_from_thread(self.apply_state, state)

    def visible(self):
        sessions = (self.state or {}).get("sessions", [])
        return [s for s in sessions if s["status"] != "ended" or self.show_inactive]

    def render_top(self):
        sessions = self.visible()
        counts = {}
        for s in sessions:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        t = Text()
        t.append("Agents", style=f"bold {INK}")
        t.append("    ")
        for key, name, color in SECTIONS:
            if not counts.get(key):
                continue
            t.append("● ", style=color)
            t.append(f"{counts[key]} ", style=f"bold {INK}")
            t.append(f"{name.lower()}     ", style=MUTED)
        stamp = f"updated {datetime.now().strftime('%H:%M')}"
        width = self.size.width - 4
        t.append(" " * max(2, width - t.cell_len - len(stamp)))
        t.append(stamp, style=MUTED)
        self.query_one("#top", Static).update(t)

    def apply_state(self, state, force=False):
        sig = json.dumps([(s["sessionId"], s["status"], s["reasons"], s["title"], s["lastActivity"],
                           [(p["key"], p["state"], p["unresolvedThreads"], p["newComments"]) for p in s["prs"]])
                          for s in state["sessions"]] + [self.show_inactive])
        self.state = state
        self.render_top()
        if sig == self.signature and not force:
            return
        self.signature = sig
        focused = self.focused
        if focused is not None and hasattr(focused, "session"):
            self.focused_id = focused.session["sessionId"]

        lst = self.query_one("#list", VerticalScroll)
        lst.remove_children()
        widgets = []
        groups = {}
        for s in self.visible():
            groups.setdefault(s["status"], []).append(s)
        for key, name, color in SECTIONS:
            items = groups.get(key)
            if not items:
                continue
            header = Text()
            header.append(name, style=f"bold {color}")
            header.append(f"  {len(items)}", style=MUTED)
            widgets.append(SectionHeader(header))
            widgets.append(ItemGrid(*[AgentTile(s) for s in items], min_column_width=38))
        if not widgets:
            widgets.append(Static("No agents right now. Start one, and it shows up here.", id="empty"))
        lst.mount_all(widgets)
        self.call_after_refresh(self.restore_focus)

    def cards(self):
        return [w for w in self.query("AgentTile")]

    def restore_focus(self):
        cards = self.cards()
        if not cards:
            self.query_one(Preview).show(None)
            return
        target = next((c for c in cards if c.session["sessionId"] == self.focused_id), cards[0])
        target.focus()

    def on_descendant_focus(self, event):
        w = event.widget
        if hasattr(w, "session"):
            self.focused_id = w.session["sessionId"]
            self.query_one(Preview).show(w.session)
            w.scroll_visible()

    def selected(self):
        w = self.focused
        if w is not None and hasattr(w, "session"):
            return w.session
        sessions = (self.state or {}).get("sessions", [])
        return next((s for s in sessions if s["sessionId"] == self.focused_id), None)

    def action_move(self, step):
        cards = self.cards()
        if not cards:
            return
        try:
            i = cards.index(self.focused)
        except ValueError:
            i = -1
        cards[max(0, min(len(cards) - 1, i + step))].focus()

    def action_refresh(self):
        self.load()

    def action_toggle_inactive(self):
        self.show_inactive = not self.show_inactive
        if self.state:
            self.apply_state(self.state, force=True)

    def open_url(self, url):
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def action_open_session(self):
        s = self.selected()
        if s and s.get("remoteUrl"):
            self.open_url(s["remoteUrl"])
        elif s:
            self.notify("This session has no claude.ai link.")

    def action_open_pr(self):
        s = self.selected()
        if s and s["prs"]:
            self.open_url(s["prs"][0].get("sinceReviewUrl") or s["prs"][0]["url"])
        elif s:
            self.notify("This session has no PR.")

    def action_open_ticket(self):
        s = self.selected()
        if s and s["tickets"]:
            self.open_url(f"https://linear.app/pheedloop/issue/{s['tickets'][0]}")
        elif s:
            self.notify("This session has no ticket.")

    def action_close_agent(self):
        s = self.selected()
        if not s:
            return
        if not s["alive"]:
            self.dismiss_worker(s["sessionId"])
            return

        def done(confirmed):
            if confirmed:
                self.close_worker(s["sessionId"])

        self.push_screen(ConfirmClose(s["title"]), done)

    @work(thread=True)
    def close_worker(self, session_id):
        ok, message = close_session(session_id)
        self.call_from_thread(self.notify, message, severity="information" if ok else "error")
        self.call_from_thread(self.load)

    @work(thread=True)
    def dismiss_worker(self, session_id):
        ok, message = dismiss_session(session_id)
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")
        self.call_from_thread(self.load)

    def action_resume(self):
        s = self.selected()
        if not s:
            return
        if not s.get("resumeCmd"):
            self.action_open_pr()
            return
        if s["alive"]:
            self.notify(f"{s.get('name') or 'This agent'} is still running. Press o to open it.")
            return
        self.resume_target = s
        self.exit()


def main():
    app = Board()
    app.run()
    s = app.resume_target
    if s:
        if s.get("cwd") and os.path.isdir(s["cwd"]):
            os.chdir(s["cwd"])
        os.execvp("claude", ["claude", "--resume", s["sessionId"]])


if __name__ == "__main__":
    main()
