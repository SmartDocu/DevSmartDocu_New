"""within_contribution 모듈 — 차원 내 항목별 기여도 (§12-B).

dimension_impact(§12-A)가 "어느 차원이 흔들렸나"를 답한다면, 이 모듈은 그 차원 **안에서**
"어느 항목이 얼마나 밀었나"를 답한다. 기여율 = 항목 증감액 / 전체 증감액.

분모는 measure_summary가 산출한 공용 `total_variance`다. 여기서 다시 구하지 않는다(§6.2).
그래서 표의 기여율은 차원 전체를 합하면 정확히 1.0이 되고, 다른 스텝 숫자와 어긋나지 않는다.

상위를 기여율의 **절대값**으로 뽑는다. 증가 기여만 보면 그것을 깎아먹은 감소 항목이 표에서 사라져
"왜 이만큼밖에 안 늘었는지"를 설명할 수 없다. 증감 양방향을 함께 싣는다.
"""
from __future__ import annotations

from d2insight.engine.chart import chart_spec
from d2insight.engine.modules._shared import get_item_variance
from d2insight.engine.schema import get_schema
from d2insight.engine.types import ModuleResult, Render

import pandas as pd

_CHART_MAX = 12          # 막대 가독성 상한

_COLUMNS = [
    "Item_Name", "Comparison_Value", "Actual_Value", "Variance",
    "Rate", "Contribution_Rate", "New_Lost_Flag", "Is_Main",
]


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    """표시용 표 — 비율은 퍼센트로 보여야 읽힌다(기여율 1.7433 → +174.3%)."""
    return pd.DataFrame({
        "항목": df["Item_Name"],
        "비교기간": df["Comparison_Value"].map(lambda v: f"{v:,.0f}"),
        "분석기간": df["Actual_Value"].map(lambda v: f"{v:,.0f}"),
        "증감": df["Variance"].map(lambda v: f"{v:+,.0f}"),
        "증감률": df["Rate"].map(lambda v: f"{v * 100:+.1f}%"),
        "기여율": df["Contribution_Rate"].map(lambda v: f"{v * 100:+.1f}%"),
        "신규/단종": df["New_Lost_Flag"],
        "주요항목": df["Is_Main"].map(lambda v: "O" if v == 1 else ""),
    })


def run(ctx, params, tools) -> ModuleResult:
    dimension = params.get("dimension")
    if not dimension:
        return ModuleResult(status="failed", error="params.dimension이 필요합니다(차원 미지정).")

    key_measure = get_schema(ctx).key_measure
    measure = params.get("measure")
    if measure and measure != key_measure:
        return ModuleResult(
            status="failed",
            error=f"기여도 분석은 현재 핵심 measure '{key_measure}'만 지원합니다 (요청: '{measure}').",
        )

    total_variance = ctx.get("total_variance")
    if not total_variance or not total_variance.get("variance"):
        # 전체 증감이 0이면 기여율의 분모가 없다. 비율 대신 증감액만 보는 게 맞으므로 명시적 실패.
        return ModuleResult(status="failed", error="전체 증감액이 0이라 기여율을 계산할 수 없습니다.")

    byitem = get_item_variance(ctx)
    sub = byitem[byitem["Dimension_Logical_Name"] == dimension]
    if sub.empty:
        available = sorted(byitem["Dimension_Logical_Name"].unique().tolist())
        return ModuleResult(
            status="failed",
            error=f"차원 '{dimension}' 데이터가 없습니다. 사용 가능: {available}",
        )

    top_n = int(params.get("top_n") or 20)
    ranked = (
        sub.assign(_abs=sub["Contribution_Rate"].abs())
        .sort_values("_abs", ascending=False)
        .head(top_n)
        .drop(columns="_abs")
        .reset_index(drop=True)
    )

    table = _display_table(ranked[[c for c in _COLUMNS if c in ranked.columns]])

    # 상위 항목이 전체 증감을 얼마나 설명하는지 — "몇 개만 보면 되는가"에 대한 답.
    covered = float(ranked["Contribution_Rate"].sum())
    up = ranked[ranked["Variance"] > 0]
    down = ranked[ranked["Variance"] < 0]
    top_up = up.iloc[0] if not up.empty else None
    top_down = down.iloc[0] if not down.empty else None

    parts = [f"'{dimension}' 차원 상위 {len(ranked)}개 항목이 전체 증감의 {covered * 100:+.1f}%를 설명"]
    if top_up is not None:
        parts.append(
            f"최대 증가 {top_up['Item_Name']} ({top_up['Variance']:+,.0f}, "
            f"기여 {top_up['Contribution_Rate'] * 100:+.1f}%)"
        )
    if top_down is not None:
        parts.append(
            f"최대 감소 {top_down['Item_Name']} ({top_down['Variance']:+,.0f}, "
            f"기여 {top_down['Contribution_Rate'] * 100:+.1f}%)"
        )
    summary = " — ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0] + "."

    new_cnt = int((ranked["New_Lost_Flag"] == "New").sum())
    lost_cnt = int((ranked["New_Lost_Flag"] == "Lost").sum())

    # 차트 — 항목별 증감액(양/음 함께). 증가를 깎은 감소 항목이 한눈에 보인다.
    chart_data = pd.DataFrame({
        "항목": ranked["Item_Name"].head(_CHART_MAX),
        "증감": ranked["Variance"].head(_CHART_MAX),
    })

    return ModuleResult(
        outputs={"within_contribution": ranked},
        render=Render(
            summary=summary,
            table=table,
            chart=chart_spec(chart_data, "bar", f"'{dimension}' 항목별 증감"),
            key_value={
                "차원": dimension,
                "상위 항목수": len(ranked),
                "상위 누적 기여율": f"{covered * 100:+.1f}%",
                "상위 내 신규/단종": f"{new_cnt} / {lost_cnt}",
            },
        ),
    )
