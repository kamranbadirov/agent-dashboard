from textual_image.renderable import Image as AutoRenderable
from textual_image.widget import BaseImage

WIDTH = 4
HEIGHT = 2


class RepoImage(BaseImage, Renderable=AutoRenderable):
    def __init__(self, path, pr):
        super().__init__(path, classes="repo-image")
        self.pr = pr
        self.tooltip = f"{pr['repo']}#{pr['number']}"

    def on_click(self, event):
        event.stop()
        self.app.open_url(self.pr["url"])
