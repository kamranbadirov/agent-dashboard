from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..format import ago, chips, pr_badges
from ..jobs_view import job_text
from ..theme import AQUA, COLOR, GRAY, INK, MUTED, NAME


class SectionHeader(Static):
    pass


class CloseButton(Static):
    def on_click(self):
        self.app.action_close_agent()


class Preview(VerticalScroll):
    def compose(self):
        yield CloseButton("✕ Close agent", id="close-btn")
        yield Static(id="preview-body")

    def show(self, s):
        body = self.query_one("#preview-body", Static)
        btn = self.query_one("#close-btn")
        btn.display = bool(s)
        btn.update("✕ Close agent" if s and s["alive"] else "✕ Remove")
        if not s:
            body.update(Text("Nothing selected.", style=MUTED))
            return
        color = COLOR.get(s["status"], GRAY)
        t = Text()
        t.append(f" {NAME.get(s['status'], s['status'])} ", style=f"bold #0d1117 on {color}")
        t.append(f"   {ago(s['lastActivity'])}\n\n", style=MUTED)
        t.append(s["title"] + "\n", style=f"bold {INK}")
        if s.get("job"):
            t.append("\n")
            t.append_text(job_text(s["job"]))
            body.update(t)
            return
        meta = "   ".join(v for v in [s.get("name"), s.get("gitBranch")] if v)
        if meta:
            t.append(meta + "\n", style=MUTED)
        if s["tickets"]:
            t.append("\n")
            t.append_text(chips(s["tickets"]))
            t.append("\n")

        if s["status"] == "your_move":
            t.append("\nWhat you need to do\n", style=f"bold {AQUA}")
            for r in s["reasons"]:
                t.append(f"  {r[0].upper() + r[1:]}\n", style=INK)
            if s.get("pendingQuestion"):
                t.append(f"\n  {s['pendingQuestion']}\n", style=INK)

        if s["prs"]:
            t.append("\nPull requests\n", style=f"bold {INK}")
            for p in s["prs"]:
                t.append(f"  {p['repo']}#{p['number']}  ", style=f"bold {INK}")
                for text, col in pr_badges(p):
                    t.append(f" {text} ", style=f"#0d1117 on {col}")
                    t.append(" ")
                t.append(f"\n  {p['title']}\n", style=MUTED)

        text = s.get("summary")
        if text:
            t.append("\nLatest recap\n", style=f"bold {INK}")
            t.append(text.strip() + "\n", style=INK)
        if s.get("lastAssistant"):
            t.append("\nLast reply\n", style=f"bold {INK}")
            t.append(s["lastAssistant"].strip()[-700:] + "\n", style=MUTED)
        if s.get("cwd"):
            t.append(f"\n{s['cwd']}\n", style=MUTED)
        body.update(t)
        self.scroll_home(animate=False)
