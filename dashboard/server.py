#!/usr/bin/env python3
"""Zero-dependency dashboard server.

Serves the experiment results to a local web dashboard.
Uses only the Python standard library (http.server) — no Flask/FastAPI needed.

    python dashboard/server.py
    # then open http://localhost:8765

Routes:
    GET /                         -> dashboard UI (index.html)
    GET /style.css /app.js        -> static assets
    GET /api/runs                 -> list of all runs (metadata)
    GET /api/run/<tag>            -> full summary.json for a run
    GET /api/run/<tag>/results    -> raw per-call records (jsonl -> json array)
"""
from __future__ import annotations

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
DASH_DIR = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", 8765


def _list_runs() -> list[dict]:
    out = []
    if not RUNS_DIR.exists():
        return out
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        s = d / "summary.json"
        if not s.exists():
            continue
        try:
            data = json.loads(s.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "tag": data.get("tag", d.name),
            "model": data.get("model", "?"),
            "baseline_acc": data.get("baseline_acc"),
            "n_groups": len(data.get("groups", [])),
            "n_calls": sum(g.get("n_calls", 0) for g in data.get("groups", [])),
        })
    return out


def _load_summary(tag: str) -> dict | None:
    p = RUNS_DIR / tag / "summary.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _load_results(tag: str, limit: int = 2000) -> list[dict]:
    p = RUNS_DIR / tag / "results.jsonl"
    if not p.exists():
        return []
    rows = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
            if len(rows) >= limit:
                break
    return rows


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _send_file(self, path: Path, ctype: str):
        if not path.exists() or not path.is_file():
            self._send(404, b"Not found", "text/plain")
            return
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._send_file(DASH_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self._send_file(DASH_DIR / "style.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_file(DASH_DIR / "app.js", "application/javascript; charset=utf-8")
        elif path == "/api/runs":
            self._send_json(200, _list_runs())
        elif path.startswith("/api/run/"):
            parts = path.rstrip("/").split("/")
            # /api/run/<tag> or /api/run/<tag>/results
            tag = parts[3] if len(parts) > 3 else ""
            if len(parts) >= 5 and parts[4] == "results":
                self._send_json(200, _load_results(tag))
            else:
                s = _load_summary(tag)
                if s is None:
                    self._send_json(404, {"error": "run not found"})
                else:
                    self._send_json(200, s)
        else:
            self._send(404, b"Not found", "text/plain")

    def log_message(self, *args):  # silence default logging
        pass


def main(open_browser: bool = True):
    if not RUNS_DIR.exists():
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = len(_list_runs())
    print(f"[dashboard] {n} run(s) found under {RUNS_DIR}", file=sys.stderr)
    url = f"http://{HOST}:{PORT}"
    print(f"[dashboard] serving on {url}", file=sys.stderr)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    main(open_browser=not args.no_browser)
