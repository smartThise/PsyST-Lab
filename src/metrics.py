"""Answer parsing and scoring.

A response is "correct for key K" if the model's stated value for K equals
the target (last-assigned) value. We parse leniently: look for the pattern
"<key> ... is <value>" first; fall back to whether the target appears at all
after the key's last mention.
"""
from __future__ import annotations

import re
from statistics import mean

from pi_test import PITest


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def extract_value_for_key(response: str, key: str) -> str | None:
    """Extract the value the model assigned to `key`, or None."""
    text = response or ""
    # pattern 1: "current value of <key> is <value>" / "<key> ... is <value>"
    pat = rf"{re.escape(key)}[^.]*?\bis\s+([A-Za-z][A-Za-z\- ]{{0,30}})"
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        # take first word, strip trailing punctuation
        val = m.group(1).strip().split()[0]
        return re.sub(r"[^A-Za-z\-]", "", val)
    return None


def check_correct(response: str, key: str, target: str) -> bool:
    ext = extract_value_for_key(response, key)
    if ext and _norm(ext) == _norm(target):
        return True
    # fallback: target substring appears after key's last mention
    last = response.lower().rfind(key.lower())
    if last >= 0:
        tail = response[last:]
        return _norm(target) and _norm(target) in _norm(tail)
    return False


def accuracy_over_keys(response: str, test: PITest) -> float:
    if not response:
        return 0.0
    hits = sum(1 for k in test.keys if check_correct(response, k, test.targets[k]))
    return hits / len(test.keys)


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
