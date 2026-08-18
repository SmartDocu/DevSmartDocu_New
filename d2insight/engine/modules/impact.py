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

import pandas as pd

from d2insight.engine.chart import chart_spec
from d2insight.engine.modules._shared import get_item_variance
from d2insight.engine.schema import get_schema
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.dataset_builder import build_by_item_summary_dataset

# 툴 → 정렬 기준 컬럼
_RANK_COLUMN = {"dvi": "DVI", "shapley": "Shapley_Value"}

# 보고서 표에 싣는 컬럼(σ 구간 6개는 anomaly가 쓰는 값이라 총평 표에서는 뺀다)
_RENDER_COLUMNS = [
    "Dimension_Logical_Name", "Count", "Impact_Score",
    "Shapley_Value", "HHI", "Average_Z", "DVI",
]


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    """표시용 표 — Shapley는 배분 비율이라 퍼센트가 읽기 쉽다.

    "임팩트"는 절댓값 합(Σ|Δi|)이라 전체 증감액(total_variance)과 스케일이 다르다
    (§5 정의). 라벨에 그 사실을 박아 total_variance로 오인하지 않게 한다.
    컬럼 헤더에 "|"(파이프)를 쓰면 마크다운 표 렌더링이 깨지므로(2026-07-21 발견·수정) 쓰지 않는다.
    """
    return pd.DataFrame({
        "차원": df["Dimension_Logical_Name"],
        "항목수": df["Count"],
        "임팩트(변동총량, 전체 증감액과 별개 척도)": df["Impact_Score"].map(lambda v: f"{v:,.0f}"),
        "집중도(HHI)": df["HHI"].map(lambda v: f"{v:.2f}"),
        "평균Z": df["Average_Z"].map(lambda v: f"{v:.2f}"),
        "DVI": df["DVI"].map(lambda v: f"{v:,.0f}"),
        "Shapley": df["Shapley_Value"].map(lambda v: f"{v * 100:.1f}%"),
    })


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
    top3 = ", ".join(stats["Dimension_Logical_Name"].head(3).tolist())
    basis = "DVI" if rank_col == "DVI" else "Shapley"
    summary = (
        f"{schema.logical_name(measure)} 변화를 주도한 차원은 '{top['Dimension_Logical_Name']}'"
        f"({basis} 1위 — 임팩트 {top['Impact_Score']:,.0f}, 집중도(HHI) {top['HHI']:.2f}, "
        f"Shapley {top['Shapley_Value']:.2f}). 상위 3개 차원: {top3}."
    )

    # 임팩트(Σ|Δi|)는 전체 증감액(total_variance)과 스케일이 다른 지표다 — 혼동 방지용 참고 문구.
    tv = ctx.get("total_variance")
    if tv:
        summary += (
            f" (참고: 임팩트는 항목별 증감의 절댓값 합이라 전체 증감액 {tv['variance']:+,.0f}과 "
            f"직접 비교되는 수치가 아닙니다 — 항목이 많거나 서로 반대 방향으로 움직인 차원일수록 커집니다.)"
        )

    # Shapley는 높은데 DVI 상위 3위 밖인 차원 — 항목 다수가 한 방향으로 통째로 움직여
    # 변동성(Average_Z)이 0에 가까운 경우가 많다(예: 한 차원 전체가 이탈). 놓치기 쉬운 신호라 짚어준다.
    top3_names = stats["Dimension_Logical_Name"].head(3).tolist()
    high_shapley = stats.loc[stats["Shapley_Value"].idxmax()]
    if (high_shapley["Dimension_Logical_Name"] not in top3_names
            and high_shapley["Shapley_Value"] >= 0.3):
        reason = ("값 대부분이 같은 방향(예: 전량 이탈)으로 움직여 항목간 변동성(Average_Z)이 낮기 때문"
                   if high_shapley["Average_Z"] < 0.05 else
                   "항목 수가 많아 절댓값 합(임팩트)이 자연히 크게 잡히기 때문")
        summary += (
            f" 참고: '{high_shapley['Dimension_Logical_Name']}' 차원은 Shapley 기여율이 "
            f"{high_shapley['Shapley_Value'] * 100:.1f}%로 매우 높지만 {basis} 순위 상위 3위 밖입니다 — {reason}. "
            f"이 차원은 항목 단위(신규·이탈 등)로 별도로 들여다볼 필요가 있습니다."
        )

    render_table = _display_table(stats[[c for c in _RENDER_COLUMNS if c in stats.columns]])

    # 차트 — 선택된 순위 기준(DVI 또는 Shapley)으로 차원을 비교한다.
    chart_data = pd.DataFrame({"차원": stats["Dimension_Logical_Name"], basis: stats[rank_col]})

    return ModuleResult(
        outputs={"dimension_stats": stats},
        render=Render(
            summary=summary,
            table=render_table,
            chart=chart_spec(chart_data, "bar", f"차원별 {basis}"),
            key_value={
                "순위 기준": basis,
                "주도 차원": str(top["Dimension_Logical_Name"]),
                "차원 수": int(len(stats)),
            },
        ),
    )
