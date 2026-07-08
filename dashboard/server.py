#!/usr/bin/env python3
"""Zero-dependency dashboard + control server.

Stdlib only. Serves results, live status, cross-run comparison, group
descriptions, API-profile management, and a launch endpoint.

Routes:
    GET  /                         UI
    GET  /style.css /app.js        static
    GET  /api/runs                 list run metadata
    GET  /api/run/<tag>            summary.json
    GET  /api/run/<tag>/results    per-call records
    GET  /api/status               live: running process, log tail, progress
    GET  /api/compare?tags=...     cross-run group metrics
    GET  /api/groups               group ids + names + descriptions
    GET  /api/profiles             saved API profiles (keys masked)
    POST /api/profiles             add/update a profile {name, base_url, api_key, model}
    DELETE /api/profiles?name=...  remove a profile
    POST /api/launch               {profile, groups, n_keys, ...} -> spawn run
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
CONFIG_YAML = ROOT / "config" / "config.yaml"
PROFILES_YAML = ROOT / "config" / "api_profiles.yaml"
DASH_DIR = Path(__file__).resolve().parent
LOG_FILE = Path("/tmp/pi_run.log")
HOST, PORT = "127.0.0.1", 8765

# ---- 模块系统 ----
sys.path.insert(0, str(ROOT))
from core.registry import discover_modules, list_modules as _list_mods  # noqa: E402
_MODULES = discover_modules()

# 收集所有模块的条件 (供 launch form) + 分组元数据 (供 task composer)
_ALL_CONDITIONS: list[dict] = []
_MODULE_GROUPS: dict[str, list[dict]] = {}  # module_id -> old-style group list
_MODULE_MAP: dict[str, str] = {}  # condition_id -> module_id
for _mid, _mod in _MODULES.items():
    for _c in _mod.build_conditions():
        params = _c.params if isinstance(_c.params, dict) else {}
        _ALL_CONDITIONS.append({
            "id": _c.id, "name": _c.name, "module_id": _mid,
            **{k:v for k,v in params.items() if k in ("color","desc","position","composable")}
        })
        _MODULE_MAP[_c.id] = _mid
    # 从 launch config 读 features (兼容旧 get_groups)
    spec = _mod.get_spec() if hasattr(_mod, "get_spec") else {}
    launch = spec.get("launch") or {}
    _MODULE_GROUPS[_mid] = launch.get("features", [])


# ---- 数据 (兼容旧 runs/<tag>/ 和 新 runs/<module>/<tag>/ 两种格式) ----
def _normalize_summary(data: dict, run_dir: str = "") -> dict:
    """统一新旧格式。旧格式(PI release)自动补 module_id, 映射 groups→conditions."""
    if "module_id" in data:
        return data  # 新格式
    # 旧 PI release 格式
    groups = data.get("groups", [])
    conditions = []
    for g in groups:
        conditions.append({
            "condition_id": g.get("id", g.get("name", "?")),
            "condition_name": g.get("name", g.get("id", "?")),
            "accuracy": g.get("accuracy"),
            "re": g.get("re"),
            "cp": g.get("cp"),
            "robustness_delta": g.get("robustness_delta"),
            "n": g.get("n_calls", g.get("n_trials", 0)),
        })
    return {
        "module_id": "pi_release",
        "module_name": "PI Release 实验",
        "tag": data.get("tag", Path(run_dir).name if run_dir else ""),
        "model": data.get("model", "?"),
        "baseline_acc": data.get("baseline_acc"),
        "pi_test": data.get("pi_test", {}),
        "conditions": conditions,
        "n_trials": (data.get("pi_test") or {}).get("n_trials", 0),
        "k_repeats": (data.get("eval") or {}).get("k_repeats", 0),
        "_legacy": True,
    }


def _list_runs() -> list[dict]:
    out = []
    if not RUNS_DIR.exists():
        return out

    def _collect(base: Path, module_id: str):
        for run_dir in sorted(base.iterdir(), reverse=True):
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            s = run_dir / "summary.json"
            if not s.exists():
                continue
            try:
                data = json.loads(s.read_text(encoding="utf-8"))
            except Exception:
                continue
            data = _normalize_summary(data, str(run_dir))
            data.setdefault("module_id", module_id)
            out.append({
                "tag": data.get("tag", run_dir.name),
                "module_id": data.get("module_id", module_id),
                "module_name": data.get("module_name", ""),
                "model": data.get("model", "?"),
                "baseline_acc": data.get("baseline_acc"),
                "n_conditions": len(data.get("conditions", [])),
                "n_calls": sum(c.get("n", 0) for c in data.get("conditions", [])),
                "run_dir": str(run_dir.relative_to(ROOT)),
            })

    # 新格式: runs/<module_id>/<tag>/
    for mod_dir in sorted(RUNS_DIR.iterdir()):
        if mod_dir.is_dir() and not mod_dir.name.startswith("."):
            _collect(mod_dir, mod_dir.name)

    # 旧格式: runs/<tag>/ (direct)
    for d in sorted(RUNS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and (d / "summary.json").exists():
            # 检查是否已被新格式覆盖
            already = any(str(d.relative_to(ROOT)).startswith(str(md.relative_to(ROOT)))
                         for md in RUNS_DIR.iterdir() if md.is_dir() and md != d)
            if not already:
                _collect(RUNS_DIR, "pi_release")
                break  # only scan once for legacy dirs

    return out


def _load_summary(run_dir: str) -> dict | None:
    p = ROOT / run_dir / "summary.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return _normalize_summary(data, run_dir)


def _load_results(run_dir: str, limit: int = 2000) -> list[dict]:
    p = ROOT / run_dir / "results.jsonl"
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
    """PIDs of live launch.py processes."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,stat=,command="], capture_output=True, text=True, timeout=2
        ).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, stat, cmd = parts
        if "Z" in stat:  # zombie / defunct — already dead
            continue
        low = cmd.lower()
        if "launch.py" in cmd and "python" in low and "--dashboard" not in cmd:
    return pids


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

    latest_tag, records, total = None, 0, None
    if RUNS_DIR.exists():
        subs = [d for d in RUNS_DIR.iterdir() if d.is_dir()]
        if subs:
            ld = max(subs, key=lambda d: d.stat().st_mtime)
            latest_tag = ld.name
            rf = ld / "results.jsonl"
            if rf.exists():
                records = sum(1 for _ in open(rf, "r", encoding="utf-8"))
            try:
                rc = json.loads((ld / "run_config.json").read_text(encoding="utf-8"))
                total = rc.get("planned_total")
            except Exception:
                pass

    current_group = None
    for line in reversed(log_tail.splitlines()):
        m = re.search(r"=== (?:Group|Task) (\S+)", line)
        if m:
            current_group = m.group(1).split("(")[0].strip()
            break

    return {
        "running": running, "pids": pids, "current_group": current_group,
        "latest_run": latest_tag, "records_done": records,
        "records_total": total, "log_tail": log_tail,
    }


def _force_stop() -> dict:
    """Force-kill any running launch.py and delete the newest (incomplete) run dir."""
    pids = _find_runner_pids()
    killed = []
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
            killed.append(pid)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
    deleted = None
    if RUNS_DIR.exists():
        subs = [d for d in RUNS_DIR.iterdir() if d.is_dir()]
        if subs:
            ld = max(subs, key=lambda d: d.stat().st_mtime)
            incomplete = not (ld / "summary.json").exists()
            if pids or incomplete:  # a run was in progress, or a partial folder lingers
                shutil.rmtree(ld, ignore_errors=True)
                deleted = ld.name
    return {"ok": True, "killed": killed, "deleted": deleted}


# ----------------------------- compare -----------------------------

def _compare(tags: list[str]) -> dict:
    out = {}
    for tag in tags:
        s = _load_summary(tag)
        if s is None: continue
        # 兼容新旧格式: conditions (新) 或 groups (旧)
        items = s.get("conditions") or s.get("groups") or []
        groups = {}
        for g in items:
            gid = g.get("condition_id") or g.get("id") or "?"
            groups[gid] = {
                "id": gid,
                "accuracy": g.get("accuracy"),
                "re": g.get("re"),
                "cp": g.get("cp"),
                "robustness_delta": g.get("robustness_delta"),
            }
        out[tag] = {
            "tag": s.get("tag", tag.split("/")[-1]),
            "model": s.get("model"),
            "baseline_acc": s.get("baseline_acc"),
            "pi_test": s.get("pi_test", {}),
            "groups": groups,
        }
    return out


# ----------------------------- API profiles -----------------------------

def _mask_key(k: str) -> str:
    k = str(k or "")
    if len(k) <= 8:
        return "***"
    return k[:4] + "***" + k[-4:]


def _load_profiles() -> list[dict]:
    if not PROFILES_YAML.exists():
        return []
    try:
        data = yaml.safe_load(PROFILES_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    return data.get("profiles", []) if isinstance(data, dict) else []


def _save_profiles(profiles: list[dict]) -> None:
    PROFILES_YAML.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_YAML.write_text(
        yaml.safe_dump({"profiles": profiles}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _seed_profiles_from_config() -> None:
    """If no profiles exist yet, seed one from the current config.yaml."""
    if _load_profiles():
        return
    if not CONFIG_YAML.exists():
        return
    try:
        cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return
    base_url = cfg.get("base_url") or ""
    api_key = cfg.get("api_key") or ""
    model = cfg.get("model") or ""
    if not (base_url and api_key and model):
        return
    name = "default"
    # derive a short name from host's registrable segment (api.deepseek.com -> deepseek)
    m = re.search(r"://([^/]+)", base_url)
    if m:
        parts = m.group(1).split(".")
        name = parts[-2] if len(parts) >= 2 else m.group(1)
    _save_profiles([{
        "name": name, "base_url": base_url, "api_key": api_key, "model": model,
        "extra_body": cfg.get("extra_body") or {},
    }])


def _apply_profile_to_config(profile: dict) -> None:
    """Write the chosen profile's base_url/api_key/model into config.yaml so
    launch.py (which reads config.yaml) uses them. Preserves other fields
    like extra_body; comments are lost on rewrite."""
    CONFIG_YAML.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CONFIG_YAML.exists():
        try:
            data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data["base_url"] = profile["base_url"]
    data["api_key"] = profile["api_key"]
    data["model"] = profile["model"]
    eb = profile.get("extra_body")
    if eb:
        data["extra_body"] = eb
    else:
        data.pop("extra_body", None)
    CONFIG_YAML.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ----------------------------- launch -----------------------------

def _launch(body: dict) -> dict:
    if _find_runner_pids():
        return {"launched": False, "error": "已有 run 在跑,请等它结束"}

    # resolve profile -> write into config.yaml
    profiles = _load_profiles()
    pname = body.get("profile")
    profile = next((p for p in profiles if p["name"] == pname), None)
    if profile is None:
        profile = {"name": "(current config)", "base_url": None, "api_key": None, "model": None}
    else:
        _apply_profile_to_config(profile)

    py = str(ROOT / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable

    module_id = body.get("module_id", "pi_release")
    conditions = body.get("conditions", [])
    if not conditions:
        return {"launched": False, "error": "no conditions selected"}

    args = [py, str(ROOT / "launch.py"), "--module", module_id, "--conditions"] + conditions

    if profile.get("model"):
        args += ["--model", str(profile["model"])]
    for key, cli in [("n_trials", "--trials"), ("k_repeats", "--repeats"), ("seed", "--seed")]:
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
    return {"launched": True, "profile": profile.get("name"),
            "model": profile.get("model"), "module_id": module_id,
            "conditions": conditions}


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

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or "{}")
        except Exception:
            return {}

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
        elif p == "/api/modules":
            self._send_json(200, _list_mods())
        elif p.startswith("/api/spec/"):
            mid = p.split("/")[-1]
            mod = _MODULES.get(mid)
            if mod:
                self._send_json(200, mod.get_spec())
            else:
                self._send_json(404, {"error": f"module {mid} not found"})
        elif p == "/api/groups":
            mid = qs.get("module", [""])[0] or "pi_release"
            conds = [c for c in _ALL_CONDITIONS if c["module_id"] == mid] if mid else _ALL_CONDITIONS
            groups = _MODULE_GROUPS.get(mid, [])
            self._send_json(200, {"groups": groups, "conditions": conds, "modules": _list_mods()})
        elif p == "/api/profiles":
            profiles = [{**p, "api_key": _mask_key(p.get("api_key"))}
                        for p in _load_profiles()]
            self._send_json(200, {"profiles": profiles})
        elif p == "/api/compare":
            tags = [t for t in qs.get("tags", [""])[0].split(",") if t]
            self._send_json(200, _compare(tags))
        elif p.startswith("/api/run/"):
            parts = p.rstrip("/").split("/")
            # runs/<module_id>/<tag> → parts[3]=module_id, parts[4]=tag
            run_dir_parts = parts[3:]
            run_path = "/".join(run_dir_parts)
            if p.endswith("/results"):
                run_path = "/".join(run_dir_parts[:-1])
                self._send_json(200, _load_results(run_path))
            else:
                s = _load_summary(run_path)
                self._send_json(200, s if s else {"error": "run not found"})
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):  # noqa: N802
        p = urlparse(self.path).path
        if p == "/api/launch":
            self._send_json(200, _launch(self._read_body()))
        elif p == "/api/force-stop":
            self._send_json(200, _force_stop())
        elif p == "/api/profiles":
            body = self._read_body()
            name = (body.get("name") or "").strip()
            if not name or not body.get("base_url") or not body.get("api_key"):
                self._send_json(400, {"ok": False, "error": "name / base_url / api_key 不能为空"})
                return
            profiles = _load_profiles()
            profiles = [pp for pp in profiles if pp.get("name") != name]  # replace if exists
            # parse optional extra_body (YAML string -> dict), e.g. "thinking:\n  type: disabled"
            extra_yaml = (body.get("extra_body") or "").strip()
            extra_body = {}
            if extra_yaml:
                try:
                    parsed = yaml.safe_load(extra_yaml)
                except Exception as e:
                    self._send_json(400, {"ok": False, "error": f"额外参数 YAML 解析失败:{e}"})
                    return
                if not isinstance(parsed, dict):
                    self._send_json(400, {"ok": False, "error": "额外参数必须是 YAML dict(如 thinking:\\n  type: disabled)"})
                    return
                extra_body = parsed
            profiles.append({
                "name": name,
                "base_url": body["base_url"].strip(),
                "api_key": body["api_key"].strip(),
                "model": (body.get("model") or "").strip(),
                "extra_body": extra_body,
            })
            _save_profiles(profiles)
            self._send_json(200, {"ok": True, "name": name})
        else:
            self._send(404, b"Not found", "text/plain")

    def do_DELETE(self):  # noqa: N802
        p = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if p == "/api/profiles":
            name = (qs.get("name", [""])[0]).strip()
            profiles = [pp for pp in _load_profiles() if pp.get("name") != name]
            _save_profiles(profiles)
            self._send_json(200, {"ok": True, "deleted": name})
        else:
            self._send(404, b"Not found", "text/plain")

    def log_message(self, *args):
        pass


def main(open_browser: bool = True):
    # auto-reap spawned launch.py children so they don't linger as zombies
    # (a zombie would still match the running-process check and block launches)
    import signal
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    except (ValueError, OSError):
        pass  # not main thread / unsupported

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _seed_profiles_from_config()  # first run: import current config.yaml as a profile
    n = len(_list_runs())
    print(f"[dashboard] {n} run(s), {len(_load_profiles())} profile(s)", file=sys.stderr)
    print(f"[dashboard] serving on http://{HOST}:{PORT}", file=sys.stderr)
    if open_browser:
        try:
            webbrowser.open(f"http://{HOST}:{PORT}")
        except Exception:
            pass
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    main(open_browser=not args.no_browser)
