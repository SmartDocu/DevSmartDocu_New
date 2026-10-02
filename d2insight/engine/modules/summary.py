"""measure_summary 모듈 — 전체 증감 총평 + 공용 분모 산출 (§11).

두 가지를 내보낸다.
  1. measure_summary : Measure별 비교값/실적값/증감액/증감률 표(§3 Summary_DataSet)
                       + 파생 measure(단가·할인율)
  2. total_variance  : 핵심 measure의 전체 증감액·증감률. **공용 분모**다.
                       within_contribution(§12-B)·sales_bridge(§13)가 그대로 재사용하며
                       절대 다시 계산하지 않는다(§6.2 — 스텝 간 숫자 불일치의 주 원인).

컬럼명을 코드에 박지 않는다. 어떤 컬럼이 금액·물량·할인인지는 **데이터소스 정의**가 말해 준다
(src/engine/schema.py). 그래서 구매분석(구매액·발주수량)에서도 이 모듈이 그대로 동작한다.

파생 measure
  단가(ASP) = 금액 / 물량                      (물량 역할이 없으면 생략)
  할인율    = 할인액 / (금액 + 할인액)          (할인 역할이 없으면 생략)
              금액이 할인 후 순액이라는 전제 — 정가 기준으로 환산해 비율을 낸다.

데이터 조회 (2026-09-28 재작성)
  이 모듈은 더 이상 스텝 공용 actual_dataset/compare_dataset을 쓰지 않는다 — 헤더/디테일처럼
  1:N으로 조인되는 소스에서, 서로 다른 테이블의 측정값을 한 조회에 섞으면 '1'쪽 측정값이
  'N'쪽 행 수만큼 부풀려진다(§ header-detail fan-out, 2026-09-28 실사고). 그래서 필요한
  측정값을 **원래 테이블별로 묶어서 그때그때 직접 조회**한다 — 차원(dimension)은 요청하지
  않으므로(총평은 기간 합계만 필요) 같은 테이블 안에서는 조인 없이 안전하게 합산된다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.pipeline.data_request import fetch_measure_groups, is_upload, load_meta, source_of
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import role_column
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_DISCOUNT, ROLE_QUANTITY, Schema
from d2insight.engine.types import ModuleResult

DERIVED_UNIT_PRICE = "단가"
DERIVED_DISCOUNT_RATE = "할인율"


def _fmt_pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def _row(name: str, logical: str, compare: float, actual: float) -> dict:
    """반올림하지 않는다 — 할인율(0.0006)처럼 작은 비율이 0으로 뭉개진다. 서식은 표시 단계에서."""
    variance = actual - compare
    return {
        "Physical_Name": name,
        "Logical_Name": logical,
        "Comparison_Value": compare,
        "Actual_Value": actual,
        "Variance": variance,
        "Rate": variance / compare if compare else 0.0,
    }


def _display_table(df: pd.DataFrame, ratio_rows: set[str]) -> pd.DataFrame:
    """표시용 표 — 한 열에 금액과 비율이 섞이므로 **행별로** 서식을 정한다."""
    def _cell(row, col: str) -> str:
        v = float(row[col])
        if row["Physical_Name"] in ratio_rows:
            return f"{v * 100:.2f}%p" if col == "Variance" else f"{v * 100:.2f}%"
        if row["Physical_Name"] == DERIVED_UNIT_PRICE:
            return f"{v:,.2f}"
        return f"{v:,.0f}"

    return pd.DataFrame({
        "측정": df["Logical_Name"],
        "비교기간": df.apply(lambda r: _cell(r, "Comparison_Value"), axis=1),
        "분석기간": df.apply(lambda r: _cell(r, "Actual_Value"), axis=1),
        "증감": df.apply(lambda r: _cell(r, "Variance"), axis=1),
        "증감률": df["Rate"].map(_fmt_pct),
    })


def _fetch_measure_sums(ctx_meta: dict, measures: list[str],
                        meta: pd.DataFrame, queries: list | None = None) -> tuple[dict, dict, list[str]]:
    """측정값들을 원래 테이블(파일)별로 묶어 따로따로 조회하고, 각각의 기간 합계(SUM)만
    돌려준다. 조회 방식은 공통 함수(data_request)가 정한다 — DB는 SQL, 업로드는 판다스.
    차원을 요청하지 않으므로 같은 테이블 안에서는 조인이 없어 안전하다.

    반환: (실적 합계 dict, 비교 합계 dict, 조회 실패한 측정값 목록)
    """
    actual_sums: dict[str, float] = {}
    compare_sums: dict[str, float] = {}
    failed: list[str] = []
    for group in fetch_measure_groups(ctx_meta, measures, meta, queries=queries):
        if group["error"]:
            failed.extend(group["measures"])
            continue
        actual_df, compare_df = group["actual"], group["compare"]
        for m in group["measures"]:
            if m in actual_df.columns:
                actual_sums[m] = float(actual_df[m].sum())
                compare_sums[m] = float(compare_df[m].sum()) if m in compare_df.columns else 0.0
            else:
                failed.append(m)
    return actual_sums, compare_sums, failed


def run(ctx, params, tools) -> ModuleResult:
    try:
        meta = load_meta(ctx.meta)   # 필터 없는 전체 스키마(역할이 그대로 잡혀 있음) — DB/업로드 공통
    except ValueError as e:
        return ModuleResult(status="failed", error=str(e))
    schema = Schema(meta)
    # 핵심 측정값은 금액 역할 중 기준 파일(여럿이면 가장 세분된 거래 기록)의 것이다. 합친 메타의 첫 핵심
    # 표시를 그대로 쓰면 다른 파일(월 집계 표 등)의 금액이 잡힐 수 있다.
    key_measure = role_column(ctx, ROLE_AMOUNT) or schema.key_measure

    requested = params.get("measures")
    measures = list(schema.measures)
    # 여러 파일이면 핵심 측정값과 같은 파일의 측정값만 총평에 담는다(다른 표의 측정값은 따로 분석한다).
    key_src = source_of(ctx.meta, meta, key_measure)
    if key_src and is_upload(ctx.meta):
        measures = [m for m in measures if source_of(ctx.meta, meta, m) in (key_src, None)]
    if requested:
        measures = [m for m in measures if m in set(requested) | {key_measure}]
    if key_measure not in measures:
        measures = [key_measure] + measures

    # 만든 SQL은 params["_queries"]에 남겨 정기보고서 등록 때 저장된다(entry.collect_execution_cache).
    # 밑줄로 시작해야 계획 검증(options.py)이 카탈로그에 없는 실행 캐시로 허용한다.
    actual_sums, compare_sums, failed_measures = _fetch_measure_sums(
        ctx.meta, measures, meta, queries=params.setdefault("_queries", []))
    if key_measure not in actual_sums:
        return ModuleResult(
            status="failed",
            error=f"핵심 measure '{key_measure}' 조회에 실패했습니다.",
        )
    measures = [m for m in measures if m in actual_sums]  # 조회 실패한 건 총평에서 뺀다

    rows = [
        _row(m, schema.logical_name(m), compare_sums.get(m, 0.0), actual_sums[m])
        for m in measures
    ]

    ratio_rows: set[str] = set()

    # 파생: 단가(ASP) — 물량 역할이 선언된 경우에만
    amount_col = key_measure
    qty_col = role_column(ctx, ROLE_QUANTITY, amount_col)
    if qty_col and qty_col in actual_sums and amount_col in actual_sums:
        a_qty, c_qty = actual_sums[qty_col], compare_sums.get(qty_col, 0.0)
        a_asp = actual_sums[amount_col] / a_qty if a_qty else 0.0
        c_asp = compare_sums.get(amount_col, 0.0) / c_qty if c_qty else 0.0
        rows.append(_row(DERIVED_UNIT_PRICE, f"단가({schema.logical_name(amount_col)}/"
                                             f"{schema.logical_name(qty_col)})", c_asp, a_asp))

    # 파생: 할인율 — 할인 역할이 선언된 경우에만. 비율이라 합산이 성립하지 않아 기간별로 계산한다.
    disc_col = role_column(ctx, ROLE_DISCOUNT, amount_col)
    if disc_col and disc_col in actual_sums:
        def _rate(disc: float, amount: float) -> float:
            gross = amount + disc                            # 금액이 할인 후 순액이라는 전제
            return disc / gross if gross else 0.0
        rows.append(_row(DERIVED_DISCOUNT_RATE, DERIVED_DISCOUNT_RATE,
                         _rate(compare_sums.get(disc_col, 0.0), compare_sums.get(amount_col, 0.0)),
                         _rate(actual_sums[disc_col], actual_sums.get(amount_col, 0.0))))
        ratio_rows.add(DERIVED_DISCOUNT_RATE)

    summary_df = pd.DataFrame(rows)
    key_row = summary_df[summary_df["Physical_Name"] == key_measure]
    if key_row.empty:
        return ModuleResult(
            status="failed",
            error=f"핵심 measure '{key_measure}' 집계값이 없어 총평·공용 분모를 만들 수 없습니다.",
        )
    key = key_row.iloc[0]

    # 공용 분모 — 이후 모든 기여도·브리지 분석이 이 값을 분모로 쓴다(재계산 금지).
    total_variance = {
        "measure": key_measure,
        "compare_value": float(key["Comparison_Value"]),
        "actual_value": float(key["Actual_Value"]),
        "variance": float(key["Variance"]),
        "rate": float(key["Rate"]),
    }

    # 파생 지표는 실제로 만들어졌을 때만 언급한다 — 없는데 "단가·할인율" 같은 말을 지침에
    # 넣으면 해설자가 그 데이터에 없는 이야기를 지어낸다(로그 데이터에서 "판매 전략" 언급).
    derived = [r["Logical_Name"] for r in rows
               if r["Physical_Name"] in (DERIVED_UNIT_PRICE, DERIVED_DISCOUNT_RATE)]
    hint = f"핵심 측정값({schema.logical_name(key_measure)})의 증감을 먼저 말하라."
    if derived:
        hint += f" 이어서 파생 지표({', '.join(derived)})의 변화도 짚어라."
    hint += " 표에 없는 지표는 언급하지 마라."

    render = render_from_dataframe(
        _display_table(summary_df, ratio_rows),
        purpose="측정값 전체 증감 총평을 제시.",
        narrative_hint=hint,
        params={"핵심 측정값": schema.logical_name(key_measure)}, label="measure_summary",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {
        "실적": f"{total_variance['actual_value']:,.0f}",
        "비교": f"{total_variance['compare_value']:,.0f}",
        "증감액": f"{total_variance['variance']:+,.0f}",
        "증감률": _fmt_pct(total_variance["rate"]),
    }
    return ModuleResult(outputs={"measure_summary": summary_df, "total_variance": total_variance}, render=render)
