"""PI Release 模块."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from core.base import BaseModule, Condition, Task, Result
from core.utils import load_yaml
from core.charts import (
    register_kpi, register_chart, register_column, register_launch,
    KPISpec, ChartSpec, ColumnSpec, LaunchConfig,
)

from . import groups, pi_test, metrics

# ═══════════════════════════════════════════════════════════════
# 模块自描述 — 启动面板
# ═══════════════════════════════════════════════════════════════
groups.discover()
register_launch("pi_release", LaunchConfig(
    composer="drag",
    description="拖 feature 到任务框组成任务; 空任务 = 基线。多任务并行对比, 顺序敏感 (G1+G2 ≠ G2+G1)。无基线任务时后端自动补 G0。",
    extra_params=[
        {"key": "n_keys", "label": "Keys", "type": "int", "default": 46},
        {"key": "updates_per_key", "label": "Updates/Key", "type": "int", "default": 4},
        {"key": "n_trials", "label": "试次数", "type": "int", "default": 10},
        {"key": "k_repeats", "label": "K Repeats", "type": "int", "default": 3},
        {"key": "seed", "label": "Seed", "type": "int", "default": 42},
    ],
    features=groups.GROUP_META,  # [{id,name,desc,color,position,composable}]
))

# ═══════════════════════════════════════════════════════════════
# 模块自描述 — KPI / 图表 / 表格
# ═══════════════════════════════════════════════════════════════
register_kpi("pi_release", KPISpec("baseline", "基线准确率", "accuracy", aggregate="first", fmt="pct"))
register_kpi("pi_release", KPISpec("best_re",   "最佳 RE",     "re",       aggregate="max", fmt=".3f", accent=True, exclude_g0=True))
register_kpi("pi_release", KPISpec("avg_cp",    "平均 CP",     "cp",       aggregate="mean", fmt="pct"))

register_chart("pi_release", ChartSpec("acc_bar", "准确率按组", "bar", data_key="accuracy"))
register_chart("pi_release", ChartSpec("re_bar",  "RE 按组",   "bar", data_key="re"))

register_column("pi_release", ColumnSpec("accuracy", "准确率", fmt="pct"))
register_column("pi_release", ColumnSpec("re", "RE", fmt=".3f"))
register_column("pi_release", ColumnSpec("cp", "CP", fmt="pct"))
register_column("pi_release", ColumnSpec("robustness_delta", "鲁棒性Δ", fmt=".3f"))
register_column("pi_release", ColumnSpec("n_calls", "调用数", fmt="d"))


class PIModule(BaseModule):
    module_id = "pi_release"
    module_name = "PI Release 实验"

    def setup(self, config: dict[str, Any]) -> None:
        super().setup(config)
        exp = load_yaml(Path(__file__).resolve().parent.parent.parent / "config" / "experiment.yaml")
        pi_cfg = exp.get("pi_test", {}); eval_cfg = exp.get("eval", {})
        self.n_keys = int(pi_cfg.get("n_keys", 46))
        self.updates_per_key = int(pi_cfg.get("updates_per_key", 4))
        self.n_trials = int(pi_cfg.get("n_trials", 10))
        self.k_repeats = int(eval_cfg.get("k_repeats", 3))
        self.base_seed = int(pi_cfg.get("seed", 42))

    def build_conditions(self) -> list[Condition]:
        groups.discover()
        return [Condition(id=g["id"], name=g["name"], params=g) for g in groups.GROUP_META]

    def build_task(self, condition: Condition, seed: int) -> Task:
        test = pi_test.generate(n_keys=self.n_keys, updates_per_key=self.updates_per_key, seed=seed)
        msg = groups.build_message(condition.id, test, seed=seed)
        return Task(
            messages=[{"role": "user", "content": msg}],
            metadata={"group_id": condition.id, "test_keys": list(test.keys),
                      "test_first_values": dict(test.first_values)},
        )

    def score(self, task: Task, response: str) -> Result:
        from .pi_test import PITest as PT
        test = PT(keys=task.metadata["test_keys"], updates_per_key=self.updates_per_key, seed=0)
        test.first_values = task.metadata["test_first_values"]
        acc = metrics.accuracy_over_keys(response, test)
        return Result(condition_id=task.metadata["group_id"], scores={"accuracy": acc},
                      raw={"response": response})
