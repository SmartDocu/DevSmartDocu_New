"""물량(Volume)/구성 이동(Mix)/단가(Price) — 시나리오 1 '매출 증감 원인 분석'의 세 독립 스텝.

계산은 `_shared.get_pvm_effects(ctx)`가 **최초 1회만** 한다(§6.2 재계산 금지). 세 스텝이
각각 여기서 그 결과의 자기 몫만 꺼내 보여준다 — 스텝(=섹션) 하나가 계산 하나를 전담하지
않고 셋으로 갈라진 이유는 시나리오 설계가 Volume·Price·Mix를 **독립 스텝**으로 정의했기
때문이다(스텝=섹션 원칙, 2026-07-20). 계산을 셋으로 쪼개 각자 다시 하면 반올림·데이터 스냅샷
차이로 세 스텝의 합이 어긋날 수 있어, 계산은 하나로 두고 표시만 나눈다.

규약은 `_shared.get_pvm_effects`의 docstring 참조. 세 값의 합은 **공통 항목 매출 변화**
(covered_variance)와 같다 — 신규·단종 항목(두 기간 모두 존재하지 않는 항목)은 대상이 아니다.

비중(%)은 covered_variance가 아니라 **전체 증감액(total_variance)** 기준으로 통일한다
(2026-07-21 수정). covered_variance를 분모로 쓰면 신규·단종 효과가 큰 달에는 분모 자체가
전체 증감액과 부호까지 달라져(이 데이터셋 2013-05 실측: covered_variance −479,895 vs
total_variance +713,358) 독자가 "물량은 줄었는데 비중은 왜 +인가"처럼 오독하게 된다.
그래서 Volume+Price+Mix의 비중 합이 100%가 아닐 수 있는데, 그 차이(신규·단종 등 효과)를
"미포함 효과"로 별도 명시해 총합이 항상 전체 증감액과 맞아떨어짐을 보여준다.

sales_bridge(§13)와 다르다 — 그건 상품/고객 관점의 신규·이탈까지 포함한 분해이고, 이건
**두 기간 모두 존재하는 항목**만 대상으로 물량 자체를 더 쪼갠 것이다.
"""
from __future__ import annotations

from d2insight.engine.modules._shared import get_bridge_effects, get_pvm_effects
from d2insight.engine.types import ModuleResult, Render


def _share(value: float, total: float) -> float:
    return value / total * 100 if total else 0.0


def _bridge_item_top(item_df, effect_col: str, top_n: int):
    """item_effects를 효과 크기(절댓값) 기준 상위 top_n으로 자른다."""
    dim_col = item_df.columns[0]           # reset_index()로 되살아난 항목 차원 컬럼
    ordered = item_df.reindex(item_df[effect_col].abs().sort_values(ascending=False).index)
    return ordered.head(top_n)[[dim_col, "증감", effect_col]]


def _run_bridge_effect(ctx, params, *, effect_col: str, effect_label: str,
                       direction_up: str, direction_down: str) -> ModuleResult:
    """Volume/Price의 "bridge" 툴 공용 실행 — get_bridge_effects의 기존 항목 효과 하나를 꺼내 보여준다.

    PVM과 달리 항목별 top_n 표를 낸다(§13 방식은 전체 증감액과 검산까지 통과한다).
    """
    try:
        effects = get_bridge_effects(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))
    if not effects["quantity_available"] or effects["item_effects"] is None:
        return ModuleResult(status="failed", error="수량(quantity) 역할이 없어 물량·단가 효과를 분해할 수 없습니다.")

    total_variance = effects["total_variance"]
    item_df = effects["item_effects"]
    amount = float(item_df[effect_col].sum())
    share = _share(amount, total_variance)
    direction = direction_up if amount >= 0 else direction_down
    top_n = int(params.get("top_n") or 10)

    summary = (
        f"{effect_label} 효과 {amount:+,.0f} — 두 기간 모두 판매된 기존 항목 기준으로 "
        f"{direction}된 영향이다. 전체 증감액의 {share:+.1f}%. "
        "(신규·단종 등 그 외 효과는 별도 — 브리지 분해 참고)"
    )
    return ModuleResult(render=Render(
        summary=summary,
        table=_bridge_item_top(item_df, effect_col, top_n),
        key_value={f"{effect_label}(전체 증감액 대비)": f"{share:+.1f}%",
                   effect_label: f"{amount:+,.0f}"},
    ))


def _uncovered_note(effects: dict, total_variance: float) -> str:
    """공통 항목만의 변화(covered_variance)와 전체 증감액(total_variance)의 차이를 밝힌다.

    이 차이는 신규·단종 등 두 기간 모두 존재하지 않는 항목의 효과다(new_lost_detection·
    sales_bridge가 그 세부를 다룬다 — 여기서는 다시 계산하지 않고 차액만 보여준다).
    """
    gap = total_variance - effects["covered_variance"]
    gap_share = _share(gap, total_variance)
    return (
        f" (참고: Volume+Price+Mix는 두 기간 모두 존재한 공통 항목만 대상이다. "
        f"신규·단종 등 그 밖의 항목 효과는 별도로 {gap:+,.0f}(비중 {gap_share:+.1f}%)이며, "
        f"셋을 더한 값과 이 효과를 합치면 전체 증감액과 일치한다.)"
    )


def _total_variance(ctx) -> float | None:
    tv = ctx.get("total_variance")
    if not tv:
        return None
    return float(tv.get("variance") or 0.0)


def run_volume(ctx, params, tools) -> ModuleResult:
    if (tools[0] if tools else "pvm") == "bridge_decompose":
        return _run_bridge_effect(
            ctx, params, effect_col="수량효과", effect_label="물량(Volume)",
            direction_up="확대", direction_down="축소",
        )
    try:
        effects = get_pvm_effects(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))
    total_variance = _total_variance(ctx)
    if total_variance is None:
        return ModuleResult(status="failed", error="전체 증감액(total_variance)이 없어 비중을 계산할 수 없습니다.")

    volume = effects["volume"]
    share = _share(volume, total_variance)
    direction = "확대" if volume >= 0 else "축소"
    summary = (
        f"순수 물량(Volume) 효과 {volume:+,.0f} — 믹스·단가 변화를 제외한 판매량 자체가 "
        f"{direction}된 영향이다. 전체 증감액의 {share:+.1f}%."
        + _uncovered_note(effects, total_variance)
    )
    return ModuleResult(render=Render(
        summary=summary,
        key_value={"물량(Volume)": f"{volume:+,.0f}", "비중(전체 증감액 대비)": f"{share:+.1f}%"},
    ))


def run_price(ctx, params, tools) -> ModuleResult:
    if (tools[0] if tools else "pvm") == "bridge_decompose":
        return _run_bridge_effect(
            ctx, params, effect_col="ASP효과", effect_label="단가(Price)",
            direction_up="상승", direction_down="하락",
        )
    try:
        effects = get_pvm_effects(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))
    total_variance = _total_variance(ctx)
    if total_variance is None:
        return ModuleResult(status="failed", error="전체 증감액(total_variance)이 없어 비중을 계산할 수 없습니다.")

    price = effects["price"]
    share = _share(price, total_variance)
    direction = "상승" if price >= 0 else "하락"
    summary = (
        f"단가(Price) 효과 {price:+,.0f} — 물량 변화를 제외한 항목별 판매 단가가 "
        f"{direction}한 영향이다. 전체 증감액의 {share:+.1f}%."
        + _uncovered_note(effects, total_variance)
    )
    return ModuleResult(render=Render(
        summary=summary,
        key_value={"단가(Price)": f"{price:+,.0f}", "비중(전체 증감액 대비)": f"{share:+.1f}%"},
    ))


def run(ctx, params, tools) -> ModuleResult:
    """Mix 스텝. 물량은 volume_effect, 단가는 price_effect가 맡는다."""
    try:
        effects = get_pvm_effects(ctx)
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))
    total_variance = _total_variance(ctx)
    if total_variance is None:
        return ModuleResult(status="failed", error="전체 증감액(total_variance)이 없어 비중을 계산할 수 없습니다.")

    mix = effects["mix"]
    share = _share(mix, total_variance)
    direction = "유리한" if mix >= 0 else "불리한"
    summary = (
        f"구성 이동(Mix) 효과 {mix:+,.0f} — 물량 총량·단가 변화를 제외하면 판매 구성 자체가 "
        f"매출에 {direction} 방향으로 옮겨갔다. 전체 증감액의 {share:+.1f}%."
        + _uncovered_note(effects, total_variance)
    )
    return ModuleResult(render=Render(
        summary=summary,
        key_value={"믹스(Mix)": f"{mix:+,.0f}", "비중(전체 증감액 대비)": f"{share:+.1f}%"},
    ))
