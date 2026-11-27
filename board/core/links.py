import shutil
import subprocess
import sys
import webbrowser

from .config import LINEAR_WORKSPACE


def ticket_url(ticket):
    return f"https://linear.app/{LINEAR_WORKSPACE}/issue/{ticket}"


def opener():
    if sys.platform == "darwin":
        return ["open"]
    if sys.platform.startswith("linux") and shutil.which("xdg-open"):
        return ["xdg-open"]
    return None


def open_url(url):
    argv = opener()
    if argv:
        subprocess.Popen([*argv, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)
