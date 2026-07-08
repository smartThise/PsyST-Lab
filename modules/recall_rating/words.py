"""词表加载与管理。

从 data/mewhort_words.json 加载 Wickens (1970) 的 12 对语义类别的完整词表。
每对类别包含: 诱导类 (cat_a) + 释放类 (cat_b) + 已知的人类 RPI 值。
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent / "data" / "mewhort_words.json"


@dataclass
class WordPair:
    """一对语义类别的完整信息."""
    pair_id: str
    name: str
    source: str
    rpi_expected: float          # Wickens (1970) 实测 RPI
    cat_a_name: str               # 诱导类别名
    cat_a_words: list[str]        # 诱导类词汇
    cat_b_name: str               # 释放类别名
    cat_b_words: list[str]        # 释放类词汇

    @property
    def all_words(self) -> list[str]:
        return self.cat_a_words + self.cat_b_words

    @property
    def rpi_description(self) -> str:
        if self.rpi_expected >= 0.7:
            return "高释放"
        elif self.rpi_expected >= 0.4:
            return "中释放"
        elif self.rpi_expected >= 0.15:
            return "低释放"
        return "几乎无释放"

    def sample(self, n_per_cat: int = 8, rng: random.Random | None = None) -> tuple[list[str], list[str]]:
        """从每类中随机抽样指定数量的词."""
        rng = rng or random.Random()
        a = rng.sample(self.cat_a_words, min(n_per_cat, len(self.cat_a_words)))
        b = rng.sample(self.cat_b_words, min(n_per_cat, len(self.cat_b_words)))
        return a, b


def load_word_pairs(seed: int | None = None) -> dict[str, WordPair]:
    """加载所有 12 对类别."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"词表文件不存在: {DATA_PATH}")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    pairs = data.get("pairs", {})
    result: dict[str, WordPair] = {}
    for pid, info in pairs.items():
        wp = WordPair(
            pair_id=pid,
            name=info["name"],
            source=info["source"],
            rpi_expected=info["rpi"],
            cat_a_name=info["cat_a"]["name"],
            cat_a_words=list(info["cat_a"]["words"]),
            cat_b_name=info["cat_b"]["name"],
            cat_b_words=list(info["cat_b"]["words"]),
        )
        result[pid] = wp
    return result


def get_pair_ids() -> list[str]:
    """返回所有 pair_id,按 RPI 升序排列."""
    pairs = load_word_pairs()
    return sorted(pairs, key=lambda p: pairs[p].rpi_expected)
