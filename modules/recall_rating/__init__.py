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
    description="勾选要测试的语义类别对。每个词对会同时跑 recall (测 PI 释放) 和 rating (测序列评分偏差) 两种模式。Recall=多轮回忆实验组(第4轮切换类别), 对照=不切换基线, Rating=逐词valence评分。",
    extra_params=[
        {"key": "n_trials", "label": "试次数", "type": "int", "default": 1},
        {"key": "k_repeats", "label": "K Repeats", "type": "int", "default": 1},
        {"key": "seed", "label": "Seed", "type": "int", "default": 42},
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
            rpi_desc = f"释放{wp.rpi_expected*100:.0f}%" if wp.rpi_expected > 0.3 else "几乎无释放"
            conds += [
                Condition(id=f"{pid}_exp", name="Recall",
                          params={"pair_id": pid, "mode": "recall", "block": "exp",
                                  "group": pid, "group_label": f"{wp.name}",
                                  "desc": f"{wp.cat_a_name} → {wp.cat_b_name} (第4轮切换, RPI预期{wp.rpi_expected:.2f})",
                                  "rpi_expected": wp.rpi_expected}),
                Condition(id=f"{pid}_ctrl", name="对照",
                          params={"pair_id": pid, "mode": "recall", "block": "ctrl",
                                  "group": pid, "group_label": f"{wp.name}",
                                  "desc": f"全部{wp.cat_a_name}词, 不切换(基线)",
                                  "rpi_expected": wp.rpi_expected}),
                Condition(id=f"{pid}_rating", name="Rating",
                          params={"pair_id": pid, "mode": "rating",
                                  "group": pid, "group_label": f"{wp.name}",
                                  "desc": f"AB交替逐词valence评分, 测序列同化/对比偏差",
                                  "rpi_expected": wp.rpi_expected}),
            ]
        return conds

    def build_task(self, condition: Condition, seed: int) -> Task:
        p = condition.params; wp = self.pairs[p["pair_id"]]; rng = random.Random(seed)
        if p["mode"] == "recall":
            return self._recall_task(wp, p["block"], rng)
        return self._rating_task(wp, rng)

    def _recall_task(self, wp, block, rng):
        """多轮 recall: 逐 trial 呈现→立即回忆, 前轮 context 累积产生 PI."""
        from .tasks import generate_recall_design
        d = generate_recall_design(wp, self._wpt, self._n_ind, rng.randint(0, 100000))
        trials = d.experimental if block == "exp" else d.control
        turns = []
        for t in trials:
            words_str = ", ".join(t.words)
            turns.append({
                "user": f"[Trial {t.trial_index}/{len(trials)}] Study these words: {words_str}\nNow recall them exactly. Output only the words, separated by spaces.",
                "meta": {"trial": t.trial_index, "words": t.words, "cat": t.category},
            })
        return Task(
            messages=[{"role": "system", "content": RECALL_SYSTEM}],
            metadata={
                "multi_turn": True, "turns": turns,
                "mode": "recall", "pair_id": wp.pair_id, "rpi_expected": wp.rpi_expected,
                "trials": [{"trial": t.trial_index, "words": t.words, "cat": t.category} for t in trials],
            },
        )

    def _rating_task(self, wp, rng):
        """多轮 rating: 逐词呈现→立即评分, 前轮评分在 context 里产生序列依赖."""
        from .tasks import generate_rating_sequence
        seq = generate_rating_sequence(wp, self._n_per, self._dim, True, rng.randint(0, 100000))
        turns = []
        for item in seq.items:
            turns.append({
                "user": f"Rate this word for {self._dim} (1=lowest, 100=highest). Output ONLY one integer.\nWord: {item.word}",
                "meta": {"position": item.position, "word": item.word, "category": item.category},
            })
        return Task(
            messages=[{"role": "system", "content": RATING_SYSTEM}],
            metadata={
                "multi_turn": True, "turns": turns,
                "mode": "rating", "pair_id": wp.pair_id,
                "words": [t["meta"]["word"] for t in turns],
                "categories": [t["meta"]["category"] for t in turns],
            },
            overrides={"temperature": 0.7},
        )

    def score(self, task: Task, response: str) -> Result:
        turn_log = task.metadata.get("turn_log", [])
        if task.metadata["mode"] == "recall": return self._score_recall(task, turn_log)
        return self._score_rating(task, turn_log)

    def _score_recall(self, task, turn_log):
        """从多轮日志逐 trial 评分."""
        from .metrics import score_recall_trial, score_intrusions
        trials = task.metadata["trials"]
        scores = {}; prev_words = []; accs = []
        all_responses = []
        for ti, t in enumerate(trials):
            resp = turn_log[ti]["response"] if ti < len(turn_log) else ""
            s = score_recall_trial(t["words"], resp)
            i = score_intrusions(t["words"], prev_words, resp)
            scores[f"trial{t['trial']}_acc"] = s["accuracy"]
            scores[f"trial{t['trial']}_intr"] = i["n_intrusions"]
            accs.append(s["accuracy"]); prev_words.extend(t["words"])
            all_responses.append({"trial": t["trial"], "words_presented": t["words"],
                                  "response": resp, "accuracy": s["accuracy"],
                                  "intrusions": i["n_intrusions"], "intruded": i["intruded_words"]})
        if len(accs) >= 4:
            scores["rpi"] = accs[3] - accs[2]
            scores["pi_slope"] = (accs[0] - accs[2]) / 2.0
        scores["mean_accuracy"] = sum(accs) / len(accs) if accs else 0
        return Result(condition_id=task.metadata["pair_id"], scores=scores,
                      raw={"turn_log": all_responses})

    def _score_rating(self, task, turn_log):
        """从多轮日志逐词提取评分."""
        from .metrics import compute_serial_bias, compute_doG_amplitude
        words = task.metadata["words"]; cats = task.metadata["categories"]
        ratings = []
        for ti, entry in enumerate(turn_log):
            resp = entry["response"]
            nums = re.findall(r"\b(\d+)\b", resp)
            v = max(1, min(100, int(nums[0]))) if nums else 50
            ratings.append({"position": ti+1, "word": words[ti] if ti < len(words) else "?",
                            "category": cats[ti] if ti < len(cats) else "?", "rating": v,
                            "response": resp})
        bias = compute_serial_bias(ratings); dog = compute_doG_amplitude(ratings)
        return Result(condition_id=task.metadata["pair_id"], scores={
            "lag1_corr": bias.get("lag1_corr"),
            "assimilation_score": bias.get("assimilation_score"),
            "direction_tag": 1.0 if bias.get("direction") == "assimilation" else (-1.0 if bias.get("direction") == "contrast" else 0.0),
            "doG_A": dog.get("A"), "doG_half_amp": dog.get("half_amplitude"),
        }, raw={"ratings": ratings})
