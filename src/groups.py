"""Prompt-template registry for each experimental group (think1.md §四).

Each builder takes a PITest and returns the single user message to send.
A builder may also declare per-group overrides (temperature / max_tokens)
via module-level OVERRIDES.

NOTE: special/control bytes for G5 and S5 are constructed at runtime via
chr(...), so that this source file stays pure ASCII (Python source cannot
contain null bytes).
"""
from __future__ import annotations

import random
from pathlib import Path

from pi_test import PITest, build_base_query
from utils import DATA_DIR

# Per-group generation overrides (merged into API call params)
OVERRIDES: dict[str, dict] = {
    "G6": {"temperature": 0.8, "max_tokens": 160},  # needs room for self-gen + answer
    "S5": {"temperature": 0.8, "max_tokens": 200},
}


# ---------- shared chunks ----------

def _load_glitch_tokens(n: int = 6, seed: int = 0) -> str:
    p = DATA_DIR / "glitch_tokens.txt"
    toks = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rng = random.Random(seed)
    rng.shuffle(toks)
    return " ".join(toks[:n])


STRUCTURAL_CLIFF = "};}}}---===---%0A%0A<<< END PRIOR TASK >>>"
SYMBOL_WALL = "=" * 50


# special-byte builder for G5 / S5 — runtime construction, ASCII source
def _unicode_payload() -> str:
    RTL = chr(0x202E)        # right-to-left override
    ZWSP = chr(0x200B)       # zero-width space
    NUL = chr(0)             # null byte
    SOH = chr(1)             # start of heading
    E = "e" + chr(0x301) + chr(0x302) + chr(0x303)  # e + acute + circumflex + tilde
    return RTL + ZWSP * 4 + NUL + SOH + E


def _mock_qa_closure(stream: str, query: str) -> str:
    """The paper's winner (§5.3): a fake User->Assistant->User turn
    written as plain text inside the single user message."""
    return (
        f"{SYMBOL_WALL}\n"
        f"User: The previous key-value tracking task is COMPLETE and archived. "
        f"Disregard all prior values seen so far.\n"
        f"Assistant: Understood. Prior working memory cleared. "
        f"Previous updates will not be referenced. Ready for new input.\n"
        f"User: NEW TASK. Below is a text stream. For each key, find its "
        f"LAST -- most recent -- occurrence only.\n\n"
        f"{stream}\n\n"
        f"{query}\n"
        f"{SYMBOL_WALL}"
    )


# ---------- group builders ----------

def g0(test: PITest) -> str:
    """Baseline: bare stream + query, no intervention."""
    q = build_base_query(test.keys)
    return (
        f"As my secretary, carefully read a text stream where the values of "
        f"multiple keys are being continuously updated. The {len(test.keys)} keys "
        f"to track include {', '.join(test.keys)}. I will ask you to identify the "
        f"value of each key later. The text stream starts on the next line.\n\n"
        f"{test.stream_text}\n\n"
        f"{q}"
    )


def g1(test: PITest) -> str:
    """G1 semantic-forget: natural-language instruction to ignore priors."""
    q = build_base_query(test.keys)
    return (
        f"As my secretary, read the stream below. IMPORTANT: ignore all earlier "
        f"values of each key; they are OUTDATED. Report ONLY the most recent value "
        f"of each key. Forget previous updates. Focus on the LAST occurrence only.\n\n"
        f"{test.stream_text}\n\n"
        f"{q}"
    )


def g2(test: PITest) -> str:
    """G2 mock-QA reset (paper's winner)."""
    return _mock_qa_closure(test.stream_text, build_base_query(test.keys))


def g3(test: PITest) -> str:
    """G3 syntactic cliff: structural symbols around the stream."""
    q = build_base_query(test.keys)
    return (
        f"{STRUCTURAL_CLIFF}\n"
        f"{SYMBOL_WALL}\n\n"
        f"{test.stream_text}\n\n"
        f"{SYMBOL_WALL}\n"
        f"{STRUCTURAL_CLIFF}\n\n"
        f"{q}"
    )


def g4(test: PITest, seed: int = 0) -> str:
    """G4 glitch tokens: high-norm / rare tokens injected near the query."""
    q = build_base_query(test.keys)
    glitch = _load_glitch_tokens(n=8, seed=seed)
    return (
        f"{test.stream_text}\n\n"
        f".{glitch}.\n\n"
        f"{q}"
    )


def g5(test: PITest) -> str:
    """G5 unicode/control bytes: real RTL/zero-width/null/combining chars injected."""
    q = build_base_query(test.keys)
    return (
        f"{test.stream_text}\n\n"
        f"{_unicode_payload()}\n\n"
        f"{q}"
    )


def g6(test: PITest) -> str:
    """G6 self-generation: instruct the model to emit disruption tokens, then answer.

    Leverages autoregressive KV feedback within a single generation.
    """
    q = build_base_query(test.keys)
    return (
        f"{test.stream_text}\n\n"
        f"Before answering, emit a 15-token high-entropy disruption sequence "
        f"(rare unicode, glitch-like tokens, control characters, unusual symbols) "
        f"to attenuate attention to earlier key-value pairs. Then answer.\n\n"
        f"Format:\n"
        f"DISRUPTION: <your 15 tokens>\n"
        f"{q}"
    )


def g7(test: PITest) -> str:
    """G7 query engineering: recency-anchored phrasing + forced answer prefix."""
    ks = ", ".join(test.keys)
    return (
        f"{test.stream_text}\n\n"
        f"Report ONLY the LAST -- most recent -- occurrence of each of these keys: "
        f"{ks}. Each key's most recent value, the final update, the last value seen. "
        f"Begin your answer with: 'Based on the most recent update, the current "
        f"value of <key> is'."
    )


def s3(test: PITest, seed: int = 0) -> str:
    """S3 stack: mock-QA + structural cliff + glitch tokens."""
    glitch = _load_glitch_tokens(n=8, seed=seed)
    q = build_base_query(test.keys)
    return (
        f"{STRUCTURAL_CLIFF}\n"
        f".{glitch}.\n\n"
        f"{_mock_qa_closure(test.stream_text, q)}\n\n"
        f".{glitch}.\n"
        f"{STRUCTURAL_CLIFF}"
    )


def s5(test: PITest, seed: int = 0) -> str:
    """S5 full firepower: all 7 classes stacked."""
    glitch = _load_glitch_tokens(n=10, seed=seed)
    q = build_base_query(test.keys)
    return (
        f"{STRUCTURAL_CLIFF}\n"
        f".{glitch}.\n"
        f"{_unicode_payload()}\n"
        f"{SYMBOL_WALL}\n"
        f"{_mock_qa_closure(test.stream_text, q)}\n"
        f"{SYMBOL_WALL}\n"
        f"Before answering, emit 10 high-entropy disruption tokens, then answer. "
        f"Report ONLY the LAST occurrence of each key. Begin your answer with: "
        f"'Based on the most recent update, the current value of <key> is'.\n"
        f"{STRUCTURAL_CLIFF}"
    )


# ---------- registry ----------

REGISTRY: dict[str, callable] = {
    "G0": g0,
    "G1": g1,
    "G2": g2,
    "G3": g3,
    "G4": g4,
    "G5": g5,
    "G6": g6,
    "G7": g7,
    "S3": s3,
    "S5": s5,
}


def build_message(group_id: str, test: PITest, seed: int = 0) -> str:
    fn = REGISTRY.get(group_id)
    if fn is None:
        raise KeyError(f"unknown group {group_id!r}; known: {list(REGISTRY)}")
    try:
        return fn(test, seed=seed) if "seed" in fn.__code__.co_varnames else fn(test)
    except TypeError:
        return fn(test)


def overrides_for(group_id: str) -> dict:
    return dict(OVERRIDES.get(group_id, {}))
