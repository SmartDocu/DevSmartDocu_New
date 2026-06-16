"""DataValidator: 입력 데이터 오류 패턴 4종 감지."""
from __future__ import annotations

import pandas as pd

from d2insight import config

_ITEM_DIMS = ["제품", "채널"]
_DUPLICATE_RATIO = 2.0
_DROP_RATIO = 0.30
_RISE_RATIO = 1.70
_UNIT_VS_2ND = 1.50
_TOTAL_SIMILAR = 0.05
_ITEM_BIG_MOVE = 0.05


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def run_data_validation(df: pd.DataFrame, target_month: str) -> dict:
    prev_month = _shift_month(target_month, -1)
    prev2_month = _shift_month(target_month, -2)

    curr = df[df["월"] == target_month]
    prev = df[df["월"] == prev_month]
    prev2 = df[df["월"] == prev2_month]

    total_curr = float(curr["매출"].sum())
    total_prev = float(prev["매출"].sum())
    total_prev2 = float(prev2["매출"].sum())

    issues: list[dict] = []

    if total_prev > 0:
        ratio = total_curr / total_prev
        if ratio >= _DUPLICATE_RATIO:
            issues.append({
                "pattern": "duplicate_entry",
                "description": "중복 입력 의심",
                "detail": f"당월 총매출이 전월 대비 {ratio:.0%} — 200% 이상 급상승",
                "severity": "🚨",
            })

    if total_prev2 > 0 and total_prev > 0:
        ratio_drop = total_prev / total_prev2
        ratio_rise = total_curr / total_prev
        if ratio_drop < _DROP_RATIO and ratio_rise > _RISE_RATIO:
            detail = f"전전월→전월 {ratio_drop:.0%}, 전월→당월 {ratio_rise:.0%} 연속"
            expected = total_prev2 * 2
            deviation = abs((total_prev + total_curr) - expected) / expected
            if deviation < 0.10:
                detail += " — 전월+당월 ≈ 전전월×2 (누락 후 합산 거의 확실)"
                severity = "🚨"
            else:
                severity = "⚠️"
            issues.append({
                "pattern": "omission_and_merge",
                "description": "누락 후 합산 의심",
                "detail": detail,
                "severity": severity,
            })

    monthly_totals = df.groupby("월")["매출"].sum().sort_values(ascending=False)
    if len(monthly_totals) >= 3 and monthly_totals.index[0] == target_month:
        second_max = float(monthly_totals.iloc[1])
        if second_max > 0 and total_curr / second_max >= _UNIT_VS_2ND:
            issues.append({
                "pattern": "unit_error",
                "description": "단위 오류 의심",
                "detail": (
                    f"당월 총매출 {total_curr:,.0f}이 전체 기간 최고치, "
                    f"2위 {second_max:,.0f} 대비 {total_curr / second_max:.0%}"
                ),
                "severity": "🚨",
            })

    if total_prev > 0 and total_curr > 0:
        total_diff_ratio = abs(total_curr - total_prev) / total_prev
        if total_diff_ratio < _TOTAL_SIMILAR:
            curr_items = curr.groupby(_ITEM_DIMS)["매출"].sum()
            prev_items = prev.groupby(_ITEM_DIMS)["매출"].sum()
            joined = (
                pd.concat([prev_items.rename("prev"), curr_items.rename("curr")], axis=1)
                .fillna(0.0)
            )
            joined["abs_change"] = (joined["curr"] - joined["prev"]).abs()
            big_movers = joined[joined["abs_change"] / total_curr >= _ITEM_BIG_MOVE]
            if len(big_movers) >= 2:
                issues.append({
                    "pattern": "item_reclassification",
                    "description": "항목 간 이동 의심",
                    "detail": (
                        f"전체 합계 차이 {total_diff_ratio:.1%}로 유사하나 "
                        f"{len(big_movers)}개 항목이 총매출의 5% 이상 급변"
                    ),
                    "severity": "⚠️",
                    "flagged_items": (
                        big_movers.reset_index()[_ITEM_DIMS]
                        .to_dict(orient="records")
                    ),
                })

    monthly_summary = (
        monthly_totals.reset_index()
        .rename(columns={"매출": "총매출"})
        .to_dict(orient="records")
    )

    return {
        "target_month": target_month,
        "has_issues": len(issues) > 0,
        "issue_count": len(issues),
        "issues": issues,
        "monthly_totals": monthly_summary,
    }
