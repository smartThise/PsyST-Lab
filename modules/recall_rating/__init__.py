"""Recall-Rating 模块."""
from __future__ import annotations
import random, re
from typing import Any

from core.base import BaseModule, Condition, Task, Result
from core.charts import (
    register_kpi, register_chart, register_column, register_launch,
    KPISpec, ChartSpec, ColumnSpec, LaunchConfig,
)

from .words import load_word_pairs, WordPair
from .prompts import RECALL_SYSTEM, RATING_SYSTEM

# ═══════════════════════════════════════════════════════════════
# 模块自描述 — 启动面板
# ═══════════════════════════════════════════════════════════════
register_launch("recall_rating", LaunchConfig(
    composer="checklist",
    description="勾选要测试的语义类别对。每个词对会同时跑 recall (测 PI 释放) 和 rating (测序列评分偏差) 两种模式。",
    extra_params=[
        {"key": "n_trials", "label": "试次数", "type": "int", "default": 1},
        {"key": "k_repeats", "label": "K Repeats", "type": "int", "default": 1},
    ],
))

# ═══════════════════════════════════════════════════════════════
# 模块自描述 — KPI / 图表 / 表格
# ═══════════════════════════════════════════════════════════════
register_kpi("recall_rating", KPISpec("n_pairs", "词对数", "n_conditions", aggregate="first", fmt="d"))
register_kpi("recall_rating", KPISpec("best_rpi", "最大 RPI", "rpi", aggregate="max", fmt=".3f", accent=True))
register_kpi("recall_rating", KPISpec("bias_dir", "评分偏差方向", "direction_tag", aggregate="first", fmt="str"))

register_chart("recall_rating", ChartSpec("rpi_bar", "RPI 实测 vs 预期", "bar", data_key="rpi"))
register_chart("recall_rating", ChartSpec("lag1_chart", "评分 Lag-1 相关", "bar", data_key="lag1_corr"))

register_column("recall_rating", ColumnSpec("rpi", "RPI (实测)", fmt=".3f"))
register_column("recall_rating", ColumnSpec("lag1_corr", "评分 Lag-1 相关", fmt=".3f"))
register_column("recall_rating", ColumnSpec("mean_accuracy", "平均回忆率", fmt="pct"))
register_column("recall_rating", ColumnSpec("assimilation_score", "同化分数", fmt=".3f"))
register_column("recall_rating", ColumnSpec("n", "样本数", fmt="d"))


class RRModule(BaseModule):
    module_id = "recall_rating"
    module_name = "Recall vs Rating 对比实验"

    def __init__(self):
        super().__init__()
        self._pairs = None; self._wpt = 3; self._n_ind = 3; self._n_per = 8; self._dim = "valence"

    @property
    def pairs(self):
        if self._pairs is None: self._pairs = load_word_pairs()
        return self._pairs

    def build_conditions(self) -> list[Condition]:
        conds = []
        for pid in sorted(self.pairs, key=lambda k: self.pairs[k].rpi_expected):
            wp = self.pairs[pid]
            conds += [
                Condition(id=f"{pid}_exp", name=f"[Recall] {wp.name}",
                          params={"pair_id": pid, "mode": "recall", "block": "exp"}),
                Condition(id=f"{pid}_ctrl", name=f"[Recall-对照] {wp.name}",
                          params={"pair_id": pid, "mode": "recall", "block": "ctrl"}),
                Condition(id=f"{pid}_rating", name=f"[Rating] {wp.name}",
                          params={"pair_id": pid, "mode": "rating"}),
            ]
        return conds

    def build_task(self, condition: Condition, seed: int) -> Task:
        p = condition.params; wp = self.pairs[p["pair_id"]]; rng = random.Random(seed)
        if p["mode"] == "recall":
            return self._recall_task(wp, p["block"], rng)
        return self._rating_task(wp, rng)

    def _recall_task(self, wp, block, rng):
        from .tasks import generate_recall_design
        d = generate_recall_design(wp, self._wpt, self._n_ind, rng.randint(0, 100000))
        trials = d.experimental if block == "exp" else d.control
        study = "\n".join(f"[Trial {t.trial_index}] Study: {', '.join(t.words)}" for t in trials)
        recs = "\n".join(f"Trial {t.trial_index}:" for t in trials)
        prompt = f"{'='*50}\n{study}\n{'='*50}\n\nRecall each trial:\n{recs}"
        return Task(
            messages=[{"role": "system", "content": RECALL_SYSTEM}, {"role": "user", "content": prompt}],
            metadata={"mode": "recall", "pair_id": wp.pair_id, "rpi_expected": wp.rpi_expected,
                      "trials": [{"trial": t.trial_index, "words": t.words, "cat": t.category} for t in trials]},
        )

    def _rating_task(self, wp, rng):
        from .tasks import generate_rating_sequence
        seq = generate_rating_sequence(wp, self._n_per, self._dim, True, rng.randint(0, 100000))
        words = "\n".join(i.word for i in seq.items)
        prompt = f"Rate each word for {self._dim} (1-100). One integer per line:\n{words}"
        return Task(
            messages=[{"role": "system", "content": RATING_SYSTEM}, {"role": "user", "content": prompt}],
            metadata={"mode": "rating", "pair_id": wp.pair_id, "words": [i.word for i in seq.items],
                      "categories": [i.category for i in seq.items]},
            overrides={"temperature": 0.7},
        )

    def score(self, task: Task, response: str) -> Result:
        if task.metadata["mode"] == "recall": return self._score_recall(task, response)
        return self._score_rating(task, response)

    def _score_recall(self, task, response):
        from .metrics import score_recall_trial, score_intrusions
        trials = task.metadata["trials"]; lines = response.strip().split("\n")
        trial_resp = {}; cur = None
        for ln in lines:
            ln = ln.strip()
            for t in trials:
                if ln.lower().startswith(f"trial {t['trial']}"):
                    cur = t["trial"]; _, _, rest = ln.partition(":"); trial_resp[cur] = rest.strip(); break
            else:
                if cur: trial_resp.setdefault(cur, ""); trial_resp[cur] += " " + ln
        scores = {}; prev = []; accs = []
        for t in trials:
            r = trial_resp.get(t["trial"], "")
            s = score_recall_trial(t["words"], r)
            i = score_intrusions(t["words"], prev, r)
            scores[f"trial{t['trial']}_acc"] = s["accuracy"]
            scores[f"trial{t['trial']}_intr"] = i["n_intrusions"]
            accs.append(s["accuracy"]); prev.extend(t["words"])
        if len(accs) >= 4:
            scores["rpi"] = accs[3] - accs[2]
            scores["pi_slope"] = (accs[0] - accs[2]) / 2.0
        scores["mean_accuracy"] = sum(accs) / len(accs) if accs else 0
        return Result(condition_id=task.metadata["pair_id"], scores=scores, raw={"response": response})

    def _score_rating(self, task, response):
        from .metrics import compute_serial_bias, compute_doG_amplitude
        words = task.metadata["words"]; cats = task.metadata["categories"]
        lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
        ratings = []
        for i, ln in enumerate(lines[:len(words)]):
            nums = re.findall(r"\b(\d+)\b", ln)
            v = max(1, min(100, int(nums[0]))) if nums else 50
            ratings.append({"position": i+1, "word": words[i], "category": cats[i], "rating": v})
        bias = compute_serial_bias(ratings); dog = compute_doG_amplitude(ratings)
        return Result(condition_id=task.metadata["pair_id"], scores={
            "lag1_corr": bias.get("lag1_corr"),
            "assimilation_score": bias.get("assimilation_score"),
            "direction_tag": 1.0 if bias.get("direction") == "assimilation" else (-1.0 if bias.get("direction") == "contrast" else 0.0),
            "doG_A": dog.get("A"), "doG_half_amp": dog.get("half_amplitude"),
        }, raw={"response": response})
