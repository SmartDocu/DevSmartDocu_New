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

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_series, key_measure_of
from d2insight.engine.pipeline.data_request import fetch_frame, load_meta
from d2insight.engine.schema import get_schema
from d2insight.engine.types import ModuleResult


def _resolve(ctx, params) -> tuple:
    """(schema, measure, 표시명) — measure 미지정 시 핵심 measure."""
    schema = get_schema(ctx)
    measure = params.get("measure") or key_measure_of(ctx)
    return schema, measure, schema.logical_name(measure)


def _frames(ctx, params, schema, measure) -> tuple:
    """(실적표, 비교표, measure, 대체 안내, 실패 결과).

    기준(차원)이 있으면 같은 테이블이든 아니든 항상 이 모듈 전용 조회를 쓴다 — 스텝 공용 표는
    두 테이블을 조인해 만들어져 '1'쪽 값(주문 총액 등)이 '여러 줄'쪽 행 수만큼 복사되어 합계가
    부풀려진다(2026-09-28 사고). 측정값과 기준이 같은 테이블이어도 공용 표 자체가 조인된 표라
    마찬가지다(2026-09-29 지역별 분석에서 확인). DB는 조회 생성기(LLM)가, 업로드는 판다스가
    답한다(data_request).

    조회 뒤에 기준별 합계가 차원 없는 총합과 같은지 검사한다. 다르면 그 결과를 쓰지 않고 실패로
    알린다. 요청한 측정값 대신 나눌 수 있는 다른 측정값으로 조회됐으면 조용히 바꾸지 않고
    안내문을 돌려준다.
    """
    dimension = params.get("dimension")
    if not dimension:
        # 이 모듈들은 차원이 있어야 의미가 있다. 스텝 공용 표를 읽을 필요 없이 바로 실패로 알린다.
        return None, None, measure, "", ModuleResult(
            status="failed", error="params.dimension이 필요합니다(차원 미지정).")

    meta = ctx.get("meta_columns")
    if meta is None or measure not in set(meta["Physical_Name"]) or dimension not in set(meta["Physical_Name"]):
        meta = load_meta(ctx.meta)          # 스텝 공용 표에 없는 컬럼이면 전체 메타를 쓴다

    # 조회·힌트·합계 검사는 공통 부품(data_request.fetch_frame)이 한다 — 다른 모듈도 같이 쓴다.
    r = fetch_frame(ctx.meta, meta, schema, measure, [dimension], params.setdefault("_queries", []))
    if r.get("error"):
        return None, None, measure, "", ModuleResult(status="failed", error=r["error"])
    note = f" {r['note']} — 이 사실을 한 문장으로 밝혀라." if r["note"] else ""
    return r["actual"], r["compare"], r["measure"], note, None


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
    schema, measure, measure_name = _resolve(ctx, params)
    actual_df, compare_df, measure, subst_note, err = _frames(ctx, params, schema, measure)
    if err:
        return err
    measure_name = schema.logical_name(measure)
    dimension, err = _need_dimension(params, actual_df)
    if err:
        return err

    top_n = int(params.get("top_n") or 20)
    panel = _compare_panel(actual_df, compare_df, dimension, measure)
    panel = panel.sort_values("Actual_Value", ascending=False).reset_index(drop=True)
    shown = panel.head(top_n)
    shown = shown.rename(columns={"Item_Name": schema.logical_name(dimension)})

    total_a = float(panel["Actual_Value"].sum())
    total_v = float(panel["Variance"].sum())
    dim_name = schema.logical_name(dimension)

    hint = (
        "규모가 큰 항목과 증감이 큰 항목이 다르면 그 차이를 짚어라. 비교기간 대비 분석기간을 "
        "함께 보여줘라(가능하면 차트도 비교기간·분석기간 두 계열로)."
    )
    if not shown.empty and (shown["Comparison_Value"] == 0).all():
        hint += (" 상위 항목 전부 비교기간 실적이 0(신규 취급)이라 증감률이 의미 없다는 것도 밝혀라"
                 " — 재구매 주기가 길어 원시 2개월 비교의 함정일 수 있다.")
    hint += subst_note

    render = render_from_dataframe(
        shown, purpose="차원×항목 실적과 증감을 표·차트로 제시.", narrative_hint=hint,
        params={"차원": dim_name, "측정값": measure_name}, label="actual_aggregate",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {"차원": dim_name, "합계": f"{total_a:,.0f}", "증감": f"{total_v:+,.0f}"}
    return ModuleResult(render=render)


# ── 구성비 ───────────────────────────────────────────────────────────────────
def run_composition(ctx, params, tools) -> ModuleResult:
    schema, measure, measure_name = _resolve(ctx, params)
    actual_df, compare_df, measure, subst_note, err = _frames(ctx, params, schema, measure)
    if err:
        return err
    measure_name = schema.logical_name(measure)
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
    dim_name = schema.logical_name(dimension)
    shown = shown.rename(columns={"Item_Name": dim_name})

    top = panel.iloc[0]
    render = render_from_dataframe(
        shown,
        purpose="차원 항목별 구성비와 비중 변화를 제시.",
        narrative_hint="비중이 커진 항목과 줄어든 항목을 짚고, 집중도가 높아졌는지 낮아졌는지 말하라." + subst_note,
        params={"차원": dim_name, "측정값": measure_name}, label="composition",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {"1위": str(top["Item_Name"]), "1위 비중": f"{top['Share'] * 100:.1f}%"}
    return ModuleResult(render=render)


# ── 순위 ─────────────────────────────────────────────────────────────────────
def run_ranking(ctx, params, tools) -> ModuleResult:
    schema, measure, measure_name = _resolve(ctx, params)
    actual_df, compare_df, measure, subst_note, err = _frames(ctx, params, schema, measure)
    if err:
        return err
    measure_name = schema.logical_name(measure)
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
    if not len(shown):
        return ModuleResult(status="failed", error="순위를 낼 항목이 없습니다.")

    dim_name = schema.logical_name(dimension)
    shown = shown.copy()
    shown.insert(0, "순위", range(1, len(shown) + 1))
    shown = shown.rename(columns={"Item_Name": dim_name})

    label = "상위" if order == "desc" else "하위"
    basis = measure_name if by == "actual" else f"{measure_name} 증감"
    render = render_from_dataframe(
        shown,
        purpose="항목 상/하위 순위를 제시.",
        narrative_hint="상위권의 규모 차이가 큰지 고른지 짚어라. 순위와 증감 방향이 어긋나면 그 점을 말하라." + subst_note,
        params={"차원": dim_name, "기준": basis, "정렬": label}, label="ranking",
        cache=params.get("_llm_render_cache"),
    )
    return ModuleResult(render=render)


# ── 추이 (기간별 값을 직접 요청) ─────────────────────────────────────────────
def _series(ctx, params, measure, dimension):
    """(기간별 표, 기간 컬럼, 실패 결과) — 측정값을 기간별로 직접 요청한다(params.aggregate로 집계 방식)."""
    try:
        frame = get_series(ctx, measure, dimension, params)
    except ValueError as e:
        return None, None, ModuleResult(status="failed", error=f"기간별 값 조회에 실패했습니다: {e}")
    return frame, frame.columns[0], None


def run_trend(ctx, params, tools) -> ModuleResult:
    schema, measure, measure_name = _resolve(ctx, params)
    dimension = params.get("dimension")
    history, period_col, failed = _series(ctx, params, measure, dimension)
    if failed:
        return failed
    window_note = ""

    if dimension:
        top_n = int(params.get("top_n") or 5)
        totals = history.groupby(dimension)[measure].sum().sort_values(ascending=False)
        keep = totals.head(top_n).index
        sub = history[history[dimension].isin(keep)]
        series = sub.pivot_table(index=period_col, columns=dimension,
                                 values=measure, aggfunc="sum").fillna(0.0).sort_index()
        table = series.reset_index().rename(columns={period_col: "기간"})
    else:
        series = history.groupby(period_col)[measure].sum().sort_index()
        diff = series.diff()
        table = pd.DataFrame({
            "기간": series.index,
            measure_name: series.values,
            "전기 대비": diff.values,
        })

    totals_by_period = history.groupby(period_col)[measure].sum().sort_index()
    peak = totals_by_period.idxmax()

    render = render_from_dataframe(
        table,
        purpose="측정값의 기간별 추이를 제시.",
        narrative_hint=(
            "추이의 방향·변곡점·계절성 여부를 짚어라. 단발 등락과 추세를 구분해 서술하라."
            + window_note
        ),
        params={"측정값": measure_name}, label="trend",
        cache=params.get("_llm_render_cache"),
    )
    render.layout = ["narrative", "key_value", "chart", "table"]
    render.key_value = {"기간수": len(totals_by_period), "최고 기간": str(peak)}
    return ModuleResult(render=render)


# ── 누계·진척 (기간별 값을 직접 요청) ────────────────────────────────────────
def run_cumulative_progress(ctx, params, tools) -> ModuleResult:
    schema, measure, measure_name = _resolve(ctx, params)
    history, period_col, failed = _series(ctx, params, measure, None)
    if failed:
        return failed
    window_note = ""

    series = history.groupby(period_col)[measure].sum().sort_index()
    cumulative = series.cumsum()
    target = params.get("target")

    table = pd.DataFrame({"기간": series.index, measure_name: series.values, "누계": cumulative.values})
    if target:
        table["진척률(%)"] = (cumulative / float(target) * 100).values

    total = float(cumulative.iloc[-1])
    key_value = {"누계": f"{total:,.0f}", "기간수": len(series)}
    hint = "누계 추세와 기간 평균 규모를 짚어라." + window_note
    if target:
        rate = total / float(target)
        key_value["진척률"] = f"{rate * 100:.1f}%"
        hint += f" 목표 {float(target):,.0f} 대비 진척률({rate * 100:.1f}%)도 언급하라."

    render = render_from_dataframe(
        table, purpose="기간 누계와 진척률을 제시.", narrative_hint=hint,
        params={"측정값": measure_name}, label="cumulative_progress",
        cache=params.get("_llm_render_cache"),
    )
    render.layout = ["narrative", "key_value", "chart", "table"]
    render.key_value = key_value
    return ModuleResult(render=render)
