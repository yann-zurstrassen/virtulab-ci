"""`virtulab ui`: a local web page to pick board, protocols, sensors and tests.

Standard library only, bound to 127.0.0.1. Every API call needs the random
token printed in the URL, so another web page in your browser cannot write
files or start runs. Files are only ever written inside the project directory
the server was started with; the browser never supplies a path.
"""

import json
import secrets
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .. import VirtulabError, catalog, cigen, config, datasheets, subprocess_env
from ..check import check
from ..scaffold import apply_defaults, scaffold

PAGE = Path(__file__).with_name("index.html")
MAX_BODY = 256 * 1024


class Runs:
    """Background `virtulab run` processes, so the page can poll their output."""

    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.current: dict | None = None

    def start(self, only: list[str] | None) -> dict:
        with self.lock:
            if self.current and self.current["proc"].poll() is None:
                raise VirtulabError("A run is already in progress.")
            cmd = [sys.executable, "-m", "virtulab", "run", "-C", str(self.root)]
            if only:
                cmd += ["--only", ",".join(only)]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True, cwd=self.root,
                                    env=subprocess_env())
            run = {"proc": proc, "output": [], "id": secrets.token_hex(4)}
            threading.Thread(target=self._pump, args=(run,), daemon=True).start()
            self.current = run
            return {"id": run["id"]}

    @staticmethod
    def _pump(run: dict) -> None:
        for line in run["proc"].stdout:
            run["output"].append(line)

    def status(self) -> dict:
        run = self.current
        if not run:
            return {"state": "idle", "output": ""}
        code = run["proc"].poll()
        report = ""
        if code is not None:
            path = self.root / ".virtulab" / "report.md"
            report = path.read_text() if path.is_file() else ""
        return {"id": run["id"], "state": "running" if code is None else "done", "exit_code": code,
                "output": "".join(run["output"])[-60000:], "report": report}


def _config_from_payload(payload: dict) -> config.ProjectConfig:
    return config.from_dict(payload.get("config") or {})


def make_handler(root: Path, token: str):
    runs = Runs(root)

    class Handler(BaseHTTPRequestHandler):
        server_version = "VirtuLabUI"

        def log_message(self, *_):  # keep the terminal clean
            pass

        def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self' 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(status, json.dumps(data).encode())

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost", "[::1]")  # blocks DNS rebinding

        def do_GET(self):
            if not self._host_ok():
                return self._json({"error": "bad host"}, HTTPStatus.FORBIDDEN)
            path, _, query = self.path.partition("?")
            params = parse_qs(query)
            if path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if not self._authorized():
                return self._json({"error": "missing or wrong token"}, HTTPStatus.FORBIDDEN)
            try:
                if path == "/api/catalog":
                    return self._json(catalog.as_json())
                if path == "/api/project":
                    existing = config.load(root)
                    return self._json({"root": str(root),
                                       "config": existing.to_dict() if existing else None})
                if path == "/api/run":
                    return self._json(runs.status())
                if path == "/api/datasheet":
                    return self._json(datasheets.load(params["module"][0]))
                if path == "/api/source":
                    return self._json(datasheets.source_window(
                        params["module"][0], params["path"][0], int(params["line"][0])))
            except (KeyError, IndexError, ValueError):
                return self._json({"error": "bad request"}, HTTPStatus.BAD_REQUEST)
            except VirtulabError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-VirtuLab-Token", ""), token)

        def do_POST(self):
            if not self._host_ok() or not self._authorized():
                return self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json({"error": "request too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                path = self.path
                if path == "/api/check":
                    cfg = _config_from_payload(payload)
                    if payload.get("sample"):
                        apply_defaults(cfg)
                    result = check(cfg, None if payload.get("sample") else root, tools="warn")
                    return self._json(result.to_json())
                if path == "/api/preview":
                    cfg = _config_from_payload(payload)
                    if payload.get("sample"):
                        apply_defaults(cfg)
                    ci_path, ci_text = cigen.render(cfg)
                    return self._json({"yaml": cfg.dumps(), "ci_path": ci_path, "ci": ci_text,
                                       "docker": cigen.DOCKER_ONE_LINER})
                if path == "/api/save":
                    cfg = _config_from_payload(payload)
                    written = []
                    if payload.get("sample"):
                        written += scaffold(cfg, root, force=bool(payload.get("force")))
                    target = root / "virtulab.yml"
                    if target.exists() and not payload.get("force"):
                        raise VirtulabError("virtulab.yml already exists. Tick 'overwrite' to replace it.")
                    cfg = config.from_dict(cfg.to_dict())
                    result = check(cfg, root, tools=False)
                    if not result.ok:
                        raise VirtulabError("; ".join(f"{f.subject}: {f.message}" for f in result.errors))
                    target.write_text(cfg.dumps())
                    written.append("virtulab.yml")
                    if payload.get("write_ci", True):
                        ci_path, ci_text = cigen.render(cfg)
                        (root / ci_path).parent.mkdir(parents=True, exist_ok=True)
                        (root / ci_path).write_text(ci_text)
                        written.append(ci_path)
                    return self._json({"written": sorted(written)})
                if path == "/api/run":
                    only = payload.get("only")
                    if only is not None and not (isinstance(only, list) and all(isinstance(o, str) for o in only)):
                        raise VirtulabError("'only' must be a list of test names")
                    return self._json(runs.start(only))
            except (VirtulabError, KeyError, ValueError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    return Handler


def serve(root: Path, port: int = 8765, open_browser: bool = True) -> int:
    root.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(16)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(root, token))
    except OSError as exc:
        raise VirtulabError(f"Cannot listen on 127.0.0.1:{port} ({exc}). Try --port.") from None
    url = f"http://127.0.0.1:{server.server_port}/#token={token}"
    print(f"🧭 VirtuLab setup page for {root}\n   {url}\n   Press Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0
