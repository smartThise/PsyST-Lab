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

from ..pi_test import PITest

REGISTRY: dict[str, callable] = {}
FEATURES: dict[str, callable] = {}
FEATURE_POSITION: dict[str, str] = {}
GROUP_META: list[dict] = []
_OVERRIDES: dict[str, dict] = {}
KNOWN_GROUPS: list[str] = []


def discover() -> None:
    """Re-scan src/groups/ for modules. Safe to call repeatedly (clears first),
    so the dashboard can pick up newly dropped group files without a restart."""
    REGISTRY.clear()
    FEATURES.clear()
    FEATURE_POSITION.clear()
    GROUP_META.clear()
    _OVERRIDES.clear()
    for m in pkgutil.iter_modules(__path__):
        name = m.name
        if name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{name}")
        gid = getattr(mod, "ID", name.upper())
        if not hasattr(mod, "build"):
            continue
        REGISTRY[gid] = mod.build
        if hasattr(mod, "feature"):
            FEATURES[gid] = mod.feature
            FEATURE_POSITION[gid] = getattr(mod, "POSITION", "midstream")
        GROUP_META.append({
            "id": gid,
            "name": getattr(mod, "NAME", gid),
            "desc": getattr(mod, "DESC", ""),
            "color": getattr(mod, "COLOR", None),
            "position": getattr(mod, "POSITION", "midstream"),
            "composable": hasattr(mod, "feature"),
        })
        if hasattr(mod, "OVERRIDES"):
            _OVERRIDES[gid] = dict(mod.OVERRIDES)
    # deterministic order: G* first, then S*
    GROUP_META.sort(key=lambda g: (1 if g["id"].startswith("S") else 0, g["id"]))
    KNOWN_GROUPS.clear()
    KNOWN_GROUPS.extend(g["id"] for g in GROUP_META)


discover()


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


def build_task_message(test: PITest, feature_ids: list[str], seed: int = 0) -> str:
    """Compose a task = ordered feature list. Empty list = baseline. Mid-stream
    features concatenate (in feature_ids order) into one block at len-tail;
    end-positioned features concatenate into one block before the query. Order
    within each position group follows feature_ids, so [G1,G2] != [G2,G1]."""
    import groups._common as _common
    if not feature_ids:
        return _common.assemble(test)
    mid: list[str] = []
    end: list[str] = []
    for fid in feature_ids:
        fn = FEATURES.get(fid)
        if fn is None:
            raise KeyError(f"unknown feature {fid!r}; known: {list(FEATURES)}")
        txt = fn(test, seed)
        if not txt:
            continue
        (mid if FEATURE_POSITION.get(fid, "midstream") == "midstream" else end).append(txt)
    if not mid and not end:
        return _common.assemble(test)
    if mid and not end:
        return _common.assemble_midstream(test, injection="\n".join(mid))
    if end and not mid:
        return _common.assemble(test, injection="\n".join(end))
    return _common.assemble_hybrid(test, mid_injection="\n".join(mid),
                                   end_injection="\n".join(end))
