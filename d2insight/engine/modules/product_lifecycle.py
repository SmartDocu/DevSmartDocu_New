"""product_lifecycle 모듈 — 제품 수명주기(PLC) 단계 분류 (시나리오 4 'Life Cycle').

항목별 월별 매출 추이로 도입/성장/성숙/쇠퇴를 판정한다. new_lost의 생애주기(신규/복귀/유지/이탈,
활동 유무 기반)와 **다르다** — 이건 **추이 기울기·활동 기간** 기반이다.

규약(config 임계값):
    age_months = 활동(매출>0) 개월수
    growth     = (후반부 평균 − 전반부 평균) / 전반부 평균     추이 방향
    도입 : age ≤ PLC_INTRO_MAX_MONTHS        (신생·램프업)
    성장 : growth ≥ PLC_GROWTH_UP
    쇠퇴 : growth ≤ PLC_GROWTH_DOWN
    성숙 : 그 외 (확립·평탄)

분류 단위(grain)는 item 역할 기본, params.dimensions로 명시 지정. 컬럼명을 코드에 박지 않고
스키마 역할(item/amount/period)로 질의한다(§7.4). 역할 없으면 조용히 처리하지 않고 명시적 실패(§11 Step2).
다월 추이가 필요하므로 금액을 항목별·기간별로 직접 요청한다(get_series).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import d2insight.config as config
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_full_schema, get_series, pick_dimension, role_column
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_ITEM
from d2insight.engine.types import ModuleResult

_STAGE_ORDER = ["도입", "성장", "성숙", "쇠퇴"]


def _stage(age: int, growth: float, intro_max: int, g_up: float, g_down: float) -> str:
    if age <= intro_max:
        return "도입"
    if growth >= g_up:
        return "성장"
    if growth <= g_down:
        return "쇠퇴"
    return "성숙"


def run(ctx, params, tools) -> ModuleResult:
    schema = get_full_schema(ctx)
    amount_col = params.get("measure") or role_column(ctx, ROLE_AMOUNT) or schema.key_measure
    requested = params.get("dimensions")
    item_col = requested[0] if requested else pick_dimension(ctx, ROLE_ITEM, [amount_col])
    if not item_col:
        return ModuleResult(
            status="failed",
            error="분류할 항목 차원이 없습니다. item 의미 표시를 선언하거나 params.dimensions를 지정하세요.",
        )
    grain = [item_col]

    # 창을 자르면 전반/후반 분할 기준이 통째로 이동하므로 판정 결과가 달라진다. 창 지정이 없으면
    # 보고서 설정의 기간 수 전체를 쓴다(get_series).
    try:
        history = get_series(ctx, amount_col, item_col, params)
    except ValueError as e:
        return ModuleResult(status="failed", error=f"기간별 값 조회에 실패했습니다: {e}")
    period_col = history.columns[0]
    window_note = ""

    months = sorted(history[period_col].unique())
    if len(months) < 2:
        return ModuleResult(status="failed", error="추이 판정에 최소 2개월 이력이 필요합니다.")

    pivot = (
        history.groupby(grain + [period_col])[amount_col].sum()
        .unstack(fill_value=0.0)
        .reindex(columns=months, fill_value=0.0)
    )
    if pivot.empty:
        return ModuleResult(status="failed", error="분류 대상 데이터가 없습니다.")

    intro_max = int(getattr(config, "PLC_INTRO_MAX_MONTHS", 2))
    g_up = float(getattr(config, "PLC_GROWTH_UP", 0.15))
    g_down = float(getattr(config, "PLC_GROWTH_DOWN", -0.15))
    half = len(months) // 2

    values = pivot.values.astype(float)
    age = (values > 0).sum(axis=1)
    first_avg = values[:, :half].mean(axis=1) if half else np.zeros(len(values))
    second_avg = values[:, half:].mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        growth = np.where(first_avg > 0, (second_avg - first_avg) / first_avg,
                          np.where(second_avg > 0, np.inf, 0.0))

    res = pd.DataFrame({
        "Recent_Value": values[:, -1],
        "Total_Value": values.sum(axis=1),
        "Age_Months": age.astype(int),
        "Growth": np.round(np.where(np.isfinite(growth), growth, np.nan), 4),
    }, index=pivot.index).reset_index()
    res["Item_Name"] = res[grain].astype(str).agg(" × ".join, axis=1)
    res["Stage"] = [
        _stage(int(a), float(g) if np.isfinite(g) else float("inf"), intro_max, g_up, g_down)
        for a, g in zip(age, growth)
    ]
    res = res.sort_values("Total_Value", ascending=False).reset_index(drop=True)

    by_stage = res["Stage"].value_counts().to_dict()
    stage_str = ", ".join(f"{s} {by_stage.get(s, 0)}개" for s in _STAGE_ORDER if by_stage.get(s))
    decline_n = int(by_stage.get("쇠퇴", 0))

    counts = res["Stage"].value_counts().reindex(_STAGE_ORDER).dropna()
    chart_df = pd.DataFrame({"단계": counts.index, "항목수": counts.values.astype(int)})

    top_n = int(params.get("top_n") or 20)
    table = res[["Item_Name", "Stage", "Age_Months", "Growth", "Recent_Value"]].rename(
        columns={"Item_Name": "항목", "Stage": "단계", "Age_Months": "활동개월",
                "Growth": "성장률", "Recent_Value": "최근매출"}).head(top_n)

    render = render_from_dataframe(
        table,
        purpose="항목별 매출 추이로 수명주기 단계(도입/성장/성숙/쇠퇴)를 분류.",
        narrative_hint=(
            f"단계 분포({stage_str})를 밝히고, 쇠퇴 단계 {decline_n}개는 관리·정리 검토 대상임을 "
            f"짚어라. 판정 구간: {months[0]}~{months[-1]}({len(months)}개월).{window_note}"
        ),
        params={"기준": schema.logical_name(amount_col)}, label="product_lifecycle", chart_df=chart_df,
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {"분류 항목수": len(res), "쇠퇴 단계": f"{decline_n}개"}
    return ModuleResult(outputs={"lifecycle_stages": res}, render=render)
