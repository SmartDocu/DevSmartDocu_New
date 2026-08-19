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
from d2insight.engine.chart import chart_spec
from d2insight.engine.schema import ROLE_COST, ROLE_INVENTORY, ROLE_ITEM, get_schema
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
    actual_df = ctx.get("actual_dataset")
    compare_df = ctx.get("compare_dataset")
    if actual_df is None or compare_df is None:
        return ModuleResult(status="failed", error="actual_dataset/compare_dataset이 없습니다.")

    schema = get_schema(ctx)
    inv_col = schema.column(ROLE_INVENTORY)
    cost_col = schema.column(ROLE_COST)

    if not inv_col or inv_col not in actual_df.columns:
        return ModuleResult(
            status="failed",
            error="재고(inventory 역할) 컬럼이 없어 재고 분석을 할 수 없습니다. "
                  "데이터소스 정의에 inventory 역할을 선언하세요.",
        )
    if not cost_col or cost_col not in actual_df.columns:
        # 매출로 대체하면 마진만큼 회전율이 부풀려진다. 조용히 대체하지 않는다.
        return ModuleResult(
            status="failed",
            error="매출원가(cost 역할) 컬럼이 없어 회전율을 낼 수 없습니다. "
                  "재고는 원가로 계상되므로 분자도 원가여야 합니다.",
        )

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
    item_col = params.get("dimension") or schema.column(ROLE_ITEM)
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

    table = pd.DataFrame()
    chart = None
    if not detail.empty:
        shown = detail.head(top_n)
        table = pd.DataFrame({
            "항목": shown["Item_Name"].astype(str),
            "평균재고": shown["Avg_Inventory"].map(lambda v: f"{v:,.0f}"),
            schema.logical_name(cost_col): shown[cost_col].map(lambda v: f"{v:,.0f}"),
            "회전율": shown["Turnover"].map(lambda v: f"{v:.2f}회" if pd.notna(v) else "-"),
            "재고일수": shown["Days"].map(_fmt_days),
            "구분": shown["Flag"],
        })
        # 차트: 재고가 큰 항목의 재고일수 — 길수록 묶여 있는 돈이 많다는 뜻.
        finite = shown[np.isfinite(shown["Days"])].head(_CHART_MAX)
        if not finite.empty:
            chart = chart_spec(
                pd.DataFrame({"항목": finite["Item_Name"].astype(str),
                              "재고일수": finite["Days"].astype(float)}),
                "bar", "항목별 재고일수 (재고 상위)")

    return ModuleResult(
        outputs={"inventory_metrics": detail if not detail.empty else pd.DataFrame(),
                 "inventory_summary": {"turnover": turnover, "days": days,
                                       "avg_inventory": avg_inv, "cogs": cogs,
                                       "begin": inv_begin, "end": inv_end}},
        render=Render(
            summary=summary,
            table=table,
            chart=chart,
            key_value={
                "회전율": f"{turnover:.2f}회",
                "재고일수": _fmt_days(days),
                "평균재고": f"{avg_inv:,.0f}",
                FLAG_SLOW: f"{slow_n}개",
            },
        ),
    )


# ── Dead Stock / Slow Moving 분리 스텝 (2026-07-21, 시나리오 "재고 분석") ─────────
# 원본 스텝은 회전율과 Dead Stock·Slow Moving이 별도다(스텝 분리 원칙). 새로 계산하지 않고
# inventory_turnover가 이미 만든 이름표 "inventory_metrics"(항목별 Flag 포함 표)를 필터링만
# 한다 — requires로 명시하면 이 스텝만 골라 실행해도 inventory_turnover가 자동으로 딸려온다.
def _flagged_table(detail: pd.DataFrame, flag: str, schema, cost_col: str, top_n: int) -> pd.DataFrame:
    sub = detail[detail["Flag"] == flag].sort_values("Avg_Inventory", ascending=False).head(top_n)
    return pd.DataFrame({
        "항목": sub["Item_Name"].astype(str),
        "평균재고": sub["Avg_Inventory"].map(lambda v: f"{v:,.0f}"),
        schema.logical_name(cost_col): sub[cost_col].map(lambda v: f"{v:,.0f}"),
        "재고일수": sub["Days"].map(_fmt_days),
    })


def run_dead_stock(ctx, params, tools) -> ModuleResult:
    detail = ctx.get("inventory_metrics")
    if detail is None or detail.empty:
        return ModuleResult(status="failed", error="재고 항목별 데이터(inventory_metrics)가 없습니다.")

    schema = get_schema(ctx)
    cost_col = schema.column(ROLE_COST)
    top_n = int(params.get("top_n") or 20)

    dead = detail[detail["Flag"] == FLAG_DEAD]
    count = len(dead)
    tied_up = float(dead["Avg_Inventory"].sum())
    summary = (
        f"미회전(Dead Stock) {count}개 — 묶인 평균재고 {tied_up:,.0f}. "
        "기간 중 출고(원가 인식)가 전혀 없어 처분·폐기 검토 대상."
    )

    table = _flagged_table(detail, FLAG_DEAD, schema, cost_col, top_n) if count else None
    chart = None
    if count:
        top = dead.sort_values("Avg_Inventory", ascending=False).head(_CHART_MAX)
        chart = chart_spec(
            pd.DataFrame({"항목": top["Item_Name"].astype(str),
                          "평균재고": top["Avg_Inventory"].astype(float)}),
            "bar", "미회전(Dead Stock) 항목 Top (평균재고)")

    return ModuleResult(render=Render(
        summary=summary, table=table, chart=chart,
        key_value={"미회전 항목수": f"{count}개", "묶인 평균재고": f"{tied_up:,.0f}"},
    ))


def run_slow_moving(ctx, params, tools) -> ModuleResult:
    detail = ctx.get("inventory_metrics")
    if detail is None or detail.empty:
        return ModuleResult(status="failed", error="재고 항목별 데이터(inventory_metrics)가 없습니다.")

    schema = get_schema(ctx)
    cost_col = schema.column(ROLE_COST)
    top_n = int(params.get("top_n") or 20)
    slow_days_cfg = float(params.get("slow_days") or getattr(config, "INVENTORY_SLOW_DAYS", 90.0))

    slow = detail[detail["Flag"] == FLAG_SLOW]
    count = len(slow)
    tied_up = float(slow["Avg_Inventory"].sum())
    summary = (
        f"장기체화(Slow Moving, 재고일수 {slow_days_cfg:g}일 이상) {count}개 — "
        f"묶인 평균재고 {tied_up:,.0f}."
    )

    table = _flagged_table(detail, FLAG_SLOW, schema, cost_col, top_n) if count else None
    chart = None
    if count:
        top = slow.sort_values("Days", ascending=False).head(_CHART_MAX)
        chart = chart_spec(
            pd.DataFrame({"항목": top["Item_Name"].astype(str),
                          "재고일수": top["Days"].astype(float)}),
            "bar", "장기체화(Slow Moving) 항목 Top (재고일수)")

    return ModuleResult(render=Render(
        summary=summary, table=table, chart=chart,
        key_value={"장기체화 항목수": f"{count}개", "묶인 평균재고": f"{tied_up:,.0f}"},
    ))
