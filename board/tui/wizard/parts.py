from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from ..theme import INK, LINE, MUTED


def crumbs(step, total):
    """The row of segments at the top of a step: filled up to the current one."""
    text = Text()
    for i in range(total):
        text.append("━━ ", style=INK if i < step else LINE)
    text.append(f"Step {step} of {total}", style=MUTED)
    return text


def key_values(pairs, width=None):
    width = width or max(len(k) for k, _ in pairs)
    text = Text()
    for i, (key, value) in enumerate(pairs):
        text.append("\n" if i else "")
        text.append(key.ljust(width + 2), style=MUTED)
        text.append(value, style=INK)
    return text


class Callout(Static):
    """A short message with a colored edge. kind is "error", "warn" or "info"."""

    def __init__(self, text="", kind="info", **kwargs):
        super().__init__(text, classes=f"callout {kind}", **kwargs)


class Btn(Static):
    """A button drawn as a bordered row. kind is "plain", "primary", "ghost" or "danger"."""

    class Pressed(Message):
        def __init__(self, action):
            super().__init__()
            self.action = action

    def __init__(self, label, action, kind="plain", **kwargs):
        super().__init__(label, classes=f"btn {kind}", **kwargs)
        self.action = action

    def on_click(self, event):
        event.stop()
        self.post_message(self.Pressed(self.action))
