"""inventory_turnover 모듈 — 재고회전율·재고일수 (시나리오 6 '재고 분석').

    평균재고 = (기초재고 + 기말재고) / 2      기초 = 비교기간 재고, 기말 = 분석기간 재고
    회전율   = 매출원가 / 평균재고
    재고일수 = 기간일수(config) / 회전율      회전이 빠를수록 짧다

왜 매출원가로 나누는가: 재고는 원가로 계상되므로 분자도 원가여야 단위가 맞는다. 매출로 나누면
마진만큼 회전율이 부풀려진다. 그래서 cost 역할을 필수로 본다 — 없으면 명시적 실패(§11 Step 2).

전체 회전율과 함께 항목별 회전율을 내고, 재고일수가 config.INVENTORY_SLOW_DAYS 이상인 항목을
'장기체화'로 표기한다. 회전이 0(=기간 중 나가지 않은 재고)인 항목은 재고일수가 무한이므로
숫자로 뭉개지 않고 별도 표기한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import d2insight.config as config
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import additive_cols, get_dim_frames, get_full_schema, pick_dimension
from d2insight.engine.pipeline.data_request import fetch_series, is_upload, load_meta, reachable_dims
from d2insight.engine.schema import ROLE_COST, ROLE_INVENTORY, ROLE_ITEM, ROLE_OUTBOUND, get_schema
from d2insight.engine.types import ModuleResult, Render

FLAG_SLOW = "장기체화"
FLAG_DEAD = "미회전"       # 기간 중 출고(원가 인식)가 전혀 없음
FLAG_NORMAL = "정상"

_CHART_MAX = 12


def _classify(days: float, slow_days: float) -> str:
    if not np.isfinite(days):
        return FLAG_DEAD
    return FLAG_SLOW if days >= slow_days else FLAG_NORMAL


def _fmt_days(days: float) -> str:
    return f"{days:,.1f}일" if np.isfinite(days) else "-"


def run(ctx, params, tools) -> ModuleResult:
    schema = get_full_schema(ctx)         # 역할은 전체 스키마에서 찾는다(스텝 표에 없는 컬럼도 있다)
    inv_col = schema.column(ROLE_INVENTORY)
    cost_col = schema.column(ROLE_COST)

    if not inv_col:
        return ModuleResult(
            status="failed",
            error="재고(inventory 역할) 컬럼이 없어 재고 분석을 할 수 없습니다. "
                  "데이터소스 정의에 inventory 역할을 선언하세요.",
        )
    # 분자: 매출원가(cost)가 실제 금액 측정값이면 그것을, 단가 같은 값(측정값이 아님)뿐이면 같은 재고 장부의
    # 출고를 쓴다 — 출고와 재고는 같은 단위라 회전율 비율이 같다.
    # 원가는 항목(item)으로 나눌 수 있을 때만 쓴다 — 월·치료군 단위 원가표는 재고 항목별로 나뉘지 않는다.
    item_col = params.get("dimension") or pick_dimension(ctx, ROLE_ITEM, [inv_col])
    flow_col = None
    cost_cands = [c for c in schema.columns(ROLE_COST) if c in schema.measures
                  and item_col and reachable_dims(ctx.meta, [c], [item_col])]
    if cost_cands:
        picked = additive_cols(ctx, cost_cands, params)
        flow_col = picked[0] if len(picked) == 1 else None
    flow_col = flow_col or schema.column(ROLE_OUTBOUND)
    if not flow_col:
        # 매출로 대체하면 마진만큼 회전율이 부풀려진다. 조용히 대체하지 않는다.
        return ModuleResult(
            status="failed",
            error="매출원가(cost 역할)나 출고(outbound 역할) 컬럼이 없어 회전율을 낼 수 없습니다. "
                  "재고는 원가로 계상되므로 분자도 같은 단위여야 합니다.",
        )
    cost_col = flow_col

    if is_upload(ctx.meta):
        # 업로드는 필요한 값을 직접 요청한다 — 재고는 잔액이라 기간 말 값(기초 = 직전 기간 말, 기말 = 분석
        # 기간 말), 출고는 분석 기간 합계.
        try:
            grain = ctx.meta.get("grain") or "month"
            meta = load_meta(ctx.meta)
            queries = params.setdefault("_queries", [])
            inv = fetch_series(ctx.meta, meta, schema, inv_col, item_col, 2, grain, "last", queries)
            flow = fetch_series(ctx.meta, meta, schema, cost_col, item_col, 1, grain, "sum", queries)
        except Exception as e:
            return ModuleResult(status="failed", error=f"재고·출고 조회에 실패했습니다: {e}")
        pcol = inv.columns[0]
        pids = sorted(inv[pcol].unique())
        end_s = inv[inv[pcol] == pids[-1]].set_index(item_col)[inv_col]
        begin_s = (inv[inv[pcol] == pids[0]].set_index(item_col)[inv_col] if len(pids) > 1 else end_s)
        flow_s = flow.set_index(item_col)[cost_col]
        actual_df = pd.DataFrame({inv_col: end_s, cost_col: flow_s}).fillna(0.0).rename_axis(item_col).reset_index()
        compare_df = begin_s.to_frame(inv_col).rename_axis(item_col).reset_index()
    else:
        # DB는 아직 이전 방식(항목 차원 전용 조회)을 쓴다.
        try:
            frames = get_dim_frames(ctx, [inv_col, cost_col], item_col, params)
        except ValueError as e:
            return ModuleResult(status="failed", error=str(e))
        swapped = [c for c in (inv_col, cost_col) if frames["used"][c] != c]
        if swapped:
            # 재고·원가는 다른 측정값으로 바꿔 계산하면 의미가 달라진다 — 조용히 대체하지 않는다.
            return ModuleResult(
                status="failed",
                error=f"'{', '.join(schema.logical_name(c) for c in swapped)}'을(를) 항목 차원으로 작성할 수 없어 "
                      "재고회전율을 낼 수 없습니다(다른 측정값으로 대체하지 않습니다).",
            )
        actual_df, compare_df = frames["actual"], frames["compare"]

    period_days = int(getattr(config, "INVENTORY_PERIOD_DAYS", 30))
    slow_days = float(params.get("slow_days") or getattr(config, "INVENTORY_SLOW_DAYS", 90.0))
    top_n = int(params.get("top_n") or 20)

    # ── 전체 회전율 ──────────────────────────────────────────────────────────
    inv_end = float(actual_df[inv_col].sum())
    inv_begin = float(compare_df[inv_col].sum()) if inv_col in compare_df.columns else 0.0
    avg_inv = (inv_begin + inv_end) / 2
    cogs = float(actual_df[cost_col].sum())

    if not avg_inv > 0:
        return ModuleResult(
            status="failed",
            error="평균재고가 0이라 회전율을 낼 수 없습니다(기초·기말 재고 모두 0).",
        )

    turnover = cogs / avg_inv
    days = period_days / turnover if turnover > 0 else float("inf")

    # ── 항목별 회전율 ────────────────────────────────────────────────────────
    detail = pd.DataFrame()
    if item_col and item_col in actual_df.columns:
        a = actual_df.groupby(item_col)[[inv_col, cost_col]].sum()
        c = (compare_df.groupby(item_col)[[inv_col]].sum()
             if inv_col in compare_df.columns else pd.DataFrame(columns=[inv_col]))
        merged = a.join(c, how="left", rsuffix="_begin").fillna(0.0)
        begin = merged[f"{inv_col}_begin"] if f"{inv_col}_begin" in merged.columns else 0.0
        merged["Avg_Inventory"] = (merged[inv_col] + begin) / 2
        with np.errstate(divide="ignore", invalid="ignore"):
            merged["Turnover"] = np.where(
                merged["Avg_Inventory"] > 0, merged[cost_col] / merged["Avg_Inventory"], np.nan)
            merged["Days"] = np.where(
                merged["Turnover"] > 0, period_days / merged["Turnover"], np.inf)
        merged["Flag"] = [_classify(float(d), slow_days) for d in merged["Days"]]
        detail = (merged[merged["Avg_Inventory"] > 0]
                  .sort_values("Avg_Inventory", ascending=False)
                  .reset_index()
                  .rename(columns={item_col: "Item_Name"}))

    slow_n = int((detail["Flag"] == FLAG_SLOW).sum()) if not detail.empty else 0
    dead_n = int((detail["Flag"] == FLAG_DEAD).sum()) if not detail.empty else 0

    inv_shift = inv_end - inv_begin
    summary = (
        f"재고회전율 {turnover:.2f}회, 재고일수 {_fmt_days(days)} "
        f"(평균재고 {avg_inv:,.0f}, {schema.logical_name(cost_col)} {cogs:,.0f}, {period_days}일 기준). "
        f"재고 {inv_begin:,.0f} → {inv_end:,.0f} ({inv_shift:+,.0f})."
    )
    if not detail.empty:
        summary += (f" 항목 {len(detail)}개 중 {FLAG_SLOW}({slow_days:g}일 이상) {slow_n}개, "
                    f"{FLAG_DEAD} {dead_n}개.")

    outputs = {"inventory_metrics": detail if not detail.empty else pd.DataFrame(),
              "inventory_summary": {"turnover": turnover, "days": days,
                                    "avg_inventory": avg_inv, "cogs": cogs,
                                    "begin": inv_begin, "end": inv_end,
                                    "flow_col": cost_col}}
    key_value = {
        "회전율": f"{turnover:.2f}회", "재고일수": _fmt_days(days),
        "평균재고": f"{avg_inv:,.0f}", FLAG_SLOW: f"{slow_n}개",
    }
    if detail.empty:
        return ModuleResult(outputs=outputs, render=Render(summary=summary, key_value=key_value))

    shown = detail.head(top_n)
    table = pd.DataFrame({
        "항목": shown["Item_Name"].astype(str), "평균재고": shown["Avg_Inventory"],
        schema.logical_name(cost_col): shown[cost_col],
        "회전율": shown["Turnover"], "재고일수": shown["Days"].replace(np.inf, np.nan),
        "구분": shown["Flag"],
    })
    render = render_from_dataframe(
        table,
        purpose="재고회전율·재고일수를 항목별로 제시.",
        narrative_hint=(
            summary + f" 재고일수가 긴 항목({FLAG_SLOW}/{FLAG_DEAD})을 처분·폐기 검토 대상으로 지목하라."
        ),
        params={"기준": schema.logical_name(cost_col)}, label="inventory_turnover",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = key_value
    return ModuleResult(outputs=outputs, render=render)


# ── Dead Stock / Slow Moving 분리 스텝 (2026-07-21, 시나리오 "재고 분석") ─────────
# 원본 스텝은 회전율과 Dead Stock·Slow Moving이 별도다(스텝 분리 원칙). 새로 계산하지 않고
# inventory_turnover가 이미 만든 이름표 "inventory_metrics"(항목별 Flag 포함 표)를 필터링만
# 한다 — requires로 명시하면 이 스텝만 골라 실행해도 inventory_turnover가 자동으로 딸려온다.
def _flagged_table(detail: pd.DataFrame, flag: str, schema, cost_col: str, top_n: int,
                   sort_col: str = "Avg_Inventory") -> pd.DataFrame:
    sub = detail[detail["Flag"] == flag].sort_values(sort_col, ascending=False).head(top_n)
    return pd.DataFrame({
        "항목": sub["Item_Name"].astype(str), "평균재고": sub["Avg_Inventory"],
        schema.logical_name(cost_col): sub[cost_col], "재고일수": sub["Days"].replace(np.inf, np.nan),
    })


def run_dead_stock(ctx, params, tools) -> ModuleResult:
    detail = ctx.get("inventory_metrics")
    if detail is None or detail.empty:
        return ModuleResult(status="failed", error="재고 항목별 데이터(inventory_metrics)가 없습니다.")

    schema = get_schema(ctx)
    cost_col = (ctx.get("inventory_summary") or {}).get("flow_col") or schema.column(ROLE_COST)
    top_n = int(params.get("top_n") or 20)

    dead = detail[detail["Flag"] == FLAG_DEAD]
    count = len(dead)
    tied_up = float(dead["Avg_Inventory"].sum())
    key_value = {"미회전 항목수": f"{count}개", "묶인 평균재고": f"{tied_up:,.0f}"}
    if not count:
        return ModuleResult(render=Render(
            summary="미회전(Dead Stock) 항목이 없습니다.", key_value=key_value))

    render = render_from_dataframe(
        _flagged_table(detail, FLAG_DEAD, schema, cost_col, top_n),
        purpose="기간 중 출고가 전혀 없는 미회전(Dead Stock) 항목을 제시.",
        narrative_hint=(
            f"미회전 {count}개, 묶인 평균재고 {tied_up:,.0f}을 밝히고, 처분·폐기 검토 대상임을 짚어라."
        ),
        params={"미회전 항목수": count}, label="dead_stock",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = key_value
    return ModuleResult(render=render)


def run_slow_moving(ctx, params, tools) -> ModuleResult:
    detail = ctx.get("inventory_metrics")
    if detail is None or detail.empty:
        return ModuleResult(status="failed", error="재고 항목별 데이터(inventory_metrics)가 없습니다.")

    schema = get_schema(ctx)
    cost_col = (ctx.get("inventory_summary") or {}).get("flow_col") or schema.column(ROLE_COST)
    top_n = int(params.get("top_n") or 20)
    slow_days_cfg = float(params.get("slow_days") or getattr(config, "INVENTORY_SLOW_DAYS", 90.0))

    slow = detail[detail["Flag"] == FLAG_SLOW]
    count = len(slow)
    tied_up = float(slow["Avg_Inventory"].sum())
    key_value = {"장기체화 항목수": f"{count}개", "묶인 평균재고": f"{tied_up:,.0f}"}
    if not count:
        return ModuleResult(render=Render(
            summary="장기체화(Slow Moving) 항목이 없습니다.", key_value=key_value))

    render = render_from_dataframe(
        _flagged_table(detail, FLAG_SLOW, schema, cost_col, top_n, sort_col="Days"),
        purpose="재고일수가 긴 장기체화(Slow Moving) 항목을 제시.",
        narrative_hint=(
            f"장기체화(재고일수 {slow_days_cfg:g}일 이상) {count}개, 묶인 평균재고 {tied_up:,.0f}을 "
            "밝히고, 재고일수가 가장 긴 항목을 짚어라."
        ),
        params={"장기체화 항목수": count}, label="slow_moving",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = key_value
    return ModuleResult(render=render)
