"""任务生成器: recall 和 rating 两种模式的 trial 序列。

Recall 模式 (Brown-Peterson):
  3 个 induction trial (cat_a) + 1 个 switch trial (cat_b) = experimental
  4 个 trial 全部 cat_a = control
  每个 trial = 3 个词, 需要回忆

Rating 模式 (sequential):
  从 cat_a 和 cat_b 交替抽词, 逐词评分
  序列结构: [a1, b1, a2, b2, ...] 或随机插混
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .words import WordPair


# ---------------------------------------------------------------------------
# Recall trial structure
# ---------------------------------------------------------------------------
@dataclass
class RecallTrial:
    trial_index: int          # 1-based trial number in block
    words: list[str]          # 3 words to study & recall
    category: str             # "induction" | "switch" | "control"
    cat_name: str             # human-readable category name


@dataclass
class RecallDesign:
    """一个完整的 recall 实验设计 (experimental + control)"""
    pair_id: str
    induction_category: str
    switch_category: str
    words_per_trial: int      # default 3
    n_induction: int          # default 3
    experimental: list[RecallTrial]   # 3 induction + 1 switch
    control: list[RecallTrial]        # 4 same-category (baseline)


def generate_recall_design(
    wp: WordPair,
    words_per_trial: int = 3,
    n_induction: int = 3,
    seed: int = 0,
) -> RecallDesign:
    """为一个类别对生成 recall 实验设计.

    从 cat_a 和 cat_b 中各抽取所需数量的词, 构建:
      - experimental: 前 n_induction 个 trial 用 cat_a, 最后一个用 cat_b
      - control: 全部 trial 用 cat_a (不同词)
    """
    rng = random.Random(seed)

    # 总需求:
    #   experimental: n_induction trials (cat_a) + 1 switch trial (cat_b)
    #   control:      (n_induction + 1) trials (all cat_a)
    #   → cat_a = (2*n_induction + 1) * wpt,  cat_b = 1 * wpt
    total_a = (2 * n_induction + 1) * words_per_trial
    total_b = 1 * words_per_trial

    # 抽样: 词不够时用 choices (有放回), 够时用 sample (无放回)
    def _sample(pool: list[str], n: int) -> list[str]:
        if len(pool) >= n:
            return rng.sample(pool, n)
        # 不够, 先全取再补随机抽
        result = list(pool)
        result.extend(rng.choices(pool, k=n - len(pool)))
        rng.shuffle(result)
        return result

    a_shuffled = _sample(wp.cat_a_words, total_a)
    b_shuffled = _sample(wp.cat_b_words, total_b)

    # Build experimental trials
    exp_trials: list[RecallTrial] = []
    idx = 0
    for t in range(1, n_induction + 1):
        w = a_shuffled[idx:idx + words_per_trial]
        idx += words_per_trial
        exp_trials.append(RecallTrial(t, w, "induction", wp.cat_a_name))
    # Switch trial
    exp_trials.append(RecallTrial(n_induction + 1, b_shuffled, "switch", wp.cat_b_name))

    # Build control trials (all cat_a, last trial = different a words)
    ctrl_trials: list[RecallTrial] = []
    ctrl_start = idx  # remaining cat_a words start here
    for t in range(1, n_induction + 2):
        w = a_shuffled[ctrl_start:ctrl_start + words_per_trial]
        ctrl_start += words_per_trial
        ctrl_trials.append(RecallTrial(t, w, "control", wp.cat_a_name))

    return RecallDesign(
        pair_id=wp.pair_id,
        induction_category=wp.cat_a_name,
        switch_category=wp.cat_b_name,
        words_per_trial=words_per_trial,
        n_induction=n_induction,
        experimental=exp_trials,
        control=ctrl_trials,
    )


# ---------------------------------------------------------------------------
# Rating sequence structure
# ---------------------------------------------------------------------------
@dataclass
class RatingItem:
    position: int
    word: str
    category: str             # "a" | "b"
    cat_label: str            # human-readable


@dataclass
class RatingSequence:
    """一个完整的 rating 序列"""
    pair_id: str
    cat_a_name: str
    cat_b_name: str
    rating_dimension: str     # 评分维度: "valence" | "familiarity" | "concreteness"
    items: list[RatingItem]


def generate_rating_sequence(
    wp: WordPair,
    n_per_cat: int = 8,
    rating_dimension: str = "valence",
    interleave: bool = True,
    seed: int = 0,
) -> RatingSequence:
    """为类别对生成顺序评分序列.

    Args:
        wp: 词对
        n_per_cat: 每类抽多少个词
        rating_dimension: 评分维度
        interleave: True=交替 ABAB..., False=先全部 A 再全部 B (block design)
        seed: 随机种子
    """
    rng = random.Random(seed)

    a_words = rng.sample(wp.cat_a_words, min(n_per_cat, len(wp.cat_a_words)))
    b_words = rng.sample(wp.cat_b_words, min(n_per_cat, len(wp.cat_b_words)))

    items: list[RatingItem] = []
    pos = 0
    if interleave:
        # ABAB交替
        for i in range(max(len(a_words), len(b_words))):
            if i < len(a_words):
                pos += 1
                items.append(RatingItem(pos, a_words[i], "a", wp.cat_a_name))
            if i < len(b_words):
                pos += 1
                items.append(RatingItem(pos, b_words[i], "b", wp.cat_b_name))
    else:
        # Block: 先全部A, 再全部B
        for w in a_words:
            pos += 1
            items.append(RatingItem(pos, w, "a", wp.cat_a_name))
        for w in b_words:
            pos += 1
            items.append(RatingItem(pos, w, "b", wp.cat_b_name))

    return RatingSequence(
        pair_id=wp.pair_id,
        cat_a_name=wp.cat_a_name,
        cat_b_name=wp.cat_b_name,
        rating_dimension=rating_dimension,
        items=items,
    )
