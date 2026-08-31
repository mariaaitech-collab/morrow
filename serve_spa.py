import json
import os
from urllib.parse import urlparse
from urllib.request import Request as URequest, urlopen
from urllib.error import HTTPError, URLError
from http.server import SimpleHTTPRequestHandler, HTTPServer

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist"))
BACKEND = "http://127.0.0.1:8000"


class SPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # ---- API proxy (so the built app can reach FastAPI on :8000) ----
    def _proxy(self):
        target = BACKEND + self.path
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else None
        fwd = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
        req = URequest(target, data=body, headers=fwd, method=self.command)
        try:
            with urlopen(req, timeout=20) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(k, v)
                self.end_headers()
                if data:
                    self.wfile.write(data)
        except HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data if data else b"{}")
        except (URLError, Exception) as e:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "detail": "Brandora backend (%s) is not running. Start it first, then try again." % BACKEND
            }).encode())

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return self._serve_spa()

    def end_headers(self):
        # Never let the browser cache the SPA shell or assets. A stale
        # cached index.html would reference old hashed bundles that no
        # longer exist, leaving the app blank. Always fetch fresh.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_POST(self):
        return self._proxy()

    def do_PUT(self):
        return self._proxy()

    def do_PATCH(self):
        return self._proxy()

    def do_DELETE(self):
        return self._proxy()

    def do_OPTIONS(self):
        return self._proxy()

    def _serve_spa(self):
        path = urlparse(self.path).path
        file_path = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if path != "/" and os.path.isfile(file_path):
            return super().do_GET()
        if "." in os.path.basename(path):
            return super().do_GET()
        self.path = "/index.html"
        return super().do_GET()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5173))
    print(f"SPA preview serving {ROOT} on http://127.0.0.1:{port} (proxying /api -> {BACKEND})")
    HTTPServer(("127.0.0.1", port), SPAHandler).serve_forever()
