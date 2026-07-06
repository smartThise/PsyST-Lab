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


def _pseudo_randomize(records: list[dict], rng: random.Random) -> list[dict]:
    """Shuffle update records so no two consecutive share the same key.

    Matches the paper's `pseudo_randomize(max_key_repeat=0)`: fully random order
    (NOT round-robin), with the only constraint being no immediate key repetition.
    This is critical — a round-robin schedule puts every key's final update in the
    last round, letting the model read all answers off the stream's tail.
    """
    remaining = list(records)
    rng.shuffle(remaining)
    result = [remaining.pop()]
    while remaining:
        last_key = result[-1]["key"]
        candidates = [i for i, r in enumerate(remaining) if r["key"] != last_key]
        # with >=2 keys and balanced counts, candidates is essentially always non-empty;
        # if it ever empties near the tail, fall back to any remaining record.
        next_idx = rng.choice(candidates) if candidates else rng.randrange(len(remaining))
        result.append(remaining.pop(next_idx))
    return result


def generate(n_keys: int = 3, updates_per_key: int = 80, seed: int | None = None) -> PITest:
    rng = random.Random(seed)
    cats = _load_categories()
    if n_keys > len(cats):
        raise ValueError(f"n_keys={n_keys} but only {len(cats)} categories available")
    chosen = rng.sample(list(cats.keys()), n_keys)

    updates_per_key = int(updates_per_key)
    # Paper uses sample_replacement=0: each value appears at most once per key.
    for k in chosen:
        if updates_per_key > len(cats[k]):
            raise ValueError(
                f"updates_per_key={updates_per_key} exceeds {len(cats[k])} "
                f"available words for '{k}' (set sample_replacement on, or lower updates)"
            )
    per_key_values = {k: rng.sample(cats[k], updates_per_key) for k in chosen}

    # build one record per update, then pseudo-randomize their stream order.
    records: list[dict] = []
    for k in chosen:
        for i in range(updates_per_key):
            records.append({"key": k, "value": per_key_values[k][i], "idx": i + 1})
    updates = _pseudo_randomize(records, rng)

    # CRITICAL: "current value" = the value of each key's LAST occurrence in
    # the SHUFFLED stream (stream order IS the temporal order the model sees).
    # per_key_values[k][-1] would be the highest sample-index, which after
    # shuffling lands at a random position — NOT the positional-last.
    targets: dict[str, str] = {}
    first_values: dict[str, str] = {}
    for u in updates:
        k = u["key"]
        if k not in first_values:
            first_values[k] = u["value"]
        targets[k] = u["value"]  # last occurrence in stream order wins

    # format stream (paper: f"{key}: {item}; " concatenated, trailing "; ")
    stream_text = "".join(f"{u['key']}: {u['value']}; " for u in updates)
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
