"""cross_drilldown 모듈 — 이상 항목을 다른 차원으로 쪼개 원인을 찾는다 (§15).

§14가 "무엇이 이상한가"를 답했다면, §15는 "그 이상이 **어디서 왔는가**"를 답한다.
방침 15장: 이상징후 중 금액 영향 Top N에 대해, 다른 차원의 어떤 항목이 그 변화를 만들었는지 본다.
교차할 차원은 차원 영향도(DVI) 상위에서 고른다 — 크게 흔들린 차원일수록 설명력이 높다.

**교차 차원 선택은 데이터가 판정한다(도메인 상수 없음, §7.3).**
  이상 항목을 후보 차원으로 나눴을 때 그룹이 1개뿐이면 설명력이 0이다. 예컨대 제품중분류의
  'Touring Bikes'를 제품대분류로 나누면 'Bikes' 한 줄만 나온다("증감의 100%가 Bikes에서 왔다" —
  동어반복). 상위(부모) 차원이 그렇다. 계층 목록을 코드에 박지 않고, **실제로 쪼개지는지**를 보고
  고르면 어떤 데이터셋에서도 동작한다.

방침의 예시("A 고객 +19억 → 수량 +12억 / ASP +4억 / 신제품 +3억")처럼 원인 요인까지 짚는다.
그래서 교차 항목마다 증감의 주요인을 함께 표시한다.
  수량 / ASP / 할인 : 두 기간 모두 존재 → §13과 같은 공식(정가ASP 기준, 할인 분리)
  신규유입 / 이탈    : 한 기간에만 존재 → 그 자체가 원인
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_DISCOUNT, ROLE_PERIOD, ROLE_QUANTITY, get_schema
from d2insight.engine.types import ModuleResult, Render

MIN_CROSS_GROUPS = 2      # 이보다 적게 쪼개지면 설명력이 없다고 본다


def _effects(row: pd.Series, amount: str, quantity: str | None,
             discount: str | None) -> tuple[str, float, float]:
    """교차 항목 하나의 증감 주요인. (요인명, 수량효과, ASP효과)"""
    ra, rc = float(row[f"{amount}_a"]), float(row[f"{amount}_c"])
    if rc <= 0:
        return "신규유입", 0.0, 0.0
    if ra <= 0:
        return "이탈", 0.0, 0.0
    if not quantity:
        return "금액", 0.0, 0.0              # 물량 역할이 없으면 가격/물량을 가를 수 없다

    qa, qc = float(row[f"{quantity}_a"]), float(row[f"{quantity}_c"])
    da = float(row[f"{discount}_a"]) if discount else 0.0
    dc = float(row[f"{discount}_c"]) if discount else 0.0

    gross_a = (ra + da) / qa if qa else 0.0
    gross_c = (rc + dc) / qc if qc else 0.0
    qty_effect = (qa - qc) * gross_c
    asp_effect = (gross_a - gross_c) * qa

    candidates = [("수량", qty_effect), ("ASP", asp_effect)]
    if discount:
        candidates.append(("할인", -(da - dc)))
    factor = max(candidates, key=lambda kv: abs(kv[1]))[0]
    return factor, qty_effect, asp_effect


def run(ctx, params, tools) -> ModuleResult:
    outliers = ctx.get("outlier_result")
    stats = ctx.get("dimension_stats")
    actual_df = ctx.get("actual_dataset")
    compare_df = ctx.get("compare_dataset")
    if actual_df is None or compare_df is None or stats is None:
        return ModuleResult(status="failed", error="선행 데이터(actual/compare/dimension_stats)가 없습니다.")

    if outliers is None or outliers.empty:
        # 쪼갤 대상이 없는 것은 실패가 아니라 "해당 없음"이다.
        return ModuleResult(
            outputs={"drilldown_result": pd.DataFrame()},
            render=Render(summary="이상징후로 지목된 항목이 없어 교차 분석 대상이 없습니다."),
        )

    top_n = int(params.get("top_n") or 5)
    per_item = int(params.get("cross_top_n") or 5)
    requested_subs = params.get("sub_dimensions")

    schema = get_schema(ctx)
    amount = schema.column(ROLE_AMOUNT) or schema.key_measure
    quantity = schema.column(ROLE_QUANTITY)
    discount = schema.column(ROLE_DISCOUNT)
    if quantity and quantity not in actual_df.columns:
        quantity = None
    if discount and discount not in actual_df.columns:
        discount = None

    dvi_order = stats.sort_values("DVI", ascending=False)["Dimension_Logical_Name"].tolist()
    measures = [c for c in (amount, quantity, discount) if c]

    rows: list[dict] = []
    skipped: list[str] = []

    for _, out in outliers.head(top_n).iterrows():
        dim, item = out["Dimension_Logical_Name"], out["Item_Name"]
        item_variance = float(out["Variance"])

        actual_rows = actual_df[actual_df[dim] == item]
        compare_rows = compare_df[compare_df[dim] == item]

        # candidates = ([d for d in (requested_subs or []) if d in actual_df.columns]
        #               or [d for d in dvi_order if d != dim and d in actual_df.columns])

        period_col = schema.column(ROLE_PERIOD)
        exclude = {dim, period_col}
        candidates = ([d for d in (requested_subs or []) if d in actual_df.columns and d not in exclude]
                    or [d for d in dvi_order if d not in exclude and d in actual_df.columns])

        # 실제로 쪼개지는 차원을 고른다 — 그룹이 1개면 정보가 없다(부모 차원·상수 차원).
        panel = None
        cross_dim = None
        rejected: list[str] = []
        for cand in candidates:
            a = actual_rows.groupby(cand)[measures].sum()
            c = compare_rows.groupby(cand)[measures].sum()
            merged = a.join(c, how="outer", lsuffix="_a", rsuffix="_c").fillna(0.0)
            if len(merged) < MIN_CROSS_GROUPS:
                rejected.append(cand)
                continue
            panel, cross_dim = merged, cand
            break

        if panel is None:
            reason = f"쪼개지는 차원 없음(단일 그룹: {', '.join(rejected)})" if rejected else "교차 가능한 차원 없음"
            skipped.append(f"{dim} {item}({reason})")
            continue

        panel["Variance"] = panel[f"{amount}_a"] - panel[f"{amount}_c"]
        panel = panel.reindex(panel["Variance"].abs().sort_values(ascending=False).index)

        for cross_item, r in panel.head(per_item).iterrows():
            factor, qty_effect, asp_effect = _effects(r, amount, quantity, discount)
            rows.append({
                "Outlier": f"{dim} {item}",
                "Outlier_Variance": item_variance,
                "Cross_Dimension": cross_dim,
                "Cross_Item": cross_item,
                "Comparison_Value": float(r[f"{amount}_c"]),
                "Actual_Value": float(r[f"{amount}_a"]),
                "Variance": float(r["Variance"]),
                # 그 이상 항목의 증감을 이 하위 항목이 얼마나 설명하는가
                "Share": float(r["Variance"]) / item_variance if item_variance else 0.0,
                "Factor": factor,
                "Qty_Effect": qty_effect,
                "ASP_Effect": asp_effect,
            })

    if not rows:
        return ModuleResult(
            status="failed",
            error="교차 분석할 하위 데이터를 찾지 못했습니다: " + "; ".join(skipped),
        )

    result = pd.DataFrame(rows)
    note = f" 교차 불가: {', '.join(skipped)}." if skipped else ""

    display = result[["Outlier", "Cross_Dimension", "Cross_Item", "Comparison_Value",
                      "Actual_Value", "Variance", "Share", "Factor"]]
    render = render_from_dataframe(
        display,
        purpose="이상 항목을 다른 차원으로 쪼개 원인을 찾는다.",
        narrative_hint=(
            "이상 항목마다 어느 하위 항목이 그 변화를 얼마나 설명하는지(비중), 주요인(수량/ASP/할인/"
            "신규유입/이탈)이 무엇인지 짚어라." + note
        ),
        params={"이상 항목 수": result["Outlier"].nunique()}, label="cross_drilldown",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {"교차 분석 대상": result["Outlier"].nunique(),
                        "교차 차원": ", ".join(sorted(result["Cross_Dimension"].unique()))}
    return ModuleResult(outputs={"drilldown_result": result}, render=render)
