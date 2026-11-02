from rich.text import Text
from textual import work
from textual.containers import Vertical
from textual.widgets import Static

from ...core import agents, ptyhost
from ..jobs_view import PLACES
from ..theme import GRAY, INK, MUTED

POLL_SECONDS = 0.25
LEAVE_KEY = "ctrl+right_square_bracket"
ENDED = "This agent has ended. Press a key to resume it."


class TerminalView(Static, can_focus=True):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.key = None
        self.screen_text = None
        self.running = False

    def on_mount(self):
        self.set_interval(POLL_SECONDS, self.poll)

    def show(self, session_id):
        if session_id != self.key:
            self.key = session_id
            self.screen_text = None
        if not ptyhost.available():
            self.update(Text(ptyhost.MISSING, style=MUTED))
            return
        self.poll()

    def poll(self):
        if self.key and self.parent.display and self.size.height > 0 and ptyhost.available():
            self.capture(self.key, self.size.height, self.size.width)

    @work(thread=True, exclusive=True, group="capture")
    def capture(self, key, rows, cols):
        screen = ptyhost.capture(key, rows, cols)
        self.app.call_from_thread(self.draw, key, screen)

    def draw(self, key, screen):
        if key != self.key:
            return
        was_running, self.running = self.running, screen is not None
        if was_running != self.running:
            self.parent.update_header()
        if screen == self.screen_text and self.screen_text is not None:
            return
        self.screen_text = screen
        self.update(Text.from_ansi(screen, no_wrap=True, overflow="crop") if screen is not None else Text(ENDED, style=MUTED))

    def on_resize(self, event):
        if event.size.height > 0 and event.size.width > 0:
            ptyhost.set_size(event.size.height, event.size.width)
        self.poll()

    def check_consume_key(self, key, character):
        return key == "enter" or bool(character and character.isprintable())

    def on_key(self, event):
        if event.key == LEAVE_KEY:
            event.stop()
            self.app.leave_terminal()
            return
        if event.key != "enter" and not event.is_printable:
            return
        event.stop()
        event.prevent_default()
        self.open(event.character if event.is_printable else None)

    def open(self, text=None):
        if not ptyhost.available():
            self.app.notify(ptyhost.MISSING, severity="error")
            return
        if not ptyhost.alive(self.key):
            ok, message = agents.resume_agent(self.key)
            if not ok:
                self.app.notify(message, severity="error")
                return
        elif text:
            ptyhost.send_text(self.key, text)
        with self.app.suspend():
            ptyhost.attach(self.key)
        self.screen_text = None
        self.poll()
        self.parent.update_header()


class AgentTerminal(Vertical):
    """The right-hand panel for an agent the board started: what it is, above its terminal."""

    def compose(self):
        yield Static(id="terminal-header")
        yield TerminalView(id="terminal-view")

    def on_mount(self):
        self.record = None
        self.session = None
        self.set_interval(1, self.update_header)

    @property
    def view(self):
        return self.query_one(TerminalView)

    def show(self, record, session=None):
        self.record = record
        self.session = session
        self.view.show(record["sessionId"])
        self.update_header()

    def update_header(self):
        if not self.record:
            return
        record, session = self.record, self.session or {}
        running = self.view.running
        hint = "enter attach · ctrl+] leave" if running else "press a key to resume"
        width = max(20, self.size.width - 4)
        title = Text(no_wrap=True)
        title.append("● " if running else "○ ", style=INK if running else GRAY)
        title.append(session.get("title") or record["title"], style=f"bold {INK}")
        title.truncate(width - len(hint) - 2, overflow="ellipsis")
        title.append(" " * max(2, width - title.cell_len - len(hint)))
        title.append(hint, style=MUTED)
        shown = session.get("title") or record["title"]
        details = [record.get("branch") if record.get("branch") != shown else "", ", ".join(session.get("tickets") or []), PLACES.get(record["where"]),
                   ", ".join(sorted({p["repo"] for p in session.get("prs") or []}))]
        meta = Text("  ·  ".join(d for d in details if d), style=MUTED, no_wrap=True, overflow="ellipsis")
        self.query_one("#terminal-header", Static).update(Text("\n").join([title, meta]))

    def focus_terminal(self):
        self.update_header()
        self.view.focus()
