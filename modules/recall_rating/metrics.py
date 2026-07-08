"""评分与指标: recall 和 rating 两种模式。

Recall 指标:
  - 逐 trial 正确率 (0-1, 最多 1.0 = 全对)
  - RPI = release 幅度 = trial_4_experimental − trial_4_control
  - 入侵率: 回忆时出现之前 trial 的词的比率

Rating 指标:
  - 顺序偏差: 当前 rating 是否被上一个 trial 的 rating/刺激值吸引
  - doG (derivative-of-Gaussian) 振幅: 沿连续维度 Δ 的调谐曲线
"""
from __future__ import annotations

import re
import math
from statistics import mean
from typing import Any

# numpy 可选 — 有它时 doG 拟合和线性回归更准确, 没有也可降级
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Recall scoring
# ---------------------------------------------------------------------------
def _clean_word(w: str) -> str:
    """规范化: 去标点、转小写."""
    return re.sub(r"[^\w]", "", w).strip().lower()


def score_recall_trial(expected: list[str], response: str) -> dict[str, Any]:
    """评一个 recall trial 的分数.

    Returns:
        dict with:
          - n_correct: 正确回忆的词数
          - n_total: 应回忆的词数
          - accuracy: n_correct / n_total
          - recalled: 实际回忆的词列表
          - missing: 漏掉的词
    """
    expected_clean = [_clean_word(w) for w in expected]
    # 从响应中提取词
    response_clean = [_clean_word(t) for t in response.split()]
    response_set = set(response_clean)

    n_correct = sum(1 for w in expected_clean if w in response_set)
    n_total = len(expected_clean)
    accuracy = n_correct / n_total if n_total > 0 else 0.0
    missing = [w for w in expected_clean if w not in response_set]

    return {
        "n_correct": n_correct,
        "n_total": n_total,
        "accuracy": accuracy,
        "recalled": response_clean,
        "missing": missing,
    }


def score_intrusions(
    expected: list[str],
    all_previous_words: list[str],
    response: str,
) -> dict[str, Any]:
    """检测入侵: 当前 trial 的响应中是否出现了之前 trial 的词.

    Returns:
        dict with n_intrusions, intruded_words, intrusion_rate
    """
    expected_clean = {_clean_word(w) for w in expected}
    prev_clean = [_clean_word(w) for w in all_previous_words if _clean_word(w) not in expected_clean]
    response_clean = [_clean_word(t) for t in response.split()]

    intruded = [w for w in response_clean if w in prev_clean]
    n_intrusions = len(intruded)
    intrusion_rate = n_intrusions / len(response_clean) if response_clean else 0.0

    return {
        "n_intrusions": n_intrusions,
        "intruded_words": intruded,
        "intrusion_rate": intrusion_rate,
    }


def compute_rpi(
    exp_trial_scores: list[dict],
    ctrl_trial_scores: list[dict],
) -> dict[str, Any]:
    """计算 Release from PI.

    RPI = accuracy(switch trial, experimental) − accuracy(same trial, control)

    如果 RPI > 0: 类别切换后回忆准确率回升 = release 成功
    如果 RPI ≈ 0: 无释放
    """
    if len(exp_trial_scores) < 4 or len(ctrl_trial_scores) < 4:
        return {"rpi": None, "error": "trial 数量不足 (需要 ≥4)"}

    # Trial 4 (index 3) is the switch trial
    exp_t4 = exp_trial_scores[3].get("accuracy", 0.0)
    ctrl_t4 = ctrl_trial_scores[3].get("accuracy", 0.0)

    # PI buildup: accuracy trend across induction trials 1-3
    pi_curve_exp = [exp_trial_scores[i].get("accuracy", 0.0) for i in range(3)]
    pi_curve_ctrl = [ctrl_trial_scores[i].get("accuracy", 0.0) for i in range(3)]

    rpi = exp_t4 - ctrl_t4

    return {
        "rpi": rpi,
        "exp_trial4_acc": exp_t4,
        "ctrl_trial4_acc": ctrl_t4,
        "pi_curve_experimental": pi_curve_exp,
        "pi_curve_control": pi_curve_ctrl,
        "pi_slope_exp": _linear_slope(pi_curve_exp),
        "pi_slope_ctrl": _linear_slope(pi_curve_ctrl),
    }


def _linear_slope(values: list[float]) -> float:
    """拟合线性趋势的斜率。负值 = PI 累积 (正确率下降)."""
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    # 简单的最小二乘斜率
    n = len(x)
    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x)**2)
    return float(slope)


# ---------------------------------------------------------------------------
# Rating sequential bias scoring
# ---------------------------------------------------------------------------
def compute_serial_bias(ratings: list[dict]) -> dict[str, Any]:
    """计算顺序评分偏差.

    对 ratings 序列 (每个 dict 含 position, rating, word),
    计算 lag-1 偏差: rating_t 与 rating_{t-1} 的相关/吸引.

    Returns:
        dict with lag1_corr, mean_shift, assimilation_score
    """
    if len(ratings) < 2:
        return {"lag1_corr": None, "error": "评分太少 (<2)"}

    r = [max(1, min(100, d.get("rating", 50) or 50)) for d in ratings]
    r_t = r[1:]      # ratings at positions 2..N
    r_tm1 = r[:-1]   # ratings at positions 1..N-1

    # Lag-1 Pearson correlation
    lag1_corr = float(np.corrcoef(r_t, r_tm1)[0, 1]) if len(r_t) > 1 else None

    # Mean shift: 跨类别边界时的评分跳跃
    # 找到类别切换点, 计算前后评分的平均变化
    cat_boundaries = []
    for i in range(1, len(ratings)):
        if ratings[i].get("category") != ratings[i-1].get("category"):
            cat_boundaries.append(i)

    boundary_shifts = []
    for b in cat_boundaries:
        if b >= 1 and b < len(r):
            shift = r[b] - r[b-1]
            boundary_shifts.append(shift)

    mean_boundary_shift = float(np.mean(boundary_shifts)) if boundary_shifts else None

    # Assimilation score: positive = assimilation (被前一个 trial 吸引),
    #                    negative = contrast (被前一个 trial 排斥)
    # 简单版: lag1_corr > 0 = assimilation, < 0 = contrast
    assimilation_score = lag1_corr if lag1_corr is not None else None

    return {
        "lag1_corr": lag1_corr,
        "mean_boundary_shift": mean_boundary_shift,
        "n_boundary_shifts": len(boundary_shifts),
        "assimilation_score": assimilation_score,
        "direction": (
            "assimilation" if (assimilation_score or 0) > 0.05
            else "contrast" if (assimilation_score or 0) < -0.05
            else "null"
        ),
    }


def compute_doG_amplitude(ratings: list[dict]) -> dict[str, Any]:
    """拟合 derivative-of-Gaussian 调谐曲线 (复用 SD 仓库的 doG 思路).

    用前一个 trial 的 rating 作为 "stimulus value",
    当前 trial 的 rating 作为 "response",
    拟合 doG(Δ) = A · Δ · exp(−½(Δ/σ)²).

    Returns:
        dict with A (振幅), sigma (宽度), half_amp, r2
    """
    if len(ratings) < 4:
        return {"A": None, "error": "数据点太少 (<4)"}

    # Build delta and error arrays
    r_vals = [max(1, min(100, d.get("rating", 50) or 50)) for d in ratings]
    deltas = []
    errors = []
    for i in range(1, len(r_vals)):
        delta = r_vals[i-1] - r_vals[i]  # prev - current
        # error = current − mean([prev, current])  (残差)
        mean_val = (r_vals[i-1] + r_vals[i]) / 2.0
        error = r_vals[i] - mean_val
        deltas.append(delta)
        errors.append(error)

    deltas = np.array(deltas, dtype=float)
    errors = np.array(errors, dtype=float)

    try:
        from scipy.optimize import curve_fit

        def dog_model(delta, c0, A, sigma):
            return c0 + A * delta * np.exp(-0.5 * (delta / max(sigma, 1e-6))**2)

        popt, _ = curve_fit(dog_model, deltas, errors, p0=[0, 0.001, 20], maxfev=5000)
        c0, A, sigma = popt
        yhat = dog_model(deltas, c0, A, sigma)
        ss_res = np.sum((errors - yhat)**2)
        ss_tot = np.sum((errors - np.mean(errors))**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        half_amp = abs(A) * sigma / 2.0

        return {
            "c0": float(c0),
            "A": float(A),
            "sigma": float(sigma),
            "half_amplitude": float(half_amp),
            "r2": float(r2),
            "direction": "assimilation" if A > 0 else "contrast",
        }
    except Exception:
        return {"A": None, "error": "doG 拟合失败"}


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------
def summarize_run(
    pair_id: str,
    rpi_expected: float,
    recall_results: dict[str, Any] | None,
    rating_results: dict[str, Any] | None,
) -> dict[str, Any]:
    """生成单个条件 (类别对) 的汇总."""
    summary = {
        "pair_id": pair_id,
        "rpi_expected": rpi_expected,
    }

    if recall_results:
        summary["recall"] = {
            "rpi_observed": recall_results.get("rpi"),
            "pi_slope_exp": recall_results.get("pi_slope_exp"),
            "pi_slope_ctrl": recall_results.get("pi_slope_ctrl"),
        }

    if rating_results:
        bias = rating_results.get("serial_bias", {})
        dog = rating_results.get("doG", {})
        summary["rating"] = {
            "lag1_corr": bias.get("lag1_corr"),
            "assimilation_score": bias.get("assimilation_score"),
            "direction": bias.get("direction"),
            "doG_A": dog.get("A"),
            "doG_half_amp": dog.get("half_amplitude"),
        }

    return summary
