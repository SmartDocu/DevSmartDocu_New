"""customer_lifecycle 모듈 — 고객(party) 차원의 신규/이탈을 독립 스텝으로 분리.

시나리오 "고객 분석"의 원본 스텝은 `신규 고객 ↓ 이탈 고객`이 서로 다른 스텝이다(스텝=섹션
원칙, 2026-07-20). new_lost_detection은 여러 차원을 한 번에 보여주는 통합 모듈이라 신규·이탈을
갈라 두 스텝으로 쓸 수 없으므로(같은 모듈이 같은 이름표를 두 번 생산 — §3.4-2), 이 모듈은 리프
(produces=[])로 두 함수를 나눠 각자 party 차원 하나만, 신규 쪽/이탈 쪽만 본다.

계산은 new_lost_detection과 같은 캐시(`_shared.get_lifecycle_effects`)를 공유하므로 숫자가
항상 일치한다 — 이 모듈이 별도로 재계산하지 않는다(§6.2).
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.chart import chart_spec
from d2insight.engine.modules._shared import (
    LIFECYCLE_CHURN, LIFECYCLE_DORMANT, LIFECYCLE_NEW, LIFECYCLE_RETURN, get_lifecycle_effects,
)
from d2insight.engine.schema import ROLE_PARTY, get_schema
from d2insight.engine.types import ModuleResult, Render

_CHART_MAX = 12


def _party_slice(ctx, stages: list[str]) -> tuple[pd.DataFrame, str, str] | ModuleResult:
    """party 차원으로 필터링한 lifecycle_effects 조각. 실패하면 ModuleResult를 그대로 돌려준다."""
    merged = get_lifecycle_effects(ctx)
    if merged is None:
        return ModuleResult(
            status="failed",
            error=("과거 이력(history_dataset)이 없어 고객 생애주기를 판정할 수 없습니다. "
                   "1개월 비교만으로는 구매 주기와 실제 이탈을 구분할 수 없습니다."),
        )
    schema = get_schema(ctx)
    party = schema.column(ROLE_PARTY)
    if not party:
        return ModuleResult(status="failed", error="고객(party) 역할이 없어 신규/이탈 고객을 가를 수 없습니다.")
    if party not in set(merged["Dimension_Logical_Name"].unique()):
        return ModuleResult(status="failed", error=f"'{party}' 차원의 생애주기 판정 결과가 없습니다.")

    party_all = merged[merged["Dimension_Logical_Name"] == party]
    sub = party_all[party_all["Lifecycle"].isin(stages)]
    return sub, party, schema.logical_name(party)


def _render(sub: pd.DataFrame, label: str, stage_title: str, stages: list[str],
            top_n: int, extra_note: str = "") -> ModuleResult:
    counts = {stage: int((sub["Lifecycle"] == stage).sum()) for stage in stages}
    amounts = {stage: float(sub[sub["Lifecycle"] == stage]["Effect"].sum()) for stage in stages}
    total_count = sum(counts.values())
    total_amount = sum(amounts.values())

    items = sub.reindex(sub["Effect"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    breakdown = ", ".join(f"{stage} {counts[stage]:,}건({amounts[stage]:+,.0f})" for stage in stages)
    summary = (
        f"{label} {stage_title} {total_count:,}건, 금액효과 {total_amount:+,.0f} — {breakdown}."
        + extra_note
    )

    table = None
    if not items.empty:
        table = pd.DataFrame({
            "고객": items["Item_Name"],
            "생애주기": items["Lifecycle"],
            "금액효과": items["Effect"].map(lambda v: f"{v:+,.0f}"),
        }).head(top_n)

    chart = None
    chart_top = items.head(_CHART_MAX)
    if not chart_top.empty:
        chart_data = pd.DataFrame({
            "고객": chart_top["Item_Name"].astype(str),
            "금액효과": chart_top["Effect"].astype(float),
        })
        chart = chart_spec(chart_data, "bar", f"{label} {stage_title} Top")

    key_value = {
        f"{stage_title} 건수": f"{total_count:,}건",
        f"{stage_title} 금액효과": f"{total_amount:+,.0f}",
    }
    return ModuleResult(render=Render(summary=summary, table=table, chart=chart, key_value=key_value))


def run_new_customers(ctx, params, tools) -> ModuleResult:
    stages = [LIFECYCLE_NEW, LIFECYCLE_RETURN]
    sliced = _party_slice(ctx, stages)
    if isinstance(sliced, ModuleResult):
        return sliced
    sub, _, label = sliced
    top_n = int(params.get("top_n") or 10)
    return _render(sub, label, "신규 고객", stages, top_n)


def run_lost_customers(ctx, params, tools) -> ModuleResult:
    stages = [LIFECYCLE_CHURN]
    sliced = _party_slice(ctx, stages)
    if isinstance(sliced, ModuleResult):
        return sliced
    sub, party, label = sliced
    top_n = int(params.get("top_n") or 10)

    # 일시미구매는 이탈이 아니므로 집계에서 빼되, 몇 건인지는 밝혀 "이탈이 적어 보이는" 착시를 막는다.
    merged = get_lifecycle_effects(ctx)
    dormant_count = int((merged[(merged["Dimension_Logical_Name"] == party)
                                 & (merged["Lifecycle"] == LIFECYCLE_DORMANT)]).shape[0])
    note = f" 일시미구매(구매 주기에 따른 미등장) {dormant_count:,}건은 이탈로 보지 않음."
    return _render(sub, label, "이탈 고객", stages, top_n, extra_note=note)
