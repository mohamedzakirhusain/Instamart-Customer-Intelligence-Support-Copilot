"""app.py -- optional local web UI for the Copilot. Standard library only (no extra packages).

    python app.py          then open  http://127.0.0.1:8000

It serves web/index.html and a few JSON endpoints that call the same functions as the pipeline
(src/services.py). Run `python run_project.py` once first so the data files exist."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src import services as S  # noqa: E402

HOST, PORT = "127.0.0.1", 8000          # local only: not reachable from other computers
MAX_BODY = 20_000

POST_ROUTES = {
    "/api/redact": lambda b: S.redact_text(b["text"]),
    "/api/classify": lambda b: S.classify_ticket(b["text"], bool(b.get("few_shot", True))),
    "/api/policy": lambda b: S.policy_answer(b["question"]),
    "/api/refund": lambda b: S.request_refund(b["order_id"]),
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            with open(os.path.join(ROOT, "web", "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html")
        static = {"/style.css": "text/css", "/app.js": "text/javascript"}      # only these two files are served
        if url.path in static:
            with open(os.path.join(ROOT, "web", url.path.lstrip("/")), "rb") as f:
                return self._send(200, f.read(), static[url.path])
        if url.path == "/api/segments":
            try:
                q = parse_qs(url.query)
                return self._send(200, S.segments(q.get("customer_id", [""])[0], q.get("view", ["summary"])[0]))
            except FileNotFoundError:
                return self._send(500, {"error": "Data files are missing. Run `python run_project.py` first."})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        route = POST_ROUTES.get(urlparse(self.path).path)
        if route is None:
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                return self._send(413, {"error": "input too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            return self._send(200, route(body))
        except (KeyError, json.JSONDecodeError):
            return self._send(400, {"error": "bad request"})
        except FileNotFoundError:
            return self._send(500, {"error": "Data files are missing. Run `python run_project.py` first."})
        except Exception as exc:                          # show the problem in the page instead of crashing
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):                    # quieter console
        print(f"{self.address_string()} {fmt % args}")


class Server(HTTPServer):
    # On Windows, allow_reuse_address=True lets a second copy bind the same port without any error, so an old
    # server can silently keep answering with outdated code. Turn it off so a second start fails loudly.
    allow_reuse_address = False


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT          # python app.py 8001
    # Single-threaded on purpose: the mock model keeps global counters, so requests must run one at a time.
    try:
        server = Server((HOST, port), Handler)
    except OSError:
        sys.exit(f"Port {port} is already in use: another copy of app.py is probably still running.\n"
                 f"Close it (Ctrl+C in its terminal) and start again, or use another port: python app.py {port + 1}")
    print(f"Copilot UI running at http://{HOST}:{port}   (press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
