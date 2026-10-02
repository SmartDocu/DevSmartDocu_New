"""safety_stock 모듈 — 항목별 안전재고 대비 현재 재고 위험 진단 (시나리오 '재고 분석').

두 갈래(우선순위 순):
  1. **정책값 우선** — 데이터에 안전재고 목표치(safety_stock 역할)가 이미 정의돼 있으면 그대로
     쓴다. 회사가 정한 정책값이므로 계산값보다 항상 우선한다(메타 정확성은 데이터 관리자 책임).
  2. **추정(정책값이 없을 때만)** — 표준 공식으로 추정한다:
         Safety Stock ≈ Z × σ(월별 원가)      (리드타임 = 1개 리뷰기간(월) 가정)
     리드타임 데이터가 스키마에 없어 쓰는 단순화이므로, **추정값임을 보고서에 명시**한다
     (회사 정책이 아니라 계산값이라는 것을 숨기지 않는다).

재고(inventory)를 원가 기준으로 본다 — inventory_turnover가 이미 그렇게 다루고 있어(재고는
원가로 계상) 같은 단위 관례를 따른다. 안전재고 역할도 없고 기간별 이력도 가져올 수 없으면
계산 자체가 불가능하므로 명시적으로 실패한다(§11 Step 2, 조용히 0 처리하지 않는다).
"""
from __future__ import annotations

import pandas as pd

import d2insight.config as config
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_dim_frames, get_full_schema, get_series, pick_dimension
from d2insight.engine.pipeline.data_request import fetch_attribute, fetch_series, is_upload, load_meta
from d2insight.engine.schema import ROLE_COST, ROLE_INVENTORY, ROLE_ITEM, ROLE_PERIOD, ROLE_SAFETY_STOCK, get_schema
from d2insight.engine.types import ModuleResult, Render

_CHART_MAX = 12


def _estimate_target(ctx, params, item_col: str, cost_col: str) -> tuple[pd.Series | None, str]:
    """정책값이 없을 때 항목별 안전재고를 Z×σ(월별 원가)로 추정한다. 실패하면 (None, 사유)."""
    try:
        history = get_series(ctx, cost_col, item_col, params)
    except ValueError as e:
        return None, f"원가의 기간별 값을 가져오지 못해 안전재고를 추정할 수 없습니다: {e}"
    period_col = history.columns[0]

    monthly = history.groupby([item_col, period_col])[cost_col].sum().reset_index()
    stats = monthly.groupby(item_col)[cost_col].agg(months="count", std="std")
    min_months = int(getattr(config, "SAFETY_STOCK_MIN_MONTHS", 3))
    usable = stats[stats["months"] >= min_months]
    if usable.empty:
        return None, (f"항목별 이력이 {min_months}개월 미만이라 표준편차를 신뢰할 수 없어 "
                       "안전재고를 추정할 수 없습니다.")

    z = float(getattr(config, "SAFETY_STOCK_Z", 1.65))
    target = (usable["std"].fillna(0.0) * z).rename("Safety_Stock_Target")
    return target, ""


def run(ctx, params, tools) -> ModuleResult:
    schema = get_full_schema(ctx)         # 역할은 전체 스키마에서 찾는다(스텝 표에 없는 컬럼도 있다)
    inv_col = schema.column(ROLE_INVENTORY)
    cost_col = schema.column(ROLE_COST)
    item_col = params.get("dimension") or pick_dimension(ctx, ROLE_ITEM, [inv_col] if inv_col else [])
    safety_col = schema.column(ROLE_SAFETY_STOCK)

    if not inv_col:
        return ModuleResult(
            status="failed",
            error="재고(inventory 역할) 컬럼이 없어 안전재고 대비 진단을 할 수 없습니다.",
        )
    if not item_col:
        return ModuleResult(status="failed", error="항목(item) 역할이 없어 항목별로 진단할 수 없습니다.")

    # 업로드는 필요한 값을 직접 요청한다 — 현재 재고는 재고 파일의 당기 말 값(잔액이라 합계가 아니다),
    # 정책값은 그 컬럼이 든 파일에서 항목별 max(같은 값이 여러 줄에 반복돼도 부풀지 않는다).
    # DB는 아직 이전 방식(항목 차원 전용 조회 + 스텝 공용 표)을 쓴다.
    target = None
    if is_upload(ctx.meta):
        try:
            series = fetch_series(
                ctx.meta, load_meta(ctx.meta), schema, inv_col, item_col, 1,
                ctx.meta.get("grain") or "month", "last", params.setdefault("_queries", []),
            )
            current = series.set_index(item_col)[inv_col].rename("Current_Inventory")
            if safety_col:
                target = fetch_attribute(ctx.meta, safety_col, item_col).rename("Safety_Stock_Target")
        except Exception as e:
            return ModuleResult(status="failed", error=f"재고·안전재고 조회에 실패했습니다: {e}")
        has_policy = target is not None
    else:
        try:
            frames = get_dim_frames(ctx, [inv_col], item_col, params)
        except ValueError as e:
            return ModuleResult(status="failed", error=str(e))
        if frames["used"][inv_col] != inv_col:
            return ModuleResult(
                status="failed",
                error=f"'{schema.logical_name(inv_col)}'을(를) 항목 차원으로 작성할 수 없어 안전재고를 진단할 수 없습니다"
                      "(다른 측정값으로 대체하지 않습니다).",
            )
        current = frames["actual"].groupby(item_col)[inv_col].sum().rename("Current_Inventory")
        step_actual = ctx.get("actual_dataset")
        has_policy = bool(safety_col and step_actual is not None and safety_col in step_actual.columns
                          and item_col in step_actual.columns)
        if has_policy:
            target = step_actual.groupby(item_col)[safety_col].max().rename("Safety_Stock_Target")

    source_label = ""
    if has_policy:
        source_label = "정책값(데이터 정의)"
        estimate_note = ""
    else:
        if not cost_col:
            return ModuleResult(
                status="failed",
                error=("안전재고(safety_stock 역할) 정책값이 데이터에 없고, 추정에 필요한 "
                       "매출원가(cost 역할)도 없어 안전재고 진단을 할 수 없습니다."),
            )
        target, err = _estimate_target(ctx, params, item_col, cost_col)
        if target is None:
            return ModuleResult(
                status="failed",
                error=f"안전재고(safety_stock 역할) 정책값이 데이터에 없습니다. {err}",
            )
        source_label = f"추정값(공식: Z×σ(월별 {schema.logical_name(cost_col)}), 리드타임 1개월 가정)"
        estimate_note = (
            f" 안전재고는 회사 정책값이 아니라 위 공식으로 계산한 추정값입니다"
            f"(Z={getattr(config, 'SAFETY_STOCK_Z', 1.65):.2f})."
        )

    # 재고 기록이 없는 항목(재고 0과 다르다)과 정책값이 없는 항목은 판정에서 뺀다 — 빈칸을 0으로 채우면
    # 기록이 없는 항목이 "재고 0 = 부족"으로 잘못 잡힌다.
    both = pd.concat([current, target], axis=1)
    no_stock = int(both["Current_Inventory"].isna().sum())
    no_policy = int(both["Safety_Stock_Target"].isna().sum())
    merged = both.dropna().copy()
    excluded_note = ""
    if no_stock or no_policy:
        parts = ([f"재고 기록 없음 {no_stock}개"] if no_stock else []) + \
                ([f"안전재고 기준 없음 {no_policy}개"] if no_policy else [])
        excluded_note = f" 판정에서 제외: {', '.join(parts)}."
    estimate_note += excluded_note
    merged["Gap"] = merged["Current_Inventory"] - merged["Safety_Stock_Target"]
    merged = merged.reset_index().rename(columns={item_col: "Item_Name"})

    at_risk = merged[merged["Gap"] < 0].sort_values("Gap")
    risk_n = len(at_risk)
    total_n = len(merged)

    key_value = {"부족 위험 항목수": f"{risk_n}/{total_n}개", "기준": source_label}
    if not risk_n:
        return ModuleResult(render=Render(
            summary=f"안전재고 부족 위험 항목 없음 — 기준: {source_label}." + estimate_note,
            key_value=key_value,
        ))

    top_n = int(params.get("top_n") or 20)
    shown = at_risk.head(top_n)
    table = pd.DataFrame({
        "항목": shown["Item_Name"].astype(str), "현재 재고": shown["Current_Inventory"],
        "안전재고 기준": shown["Safety_Stock_Target"], "차이": shown["Gap"],
    })
    render = render_from_dataframe(
        table,
        purpose="안전재고 대비 현재 재고 부족 위험을 항목별로 진단.",
        narrative_hint=(
            f"부족 위험 {risk_n}/{total_n}개 항목, 기준: {source_label}.{estimate_note} "
            "가장 심각한 항목과 부족 정도를 짚고, 보충 발주가 필요함을 말하라."
        ),
        params={"기준": source_label}, label="safety_stock",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = key_value
    return ModuleResult(render=render)
