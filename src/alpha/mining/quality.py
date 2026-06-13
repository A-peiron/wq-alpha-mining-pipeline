from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional


# ─── 自适应阈值参数 ────────────────────────────────────────────

_REGION_FACTORS: dict[str, float] = {
    "USA": 1.0, "EUR": 0.95, "GLB": 0.95,
    "ASI": 0.90, "CHN": 0.90, "IND": 0.90,
    "KOR": 0.85, "HKG": 0.85, "JPN": 0.90, "TWN": 0.85,
}

_CATEGORY_FACTORS: dict[str, float] = {
    "pv": 1.0,
    "analyst": 1.1,
    "fundamental": 0.95,
    "news": 0.85,
    "other": 1.0,
}

_BASE_SHARPE = {"USER": 1.25, "CONSULTANT": 1.58}
_BASE_FITNESS = 1.0
_SELF_CORR_MAX = 0.7
_TURNOVER_MIN = 0.01
_TURNOVER_MAX = 0.70
_MARGIN_MIN_USA_EUR = 10.0
_MARGIN_MIN_GLB_ASI = 15.0


@dataclass
class QualityResult:
    quality_status: str
    signal_light: str
    quality_tier: str
    reasons: list[str]
    diagnosis: dict
    official_check_status: str = "unknown"
    fallback_used: bool = False
    fallback_reason: str = ""
    review_priority: int = 0


def _to_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _adaptive_thresholds(mode: str = "USER", region: str = "USA",
                          dataset_category: str = "other", delay: int = 1) -> dict:
    region_f = _REGION_FACTORS.get(region, 0.90)
    cat_f = _CATEGORY_FACTORS.get(dataset_category, 1.0)
    base_sharpe = _BASE_SHARPE.get(mode, 1.25)
    adj_sharpe = base_sharpe * region_f * cat_f
    adj_fitness = _BASE_FITNESS * region_f * cat_f
    margin_min = _MARGIN_MIN_GLB_ASI if region in ("GLB", "ASI", "IND", "HKG", "JPN", "CHN", "KOR", "TWN") else _MARGIN_MIN_USA_EUR
    return {
        "sharpe_min": adj_sharpe,
        "fitness_min": adj_fitness,
        "self_corr_max": _SELF_CORR_MAX,
        "turnover_min": _TURNOVER_MIN,
        "turnover_max": _TURNOVER_MAX,
        "margin_min": margin_min,
        "optimize_min": 0.3,
        "optimize_max": adj_sharpe,
    }


def parse_official_checks(brain_checks: Optional[list[dict]]) -> tuple[str, list[str]]:
    if not brain_checks:
        return "unavailable", []

    failed: list[str] = []
    has_definitive = False
    for check in brain_checks:
        result = str(check.get("result", "")).upper()
        name = check.get("name", "")
        if result == "FAIL":
            failed.append(name)
            has_definitive = True
        elif result in ("PASS", "WARNING"):
            has_definitive = True

    if not has_definitive:
        return "pending", []

    return ("fail" if failed else "pass"), failed


def evaluate_alpha(
    metrics: dict,
    mode: str = "USER",
    region: str = "USA",
    dataset_category: str = "other",
    delay: int = 1,
    brain_checks: Optional[list[dict]] = None,
) -> QualityResult:
    sharpe = abs(_to_float(metrics.get("sharpe")))
    fitness = abs(_to_float(metrics.get("fitness")))
    turnover = _to_float(metrics.get("turnover"))
    margin = _to_float(metrics.get("margin"))
    self_corr = _to_float(metrics.get("self_corr"), default=0.0)

    # 从 metrics 中读出 brain_checks（check.py 会注入）
    bc_raw = brain_checks or metrics.get("brain_checks") or metrics.get("checks") or []
    official_status, official_failed = parse_official_checks(bc_raw)

    thresholds = _adaptive_thresholds(mode, region, dataset_category, delay)
    sharpe_min = thresholds["sharpe_min"]
    fitness_min = thresholds["fitness_min"]
    self_corr_max = thresholds["self_corr_max"]
    turnover_min = thresholds["turnover_min"]
    turnover_max = thresholds["turnover_max"]
    margin_min = thresholds["margin_min"]

    reasons: list[str] = []
    suggestions: list[str] = []
    fallback_used = False
    fallback_reason = ""

    if official_status == "fail":
        # 官方 checks 确认失败
        check_name_map = {
            "LOW_SHARPE": f"sharpe<{sharpe_min:.2f}（官方判定）",
            "LOW_FITNESS": f"fitness<{fitness_min:.2f}（官方判定）",
            "HIGH_TURNOVER": "turnover过高（官方判定）",
            "LOW_TURNOVER": "turnover过低（官方判定）",
            "CONCENTRATED_WEIGHT": "权重过于集中（官方判定）",
            "LOW_SUB_UNIVERSE_SHARPE": "子域Sharpe不足（官方判定）",
        }
        for name in official_failed:
            reasons.append(check_name_map.get(name, f"{name} 未通过（官方判定）"))
    elif official_status in ("pending", "unavailable"):
        # 官方 checks 不可用，fallback 到本地阈值
        fallback_used = True
        fallback_reason = "官方checks未就绪" if official_status == "pending" else "官方checks不可用"
        if sharpe < sharpe_min:
            reasons.append(f"sharpe<{sharpe_min:.2f}")
            suggestions.append("提高信号稳定性或更换字段方向")
        if fitness < fitness_min:
            reasons.append(f"fitness<{fitness_min:.2f}")
            suggestions.append("降低换手或提升收益稳定性")
        if turnover > turnover_max:
            reasons.append(f"turnover>{turnover_max:.0%}")
            suggestions.append("增加 decay 或使用平滑外层")
        if turnover < turnover_min:
            reasons.append(f"turnover<{turnover_min:.0%}")
            suggestions.append("降低 decay 或换更活跃字段")
        if margin < margin_min:
            reasons.append(f"margin<{margin_min:.0f}bps")
            suggestions.append("提升收益/降低交易成本")
    # 不管官方 checks 结果如何，自相关都检查
    if self_corr > self_corr_max:
        reasons.append(f"self_corr>{self_corr_max:.1f}")
        suggestions.append("降低与已提交/OS 因子的相关性")

    passed = len(reasons) == 0

    # OPTIMIZE 决策树（参考 WorldQuantDIG alpha_scoring.py）
    opt_min = thresholds["optimize_min"]
    opt_max = thresholds["optimize_max"]
    if passed:
        quality_status = "PASS"
    elif sharpe <= 0 and fitness <= 0:
        quality_status = "REJECT"
    elif sharpe < opt_min and fitness <= 0:
        quality_status = "REJECT"
    elif opt_min <= sharpe < opt_max:
        quality_status = "OPTIMIZE"
    elif turnover > 0.6 and sharpe >= opt_min:
        quality_status = "OPTIMIZE"
    elif sharpe >= opt_max and fitness < fitness_min:
        quality_status = "OPTIMIZE"
    else:
        quality_status = "REJECT"

    # 信号灯
    if sharpe >= 2.5 and fitness >= 2.0 and 0.05 <= turnover <= 0.15 and self_corr <= 0.4:
        signal_light = "GREEN"
        quality_tier = "HIGH_VF"
    elif passed:
        signal_light = "YELLOW"
        quality_tier = "SUBMIT"
    elif quality_status == "OPTIMIZE":
        signal_light = "RED"
        quality_tier = "NONE"
    else:
        if sharpe < sharpe_min * 0.5 or fitness < fitness_min * 0.3:
            signal_light = "DEAD"
        else:
            signal_light = "RED"
        quality_tier = "NONE"

    # review_priority: 越低越优先（0=最高优先级）
    priority_map = {"GREEN": 0, "YELLOW": 1, "RED": 2, "DEAD": 3}
    status_boost = {"PASS": 0, "OPTIMIZE": 1, "REJECT": 2}
    review_priority = priority_map.get(signal_light, 3) * 10 + status_boost.get(quality_status, 2)
    if fallback_used:
        review_priority += 5

    diagnosis: dict = {
        "suggestions": list(dict.fromkeys(suggestions)),
        "adaptive_thresholds": {
            "sharpe_min": round(sharpe_min, 3),
            "fitness_min": round(fitness_min, 3),
            "margin_min": margin_min,
        },
    }

    return QualityResult(
        quality_status=quality_status,
        signal_light=signal_light,
        quality_tier=quality_tier,
        reasons=reasons,
        diagnosis=diagnosis,
        official_check_status=official_status,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        review_priority=review_priority,
    )


# ─── DSI 增强 ─────────────────────────────────────────────────

def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _wilson_score(k: int, n: int, z: float = 1.0) -> float:
    if n == 0:
        return 0.0
    p_hat = k / n
    denom = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    return max(0.0, min(1.0, center))


def count_op_families(expressions: Iterable[str]) -> int:
    families = {
        "ts": ("ts_",),
        "group": ("group_",),
        "math": ("log(", "sqrt(", "abs(", "winsorize("),
        "rank": ("rank(", "zscore(", "normalize("),
        "cond": ("if_else(", "trade_when("),
        "vector": ("vec_",),
    }
    text = " ".join(str(expr).lower() for expr in expressions)
    return sum(1 for needles in families.values() if any(needle in text for needle in needles))


def calculate_dsi(
    sharpe_values: Iterable[float],
    pass_count: int,
    op_family_count: int = 0,
) -> tuple[float, str]:
    values = [abs(_to_float(v)) for v in sharpe_values]
    n = len(values)
    if n == 0:
        return 0.0, "YELLOW"
    if n < 5:
        # 小样本保护：最多黄灯
        return 0.3, "YELLOW"

    mean = _mean(values)
    std = _std(values)
    max_sharpe = max(values)

    ceiling = min(1.0, max_sharpe / 2.0)
    # Wilson 通过率（比简单比例更保守）
    pass_rate = _wilson_score(pass_count, n)
    consistency = 1.0 / (1.0 + (std / mean)) if mean else 0.0
    diversity = min(1.0, op_family_count / 4.0)
    # 均值得分：相对于提交底线 1.25
    mean_score = min(1.0, mean / 1.25)

    dsi = 0.30 * mean_score + 0.25 * ceiling + 0.25 * pass_rate + 0.10 * consistency + 0.10 * diversity

    # 天花板保护：有高分个体不判死
    if dsi >= 0.65:
        signal = "GREEN"
    elif dsi >= 0.35:
        signal = "YELLOW"
    elif max_sharpe >= 1.4:
        signal = "RED"
    elif n >= 10 and mean < 0.8 and max_sharpe < 1.2:
        signal = "DEAD"
    else:
        signal = "RED"
    return round(dsi, 4), signal


def build_batch_stats(
    all_alphas: list[dict],
    passed: list[dict],
    failed: list[dict],
    expressions: Optional[list[str]] = None,
) -> dict:
    sharpe_values = [abs(_to_float(a.get("sharpe"))) for a in all_alphas if a.get("sharpe") is not None]
    op_families = count_op_families(expressions or []) if expressions else 0
    dsi, dsi_signal = calculate_dsi(sharpe_values, len(passed), op_families)
    fail_reasons: dict[str, int] = {}
    for a in failed:
        for reason in str(a.get("quality_reasons", "")).split(";"):
            r = reason.strip()
            if r:
                fail_reasons[r] = fail_reasons.get(r, 0) + 1
    return {
        "total": len(all_alphas),
        "passed": len(passed),
        "failed": len(failed),
        "pass_rate": len(passed) / len(all_alphas) if all_alphas else 0.0,
        "dsi": dsi,
        "dsi_signal": dsi_signal,
        "op_family_count": op_families,
        "fail_reason_counts": fail_reasons,
        "sharpe_mean": round(_mean(sharpe_values), 3) if sharpe_values else None,
        "sharpe_max": round(max(sharpe_values), 3) if sharpe_values else None,
    }


# ─── 记录增强 ─────────────────────────────────────────────────

def enrich_alpha_record(alpha: dict, mode: str = "USER") -> dict:
    result = evaluate_alpha(
        alpha,
        mode=mode,
        region=str(alpha.get("region") or "USA"),
        dataset_category=_infer_category(alpha),
        delay=int(_to_float(alpha.get("delay"), 1)),
        brain_checks=alpha.get("brain_checks") or alpha.get("checks"),
    )
    enriched = dict(alpha)
    enriched["quality_status"] = result.quality_status
    enriched["signal_light"] = result.signal_light
    enriched["quality_tier"] = result.quality_tier
    enriched["quality_reasons"] = ";".join(result.reasons)
    enriched["official_check_status"] = result.official_check_status
    enriched["fallback_used"] = result.fallback_used
    enriched["fallback_corr"] = alpha.get("fallback_corr")
    enriched["review_priority"] = result.review_priority
    enriched["dsi_signal"] = alpha.get("dsi_signal")
    enriched["diagnosis_summary"] = "; ".join(result.diagnosis.get("suggestions", []))[:200]
    enriched["risk_flags"] = (
        "official_fail " if result.official_check_status == "fail" else ""
    ) + ("fallback " if result.fallback_used else "") + (
        "high_self_corr " if _to_float(alpha.get("self_corr"), 0.0) > 0.65 else ""
    )
    return enriched


def _infer_category(alpha: dict) -> str:
    tags = str(alpha.get("tags") or "")
    code = str(alpha.get("code") or alpha.get("expression") or "")
    if "fundamental" in tags or "fundamental" in code:
        return "fundamental"
    if "analyst" in tags or "analyst" in code:
        return "analyst"
    if "news" in tags or "news" in code:
        return "news"
    return "other"


def _pnl_correlation(returns_a: list[float], returns_b: list[float]) -> float:
    """两条 PnL 差分序列的皮尔逊相关系数（尾部对齐，纯 Python 实现）。

    用于本地相关性剪枝，输入为日收益序列（即 pnl.diff() 的结果）。
    样本不足或方差为 0 时返回 0.0（保守视为不相关，保留候选）。
    """
    a = [_to_float(x) for x in returns_a]
    b = [_to_float(x) for x in returns_b]
    n = min(len(a), len(b))
    if n < 30:  # 样本太少，相关性不可靠
        return 0.0
    a, b = a[-n:], b[-n:]
    mean_a, mean_b = _mean(a), _mean(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a <= 0 or var_b <= 0:
        return 0.0
    corr = cov / math.sqrt(var_a * var_b)
    if corr != corr:  # NaN 保护
        return 0.0
    return max(-1.0, min(1.0, corr))


def correlation_pruning(
    alpha_ids: list[str],
    sharpe_values: list[float],
    pnl_map: dict[str, list[float]],
    threshold: float = 0.65,
) -> list[str]:
    """贪心相关性剪枝：按 |sharpe| 降序保留，剔除与已保留因子高相关的候选。

    Args:
        alpha_ids: 候选 alpha id 列表
        sharpe_values: 与 alpha_ids 等长的 sharpe 列表（用于排序优先级）
        pnl_map: {alpha_id: pnl 差分序列}
        threshold: 相关性阈值，|corr| 超过则视为重复并剔除

    Returns:
        保留下来的 alpha id 列表（按 sharpe 降序）
    """
    order = sorted(
        range(len(alpha_ids)),
        key=lambda i: -abs(_to_float(sharpe_values[i])) if i < len(sharpe_values) else 0.0,
    )
    kept: list[str] = []
    for idx in order:
        aid = alpha_ids[idx]
        rets = pnl_map.get(aid)
        if not rets:
            kept.append(aid)  # 无 PnL 数据无法比较，保守保留
            continue
        too_corr = any(
            pnl_map.get(kid) and abs(_pnl_correlation(rets, pnl_map[kid])) > threshold
            for kid in kept
        )
        if not too_corr:
            kept.append(aid)
    return kept


def sort_submitable_records(records: list[dict]) -> list[dict]:
    light_rank = {"GREEN": 0, "YELLOW": 1, "RED": 2, "DEAD": 3}
    status_rank = {"PASS": 0, "OPTIMIZE": 1, "REJECT": 2}
    official_rank = {"pass": 0, "pending": 1, "unavailable": 2, "fail": 3, "unknown": 2}

    return sorted(
        records,
        key=lambda row: (
            int(_to_float(row.get("review_priority"), 99)),
            status_rank.get(str(row.get("quality_status", "")), 9),
            light_rank.get(str(row.get("signal_light", "")), 9),
            official_rank.get(str(row.get("official_check_status", "unknown")), 2),
            -abs(_to_float(row.get("fitness"))),
            -abs(_to_float(row.get("sharpe"))),
            -_to_float(row.get("margin")),
            _to_float(row.get("self_corr"), 1.0),
        ),
    )
