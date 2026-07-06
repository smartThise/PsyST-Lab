#!/usr/bin/env python3
"""Zero-dependency dashboard + control server.

Stdlib only (http.server). Serves results, live run status, cross-run
comparison, and a launch endpoint to start runs from the UI.

    python dashboard/server.py
    # open http://localhost:8765

Routes:
    GET  /                           UI (index.html)
    GET  /style.css /app.js          static
    GET  /api/runs                   list run metadata
    GET  /api/run/<tag>              summary.json
    GET  /api/run/<tag>/results      per-call records (jsonl -> array)
    GET  /api/status                 live: running process, log tail, progress
    GET  /api/compare?tags=a,b,...   cross-run group metrics
    GET  /api/groups                 known group IDs (for launch form)
    POST /api/launch                 launch a run {model, groups, n_keys, ...}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
DASH_DIR = Path(__file__).resolve().parent
LOG_FILE = Path("/tmp/pi_run.log")
HOST, PORT = "127.0.0.1", 8765

# groups the launch form can pick from (must match src/groups.py REGISTRY)
KNOWN_GROUPS = ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "S3", "S5"]


# ----------------------------- data helpers -----------------------------

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
            "pi_test": data.get("pi_test", {}),
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


# ----------------------------- live status -----------------------------

def _find_runner_pids() -> list[str]:
    try:
        out = subprocess.run(
            ["pgrep", "-f", "run_all.py"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        return [p for p in out.split() if p]
    except Exception:
        return []


def _status() -> dict:
    pids = _find_runner_pids()
    running = bool(pids)

    log_tail = ""
    if LOG_FILE.exists():
        try:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = "\n".join(lines[-40:])
        except Exception:
            pass

    # latest run dir + its record count
    latest_tag, records, total = None, 0, None
    if RUNS_DIR.exists():
        subs = [d for d in RUNS_DIR.iterdir() if d.is_dir()]
        if subs:
            ld = max(subs, key=lambda d: d.stat().st_mtime)
            latest_tag = ld.name
            rf = ld / "results.jsonl"
            if rf.exists():
                records = sum(1 for _ in open(rf, "r", encoding="utf-8"))
            # planned total from the latest run's run_config.json (reflects overrides + filters)
            try:
                rc = json.loads((ld / "run_config.json").read_text(encoding="utf-8"))
                total = rc.get("planned_total")
            except Exception:
                pass

    # current group from log
    current_group = None
    for line in reversed(log_tail.splitlines()):
        m = re.search(r"=== Group (\S+)", line)
        if m:
            current_group = m.group(1).split("(")[0].strip()
            break

    return {
        "running": running,
        "pids": pids,
        "current_group": current_group,
        "latest_run": latest_tag,
        "records_done": records,
        "records_total": total,
        "log_tail": log_tail,
    }


# ----------------------------- compare -----------------------------

def _compare(tags: list[str]) -> dict:
    out = {}
    for tag in tags:
        s = _load_summary(tag)
        if s is None:
            continue
        out[tag] = {
            "tag": tag,
            "model": s.get("model"),
            "baseline_acc": s.get("baseline_acc"),
            "pi_test": s.get("pi_test", {}),
            "groups": {g["id"]: g for g in s.get("groups", [])},
        }
    return out


# ----------------------------- launch -----------------------------

def _launch(body: dict) -> dict:
    if _find_runner_pids():
        return {"launched": False, "error": "a run is already running; wait for it to finish"}
    groups = [g for g in body.get("groups", []) if g in KNOWN_GROUPS]
    if not groups:
        return {"launched": False, "error": "no valid groups selected"}

    py = str(ROOT / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable
    args = [py, str(ROOT / "scripts" / "run_all.py"), "--groups"] + groups
    if body.get("model"):
        args += ["--model", str(body["model"])]
    for key, cli in [("n_keys", "--n-keys"), ("updates_per_key", "--updates"),
                     ("n_trials", "--trials"), ("k_repeats", "--k-repeats")]:
        v = body.get(key)
        if v is not None and v != "":
            try:
                args += [cli, str(int(v))]
            except (ValueError, TypeError):
                pass

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(LOG_FILE, "w")
    subprocess.Popen(
        args, cwd=str(ROOT), stdout=log_fp, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {"launched": True, "args": args, "groups": groups}


# ----------------------------- handler -----------------------------

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
        p = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)

        if p in ("/", "/index.html"):
            self._send_file(DASH_DIR / "index.html", "text/html; charset=utf-8")
        elif p == "/style.css":
            self._send_file(DASH_DIR / "style.css", "text/css; charset=utf-8")
        elif p == "/app.js":
            self._send_file(DASH_DIR / "app.js", "application/javascript; charset=utf-8")
        elif p == "/api/runs":
            self._send_json(200, _list_runs())
        elif p == "/api/status":
            self._send_json(200, _status())
        elif p == "/api/groups":
            self._send_json(200, {"groups": KNOWN_GROUPS})
        elif p == "/api/compare":
            tags = [t for t in qs.get("tags", [""])[0].split(",") if t]
            self._send_json(200, _compare(tags))
        elif p.startswith("/api/run/"):
            parts = p.rstrip("/").split("/")
            tag = parts[3] if len(parts) > 3 else ""
            if len(parts) >= 5 and parts[4] == "results":
                self._send_json(200, _load_results(tag))
            else:
                s = _load_summary(tag)
                self._send_json(200, s if s else {"error": "run not found"})
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):  # noqa: N802
        p = urlparse(self.path).path
        if p == "/api/launch":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or "{}")
            except Exception:
                body = {}
            self._send_json(200, _launch(body))
        else:
            self._send(404, b"Not found", "text/plain")

    def log_message(self, *args):
        pass


def main(open_browser: bool = True):
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
