from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Rule, Static

from ...core import agents
from ...core.jobs import Busy
from ...core.root import RootMissing
from ...core.wizard import preflight
from ...core.wizard.commands import build
from ...core.wizard.flows import FLOWS
from ...core.wizard.model import Option, Question, options_for
from ...core.wizard.run import launch
from ..theme import MUTED
from .inputs import Changed, Submitted, make_input
from .parts import Btn, crumbs
from .styles import WIZARD_CSS
from .views import ProgressView, ReadyView, SummaryView

MENU = Question("flow", "choice", "What do you want to do?", "Pick one. You can cancel at any step.",
                [Option(f.key, f.label, f.detail, tag=f.tag) for f in FLOWS.values()])
VERBS = {"new": "Create platform", "review": "Create platform", "clean": "Delete"}
AFTER_QUESTIONS = {"new": 3, "review": 3, "clean": 2}  # summary, progress, and the ready screen for flows that have one
TICK_SECONDS = 0.4


def button(spec):
    label, action, kind, *extra = spec
    return Btn(label, action, kind, **(extra[0] if extra else {}))


class WizardScreen(ModalScreen):
    """Asks one question at a time, then shows a summary, runs the job and shows the result.
    The questions live in core/wizard/flows.py; this class only draws them."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("enter", "confirm", "Confirm", show=False),
        Binding("r", "recheck", "Re-check", show=False),
        Binding("c", "toggle_command", "Command", show=False),
    ]
    DEFAULT_CSS = WIZARD_CSS

    def __init__(self):
        super().__init__()
        self.flow = None
        self.answers = {}
        self.position = -1
        self.loaded = {}
        self.question = MENU
        self.phase = "question"
        self.checks_ok = False
        self.job = None
        self.tick = 0
        self.failed_footer = False

    def compose(self):
        with Vertical(id="wizard"):
            with Vertical(id="wizard-head"):
                yield Static(id="crumbs")
                yield Static(id="wizard-title")
                yield Static(id="wizard-help")
            yield Rule()
            yield VerticalScroll(id="wizard-body")
            yield Rule()
            yield Horizontal(id="wizard-foot")

    def on_mount(self):
        self.set_interval(TICK_SECONDS, self.on_tick)
        self.fit_body()
        self.show_question(MENU)

    def on_resize(self):
        self.fit_body()

    def fit_body(self):
        # the head, footer, rules and border take about 15 rows; the body scrolls in what is left
        self.query_one("#wizard-body").styles.max_height = max(6, self.size.height - 15)

    # layout helpers

    def head(self, title, help_text, step=None, total=None):
        crumbs_row = self.query_one("#crumbs", Static)
        crumbs_row.display = step is not None
        if step is not None:
            crumbs_row.update(crumbs(step, total))
        self.query_one("#wizard-title", Static).update(Text(title, style="bold"))
        self.query_one("#wizard-help", Static).update(Text(help_text, style=MUTED))
        self.query_one("#wizard-help").display = bool(help_text)

    def body(self, *widgets):
        area = self.query_one("#wizard-body")
        area.remove_children()
        area.mount(*widgets)
        area.scroll_home(animate=False)
        return widgets[0]

    def foot(self, left, right):
        foot = self.query_one("#wizard-foot")
        foot.remove_children()
        foot.mount(*[button(spec) for spec in left], Static(classes="spacer"), *[button(spec) for spec in right])

    def set_enabled(self, button_id, enabled):
        for found in self.query(f"#{button_id}"):
            found.disabled = not enabled

    def questions(self):
        return self.flow.questions

    def is_asked(self, question):
        return question.when is None or question.when(self.answers)

    def asked_count(self):
        return len([q for q in self.questions() if self.is_asked(q)])

    def step_of(self, offset=0):
        asked = [q for q in self.questions() if self.is_asked(q)]
        total = len(asked) + AFTER_QUESTIONS[self.flow.key]
        return (offset or asked.index(self.question) + 1), total

    # questions

    def move(self, step):
        self.position += step
        while 0 <= self.position < len(self.questions()) and not self.is_asked(self.questions()[self.position]):
            self.position += step
        if self.position < 0:
            self.flow, self.position = None, -1
            self.show_question(MENU)
        elif self.position >= len(self.questions()):
            self.show_summary()
        else:
            self.show_question(self.questions()[self.position])

    def show_question(self, question):
        self.phase, self.question = "question", question
        step, total = self.step_of() if self.flow else (None, None)
        self.head(question.title, question.help, step, total)
        self.foot([("Back" if self.flow else "Cancel", "back", "ghost")],
                  [("Next" if self.flow else "Choose", "next", "primary", {"disabled": True})])
        if callable(question.options):
            self.body(Static(Text("Loading…", style=MUTED)))
            self.set_next_enabled(False)
            self.load_options(question)
        else:
            self.mount_input(question, options_for(question, self.answers))

    @work(thread=True, exclusive=True)
    def load_options(self, question):
        try:
            options = options_for(question, self.answers)
        except Exception as e:
            self.app.call_from_thread(self.body, Static(Text(f"Could not load: {e}", style=MUTED)))
            return
        self.app.call_from_thread(self.mount_input, question, options)

    def mount_input(self, question, options):
        if question is not self.question:
            return
        if question.kind != "text" and not options:
            self.body(Static(Text("Nothing found.", style=MUTED)))
            self.set_next_enabled(False)
            return
        self.loaded[question.id] = options
        widget = self.body(make_input(question, options, self.answers))
        self.call_after_refresh(widget.focus)

    def set_next_enabled(self, enabled):
        for button in self.query("#wizard-foot Btn"):
            if button.action == "next":
                button.disabled = not enabled

    def current_input(self):
        found = self.query("#wizard-body > *")
        return found.first() if found else None

    def on_changed(self, event: Changed):
        widget = self.current_input()
        if self.phase == "question" and widget is not None and hasattr(widget, "valid"):
            self.set_next_enabled(widget.valid)
        elif self.phase == "summary":
            self.update_create()

    def on_submitted(self, event: Submitted):
        event.stop()
        self.action_next()

    def on_input_submitted(self, event):
        self.action_confirm()

    def action_next(self):
        widget = self.current_input()
        if self.phase != "question" or widget is None or not hasattr(widget, "answer") or not widget.valid:
            return
        self.answers[self.question.id] = widget.answer()
        if self.flow is None:
            self.flow, self.answers = FLOWS[widget.answer()], {}
        self.move(1)

    # summary

    def label_for(self, question, value):
        names = {o.value: o for o in self.loaded.get(question.id) or options_for(question, self.answers)}
        return names[value].label if value in names else value

    def recap_rows(self):
        rows = []
        for question in self.questions():
            if not self.is_asked(question) or question.id not in self.answers:
                continue
            value = self.answers[question.id]
            names = {o.value: o for o in self.loaded.get(question.id) or []}
            for i, item in enumerate(value if isinstance(value, list) else [value]):
                badge = names[item].badge if item in names else ""
                rows.append((question.short if i == 0 else "", self.label_for(question, item), question.id if i == 0 else "", badge))
        return rows

    def show_summary(self):
        self.phase, self.checks_ok = "summary", False
        self.head(f"Ready to {VERBS[self.flow.key].split()[0].lower()}", self.flow.label,
                  *self.step_of(self.asked_count() + 1))
        word = self.flow.typed_confirm(self.answers) if self.flow.typed_confirm else None
        summary = SummaryView(self.recap_rows(), build(self.flow.key, self.answers)[0], word)
        self.body(summary)
        kind = "danger" if self.flow.key == "clean" else "primary"
        self.foot([("Back", "back", "ghost")], [(VERBS[self.flow.key], "create", kind, {"id": "create", "disabled": True})])
        self.run_checks()

    @work(thread=True, exclusive=True)
    def run_checks(self):
        results = preflight.run(self.flow.key, self.answers)
        self.app.call_from_thread(self.show_checks, results)

    def show_checks(self, results):
        if self.phase != "summary":
            return
        self.checks_ok = all(r["ok"] for r in results)
        self.query_one(SummaryView).show_checks(results)
        self.update_create()

    def update_create(self):
        summary = self.query_one(SummaryView)
        self.set_enabled("create", self.checks_ok and summary.confirmed)

    def edit(self, question_id):
        self.position = next(i for i, q in enumerate(self.questions()) if q.id == question_id)
        self.show_question(self.questions()[self.position])

    def action_recheck(self):
        if self.phase == "summary":
            self.query_one(SummaryView).show_checks([])
            self.run_checks()

    def action_toggle_command(self):
        if self.phase == "summary":
            self.query_one(SummaryView).toggle_command()

    # running

    def create(self):
        try:
            self.job = launch(self.flow.key, self.answers)
        except (Busy, RootMissing) as e:
            self.notify(str(e), severity="error")
            return
        self.phase = "progress"
        self.head(f"{'Cleaning up' if self.flow.key == 'clean' else 'Creating platform'}…", self.job.label,
                  *self.step_of(self.asked_count() + 2))
        self.body(ProgressView())
        self.foot([("Hide", "hide", "ghost")], [("Continue", "continue", "primary", {"id": "continue", "disabled": True})])
        self.failed_footer = False
        self.call_after_refresh(self.show_progress)

    def show_progress(self):
        self.query_one(ProgressView).update_job(self.job, self.tick)

    def on_tick(self):
        self.tick += 1
        if self.phase == "progress":
            self.show_progress()
            self.set_enabled("continue", self.job.state == "done")
            if self.job.state == "failed" and not self.failed_footer:
                self.failed_footer = True
                self.foot([("Hide", "hide", "ghost")], [("Close", "close", "plain")])
        elif self.phase == "ready":
            self.query_one(ReadyView).update_job(self.job)

    def show_ready(self):
        self.phase = "ready"
        self.head(f"{self.job.label} is ready", "All repos are on your branch." if self.flow.key == "new"
                  else "Real PR branches are checked out, so a push goes to the PR.",
                  *self.step_of(self.asked_count() + 3))
        view = ReadyView()
        self.body(view)
        meta = self.job.meta
        opener = {"background": ("Open agent", "open_agent"), "cmux": ("Open in cmux", "bring"),
                  "terminal": (f"Open in {meta['terminal_app']}", "bring")}.get(meta["where"])
        right = ([(*opener, "plain")] if meta["agent_prompt"] and opener else []) + [("Run dev servers", "servers", "primary")]
        self.foot([("Back to board", "close", "plain")], right)
        self.call_after_refresh(view.update_job, self.job)

    def advance(self):
        if self.phase == "progress" and self.job.state == "done":
            if self.flow.key == "clean":
                self.dismiss(self.job)
            else:
                self.show_ready()

    # buttons and keys

    def on_btn_pressed(self, event: Btn.Pressed):
        action = event.action
        if action.startswith("edit:"):
            self.edit(action[len("edit:"):])
        elif action in ("back", "next", "create", "continue", "recheck"):
            {"back": self.action_back, "next": self.action_next, "create": self.action_confirm,
             "continue": self.action_confirm, "recheck": self.action_recheck}[action]()
        elif action == "command":
            self.action_toggle_command()
        elif action in ("hide", "close"):
            self.dismiss(self.job)
        elif action == "open_agent":
            self.dismiss((self.job, "open_agent"))
        elif action == "bring":
            agents.bring_forward(self.job.meta["where"], self.job.meta["terminal_app"])
        elif action == "servers":
            self.run_servers()

    @work(thread=True)
    def run_servers(self):
        meta = self.job.meta
        ok, message = agents.run_dev_servers(meta["platform"], meta["where"], meta["terminal_app"])
        self.app.call_from_thread(self.notify, "Dev servers started." if ok else message, severity="information" if ok else "error")

    def action_confirm(self):
        if self.phase == "question":
            self.action_next()
        elif self.phase == "summary" and self.checks_ok and self.query_one(SummaryView).confirmed:
            self.create()
        elif self.phase == "progress":
            self.advance()

    def action_back(self):
        if self.phase == "summary":
            self.position = len(self.questions())
            self.move(-1)
        elif self.phase in ("progress", "ready"):
            self.dismiss(self.job)
        elif self.flow is None:
            self.dismiss(None)
        else:
            self.move(-1)
