"""n-back × 类别切换 × Rating 模块.

Recall 模式: semantic n-back stream + 中段类别切换 (Gong 2024 × Mewhort 2018)
Rating 模式: 逐词 valence 评分 (不变)
"""
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

# ══════════════════════════════════════════════════════
# 模块自描述 — 启动面板
# ══════════════════════════════════════════════════════
register_launch("recall_rating", LaunchConfig(
    composer="checklist",
    description="Recall=n-back流+中段类别切换(测WM容量+语义释放). 对照=同类别n-back. Rating=逐词valence评分(测序列同化/对比). n-back值越大越难.",
    extra_params=[
        {"key": "n_back", "label": "n-back 值", "type": "int", "default": 2},
        {"key": "n_trials", "label": "试次数", "type": "int", "default": 1},
        {"key": "k_repeats", "label": "K Repeats", "type": "int", "default": 1},
        {"key": "seed", "label": "Seed", "type": "int", "default": 42},
    ],
))

# ══════════════════════════════════════════════════════
# 模块自描述 — KPI / 图表 / 表格
# ══════════════════════════════════════════════════════
register_kpi("recall_rating", KPISpec("kpi_dprime", "n-back d'", "d_prime", aggregate="mean", fmt=".3f", accent=True))
register_kpi("recall_rating", KPISpec("kpi_hitrate", "Hit Rate", "hit_rate", aggregate="mean", fmt="pct"))
register_kpi("recall_rating", KPISpec("kpi_fa", "False Alarm", "false_alarm", aggregate="mean", fmt="pct"))

register_chart("recall_rating", ChartSpec("dprime_bar", "n-back d' 按词对", "bar", data_key="d_prime"))
register_chart("recall_rating", ChartSpec("lag1_chart", "评分 Lag-1 相关", "bar", data_key="lag1_corr"))

register_column("recall_rating", ColumnSpec("d_prime", "n-back d'", fmt=".3f"))
register_column("recall_rating", ColumnSpec("hit_rate", "Hit Rate", fmt="pct"))
register_column("recall_rating", ColumnSpec("false_alarm", "False Alarm", fmt="pct"))
register_column("recall_rating", ColumnSpec("lag1_corr", "评分 Lag-1 相关", fmt=".3f"))
register_column("recall_rating", ColumnSpec("assimilation_score", "同化分数", fmt=".3f"))
register_column("recall_rating", ColumnSpec("n", "样本数", fmt="d"))


class RRModule(BaseModule):
    module_id = "recall_rating"
    module_name = "n-back × 类别切换 + Rating"

    def __init__(self):
        super().__init__()
        self._pairs = None; self._n_back = 2; self._n_per = 8; self._dim = "valence"

    @property
    def pairs(self):
        if self._pairs is None: self._pairs = load_word_pairs()
        return self._pairs

    def setup(self, config: dict[str, Any]) -> None:
        super().setup(config)
        self._n_back = int(config.get("n_back", 2))

    def build_conditions(self) -> list[Condition]:
        conds = []
        for pid in sorted(self.pairs, key=lambda k: self.pairs[k].rpi_expected):
            wp = self.pairs[pid]
            conds += [
                Condition(id=f"{pid}_exp", name="Recall",
                          params={"pair_id": pid, "mode": "recall", "block": "exp",
                                  "group": pid, "group_label": f"{wp.name}",
                                  "desc": f"n-back流: {wp.cat_a_name}(前半) → {wp.cat_b_name}(后半) 类别切换",
                                  "rpi_expected": wp.rpi_expected}),
                Condition(id=f"{pid}_ctrl", name="对照",
                          params={"pair_id": pid, "mode": "recall", "block": "ctrl",
                                  "group": pid, "group_label": f"{wp.name}",
                                  "desc": f"n-back流: 全程{wp.cat_a_name}, 不切换(基线)",
                                  "rpi_expected": wp.rpi_expected}),
                Condition(id=f"{pid}_rating", name="Rating",
                          params={"pair_id": pid, "mode": "rating",
                                  "group": pid, "group_label": f"{wp.name}",
                                  "desc": f"AB交替逐词valence评分, 测序列同化/对比偏差",
                                  "rpi_expected": wp.rpi_expected}),
            ]
        return conds

    # ══════════════════════════════════════════════════════
    # Task builders
    # ══════════════════════════════════════════════════════
    def build_task(self, condition: Condition, seed: int) -> Task:
        p = condition.params; wp = self.pairs[p["pair_id"]]; rng = random.Random(seed)
        task = self._nback_task(wp, p["block"], rng) if p["mode"] == "recall" else self._rating_task(wp, rng)
        task.metadata["condition_id"] = condition.id
        return task

    def _nback_task(self, wp, block, rng):
        """n-back 流 + 类别切换.
        24 词/block, 8 matches, Gong 2024 规格.
        experimental: 前半 cat_a → 后半 cat_b
        control:      全程 cat_a
        """
        n = self._n_back; seq_len = 24; switch_pos = 13
        n_matches = 8

        # 确定哪些位置是 match (> n)
        match_positions = set(rng.sample(range(n, seq_len), n_matches))

        # 构建流
        stream = []
        for pos in range(seq_len):
            if block == "exp":
                cat = "a" if pos < switch_pos else "b"
            else:
                cat = "a"
            pool = wp.cat_a_words if cat == "a" else wp.cat_b_words

            if pos in match_positions:
                word = stream[pos - n]["word"]  # 匹配 n-back 位置
                is_match = True
            else:
                ref = stream[pos - n]["word"] if pos >= n else None
                # 确保不产生意外 match
                if len(pool) > 1 and ref:
                    w = rng.choice([x for x in pool if x != ref])
                else:
                    w = rng.choice(pool)
                word = w
                is_match = False
            stream.append({"pos": pos, "word": word, "match": is_match, "cat": cat})

        # 多轮对话: 逐位呈现
        turns = []
        for s in stream:
            cat_tag = f" [{wp.cat_a_name}]" if s["cat"] == "a" else f" [{wp.cat_b_name}]" if block == "exp" else ""
            turns.append({
                "user": f"Word: {s['word']}{cat_tag}\nn={n}-back: same as {n} steps ago? Output ONLY 'm' or '-'.",
                "meta": {"pos": s["pos"], "word": s["word"], "match": s["match"], "cat": s["cat"]},
            })
        return Task(
            messages=[{"role": "system", "content": RECALL_SYSTEM}],
            metadata={
                "multi_turn": True, "turns": turns,
                "mode": "recall", "pair_id": wp.pair_id, "rpi_expected": wp.rpi_expected,
                "n_back": n, "block": block, "stream": stream,
            },
        )

    def _rating_task(self, wp, rng):
        """多轮 rating: 逐词呈现→立即评分 (不变)."""
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

    # ══════════════════════════════════════════════════════
    # Scoring
    # ══════════════════════════════════════════════════════
    def score(self, task: Task, response: str) -> Result:
        turn_log = task.metadata.get("turn_log", [])
        if task.metadata["mode"] == "recall": return self._score_nback(task, turn_log)
        return self._score_rating(task, turn_log)

    def _score_nback(self, task, turn_log):
        """n-back 评分: hit rate / false alarm / d' (Gong 2024 标准)."""
        stream = task.metadata["stream"]
        n = task.metadata["n_back"]
        hits = 0; misses = 0; false_alarms = 0; correct_rejects = 0

        entries = []
        for i, s in enumerate(stream):
            resp = turn_log[i]["response"].strip().lower() if i < len(turn_log) else ""
            is_m = "m" in resp and "-" not in resp  # 判定为 m 响应
            is_match = s["match"]
            # 排除前 n 个位置 (不可能有 match)
            if i < n:
                entries.append({"pos": i, "word": s["word"], "match": is_match,
                                "response": resp, "type": "skip", "cat": s["cat"]})
                continue
            if is_match and is_m: hits += 1; t = "hit"
            elif is_match and not is_m: misses += 1; t = "miss"
            elif not is_match and is_m: false_alarms += 1; t = "false_alarm"
            else: correct_rejects += 1; t = "correct_reject"
            entries.append({"pos": i, "word": s["word"], "match": is_match,
                            "response": resp, "type": t, "cat": s["cat"]})

        total_match = hits + misses
        total_nonmatch = false_alarms + correct_rejects
        hit_rate = hits / total_match if total_match > 0 else 0
        fa_rate = false_alarms / total_nonmatch if total_nonmatch > 0 else 0

        # d' (带 ±3 cap, 避免极端值)
        def norm_z(p):
            """逆正态CDF近似 (Abramowitz & Stegun 26.2.23)."""
            import math
            p = max(0.001, min(0.999, p))
            if p < 0.5: return -norm_z(1 - p)
            t = math.sqrt(max(0, -2 * math.log(1 - p)))
            c = [2.515517, 0.802853, 0.010328]
            d = [1.0, 1.432788, 0.189269, 0.001308]
            num = c[0] + c[1]*t + c[2]*t*t
            den = d[0] + d[1]*t + d[2]*t*t + d[3]*t*t*t
            return t - num / den
        d_prime = max(-3, min(3, norm_z(hit_rate) - norm_z(fa_rate)))

        # 按类别拆 (前半 vs 后半)
        first_half = [e for e in entries if e["cat"] == "a" and e["type"] != "skip"]
        second_half = [e for e in entries if e["cat"] != "a" and e["type"] != "skip"]
        def _acc(es): return sum(1 for e in es if e["type"] in ("hit","correct_reject"))/len(es) if es else 0

        scores = {
            "d_prime": d_prime, "hit_rate": hit_rate, "false_alarm": fa_rate,
            "acc_first_half": _acc(first_half), "acc_second_half": _acc(second_half),
            "release": _acc(second_half) - _acc(first_half),
            "hits": hits, "misses": misses, "false_alarms": false_alarms, "correct_rejects": correct_rejects,
        }
        return Result(condition_id=task.metadata.get("condition_id") or task.metadata["pair_id"], scores=scores,
                      raw={"entries": entries, "n_back": n, "block": task.metadata["block"]})

    def _score_rating(self, task, turn_log):
        """评分模式 (不变)."""
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
        return Result(condition_id=task.metadata.get("condition_id") or task.metadata["pair_id"], scores={
            "lag1_corr": bias.get("lag1_corr"),
            "assimilation_score": bias.get("assimilation_score"),
            "direction_tag": 1.0 if bias.get("direction") == "assimilation" else (-1.0 if bias.get("direction") == "contrast" else 0.0),
            "doG_A": dog.get("A"), "doG_half_amp": dog.get("half_amplitude"),
        }, raw={"ratings": ratings})
