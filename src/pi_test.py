"""PI stress-test generator.

Produces key-value update streams that reliably trigger proactive interference
(baseline accuracy -> ~0 at the default load). Mirrors the PI-LLM paradigm
(arXiv:2506.08184) at small scale: a few keys, many updates each, query asks
for the most recent value per key.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any

from utils import DATA_DIR


@dataclass
class PITest:
    keys: list[str]                       # category names serving as keys
    updates: list[dict]                   # ordered list of {key, value, idx}
    targets: dict[str, str]               # key -> last (correct) value
    first_values: dict[str, str]          # key -> first value (for CP probe)
    stream_text: str                      # formatted stream ready to inject


def _load_categories() -> dict[str, list[str]]:
    with open(DATA_DIR / "word_categories.json", encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _interleave(order_groups: list[list[str]], rng: random.Random) -> list[str]:
    """Interleave per-key update slots so no same key is consecutive."""
    out: list[str] = []
    prev: str | None = None
    for group in order_groups:
        queue = list(group)
        while queue:
            rng.shuffle(queue)
            # pick first admissible (different from prev)
            picked_idx = None
            for i, k in enumerate(queue):
                if k != prev:
                    picked_idx = i
                    break
            if picked_idx is None:  # all remaining == prev; must place anyway
                picked_idx = 0
            k = queue.pop(picked_idx)
            out.append(k)
            prev = k
    return out


def generate(n_keys: int = 3, updates_per_key: int = 80, seed: int | None = None) -> PITest:
    rng = random.Random(seed)
    cats = _load_categories()
    if n_keys > len(cats):
        raise ValueError(f"n_keys={n_keys} but only {len(cats)} categories available")
    chosen = rng.sample(list(cats.keys()), n_keys)

    # each key gets `updates_per_key` update slots; values sampled with replacement
    order_groups: list[list[str]] = []
    updates: list[dict] = []
    targets: dict[str, str] = {}
    first_values: dict[str, str] = {}
    per_key_idx = {k: 0 for k in chosen}

    # build the schedule first (keys only)
    key_schedule = _interleave([list(chosen) for _ in range(updates_per_key)], rng)

    # assign values per scheduled key
    for k in key_schedule:
        per_key_idx[k] += 1
        val = rng.choice(cats[k])
        if per_key_idx[k] == 1:
            first_values[k] = val
        updates.append({"key": k, "value": val, "idx": per_key_idx[k]})
        targets[k] = val  # last assignment wins

    # format stream (no numeric prefix — paper says prefixes weren't in input)
    stream_text = "; ".join(f"{u['key']}: {u['value']}" for u in updates) + "."
    return PITest(
        keys=list(chosen),
        updates=updates,
        targets=targets,
        first_values=first_values,
        stream_text=stream_text,
    )


def build_base_query(keys: list[str]) -> str:
    ks = ", ".join(keys)
    return (
        f"What are the current value of each key ({ks}) you are tracking? "
        f"End your response with: 'The current value of <key> is <value>.'"
    )


def build_cp_query(key: str) -> str:
    """Context-preservation probe: ask for an unrelated prior fact (first value)."""
    return (
        f"Separately, what was the FIRST value ever assigned to the key '{key}' "
        f"earlier in the stream? Answer in the form: 'The first value of {key} was <value>.'"
    )
