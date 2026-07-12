"""通用实验运行器 — 不依赖任何具体模块.

职责: 遍历条件 → 生成 Task → 调 API → 评分 → 存结果.
模块只需实现 BaseModule 的三个抽象方法, runner 负责剩下的所有事.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from .base import BaseModule, Condition, Task, Result
from .api import APIClient
from .utils import RUNS_DIR, load_config, save_json, append_jsonl, make_run_tag


class ExperimentRunner:
    """通用实验运行器."""

    def __init__(self, module: BaseModule):
        self.module = module
        self.config = load_config()
        self.client = self._build_client()
        self._run_dir: Path | None = None
        self._tag: str = ""

    def _build_client(self, overrides: dict | None = None) -> APIClient:
        cfg = dict(self.config)
        if overrides:
            cfg.update(overrides)
        return APIClient(
            base_url=cfg["base_url"],
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "unknown"),
            temperature=cfg.get("temperature", 0.0),
            max_tokens=cfg.get("max_tokens", 64),
            max_retries=cfg.get("max_retries", 5),
            timeout=cfg.get("timeout", 60),
            extra_body=cfg.get("extra_body"),
        )

    def _run_multi_turn(self, task, temperature, max_tokens):
        """多轮对话: 逐轮调 API, 累积 context, 返回最终 response + 逐轮日志."""
        messages = [task.messages[0]]  # system
        turn_specs = task.metadata["turns"]  # [{user, meta}, ...]
        turn_log = []
        final_response = ""

        for ti, t in enumerate(turn_specs):
            messages.append({"role": "user", "content": t["user"]})
            resp = self.client.chat(messages, temperature=temperature, max_tokens=max_tokens)
            messages.append({"role": "assistant", "content": resp})
            entry = {"turn": ti, "user": t["user"], "response": resp}
            if "meta" in t:
                entry["meta"] = t["meta"]
            turn_log.append(entry)
            final_response = resp
            time.sleep(0.05)

        return final_response, turn_log

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def run(
        self,
        condition_filter: list[str] | None = None,
        seed: int = 42,
        n_trials: int = 1,
        k_repeats: int = 1,
        overrides: dict[str, Any] | None = None,
        progress_callback: callable | None = None,
    ) -> str:
        """运行实验.

        Args:
            condition_filter: 只跑指定条件 (默认全部)
            seed: 基础随机种子
            n_trials: 每个条件跑多少条不同数据
            k_repeats: 每条数据重复调用 API 几次 (取平均)
            overrides: 覆盖 config (model, temperature 等)
            progress_callback: 进度回调 (用于 dashboard 实时更新)

        Returns:
            run_tag
        """
        if overrides:
            for k, v in overrides.items():
                self.config[k] = v
            self.client = self._build_client(overrides)
        self.module.setup(self.config)  # 始终 setup, 确保模块读到最新 config

        conditions = self.module.build_conditions()
        if condition_filter:
            conditions = [c for c in conditions if c.id in condition_filter]
        if not conditions:
            raise ValueError("没有匹配的实验条件")

        self.module.pre_run(conditions)

        # 创建 run 目录
        self._tag = make_run_tag()
        self._run_dir = RUNS_DIR / self.module.module_id / self._tag
        self._run_dir.mkdir(parents=True, exist_ok=True)

        # 自动日志: runs/<module>/<tag>/run.log
        self._log_file = self._run_dir / "run.log"
        self._log_fp = open(self._log_file, "w", encoding="utf-8")

        def _log(msg):
            print(msg, flush=True)
            self._log_fp.write(msg + "\n")
            self._log_fp.flush()

        self._log = _log
        self._log(f"[{self.module.module_id}] run {self._tag}: {len(conditions)}条件 × {n_trials}trials × {k_repeats}repeats, seed={seed}")

        # 保存 run config
        save_json(self._run_dir / "run_config.json", {
            "module_id": self.module.module_id,
            "module_name": self.module.module_name,
            "model": self.config.get("model"),
            "conditions": [{"id": c.id, "name": c.name} for c in conditions],
            "n_trials": n_trials,
            "k_repeats": k_repeats,
            "seed": seed,
            "planned_total": len(conditions) * n_trials * k_repeats,
        })

        all_results: list[Result] = []
        n_cond = len(conditions)
        total = n_cond * n_trials * k_repeats
        done = 0

        for i, cond in enumerate(conditions):
            for trial in range(n_trials):
                try:
                    task = self.module.build_task(cond, seed + i * 1000 + trial)

                    for rep in range(k_repeats):
                        temp = task.overrides.get("temperature", self.client.temperature)
                        mtok = task.overrides.get("max_tokens", self.client.max_tokens)

                        # --- 多轮对话 ---
                        if task.metadata.get("multi_turn"):
                            response, turn_log = self._run_multi_turn(task, temp, mtok)
                            task.metadata["turn_log"] = turn_log
                        else:
                            response = self.client.chat(task.messages, temperature=temp, max_tokens=mtok)

                        result = self.module.score(task, response)
                        aid = self.client.last_extra.get("x_activation_id", "")
                        if aid:
                            result.raw["activation_id"] = aid
                        done += 1

                        scores_str = " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                              for k, v in list(result.scores.items())[:5])
                        self._log(f"  [{done}/{total}] {result.condition_id}: {scores_str}")

                        record = {
                            "module_id": self.module.module_id,
                            "condition_id": result.condition_id,
                            "trial": trial,
                            "repeat": rep,
                            "scores": result.scores,
                            "raw": result.raw,
                        }
                        if task.metadata.get("turn_log"):
                            record["turn_log"] = task.metadata["turn_log"]
                        append_jsonl(self._run_dir / "results.jsonl", record)
                        all_results.append(result)

                        if progress_callback:
                            progress_callback(done, total, cond.id)

                except Exception as exc:
                    self._log(f"  [ERROR] {cond.name}: {exc}")
                    done += 1

                time.sleep(0.05)  # 温和限流

        self.module.post_run(all_results)

        # 写汇总
        self._write_summary(conditions, all_results, n_trials, k_repeats)

        self._log(f"\n[runner] 完成 → {self._run_dir}")
        self._log_fp.close()
        return self._tag

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    def _write_summary(
        self,
        conditions: list[Condition],
        results: list[Result],
        n_trials: int,
        k_repeats: int,
    ) -> None:
        """生成 summary.json — 按条件聚合指标."""
        # 按条件聚合
        by_condition: dict[str, list[dict]] = {}
        for r in results:
            by_condition.setdefault(r.condition_id, []).append(r.scores)

        aggregated = []
        for cond in conditions:
            scores_list = by_condition.get(cond.id, [])
            if not scores_list:
                aggregated.append({"condition_id": cond.id, "condition_name": cond.name, "n": 0})
                continue

            # 对所有 trial×repeat 的 scores 取平均
            keys = set()
            for s in scores_list:
                keys.update(k for k, v in s.items() if v is not None)
            avg = {}
            for k in sorted(keys):
                vals = [s[k] for s in scores_list if s.get(k) is not None]
                if vals and isinstance(vals[0], (int, float)):
                    v = sum(vals) / len(vals)
                    avg[k] = v if v == v else None
            avg["n"] = len(scores_list)
            avg["condition_id"] = cond.id
            avg["condition_name"] = cond.name
            aggregated.append(avg)

        save_json(self._run_dir / "summary.json", {
            "module_id": self.module.module_id,
            "module_name": self.module.module_name,
            "tag": self._tag,
            "model": self.config.get("model", "?"),
            "conditions": aggregated,
            "n_trials": n_trials,
            "k_repeats": k_repeats,
        })

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    @property
    def tag(self) -> str:
        return self._tag
