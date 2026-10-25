from rich.text import Text
from textual.widget import Widget

from ..format import ago, headline, ticket_line
from ..icons import repo_image
from ..theme import COLOR, GRAY, INK, MUTED, NAME
from .repo_image import HEIGHT, WIDTH, RepoImage

MAX_IMAGES = 3
GAP = 1
BOTTOM_ROW = 4


class AgentTile(Widget, can_focus=True):
    def __init__(self, session):
        super().__init__(classes=f"tile {session['status']}")
        self.session = session
        self.links = []
        self.badges = self.repo_badges()
        self.chips_width = 0

    def repo_badges(self):
        seen = {}
        for p in self.session["prs"]:
            path = repo_image(p["repo"])
            key = p["repo"].lower()
            if path and (key not in seen or (seen[key][1]["state"] != "OPEN" and p["state"] == "OPEN")):
                seen[key] = (path, p)
        return list(seen.values())[:MAX_IMAGES]

    def compose(self):
        for path, pr in self.badges:
            yield RepoImage(path, pr)

    def on_mount(self):
        self.layout_images()

    def on_resize(self):
        self.layout_images()

    def layout_images(self):
        x = 2 + self.chips_width
        for img in self.query(RepoImage):
            x += GAP if x > 2 else 0
            img.styles.offset = (x, BOTTOM_ROW)
            img.styles.width = WIDTH
            img.styles.height = HEIGHT
            x += WIDTH

    def render(self):
        s = self.session
        color = COLOR.get(s["status"], GRAY)
        width = max(10, self.size.width - 4)
        label = headline(s) if s["status"] == "your_move" else NAME.get(s["status"], s["status"])
        muted = s["status"] in ("done", "ended")
        when = ago(s["lastActivity"])
        title = Text(s["title"], style=f"bold {MUTED if muted else INK}")
        title.truncate(max(1, width - len(when) - 1), overflow="ellipsis")
        title.append(" " * max(1, width - title.cell_len - len(when)))
        title.append(when, style=MUTED)
        status = Text(label, style=f"bold {color}")
        ask = Text(s.get("pendingQuestion") or "", style=MUTED)
        bottom, links = ticket_line(s)
        self.links = [(a + 2, b + 2, url) for a, b, url in links]
        if self.chips_width != bottom.cell_len:
            self.chips_width = bottom.cell_len
            self.layout_images()
        bottom.truncate(max(1, width - 4), overflow="ellipsis")
        bottom.append(" " * max(1, width - bottom.cell_len - 3))
        bottom.append("✎", style=f"bold {MUTED}")
        bottom.append(" ")
        bottom.append("✕", style=f"bold {INK}")
        lines = []
        for body in (title, Text(), status, ask, bottom):
            body.truncate(width, overflow="ellipsis")
            line = Text("▌ ", style=color)
            line.append_text(body)
            lines.append(line)
        return Text("\n").join(lines)

    def on_click(self, event):
        offset = event.get_content_offset(self)
        edge = self.size.width - 4
        if offset and offset.y == BOTTOM_ROW and offset.x >= edge - 2:
            self.app.focused_id = self.session["sessionId"]
            if offset.x >= edge:
                self.app.action_close_agent()
            else:
                self.app.action_rename_agent()
        elif offset and offset.y == BOTTOM_ROW:
            for start, end, url in self.links:
                if start <= offset.x < end:
                    self.app.open_url(url)
                    break
