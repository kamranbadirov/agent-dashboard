from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from ..format import ago, chips, pr_badges
from ..jobs_view import job_text
from ..theme import AQUA, COLOR, GRAY, INK, MUTED, NAME

MAX_ROWS = 9


class SectionHeader(Static):
    pass


class ActionBar(Static):
    """One quiet row of the actions for the selected tile, each with its key. A click runs the action."""

    GAP = "   "

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.hits = []
        self.actions = []

    def show(self, actions):
        self.actions = list(actions)
        self.display = bool(self.actions)
        self.draw()

    def on_resize(self):
        self.draw()

    def draw(self):
        """Lay the actions out in rows that fit the panel, so none is cut off."""
        width = max(10, self.size.width or 60)
        lines, hits = [Text()], []
        for key, label, action in self.actions:
            size = len(key) + 1 + len(label)
            line = lines[-1]
            if line.cell_len and line.cell_len + len(self.GAP) + size > width:
                lines.append(Text())
                line = lines[-1]
            elif line.cell_len:
                line.append(self.GAP)
            start = line.cell_len
            line.append(key, style=f"bold {INK}")
            line.append(f" {label}", style=MUTED)
            hits.append((len(lines) - 1, start, line.cell_len, action))
        self.hits = hits
        self.update(Text("\n").join(lines))

    def on_click(self, event):
        offset = event.get_content_offset(self)
        if not offset:
            return
        for row, start, end, action in self.hits:
            if row == offset.y and start <= offset.x < end:
                getattr(self.app, f"action_{action}")()
                return


class SessionRow(Static):
    def __init__(self, index, session, picked):
        super().__init__(classes="session-row picked" if picked else "session-row")
        self.index = index
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{index + 1} ", style=f"bold {INK if picked else MUTED}")
        text.append("● ", style=COLOR.get(session["status"], GRAY))
        text.append(session["title"], style=f"bold {INK}" if picked else INK)
        text.append(f"  {ago(session['lastActivity'])}", style=MUTED)
        self.update(text)

    def on_click(self):
        self.app.action_pick(self.index)


def details(s, prs):
    t = Text()
    meta = "   ".join(v for v in [s.get("name"), s.get("gitBranch")] if v)
    if meta:
        t.append(meta + "\n", style=MUTED)
    if s["status"] == "your_move":
        t.append("\nWhat you need to do\n", style=f"bold {AQUA}")
        for r in s["reasons"]:
            t.append(f"  {r[0].upper() + r[1:]}\n", style=INK)
        if s.get("pendingQuestion"):
            t.append(f"\n  {s['pendingQuestion']}\n", style=INK)
    if prs:
        t.append("\nPull requests\n", style=f"bold {INK}")
        for p in prs:
            t.append(f"  {p['repo']}#{p['number']}  ", style=f"bold {INK}")
            for label, color in pr_badges(p):
                t.append(f" {label} ", style=f"#0d1117 on {color}")
                t.append(" ")
            t.append(f"\n  {p['title']}\n", style=MUTED)
    if s.get("summary"):
        t.append("\nLatest recap\n", style=f"bold {INK}")
        t.append(s["summary"].strip() + "\n", style=INK)
    if s.get("lastAssistant"):
        t.append("\nLast reply\n", style=f"bold {INK}")
        t.append(s["lastAssistant"].strip()[-700:] + "\n", style=MUTED)
    if s.get("cwd"):
        t.append(f"\n{s['cwd']}\n", style=MUTED)
    return t


class Preview(VerticalScroll):
    def compose(self):
        yield Static(id="preview-head")
        yield ActionBar(id="preview-actions")
        yield Vertical(id="preview-sessions")
        yield Static(id="preview-body")

    def show(self, tile, target=None, actions=()):
        head = self.query_one("#preview-head", Static)
        body = self.query_one("#preview-body", Static)
        rows = self.query_one("#preview-sessions", Vertical)
        rows.remove_children()
        self.query_one(ActionBar).show(list(actions) if tile else [])
        if not tile:
            head.update(Text("Nothing selected.", style=MUTED))
            body.update("")
            return
        target = target or tile
        t = Text()
        t.append(tile["title"] + "\n", style=f"bold {INK}")
        t.append(f" {NAME.get(tile['status'], tile['status'])} ", style=f"bold #0d1117 on {COLOR.get(tile['status'], GRAY)}")
        t.append(f"   {ago(tile['lastActivity'])}", style=MUTED)
        if tile["tickets"]:
            t.append("   ")
            t.append_text(chips(tile["tickets"][:3]))
        head.update(t)
        group = tile.get("group")
        if group:
            rows.mount(Static(Text(f"Sessions  {len(group)}", style=f"bold {INK}"), classes="section"))
            rows.mount_all([SessionRow(i, s, s is target) for i, s in enumerate(group[:MAX_ROWS])])
        if target.get("job"):
            body.update(job_text(target["job"]))
        else:
            body.update(details(target, tile["prs"] if group else target["prs"]))
        self.scroll_home(animate=False)
