"""Experiment runner: orchestrates groups x trials x repeats, writes results.

Output layout (under runs/<tag>/):
  run_config.yaml ........ snapshot of everything used
  results.jsonl .......... one record per (group, trial, call-type)
  summary.json ........... aggregated per-group metrics (dashboard input)
"""
from __future__ import annotations

import json
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

RUNS_ROOT = Path(__file__).resolve().parent.parent / "runs"


def _find_historical_baseline(cfg: dict, exp: dict) -> dict | None:
    """Find a past run whose G0 was measured under EXACTLY matching config
    (model, n_keys, updates_per_key, n_trials, base_seed, k_repeats). G0 runs
    at temperature 0 so it's deterministic — a matching historical G0 can be
    reused instead of re-running it. Returns {tag, mean, per_trial:{idx:acc}}.
    """
    if not RUNS_ROOT.exists():
        return None
    pi = exp.get("pi_test", {})
    target = {
        "model": cfg.get("model"),
        "n_keys": int(pi.get("n_keys", 0)),
        "updates_per_key": int(pi.get("updates_per_key", 0)),
        "n_trials": int(pi.get("n_trials", 0)),
        "seed": int(pi.get("seed", 42)),
        "k_repeats": int(exp.get("eval", {}).get("k_repeats", 1)),
    }
    for d in sorted(RUNS_ROOT.iterdir(), reverse=True):  # newest first
        if not d.is_dir():
            continue
        rc_p, sum_p, res_p = d / "run_config.json", d / "summary.json", d / "results.jsonl"
        if not (rc_p.exists() and sum_p.exists() and res_p.exists()):
            continue
        try:
            rc = json.loads(rc_p.read_text(encoding="utf-8"))
            rpi = rc.get("experiment", {}).get("pi_test", {})
            rev = rc.get("experiment", {}).get("eval", {})
            if (rc.get("api", {}).get("model") == target["model"]
                    and int(rpi.get("n_keys", -1)) == target["n_keys"]
                    and int(rpi.get("updates_per_key", -1)) == target["updates_per_key"]
                    and int(rpi.get("n_trials", -1)) == target["n_trials"]
                    and int(rpi.get("seed", -2)) == target["seed"]
                    and int(rev.get("k_repeats", -1)) == target["k_repeats"]):
                summ = json.loads(sum_p.read_text(encoding="utf-8"))
                g0 = next((g for g in summ.get("groups", []) if g.get("id") == "G0"), None)
                if not g0 or g0.get("accuracy") is None:
                    continue
                per_trial = {}
                with open(res_p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            r = json.loads(line)
                        except Exception:
                            continue
                        if r.get("group") == "G0" and "trial_seed" in r:
                            per_trial[int(r["trial_seed"]) - target["seed"]] = r.get("accuracy", 0.0)
                if per_trial:
                    return {"tag": d.name, "mean": summ["baseline_acc"], "per_trial": per_trial}
        except Exception:
            continue
    return None


def _build_client(cfg: dict, overrides: dict) -> api_client.APIClient:
    return api_client.APIClient(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        temperature=cfg.get("temperature", 0.0),
        max_tokens=cfg.get("max_tokens", 64),
        max_retries=cfg.get("max_retries", 5),
        timeout=cfg.get("timeout", 60),
        extra_body=cfg.get("extra_body"),
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


def _run_trial(client, task_id, features, test, k_repeats, measure_cp, measure_robust,
               trial_seed, base_temp) -> dict:
    ov: dict = {}  # task model: uniform temp 0, no per-group overrides
    main_msg = groups.build_task_message(test, features, seed=trial_seed)

    # --- main retrieval: k repeats ---
    responses = []
    for _ in range(k_repeats):
        r = _call_with_retries(client, main_msg, ov)
        responses.append(r)
        time.sleep(0.05)
    acc = sum(metrics.accuracy_over_keys(r, test) for r in responses) / max(1, len(responses))

    rec: dict = {
        "group": task_id,
        "features": list(features),
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


def run(enabled_only: bool = True, group_filter: list[str] | None = None,
        tasks: list[dict] | None = None,
        overrides: dict | None = None) -> str:
    cfg = load_config()
    exp = load_experiment()
    overrides = overrides or {}
    # runtime overrides (from CLI / dashboard launch panel)
    if overrides.get("model"):
        cfg["model"] = overrides["model"]
    for k in ("n_keys", "updates_per_key", "n_trials"):
        if k in overrides:
            exp["pi_test"][k] = overrides[k]
    if "k_repeats" in overrides:
        exp["eval"]["k_repeats"] = overrides["k_repeats"]

    if cfg.get("api_key", "") in ("", "YOUR_API_KEY"):
        print("[WARN] api_key not set in config/config.yaml — calls will fail", file=sys.stderr)

    pi_cfg = exp["pi_test"]
    eval_cfg = exp.get("eval", {})
    k_repeats = int(eval_cfg.get("k_repeats", 5))
    measure_cp = bool(eval_cfg.get("measure_cp", True))
    measure_robust = bool(eval_cfg.get("measure_robustness", True))

    # Source of truth = the groups package (auto-discovered). Two launch modes:
    #   - tasks=[...]: each task is an ordered feature list (composed). Empty
    #     list = baseline (G0). Primary mode for the task composer.
    #   - group_filter / enabled list (legacy): each group id becomes a single-
    #     feature task ([Gx]); G0 becomes the empty-feature baseline.
    import groups as _groups_mod
    _groups_mod.discover()
    all_groups = [{"id": g["id"], "name": g["name"]} for g in _groups_mod.GROUP_META]
    name_map = {g["id"]: g["name"] for g in all_groups}

    if tasks is not None:
        task_defs = []
        for t in tasks:
            feats = [f for f in t.get("features", []) if f]
            if not feats:
                tid, tname = "G0", t.get("name", "baseline")
            else:
                tid = t.get("id") or "+".join(feats)
                tname = t.get("name", tid)
            task_defs.append({"id": tid, "name": tname, "features": feats})
    else:
        enabled_map = {g["id"]: g.get("enabled", True) for g in exp.get("groups", [])}
        if group_filter:
            ids = [g["id"] for g in all_groups if g["id"] in group_filter]
        elif enabled_only:
            ids = [g["id"] for g in all_groups if enabled_map.get(g["id"], True)]
        else:
            ids = [g["id"] for g in all_groups]
        task_defs = [
            {"id": gid, "name": name_map.get(gid, gid),
             "features": ([] if gid == "G0" else [gid])}
            for gid in ids
        ]

    # Baseline (empty-feature task): if absent, REUSE a historical G0 from a
    # matching config (G0 at temp 0 is deterministic), else auto-prepend G0.
    has_baseline = any(td["features"] == [] for td in task_defs)
    baseline_reused_from = None
    reused_baseline = None
    if not has_baseline:
        reused_baseline = _find_historical_baseline(cfg, exp)
        if reused_baseline:
            baseline_reused_from = reused_baseline["tag"]
        else:
            task_defs = [{"id": "G0", "name": "baseline", "features": []}] + task_defs

    tag = make_run_tag(cfg["model"])
    out = run_dir(tag)
    save_json(out / "run_config.json", {"api": {k: v for k, v in cfg.items() if k != "api_key"},
                                       "experiment": exp, "tag": tag,
                                       "planned_groups": [td["id"] for td in task_defs],
                                       "planned_total": len(task_defs) * int(pi_cfg.get("n_trials", 10)),
                                       "tasks": [{"id": td["id"], "name": td["name"],
                                                  "features": td["features"]} for td in task_defs],
                                       "baseline_reused_from": baseline_reused_from})
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
    if reused_baseline:
        baseline_per_trial = dict(reused_baseline["per_trial"])
        print(f"[baseline] reused from {reused_baseline['tag']} "
              f"(mean={reused_baseline['mean']:.3f}, {len(baseline_per_trial)} trials) — skipping G0",
              file=sys.stderr)

    per_group_records: dict[str, list[dict]] = {}
    n_calls_done = 0

    for td in task_defs:
        tid, tname, features = td["id"], td["name"], td["features"]
        print(f"\n=== Task {tid} ({tname}) ===", file=sys.stderr)
        per_group_records[tid] = []

        for t in range(n_trials):
            test = tests[t]
            trial_seed = base_seed + t
            try:
                rec = _run_trial(client, tid, features, test, k_repeats, measure_cp, measure_robust,
                                 trial_seed, cfg.get("temperature", 0.0))
            except Exception:  # noqa: BLE001
                rec = {"group": tid, "features": list(features), "trial_seed": trial_seed,
                       "error": traceback.format_exc(), "accuracy": 0.0, "n_calls": 0}
            rec["name"] = tname
            per_group_records[tid].append(rec)
            append_jsonl(results_path, rec)
            n_calls_done += rec.get("n_calls", 0)

            if features == []:  # baseline task
                baseline_per_trial[t] = rec["accuracy"]

            baseline_acc = baseline_per_trial.get(t, 0.0)
            print(f"  trial {t}: acc={rec.get('accuracy', 0):.2f} "
                  f"(baseline={baseline_acc:.2f}) "
                  f"cp={rec.get('cp')} rob_delta={rec.get('robustness_delta')}  "
                  f"[{n_calls_done} calls]", file=sys.stderr)

    # aggregate
    baseline_mean = sum(baseline_per_trial.values()) / max(1, len(baseline_per_trial))
    summary = {"tag": tag, "model": cfg["model"], "baseline_acc": baseline_mean,
               "pi_test": pi_cfg, "eval": eval_cfg, "groups": [],
               "baseline_reused_from": baseline_reused_from}
    for td in task_defs:
        tid = td["id"]
        agg = metrics.aggregate_group(per_group_records.get(tid, []), baseline_mean)
        agg.update({"id": tid, "name": td["name"], "features": td["features"]})
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
