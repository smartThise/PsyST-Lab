"""Answer parsing and scoring — faithful port of the PI-LLM benchmark scoring.

Ports `extract_pieces_response_to_dict` + `_extract_verbal_matches` +
`_extract_colon_matches` + `compute_accuracy` from the paper's
`core/pi_flow_upgrade.py` / `core/analysis_helper.py`, so accuracy numbers
are directly comparable to arXiv:2506.08184.

Framework-specific helpers (RE / CP / robustness / aggregation) stay as-is.
"""
from __future__ import annotations

import re
from statistics import mean

from pi_test import PITest


# --------------------------------------------------------------------------
# paper: text-cleaning helpers
# --------------------------------------------------------------------------
def remove_slash(text: str) -> str:
    """Remove backslashes that are not part of '\\n'."""
    return re.sub(r"\\(?!n)", "", text)


def remove_post_ending_texts(text: str) -> str:
    """Truncate at the first of ',', '.', ';', ':', '\\n' (inclusive)."""
    signs = [",", ".", ";", ":", "\n"]
    min_index = len(text)
    for sign in signs:
        idx = text.find(sign)
        if idx != -1 and idx < min_index:
            min_index = idx
    return text[:min_index] if min_index < len(text) else text


def _clean_token(s: str) -> str:
    """Strip *, straight/curly quotes, and brackets () — match paper's regex."""
    s = re.sub(r"[\*\'\"\[\]\{\}\(\)\<\>]", "", s)
    s = re.sub(r"[‘’“”]", "", s)  # curly quotes
    return s.strip()


# --------------------------------------------------------------------------
# paper: verbal-pattern extraction
# --------------------------------------------------------------------------
# Optional quote/bracket around a token. Built as a clean non-capturing group
# so we don't repeat the paper's hand-escaped char classes (which were buggy:
# missing ']' before '?' in pattern 2/3 KEY captures).
_OQ = r"""(?:["'\[\]<>])?"""  # optional ", ', [, ], <, >

_VERBAL_PATTERNS = [
    # Pattern 1: "<key> : the current value is <value>"
    rf"({_OQ}\w+(?:\s+\w+)?{_OQ})(?:\s*[:-]\s*)(?:the)?\s*"
    rf"(?:most recent|final|last seen|last|latest|current|up-to-date|asked|queried|specified)\s+"
    rf"(?:value|word|term)(?:s)?\s+(?:is|was)(?:\s*:\s*)?\s+"
    rf"({_OQ}\w+(?:\s+\w+)?{_OQ})(?=\n|[,.;:]|$)",
    # Pattern 2: "the value for/of <key> is <value>"
    rf"(?:the)\s*(?:value|word|term)?(?:s)?(?:\s+\w+){{0,1}}\s+"
    rf"(?:with|for|of|to)?\s+(?:the )?(?:category|key)?\s*"
    rf"({_OQ}\w+(?:\s+\w+)?{_OQ})\s+(?:is|was)(?:\s*:\s*)?\s+"
    rf"({_OQ}\w+(?:\s+\w+)?{_OQ})(?=\n|[,.;:]|$)",
    # Pattern 3: "The current value of <key> is <value>"  (most common)
    rf"(?:the)?\s*(?:most recent|final|last|latest|current|up-to-date|asked|queried|specified)\s+"
    rf"(?:value|word|term)?(?:s)?(?:\s+\w+){{0,1}}\s+"
    rf"(?:with|for|of|to)?\s+(?:the )?(?:category|key)?\s*"
    rf"({_OQ}\w+(?:\s+\w+)?{_OQ})\s+(?:is|was)(?:\s*:\s*)?\s+"
    rf"({_OQ}\w+(?:\s+\w+)?{_OQ})(?=\n|[,.;:]|$)",
]


def _extract_verbal_matches(model_output: str) -> dict:
    dict_response: dict[str, str] = {}
    for pattern in _VERBAL_PATTERNS:
        matches = re.findall(pattern, model_output, re.IGNORECASE | re.DOTALL)
        for match in matches:
            if len(match) >= 2:
                key = remove_post_ending_texts(_clean_token(match[0]))
                value = remove_post_ending_texts(_clean_token(match[1]))
                if key and value:
                    dict_response[key] = value  # last wins
    return dict_response


# --------------------------------------------------------------------------
# paper: colon-pattern extraction (only fires if a "current/last/... value" phrase exists)
# --------------------------------------------------------------------------
_COLON_GUARD = r"(?:most recent|final|last|latest|current|up-to-date|asked|queried)\s+(?:value|word|term)"
_COLON_PATTERN = (
    r'(?:[-,.;:\n]|\n|^)\s*[\'‘’“”\[\]\<\>]*'
    r'(\w+(?:[ \t]+\w+)?)'
    r'[\'‘’“”\[\]\<\>]*\s*:\s*'
    r'[\'‘’“”\[\]\<\>]*'
    r'(\w+(?:[ \t]+\w+)?)'
    r'(?=[\'‘’“”\[\]\<\>]*\s*(?:\n|[,.;:]|$))'
)


def _extract_colon_matches(model_output: str) -> dict:
    if not re.search(_COLON_GUARD, model_output, re.IGNORECASE):
        return {}
    dict_colon: dict[str, str] = {}
    for ckey, cvalue in re.findall(_COLON_PATTERN, model_output):
        ckey = _clean_token(ckey)
        cvalue = _clean_token(cvalue)
        if ckey and cvalue:
            dict_colon[ckey] = cvalue  # last wins
    return dict_colon


# --------------------------------------------------------------------------
# paper: top-level extraction pipeline
# --------------------------------------------------------------------------
def extract_pieces_response_to_dict(model_output: str, probe_target: str = "current"):
    """Merge colon + verbal matches; verbal overrides colon. None on error/no-response."""
    if not model_output or len(model_output) == 0:
        return None
    if "error code" in model_output.lower():
        return None
    if model_output.startswith("error") or model_output.startswith("Error"):
        return None
    if re.search(r"\berror\b", model_output, re.IGNORECASE) and len(model_output) < 680:
        return None

    model_output = remove_slash(model_output)
    model_output = re.sub(r"\*", "", model_output)

    dict_verbal = _extract_verbal_matches(model_output)
    dict_colon = _extract_colon_matches(model_output)
    merged = dict_colon.copy()
    merged.update(dict_verbal)  # verbal wins
    merged.pop("key", None)
    return merged


def compute_accuracy(dict_response, dict_truth: dict) -> tuple[float, int]:
    """Paper's compute_accuracy: exact string match (strip+lower), case-sensitive key lookup."""
    if dict_response is None or not isinstance(dict_response, dict):
        return float("nan"), float("nan")
    if len(dict_response) == 0:
        return 0.0, len(dict_truth)
    if not dict_truth:
        return float("nan"), float("nan")
    n_total = len(dict_truth)
    n_correct = n_missing = 0
    for key, true_value in dict_truth.items():
        if key not in dict_response:
            n_missing += 1
        else:
            pred = str(dict_response[key]).strip().lower()
            if pred == str(true_value).strip().lower():
                n_correct += 1
    return (n_correct / n_total if n_total > 0 else 0.0), n_missing


# --------------------------------------------------------------------------
# framework-facing API (used by runner)
# --------------------------------------------------------------------------
def accuracy_over_keys(response: str, test: PITest) -> float:
    """Paper-aligned accuracy: extract dict from response, compare to test.targets."""
    if not response:
        return 0.0
    dict_resp = extract_pieces_response_to_dict(response, probe_target="current")
    if dict_resp is None or len(dict_resp) == 0:
        return 0.0
    acc, _ = compute_accuracy(dict_resp, test.targets)
    if isinstance(acc, float) and acc != acc:  # NaN guard
        return 0.0
    return float(acc)


def release_efficiency(group_acc: float, baseline_acc: float) -> float:
    """RE = improvement over baseline. Clipped at 0 from below."""
    return max(0.0, group_acc - baseline_acc)


def robustness_delta(acc_original: float, acc_perturbed: float) -> float:
    """How much accuracy drops when 1 char is deleted from the injection."""
    return acc_original - acc_perturbed


def aggregate_group(per_trial: list[dict], baseline_acc: float) -> dict:
    """Compute summary stats for one group across trials."""
    accs = [t["accuracy"] for t in per_trial]
    cps = [t["cp"] for t in per_trial if t.get("cp") is not None]
    robs = [t["robustness_delta"] for t in per_trial if t.get("robustness_delta") is not None]
    return {
        "accuracy": mean(accs) if accs else 0.0,
        "re": release_efficiency(mean(accs) if accs else 0.0, baseline_acc),
        "cp": mean(cps) if cps else None,
        "robustness_delta": mean(robs) if robs else None,
        "n_trials": len(per_trial),
        "n_calls": sum(t.get("n_calls", 0) for t in per_trial),
    }


# legacy helpers (still used by the CP probe in runner)
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def extract_value_for_key(response: str, key: str):  # noqa: ANN201
    """Legacy single-key extractor. Prefer accuracy_over_keys for scoring."""
    text = response or ""
    pat = rf"{re.escape(key)}[^.]*?\bis\s+([A-Za-z][A-Za-z\- ]{{0,30}})"
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        val = m.group(1).strip().split()[:2]  # paper captures up to 2 words
        return " ".join(re.sub(r"[^A-Za-z\-]", "", v) for v in val)
    return None


def check_correct(response: str, key: str, target: str) -> bool:  # legacy
    ext = extract_value_for_key(response, key)
    if ext and _norm(ext) == _norm(target):
        return True
    last = response.lower().rfind(key.lower())
    if last >= 0:
        tail = response[last:]
        return bool(_norm(target) and _norm(target) in _norm(tail))
    return False
