import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..core.config import PORT
from ..core.notify import watch
from ..core.sessions import close_session
from ..core.state import build_state
from ..core.store import dismiss_session, rename_session

STATIC = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            try:
                body = json.dumps(build_state()).encode()
                self._send(200, body, "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
        elif self.path.startswith("/assets/"):
            f = (STATIC / "assets" / Path(self.path[len("/assets/"):].split("?")[0]).name)
            ctype = {".png": "image/png", ".svg": "image/svg+xml"}.get(f.suffix)
            if ctype and f.is_file():
                self._send(200, f.read_bytes(), ctype)
            else:
                self._send(404, b"not found", "text/plain")
        elif self.path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        host = self.headers.get("Host", "").split(":")[0]
        json_body = self.headers.get("Content-Type", "").startswith("application/json")
        actions = {
            "/api/close": lambda body: close_session(body.get("sessionId", "")),
            "/api/dismiss": lambda body: dismiss_session(body.get("sessionId", "")),
            "/api/rename": lambda body: rename_session(body.get("sessionId", ""), body.get("title", "")),
        }
        if self.path not in actions:
            self._send(404, b"not found", "text/plain")
        elif host not in ("localhost", "127.0.0.1") or not json_body:
            self._send(403, b"forbidden", "text/plain")
        else:
            try:
                size = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(size))
            except Exception:
                self._send(400, json.dumps({"ok": False, "message": "Bad request."}).encode(), "application/json")
                return
            ok, message = actions[self.path](body)
            self._send(200 if ok else 409, json.dumps({"ok": ok, "message": message}).encode(), "application/json")


def serve():
    threading.Thread(target=watch, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Agent dashboard on http://localhost:{PORT}")
    server.serve_forever()
