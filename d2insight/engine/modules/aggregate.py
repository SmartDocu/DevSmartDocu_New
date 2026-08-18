"""집계·실적형 모듈 5종 (지시서 §2·§10 — 분석형과 동등한 1급 모듈).

  actual_aggregate    차원×항목 실적과 증감          (실적집계 — 재사용 핵심)
  composition         차원 항목별 구성비와 비중 변화  (구성비)
  ranking             상/하위 순위                   (순위)
  trend               기간별 추이                    (추이 — 이력 필요)
  cumulative_progress 기간 누계와 진척률             (누계/진척 — 이력 필요)

전부 **리프**다(produces=[]). 이름표를 만들지 않으므로 `dimension`만 바꿔 한 보고서에서 여러 번
실행해도 충돌하지 않는다(§3.4-2 회피). 각자의 summary는 add_summary로 수집되어 결론에 반영된다.

컬럼명을 코드에 박지 않는다 — measure는 스키마의 핵심 measure를 기본으로 쓰고, 표시명은
Logical_Name에서 가져온다(구매분석이면 "구매액"으로 찍힌다).
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.chart import chart_spec
from d2insight.engine.modules._shared import slice_history_window
from d2insight.engine.schema import ROLE_PERIOD, get_schema
from d2insight.engine.types import ModuleResult, Render

# 차트 가독성 상한 — 막대는 너무 많으면 라벨이 겹치고, 파이는 조각이 잘게 쪼개진다.
_BAR_MAX = 12
_PIE_MAX = 8


def _resolve(ctx, params) -> tuple:
    """(schema, measure, 표시명) — measure 미지정 시 핵심 measure."""
    schema = get_schema(ctx)
    measure = params.get("measure") or schema.key_measure
    return schema, measure, schema.logical_name(measure)


def _need_dimension(params, actual_df) -> tuple[str | None, ModuleResult | None]:
    dimension = params.get("dimension")
    if not dimension:
        return None, ModuleResult(status="failed", error="params.dimension이 필요합니다(차원 미지정).")
    if dimension not in actual_df.columns:
        return None, ModuleResult(
            status="failed",
            error=f"차원 '{dimension}'이 데이터에 없습니다.",
        )
    return dimension, None


def _compare_panel(actual_df, compare_df, dimension: str, measure: str) -> pd.DataFrame:
    """차원 항목별 비교기간·분석기간 집계 + 증감."""
    a = actual_df.groupby(dimension)[measure].sum().rename("Actual_Value")
    c = compare_df.groupby(dimension)[measure].sum().rename("Comparison_Value")
    panel = pd.concat([a, c], axis=1).fillna(0.0).reset_index()
    panel = panel.rename(columns={dimension: "Item_Name"})
    panel["Variance"] = panel["Actual_Value"] - panel["Comparison_Value"]
    panel["Rate"] = panel.apply(
        lambda r: r["Variance"] / r["Comparison_Value"] if r["Comparison_Value"] else 0.0, axis=1)
    return panel


# ── 실적집계 ─────────────────────────────────────────────────────────────────
def run_actual_aggregate(ctx, params, tools) -> ModuleResult:
    actual_df, compare_df = ctx.get("actual_dataset"), ctx.get("compare_dataset")
    schema, measure, measure_name = _resolve(ctx, params)
    dimension, err = _need_dimension(params, actual_df)
    if err:
        return err

    top_n = int(params.get("top_n") or 20)
    panel = _compare_panel(actual_df, compare_df, dimension, measure)
    panel = panel.sort_values("Actual_Value", ascending=False).reset_index(drop=True)
    shown = panel.head(top_n)

    table = pd.DataFrame({
        schema.logical_name(dimension): shown["Item_Name"],
        "비교기간": shown["Comparison_Value"].map(lambda v: f"{v:,.0f}"),
        "분석기간": shown["Actual_Value"].map(lambda v: f"{v:,.0f}"),
        "증감": shown["Variance"].map(lambda v: f"{v:+,.0f}"),
        "증감률": shown["Rate"].map(lambda v: f"{v * 100:+.1f}%"),
    })

    total_a = float(panel["Actual_Value"].sum())
    total_v = float(panel["Variance"].sum())
    top = panel.iloc[0] if len(panel) else None
    summary = (
        f"{schema.logical_name(dimension)}별 {measure_name} {total_a:,.0f} "
        f"({total_v:+,.0f}). 항목 {len(panel):,}개 중 상위 {len(shown)}개 표시"
        + (f", 1위 {top['Item_Name']} {top['Actual_Value']:,.0f}"
           f"({top['Rate'] * 100:+.1f}%)." if top is not None else ".")
    )
    # 상위 항목이 전부 비교기간 실적 0(=전부 신규 취급)이면 "증가율" 자체가 무의미하다 —
    # 회전율이 높은 차원(개별 고객 등)에서 원시 2개월 비교의 흔한 함정이다. 조용히 넘기지 않는다.
    if not shown.empty and (shown["Comparison_Value"] == 0).all():
        summary += (
            f" ※ 상위 {len(shown)}개 전부 비교기간 실적이 0으로 잡혀(신규 취급) 증감률이 의미가 없다 — "
            f"이 차원은 재구매 주기가 길어 원시 2개월 비교로는 대부분 신규·이탈로 분류될 수 있다. "
            "신규/이탈을 실제로 가르려면 생애주기 기반 분석이 필요하다."
        )
    dim_name = schema.logical_name(dimension)
    chart_data = pd.DataFrame({
        dim_name: shown["Item_Name"].head(_BAR_MAX),
        measure_name: shown["Actual_Value"].head(_BAR_MAX),
    })
    return ModuleResult(render=Render(
        summary=summary, table=table,
        chart=chart_spec(chart_data, "bar", f"{dim_name}별 {measure_name}"),
        key_value={"차원": dim_name, "합계": f"{total_a:,.0f}",
                   "증감": f"{total_v:+,.0f}"},
    ))


# ── 구성비 ───────────────────────────────────────────────────────────────────
def run_composition(ctx, params, tools) -> ModuleResult:
    actual_df, compare_df = ctx.get("actual_dataset"), ctx.get("compare_dataset")
    schema, measure, measure_name = _resolve(ctx, params)
    dimension, err = _need_dimension(params, actual_df)
    if err:
        return err

    panel = _compare_panel(actual_df, compare_df, dimension, measure)
    total_a = float(panel["Actual_Value"].sum())
    total_c = float(panel["Comparison_Value"].sum())
    if total_a <= 0:
        return ModuleResult(status="failed", error=f"{measure_name} 합계가 0이라 구성비를 낼 수 없습니다.")

    panel["Share"] = panel["Actual_Value"] / total_a
    panel["Compare_Share"] = panel["Comparison_Value"] / total_c if total_c else 0.0
    panel["Share_Change"] = panel["Share"] - panel["Compare_Share"]
    panel = panel.sort_values("Share", ascending=False).reset_index(drop=True)

    top_n = int(params.get("top_n") or 10)
    shown = panel.head(top_n)
    table = pd.DataFrame({
        schema.logical_name(dimension): shown["Item_Name"],
        "분석기간": shown["Actual_Value"].map(lambda v: f"{v:,.0f}"),
        "구성비": shown["Share"].map(lambda v: f"{v * 100:.1f}%"),
        "이전 구성비": shown["Compare_Share"].map(lambda v: f"{v * 100:.1f}%"),
        "비중 변화": shown["Share_Change"].map(lambda v: f"{v * 100:+.1f}%p"),
    })

    top = panel.iloc[0]
    gain = panel.loc[panel["Share_Change"].idxmax()]
    summary = (
        f"{schema.logical_name(dimension)} 구성비 — 1위 {top['Item_Name']} "
        f"{top['Share'] * 100:.1f}%({top['Share_Change'] * 100:+.1f}%p), "
        f"비중이 가장 늘어난 항목은 {gain['Item_Name']}({gain['Share_Change'] * 100:+.1f}%p). "
        f"상위 {len(shown)}개가 전체의 {shown['Share'].sum() * 100:.1f}%."
    )
    dim_name = schema.logical_name(dimension)
    chart_data = pd.DataFrame({
        dim_name: shown["Item_Name"].head(_PIE_MAX),
        measure_name: shown["Actual_Value"].head(_PIE_MAX),
    })
    return ModuleResult(render=Render(
        summary=summary, table=table,
        chart=chart_spec(chart_data, "pie", f"{dim_name} {measure_name} 구성비"),
        key_value={"1위": str(top["Item_Name"]), "1위 비중": f"{top['Share'] * 100:.1f}%"},
    ))


# ── 순위 ─────────────────────────────────────────────────────────────────────
def run_ranking(ctx, params, tools) -> ModuleResult:
    actual_df, compare_df = ctx.get("actual_dataset"), ctx.get("compare_dataset")
    schema, measure, measure_name = _resolve(ctx, params)
    dimension, err = _need_dimension(params, actual_df)
    if err:
        return err

    order = (params.get("order") or "desc").lower()
    by = params.get("by") or "actual"            # actual | variance
    top_n = int(params.get("top_n") or 10)
    sort_col = "Actual_Value" if by == "actual" else "Variance"

    panel = _compare_panel(actual_df, compare_df, dimension, measure)
    panel = panel.sort_values(sort_col, ascending=(order == "asc")).reset_index(drop=True)
    shown = panel.head(top_n)

    table = pd.DataFrame({
        "순위": range(1, len(shown) + 1),
        schema.logical_name(dimension): shown["Item_Name"],
        "분석기간": shown["Actual_Value"].map(lambda v: f"{v:,.0f}"),
        "증감": shown["Variance"].map(lambda v: f"{v:+,.0f}"),
        "증감률": shown["Rate"].map(lambda v: f"{v * 100:+.1f}%"),
    })

    if not len(shown):
        return ModuleResult(status="failed", error="순위를 낼 항목이 없습니다.")

    label = "상위" if order == "desc" else "하위"
    basis = measure_name if by == "actual" else f"{measure_name} 증감"
    names = ", ".join(str(n) for n in shown["Item_Name"].head(3))
    head = shown.iloc[0]
    # 하위 순위에서 "1위"라고 하면 오독된다 — 무엇이 첫 줄인지 그대로 말한다.
    lead = "최상위" if order == "desc" else "최하위"
    dim_name = schema.logical_name(dimension)
    summary = (f"{dim_name} {basis} {label} {len(shown)}개: {names} 등. "
               f"{lead} {head['Item_Name']} {head[sort_col]:+,.0f}.")
    chart_data = pd.DataFrame({
        dim_name: shown["Item_Name"].head(_BAR_MAX),
        basis: shown[sort_col].head(_BAR_MAX),
    })
    return ModuleResult(render=Render(
        summary=summary, table=table,
        chart=chart_spec(chart_data, "bar", f"{dim_name} {basis} {label}"),
    ))


# ── 추이 (이력 필요) ─────────────────────────────────────────────────────────
def _history(ctx, params: dict | None = None) -> tuple[pd.DataFrame | None, str | None, str]:
    """이력 패널 + 기간 컬럼. params.window_months가 있으면 최근 N개월만 잘라 준다.

    창 기본값은 None = 이력 전체(기존 동작). 창 지정은 수동 모드에서 들어온다.
    """
    history = ctx.get("history_dataset")
    if history is None or history.empty:
        return None, None, ""
    period_col = get_schema(ctx).column(ROLE_PERIOD)
    if not period_col or period_col not in history.columns:
        return None, None, ""

    window = (params or {}).get("window_months")
    history, note = slice_history_window(history, period_col, window)
    return history, period_col, note


def run_trend(ctx, params, tools) -> ModuleResult:
    history, period_col, window_note = _history(ctx, params)
    if history is None:
        return ModuleResult(status="failed",
                            error="이력(history_dataset)이 없어 추이를 낼 수 없습니다.")
    schema, measure, measure_name = _resolve(ctx, params)
    if measure not in history.columns:
        return ModuleResult(status="failed", error=f"이력에 '{measure}' 컬럼이 없습니다.")

    dimension = params.get("dimension")
    if dimension and dimension not in history.columns:
        return ModuleResult(status="failed", error=f"이력에 차원 '{dimension}'이 없습니다.")

    if dimension:
        top_n = int(params.get("top_n") or 5)
        totals = history.groupby(dimension)[measure].sum().sort_values(ascending=False)
        keep = totals.head(top_n).index
        sub = history[history[dimension].isin(keep)]
        series = sub.pivot_table(index=period_col, columns=dimension,
                                 values=measure, aggfunc="sum").fillna(0.0).sort_index()
        # 차트는 서식 적용 전 숫자 값으로 만든다(라인 여러 개 = 상위 항목별 추이).
        chart_data = series.reset_index().rename(columns={period_col: "기간"})
        table = series.reset_index().rename(columns={period_col: "기간"})
        for col in series.columns:
            table[col] = table[col].map(lambda v: f"{v:,.0f}")
    else:
        series = history.groupby(period_col)[measure].sum().sort_index()
        diff = series.diff()
        chart_data = pd.DataFrame({"기간": series.index, measure_name: series.values})
        table = pd.DataFrame({
            "기간": series.index,
            measure_name: series.map(lambda v: f"{v:,.0f}").values,
            # 첫 기간은 비교 대상이 없다. +0으로 적으면 "변화 없음"으로 오독된다.
            "전기 대비": [f"{v:+,.0f}" if pd.notna(v) else "-" for v in diff],
        })

    totals_by_period = history.groupby(period_col)[measure].sum().sort_index()
    first, last = float(totals_by_period.iloc[0]), float(totals_by_period.iloc[-1])
    peak = totals_by_period.idxmax()
    direction = "상승" if last > first else ("하락" if last < first else "보합")
    summary = (
        f"{measure_name} {len(totals_by_period)}개 기간 추이 — {direction}"
        f"({totals_by_period.index[0]} {first:,.0f} → {totals_by_period.index[-1]} {last:,.0f}, "
        f"{(last - first) / first * 100:+.1f}%)." if first else
        f"{measure_name} {len(totals_by_period)}개 기간 추이."
    )
    summary += f" 최고 기간: {peak} ({float(totals_by_period.max()):,.0f})." + window_note

    return ModuleResult(render=Render(
        summary=summary, table=table,
        chart=chart_spec(chart_data, "line", f"{measure_name} 기간별 추이"),
        # 추이는 그림이 본질이고 표는 근거다 — 차트를 표보다 먼저 배치한다.
        layout=["narrative", "key_value", "chart", "table"],
        key_value={"기간수": len(totals_by_period), "최고 기간": str(peak)},
    ))


# ── 누계·진척 (이력 필요) ────────────────────────────────────────────────────
def run_cumulative_progress(ctx, params, tools) -> ModuleResult:
    history, period_col, window_note = _history(ctx, params)
    if history is None:
        return ModuleResult(status="failed",
                            error="이력(history_dataset)이 없어 누계를 낼 수 없습니다.")
    schema, measure, measure_name = _resolve(ctx, params)
    if measure not in history.columns:
        return ModuleResult(status="failed", error=f"이력에 '{measure}' 컬럼이 없습니다.")

    series = history.groupby(period_col)[measure].sum().sort_index()
    cumulative = series.cumsum()
    target = params.get("target")

    chart_data = pd.DataFrame({"기간": series.index, "누계": cumulative.values})
    table = pd.DataFrame({
        "기간": series.index,
        measure_name: series.map(lambda v: f"{v:,.0f}").values,
        "누계": cumulative.map(lambda v: f"{v:,.0f}").values,
    })
    if target:
        table["진척률"] = (cumulative / float(target)).map(lambda v: f"{v * 100:.1f}%").values

    total = float(cumulative.iloc[-1])
    summary = (f"{measure_name} 누계 {total:,.0f} ({len(series)}개 기간, "
               f"기간 평균 {total / len(series):,.0f}).")
    key_value = {"누계": f"{total:,.0f}", "기간수": len(series)}
    if target:
        rate = total / float(target)
        summary += f" 목표 {float(target):,.0f} 대비 진척률 {rate * 100:.1f}%."
        key_value["진척률"] = f"{rate * 100:.1f}%"
    summary += window_note

    return ModuleResult(render=Render(
        summary=summary, table=table,
        chart=chart_spec(chart_data, "line", f"{measure_name} 기간 누계"),
        layout=["narrative", "key_value", "chart", "table"],
        key_value=key_value,
    ))
