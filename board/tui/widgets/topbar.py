from textual.widgets import Static


class TopBar(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.hits = []

    def on_click(self, event):
        offset = event.get_content_offset(self)
        if not offset or offset.y != 0:
            return
        for start, end, key in self.hits:
            if start <= offset.x < end:
                self.app.toggle_filter(key)
                return
