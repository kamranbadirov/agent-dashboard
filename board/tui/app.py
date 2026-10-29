import json
import subprocess
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import Footer, Static

from ..core import agents, jobs
from ..core.notify import notify_needs_you, notify_new_commits
from ..core.sessions import close_session
from ..core.state import build_state
from ..core.store import dismiss_session, rename_session
from .jobs_view import job_session, with_agent_record
from .screens import ConfirmClose, RenameTitle
from .styles import APP_CSS
from .theme import INK, MUTED, SECTIONS
from .widgets.preview import Preview, SectionHeader
from .widgets.terminal import AgentTerminal, TerminalView
from .widgets.tile import AgentTile
from .widgets.topbar import WIZARD_HIT, TopBar
from .wizard.screen import WizardScreen

REFRESH_SECONDS = 20
NEW_WORK_LABEL = " + New work  w "


class Board(App):
    TITLE = "Agents"
    CSS = APP_CSS

    BINDINGS = [
        Binding("down,j,right,l", "move(1)", "Move", show=False),
        Binding("up,k,left,h", "move(-1)", "Move", show=False),
        Binding("s", "start_ticket", "Start ticket"),
        Binding("w", "wizard", "New work"),
        Binding("c", "clean_platforms", "Clean up"),
        Binding("enter", "resume", "Resume"),
        Binding("o", "open_session", "Open"),
        Binding("p", "open_pr", "PR"),
        Binding("t", "open_ticket", "Ticket"),
        Binding("n", "rename_agent", "Rename"),
        Binding("x", "close_agent", "Close"),
        Binding("e", "toggle_inactive", "Inactive"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.state = None
        self.signature = None
        self.show_inactive = False
        self.status_filter = None
        self.focused_id = None

    def compose(self) -> ComposeResult:
        yield TopBar(id="top")
        with Horizontal(id="main"):
            yield VerticalScroll(id="list")
            with Vertical(id="side"):
                yield Preview(id="preview")
                yield AgentTerminal(id="terminal")
        yield Footer()

    def on_mount(self):
        self.query_one("#top", TopBar).update(Text("Agents  loading…", style=f"bold {INK}"))
        self.query_one("#terminal").display = False
        self.load()
        self.set_interval(REFRESH_SECONDS, self.load)
        self.set_interval(1, self.refresh_jobs)

    @work(thread=True, exclusive=True)
    def load(self):
        try:
            state = build_state()
            notify_new_commits(state)
            notify_needs_you(state)
        except Exception as e:
            self.call_from_thread(self.notify, str(e), severity="error")
            return
        self.call_from_thread(self.apply_state, state)

    def with_record(self, session):
        record = agents.record_for(session["sessionId"])
        return with_agent_record(session, record) if record else session

    def listed(self):
        started = [self.with_record(s) for s in (self.state or {}).get("sessions", [])]
        sessions = [job_session(j) for j in jobs.listed()] + started
        return [s for s in sessions if s["status"] not in ("ended", "done") or self.show_inactive]

    def visible(self):
        return [s for s in self.listed() if self.status_filter in (None, s["status"])]

    def toggle_filter(self, key):
        self.status_filter = None if key in (None, self.status_filter) else key
        if self.state:
            self.apply_state(self.state, force=True)

    def action_clear_filter(self):
        self.toggle_filter(None)

    def render_top(self):
        counts = {}
        for s in self.listed():
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        if self.status_filter and not counts.get(self.status_filter):
            self.status_filter = None
        active = self.status_filter
        t = Text()
        hits = []
        start = t.cell_len
        t.append("Agents", style=f"bold {INK}")
        hits.append((start, t.cell_len, None))
        t.append("    ")
        for key, name, color in SECTIONS:
            if not counts.get(key):
                continue
            dim = active and key != active
            start = t.cell_len
            t.append("● ", style=MUTED if dim else color)
            t.append(f"{counts[key]} ", style=f"bold {MUTED if dim else INK}")
            t.append(name.lower(), style=f"underline {color}" if key == active else MUTED)
            hits.append((start, t.cell_len, key))
            t.append("     ")
        stamp = f"updated {datetime.now().strftime('%H:%M')}"
        width = self.size.width - 4
        t.append(" " * max(2, width - t.cell_len - len(stamp) - len(NEW_WORK_LABEL) - 4))
        start = t.cell_len
        t.append(NEW_WORK_LABEL, style=f"bold #0d1117 on {INK}")
        hits.append((start, t.cell_len, WIZARD_HIT))
        t.append("    ")
        t.append(stamp, style=MUTED)
        top = self.query_one("#top", TopBar)
        top.hits = hits
        top.update(t)

    def apply_state(self, state, force=False):
        sig = json.dumps([(s["sessionId"], s["status"], s["reasons"], s["title"], s["lastActivity"],
                           [(p["key"], p["state"], p["unresolvedThreads"], p["newComments"]) for p in s["prs"]])
                          for s in state["sessions"]]
                         + [(j.id, j.state, j.current_step) for j in jobs.listed()]
                         + [self.show_inactive, self.status_filter])
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

    def leave_terminal(self):
        card = next((c for c in self.cards() if c.session["sessionId"] == self.focused_id), None)
        if card:
            card.focus()

    def restore_focus(self):
        if isinstance(self.focused, TerminalView):
            return
        cards = self.cards()
        if not cards:
            self.show_side(None)
            return
        target = next((c for c in cards if c.session["sessionId"] == self.focused_id), cards[0])
        target.focus()

    def on_descendant_focus(self, event):
        w = event.widget
        if hasattr(w, "session"):
            self.focused_id = w.session["sessionId"]
            self.show_side(w.session)
            w.scroll_visible()

    def show_side(self, session):
        record = session and agents.board_agent(session["sessionId"])
        self.query_one("#terminal").display = bool(record)
        self.query_one("#preview").display = not record
        if record:
            self.query_one(AgentTerminal).show(record, session)
        else:
            self.query_one(Preview).show(session)

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

    def wizard_closed(self, result):
        job, action = result if isinstance(result, tuple) else (result, None)
        if job and job.state == "running":
            self.notify(f"Setting up {job.label}. Its tile shows the progress.")
        if action == "open_agent" and job.agent:
            self.focused_id = job.agent["sessionId"]
            self.notify("The agent's tile appears as soon as it has started." if not self.focus_agent() else "Agent opened.")
        self.refresh_jobs()

    def action_wizard(self):
        self.push_screen(WizardScreen(), self.wizard_closed)

    def action_start_ticket(self):
        self.push_screen(WizardScreen(start="ticket"), self.wizard_closed)

    def action_clean_platforms(self):
        self.push_screen(WizardScreen(start="clean"), lambda result: self.refresh_jobs())

    def focus_agent(self):
        card = next((c for c in self.cards() if c.session["sessionId"] == self.focused_id), None)
        if card:
            card.focus()
        return bool(card)

    def refresh_jobs(self):
        for job in jobs.finished_unreported():
            if job.state == "done":
                self.notify(job.notice or f"{job.label} is ready.", severity="warning" if job.notice else "information")
            else:
                self.notify(f"{job.label} failed. Select its tile for the output.", severity="error")
        if self.state:
            self.apply_state(self.state)

    def action_close_agent(self):
        s = self.selected()
        if not s:
            return
        if s["sessionId"].startswith("job:"):
            ok, message = jobs.dismiss(s["sessionId"][len("job:"):])
            self.notify(message, severity="information" if ok else "warning")
            self.refresh_jobs()
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
        if not s or s.get("job"):
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
        if agents.board_agent(s["sessionId"]):
            self.query_one(AgentTerminal).focus_terminal()
            return
        if not s.get("resumeCmd"):
            self.action_open_pr()
            return
        if s["alive"]:
            self.notify(f"{s.get('name') or 'This agent'} is still running. Press o to open it.")
            return
        if not agents.adopt_agent(s["sessionId"], s.get("cwd"), s["title"]):
            self.notify("This session's folder no longer exists, so it cannot resume.", severity="error")
            return
        self.show_side(s)
        self.query_one(AgentTerminal).focus_terminal()


def main():
    app = Board()
    app.run()


if __name__ == "__main__":
    main()
