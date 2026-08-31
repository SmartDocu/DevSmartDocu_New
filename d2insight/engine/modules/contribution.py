"""within_contribution 모듈 — 차원 내 항목별 기여도 (§12-B).

dimension_impact(§12-A)가 "어느 차원이 흔들렸나"를 답한다면, 이 모듈은 그 차원 **안에서**
"어느 항목이 얼마나 밀었나"를 답한다. 기여율 = 항목 증감액 / 전체 증감액.

분모는 measure_summary가 산출한 공용 `total_variance`다. 여기서 다시 구하지 않는다(§6.2).
그래서 표의 기여율은 차원 전체를 합하면 정확히 1.0이 되고, 다른 스텝 숫자와 어긋나지 않는다.

상위를 기여율의 **절대값**으로 뽑는다. 증가 기여만 보면 그것을 깎아먹은 감소 항목이 표에서 사라져
"왜 이만큼밖에 안 늘었는지"를 설명할 수 없다. 증감 양방향을 함께 싣는다.
"""
from __future__ import annotations

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_item_variance
from d2insight.engine.schema import get_schema
from d2insight.engine.types import ModuleResult

_COLUMNS = [
    "Item_Name", "Comparison_Value", "Actual_Value", "Variance",
    "Rate", "Contribution_Rate", "New_Lost_Flag", "Is_Main",
]


def run(ctx, params, tools) -> ModuleResult:
    dimension = params.get("dimension")
    if not dimension:
        # 차원을 안 정해줬으면 dimension_impact(§12-A)가 찾은 1위 차원을 그대로 물려받는다
        # — Shapley 기준(항목 수에 덜 휘둘리는 표준 기여도 분해).
        stats = ctx.get("dimension_stats")
        if stats is None or stats.empty:
            return ModuleResult(status="failed", error="params.dimension이 없고 dimension_stats도 없습니다.")
        dimension = stats.sort_values("Shapley_Value", ascending=False)["Dimension_Logical_Name"].iloc[0]

    schema = get_schema(ctx)
    key_measure = schema.key_measure
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

    display = ranked[[c for c in _COLUMNS if c in ranked.columns]]

    # 상위 항목이 전체 증감을 얼마나 설명하는지 — "몇 개만 보면 되는가"에 대한 답.
    covered = float(ranked["Contribution_Rate"].sum())
    new_cnt = int((ranked["New_Lost_Flag"] == "New").sum())
    lost_cnt = int((ranked["New_Lost_Flag"] == "Lost").sum())

    dim_name = schema.logical_name(dimension)
    render = render_from_dataframe(
        display,
        purpose="차원 안에서 어느 항목이 전체 증감을 얼마나 밀었는지 제시.",
        narrative_hint=(
            "증가를 이끈 항목과 그것을 깎아먹은 감소 항목을 함께 짚어라. 상위 항목이 전체 증감을 "
            "얼마나 설명하는지(누적 기여율), 신규·단종 항목이 끼어 있는지도 언급하라."
        ),
        params={"차원": dim_name, "상위 항목수": len(ranked)},
        label="within_contribution", cache=params.get("_llm_render_cache"),
    )
    render.key_value = {
        "차원": dim_name,
        "상위 항목수": len(ranked),
        "상위 누적 기여율": f"{covered * 100:+.1f}%",
        "상위 내 신규/단종": f"{new_cnt} / {lost_cnt}",
    }

    return ModuleResult(outputs={"within_contribution": ranked}, render=render)
