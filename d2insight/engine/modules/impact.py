"""dimension_impact 모듈 — 어느 차원이 변화를 주도했는가 (§12-A).

차원별 통계(§5 By_Item_Summary_DataSet)를 만들어 `dimension_stats` 이름표로 내보낸다.
  - Impact_Score  : Σ|항목 증감액|  — 그 차원이 흔들린 총량
  - HHI           : Σ(|Δi|/Impact)² — 그 흔들림이 소수 항목에 몰렸는가(집중도)
  - Average_Z     : 평균 |Z|        — 항목 증감률이 평균에서 얼마나 벌어졌는가
  - DVI           : Impact × HHI × Average_Z — "크고, 몰렸고, 튄" 차원일수록 높다
  - Shapley_Value : 차원 조합 기여 배분(합=1)

툴 선택(shapley/dvi)은 **순위 근거**를 고른다. 두 지표를 모두 계산해 표로 보여주되,
정렬·상위 지목은 선택된 툴 기준으로 한다(계산은 같고 해석 기준만 다름).

산출된 dimension_stats는 anomaly_detection(§14)의 σ 구간과 cross_drilldown(§15)의
대상 차원 선정에 그대로 재사용된다(재계산 금지).
"""
from __future__ import annotations

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_item_variance
from d2insight.engine.schema import get_schema
from d2insight.engine.types import ModuleResult
from d2insight.engine.pipeline.dataset_builder import build_by_item_summary_dataset

# 툴 → 정렬 기준 컬럼
_RANK_COLUMN = {"dvi": "DVI", "shapley": "Shapley_Value"}

# 표에 후보로 내놓는 컬럼 — DVI/HHI/평균Z 같은 내부 계산용 지표도 포함해 후보로 주고,
# 실제로 표에 넣을지는 LLM이 고른다(dimension_stats 이름표 자체는 그대로 전체를 남겨
# anomaly_detection/cross_drilldown이 재계산 없이 계속 쓴다).
_RENDER_COLUMNS = ["Dimension_Logical_Name", "Count", "Impact_Score", "HHI", "Average_Z", "DVI", "Shapley_Value"]


def run(ctx, params, tools) -> ModuleResult:
    schema = get_schema(ctx)
    # measure별로 따로 계산·캐시한다(2026-07-24 4단계) — get_item_variance가 measure를 받아
    # 캐시 키에 반영하므로, 같은 보고서에서 매출 기준 dimension_impact와 수량 기준을 각각
    # 계산해도 서로 덮어쓰지 않는다.
    measure = params.get("measure") or schema.key_measure

    byitem = get_item_variance(ctx, measure)
    if byitem is None or byitem.empty:
        return ModuleResult(status="failed", error="차원×항목 증감 데이터가 비어 있습니다.")

    dimensions = params.get("dimensions")
    if dimensions:
        byitem = byitem[byitem["Dimension_Logical_Name"].isin(dimensions)]
        if byitem.empty:
            return ModuleResult(
                status="failed",
                error=f"요청한 차원 {dimensions}에 해당하는 데이터가 없습니다.",
            )

    stats = build_by_item_summary_dataset(
        byitem, ctx.get("actual_dataset"), ctx.get("compare_dataset"), measure=measure
    )
    if stats.empty:
        return ModuleResult(status="failed", error="차원별 통계를 계산하지 못했습니다.")

    tool = tools[0] if tools else "dvi"          # runner가 선택 툴을 리스트로 넘긴다
    rank_col = _RANK_COLUMN.get(tool, "DVI")
    stats = stats.sort_values(rank_col, ascending=False).reset_index(drop=True)

    top = stats.iloc[0]
    basis = "DVI" if rank_col == "DVI" else "Shapley"
    display = stats[[c for c in _RENDER_COLUMNS if c in stats.columns]]

    render = render_from_dataframe(
        display,
        purpose="어느 차원이 변화를 가장 크게 설명하는지 제시.",
        narrative_hint=(
            "1위 차원이 전체 변화의 몇 %를 설명하는지만 짧게 말하라. DVI·HHI·집중도·평균Z 같은 "
            "내부 지표 용어는 본문에 쓰지 마라 — 구체적으로 어떤 항목이 얼마나 움직였는지는 "
            "다음 스텝(항목별 증감)이 다룬다."
        ),
        params={"측정값": schema.logical_name(measure), "순위 기준": basis},
        label="dimension_impact", cache=params.get("_llm_render_cache"),
    )
    render.key_value = {
        "순위 기준": basis,
        "주도 차원": str(top["Dimension_Logical_Name"]),
        "차원 수": int(len(stats)),
    }

    return ModuleResult(outputs={"dimension_stats": stats}, render=render)
