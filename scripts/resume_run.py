#!/usr/bin/env python3
"""Resume an incomplete run — only re-runs trials that don't have results yet."""
import sys, json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.registry import get_module
from core.runner import ExperimentRunner

def resume(run_dir: str):
    run_path = Path(run_dir)
    if not run_path.exists():
        print(f"Run dir not found: {run_dir}")
        return

    # Read config
    rc = json.loads((run_path / "run_config.json").read_text())
    mid = rc["module_id"]
    n_trials = rc["n_trials"]
    k_repeats = rc.get("k_repeats", 1)
    seed = rc.get("seed", 42)
    cids = [c["id"] for c in rc["conditions"]]

    # Read existing results, count done per condition
    done = defaultdict(int)
    if (run_path / "results.jsonl").exists():
        with open(run_path / "results.jsonl") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    cond_id = r.get("condition_id", "")
                    done[cond_id] += 1

    # Figure out which conditions need more trials
    to_run = []
    for cid in cids:
        remaining = n_trials - done.get(cid, 0)
        if remaining > 0:
            to_run.append((cid, remaining))

    if not to_run:
        print("All conditions complete — nothing to resume.")
        return

    total = sum(r for _, r in to_run)
    already = sum(done.values())

    # Setup logging FIRST
    _log_fp = open(run_path / "run.log", "w", encoding="utf-8")
    def _log(msg):
        print(msg, flush=True)
        _log_fp.write(msg + "\n")
        _log_fp.flush()

    _log(f"Resuming {run_path.name}: {total} trials across {len(to_run)} conditions (already done: {already})")

    # Load module and runner
    mod = get_module(mid)
    runner = ExperimentRunner(mod)

    # Override run_dir to this existing directory
    runner._run_dir = run_path
    runner._tag = run_path.name
    runner._log = _log
    runner._log_fp = _log_fp

    all_conditions = mod.build_conditions()
    cond_map = {c.id: c for c in all_conditions}

    done_count = sum(done.values())

    for cid, remaining in to_run:
        cond = cond_map.get(cid)
        if not cond and hasattr(mod, "rebuild_condition"):
            cond = mod.rebuild_condition(cid)
        if not cond:
            _log(f"  [skip] unknown condition: {cid}")
            continue

        for t in range(done.get(cid, 0), n_trials):
            task = mod.build_task(cond, seed + hash(cid) % 100000 + t)

            for rep in range(k_repeats):
                temp = task.overrides.get("temperature", runner.client.temperature)
                mtok = task.overrides.get("max_tokens", runner.client.max_tokens)

                if task.metadata.get("multi_turn"):
                    response, turn_log = runner._run_multi_turn(task, temp, mtok)
                    task.metadata["turn_log"] = turn_log
                else:
                    response = runner.client.chat(task.messages, temperature=temp, max_tokens=mtok)

                result = mod.score(task, response)
                done_count += 1

                record = {
                    "module_id": mid,
                    "condition_id": result.condition_id,
                    "trial": t,
                    "repeat": rep,
                    "scores": result.scores,
                    "raw": result.raw,
                }
                if task.metadata.get("turn_log"):
                    record["turn_log"] = task.metadata["turn_log"]

                # Append to results.jsonl
                with open(run_path / "results.jsonl", "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

                scores_str = " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                      for k, v in list(result.scores.items())[:4])
                _log(f"  [{done_count}/{sum(c[1] for c in to_run) + done_count}] {cid} trial={t}: {scores_str}")

    # Rebuild summary
    _log("Rebuilding summary...")
    rebuild_summary(run_path, rc, cids, n_trials)
    _log(f"Done. {run_path}")


def rebuild_summary(run_path, rc, cids, n_trials):
    from collections import defaultdict
    results = []
    with open(run_path / "results.jsonl") as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))

    by_cond = defaultdict(list)
    for i, r in enumerate(results):
        ci = i // n_trials
        if ci < len(cids):
            by_cond[cids[ci]].append(r["scores"])

    conditions = []
    for cid in cids:
        sl = by_cond.get(cid, [])
        keys = set()
        for s in sl:
            keys.update(k for k, v in s.items() if v is not None)
        avg = {}
        for k in sorted(keys):
            vals = [s[k] for s in sl if s.get(k) is not None]
            if vals:
                avg[k] = sum(vals) / len(vals)
        avg["n"] = len(sl)
        avg["condition_id"] = cid
        avg["condition_name"] = cid
        conditions.append(avg)

    summary = {
        "module_id": rc["module_id"],
        "module_name": rc.get("module_name", ""),
        "tag": run_path.name,
        "conditions": conditions,
        "n_trials": n_trials,
        "k_repeats": rc.get("k_repeats", 1),
    }
    (run_path / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary rebuilt: {len(conditions)} conditions")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/resume_run.py runs/<module>/<tag>")
        sys.exit(1)
    resume(sys.argv[1])
