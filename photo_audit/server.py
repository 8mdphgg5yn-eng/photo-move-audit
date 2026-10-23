"""Token-protected loopback UI; no uploads or remote requests."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import tempfile
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .core import audit, report_html, validate_roots
from .demo import make_demo
from . import __version__, picker

WEB = Path(__file__).parent / "web"


class App:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.jobs = {}
        self.lock = threading.Lock()
        self.picker_lock = threading.Lock()
        self.demo_directory = tempfile.TemporaryDirectory(prefix="photo-audit-demo-")
        self.demo = None

    def close(self):
        for job in self.jobs.values():
            job["cancel"].set()
        self.demo_directory.cleanup()

    def start(self, source, target):
        source, target = validate_roots(source, target)
        with self.lock:
            if any(j["state"] == "running" for j in self.jobs.values()):
                raise ValueError("已有核对正在运行，请等待结束或先停止")
            # Keep one result in memory; reports are downloaded explicitly.
            self.jobs.clear()
            key = secrets.token_hex(8)
            job = {"id": key, "state": "running", "progress": {},
                   "source": str(source), "target": str(target),
                   "cancel": threading.Event(), "report": None}
            self.jobs[key] = job

        def progress(event):
            with self.lock:
                job["progress"] = event

        def run():
            try:
                result = audit(source, target, cancel=job["cancel"], progress=progress)
                with self.lock:
                    job["report"] = result
                    job["state"] = "done"
            except Exception as exc:
                with self.lock:
                    job["error"] = str(exc)
                    job["state"] = "error"

        threading.Thread(target=run, daemon=True).start()
        return key


def make_server(port=0):
    app = App()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"PhotoAudit/{__version__}"

        def log_message(self, *_):
            pass

        def reply(self, status, data, kind="application/json; charset=utf-8", filename=None):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            elif isinstance(data, str):
                data = data.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def allowed(self, require_token=False):
            authority = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != authority:
                self.reply(403, {"error": "仅接受本机地址"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{authority}":
                self.reply(403, {"error": "拒绝跨站请求"})
                return False
            supplied = self.headers.get("X-Photo-Audit-Token", "").encode("utf-8")
            if require_token and not secrets.compare_digest(supplied, app.token.encode("ascii")):
                self.reply(403, {"error": "会话已过期，请用终端显示的完整地址重新打开"})
                return False
            return True

        def do_GET(self):
            url = urlsplit(self.path)
            if not self.allowed(url.path.startswith("/api/")):
                return
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if url.path in static:
                name, kind = static[url.path]
                self.reply(200, (WEB / name).read_bytes(), kind)
                return
            if url.path == "/api/session":
                with app.lock:
                    job = next(iter(app.jobs.values()), None)
                    latest = {field: job[field] for field in ("id", "state", "source", "target")} if job else None
                self.reply(200, {"version": __version__, "native_picker": picker.available(), "latest": latest})
                return
            parts = url.path.strip("/").split("/")
            if len(parts) < 3 or parts[:2] != ["api", "jobs"]:
                self.reply(404, {"error": "没有这个地址"})
                return
            with app.lock:
                job = app.jobs.get(parts[2])
                if job is None:
                    self.reply(404, {"error": "核对记录不存在"})
                    return
                report = job["report"]
                status = {"id": job["id"], "state": job["state"],
                          "source": job["source"], "target": job["target"],
                          "progress": job["progress"], "error": job.get("error")}
                if report:
                    status["summary"] = report["summary"]
                    status["source_stats"] = report["source"]["stats"]
                    status["target_stats"] = report["target"]["stats"]
                    status["scope"] = report["scope"]
            if len(parts) == 3:
                self.reply(200, status)
            elif report and parts[3] == "report.json":
                self.reply(200, report, filename="photo-audit-report.json")
            elif report and parts[3] == "report.html":
                # Standalone report uses its own inline style; it contains no scripts.
                self.reply(200, report_html(report), "text/html; charset=utf-8", "photo-audit-report.html")
            elif report and parts[3] == "items":
                params = parse_qs(url.query)
                kind = params.get("kind", ["missing"])[0]
                if kind not in ("missing", "extras", "duplicates", "issues"):
                    self.reply(400, {"error": "未知列表类型"})
                    return
                try:
                    page = max(0, int(params.get("page", ["0"])[0]))
                except ValueError:
                    self.reply(400, {"error": "页码无效"})
                    return
                entries = report[kind]
                self.reply(200, {"total": len(entries), "page": page,
                                 "items": entries[page * 50:(page + 1) * 50]})
            else:
                self.reply(404, {"error": "报告尚未生成或地址不存在"})

        def do_POST(self):
            if not self.allowed(True):
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16_384:
                    self.reply(400, {"error": "请求大小无效"})
                    return
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("请求必须为对象")
                path = urlsplit(self.path).path
                if path == "/api/pick":
                    if not app.picker_lock.acquire(blocking=False):
                        raise ValueError("已有选择窗口打开，请先完成或取消")
                    try:
                        if data.get("initial_directory") is not None and not isinstance(data["initial_directory"], str):
                            raise ValueError("起始目录须为路径文字")
                        selected = picker.choose_path(data.get("kind"), data.get("initial_directory"))
                    finally:
                        app.picker_lock.release()
                    self.reply(200, {"path": selected, "cancelled": selected is None})
                elif path == "/api/demo":
                    with app.lock:
                        if app.demo is None:
                            app.demo = make_demo(app.demo_directory.name)
                    self.reply(200, {"source": app.demo[0], "target": app.demo[1]})
                elif path == "/api/jobs":
                    if not isinstance(data.get("source"), str) or not isinstance(data.get("target"), str):
                        raise ValueError("请填写来源和目标路径")
                    self.reply(202, {"id": app.start(data["source"], data["target"])})
                elif path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    key = path.split("/")[3]
                    with app.lock:
                        job = app.jobs.get(key)
                        if job is None:
                            self.reply(404, {"error": "核对记录不存在"})
                            return
                        job["cancel"].set()
                    self.reply(200, {"ok": True})
                else:
                    self.reply(404, {"error": "没有这个地址"})
            except (ValueError, OSError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except Exception:
        app.close()
        raise
    server.app = app
    return server


def serve(port=0, open_browser=True):
    server = make_server(port)
    url = f"http://127.0.0.1:{server.server_port}/#{server.app.token}"
    print(f"照片搬家核对器：{url}\n仅本机访问。按 Ctrl+C 结束。", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.app.close()
