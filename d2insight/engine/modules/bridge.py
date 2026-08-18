"""sales_bridge 모듈 — 매출 증감 원인 분해 (§13, 개정 2026-07-14).

브리지의 존재 이유는 **합이 전체 증감액과 맞는 것**이다. 맞지 않으면 "무엇이 얼마나 기여했는가"를
말할 수 없다. 그래서 두 가지를 바로잡았다.

1) 할인 효과 이중 계상 제거
   매출(LineTotal)은 **할인 후 순매출**이다. 순ASP(=순매출/수량)로 가격 효과를 구하면 할인이 이미
   그 안에 녹아 있는데, 거기에 할인 효과를 또 더하면 같은 금액을 두 번 센다.
   → 가격 효과는 **정가ASP**((매출+할인액)/수량)로 구하고, 할인은 별도 항으로 뺀다. 그러면 정확히
     가법이 성립한다:
       ΔRev = (Qa−Qc)·gASPc  +  (gASPa−gASPc)·Qa  −  (Da−Dc)
              [수량 효과]        [정가(ASP) 효과]      [할인 효과]

2) 상품·고객을 한 합계에 섞지 않음
   신규 고객이 기존 상품을 사면 그 매출은 '신규고객 효과'이면서 동시에 '수량 효과'다. 7개 항목을
   한 줄로 더하면 이중 계상이라 합이 맞지 않는다.
   → **관점을 둘로 나눈다. 각 관점이 독립적으로 전체 증감액과 일치한다.**
       상품 관점: 신규상품 + 복귀상품 + 단종상품 + 일시미판매 + 기존상품(수량 + 정가ASP + 할인)
       고객 관점: 진성신규 + 복귀 + 진성이탈 + 일시미구매 + 유지고객 증감
   같은 숫자를 두 렌즈로 보는 것이며, 두 합계 모두 total_variance와 같아야 한다(검산 포함).

신규/이탈 구분은 §4.1 생애주기 기준이다(2기간 비교만 쓰면 구매 주기를 이탈로 오인한다).
이력이 없으면 산술 신규/이탈로 폴백하되 **그 사실을 보고서에 명시**한다.
분모(전체 증감액)는 measure_summary의 공용 total_variance를 그대로 쓴다(재계산 금지 §6.2).
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.modules._shared import get_bridge_effects
from d2insight.engine.chart import chart_spec
from d2insight.engine.schema import ROLE_ITEM, get_schema
from d2insight.engine.types import ModuleResult, Render


def _display_table(views: dict[str, list[dict]], total: float) -> pd.DataFrame:
    rows = []
    for view, effects in views.items():
        for e in effects:
            rows.append({
                "관점": view,
                "효과": e["효과"],
                "금액": f"{e['금액']:+,.0f}",
                "전체 증감 대비": f"{e['금액'] / total * 100:+.1f}%" if total else "-",
                "항목수": f"{e['항목수']:,}",
            })
        s = sum(e["금액"] for e in effects)
        rows.append({
            "관점": view, "효과": "합계 (검산)", "금액": f"{s:+,.0f}",
            "전체 증감 대비": f"{s / total * 100:+.1f}%" if total else "-", "항목수": "",
        })
    return pd.DataFrame(rows)


def run(ctx, params, tools) -> ModuleResult:
    try:
        effects = get_bridge_effects(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))

    total = effects["total_variance"]
    views = effects["views"]
    lifecycle_available = effects["lifecycle_based"]

    top_n = int(params.get("top_n") or 10)
    bridge_effects = {
        "total_variance": total,
        "views": {v: {e["효과"]: e["금액"] for e in eff} for v, eff in views.items()},
        "lifecycle_based": lifecycle_available,
    }

    # 기존 개체(item)의 효과별 Top N (§13 "수량 증가 효과 Top 10 제품 리스트")
    if effects["item_effects"] is not None:
        bridge_effects["item_top"] = effects["item_effects"].head(top_n)

    # 관점을 가로질러 최댓값을 뽑으면 안 된다(고객 관점의 유입·상쇄 금액은 전체 증감액보다 훨씬 크다).
    # 관점별로 최대 증가·최대 감소 효과를 따로 말한다.
    parts = []
    for view, effects in views.items():
        ups = [e for e in effects if e["금액"] > 0]
        downs = [e for e in effects if e["금액"] < 0]
        chunk = []
        if ups:
            top_up = max(ups, key=lambda e: e["금액"])
            chunk.append(f"{top_up['효과']} {top_up['금액']:+,.0f}")
        if downs:
            top_down = min(downs, key=lambda e: e["금액"])
            chunk.append(f"{top_down['효과']} {top_down['금액']:+,.0f}")
        parts.append(f"{view} — " + ", ".join(chunk))

    note = "" if lifecycle_available else " (이력 없음 — 신규/이탈을 2기간 산술 기준으로 구분함)"
    summary = (
        f"전체 증감 {total:+,.0f}을 두 관점으로 분해(각 관점 합계 = 전체 증감액). "
        + " / ".join(parts) + f".{note}"
    )

    # 차트: 상품(개체) 관점의 효과별 증감을 부호 있는 막대로. 상품 관점은 수량/정가ASP/할인까지
    #   분해돼 §13의 가격·물량 스토리를 담는다. 워터폴(누적 흐름)은 표의 검산 합계가 보완한다.
    #   제목엔 도메인 어휘를 박지 않고 관점명만 쓴다(§7.4 역할 중립화).
    schema = get_schema(ctx)
    item_dim = schema.column(ROLE_ITEM)
    item_view = f"{schema.logical_name(item_dim)} 관점" if item_dim else None
    chart = None
    if item_view and item_view in views:
        eff = views[item_view]
        chart_data = pd.DataFrame({
            "효과": [e["효과"] for e in eff],
            "증감": [e["금액"] for e in eff],
        })
        chart = chart_spec(chart_data, "bar", f"{item_view} 증감 효과 분해")

    return ModuleResult(
        outputs={"bridge_effects": bridge_effects},
        render=Render(
            summary=summary,
            table=_display_table(views, total),
            chart=chart,
            key_value={"전체 증감액": f"{total:+,.0f}",
                       "신규/이탈 기준": "생애주기" if lifecycle_available else "2기간 산술"},
        ),
    )
