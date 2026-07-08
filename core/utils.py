"""共享工具: 配置加载、JSON IO、运行标签."""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
RUNS_DIR = PROJECT_ROOT / "runs"


# ---- 配置 ----
def load_yaml(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> dict[str, Any]:
    """加载 config/config.yaml (API keys, model 等)."""
    real = CONFIG_DIR / "config.yaml"
    if real.exists():
        return load_yaml(real)
    return load_yaml(CONFIG_DIR / "config.example.yaml")


def load_profiles() -> dict[str, Any]:
    """加载 config/api_profiles.yaml."""
    return load_yaml(CONFIG_DIR / "api_profiles.yaml")


# ---- IO ----
def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


# ---- 标签 ----
def make_run_tag() -> str:
    """生成运行标签: YYYYMMDD_HHMMSS."""
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def sanitize_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", s)
