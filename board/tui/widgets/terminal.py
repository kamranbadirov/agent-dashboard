import pyte
from rich.style import Style
from rich.text import Text
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from ...core import agents, ptyhost
from ..jobs_view import PLACES
from ..theme import GRAY, INK, MUTED

REFRESH_SECONDS = 0.04
LEAVE_KEY = "ctrl+right_square_bracket"
MOVEMENT = {
    "enter": b"\r", "escape": b"\x1b", "tab": b"\t", "shift+tab": b"\x1b[Z", "backspace": b"\x7f",
    "delete": b"\x1b[3~", "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
}


def to_bytes(event):
    if event.key in MOVEMENT:
        return MOVEMENT[event.key]
    if event.key.startswith("ctrl+") and len(event.key) == 6 and event.key[-1].isalpha():
        return bytes([ord(event.key[-1]) - 96])
    if event.key.startswith("alt+") and event.character:
        return b"\x1b" + event.character.encode()
    return event.character.encode() if event.character else b""


ANSI_NAMES = {"black", "red", "green", "blue", "magenta", "cyan", "white"}
HEX_DIGITS = set("0123456789abcdefABCDEF")


def rich_color(name):
    """pyte names the 16 basic colours and gives every other colour as six hex digits."""
    if name == "brown":
        return "yellow"
    base = name[len("bright"):] if name.startswith("bright") else name
    if base in ANSI_NAMES:
        return ("bright_" if base != name else "") + base
    if len(name) == 6 and set(name) <= HEX_DIGITS:
        return "#" + name
    return None


def cell_style(char, is_cursor):
    return Style(
        color=rich_color(char.fg), bgcolor=rich_color(char.bg), bold=char.bold, italic=char.italics,
        underline=char.underscore, strike=char.strikethrough, reverse=char.reverse != is_cursor,
    )


class TerminalView(Widget, can_focus=True):
    """Draws a program running in a pseudo-terminal and sends it the keys typed here. When the
    program is not running, as after a board restart, the saved output is shown and the first
    key resumes it."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.key = None
        self.pty = None
        self.seen = 0
        self.dirty = False
        self.emulator = pyte.Screen(100, 30)
        self.stream = pyte.ByteStream(self.emulator)

    def on_mount(self):
        self.set_interval(REFRESH_SECONDS, self.poll)

    def show(self, session_id):
        self.key = session_id
        self.pty = ptyhost.get(session_id)
        self.emulator.reset()
        self.seen = 0
        if self.pty:
            self.pty.resize(self.emulator.lines, self.emulator.columns)
        else:
            self.stream.feed(ptyhost.history(session_id))
        self.dirty = True

    @property
    def running(self):
        return bool(self.pty and self.pty.alive)

    def poll(self):
        if self.pty:
            data, self.seen = self.pty.buffer.read_since(self.seen)
            if data:
                self.stream.feed(data)
                self.dirty = True
        if self.dirty:
            self.dirty = False
            self.refresh()

    def on_resize(self, event):
        rows, cols = max(2, event.size.height), max(10, event.size.width)
        self.emulator.resize(rows, cols)
        if self.pty:
            self.pty.resize(rows, cols)
        self.dirty = True

    def check_consume_key(self, key, character):
        return True

    def on_key(self, event):
        event.stop()
        event.prevent_default()
        if event.key == LEAVE_KEY:
            self.app.leave_terminal()
            return
        if not self.running:
            self.resume()
            return
        self.pty.write(to_bytes(event))

    def on_paste(self, event):
        if self.running:
            self.pty.write(event.text.encode())

    def resume(self):
        self.pty = agents.resume_agent(self.key)
        self.seen = 0
        if self.pty:
            self.emulator.reset()
            self.pty.resize(self.emulator.lines, self.emulator.columns)
            self.dirty = True
        self.parent.update_header()

    def render(self):
        screen = self.emulator
        cursor_at = (screen.cursor.y, screen.cursor.x) if self.has_focus and not screen.cursor.hidden else None
        lines = []
        for y in range(screen.lines):
            line = Text(no_wrap=True, overflow="crop")
            for x in range(screen.columns):
                char = screen.buffer[y][x]
                line.append(char.data or " ", style=cell_style(char, cursor_at == (y, x)))
            lines.append(line)
        return Text("\n").join(lines)


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
        hint = "ctrl+] leave" if running else "press a key to resume"
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
