"""
Local review GUI for staging crawl diffs — a git-diff-style approval page.

Flow:
    uv run script/crawl_heroes.py --detail --staging
    uv run script/review_server.py            # open http://127.0.0.1:8765
    (approve / edit / apply in the browser)
    uv run script/llm_translate.py --batch-size 10 --parallel 3
    npm run data

Endpoints:
    GET  /          — review_ui.html
    GET  /api/diff  — recompute staging-vs-current diff, return JSON
    POST /api/apply — apply decisions via merge_crawl.apply_decisions
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import diff_crawl
import merge_crawl

UI_PATH = Path(__file__).parent / "review_ui.html"
DEFAULT_PORT = 8765


class ReviewHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/diff":
            try:
                diff = diff_crawl.compute_diff()
                diff_crawl.write_diff(diff)
                self._send_json(200, diff)
            except FileNotFoundError as e:
                self._send_json(404, {"error": str(e)})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/apply":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            decisions = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as e:
            self._send_json(400, {"ok": False, "errors": [f"bad JSON: {e}"]})
            return
        try:
            result = merge_crawl.apply_decisions(decisions)
        except Exception as e:  # surface merge bugs to the UI, keep server up
            self._send_json(500, {"ok": False, "errors": [f"apply crashed: {e}"]})
            return
        self._send_json(200, result)

    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), ReviewHandler)
    print(f"[review] http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[review] stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
