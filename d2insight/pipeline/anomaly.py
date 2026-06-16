"""AnomalyDetector: 차원별 양방향 이상치 감지 + 5단계 심각도 분류."""
from __future__ import annotations

import pandas as pd

from d2insight import config

_DIMENSIONS = config.DIMENSIONS


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def _classify(ratio: float | None) -> str:
    if ratio is None:
        return "🔵"
    if ratio >= config.ANOMALY_SURGE_CRITICAL:
        return "🚨"
    if ratio > config.ANOMALY_NORMAL_HIGH:
        return "🔵"
    if ratio >= config.ANOMALY_NORMAL_LOW:
        return "🟢"
    if ratio >= config.ANOMALY_CRITICAL:
        return "🟡"
    return "🔴"


def _analyze_dimension(
    curr: pd.DataFrame,
    prev: pd.DataFrame,
    dim: str,
    total_curr: float,
) -> dict:
    curr_grp = curr.groupby(dim)["매출"].sum()
    prev_grp = prev.groupby(dim)["매출"].sum()

    joined = pd.concat(
        [prev_grp.rename("prev"), curr_grp.rename("curr")], axis=1
    ).fillna(0.0)

    joined["delta"] = joined["curr"] - joined["prev"]
    joined["ratio"] = joined.apply(
        lambda r: (r["curr"] / r["prev"]) if r["prev"] > 0 else None, axis=1
    )
    joined["severity"] = joined["ratio"].apply(_classify)
    joined["share_of_total"] = (
        (joined["curr"] / total_curr).round(4) if total_curr > 0 else 0.0
    )
    joined["ratio"] = joined["ratio"].apply(
        lambda v: round(v, 4) if v is not None else None
    )

    records = joined.reset_index().to_dict(orient="records")
    anomalies = [r for r in records if r["severity"] != "🟢"]
    anomalies.sort(key=lambda r: r["delta"])

    return {
        "all": records,
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
    }


def run_anomaly_detection(df: pd.DataFrame, target_month: str) -> dict:
    prev_month = _shift_month(target_month, -1)
    curr = df[df["월"] == target_month]
    prev = df[df["월"] == prev_month]

    total_curr = float(curr["매출"].sum())
    total_prev = float(prev["매출"].sum())
    overall_ratio = (total_curr / total_prev) if total_prev > 0 else None

    dimension_results: dict[str, dict] = {}
    for dim in _DIMENSIONS:
        if dim not in df.columns:
            continue
        dimension_results[dim] = _analyze_dimension(curr, prev, dim, total_curr)

    return {
        "target_month": target_month,
        "prev_month": prev_month,
        "overall": {
            "total_curr": round(total_curr, 2),
            "total_prev": round(total_prev, 2),
            "delta": round(total_curr - total_prev, 2),
            "ratio": round(overall_ratio, 4) if overall_ratio is not None else None,
            "severity": _classify(overall_ratio),
        },
        "dimensions": dimension_results,
        "severity_guide": {
            "🚨": f"데이터 오류 의심 (달성률 {config.ANOMALY_SURGE_CRITICAL:.0%} 이상)",
            "🔴": f"심각 하락 (달성률 {config.ANOMALY_CRITICAL:.0%} 미만)",
            "🟡": f"주의 하락 (달성률 {config.ANOMALY_CRITICAL:.0%}~{config.ANOMALY_NORMAL_LOW:.0%})",
            "🟢": f"정상 (달성률 {config.ANOMALY_NORMAL_LOW:.0%}~{config.ANOMALY_NORMAL_HIGH:.0%})",
            "🔵": f"상승 이상치 (달성률 {config.ANOMALY_NORMAL_HIGH:.0%} 초과, 원인 확인 필요)",
        },
    }
