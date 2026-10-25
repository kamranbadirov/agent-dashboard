import os
from pathlib import Path

from ..core.assets import repo_images

GITHUB_ICON = "\uf09b"
def repo_image(repo):
    return repo_images().get((repo or "").lower())


def nerd_font():
    forced = os.environ.get("NERD_FONT")
    if forced in ("0", "1"):
        return forced == "1"
    if os.environ.get("TERM_PROGRAM") == "ghostty":
        return True
    dirs = [Path.home() / "Library" / "Fonts", Path("/Library/Fonts"),
            Path.home() / ".local" / "share" / "fonts", Path("/usr/share/fonts")]
    return any(next(d.glob("**/*[Nn]erd*"), None) for d in dirs if d.is_dir())


NERD = nerd_font()
