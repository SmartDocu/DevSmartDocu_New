"""손익 계단 5스텝 — 시나리오 "손익 분석"의 Revenue/COGS/Gross Margin/OPEX/EBIT 독립 스텝.

스텝 분리 원칙(2026-07-20)에 따라 원래 pnl_summary 하나가 내던 손익 계단을 다섯 개 리프
모듈로 나눈다. 다섯 스텝 모두 `_shared.get_pnl_ladder()`의 캐시된 계산 결과에서 자기 단계만
떼어 보여주므로(§6.2 재계산 금지), 실행 순서와 무관하게 숫자가 항상 일치한다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_pnl_ladder
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_COST, ROLE_OPEX, get_schema
from d2insight.engine.types import ModuleResult, Render

STEP_REVENUE = "매출"
STEP_COGS = "매출원가"
STEP_GROSS_MARGIN = "매출총이익"
STEP_OPEX = "판매관리비"
STEP_EBIT = "영업이익"

# 각 단계 값을 행 단위 데이터에서 만드는 조합(역할 → 부호). 예: 매출총이익 = +amount −cost.
_STEP_COMBO: dict[str, dict[str, int]] = {
    STEP_REVENUE:      {ROLE_AMOUNT: 1},
    STEP_COGS:         {ROLE_COST: 1},
    STEP_GROSS_MARGIN: {ROLE_AMOUNT: 1, ROLE_COST: -1},
    STEP_OPEX:         {ROLE_OPEX: 1},
    STEP_EBIT:         {ROLE_AMOUNT: 1, ROLE_COST: -1, ROLE_OPEX: -1},
}


def _maybe_breakdown(ctx, params, step_name: str) -> tuple[pd.DataFrame | None, str]:
    """params.dimension이 지정됐을 때만 그 단계 값을 차원별로 분해한 표를 만든다(2026-07-23 옵션 추가).

    미지정이면 (None, "") — 기존처럼 총계 요약만 나간다. 필요한 역할 컬럼이나 차원 컬럼이
    없으면 표를 생략하고 사유를 summary에 덧붙인다(총계는 유효하므로 스텝 전체를 실패시키지
    않되, 조용히 감추지도 않는다 §11 Step 2).
    """
    dimension = (params or {}).get("dimension")
    if not dimension:
        return None, ""
    top_n = int((params or {}).get("top_n") or 10)

    actual_df = ctx.get("actual_dataset")
    compare_df = ctx.get("compare_dataset")
    schema = get_schema(ctx)

    # 옵션 통로(options.py)가 역할명을 물리 컬럼으로 바꿔 주지만, 직접 호출 대비 역할명도 받는다.
    dim_col = dimension if dimension in actual_df.columns else schema.column(dimension)
    if not dim_col or dim_col not in actual_df.columns:
        return None, f" (차원 '{dimension}' 컬럼이 없어 차원별 상세는 생략)"

    signed_cols: dict[str, int] = {}
    for role, sign in _STEP_COMBO[step_name].items():
        col = schema.column(role) or (schema.key_measure if role == ROLE_AMOUNT else None)
        if not col or col not in actual_df.columns:
            return None, f" ('{role}' 역할 컬럼이 없어 차원별 상세는 생략)"
        signed_cols[col] = sign

    def _value(df: pd.DataFrame) -> pd.Series:
        grouped = df.groupby(dim_col)
        total: pd.Series | None = None
        for col, sign in signed_cols.items():
            part = grouped[col].sum() * sign
            total = part if total is None else total.add(part, fill_value=0.0)
        return total

    merged = pd.DataFrame({"Actual": _value(actual_df), "Comparison": _value(compare_df)}).fillna(0.0)
    merged["Variance"] = merged["Actual"] - merged["Comparison"]
    merged["Rate"] = [
        v / c if c else 0.0 for v, c in zip(merged["Variance"], merged["Comparison"])
    ]
    merged = merged.reindex(merged["Variance"].abs().sort_values(ascending=False).index).head(top_n)

    display = pd.DataFrame({
        schema.logical_name(dim_col): merged.index.astype(str),
        "비교기간": merged["Comparison"], "당기": merged["Actual"], "증감": merged["Variance"],
        "증감률(%)": merged["Rate"] * 100,
    }).reset_index(drop=True)
    return display, f" {schema.logical_name(dim_col)}별 상위 {len(display)}개(|증감| 기준) 상세 표 포함."


def _get_step(ctx, key: str) -> tuple[dict | None, str]:
    """이름표가 아니라 공유 캐시(_shared)에서 단계 하나를 꺼낸다. 실패 시 (None, 사유)."""
    try:
        ladder = get_pnl_ladder(ctx)
    except ValueError as e:
        return None, str(e)
    step = ladder["steps"].get(key)
    if step is None:
        return None, (f"'{key}' 단계를 계산할 수 없습니다. 판매관리비(opex 역할)가 없어 "
                       "판관비·영업이익 단계는 산출되지 않습니다.")
    return step, ""


def _summary_line(step: dict, *, profit_like: bool, cost_like: bool) -> str:
    variance, rate = step["Variance"], step["Rate"]
    margin = step["Actual_Margin"] * 100
    margin_shift = (step["Actual_Margin"] - step["Comparison_Margin"]) * 100
    if profit_like:
        direction = "개선" if variance >= 0 else "악화"
        margin_label = "매출 대비"
    else:
        direction = "증가" if variance >= 0 else "감소"
        margin_label = "매출 대비 비용률" if cost_like else "매출 대비 비율"
    return (
        f"{step['Step']} {step['Actual_Value']:,.0f} ({variance:+,.0f}, {rate * 100:+.1f}%) "
        f"— {direction}. {margin_label} {margin:.1f}%({margin_shift:+.2f}%p)."
    )


def _run_step(ctx, params, step_name: str, *, profit_like: bool, cost_like: bool,
              extra_kv) -> ModuleResult:
    """다섯 스텝의 공통 실행부 — 총계 요약 + (dimension 지정 시) 차원별 상세 표."""
    step, err = _get_step(ctx, step_name)
    if err:
        return ModuleResult(status="failed", error=err)
    table, note = _maybe_breakdown(ctx, params, step_name)
    base_summary = _summary_line(step, profit_like=profit_like, cost_like=cost_like) + note

    if table is None:
        return ModuleResult(render=Render(summary=base_summary, key_value=extra_kv(step)))

    render = render_from_dataframe(
        table, purpose=f"{step_name} 단계를 차원별로 분해해 제시.", narrative_hint=base_summary,
        params={"단계": step_name}, label="pnl_step",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = extra_kv(step)
    return ModuleResult(render=render)


def run_revenue(ctx, params, tools) -> ModuleResult:
    return _run_step(ctx, params, STEP_REVENUE, profit_like=False, cost_like=False,
                     extra_kv=lambda s: {STEP_REVENUE: f"{s['Actual_Value']:,.0f}",
                                         "증감률": f"{s['Rate'] * 100:+.1f}%"})


def run_cogs(ctx, params, tools) -> ModuleResult:
    return _run_step(ctx, params, STEP_COGS, profit_like=False, cost_like=True,
                     extra_kv=lambda s: {STEP_COGS: f"{s['Actual_Value']:,.0f}",
                                         "증감률": f"{s['Rate'] * 100:+.1f}%"})


def run_gross_margin(ctx, params, tools) -> ModuleResult:
    return _run_step(ctx, params, STEP_GROSS_MARGIN, profit_like=True, cost_like=False,
                     extra_kv=lambda s: {STEP_GROSS_MARGIN: f"{s['Actual_Value']:,.0f}",
                                         "매출총이익률": f"{s['Actual_Margin'] * 100:.1f}%"})


def run_opex(ctx, params, tools) -> ModuleResult:
    return _run_step(ctx, params, STEP_OPEX, profit_like=False, cost_like=True,
                     extra_kv=lambda s: {STEP_OPEX: f"{s['Actual_Value']:,.0f}",
                                         "증감률": f"{s['Rate'] * 100:+.1f}%"})


def run_ebit(ctx, params, tools) -> ModuleResult:
    return _run_step(ctx, params, STEP_EBIT, profit_like=True, cost_like=False,
                     extra_kv=lambda s: {STEP_EBIT: f"{s['Actual_Value']:,.0f}",
                                         "영업이익률": f"{s['Actual_Margin'] * 100:.1f}%"})
