"""ABC-XYZ classification at (제품, 채널) item level.

Two windows per design (§5.3):
  - 분석 필터용 (analysis filter): 당월 제외 직전 3개월
  - 현황 표시용 (display): 당월 포함 최근 3개월

ABC: cumulative revenue share thresholds (config.ABC_THRESHOLDS)
XYZ: coefficient of variation (CV = std/mean) thresholds (config.XYZ_THRESHOLDS)

Grade-change detection compares the current 분석 필터용 window with the same
window shifted one month earlier (the previous report's filter window).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import d2insight.config as config

ITEM_DIMS: list[str] = ["제품", "채널"]


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def _three_month_window(target_month: str, *, include_target: bool) -> list[str]:
    offsets = [0, -1, -2] if include_target else [-1, -2, -3]
    return sorted(_shift_month(target_month, off) for off in offsets)


def _xyz_grade(cv: float, x_thr: float, y_thr: float) -> str:
    if cv < x_thr:
        return "X"
    if cv < y_thr:
        return "Y"
    return "Z"


def classify_abc_xyz(
    df: pd.DataFrame, *, target_month: str, include_target: bool
) -> dict:
    """Classify items at ITEM_DIMS level over the chosen 3-month window."""
    months = _three_month_window(target_month, include_target=include_target)
    window = df[df["월"].isin(months)]

    pivot = (
        window.groupby(ITEM_DIMS + ["월"])["매출"]
        .sum()
        .unstack(fill_value=0.0)
        .reindex(columns=months, fill_value=0.0)
    )
    if pivot.empty:
        return {
            "window_months": months,
            "classification": pd.DataFrame(),
            "summary": {"n_items": 0, "total_revenue": 0.0, "by_grade": {}},
        }

    total_rev = pivot.sum(axis=1)
    total_sum = float(total_rev.sum())

    # ABC ─ cumulative share by descending revenue
    a_thr, b_thr = config.ABC_THRESHOLDS
    sorted_rev = total_rev.sort_values(ascending=False)
    if total_sum > 0:
        cum_share_sorted = sorted_rev.cumsum() / total_sum
        abc_sorted = cum_share_sorted.apply(
            lambda s: "A" if s <= a_thr else ("B" if s <= b_thr else "C")
        )
    else:
        cum_share_sorted = sorted_rev * 0.0
        abc_sorted = pd.Series("C", index=sorted_rev.index)
    abc = abc_sorted.reindex(total_rev.index)
    cum_share = cum_share_sorted.reindex(total_rev.index)
    point_share = total_rev / total_sum if total_sum > 0 else total_rev * 0.0

    # XYZ ─ coefficient of variation (population std)
    mean_rev = pivot.mean(axis=1)
    std_rev = pivot.std(axis=1, ddof=0)
    mean_safe = mean_rev.replace(0, np.nan)
    cv = (std_rev / mean_safe).fillna(np.inf)
    x_thr, y_thr = config.XYZ_THRESHOLDS
    xyz = cv.apply(lambda c: _xyz_grade(c, x_thr, y_thr))

    result = pivot.copy()
    result["매출_3M"] = total_rev
    result["점유율"] = point_share.round(4)
    result["누적점유율"] = cum_share.round(4)
    result["CV"] = cv.replace(np.inf, np.nan).round(4)
    result["ABC"] = abc
    result["XYZ"] = xyz
    result["등급"] = abc + xyz
    result = result.reset_index().sort_values("매출_3M", ascending=False)

    summary = {
        "n_items": int(len(result)),
        "total_revenue": total_sum,
        "by_grade": {k: int(v) for k, v in result["등급"].value_counts().items()},
        "by_abc": {k: int(v) for k, v in result["ABC"].value_counts().items()},
        "by_xyz": {k: int(v) for k, v in result["XYZ"].value_counts().items()},
    }
    return {"window_months": months, "classification": result, "summary": summary}


def detect_grade_changes(curr: dict, prev: dict) -> pd.DataFrame:
    """Items whose 등급 differs between current and previous filter windows."""
    curr_df = curr["classification"]
    prev_df = prev["classification"]
    if curr_df.empty:
        return pd.DataFrame()

    curr_idx = curr_df.set_index(ITEM_DIMS)[["등급", "ABC", "XYZ", "매출_3M"]]
    if prev_df.empty:
        merged = curr_idx.assign(전월_등급="신규", 전월_ABC=np.nan, 전월_XYZ=np.nan)
    else:
        prev_idx = prev_df.set_index(ITEM_DIMS)[["등급", "ABC", "XYZ"]].rename(
            columns={"등급": "전월_등급", "ABC": "전월_ABC", "XYZ": "전월_XYZ"}
        )
        merged = curr_idx.join(prev_idx, how="left")
        merged["전월_등급"] = merged["전월_등급"].fillna("신규")

    changed = merged[merged["등급"] != merged["전월_등급"]]
    return changed.reset_index().sort_values("매출_3M", ascending=False)


def filter_analysis_targets(classification: pd.DataFrame) -> pd.DataFrame:
    if classification.empty:
        return classification
    return classification[
        classification["등급"].isin(config.ANALYSIS_TARGETS)
    ].copy()


def run_phase2(df: pd.DataFrame, target_month: str) -> dict:
    """Full Phase 2 pipeline for a target month."""
    filter_curr = classify_abc_xyz(df, target_month=target_month, include_target=False)
    prev_target = _shift_month(target_month, -1)
    filter_prev = classify_abc_xyz(df, target_month=prev_target, include_target=False)
    display = classify_abc_xyz(df, target_month=target_month, include_target=True)

    return {
        "target_month": target_month,
        "filter_window": filter_curr,
        "display_window": display,
        "grade_changes": detect_grade_changes(filter_curr, filter_prev),
        "analysis_targets": filter_analysis_targets(filter_curr["classification"]),
    }
