import json
import os
import subprocess
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import Footer, Static

from ..core import agents, jobs, plain, procs, ptyhost, rexpane
from ..core.group import group
from ..core.notify import notify_needs_you, notify_new_commits
from ..core.root import RootMissing, platform_of, root_dir
from ..core.sessions import close_all, done_and_live
from ..core.state import build_state
from ..core.store import dismiss_session, rename_session, stop_session
from .jobs_view import job_session, proc_session, with_agent_record
from .screens import ConfirmClose, RenameTitle
from .styles import APP_CSS
from .theme import INK, MUTED, SECTIONS
from .widgets.preview import Preview, SectionHeader
from .widgets.terminal import AgentTerminal, TerminalView
from .widgets.tile import AgentTile
from .widgets.topbar import WIZARD_HIT, TopBar
from .wizard.screen import WizardScreen

REFRESH_SECONDS = 20
NARROW_COLUMNS = 120
TILE_MIN, TILE_MAX = 38, 48
NEW_WORK_LABEL = " + New work  w "


class Board(App):
    TITLE = "Agents"
    CSS = APP_CSS

    BINDINGS = [
        Binding("down,j,right,l", "move(1)", "Move", show=False),
        Binding("up,k,left,h", "move(-1)", "Move", show=False),
        Binding("s", "start_ticket", "Start ticket"),
        Binding("w", "wizard", "New work"),
        Binding("n", "new_chat", "New chat"),
        Binding("c", "clean_platforms", "Clean up"),
        Binding("enter", "resume", "Open"),
        Binding("o", "open_session", "Open"),
        Binding("p", "open_pr", "PR"),
        Binding("t", "open_ticket", "Ticket"),
        Binding("R", "rename_agent", "Rename"),
        Binding("T", "terminal", "Terminal"),
        Binding("D", "dev_servers", "Dev servers"),
        Binding("x", "close_agent", "Close"),
        Binding("X", "close_done", "Close all done", show=False),
        Binding("e", "toggle_inactive", "Inactive"),
        Binding("a", "toggle_chats", "Chats"),
        Binding("r", "refresh", "Refresh"),
        Binding("u", "plain_refresh", "Plain words", show=False),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        *[Binding(str(n), f"pick({n - 1})", f"Session {n}", show=False) for n in range(1, 10)],
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.state = None
        self.signature = None
        self.show_inactive = False
        self.show_chats = False
        self.status_filter = None
        self.focused_id = None
        self.in_rex = rexpane.available()
        self.procs = []
        self.alert_id = None
        self.picks = {}

    def compose(self) -> ComposeResult:
        yield TopBar(id="top")
        with Horizontal(id="main"):
            yield VerticalScroll(id="list")
            with Vertical(id="side"):
                yield Preview(id="preview")
                yield AgentTerminal(id="terminal")
        yield Footer()

    def on_resize(self, event):
        """A narrow board, such as beside the agent pane in Rex, puts the details under the tiles, not beside them."""
        self.query_one("#main").set_class(event.size.width < NARROW_COLUMNS, "narrow")

    def on_mount(self):
        self.query_one("#main").set_class(self.size.width < NARROW_COLUMNS, "narrow")
        self.query_one("#top", TopBar).update(Text("Agents  loading…", style=f"bold {INK}"))
        self.query_one("#terminal").display = False
        self.load()
        self.set_interval(REFRESH_SECONDS, self.load)
        self.set_interval(1, self.refresh_jobs)
        self.set_interval(2, self.load_procs)
        self.load_procs()

    @work(thread=True, exclusive=True)
    def load(self):
        try:
            state = build_state()
            notify_new_commits(state)
            sent = notify_needs_you(state)
        except Exception as e:
            self.call_from_thread(self.notify, str(e), severity="error")
            return
        self.call_from_thread(self.apply_state, state)
        if sent:
            self.call_from_thread(setattr, self, "alert_id", sent[-1]["sessionId"])

    def on_app_focus(self, event):
        alert_id, self.alert_id = self.alert_id, None
        if alert_id and self.focus_session(alert_id):
            record = self.tmux_record(self.target())
            if record:
                self.open_agent(record["sessionId"])

    @work(thread=True, exclusive=True, group="procs")
    def load_procs(self):
        found = procs.listed()
        self.call_from_thread(self.apply_procs, found)

    def apply_procs(self, found):
        if found != self.procs:
            self.procs = found
            if self.state:
                self.apply_state(self.state)

    def with_record(self, session):
        record = agents.record_for(session["sessionId"])
        return with_agent_record(session, record) if record else session

    def listed(self):
        started = [self.with_record(s) for s in (self.state or {}).get("sessions", []) if s.get("work", True) or self.show_chats]
        sessions = [job_session(j) for j in jobs.listed()] + [proc_session(p) for p in self.procs if not procs.is_terminal(p["key"])] + started
        return [s for s in group(sessions) if s.get("alive") or s["status"] not in ("ended", "done") or self.show_inactive]

    def visible(self):
        return [s for s in self.listed() if self.status_filter in (None, s["status"])]

    def toggle_filter(self, key):
        self.status_filter = None if key in (None, self.status_filter) else key
        if self.state:
            self.apply_state(self.state, force=True)

    def action_clear_filter(self):
        if self.screen.query("HelpPanel"):
            self.action_hide_help_panel()
            return
        self.toggle_filter(None)

    def get_system_commands(self, screen):
        for command in super().get_system_commands(screen):
            if command.title not in ("Maximize", "Minimize"):
                yield command

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
                         + [(p["key"], p["dead"], p["exitCode"]) for p in self.procs]
                         + [self.show_inactive, self.show_chats, self.status_filter])
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
            widgets.append(ItemGrid(*[AgentTile(s) for s in items], min_column_width=TILE_MIN, max_column_width=TILE_MAX))
        if not widgets:
            widgets.append(Static("No agents right now. Start one, and it shows up here.", id="empty"))
        lst.mount_all(widgets)
        self.call_after_refresh(self.restore_focus)

    def cards(self):
        return [w for w in self.query("AgentTile")]

    def leave_terminal(self):
        self.focus_agent()

    def picked(self, session):
        if not session or not session.get("group"):
            return session
        index = self.picks.get(session["sessionId"])
        return session["group"][index] if index is not None and index < len(session["group"]) else session["lead"]

    def target(self):
        return self.picked(self.selected())

    def focus_session(self, session_id):
        for card in self.cards():
            members = [s["sessionId"] for s in card.session.get("group") or []]
            if card.session["sessionId"] == session_id or session_id in members:
                if session_id in members:
                    self.picks[card.session["sessionId"]] = members.index(session_id)
                self.focused_id = card.session["sessionId"]
                card.focus()
                self.show_side(card.session)
                return True
        return False

    def action_pick(self, index):
        s = self.selected()
        if not s or not s.get("group") or index >= len(s["group"]):
            return
        self.picks[s["sessionId"]] = index
        self.show_side(s)
        self.action_resume()

    def actions_for(self, session):
        target = self.picked(session)
        out = []
        if target and (self.tmux_record(target) or target.get("resumeCmd")):
            out.append(("⏎", "Open", "resume"))
        if session["prs"]:
            out.append(("p", "PR", "open_pr"))
        if session["tickets"]:
            out.append(("t", "Ticket", "open_ticket"))
        if self.platform_dir(target):
            out.append(("D", "Servers", "dev_servers"))
        if target and not (target.get("job") or target.get("proc") or target["sessionId"].startswith("pr:")):
            out.append(("R", "Rename", "rename_agent"))
        if target:
            out.append(("x", "Stop" if target.get("alive") else "Dismiss", "close_agent"))
        return out

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

    def tmux_record(self, session):
        if not session:
            return None
        if session.get("proc"):
            return {"sessionId": session["proc"]["key"], "title": session["title"], "where": "background"}
        return agents.board_agent(session["sessionId"])

    def main_ticket(self, tile):
        return tile["tickets"][0] if tile and tile.get("tickets") else None

    def ensure_plain(self, tile, force=False):
        ticket = self.main_ticket(tile)
        if ticket and (force or plain.is_due(ticket)):
            self.plain_worker(ticket, force)

    @work(thread=True, group="plain")
    def plain_worker(self, ticket, force):
        plain.refresh(ticket, force)
        self.call_from_thread(self.redraw_preview, ticket)

    def redraw_preview(self, ticket):
        tile = self.selected()
        preview = self.query_one(Preview)
        if preview.display and self.main_ticket(tile) == ticket:
            preview.show(tile, self.picked(tile), self.actions_for(tile))

    def action_plain_refresh(self):
        tile = self.selected()
        if not self.main_ticket(tile):
            self.notify("This tile has no ticket.")
            return
        self.ensure_plain(tile, force=True)
        self.notify(f"Reading {self.main_ticket(tile)} again.")

    def show_side(self, session):
        tile, session = session, self.picked(session)
        self.ensure_plain(tile)
        record = self.tmux_record(session)
        if self.in_rex and record:
            self.show_in_pane(record["sessionId"], focus=False, open_new=False)
        in_panel = bool(record) and not self.in_rex
        self.query_one("#terminal").display = in_panel
        self.query_one("#preview").display = not in_panel
        if in_panel:
            self.query_one(AgentTerminal).show(record, session)
        else:
            self.query_one(Preview).show(tile, session, self.actions_for(tile) if tile else [])

    @work(thread=True, exclusive=True, group="rexpane")
    def show_in_pane(self, key, focus, open_new, name=rexpane.AGENT):
        if not ptyhost.alive(key):
            if not open_new:
                return
            ok, message = agents.resume_agent(key)
            if not ok:
                self.call_from_thread(self.notify, message, severity="error")
                return
        ok, message = rexpane.show(key, focus=focus, open_new=open_new, name=name)
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")

    def terminal_dir(self):
        """The folder for T: the selected session's folder, else the root checkout."""
        target = self.target()
        record = self.tmux_record(target) if target else None
        cwd = (target or {}).get("cwd") or (record or {}).get("cwd")
        if not cwd and target and target.get("job"):
            cwd = target["job"].meta.get("platform")
        if cwd and os.path.isdir(cwd):
            return cwd
        try:
            return str(root_dir())
        except RootMissing:
            return os.path.expanduser("~")

    def platform_dir(self, target):
        record = self.tmux_record(target) if target else None
        if target and target.get("job"):
            return target["job"].meta.get("platform")
        found = platform_of((target or {}).get("cwd") or (record or {}).get("cwd"))
        return str(found) if found else None

    def action_dev_servers(self):
        platform = self.platform_dir(self.target())
        if not platform:
            self.notify("This tile has no platform, so there are no dev servers to start.")
            return
        self.dev_servers_worker(platform)

    @work(thread=True, group="terminal")
    def dev_servers_worker(self, platform):
        ok, message, key = procs.start_dev_servers(platform)
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")
            return
        self.call_from_thread(self.load_procs)
        if self.in_rex:
            self.show_in_pane(key, focus=True, open_new=True, name=rexpane.TERM)
        else:
            self.call_from_thread(self.notify, f"Dev servers: {message} Select their tile to see them.")

    def action_terminal(self):
        self.terminal_worker(self.terminal_dir())

    @work(thread=True, group="terminal")
    def terminal_worker(self, cwd):
        ok, message, key = procs.start_terminal(cwd)
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")
            return
        if self.in_rex:
            self.show_in_pane(key, focus=True, open_new=True, name=rexpane.TERM)
        else:
            self.call_from_thread(self.attach_full, key)

    def attach_full(self, key):
        with self.suspend():
            ptyhost.attach(key)

    def open_agent(self, session_id):
        if self.in_rex:
            self.show_in_pane(session_id, focus=True, open_new=True)
        else:
            self.query_one(AgentTerminal).focus_terminal()

    def tile_clicked(self, session):
        record = self.tmux_record(self.picked(session))
        if record:
            self.open_agent(record["sessionId"])

    def selected(self):
        w = self.focused
        if w is not None and hasattr(w, "session"):
            return w.session
        return next((s for s in self.listed() if s["sessionId"] == self.focused_id), None)

    def action_quit(self):
        if self.in_rex:
            rexpane.close_pane()
        self.exit()

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

    def action_toggle_chats(self):
        self.show_chats = not self.show_chats
        self.notify("Showing chats with no ticket or PR." if self.show_chats else "Hiding chats with no ticket or PR.")
        if self.state:
            self.apply_state(self.state, force=True)

    def open_url(self, url):
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def action_open_session(self):
        s = self.target()
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
        job, action, key = (tuple(result) + (None,))[:3] if isinstance(result, tuple) else (result, None, None)
        if action == "open_proc" and key:
            self.load_procs()
            self.set_timer(0.5, lambda: self.focus_session(f"proc:{key}"))
            self.open_agent(key)
        if job and job.state == "running":
            self.notify(f"Setting up {job.label}. Its tile shows the progress.")
        if action == "open_agent" and job.agent:
            found = self.focus_session(job.agent["sessionId"])
            self.notify("Agent opened." if found else "The agent's tile appears as soon as it has started.")
        self.refresh_jobs()

    def action_wizard(self):
        self.push_screen(WizardScreen(), self.wizard_closed)

    def action_start_ticket(self):
        self.push_screen(WizardScreen(start="ticket"), self.wizard_closed)

    def action_new_chat(self):
        self.new_chat_worker()

    @work(thread=True, group="new_chat")
    def new_chat_worker(self):
        ok, message, record = agents.start_chat()
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")
            return
        self.call_from_thread(self.chat_started, record["sessionId"])

    def chat_started(self, session_id):
        self.focused_id = session_id
        self.load()
        if self.in_rex:
            self.open_agent(session_id)
        else:
            self.notify("Chat started. Its tile appears in a moment. Press Enter on it to type.")

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
        s = self.target()
        if not s:
            return
        if s.get("proc"):
            if s["proc"]["dead"]:
                procs.stop(s["proc"]["key"])
                self.load_procs()
                return

            def stop(confirmed):
                if confirmed:
                    ok, message = procs.stop(s["proc"]["key"])
                    self.notify(message, severity="information" if ok else "warning")
                    self.load_procs()

            self.push_screen(ConfirmClose(s["title"], "Stop this program?", "stop"), stop)
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

        self.push_screen(ConfirmClose(s["title"], "Stop this agent? You can resume it later.", "stop"), done)

    def action_close_done(self):
        found = done_and_live((self.state or {}).get("sessions", []))
        if not found:
            self.notify("No done session is running.")
            return
        names = ", ".join(s["title"][:30] for s in found[:3]) + (f" and {len(found) - 3} more" if len(found) > 3 else "")

        def done(confirmed):
            if confirmed:
                self.close_all_worker([s["sessionId"] for s in found])

        self.push_screen(ConfirmClose(names, f"Stop {len(found)} done session{'s' if len(found) > 1 else ''}? "
                                      "You can resume each one later.", "stop"), done)

    @work(thread=True)
    def close_all_worker(self, session_ids):
        closed, failed = close_all(session_ids)
        message = f"Stopped {closed}." + (f" {failed} could not be stopped." if failed else "")
        self.call_from_thread(self.notify, message, severity="warning" if failed else "information")
        self.call_from_thread(self.load)

    def action_rename_agent(self):
        s = self.target()
        if not s or s.get("job") or s.get("proc"):
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
        ok, message = stop_session(session_id)
        self.call_from_thread(self.notify, message, severity="information" if ok else "error")
        self.call_from_thread(self.load)

    @work(thread=True)
    def dismiss_worker(self, session_id):
        ok, message = dismiss_session(session_id)
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")
        self.call_from_thread(self.load)

    def action_resume(self):
        s = self.target()
        if not s:
            return
        record = self.tmux_record(s)
        if record:
            self.open_agent(record["sessionId"])
            return
        if not s.get("resumeCmd"):
            self.action_open_pr()
            return
        if s["alive"]:
            def move(confirmed):
                if confirmed:
                    self.move_worker(s)

            self.push_screen(ConfirmClose(s["title"], f"Move this session into the board? It stops in "
                                          f"{s.get('name') or 'its terminal'} and resumes here, with its whole conversation.",
                                          "move"), move)
            return
        ok, message = agents.adopt_agent(s["sessionId"], s.get("cwd"), s["title"])
        if not ok:
            self.notify(message, severity="error")
            return
        self.show_side(s)
        self.open_agent(s["sessionId"])


    @work(thread=True)
    def move_worker(self, s):
        ok, message = agents.move_into_board(s["sessionId"], s.get("cwd"), s["title"])
        if not ok:
            self.call_from_thread(self.notify, message, severity="error")
            return
        self.call_from_thread(self.notify, "Moved into the board.")
        self.call_from_thread(self.load)
        self.call_from_thread(self.open_agent, s["sessionId"])


def main():
    app = Board()
    app.run()


if __name__ == "__main__":
    main()
