"""pnl_driver 모듈 — 영업이익(EBIT) 증감을 매출·매출원가·판매관리비 효과로 분해.

손익 분석 시나리오의 "원인 분석" 스텝(원본 표: Revenue↓COGS↓Gross Margin↓OPEX↓EBIT↓
원인 분석↓개선 방안). 앞선 5스텝(revenue_step~ebit_step)이 각 단계의 금액과 증감을 따로
보여줬다면, 이 스텝은 그 증감들을 "EBIT가 왜 이렇게 움직였는가" 하나의 질문으로 다시 묶는다.

EBIT = Revenue − COGS − OPEX이므로 증감도 그대로 분해된다(가법·검산 정확, 새 계산 아님):
    ΔEBIT = ΔRevenue − ΔCOGS − ΔOPEX
          = 매출 효과(ΔRevenue) + 매출원가 효과(−ΔCOGS) + 판매관리비 효과(−ΔOPEX)

opex 역할이 없으면 영업이익 자체가 없어 원인 분석이 성립하지 않으므로 명시적으로 실패한다(§11 Step 2).
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.chart import chart_spec
from d2insight.engine.modules._shared import get_pnl_ladder
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_COST, ROLE_OPEX, get_schema
from d2insight.engine.types import ModuleResult, Render


def _item_decompose(ctx, dimension: str, top_n: int) -> tuple[pd.DataFrame | None, str]:
    """차원 항목별 ΔEBIT 분해 표(2026-07-23 옵션 추가) — "영업이익 악화를 어느 항목이 주도했나".

    항목별로 매출 효과(ΔRevenue)·매출원가 효과(−ΔCOGS)·판관비 효과(−ΔOPEX)와 그 합(EBIT 증감)을
    내고 |EBIT 증감| 상위 top_n개를 돌려준다. 컬럼이 없으면 표 없이 사유만(총계 분해는 유효).
    """
    actual_df = ctx.get("actual_dataset")
    compare_df = ctx.get("compare_dataset")
    schema = get_schema(ctx)

    dim_col = dimension if dimension in actual_df.columns else schema.column(dimension)
    if not dim_col or dim_col not in actual_df.columns:
        return None, f" (차원 '{dimension}' 컬럼이 없어 항목별 상세는 생략)"

    amount_col = schema.column(ROLE_AMOUNT) or schema.key_measure
    cost_col, opex_col = schema.column(ROLE_COST), schema.column(ROLE_OPEX)
    if not cost_col or not opex_col:
        return None, " (cost/opex 역할 컬럼이 없어 항목별 상세는 생략)"

    def _sums(df: pd.DataFrame) -> pd.DataFrame:
        return df.groupby(dim_col)[[amount_col, cost_col, opex_col]].sum()

    actual_s, compare_s = _sums(actual_df), _sums(compare_df)
    delta = actual_s.sub(compare_s, fill_value=0.0)

    detail = pd.DataFrame({
        "매출 효과": delta[amount_col],
        "매출원가 효과": -delta[cost_col],
        "판매관리비 효과": -delta[opex_col],
    })
    detail["EBIT 증감"] = detail.sum(axis=1)
    detail = detail.reindex(detail["EBIT 증감"].abs().sort_values(ascending=False).index).head(top_n)

    display = pd.DataFrame({schema.logical_name(dim_col): detail.index.astype(str)})
    for col in ["매출 효과", "매출원가 효과", "판매관리비 효과", "EBIT 증감"]:
        # .values — display는 RangeIndex, detail은 항목명 인덱스라 그대로 대입하면 어긋난다
        display[col] = detail[col].map(lambda v: f"{v:+,.0f}").values
    return display.reset_index(drop=True), (
        f" {schema.logical_name(dim_col)}별 상위 {len(display)}개(|EBIT 증감| 기준) 상세 표 포함."
    )


def run(ctx, params, tools) -> ModuleResult:
    try:
        ladder = get_pnl_ladder(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))

    if not ladder["has_opex"]:
        return ModuleResult(
            status="failed",
            error="판매관리비(opex 역할)가 없어 영업이익이 산출되지 않아 원인 분석을 할 수 없습니다.",
        )

    steps = ladder["steps"]
    ebit_variance = steps["영업이익"]["Variance"]

    drivers = [
        ("매출 효과", steps["매출"]["Variance"]),
        ("매출원가 효과", -steps["매출원가"]["Variance"]),
        ("판매관리비 효과", -steps["판매관리비"]["Variance"]),
    ]
    rows = []
    for name, value in drivers:
        share = value / ebit_variance * 100 if ebit_variance else 0.0
        rows.append({"구분": name, "효과": value, "기여율": share})
    rows.sort(key=lambda r: abs(r["효과"]), reverse=True)
    driver_df = pd.DataFrame(rows)

    top = rows[0]
    direction = "개선" if ebit_variance >= 0 else "악화"
    top_direction = "긍정적" if top["효과"] >= 0 else "부정적"
    summary = (
        f"영업이익 {ebit_variance:+,.0f} {direction} — 가장 큰 요인은 {top['구분']}"
        f"({top['효과']:+,.0f}, 기여율 {top['기여율']:+.1f}%), {top_direction} 방향으로 작용했다."
    )

    display = pd.DataFrame({
        "구분": driver_df["구분"],
        "효과": driver_df["효과"].map(lambda v: f"{v:+,.0f}"),
        "EBIT 증감 기여율": driver_df["기여율"].map(lambda v: f"{v:+.1f}%"),
    })
    key_value = {"영업이익 증감": f"{ebit_variance:+,.0f}", "최대 요인": top["구분"]}

    # dimension 지정 시(옵션, 2026-07-23) 표는 항목별 상세로 바꾸고, 3요인 분해값은 key_value로
    # 옮겨 정보 손실 없이 보여준다(Render.table은 한 장이므로).
    dimension = (params or {}).get("dimension")
    if dimension:
        detail, note = _item_decompose(ctx, dimension, int((params or {}).get("top_n") or 10))
        summary += note
        if detail is not None:
            display = detail
            for r in rows:
                key_value[r["구분"]] = f"{r['효과']:+,.0f} ({r['기여율']:+.1f}%)"

    chart_data = pd.DataFrame({
        "구분": driver_df["구분"].astype(str),
        "효과": driver_df["효과"].astype(float),
    })

    return ModuleResult(
        render=Render(
            summary=summary,
            table=display,
            chart=chart_spec(chart_data, "bar", "영업이익 증감 요인"),
            key_value=key_value,
        ),
    )
