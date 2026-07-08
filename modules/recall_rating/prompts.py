"""提示词构建: recall 和 rating 两种模式。

Recall 模式: Brown-Peterson 即时回忆, 每个 trial = 3 词
Rating 模式: 顺序单词评分, 类似 serial-dependence-main 的 sequential rating
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
RECALL_SYSTEM = (
    "You are a participant in a memory experiment. "
    "In each trial, you will see a short list of words. "
    "Your task is to read them carefully and then write them back "
    "exactly as presented, separated by spaces. "
    "Do not add extra words, punctuation, or commentary."
)

RATING_SYSTEM = (
    "You are a participant in a behavioral experiment. "
    "Reply with exactly one integer between 1 and 100 inclusive. "
    "Digits only: no words, no decimals, and no punctuation."
)


# ---------------------------------------------------------------------------
# Recall prompts
# ---------------------------------------------------------------------------
def build_recall_prompt(trial_index: int, words: list[str]) -> str:
    """构建一个 recall trial 的 prompt.

    Args:
        trial_index: 1-based trial number
        words: 要回忆的单词列表
    """
    word_str = ", ".join(words)
    return (
        f"[Trial {trial_index}] "
        f"Read these words carefully: {word_str}\n"
        f"Now write the words back exactly. Output only the words, separated by spaces."
    )


def build_recall_prompt_distracted(trial_index: int, words: list[str]) -> str:
    """带干扰的 recall prompt — 先让模型重复, 再回忆.

    添加一个简单的算术干扰来模拟 Brown-Peterson 的计数干扰.
    """
    word_str = ", ".join(words)
    return (
        f"[Trial {trial_index}] "
        f"Read these words carefully: {word_str}\n"
        f"First, count backwards from 10 to 1, one number per line.\n"
        f"Then, write the words back exactly, separated by spaces."
    )


# ---------------------------------------------------------------------------
# Rating prompts — 参考 serial-dependence-main/src/prompts.py
# ---------------------------------------------------------------------------
def build_rating_prompt(
    word: str,
    dimension: str = "valence",
    emotion_type: str | None = None,
) -> str:
    """为单个词构建评分 prompt (复刻 SD 仓库的 build_user_prompt).

    Args:
        word: 要评分的词
        dimension: 评分维度 {"valence", "arousal", "concreteness", "emotion"}
        emotion_type: emotion 维度时的子类型
    """
    dim = dimension.strip().lower()

    if dim == "valence":
        instruction = (
            "Rate how the following single word makes a person feel on a 1-100 scale, "
            "where 1 means very negative, bad and 100 means very positive, good.\n"
        )
    elif dim == "arousal":
        instruction = (
            "Rate how the following single word makes a person feel on a 1-100 scale, "
            "where 1 means very calm, relaxed and 100 means very aroused, energized.\n"
        )
    elif dim == "emotion":
        emo = (emotion_type or "joy").strip().lower()
        instruction = (
            f"Rate how strongly the following single word is associated with {emo} "
            f"on a 1-100 scale, where 1 means associated with the LEAST {emo} "
            f"and 100 means associated with the MOST {emo}.\n"
        )
    else:  # concreteness (default)
        instruction = (
            "Rate the concreteness of the following single word on a 1-100 scale, "
            "where 1 means very abstract and 100 means very concrete.\n"
        )

    return (
        instruction
        + f"The word is: {word}\n"
        + "Output: only answer a single integer from 1 to 100. "
        "No extra text, no decimals, no punctuation."
    )


def build_generic_rating_prompt(word: str, dimension: str = "valence") -> str:
    """简便接口: 直接给词和维度, 返回完整 prompt."""
    return build_rating_prompt(word, dimension=dimension)
