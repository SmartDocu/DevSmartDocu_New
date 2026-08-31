"""stock_movement 모듈 — 재고 이동(기초·입고·출고·기말)과 정합성 점검 (시나리오 6 '재고 분석').

    기초재고 + 입고 − 출고 = 기말재고

이 항등식이 맞는지 먼저 확인한다. 어긋나면 재고 데이터에 누락·중복·미기록 이동이 있다는 뜻이라
분석보다 **데이터 신뢰성 경고가 먼저**다. 차이를 조용히 흡수하면 이후 회전율·안전재고가 전부
틀린 전제 위에 서게 된다(§11 Step 2).

항목별로도 같은 항등식을 확인해 어긋난 항목을 짚어 준다. 순증감(입고−출고)이 큰 항목은
재고가 쌓이거나 빠지는 지점이므로 함께 보여 준다.

inbound/outbound/inventory 역할이 모두 필요하다. 없으면 명시적 실패한다.
"""
from __future__ import annotations

import pandas as pd

import d2insight.config as config
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.schema import (
    ROLE_INBOUND, ROLE_INVENTORY, ROLE_ITEM, ROLE_OUTBOUND, get_schema,
)
from d2insight.engine.types import ModuleResult, Render

_CHART_MAX = 12


def run(ctx, params, tools) -> ModuleResult:
    actual_df = ctx.get("actual_dataset")
    compare_df = ctx.get("compare_dataset")
    if actual_df is None or compare_df is None:
        return ModuleResult(status="failed", error="actual_dataset/compare_dataset이 없습니다.")

    schema = get_schema(ctx)
    inv_col = schema.column(ROLE_INVENTORY)
    in_col = schema.column(ROLE_INBOUND)
    out_col = schema.column(ROLE_OUTBOUND)

    missing = [role for role, col in
               ((ROLE_INVENTORY, inv_col), (ROLE_INBOUND, in_col), (ROLE_OUTBOUND, out_col))
               if not col or col not in actual_df.columns]
    if missing:
        return ModuleResult(
            status="failed",
            error=f"재고 이동 분석에 필요한 역할 {missing}이 없습니다. "
                  "데이터소스 정의에 inventory/inbound/outbound 역할을 선언하세요.",
        )

    tolerance = float(getattr(config, "STOCK_RECONCILE_TOLERANCE", 0.01))
    top_n = int(params.get("top_n") or 20)

    begin = float(compare_df[inv_col].sum()) if inv_col in compare_df.columns else 0.0
    inbound = float(actual_df[in_col].sum())
    outbound = float(actual_df[out_col].sum())
    end = float(actual_df[inv_col].sum())

    expected = begin + inbound - outbound
    gap = end - expected
    gap_ratio = abs(gap) / abs(end) if end else (0.0 if not gap else 1.0)
    reconciled = gap_ratio <= tolerance

    flow = pd.DataFrame([
        {"Step": "기초재고", "Value": begin},
        {"Step": "입고", "Value": inbound},
        {"Step": "출고", "Value": -outbound},
        {"Step": "기말재고", "Value": end},
    ])

    # ── 항목별 정합성 ────────────────────────────────────────────────────────
    item_col = params.get("dimension") or schema.column(ROLE_ITEM)
    detail = pd.DataFrame()
    if item_col and item_col in actual_df.columns:
        a = actual_df.groupby(item_col)[[in_col, out_col, inv_col]].sum()
        c = (compare_df.groupby(item_col)[[inv_col]].sum()
             if inv_col in compare_df.columns else pd.DataFrame(columns=[inv_col]))
        merged = a.join(c, how="left", rsuffix="_begin").fillna(0.0)
        begin_col = f"{inv_col}_begin"
        merged["Begin"] = merged[begin_col] if begin_col in merged.columns else 0.0
        merged["Net_Change"] = merged[in_col] - merged[out_col]
        merged["Expected_End"] = merged["Begin"] + merged["Net_Change"]
        merged["Gap"] = merged[inv_col] - merged["Expected_End"]
        detail = (merged.reset_index().rename(columns={item_col: "Item_Name"})
                  .sort_values("Gap", key=lambda s: s.abs(), ascending=False)
                  .reset_index(drop=True))

    mismatched = detail[detail["Gap"].abs() > 0] if not detail.empty else pd.DataFrame()

    if reconciled:
        summary = (f"재고 이동 정합 — 기초 {begin:,.0f} + 입고 {inbound:,.0f} "
                   f"− 출고 {outbound:,.0f} = 기말 {end:,.0f}. "
                   f"순증감 {inbound - outbound:+,.0f}.")
    else:
        # 데이터 신뢰성 문제다. 분석 결론보다 먼저 알린다.
        summary = (f"재고 이동 **불일치** — 기초+입고−출고 = {expected:,.0f}이나 "
                   f"기말재고는 {end:,.0f} (차이 {gap:+,.0f}, {gap_ratio * 100:.2f}%). "
                   f"재고 데이터에 누락·중복·미기록 이동이 있을 수 있어 "
                   f"이후 재고 분석의 전제가 흔들립니다.")
    if not mismatched.empty:
        summary += f" 항목 단위로도 {len(mismatched)}개 항목이 어긋납니다."

    outputs = {"stock_flow": flow,
              "stock_movement_detail": detail if not detail.empty else pd.DataFrame()}
    key_value = {
        "기초재고": f"{begin:,.0f}", "입고": f"{inbound:,.0f}", "출고": f"{outbound:,.0f}",
        "기말재고": f"{end:,.0f}", "정합성": "일치" if reconciled else f"불일치({gap:+,.0f})",
    }
    if detail.empty:
        return ModuleResult(outputs=outputs, render=Render(summary=summary, key_value=key_value))

    shown = detail.head(top_n)
    table = pd.DataFrame({
        "항목": shown["Item_Name"].astype(str), "기초": shown["Begin"],
        "입고": shown[in_col], "출고": shown[out_col], "기말": shown[inv_col],
        "순증감": shown["Net_Change"], "차이": shown["Gap"],
    })
    render = render_from_dataframe(
        table,
        purpose="재고 이동(기초·입고·출고·기말) 정합성을 점검.",
        narrative_hint=(
            summary + " 정합성이 어긋나면 분석 결론보다 데이터 신뢰성 경고를 먼저 말하고, "
            "정합하면 재고가 쌓이는 항목과 빠지는 항목을 순증감으로 짚어라."
        ),
        params={"정합성": key_value["정합성"]}, label="stock_movement",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = key_value
    return ModuleResult(outputs=outputs, render=render)
