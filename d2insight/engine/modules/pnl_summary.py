"""pnl_summary 모듈 — 손익 계단 통합 뷰 (제품 분석 시나리오의 단일 '이익' 스텝).

    매출(Revenue)
      − 매출원가(COGS)        ← cost 역할
    = 매출총이익(Gross Margin)
      − 판매관리비(OPEX)      ← opex 역할
    = 영업이익(EBIT)

손익 분석 시나리오는 이 다섯 단계를 각각 독립 스텝(revenue_step~ebit_step, §7.4)으로 나눠 보지만,
제품 분석 시나리오는 "이익" 하나로 한눈에 보면 되므로 이 모듈이 전체 계단을 한 번에 낸다. 두 경로
모두 `_shared.get_pnl_ladder()`의 같은 계산 결과를 나눠 쓰므로 숫자가 항상 일치한다.

역할이 없으면 조용히 0으로 채우지 않는다(§11 Step 2). 원가가 없으면 손익 자체가 성립하지 않으므로
명시적 실패, 판관비만 없으면 영업이익 단계를 빼고 매출총이익까지만 낸다 — 어디까지 냈는지 밝힌다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_pnl_ladder
from d2insight.engine.types import ModuleResult

STEP_GROSS_MARGIN = "매출총이익"
STEP_EBIT = "영업이익"


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "구분": df["Step"], "비교기간": df["Comparison_Value"], "분석기간": df["Actual_Value"],
        "증감": df["Variance"], "증감률(%)": df["Rate"] * 100,
        "매출 대비(%)": df["Actual_Margin"] * 100,
        "전기 대비(%p)": (df["Actual_Margin"] - df["Comparison_Margin"]) * 100,
    })


def run(ctx, params, tools) -> ModuleResult:
    try:
        ladder = get_pnl_ladder(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))

    steps = ladder["steps"]
    has_opex = ladder["has_opex"]
    pnl_df = pd.DataFrame(list(steps.values()))

    note = "" if has_opex else (" 판매관리비(opex 역할)가 없어 영업이익 단계는 산출하지 못했습니다. "
                                 "매출총이익까지만 유효합니다.")

    bottom = steps[STEP_EBIT] if has_opex else steps[STEP_GROSS_MARGIN]
    direction = "개선" if bottom["Variance"] >= 0 else "악화"
    margin_shift = (bottom["Actual_Margin"] - bottom["Comparison_Margin"]) * 100
    rev = steps["매출"]
    summary = (
        f"{bottom['Step']} {bottom['Actual_Value']:,.0f} "
        f"({bottom['Variance']:+,.0f}, {bottom['Rate'] * 100:+.1f}%) — {direction}. "
        f"매출 {rev['Actual_Value']:,.0f}({rev['Rate'] * 100:+.1f}%), "
        f"{bottom['Step']}률 {bottom['Actual_Margin'] * 100:.1f}% ({margin_shift:+.2f}%p)."
        + note
    )

    key_value = {
        "매출": f"{rev['Actual_Value']:,.0f}",
        STEP_GROSS_MARGIN: f"{steps[STEP_GROSS_MARGIN]['Actual_Value']:,.0f}",
        "매출총이익률": f"{steps[STEP_GROSS_MARGIN]['Actual_Margin'] * 100:.1f}%",
    }
    if has_opex:
        key_value[STEP_EBIT] = f"{steps[STEP_EBIT]['Actual_Value']:,.0f}"
        key_value["영업이익률"] = f"{steps[STEP_EBIT]['Actual_Margin'] * 100:.1f}%"

    render = render_from_dataframe(
        _display_table(pnl_df), purpose="손익 계단(매출→매출총이익→영업이익)을 한눈에 제시.",
        narrative_hint=summary, params={"기준": "손익 계단"}, label="pnl_summary",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = key_value
    return ModuleResult(outputs={"pnl_steps": pnl_df}, render=render)
