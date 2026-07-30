"""고급 분석 도구 — pr_module_insight의 분석 모듈(Shapley/DVI, PVM 분해, PnL 계단)을
run_stats류와 같은 패턴(순수 데이터 입력 → dict 출력)으로 이식한 것.

pr_module_insight 원본은 SharedContext + 역할 기반 스키마(schema.py, Semantic_Type)에
의존하지만, 이 프로젝트의 메타데이터 모델(datacols.measureyn)에는 그런 역할 태그가 없다.
그래서 계산 로직(공식)만 그대로 가져오고, 입력은 execute_query로 이미 조회한 레코드 +
LLM이 메타정보를 보고 직접 지정하는 컬럼명으로 받는다 — execute_query/run_stats와 동일한
"자연어로 데이터 조회 → 그 결과를 다음 툴에 전달" 흐름을 그대로 따른다.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool


def _to_df(data: list) -> pd.DataFrame:
    return pd.DataFrame(data)


@tool
def run_variance_impact(
    actual_data: list,
    compare_data: list,
    dimension_col: str,
    measure_col: str,
) -> dict:
    """차원별 증감 영향도(Impact/HHI/DVI)를 계산합니다 — "어느 차원(항목)이 변화를 주도했는가".

    execute_query로 각각 조회한 "분석기간 {차원}별 {측정값} 합계" 데이터와
    "비교기간 {차원}별 {측정값} 합계" 데이터를 전달하세요.

    Args:
        actual_data: 분석기간 데이터 (records 형식) — dimension_col, measure_col 포함.
        compare_data: 비교기간 데이터 (records 형식) — 같은 컬럼 구조.
        dimension_col: 그룹 기준 차원 컬럼명 (예: 채널, 제품, 지역).
        measure_col: 집계된 측정값 컬럼명 (예: 매출).
    """
    a = _to_df(actual_data)
    c = _to_df(compare_data)
    if dimension_col not in a.columns or measure_col not in a.columns:
        return {"error": f"actual_data에 '{dimension_col}' 또는 '{measure_col}' 컬럼이 없습니다."}

    agg_a = a.groupby(dimension_col)[measure_col].sum().rename("actual")
    agg_c = (c.groupby(dimension_col)[measure_col].sum().rename("compare")
             if dimension_col in c.columns else pd.Series(dtype=float, name="compare"))
    merged = pd.concat([agg_a, agg_c], axis=1).fillna(0.0).reset_index()

    merged["variance"] = merged["actual"] - merged["compare"]
    merged["rate"] = merged.apply(
        lambda r: r["variance"] / r["compare"] if r["compare"] else 0.0, axis=1,
    )
    # 신규 항목(New)은 변화율이 무한대라 통계(평균/표준편차)를 왜곡하므로 제외한다(원본 §5 규칙).
    established = merged[merged["compare"] != 0]
    if established.empty:
        return {"error": "비교기간에 존재하던 항목이 없어 영향도를 계산할 수 없습니다."}

    rates = established["rate"].to_numpy(dtype=float)
    variances = established["variance"].to_numpy(dtype=float)
    n = len(established)
    rate_mean = float(np.mean(rates))
    sigma = float(np.std(rates, ddof=1)) if n > 1 else 0.0
    impact_score = float(np.sum(np.abs(variances)))
    z_scores = (rates - rate_mean) / sigma if sigma > 0 else np.zeros(n)
    avg_z = float(np.mean(np.abs(z_scores)))
    hhi = float(np.sum((np.abs(variances) / impact_score) ** 2)) if impact_score > 0 else 0.0
    dvi = impact_score * hhi * avg_z

    top = merged.reindex(merged["variance"].abs().sort_values(ascending=False).index).head(10)
    return {
        "dimension": dimension_col,
        "measure": measure_col,
        "item_count": int(len(merged)),
        "impact_score": round(impact_score, 2),
        "hhi": round(hhi, 4),
        "average_z": round(avg_z, 4),
        "dvi": round(dvi, 2),
        "top_variance_items": top.round(2).to_dict(orient="records"),
    }


@tool
def run_sales_bridge(
    actual_data: list,
    compare_data: list,
    item_col: str,
    amount_col: str,
    quantity_col: Optional[str] = None,
) -> dict:
    """매출 증감을 항목 단위로 분해합니다 — 신규/단종 효과 + 기존 항목의 수량 효과·단가(ASP) 효과.

    두 기간 모두 존재하는 항목은 물량 변화 효과와 단가 변화 효과로 나누고,
    한쪽 기간에만 존재하는 항목은 신규/단종 효과로 집계합니다. 모든 효과의 합은
    전체 증감액과 일치합니다(검산).

    Args:
        actual_data: 분석기간 항목별 데이터 (records) — item_col, amount_col(quantity_col) 포함.
        compare_data: 비교기간 항목별 데이터 (records) — 같은 컬럼 구조.
        item_col: 항목(상품/고객 등) 컬럼명.
        amount_col: 금액 컬럼명.
        quantity_col: 수량 컬럼명 — 지정 시 물량/단가 효과까지 분해. 미지정 시 항목 증감만 계산.
    """
    a = _to_df(actual_data)
    c = _to_df(compare_data)
    cols = [amount_col] + ([quantity_col] if quantity_col else [])
    if item_col not in a.columns or amount_col not in a.columns:
        return {"error": f"actual_data에 '{item_col}' 또는 '{amount_col}' 컬럼이 없습니다."}

    agg_a = a.groupby(item_col)[cols].sum()
    agg_c = c.groupby(item_col)[cols].sum() if item_col in c.columns else pd.DataFrame(columns=cols)
    panel = agg_a.join(agg_c, how="outer", lsuffix="_a", rsuffix="_c").fillna(0.0)

    a_col, c_col = f"{amount_col}_a", f"{amount_col}_c"
    total_variance = float(panel[a_col].sum() - panel[c_col].sum())

    new_items = panel[(panel[c_col] == 0) & (panel[a_col] > 0)]
    lost_items = panel[(panel[a_col] == 0) & (panel[c_col] > 0)]
    keep = panel[(panel[a_col] > 0) & (panel[c_col] > 0)]

    effects = [
        {"효과": "신규 항목 효과", "금액": round(float(new_items[a_col].sum()), 2), "항목수": int(len(new_items))},
        {"효과": "단종 항목 효과", "금액": round(float(-lost_items[c_col].sum()), 2), "항목수": int(len(lost_items))},
    ]

    if quantity_col and not keep.empty:
        qa, qc = keep[f"{quantity_col}_a"], keep[f"{quantity_col}_c"]
        pa = (keep[a_col] / qa.where(qa > 0)).fillna(0.0)
        pc = (keep[c_col] / qc.where(qc > 0)).fillna(0.0)
        qty_effect = float(((qa - qc) * pc).sum())
        price_effect = float((qa * (pa - pc)).sum())
        effects += [
            {"효과": "기존 항목 수량 효과", "금액": round(qty_effect, 2), "항목수": int(len(keep))},
            {"효과": "기존 항목 단가 효과", "금액": round(price_effect, 2), "항목수": int(len(keep))},
        ]
    elif not keep.empty:
        effects.append({
            "효과": "기존 항목 증감", "금액": round(float((keep[a_col] - keep[c_col]).sum()), 2),
            "항목수": int(len(keep)),
        })

    checksum = round(sum(e["금액"] for e in effects) - total_variance, 2)
    return {
        "total_variance": round(total_variance, 2),
        "effects": effects,
        "checksum_gap": checksum,  # 0에 가까워야 분해가 정확한 것(반올림 오차만 남아야 함)
    }


@tool
def run_pnl_waterfall(
    revenue_actual: float, revenue_compare: float,
    cogs_actual: float, cogs_compare: float,
    opex_actual: Optional[float] = None, opex_compare: Optional[float] = None,
) -> dict:
    """매출 → 매출원가 → 매출총이익 → 판관비 → 영업이익 손익 계단을 계산합니다.

    각 단계 금액은 execute_query로 미리 집계해서 전달하세요
    (예: "이번달 매출 합계", "이번달 매출원가 합계").

    Args:
        revenue_actual: 분석기간 매출.
        revenue_compare: 비교기간 매출.
        cogs_actual: 분석기간 매출원가.
        cogs_compare: 비교기간 매출원가.
        opex_actual: 분석기간 판관비 (있으면 영업이익까지 계산).
        opex_compare: 비교기간 판관비.
    """
    def _step(name: str, compare: float, actual: float) -> dict:
        variance = actual - compare
        return {
            "step": name,
            "compare": round(compare, 2),
            "actual": round(actual, 2),
            "variance": round(variance, 2),
            "rate": round(variance / compare, 4) if compare else 0.0,
        }

    gm_a, gm_c = revenue_actual - cogs_actual, revenue_compare - cogs_compare
    steps = [
        _step("매출", revenue_compare, revenue_actual),
        _step("매출원가", cogs_compare, cogs_actual),
        _step("매출총이익", gm_c, gm_a),
    ]
    if opex_actual is not None and opex_compare is not None:
        ebit_a, ebit_c = gm_a - opex_actual, gm_c - opex_compare
        steps.append(_step("판매관리비", opex_compare, opex_actual))
        steps.append(_step("영업이익", ebit_c, ebit_a))
    return {"steps": steps}


ALL_MODULE_TOOLS = [run_variance_impact, run_sales_bridge, run_pnl_waterfall]
