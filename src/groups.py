"""Prompt-template registry for each experimental group (think1.md §四).

All groups share the paper-faithful baseline structure
(`instruction\n\nThe text stream starts on the next line.\n {stream}\n\n{query}`)
and differ ONLY in an optional injection before the query and/or a query
override. This keeps group-to-group comparisons clean: G1 vs G0 isolates the
semantic-forget injection, G2 vs G0 isolates mock-QA, etc.

Intervention content is not from the paper (the paper has no G1-G7); only the
baseline scaffold is paper-aligned. Special/control bytes (G5/S5) are built at
runtime via chr() so this source file stays pure ASCII.
"""
from __future__ import annotations

import random
from pathlib import Path

from pi_test import PITest, build_base_query
from utils import DATA_DIR

# Per-group generation overrides (merged into API call params)
OVERRIDES: dict[str, dict] = {
    "G6": {"temperature": 0.8},  # self-generation needs sampling
    "S5": {"temperature": 0.8},
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


# ---------- paper-faithful baseline scaffold ----------

def _paper_instruction(test: PITest) -> str:
    """Paper's instruction (verbatim, incl. the 'updated.The' no-space concatenation)."""
    keys_csv = ", ".join(test.keys)
    return (
        "As my secretary, I need you to carefully read a text stream where the "
        "values of multiple keys are being continuously updated."
        f"The {len(test.keys)} keys to track include {keys_csv}. "
        "I will ask you to identify the value of each key later."
    )


def _paper_stream_block(test: PITest) -> str:
    return f"The text stream starts on the next line.\n {test.stream_text}"


def _assemble(test: PITest, injection: str = "", query: str | None = None) -> str:
    """Paper baseline + optional injection before query + optional query override."""
    parts = [_paper_instruction(test), _paper_stream_block(test)]
    if injection:
        parts.append(injection)
    parts.append(query or build_base_query(test.keys))
    return "\n\n".join(parts)


# ---------- intervention content ----------

SEMANTIC_FORGET = (
    "IMPORTANT: ignore all earlier values of each key; they are OUTDATED. "
    "Report ONLY the most recent (LAST) value of each key. Forget previous updates."
)

MOCK_QA_DIALOGUE = (
    f"{SYMBOL_WALL}\n"
    "User: The previous key-value tracking task is COMPLETE and archived. "
    "Disregard all prior values seen so far.\n"
    "Assistant: Understood. Prior working memory cleared. Ready for new input.\n"
    "User: NEW TASK. For each key, find its LAST -- most recent -- occurrence only.\n"
    f"{SYMBOL_WALL}"
)


def _self_gen_query(test: PITest) -> str:
    """Query that asks the model to emit disruption tokens first, then answer."""
    return (
        "First emit a 15-token high-entropy disruption sequence (rare unicode, "
        "glitch-like tokens, unusual symbols) to attenuate attention to earlier "
        "key-value pairs, then answer.\n"
        "Format:\nDISRUPTION: <your 15 tokens>\n"
        + build_base_query(test.keys)
    )


def _engineered_query(test: PITest) -> str:
    """Recency-anchored query with forced answer prefix."""
    return (
        "Report ONLY the LAST -- most recent -- occurrence of each key. "
        "The final update, the last value seen, the most recent value. "
        "Begin your answer with: 'Based on the most recent update, '.\n"
        + build_base_query(test.keys)
    )


# ---------- group builders ----------

def g0(test: PITest) -> str:
    """Baseline: paper-faithful prompt, no intervention."""
    return _assemble(test)


def g1(test: PITest) -> str:
    """G1 semantic-forget: natural-language injection to ignore priors."""
    return _assemble(test, injection=SEMANTIC_FORGET)


def g2(test: PITest) -> str:
    """G2 mock-QA reset: fake User->Assistant->User dialogue injected before query."""
    return _assemble(test, injection=MOCK_QA_DIALOGUE)


def g3(test: PITest) -> str:
    """G3 syntactic cliff: structural symbols injected before query."""
    return _assemble(test, injection=f"{STRUCTURAL_CLIFF}\n{SYMBOL_WALL}")


def g4(test: PITest, seed: int = 0) -> str:
    """G4 glitch tokens: high-norm / rare tokens injected before query."""
    glitch = _load_glitch_tokens(n=8, seed=seed)
    return _assemble(test, injection=f".{glitch}.")


def g5(test: PITest) -> str:
    """G5 unicode/control bytes: real RTL/zero-width/null/combining chars injected."""
    return _assemble(test, injection=_unicode_payload())


def g6(test: PITest) -> str:
    """G6 self-generation: query override asking for disruption tokens then answer."""
    return _assemble(test, query=_self_gen_query(test))


def g7(test: PITest) -> str:
    """G7 query engineering: recency-anchored phrasing + forced answer prefix."""
    return _assemble(test, query=_engineered_query(test))


def s3(test: PITest, seed: int = 0) -> str:
    """S3 stack: structural cliff + glitch + mock-QA."""
    glitch = _load_glitch_tokens(n=8, seed=seed)
    injection = f"{STRUCTURAL_CLIFF}\n.{glitch}.\n{MOCK_QA_DIALOGUE}"
    return _assemble(test, injection=injection)


def s5(test: PITest, seed: int = 0) -> str:
    """S5 full firepower: cliff + glitch + unicode + mock-QA + self-gen query."""
    glitch = _load_glitch_tokens(n=10, seed=seed)
    injection = (
        f"{STRUCTURAL_CLIFF}\n.{glitch}.\n{_unicode_payload()}\n{MOCK_QA_DIALOGUE}"
    )
    return _assemble(test, injection=injection, query=_self_gen_query(test))


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
