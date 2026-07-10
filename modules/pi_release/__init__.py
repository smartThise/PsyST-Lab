"""PI Release 模块 — 支持单参和扫参两种模式."""
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

def _parse_position(s: str) -> list[float]:
    """'50+2.5' → [50.0, 2.5]."""
    return [float(x.strip()) for x in s.split("+") if x.strip()] or [2.5]

# ════════════════════════════════════════════════
# 启动面板
# ════════════════════════════════════════════════
groups.discover()
register_launch("pi_release", LaunchConfig(
    composer="drag",
    description="扫参: updates_list=3,6,12,24,48,97,197,400 + strategy=G0,G1,...,G2+G8s,... + positions=2.5,50+2.5,... 三个参数笛卡尔积。留空=旧drag模式。",
    extra_params=[
        {"key": "n_keys", "label": "Keys", "type": "int", "default": 46},
        {"key": "updates_per_key", "label": "Updates/Key (单值)", "type": "int", "default": 4},
        {"key": "updates_list", "label": "Updates列表 (逗号分隔)", "type": "str", "default": ""},
        {"key": "strategy", "label": "策略列表 (逗号分隔)", "type": "str", "default": ""},
        {"key": "positions", "label": "位置列表 (逗号分隔, 如2.5,50+2.5)", "type": "str", "default": ""},
        {"key": "n_trials", "label": "试次数", "type": "int", "default": 10},
        {"key": "k_repeats", "label": "K Repeats", "type": "int", "default": 3},
        {"key": "seed", "label": "Seed", "type": "int", "default": 42},
    ],
    features=groups.GROUP_META,
))

# ════════════════════════════════════════════════
# KPI / 图表
# ════════════════════════════════════════════════
register_kpi("pi_release", KPISpec("baseline", "基线准确率", "accuracy", aggregate="first", fmt="pct"))
register_kpi("pi_release", KPISpec("best_re", "最佳 RE", "re", aggregate="max", fmt=".3f", accent=True, exclude_g0=True))
register_kpi("pi_release", KPISpec("avg_cp", "平均 CP", "cp", aggregate="mean", fmt="pct"))
# 基础图表 (兼容旧数据 + 扫参)
register_chart("pi_release", ChartSpec("acc_bar", "准确率按条件", "bar", data_key="accuracy"))
register_chart("pi_release", ChartSpec("re_bar", "RE 按条件", "bar", data_key="re"))
# 扫参图表: 多策略曲线 (仅扫参数据有效, 旧数据无 sweep 维度则跳过)
register_chart("pi_release", ChartSpec("sweep_line", "扫参: 精度 vs updates (pos=2.5%)", "line-series",
    data_key="accuracy", series_key="strategy", x_key="updates", x_label="Updates", y_label="准确率"))
register_chart("pi_release", ChartSpec("sweep_heat", "扫参: 精度热力图 (updates × position)", "heatmap",
    data_key="accuracy", x_key="updates", y_key="position", x_label="Updates", y_label="位置"))
# surface3d 仅在扫参数据有值时生效, 先注释, 跑完扫参再开启
# register_chart("pi_release", ChartSpec("sweep_3d", "扫参: 3D曲面", "surface3d", ...))
# 表格列 (新旧兼容)
register_column("pi_release", ColumnSpec("accuracy", "准确率", fmt="pct"))
register_column("pi_release", ColumnSpec("re", "RE", fmt=".3f"))
register_column("pi_release", ColumnSpec("cp", "CP", fmt="pct"))
register_column("pi_release", ColumnSpec("robustness_delta", "鲁棒性Δ", fmt=".3f"))
register_column("pi_release", ColumnSpec("updates", "Updates", fmt="d"))
register_column("pi_release", ColumnSpec("n_calls", "调用数", fmt="d"))


class PIModule(BaseModule):
    module_id = "pi_release"
    module_name = "PI Release 实验"

    def __init__(self):
        super().__init__()
        self._sweep = False

    def setup(self, config: dict[str, Any]) -> None:
        super().setup(config)
        exp = load_yaml(Path(__file__).resolve().parent.parent.parent / "config" / "experiment.yaml")
        pi_cfg = exp.get("pi_test", {}); eval_cfg = exp.get("eval", {})
        self.n_keys = int(pi_cfg.get("n_keys", 46))
        self.n_trials = int(pi_cfg.get("n_trials", 10))
        self.k_repeats = int(eval_cfg.get("k_repeats", 3))
        self.base_seed = int(pi_cfg.get("seed", 42))

        # 扫参参数
        ul = config.get("updates_list", "")
        self._updates_list = [int(x) for x in ul.split(",") if x.strip()] if ul else None
        self._upk = int(config.get("updates_per_key", 4))  # 单值模式
        strat = config.get("strategy", "")
        self._strat_list = self._parse_strategies(strat) if strat else None
        pos = config.get("positions", "")
        self._pos_keys = [p.strip() for p in pos.split(",") if p.strip()] if pos else ["2.5"]

        # 模式判断
        self._sweep = bool(self._updates_list)

    def _parse_strategies(self, s: str) -> list[str]:
        return [x.strip() for x in s.split(",") if x.strip()]

    # ══════════════════════════════════════════
    # Conditions
    # ══════════════════════════════════════════
    def build_conditions(self) -> list[Condition]:
        if self._sweep:
            return self._build_sweep_conditions()
        # 旧模式: drag composer
        groups.discover()
        return [Condition(id=g["id"], name=g["name"], params=g) for g in groups.GROUP_META]

    def _build_sweep_conditions(self) -> list[Condition]:
        conds = []
        updates = self._updates_list
        strats = self._strat_list or ALL_STRATEGIES
        for upk in updates:
            for sname in strats:
                for pkey in self._pos_keys:
                    pcts = _parse_position(pkey)
                    cid = f"{sname}_u{upk}_p{pkey.replace('+','x')}"
                    cname = f"{sname} @{upk}upk pos={pkey}"
                    conds.append(Condition(id=cid, name=cname, params={
                        "strategy": sname, "updates_per_key": upk,
                        "position_pcts": pcts, "position_key": pkey,
                    }))
        return conds

    # ══════════════════════════════════════════
    # Task builder
    # ══════════════════════════════════════════
    def build_task(self, condition: Condition, seed: int) -> Task:
        p = condition.params
        if self._sweep:
            return self._build_sweep_task(p, seed)
        # 旧模式
        upk = self._upk
        test = pi_test.generate(n_keys=self.n_keys, updates_per_key=upk, seed=seed)
        msg = groups.build_message(condition.id, test, seed=seed)
        return Task(
            messages=[{"role": "user", "content": msg}],
            metadata={"group_id": condition.id, "test_keys": list(test.keys),
                      "test_first_values": dict(test.first_values),
                      "updates_per_key": upk},
        )

    def _build_sweep_task(self, params: dict, seed: int) -> Task:
        sname = params["strategy"]
        upk = params["updates_per_key"]
        pcts = params["position_pcts"]
        pkey = params["position_key"]

        test = pi_test.generate(n_keys=self.n_keys, updates_per_key=upk, seed=seed)

        # 策略 → feature 列表
        feats = [f.strip() for f in sname.split("+")]

        # 多位置注入
        from .groups._common import assemble_multi_position
        from .groups._common import paper_instruction, paper_stream_block
        from .pi_test import build_base_query

        instruction = paper_instruction(test)
        msg = assemble_multi_position(test, instruction, feats, pcts, seed=seed)

        return Task(
            messages=[{"role": "user", "content": msg}],
            metadata={
                "group_id": sname, "test_keys": list(test.keys),
                "test_first_values": dict(test.first_values),
                "updates_per_key": upk, "position_pcts": pcts,
                "position_key": pkey, "strategy": sname,
            },
        )

    # ══════════════════════════════════════════
    # Scoring
    # ══════════════════════════════════════════
    def score(self, task: Task, response: str) -> Result:
        from .pi_test import PITest as PT
        test = PT(keys=task.metadata["test_keys"], updates=[], targets={}, first_values={}, stream_text="")
        test.first_values = task.metadata["test_first_values"]
        acc = metrics.accuracy_over_keys(response, test)
        scores = {"accuracy": acc}
        if self._sweep:
            scores["updates"] = task.metadata.get("updates_per_key", 0)
        return Result(condition_id=task.metadata.get("group_id", "?"),
                      scores=scores, raw={"response": response})
