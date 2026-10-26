from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Static

from ..theme import FIELD, INK, MUTED, RED
from .parts import Callout, key_values


class Changed(Message):
    """The answer, or whether it is acceptable, changed."""


class Submitted(Message):
    """The person pressed enter in an input."""


class ChoiceCard(Static):
    def __init__(self, option, index):
        super().__init__()
        self.option = option
        self.index = index

    def render(self):
        text = Text(self.option.label, style=f"bold {INK}")
        for line in (self.option.detail, self.option.tag):
            if line:
                text.append("\n" + line, style=MUTED)
        return text

    def on_click(self, event):
        event.stop()
        self.parent.select(self.index)


class ChoiceInput(Vertical, can_focus=True):
    """One bordered card per option. Two options sit side by side."""

    BINDINGS = [
        Binding("up,left,k", "move(-1)", "Previous", show=False),
        Binding("down,right,j", "move(1)", "Next", show=False),
        Binding("enter", "submit", "Choose", show=False),
    ]

    def __init__(self, options, current=None):
        super().__init__(classes="two" if len(options) == 2 else "")
        self.options = options
        self.index = next((i for i, o in enumerate(options) if o.value == current), 0)

    def compose(self):
        for i, option in enumerate(self.options):
            yield ChoiceCard(option, i)

    def on_mount(self):
        self.select(self.index)

    def select(self, index):
        self.index = index
        for card in self.query(ChoiceCard):
            card.set_class(card.index == index, "selected")
        self.post_message(Changed())

    def action_move(self, step):
        self.select(max(0, min(len(self.options) - 1, self.index + step)))

    def action_submit(self):
        self.post_message(Submitted())

    def answer(self):
        return self.options[self.index].value

    valid = property(lambda self: True)


class TextField(Vertical):
    """A labelled text input that checks the answer as it is typed and shows a preview."""

    def __init__(self, question, answers, current):
        super().__init__()
        self.question = question
        self.answers = answers
        self.current = current or question.default or ""
        self.valid = False

    def compose(self):
        yield Static(self.question.label, classes="label")
        yield Input(value=self.current, select_on_focus=False)
        yield Static(self.question.hint, classes="hint")
        yield Static(classes="box", id="preview")
        yield Callout(kind="error", id="field-error")

    def on_mount(self):
        self.check()

    def focus(self, scroll_visible=True):
        self.query_one(Input).focus()
        return self

    def answer(self):
        return self.query_one(Input).value.strip()

    def check(self):
        value = self.answer()
        error = self.question.validate(value, self.answers) if value and self.question.validate else None
        self.valid = bool(value) and error is None
        pairs = self.question.preview(value, self.answers) if value and self.question.preview else []
        preview = self.query_one("#preview", Static)
        preview.display = bool(pairs)
        if pairs:
            preview.update(key_values(pairs))
        failure = self.query_one("#field-error", Callout)
        failure.display = bool(error)
        failure.update(error or "")
        self.post_message(Changed())

    def on_input_changed(self, event):
        event.stop()
        self.check()

    def on_input_submitted(self, event):
        event.stop()
        self.post_message(Submitted())


class CheckRow(Static):
    def __init__(self, option):
        super().__init__()
        self.option = option
        self.checked = False

    def render(self):
        width = max(10, self.size.width - 2)
        badge = Text(f" {self.option.badge} ", style=f"bold {FIELD} on {RED}") if self.option.badge else Text()
        first = Text("☑ " if self.checked else "☐ ", style=INK if self.checked else MUTED)
        label = Text(self.option.label, style=f"bold {INK}")
        label.truncate(max(1, width - 2 - badge.cell_len - 1), overflow="ellipsis")
        first.append_text(label)
        first.append(" " * max(1, width - first.cell_len - badge.cell_len))
        first.append_text(badge)
        second = Text("  " + self.option.detail, style=MUTED)
        second.truncate(width, overflow="ellipsis")
        return Text("\n").join([first, second])

    def on_click(self, event):
        event.stop()
        self.parent.cursor_to(self)
        self.parent.toggle()


class CheckList(Vertical, can_focus=True):
    BINDINGS = [
        Binding("up,k", "move(-1)", "Previous", show=False),
        Binding("down,j", "move(1)", "Next", show=False),
        Binding("space", "toggle", "Toggle", show=False),
        Binding("enter", "submit", "Next", show=False),
    ]

    def __init__(self, options, current):
        super().__init__()
        self.options = options
        self.current = set(current or [])
        self.cursor = 0

    def compose(self):
        for option in self.options:
            yield CheckRow(option)

    def on_mount(self):
        for row in self.rows():
            row.checked = row.option.value in self.current
        self.mark_cursor()

    def rows(self):
        return list(self.query(CheckRow))

    def mark_cursor(self):
        for i, row in enumerate(self.rows()):
            row.set_class(i == self.cursor, "cursor")
            row.refresh()
        self.post_message(Changed())

    def cursor_to(self, row):
        self.cursor = self.rows().index(row)

    def action_move(self, step):
        self.cursor = max(0, min(len(self.options) - 1, self.cursor + step))
        self.mark_cursor()
        self.rows()[self.cursor].scroll_visible()

    def toggle(self):
        row = self.rows()[self.cursor]
        row.checked = not row.checked
        self.mark_cursor()

    def action_toggle(self):
        self.toggle()

    def action_submit(self):
        self.post_message(Submitted())

    def answer(self):
        return [row.option.value for row in self.rows() if row.checked]


class MultiField(Vertical):
    """A checkbox list with a message underneath until something is picked."""

    def __init__(self, question, answers, options, current):
        super().__init__()
        self.question = question
        self.answers = answers
        self.options = options
        self.current = current
        self.valid = False

    def compose(self):
        yield CheckList(self.options, self.current)
        yield Callout("Pick at least one.", kind="error", id="field-error")

    def focus(self, scroll_visible=True):
        self.query_one(CheckList).focus()
        return self

    def answer(self):
        return self.query_one(CheckList).answer()

    def on_changed(self, event):
        value = self.answer()
        error = self.question.validate(value, self.answers) if self.question.validate else None
        self.valid = error is None
        failure = self.query_one("#field-error", Callout)
        failure.display = bool(error)
        failure.update(error or "")


def make_input(question, options, answers):
    current = answers.get(question.id)
    if question.kind == "text":
        return TextField(question, answers, current)
    if question.kind == "multi":
        return MultiField(question, answers, options, current)
    return ChoiceInput(options, current or question.default)
