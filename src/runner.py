"""Experiment runner: orchestrates groups x trials x repeats, writes results.

Output layout (under runs/<tag>/):
  run_config.yaml ........ snapshot of everything used
  results.jsonl .......... one record per (group, trial, call-type)
  summary.json ........... aggregated per-group metrics (dashboard input)
"""
from __future__ import annotations

import random
import sys
import time
import traceback
from pathlib import Path

import api_client
import groups
import metrics
import pi_test
import utils
from utils import save_json, append_jsonl, load_config, load_experiment, make_run_tag, run_dir


def _build_client(cfg: dict, overrides: dict) -> api_client.APIClient:
    return api_client.APIClient(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        temperature=cfg.get("temperature", 0.0),
        max_tokens=cfg.get("max_tokens", 64),
        max_retries=cfg.get("max_retries", 5),
        timeout=cfg.get("timeout", 60),
        **{k: v for k, v in overrides.items() if k in ("temperature", "max_tokens")},
    )


def _call_with_retries(client, message, overrides):
    """Honour per-group temperature/max_tokens overrides."""
    temp = overrides.get("temperature")
    ntok = overrides.get("max_tokens")
    try:
        return client.chat(message, temperature=temp, max_tokens=ntok)
    except Exception as exc:  # noqa: BLE001
        return f"[CALL_ERROR] {exc}"


def _delete_random_char(s: str, rng: random.Random) -> str:
    if len(s) < 2:
        return s
    i = rng.randrange(len(s))
    return s[:i] + s[i + 1:]


def _run_trial(client, group_id, test, k_repeats, measure_cp, measure_robust,
               trial_seed, base_temp) -> dict:
    ov = groups.overrides_for(group_id)
    main_msg = groups.build_message(group_id, test, seed=trial_seed)

    # --- main retrieval: k repeats ---
    responses = []
    for _ in range(k_repeats):
        r = _call_with_retries(client, main_msg, ov)
        responses.append(r)
        time.sleep(0.05)
    acc = sum(metrics.accuracy_over_keys(r, test) for r in responses) / max(1, len(responses))

    rec: dict = {
        "group": group_id,
        "trial_seed": trial_seed,
        "accuracy": acc,
        "n_calls": len(responses),
    }

    # --- context preservation probe ---
    if measure_cp:
        cp_key = test.keys[0]
        cp_msg = main_msg.replace(
            pi_test.build_base_query(test.keys),
            pi_test.build_cp_query(cp_key),
        )
        # if replace didn't hit (group embeds query differently), fall back
        if cp_msg == main_msg:
            cp_msg = main_msg + "\n\n" + pi_test.build_cp_query(cp_key)
        cp_resp = _call_with_retries(client, cp_msg, ov)
        target_first = test.first_values[cp_key]
        rec["cp"] = 1.0 if metrics._norm(target_first) in metrics._norm(cp_resp) else 0.0
        rec["n_calls"] += 1

    # --- robustness: delete 1 char, single repeat ---
    if measure_robust:
        rng = random.Random(trial_seed + 1)
        perturbed = _delete_random_char(main_msg, rng)
        r = _call_with_retries(client, perturbed, ov)
        acc_p = metrics.accuracy_over_keys(r, test)
        rec["robustness_delta"] = metrics.robustness_delta(acc, acc_p)
        rec["n_calls"] += 1

    return rec


def run(enabled_only: bool = True, group_filter: list[str] | None = None) -> str:
    cfg = load_config()
    exp = load_experiment()

    if cfg.get("api_key", "") in ("", "YOUR_API_KEY"):
        print("[WARN] api_key not set in config/config.yaml — calls will fail", file=sys.stderr)

    pi_cfg = exp["pi_test"]
    eval_cfg = exp.get("eval", {})
    k_repeats = int(eval_cfg.get("k_repeats", 5))
    measure_cp = bool(eval_cfg.get("measure_cp", True))
    measure_robust = bool(eval_cfg.get("measure_robustness", True))

    group_defs = [g for g in exp["groups"] if g.get("enabled", True)] if enabled_only else exp["groups"]
    if group_filter:
        group_defs = [g for g in group_defs if g["id"] in group_filter]

    # ensure G0 is always present (baseline for RE)
    ids = [g["id"] for g in group_defs]
    if "G0" not in ids:
        g0 = next(g for g in exp["groups"] if g["id"] == "G0")
        group_defs = [g0] + group_defs

    tag = make_run_tag(cfg["model"])
    out = run_dir(tag)
    save_json(out / "run_config.json", {"api": {k: v for k, v in cfg.items() if k != "api_key"},
                                       "experiment": exp, "tag": tag})
    results_path = out / "results.jsonl"
    results_path.write_text("", encoding="utf-8")  # truncate

    client = _build_client(cfg, {})
    n_trials = int(pi_cfg.get("n_trials", 10))
    base_seed = int(pi_cfg.get("seed", 42))

    # pre-generate the trials once so every group sees the SAME streams
    tests = [pi_test.generate(int(pi_cfg["n_keys"]), int(pi_cfg["updates_per_key"]),
                              seed=base_seed + t) for t in range(n_trials)]

    # cache baseline accuracy per trial
    baseline_per_trial: dict[int, float] = {}

    per_group_records: dict[str, list[dict]] = {}
    n_calls_done = 0

    for gd in group_defs:
        gid, gname = gd["id"], gd.get("name", gd["id"])
        print(f"\n=== Group {gid} ({gname}) ===", file=sys.stderr)
        per_group_records[gid] = []

        for t in range(n_trials):
            test = tests[t]
            trial_seed = base_seed + t
            try:
                rec = _run_trial(client, gid, test, k_repeats, measure_cp, measure_robust,
                                 trial_seed, cfg.get("temperature", 0.0))
            except Exception:  # noqa: BLE001
                rec = {"group": gid, "trial_seed": trial_seed, "error": traceback.format_exc(),
                       "accuracy": 0.0, "n_calls": 0}
            rec["name"] = gname
            per_group_records[gid].append(rec)
            append_jsonl(results_path, rec)
            n_calls_done += rec.get("n_calls", 0)

            if gid == "G0":
                baseline_per_trial[t] = rec["accuracy"]

            baseline_acc = baseline_per_trial.get(t, 0.0)
            print(f"  trial {t}: acc={rec.get('accuracy', 0):.2f} "
                  f"(baseline={baseline_acc:.2f}) "
                  f"cp={rec.get('cp')} rob_delta={rec.get('robustness_delta')}  "
                  f"[{n_calls_done} calls]", file=sys.stderr)

    # aggregate
    baseline_mean = sum(baseline_per_trial.values()) / max(1, len(baseline_per_trial))
    summary = {"tag": tag, "model": cfg["model"], "baseline_acc": baseline_mean,
               "pi_test": pi_cfg, "eval": eval_cfg, "groups": []}
    for gd in group_defs:
        gid = gd["id"]
        agg = metrics.aggregate_group(per_group_records.get(gid, []), baseline_mean)
        agg.update({"id": gid, "name": gd.get("name", gid)})
        summary["groups"].append(agg)
    save_json(out / "summary.json", summary)
    print(f"\n[done] run tag = {tag}\n  summary: {out / 'summary.json'}", file=sys.stderr)
    return tag


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", nargs="*", default=None, help="subset of group IDs to run")
    args = ap.parse_args()
    run(group_filter=args.groups)
