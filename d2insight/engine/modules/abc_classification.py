"""abc_classification 모듈 — 항목을 규모(ABC)·변동성(XYZ)으로 분류 (src/pipeline/abc_xyz.py 이식).

ABC: 창(window) 기간 누적 점유율 임계(config.ABC_THRESHOLDS)로 A/B/C.
XYZ: 창 기간별 변동계수 CV=std/mean 임계(config.XYZ_THRESHOLDS)로 X/Y/Z.
등급변동: 당기 제외 직전 창(filter window) vs 한 기간 더 이전 창의 등급 차이.

분류 단위(dim_grain, 항목 차원)는 스키마 item 역할이 기본이고, params.dimensions로 명시
지정할 수 있다. 컬럼명("매출"·"월"·"제품")을 코드에 박지 않는다(§7.4). 특정 차원 조합이
필요한 시나리오는 plan/기본세트가 params.dimensions로 명시한다(재고분석 등 다른 도메인은
분류 단위가 다르므로). 역할이 없으면 조용히 0으로 처리하지 않고 명시적으로 실패한다(§11 Step 2).

다기간 비교가 필요하므로 history_dataset(기간별 패널)에 의존한다. 그 패널 위 pandas
재구성이라 새 SQL/쿼리가 없다. 임계값(ABC/XYZ)은 분석 튜닝값이라 config에 둔다(도메인 어휘 아님).

기간 단위(time_grain, 2026-07-24 3단계): month(기본)/quarter/year/week. 창(window) 이동은
dataset_builder.shift_period를 그대로 재사용한다 — 월 전용 계산을 따로 두면 grain마다
따로 구현해야 해서, 이미 검증된 하나의 구현을 공유한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import d2insight.config as config
from d2insight.engine.chart import chart_spec
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_ITEM, ROLE_PERIOD, get_schema
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.dataset_builder import shift_period

_DEFAULT_WINDOW = 3      # 창 길이 기본값(기간수). config.ABC_XYZ_WINDOW_MONTHS로 덮어쓸 수 있다.


def _window_periods(target_period: str, size: int, time_grain: str, *, include_target: bool) -> list[str]:
    """창 기간 식별자 목록. include_target=True면 당기 포함 최근 size개, False면 당기 제외 직전 size개."""
    offsets = range(0, -size, -1) if include_target else range(-1, -size - 1, -1)
    return sorted(shift_period(time_grain, target_period, off) for off in offsets)


def _xyz_grade(cv: float, x_thr: float, y_thr: float) -> str:
    if cv < x_thr:
        return "X"
    if cv < y_thr:
        return "Y"
    return "Z"


def _classify(panel: pd.DataFrame, grain: list[str], period_col: str, amount_col: str,
              months: list[str]) -> pd.DataFrame:
    """창 기간 항목별 ABC-XYZ 등급표. panel은 월별 패널(history_dataset)."""
    window = panel[panel[period_col].isin(months)]
    if window.empty:
        return pd.DataFrame()

    pivot = (
        window.groupby(grain + [period_col])[amount_col].sum()
        .unstack(fill_value=0.0)
        .reindex(columns=months, fill_value=0.0)
    )
    if pivot.empty:
        return pd.DataFrame()

    total_val = pivot.sum(axis=1)
    total_sum = float(total_val.sum())

    # ABC — 매출 내림차순 누적 점유율
    a_thr, b_thr = config.ABC_THRESHOLDS
    sorted_val = total_val.sort_values(ascending=False)
    if total_sum > 0:
        cum_sorted = sorted_val.cumsum() / total_sum
        abc_sorted = cum_sorted.apply(lambda s: "A" if s <= a_thr else ("B" if s <= b_thr else "C"))
    else:
        cum_sorted = sorted_val * 0.0
        abc_sorted = pd.Series("C", index=sorted_val.index)

    # XYZ — 월별 변동계수(모집단 표준편차)
    x_thr, y_thr = config.XYZ_THRESHOLDS
    mean_val = pivot.mean(axis=1)
    std_val = pivot.std(axis=1, ddof=0)
    cv = (std_val / mean_val.replace(0, np.nan)).fillna(np.inf)
    xyz = cv.apply(lambda c: _xyz_grade(c, x_thr, y_thr))

    res = pd.DataFrame({
        "Total_Value": total_val,
        "Share": (total_val / total_sum if total_sum > 0 else total_val * 0.0).round(4),
        "Cumulative_Share": cum_sorted.reindex(total_val.index).round(4),
        "CV": cv.replace(np.inf, np.nan).round(4),
        "ABC": abc_sorted.reindex(total_val.index),
        "XYZ": xyz,
    })
    res["Grade"] = res["ABC"] + res["XYZ"]
    res = res.reset_index()
    # grain 컬럼(들)을 하나의 표시용 항목명으로 합친다(단일 grain이면 그 값 그대로).
    res["Item_Name"] = res[grain].astype(str).agg(" × ".join, axis=1)
    return res.sort_values("Total_Value", ascending=False).reset_index(drop=True)


def _grade_changes(curr: pd.DataFrame, prev: pd.DataFrame) -> pd.DataFrame:
    """등급이 직전 창과 달라진 항목(신규 포함). 규모 큰 순."""
    if curr.empty:
        return pd.DataFrame()
    c = curr.set_index("Item_Name")[["Grade", "ABC", "XYZ", "Total_Value"]]
    if prev.empty:
        merged = c.assign(Prev_Grade="신규")
    else:
        p = prev.set_index("Item_Name")[["Grade"]].rename(columns={"Grade": "Prev_Grade"})
        merged = c.join(p, how="left")
        merged["Prev_Grade"] = merged["Prev_Grade"].fillna("신규")
    changed = merged[merged["Grade"] != merged["Prev_Grade"]]
    return changed.reset_index().sort_values("Total_Value", ascending=False).reset_index(drop=True)


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "항목": df["Item_Name"],
        "규모(창합계)": df["Total_Value"].map(lambda v: f"{v:,.0f}"),
        "점유율": df["Share"].map(lambda v: f"{v * 100:.1f}%"),
        "누적점유율": df["Cumulative_Share"].map(lambda v: f"{v * 100:.1f}%"),
        "CV": df["CV"].map(lambda v: f"{v:.2f}" if pd.notna(v) else "-"),
        "등급": df["Grade"],
    })


def run(ctx, params, tools) -> ModuleResult:
    history = ctx.get("history_dataset")
    if history is None or getattr(history, "empty", True):
        return ModuleResult(
            status="failed",
            error="이력(history_dataset)이 없어 ABC-XYZ 분류(다월 패널)를 할 수 없습니다.",
        )

    target_month = ctx.meta.get("target_month")
    if not target_month:
        return ModuleResult(status="failed", error="ctx.meta에 target_month가 없습니다.")
    # 기간 단위(2026-07-24 3단계) — 분류 단위(item 차원, 아래 변수명 grain)와 이름이 겹치므로
    # time_grain으로 구분한다.
    time_grain = ctx.meta.get("grain") or "month"

    schema = get_schema(ctx)
    period_col = schema.column(ROLE_PERIOD)
    amount_col = schema.column(ROLE_AMOUNT) or schema.key_measure
    if not period_col or period_col not in history.columns:
        return ModuleResult(
            status="failed",
            error="이력에 기간(period) 역할 컬럼이 없어 분류할 수 없습니다. "
                  "데이터소스 정의에 period 역할을 선언하세요.",
        )
    if amount_col not in history.columns:
        return ModuleResult(status="failed", error=f"이력에 금액 컬럼 '{amount_col}'이 없습니다.")

    # 분류 단위 grain — 기본은 item 역할, params.dimensions로 명시 지정 가능(§7.4).
    requested = params.get("dimensions")
    if requested:
        missing = [d for d in requested if d not in history.columns]
        if missing:
            available = [c for c in history.columns if c != period_col]
            return ModuleResult(
                status="failed",
                error=f"요청한 분류 차원 {missing}이 이력에 없습니다. 사용 가능: {available}",
            )
        grain = list(requested)
    else:
        item_col = schema.column(ROLE_ITEM)
        grain = [item_col] if item_col and item_col in history.columns else []
    if not grain:
        return ModuleResult(
            status="failed",
            error="분류할 항목 차원이 없습니다. 데이터소스 정의에 item 역할을 선언하거나 "
                  "params.dimensions로 분류 단위를 지정하세요.",
        )

    window = int(params.get("window_months") or getattr(config, "ABC_XYZ_WINDOW_MONTHS", _DEFAULT_WINDOW))
    top_n = int(params.get("top_n") or 20)

    # 현황: 당기 포함 최근 window개 기간
    classification = _classify(
        history, grain, period_col, amount_col,
        _window_periods(target_month, window, time_grain, include_target=True),
    )
    if classification.empty:
        return ModuleResult(status="failed", error="분류 대상 데이터가 없습니다(창 기간 확인).")

    # 등급 변동: 당기 제외 직전 창 vs 한 기간 더 이전 창
    filter_curr = _classify(
        history, grain, period_col, amount_col,
        _window_periods(target_month, window, time_grain, include_target=False),
    )
    filter_prev = _classify(
        history, grain, period_col, amount_col,
        _window_periods(shift_period(time_grain, target_month, -1), window, time_grain, include_target=False),
    )
    grade_changes = _grade_changes(filter_curr, filter_prev)

    by_grade = classification["Grade"].value_counts().to_dict()
    grade_str = ", ".join(f"{g} {c}개" for g, c in sorted(by_grade.items()))
    change_note = ""
    if not grade_changes.empty:
        top_chg = grade_changes.iloc[0]
        change_note = (f" 등급 변동 {len(grade_changes)}건"
                       f"(최대 규모: {top_chg['Item_Name']} {top_chg['Prev_Grade']}→{top_chg['Grade']}).")
    summary = (
        f"{schema.logical_name(amount_col)} 기준 항목 {len(classification)}개를 "
        f"ABC-XYZ로 분류 — {grade_str}.{change_note}"
    )

    # 차트 — 등급 분포(항목수). 큰데 불안정한 AZ 등이 얼마나 있는지 한눈에.
    counts = classification["Grade"].value_counts().sort_index()
    chart_data = pd.DataFrame({"등급": counts.index, "항목수": counts.values})

    return ModuleResult(
        outputs={
            "abc_xyz_classification": classification,
            "abc_grade_changes": grade_changes,
        },
        render=Render(
            summary=summary,
            table=_display_table(classification.head(top_n)),
            chart=chart_spec(chart_data, "bar", "ABC-XYZ 등급 분포"),
            key_value={
                "분류 항목수": len(classification),
                "등급 종류": len(by_grade),
                "등급 변동": f"{len(grade_changes)}건",
            },
        ),
    )
