"""DataValidator: 입력 데이터 오류 패턴 4종 감지.

감지 패턴 (documents/sales_report_analysis_summary.md §6-3):
  1. 누락 후 합산 — 급락 + 익월 급상승 연속
  2. 중복 입력   — 전월 대비 200% 이상 급상승
  3. 단위 오류   — 전체 기간 최고치 & 2위 대비 150% 이상
  4. 항목 간 이동 — 전체 합계 유사 & 개별 항목 5% 이상 급변
"""
from __future__ import annotations

import pandas as pd

import d2insight.config as config

# 기본 컬럼·차원 (판매 데이터). 엔진 경로는 스키마 역할로 이 값을 덮어써 도메인 중립으로 쓴다.
_DEFAULT_PERIOD_COL = "월"
_DEFAULT_AMOUNT_COL = "매출"
_DEFAULT_ITEM_DIMS = ["제품", "채널"]
_DUPLICATE_RATIO = 2.0    # 200% 이상 → 중복 입력 의심
_DROP_RATIO = 0.30        # 30% 이하로 하락 → 급락
_RISE_RATIO = 1.70        # 170% 이상 급상승 (급락 다음)
_UNIT_VS_2ND = 1.50       # 2위 대비 150% 이상 → 단위 오류 의심
_TOTAL_SIMILAR = 0.05     # 전체 합계 차이 5% 이내 = "유사"
_ITEM_BIG_MOVE = 0.05     # 항목 매출이 총매출의 5% 이상 급변


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def run_data_validation(
    df: pd.DataFrame,
    target_month: str,
    *,
    period_col: str = _DEFAULT_PERIOD_COL,
    amount_col: str = _DEFAULT_AMOUNT_COL,
    amount_label: str = _DEFAULT_AMOUNT_COL,
    item_dims: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """데이터 오류 패턴을 감지하고 결과를 반환한다.

    period_col/amount_col/item_dims를 인자로 받아 컬럼명에 의존하지 않는다(엔진의 역할 기반 호출용).
    amount_label은 이슈 설명에 찍히는 표시명(판매="매출", 구매="구매액")이라 다른 도메인 보고서에
    도메인 어휘가 새지 않는다. 기본값은 판매 데이터 컬럼이라 기존 호출부는 그대로 동작한다.
    item_dims가 비면 항목 간 이동 패턴(개별 항목 그룹 필요)은 건너뛴다.
    """
    item_dims = list(item_dims) if item_dims is not None else list(_DEFAULT_ITEM_DIMS)

    prev_month = _shift_month(target_month, -1)
    prev2_month = _shift_month(target_month, -2)

    curr = df[df[period_col] == target_month]
    prev = df[df[period_col] == prev_month]
    prev2 = df[df[period_col] == prev2_month]

    total_curr = float(curr[amount_col].sum())
    total_prev = float(prev[amount_col].sum())
    total_prev2 = float(prev2[amount_col].sum())

    issues: list[dict] = []

    # 1. 중복 입력: 전월 대비 200% 이상 급상승
    if total_prev > 0:
        ratio = total_curr / total_prev
        if ratio >= _DUPLICATE_RATIO:
            issues.append({
                "pattern": "duplicate_entry",
                "description": "중복 입력 의심",
                "detail": f"당월 총{amount_label}이 전월 대비 {ratio:.0%} — 200% 이상 급상승",
                "severity": "🚨",
            })

    # 2. 누락 후 합산: 전전월→전월 급락 + 전월→당월 급상승 연속
    if total_prev2 > 0 and total_prev > 0:
        ratio_drop = total_prev / total_prev2
        ratio_rise = total_curr / total_prev
        if ratio_drop < _DROP_RATIO and ratio_rise > _RISE_RATIO:
            detail = f"전전월→전월 {ratio_drop:.0%}, 전월→당월 {ratio_rise:.0%} 연속"
            # 강화 검증: (전월 + 당월) ≈ 전전월 × 2
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

    # 3. 단위 오류: 역대 최고치 & 2위 대비 150% 이상
    monthly_totals = df.groupby(period_col)[amount_col].sum().sort_values(ascending=False)
    if len(monthly_totals) >= 3 and monthly_totals.index[0] == target_month:
        second_max = float(monthly_totals.iloc[1])
        if second_max > 0 and total_curr / second_max >= _UNIT_VS_2ND:
            issues.append({
                "pattern": "unit_error",
                "description": "단위 오류 의심",
                "detail": (
                    f"당월 총{amount_label} {total_curr:,.0f}이 전체 기간 최고치, "
                    f"2위 {second_max:,.0f} 대비 {total_curr / second_max:.0%}"
                ),
                "severity": "🚨",
            })

    # 4. 항목 간 이동: 전체 합계 유사 & 개별 항목 급변 (항목 차원이 있어야 판정 가능)
    if item_dims and total_prev > 0 and total_curr > 0:
        total_diff_ratio = abs(total_curr - total_prev) / total_prev
        if total_diff_ratio < _TOTAL_SIMILAR:
            curr_items = curr.groupby(item_dims)[amount_col].sum()
            prev_items = prev.groupby(item_dims)[amount_col].sum()
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
                        f"{len(big_movers)}개 항목이 총{amount_label}의 5% 이상 급변"
                    ),
                    "severity": "⚠️",
                    "flagged_items": (
                        big_movers.reset_index()[item_dims]
                        .to_dict(orient="records")
                    ),
                })

    monthly_summary = (
        monthly_totals.reset_index()
        .rename(columns={amount_col: "총매출"})
        .to_dict(orient="records")
    )

    return {
        "target_month": target_month,
        "has_issues": len(issues) > 0,
        "issue_count": len(issues),
        "issues": issues,
        "monthly_totals": monthly_summary,
    }
