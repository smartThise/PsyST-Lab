#!/usr/bin/env python3
"""PsyST Lab — 轻量化 LLM 认知实验平台入口.

用法:
    python launch.py --list                         列出所有模块
    python launch.py --module pi_release            运行 PI release 实验
    python launch.py --module recall_rating         运行 Recall-Rating 实验
    python launch.py --module pi_release --model deepseek-chat --trials 5
    python launch.py --dashboard                    启动控制面板
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.registry import discover_modules, list_modules
from core.runner import ExperimentRunner
from core.utils import load_config


def cmd_list() -> None:
    """列出所有可用模块及其条件."""
    modules = discover_modules()
    if not modules:
        print("没有发现任何模块。请检查 modules/ 目录。")
        return
    for mid, mod in sorted(modules.items()):
        print(f"\n{'='*60}")
        print(f"  {mid} — {mod.module_name}")
        print(f"{'='*60}")
        try:
            conds = mod.build_conditions()
            for c in conds:
                print(f"  {c.id:<24} {c.name}")
            print(f"  ({len(conds)} 个条件)")
        except Exception as e:
            print(f"  [错误] 无法列出条件: {e}")


def cmd_run(module_id: str, args: argparse.Namespace) -> None:
    """运行指定模块的实验."""
    modules = discover_modules()
    if module_id not in modules:
        print(f"未知模块 '{module_id}'。可用: {list(modules)}")
        sys.exit(1)

    # 处理 --tasks-file (旧 drag 模式)
    condition_filter = args.conditions or None
    if args.tasks_file:
        import json as _json
        from pathlib import Path as _Path
        tasks = _json.loads(_Path(args.tasks_file).read_text(encoding="utf-8"))
        ids = set()
        for t in tasks:
            feats = t.get("features", [])
            ids.add("+".join(feats) if feats else "G0")
        condition_filter = list(ids)
        # 删除 pending 文件
        try: _Path(args.tasks_file).unlink()
        except: pass

    mod = modules[module_id]
    runner = ExperimentRunner(mod)

    print(f"模块: {mod.module_name} ({module_id})")
    print(f"模型: {runner.config.get('model', '?')}")
    print(f"条件数: {len(mod.build_conditions())}")
    print()

    overrides = {}
    if args.model: overrides["model"] = args.model
    if args.temperature is not None: overrides["temperature"] = args.temperature
    if getattr(args, "n_back", None) is not None: overrides["n_back"] = args.n_back
    for k in ("updates_list", "strategy", "positions"):
        v = getattr(args, k, "") or ""
        if v: overrides[k] = v

    tag = runner.run(
        condition_filter=condition_filter,
        seed=args.seed,
        n_trials=args.trials,
        k_repeats=args.repeats,
        overrides=overrides or None,
    )
    print(f"\n完成! Run tag: {tag}")
    print(f"结果目录: runs/{module_id}/{tag}/")


def cmd_dashboard() -> None:
    """启动控制面板."""
    import subprocess
    server = ROOT / "dashboard" / "server.py"
    print(f"启动控制面板: http://127.0.0.1:8765")
    subprocess.run([sys.executable, str(server)])


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SharkFin — 模块化 LLM 认知实验平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python launch.py --list                    列出所有模块和条件
  python launch.py --module pi_release       运行 PI release 实验
  python launch.py -m recall_rating -c TC WN 只跑 TC 和 WN 两个词对
  python launch.py --dashboard               启动 Web 控制面板
        """,
    )
    ap.add_argument("--list", action="store_true", help="列出所有模块")
    ap.add_argument("--module", "-m", type=str, help="要运行的模块 ID")
    ap.add_argument("--conditions", "-c", nargs="*", help="只跑指定条件")
    ap.add_argument("--model", type=str, help="覆盖 API model")
    ap.add_argument("--temperature", type=float, help="覆盖 temperature")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--trials", type=int, default=1, help="每个条件的 trial 数")
    ap.add_argument("--repeats", "-k", type=int, default=1, help="每个 trial 的重复次数")
    ap.add_argument("--n-back", type=int, default=2, help="n-back 值 (1-6, recall_rating 模块)")
    ap.add_argument("--updates-list", type=str, default="", help="PI sweep: 逗号分隔 updates 列表")
    ap.add_argument("--strategy", type=str, default="", help="PI sweep: A/C/A+C/逗号分隔策略")
    ap.add_argument("--positions", type=str, default="", help="PI sweep: 逗号分隔位置 (pct)")
    ap.add_argument("--tasks-file", type=str, default="", help="旧 drag 模式: tasks JSON 文件")
    ap.add_argument("--dashboard", "-d", action="store_true", help="启动控制面板")

    args = ap.parse_args()

    if args.dashboard:
        return cmd_dashboard()
    if args.list:
        return cmd_list()
    if args.module:
        return cmd_run(args.module, args)
    ap.print_help()


if __name__ == "__main__":
    main()
