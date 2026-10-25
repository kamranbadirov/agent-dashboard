import json
import os
import subprocess
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, VerticalScroll
from textual.widgets import Footer, Static

from ..core.notify import notify_new_commits
from ..core.sessions import close_session
from ..core.state import build_state
from ..core.store import dismiss_session, rename_session
from .screens import ConfirmClose, RenameTitle
from .styles import APP_CSS
from .theme import INK, MUTED, SECTIONS
from .widgets.preview import Preview, SectionHeader
from .widgets.tile import AgentTile

REFRESH_SECONDS = 20


class Board(App):
    TITLE = "Agents"
    CSS = APP_CSS

    BINDINGS = [
        Binding("down,j,right,l", "move(1)", "Move", show=False),
        Binding("up,k,left,h", "move(-1)", "Move", show=False),
        Binding("enter", "resume", "Resume"),
        Binding("o", "open_session", "Open"),
        Binding("p", "open_pr", "PR"),
        Binding("t", "open_ticket", "Ticket"),
        Binding("n", "rename_agent", "Rename"),
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

    def action_rename_agent(self):
        s = self.selected()
        if not s:
            return

        def done(title):
            if title is not None:
                self.rename_worker(s["sessionId"], title)

        self.push_screen(RenameTitle(s["title"], bool(s.get("customTitle"))), done)

    @work(thread=True)
    def rename_worker(self, session_id, title):
        rename_session(session_id, title)
        self.call_from_thread(self.load)

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
