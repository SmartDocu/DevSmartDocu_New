"""new_lost_detection 모듈 — 신규·이탈 현황 (§6, 개정 2026-07-14).

방침 개정 배경 (보고서작성방안.md 4·6장 참조)
  1개월 비교만으로 신규/이탈을 판정하면 **구매 주기가 긴 업종에서 거의 전원이 신규 또는 이탈로
  분류된다.** 2014-01 실측: 고객 2,073명 중 1,993명 '신규', 지난달 1,970명 중 1,890명 '이탈',
  두 달 모두 구매한 고객은 80명. 이는 이탈이 아니라 "이번 달에 안 샀다"일 뿐이다.
  그 결과 고객 차원 순효과가 전체 증감의 97%를 차지하는 동어반복이 나왔다.

현 기준: 과거 이력(history_dataset)을 보고 생애주기를 판정한다(_shared.get_item_lifecycle).
  진성신규 / 복귀 / 유지 / 진성이탈 / 일시미구매

  - 진성이탈  : 반복 구매하던 항목이 사라짐 → **관리 대상**
  - 일시미구매: 단발 구매자가 이번에 안 옴 → 구매 주기일 뿐, 이탈로 보고하지 않는다
  - 복귀      : 과거 구매 이력이 있는 항목의 재구매 → 신규로 부풀리지 않는다

history_dataset이 없으면 생애주기를 판정할 수 없다. 이때는 **1개월 정의로 조용히 되돌아가지 않고**
"판정 불가"임을 보고서에 명시한다(§11 Step 2 실패 정책).

§14(이상징후)와 역할이 다르다. §6은 총량(건수·금액), §14는 개별 이상치다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.chart import chart_spec
from d2insight.engine.modules._shared import (
    LIFECYCLE_CHURN, LIFECYCLE_DORMANT, LIFECYCLE_KEEP, LIFECYCLE_NEW, LIFECYCLE_RETURN,
    get_item_variance, get_lifecycle_effects,
)
from d2insight.engine.schema import ROLE_ITEM, ROLE_PARTY, get_schema
from d2insight.engine.types import ModuleResult, Render

# 표에 싣는 생애주기 순서 (유지는 건수만 참고용)
_STAGES = [LIFECYCLE_NEW, LIFECYCLE_RETURN, LIFECYCLE_CHURN, LIFECYCLE_DORMANT]

_CHART_MAX = 12    # 차트에 싣는 개별 항목 수(상위 |금액|)


def _display_table(df: pd.DataFrame, name_of) -> pd.DataFrame:
    # 차원 표시명은 데이터 정의(Logical_Name)에서 온다 → 구매분석이면 '품목·공급사'로 찍힌다.
    out = pd.DataFrame({"차원": df["Dimension_Logical_Name"].map(name_of)})
    for stage in _STAGES:
        out[f"{stage} 건수"] = df[f"{stage}_Count"].map(lambda v: f"{int(v):,}")
        out[f"{stage} 금액"] = df[f"{stage}_Amount"].map(lambda v: f"{v:+,.0f}")
    out["유입 합계"] = df["Inflow_Amount"].map(lambda v: f"{v:+,.0f}")
    out["유출 합계"] = df["Outflow_Amount"].map(lambda v: f"{v:+,.0f}")
    out["순효과"] = df["Net_Amount"].map(lambda v: f"{v:+,.0f}")
    return out


def run(ctx, params, tools) -> ModuleResult:
    merged = get_lifecycle_effects(ctx)
    if merged is None:
        # 1개월 정의로 되돌아가면 "이탈 1,890건" 같은 무의미한 수치가 나온다. 명시적으로 실패시킨다.
        return ModuleResult(
            status="failed",
            error=("과거 이력(history_dataset)이 없어 신규·이탈 생애주기를 판정할 수 없습니다. "
                   "1개월 비교만으로는 구매 주기와 실제 이탈을 구분할 수 없습니다."),
        )

    schema = get_schema(ctx)
    byitem = get_item_variance(ctx)
    all_dims = set(byitem["Dimension_Logical_Name"].unique())
    requested = params.get("dimensions") or ([params["dimension"]] if params.get("dimension") else None)
    if requested:
        unknown = [d for d in requested if d not in all_dims]
        if unknown:
            return ModuleResult(
                status="failed",
                error=f"차원 {unknown} 데이터가 없습니다. 사용 가능: {sorted(all_dims)}",
            )
        target_dims = requested
    else:
        # 방침 6장의 "상품·고객"은 판매 도메인에서 item·party가 불리는 이름일 뿐이다.
        # 역할로 찾으므로 구매(품목·공급사)·생산(제품·설비)에서도 그대로 동작한다.
        target_dims = [d for d in (schema.column(ROLE_ITEM), schema.column(ROLE_PARTY))
                       if d and d in all_dims]
    if not target_dims:
        return ModuleResult(
            status="failed",
            error="신규·이탈을 셀 대상 차원이 없습니다. 데이터소스 정의에 item·party 역할을 선언하세요.",
        )

    merged = merged[merged["Dimension_Logical_Name"].isin(target_dims)]
    if merged.empty:
        return ModuleResult(status="failed", error=f"대상 차원 {target_dims}의 생애주기 판정 결과가 없습니다.")

    rows = []
    for dim in target_dims:
        sub = merged[merged["Dimension_Logical_Name"] == dim]
        row = {"Dimension_Logical_Name": dim,
               "Keep_Count": int((sub["Lifecycle"] == LIFECYCLE_KEEP).sum())}
        net = 0.0
        for stage in _STAGES:
            s = sub[sub["Lifecycle"] == stage]
            amount = float(s["Effect"].sum())
            row[f"{stage}_Count"] = len(s)
            row[f"{stage}_Amount"] = amount
            net += amount
        # 유입·유출 합계를 여기서 내준다 — 결론이 직접 더하지 않게 하기 위함(재계산 금지 §6.2).
        row["Inflow_Amount"] = row[f"{LIFECYCLE_NEW}_Amount"] + row[f"{LIFECYCLE_RETURN}_Amount"]
        row["Outflow_Amount"] = row[f"{LIFECYCLE_CHURN}_Amount"] + row[f"{LIFECYCLE_DORMANT}_Amount"]
        row["Net_Amount"] = net
        rows.append(row)
    counts = pd.DataFrame(rows)

    # 개별 항목 목록 — 진성 신규/이탈만(일시미구매는 이탈이 아니므로 목록에서 뺀다)
    items = merged[merged["Lifecycle"].isin([LIFECYCLE_NEW, LIFECYCLE_RETURN, LIFECYCLE_CHURN])].copy()
    items = items.reindex(items["Effect"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    top_n = int(params.get("top_n") or 10)

    parts = []
    for _, r in counts.iterrows():
        parts.append(
            f"{schema.logical_name(r['Dimension_Logical_Name'])} "
            f"진성신규 {int(r[f'{LIFECYCLE_NEW}_Count']):,}건"
            f"({r[f'{LIFECYCLE_NEW}_Amount']:+,.0f}) / 진성이탈 "
            f"{int(r[f'{LIFECYCLE_CHURN}_Count']):,}건({r[f'{LIFECYCLE_CHURN}_Amount']:+,.0f})"
        )
    dormant_total = int(counts[f"{LIFECYCLE_DORMANT}_Count"].sum())
    net_total = float(counts["Net_Amount"].sum())
    summary = (
        f"신규·이탈 순효과 {net_total:+,.0f} — " + ", ".join(parts) +
        f". 일시미구매(구매 주기에 따른 미등장) {dormant_total:,}건은 이탈로 보지 않음."
    )

    key_value = {
        "신규·이탈 순효과": f"{net_total:+,.0f}",
        "일시미구매(이탈 아님)": f"{dormant_total:,}건",
    }
    if not items.empty:
        top = items.iloc[0]
        key_value["금액 최대"] = (
            f"{schema.logical_name(top['Dimension_Logical_Name'])} {top['Item_Name']} "
            f"({top['Lifecycle']} {top['Effect']:+,.0f})"
        )

    # 차트: 진성신규·복귀·이탈 개별 항목 Top을 금액 효과로(부호 있는 단일 막대).
    #   신규·복귀는 +, 진성이탈은 -로 나와 "누가 유입/유출을 이끌었나"가 한눈에 보인다.
    #   차원별 총량은 표가 맡으므로 차트는 개별 드라이버에 집중한다. 차원 금액 규모가
    #   1,000배까지 벌어져(상품 vs 고객) 차원별 그룹 막대는 작은 쪽이 안 보이는 문제도 피한다.
    chart_top = items.head(_CHART_MAX)
    chart_data = pd.DataFrame({
        "항목": chart_top["Item_Name"].astype(str),
        "금액효과": chart_top["Effect"].astype(float),
    })

    return ModuleResult(
        outputs={"count_summary": counts, "new_lost_items": items.head(top_n)},
        render=Render(summary=summary,
                      table=_display_table(counts, schema.logical_name),
                      chart=chart_spec(chart_data, "bar", "신규·이탈 개별 항목 Top (금액 효과)"),
                      key_value=key_value),
    )
