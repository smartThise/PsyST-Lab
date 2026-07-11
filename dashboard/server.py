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
            **{k:v for k,v in params.items() if k in ("color","desc","position","composable","group","group_label","rpi_expected","mode","block")}
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

def _find_runners() -> list[dict]:
    """返回正在运行的 launch.py 进程: [{pid, module_id}, ...]"""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,stat=,command="], capture_output=True, text=True, timeout=2
        ).stdout
    except Exception:
        return []
    runners = []
    for line in out.splitlines():
        line = line.strip()
        if not line: continue
        parts = line.split(None, 2)
        if len(parts) < 3: continue
        pid, stat, cmd = parts
        if "Z" in stat: continue
        if "python" not in cmd.lower(): continue
        if "--dashboard" in cmd: continue
        if "launch.py" not in cmd and "resume_run.py" not in cmd: continue
        # 提取模块名: launch.py用-m/--module, resume_run.py从路径 runs/<module>/ 提取
        mid = ""
        m = re.search(r"(?:--module|-m)\s+(\S+)", cmd)
        if m:
            mid = m.group(1)
        else:
            m = re.search(r"runs/(\w+)/", cmd)
            if m: mid = m.group(1)
        runners.append({"pid": pid, "module_id": mid})
    return runners


def _status(module_id: str = "") -> dict:
    all_runners = _find_runners()
    # 该模块是否在运行
    my_runners = [r for r in all_runners if not module_id or r["module_id"] == module_id]
    running = bool(all_runners) if not module_id else bool(my_runners)
    pids = [r["pid"] for r in my_runners]

    # 读最新 run 的日志和进度
    log_tail = ""
    latest_tag, latest_module, records, total = None, "", 0, None
    if RUNS_DIR.exists():
        best_mtime = 0
        for mod_dir in RUNS_DIR.iterdir():
            if not mod_dir.is_dir() or mod_dir.name.startswith("."):
                continue
            if module_id and mod_dir.name != module_id:
                continue
            for run_dir in mod_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                mt = run_dir.stat().st_mtime
                if mt > best_mtime:
                    best_mtime = mt
                    latest_tag = run_dir.name
                    latest_module = mod_dir.name
                    # 读 run.log
                    lf = run_dir / "run.log"
                    if lf.exists():
                        try:
                            lines = lf.read_text(encoding="utf-8", errors="replace").splitlines()
                            log_tail = "\n".join(lines[-40:])
                        except Exception: pass
                    rf = run_dir / "results.jsonl"
                    if rf.exists():
                        records = sum(1 for _ in open(rf, "r", encoding="utf-8"))
                    try:
                        rc = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
                        total = rc.get("planned_total")
                    except Exception: pass

    current_group = None
    for line in reversed(log_tail.splitlines()):
        # old format: "=== Group G4+G2+G8s (...)"
        m = re.search(r"===\s*(?:Group|Task)\s+(\S+)", line)
        # new format: "  [5/36] WN_exp: rpi=0.85 ..."
        if not m:
            m = re.search(r"\]\s+(\S+):", line)
        if m:
            current_group = m.group(1).split("(")[0].strip()
            break

    return {
        "running": running, "running_modules": list(set(r["module_id"] for r in all_runners if r["module_id"])),
        "pids": pids, "current_group": current_group,
        "latest_run": latest_module + "/" + latest_tag if latest_module else latest_tag,
        "records_done": records, "records_total": total, "log_tail": log_tail,
    }


def _force_stop(module_id: str = "") -> dict:
    """Force-kill 该模块的实验进程 (从 PID 文件读, 不猜 ps)."""
    killed = []
    # 读 PID 文件
    pid_file = RUNS_DIR / f".pid_{module_id}" if module_id else None
    if pid_file and pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGKILL)
            killed.append(str(pid))
            pid_file.unlink()
        except Exception:
            pass
    # 删除最新未完成的 run
    deleted = None
    try:
        if module_id and RUNS_DIR.exists():
            mod_dir = RUNS_DIR / module_id
            if mod_dir.is_dir():
                run_dirs = [d for d in mod_dir.iterdir() if d.is_dir()]
                if run_dirs:
                    ld = max(run_dirs, key=lambda d: d.stat().st_mtime)
                    if not (ld / "summary.json").exists():
                        shutil.rmtree(ld, ignore_errors=True)
                        deleted = str(ld.relative_to(RUNS_DIR))
    except Exception:
        pass
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

def _get_mechanism_url() -> str:
    """从 profiles 里找本地服务器的 URL (去掉 /v1)."""
    profiles = _load_profiles()
    for p in profiles:
        bu = p.get("base_url", "")
        if "192.168" in bu or "localhost" in bu or "127.0.0.1" in bu:
            return bu.rstrip("/v1")
    return ""


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
    module_id = body.get("module_id", "pi_release")
    runners = _find_runners()
    same_mod = [r for r in runners if r["module_id"] == module_id]
    if same_mod:
        return {"launched": False, "error": f"模块 {module_id} 已有 run 在跑,等它结束. 其他模块可并行."}

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

    conditions = body.get("conditions", [])
    is_sweep = bool(body.get("updates_list", ""))
    has_tasks = bool(body.get("tasks"))
    if not is_sweep and not has_tasks and not conditions:
        return {"launched": False, "error": "no conditions selected"}

    args = [py, str(ROOT / "launch.py"), "--module", module_id]
    tasks = body.get("tasks")
    if tasks:
        tasks_file = ROOT / "runs" / ".tasks_pending.json"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(json.dumps(tasks), encoding="utf-8")
        args += ["--tasks-file", str(tasks_file)]
    elif conditions:
        args += ["--conditions"] + conditions

    if profile.get("model"):
        args += ["--model", str(profile["model"])]
    _STR_ARGS = {"updates_list", "strategy", "positions"}
    for key, cli in [("n_trials", "--trials"), ("k_repeats", "--repeats"), ("seed", "--seed"),
                     ("n_back", "--n-back"), ("updates_list", "--updates-list"),
                     ("strategy", "--strategy"), ("positions", "--positions")]:
        v = body.get(key)
        if v is not None and v != "":
            try:
                args += [cli, str(v) if key in _STR_ARGS else str(int(v))]
            except (ValueError, TypeError):
                pass

    proc = subprocess.Popen(
        args, cwd=str(ROOT), start_new_session=True,
    )
    # 记 PID 到文件 (供 force stop 精准 kill)
    pid_file = RUNS_DIR / f".pid_{module_id}"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(proc.pid))
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
            mid = qs.get("module", [""])[0]
            self._send_json(200, _status(mid))
        elif p.startswith("/api/mechanism/"):
            # 代理到 PC demo-server
            path = p[len("/api/mechanism/"):]
            mech_url = _get_mechanism_url()
            if not mech_url:
                self._send_json(503, {"error": "没有配置本地机制服务器(profile base_url 不含 192.168)"})
                return
            query = "?" + parsed.path.split("?")[1] if "?" in self.path else ""
            try:
                import urllib.request as _req
                resp = _req.urlopen(f"{mech_url}/mechanism/{path}{query}", timeout=10)
                self._send_json(200, json.loads(resp.read()))
            except Exception as e:
                self._send_json(500, {"error": str(e)})
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
            mid = qs.get("module", [""])[0]
            try:
                result = _force_stop(mid)
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
        elif p == "/api/profiles":
            body = self._read_body()
            name = (body.get("name") or "").strip()
            if not name or not body.get("base_url"):
                self._send_json(400, {"ok": False, "error": "name / base_url 不能为空"})
                return
            # api_key 可空 (本地 server 如 vLLM/demo-server 不需要 key)
            api_key = (body.get("api_key") or "").strip()
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
                "api_key": api_key,
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
