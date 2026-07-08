"""条件定义 — 将 12 对类别映射为可运行的实验条件。

每个条件 = 一个类别对, 包含:
  - 元数据 (id, name, 预期 RPI)
  - 可同时用于 recall 和 rating 两种任务模式
"""
from __future__ import annotations

from .words import load_word_pairs, WordPair

# 懒加载 — 首次访问时才读 JSON
_PAIRS: dict[str, WordPair] | None = None


def _ensure_loaded() -> dict[str, WordPair]:
    global _PAIRS
    if _PAIRS is None:
        _PAIRS = load_word_pairs()
    return _PAIRS


def PAIRS() -> dict[str, WordPair]:
    """返回 {pair_id: WordPair}."""
    return dict(_ensure_loaded())


def list_conditions() -> list[dict]:
    """返回条件列表 (供 dashboard / launch UI 使用)."""
    pairs = _ensure_loaded()
    return [
        {
            "id": pid,
            "name": wp.name,
            "source": wp.source,
            "rpi_expected": wp.rpi_expected,
            "rpi_label": wp.rpi_description,
            "cat_a": wp.cat_a_name,
            "cat_b": wp.cat_b_name,
            "n_words_a": len(wp.cat_a_words),
            "n_words_b": len(wp.cat_b_words),
        }
        for pid, wp in pairs.items()
    ]


def get_pair(pair_id: str) -> WordPair:
    """获取指定 pair."""
    pairs = _ensure_loaded()
    if pair_id not in pairs:
        raise KeyError(f"未知类别对 {pair_id!r}, 可用: {list(pairs)}")
    return pairs[pair_id]
