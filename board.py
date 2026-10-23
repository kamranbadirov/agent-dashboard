import json
import os
import subprocess
from datetime import datetime, timezone

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, VerticalScroll
from textual.widget import Widget
from textual.widgets import Footer, Static

from server import build_state

REFRESH_SECONDS = 20

AQUA = "#2dd4bf"
RED = "#f0525a"
BLUE = "#5b8def"
GREEN = "#3fb950"
GRAY = "#8b949e"
INK = "#e6edf3"
MUTED = "#8b949e"

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


class ActionTile(Widget, can_focus=True):
    def __init__(self, session):
        super().__init__(classes="tile")
        self.session = session

    def render(self):
        s = self.session
        width = max(10, self.size.width - 2)
        lines = [
            Text(headline(s), style=f"bold {AQUA}"),
            Text(s["title"], style=f"bold {INK}"),
            Text(s.get("pendingQuestion") or "", style=MUTED),
        ]
        when = ago(s["lastActivity"])
        bottom = chips(s["tickets"][:2])
        bottom.append(" " * max(1, width - bottom.cell_len - len(when)))
        bottom.append(when, style=MUTED)
        lines.append(bottom)
        for line in lines:
            line.truncate(width, overflow="ellipsis")
        return Text("\n").join(lines)


class AgentRow(Widget, can_focus=True):
    def __init__(self, session):
        super().__init__(classes=f"row {session['status']}")
        self.session = session

    def render(self):
        s = self.session
        width = self.size.width - 2
        color = COLOR.get(s["status"], GRAY)
        right = Text()
        tickets = chips(s["tickets"][:2])
        tickets.truncate(24, overflow="ellipsis")
        right.append_text(tickets)
        right.append(" " * (25 - tickets.cell_len))
        refs = " ".join(f"#{p['number']}" for p in s["prs"][:2])
        right.append(f"{refs:<12}", style=color)
        right.append(f"{ago(s['lastActivity']):>9}", style=MUTED)
        room = max(8, width - right.cell_len - 3)
        title = s["title"] if len(s["title"]) <= room else s["title"][: room - 1] + "…"
        t = Text()
        t.append("● ", style=color)
        t.append(title, style=INK if s["status"] not in ("done", "ended") else MUTED)
        t.append(" " * max(1, width - 2 - len(title) - right.cell_len))
        t.append_text(right)
        return t


class SectionHeader(Static):
    pass


class Preview(VerticalScroll):
    def compose(self):
        yield Static(id="preview-body")

    def show(self, s):
        body = self.query_one("#preview-body", Static)
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


class Board(App):
    TITLE = "Agents"
    CSS = f"""
    Screen {{ background: #0d1117; }}
    #top {{ height: 3; padding: 1 2 0 2; }}
    #main {{ height: 1fr; }}
    #list {{ width: 3fr; padding: 0 1 0 2; scrollbar-size-vertical: 1; }}
    #preview {{ width: 2fr; min-width: 40; background: #161b22; padding: 1 2; border-left: tall #21262d; }}
    SectionHeader {{ margin: 1 0 0 0; height: 2; padding: 0 1; }}
    ItemGrid {{ grid-gutter: 1 2; height: auto; margin: 0 0 0 0; }}
    .tile {{
        text-wrap: nowrap;
        height: 6; padding: 0 1;
        background: {AQUA} 10%;
        border: tall {AQUA} 35%;
    }}
    .tile:focus {{ background: {AQUA} 22%; border: tall {AQUA}; }}
    .row {{ text-wrap: nowrap; height: 1; padding: 0 1; margin: 0 0 0 0; }}
    .row:hover {{ background: #161b22; }}
    .row.working:focus {{ background: {RED} 22%; }}
    .row.reviewing:focus {{ background: {BLUE} 22%; }}
    .row.in_review:focus {{ background: {GREEN} 22%; }}
    .row.done:focus, .row.ended:focus, .row.your_move:focus {{ background: #30363d; }}
    #empty {{ color: {MUTED}; padding: 1 1; }}
    Footer {{ background: #0d1117; }}
    """

    BINDINGS = [
        Binding("down,j,right,l", "move(1)", "Move", show=False),
        Binding("up,k,left,h", "move(-1)", "Move", show=False),
        Binding("enter", "resume", "Resume"),
        Binding("o", "open_session", "Open on claude.ai"),
        Binding("p", "open_pr", "Open PR"),
        Binding("t", "open_ticket", "Open ticket"),
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
            if key == "your_move":
                widgets.append(ItemGrid(*[ActionTile(s) for s in items], min_column_width=38))
            else:
                widgets.extend(AgentRow(s) for s in items)
        if not widgets:
            widgets.append(Static("No agents right now. Start one, and it shows up here.", id="empty"))
        lst.mount_all(widgets)
        self.call_after_refresh(self.restore_focus)

    def cards(self):
        return [w for w in self.query("ActionTile, AgentRow")]

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
        return w.session if w is not None and hasattr(w, "session") else None

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
            self.open_url(s["prs"][0]["url"])
        elif s:
            self.notify("This session has no PR.")

    def action_open_ticket(self):
        s = self.selected()
        if s and s["tickets"]:
            self.open_url(f"https://linear.app/pheedloop/issue/{s['tickets'][0]}")
        elif s:
            self.notify("This session has no ticket.")

    def action_resume(self):
        s = self.selected()
        if not s:
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
