#!/usr/bin/env python3
"""Entry point: run the full experiment.

Usage (from project root):
    python scripts/run_all.py                 # all enabled groups
    python scripts/run_all.py --groups G0 G2  # just these
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import runner  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the PI-release experiment.")
    ap.add_argument("--groups", nargs="*", default=None,
                    help="Subset of group IDs (e.g. G0 G2 G4). Default: all enabled.")
    ap.add_argument("--all", action="store_true",
                    help="Include disabled groups too.")
    ap.add_argument("--model", default=None, help="override config.model")
    ap.add_argument("--n-keys", type=int, default=None)
    ap.add_argument("--updates", type=int, default=None, help="updates per key")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--k-repeats", type=int, default=None)
    args = ap.parse_args()
    overrides = {}
    if args.model: overrides["model"] = args.model
    if args.n_keys is not None: overrides["n_keys"] = args.n_keys
    if args.updates is not None: overrides["updates_per_key"] = args.updates
    if args.trials is not None: overrides["n_trials"] = args.trials
    if args.k_repeats is not None: overrides["k_repeats"] = args.k_repeats
    tag = runner.run(enabled_only=not args.all, group_filter=args.groups, overrides=overrides)
    print(f"\nLaunch the dashboard to view results:\n  python dashboard/server.py\n")
    print(f"Run tag: {tag}")


if __name__ == "__main__":
    main()
