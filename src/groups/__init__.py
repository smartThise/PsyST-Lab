"""Group-builder registry (auto-discovered).

Each sibling module (g0.py, g1.py, ..., s5.py) defines:
    ID       str            group id, e.g. "G0"
    NAME     str            short name
    DESC     str            human-readable description (shown in the launch UI)
    build(test, seed=0)->str   the prompt message
    OVERRIDES dict (optional) e.g. {"temperature": 0.8}

Adding a new group = drop a new .py in this package. It auto-appears in the
registry, the launch UI, and the runner — no central list to edit.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

# make sibling src/ modules (pi_test, utils, ...) importable when this package
# is imported from outside the runner (e.g. by the dashboard server).
_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pi_test import PITest  # noqa: E402

REGISTRY: dict[str, callable] = {}
GROUP_META: list[dict] = []
_OVERRIDES: dict[str, dict] = {}


def _discover() -> None:
    for m in pkgutil.iter_modules(__path__):
        name = m.name
        if name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{name}")
        gid = getattr(mod, "ID", name.upper())
        if not hasattr(mod, "build"):
            continue
        REGISTRY[gid] = mod.build
        GROUP_META.append({
            "id": gid,
            "name": getattr(mod, "NAME", gid),
            "desc": getattr(mod, "DESC", ""),
        })
        if hasattr(mod, "OVERRIDES"):
            _OVERRIDES[gid] = dict(mod.OVERRIDES)
    # deterministic order: G0..G9, then S*, then anything else
    def _key(g):
        i = g["id"]
        return (1 if i.startswith("S") else 0, i)
    GROUP_META.sort(key=_key)


_discover()

KNOWN_GROUPS = [g["id"] for g in GROUP_META]


def build_message(group_id: str, test: PITest, seed: int = 0) -> str:
    fn = REGISTRY.get(group_id)
    if fn is None:
        raise KeyError(f"unknown group {group_id!r}; known: {list(REGISTRY)}")
    try:
        return fn(test, seed=seed) if "seed" in fn.__code__.co_varnames else fn(test)
    except TypeError:
        return fn(test)


def overrides_for(group_id: str) -> dict:
    return dict(_OVERRIDES.get(group_id, {}))
