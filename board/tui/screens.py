from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from .theme import AQUA, INK, MUTED, RED


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


class RenameTitle(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = f"""
    RenameTitle {{ align: center middle; }}
    #rename-dialog {{ width: 70; height: auto; padding: 1 2; background: #161b22; border: tall {AQUA}; }}
    #rename-dialog Static {{ margin: 0 0 1 0; }}
    """

    def __init__(self, title, custom):
        super().__init__()
        self.current = title
        self.custom = custom

    def compose(self):
        hint = "Enter to save, empty to reset, esc to cancel" if self.custom else "Enter to save, esc to cancel"
        with Vertical(id="rename-dialog"):
            yield Static(Text("Rename card\n" + hint, style=MUTED))
            yield Input(value=self.current, select_on_focus=True)

    def on_input_submitted(self, event):
        self.dismiss(event.value)

    def action_cancel(self):
        self.dismiss(None)
