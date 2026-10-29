import os
import sys

from .core.config import ROOT
from .core.state import build_state


def main():
    if "--json" in sys.argv:
        import json

        print(json.dumps(build_state(), indent=2))
        return
    venv_python = ROOT / ".venv" / "bin" / "python"
    os.environ["PYTHONPATH"] = str(ROOT)
    os.execv(str(venv_python), [str(venv_python), "-m", "board.tui.app"])


if __name__ == "__main__":
    main()
