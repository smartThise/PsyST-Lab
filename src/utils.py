"""Generic helpers: config loading, IO, run tagging."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RUNS_DIR = PROJECT_ROOT / "runs"


def load_yaml(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> dict[str, Any]:
    """Load API config: prefer config.yaml, fall back to example."""
    real = CONFIG_DIR / "config.yaml"
    if real.exists():
        return load_yaml(real)
    return load_yaml(CONFIG_DIR / "config.example.yaml")


def load_experiment() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "experiment.yaml")


def make_run_tag(model: str) -> str:
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = re.sub(r"[^a-zA-Z0-9._-]", "-", model or "model")
    return f"{ts}_{model_slug}"


def run_dir(tag: str) -> Path:
    d = RUNS_DIR / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_json(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def append_jsonl(path: Path, obj: Any) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def sanitize_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", s)
