import os
import sys

from .core.config import ROOT
from .core.state import build_state


def main():
    if "--tui" in sys.argv:
        venv_python = ROOT / ".venv" / "bin" / "python"
        os.environ["PYTHONPATH"] = str(ROOT)
        os.execv(str(venv_python), [str(venv_python), "-m", "agentboard.tui.app"])
    if "--json" in sys.argv:
        import json

        print(json.dumps(build_state(), indent=2))
        return
    from .web.server import serve

    serve()


if __name__ == "__main__":
    main()
