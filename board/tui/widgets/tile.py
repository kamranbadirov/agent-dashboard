from rich.text import Text
from textual.widget import Widget

from ..format import ago, headline, ticket_line
from ..icons import repo_image
from ..theme import COLOR, GRAY, INK, MUTED, NAME
from .repo_image import HEIGHT, WIDTH, RepoImage

MAX_IMAGES = 2


class AgentTile(Widget, can_focus=True):
    def __init__(self, session):
        super().__init__(classes=f"tile {session['status']}")
        self.session = session
        self.links = []
        self.badges = self.repo_badges()

    def repo_badges(self):
        seen = {}
        for p in self.session["prs"]:
            path = repo_image(p["repo"])
            if path and p["repo"].lower() not in seen:
                seen[p["repo"].lower()] = (path, p)
        return list(seen.values())[:MAX_IMAGES]

    def compose(self):
        for path, pr in self.badges:
            yield RepoImage(path, pr)

    def on_mount(self):
        self.layout_images()

    def on_resize(self):
        self.layout_images()

    def layout_images(self):
        images = list(self.query(RepoImage))
        for i, img in enumerate(images):
            img.styles.offset = (self.size.width - 2 - (WIDTH + 1) * (len(images) - i), 1)
            img.styles.width = WIDTH
            img.styles.height = HEIGHT

    def render(self):
        s = self.session
        color = COLOR.get(s["status"], GRAY)
        width = max(10, self.size.width - 4)
        label = headline(s) if s["status"] == "your_move" else NAME.get(s["status"], s["status"])
        refs = " ".join(f"#{p['number']}" for p in s["prs"][:3])
        muted = s["status"] in ("done", "ended")
        when = ago(s["lastActivity"])
        title = Text(s["title"], style=f"bold {MUTED if muted else INK}")
        title.truncate(max(1, width - len(when) - 1), overflow="ellipsis")
        title.append(" " * max(1, width - title.cell_len - len(when)))
        title.append(when, style=MUTED)
        status = Text(label, style=f"bold {color}")
        bottom, links = ticket_line(s)
        self.links = [(a + 2, b + 2, url) for a, b, url in links]
        bottom.truncate(max(1, width - 4), overflow="ellipsis")
        bottom.append(" " * max(1, width - bottom.cell_len - 3))
        bottom.append("✎", style=f"bold {MUTED}")
        bottom.append(" ")
        bottom.append("✕", style=f"bold {INK}")
        lines = []
        reserve = (WIDTH + 1) * len(self.badges)
        for row, body in enumerate((title, status, Text(s.get("pendingQuestion") or refs, style=MUTED), bottom)):
            body.truncate(width - reserve if row in (1, 2) else width, overflow="ellipsis")
            line = Text("▌ ", style=color)
            line.append_text(body)
            lines.append(line)
        return Text("\n").join(lines)

    def on_click(self, event):
        offset = event.get_content_offset(self)
        edge = self.size.width - 4
        if offset and offset.y == 3 and offset.x >= edge - 2:
            self.app.focused_id = self.session["sessionId"]
            if offset.x >= edge:
                self.app.action_close_agent()
            else:
                self.app.action_rename_agent()
        elif offset and offset.y == 3:
            for start, end, url in self.links:
                if start <= offset.x < end:
                    self.app.open_url(url)
                    break
