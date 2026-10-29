from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static

from ...core.wizard.commands import describe
from ..theme import AQUA, GREEN, INK, LINE, MUTED, RED
from .inputs import Changed
from .parts import Btn, Callout, key_values

SPINNER = "◐◓◑◒"
LOG_LINES = 8
PLACES = {"background": "in the board", "cmux": "in cmux", "terminal": "in a terminal"}


class RecapRow(Horizontal):
    def __init__(self, key, value, edit_id, badge=""):
        super().__init__()
        self.parts = (key, value, edit_id, badge)

    def compose(self):
        key, value, edit_id, badge = self.parts
        yield Static(Text(key, no_wrap=True, overflow="ellipsis"), classes="key")
        text = Text(value, style=INK, no_wrap=True, overflow="ellipsis")
        if badge:
            text.append(f"  {badge}", style=f"bold {RED}")
        yield Static(text, classes="value")
        if edit_id:
            yield Btn("Edit", f"edit:{edit_id}", "ghost link")


class SummaryView(Vertical):
    """What was chosen, with an Edit link for each answer, the checks, and the command."""

    def __init__(self, rows, command, typed_word):
        super().__init__()
        self.rows = rows
        self.command = command
        self.typed_word = typed_word

    def compose(self):
        with Vertical(id="recap"):
            for row in self.rows:
                yield RecapRow(*row)
        yield Static("Checks", classes="section")
        yield Static(Text("Checking…", style=MUTED), id="checks")
        if self.typed_word:
            yield Callout(f"Some of these have uncommitted changes that will be lost. Type {self.typed_word} to confirm.", kind="warn")
            yield Input(placeholder=self.typed_word, id="typed")
        yield Btn("▸ Show the command", "command", "ghost link", id="toggle-command")
        yield Static(describe(self.command), classes="code", id="command")

    def on_mount(self):
        self.query_one("#command").display = False

    def on_input_changed(self, event):
        event.stop()
        self.post_message(Changed())

    def toggle_command(self):
        shown = self.query_one("#command")
        shown.display = not shown.display
        self.query_one("#toggle-command", Btn).update("▾ Hide the command" if shown.display else "▸ Show the command")

    @property
    def confirmed(self):
        if not self.typed_word:
            return True
        return self.query_one("#typed", Input).value.strip() == self.typed_word

    def show_checks(self, results, recheck_seconds=None):
        text = Text()
        for i, r in enumerate(results):
            text.append("\n" if i else "")
            text.append("✓ " if r["ok"] else "✕ ", style=GREEN if r["ok"] else RED)
            text.append(r["label"], style=INK)
            if not r["ok"]:
                text.append(f"  →  {r['fix']}", style=MUTED)
        if recheck_seconds and not all(r["ok"] for r in results):
            text.append(f"\n\nFix it in another terminal. The checks run again every {recheck_seconds} seconds.", style=MUTED)
        self.query_one("#checks", Static).update(text if results else Text("Nothing to check.", style=MUTED))


class ProgressView(Vertical):
    def compose(self):
        yield Static(id="steps")
        yield Static(classes="code", id="log")
        yield Static(id="progress-note", classes="hint")
        yield Callout(kind="error", id="failure")

    def update_job(self, job, tick):
        if not self.query("#steps"):  # still mounting; the next tick draws it
            return
        expected = job.meta.get("expected", [])
        seen = job.steps
        shown = list(seen) + [step for step in expected if step not in seen]
        text = Text()
        for i, step in enumerate(shown):
            text.append("\n" if i else "")
            if step not in seen:
                text.append("○ ", style=LINE)
                text.append(step, style=MUTED)
                continue
            current = job.state == "running" and step == seen[-1]
            failed = job.state == "failed" and step == seen[-1]
            mark, style = (SPINNER[tick % len(SPINNER)], AQUA) if current else ("✕", RED) if failed else ("✓", GREEN)
            text.append(f"{mark} ", style=style)
            text.append(step, style=f"bold {INK}" if current else INK)
        self.query_one("#steps", Static).update(text)
        tail = "\n".join(list(job.log)[-LOG_LINES:])
        self.query_one("#log", Static).update(Text(tail or "Starting…", style=MUTED))
        note = "You can hide this. The board tile keeps showing progress." if job.state == "running" else ""
        self.query_one("#progress-note", Static).update(note)
        failure = self.query_one("#failure", Callout)
        failure.display = job.state == "failed"
        failure.update(job.error or "")


class ReadyView(Vertical):
    def compose(self):
        yield Static(classes="box", id="urls")
        yield Callout(id="agent-note")

    def update_job(self, job):
        if not self.query("#urls"):
            return
        urls = job.meta["urls"]
        pairs = [(name, urls[name]) for name in ("raichu", "portals", "ditto", "pikachu")]
        self.query_one("#urls", Static).update(key_values(pairs + [("folder", job.meta["platform"])]))
        note = self.query_one("#agent-note", Callout)
        if not job.meta.get("agent_prompt"):
            note.display = False
        elif job.agent:
            note.update(f"{job.meta['agent_prompt']} started {PLACES[job.meta['where']]}. It appears on the board as a tile linked to this platform.")
        elif job.notice:
            note.remove_class("info")
            note.add_class("error")
            note.update(job.notice)
        else:
            note.update("Starting the agent…")
