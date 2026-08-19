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
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.schema import ROLE_AMOUNT, ROLE_DISCOUNT, ROLE_QUANTITY, get_schema
from d2insight.engine.types import ModuleResult, Render

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


def run(ctx, params, tools) -> ModuleResult:
    actual_df = ctx.get("actual_dataset")
    compare_df = ctx.get("compare_dataset")
    if actual_df is None or compare_df is None:
        return ModuleResult(status="failed", error="actual_dataset/compare_dataset이 없습니다.")

    schema = get_schema(ctx)
    key_measure = schema.key_measure
    if key_measure not in actual_df.columns:
        return ModuleResult(
            status="failed",
            error=f"핵심 measure '{key_measure}' 컬럼이 데이터에 없습니다.",
        )

    requested = params.get("measures")
    measures = [m for m in schema.measures if m in actual_df.columns]
    if requested:
        measures = [m for m in measures if m in set(requested) | {key_measure}]

    rows = [
        _row(m, schema.logical_name(m),
             float(compare_df[m].sum()) if m in compare_df.columns else 0.0,
             float(actual_df[m].sum()))
        for m in measures
    ]

    ratio_rows: set[str] = set()

    # 파생: 단가(ASP) — 물량 역할이 선언된 경우에만
    qty_col = schema.column(ROLE_QUANTITY)
    amount_col = schema.column(ROLE_AMOUNT) or key_measure
    if qty_col and qty_col in actual_df.columns and amount_col in actual_df.columns:
        a_qty, c_qty = float(actual_df[qty_col].sum()), float(compare_df[qty_col].sum())
        a_asp = float(actual_df[amount_col].sum()) / a_qty if a_qty else 0.0
        c_asp = float(compare_df[amount_col].sum()) / c_qty if c_qty else 0.0
        rows.append(_row(DERIVED_UNIT_PRICE, f"단가({schema.logical_name(amount_col)}/"
                                             f"{schema.logical_name(qty_col)})", c_asp, a_asp))

    # 파생: 할인율 — 할인 역할이 선언된 경우에만. 비율이라 합산이 성립하지 않아 기간별로 계산한다.
    disc_col = schema.column(ROLE_DISCOUNT)
    if disc_col and disc_col in actual_df.columns:
        def _rate(df: pd.DataFrame) -> float:
            disc = float(df[disc_col].sum())
            gross = float(df[amount_col].sum()) + disc      # 금액이 할인 후 순액이라는 전제
            return disc / gross if gross else 0.0
        rows.append(_row(DERIVED_DISCOUNT_RATE, DERIVED_DISCOUNT_RATE,
                         _rate(compare_df), _rate(actual_df)))
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

    parts = [
        f"{schema.logical_name(key_measure)} {total_variance['actual_value']:,.0f} "
        f"(전기 대비 {total_variance['variance']:+,.0f}, {_fmt_pct(total_variance['rate'])})"
    ]
    for _, r in summary_df.iterrows():
        name = r["Physical_Name"]
        if name == key_measure:
            continue
        if name in ratio_rows:
            parts.append(f"{r['Logical_Name']} {r['Actual_Value'] * 100:.2f}% "
                         f"({r['Variance'] * 100:+.2f}%p)")
        else:
            parts.append(f"{r['Logical_Name']} {_fmt_pct(float(r['Rate']))}")

    direction = "증가" if total_variance["variance"] >= 0 else "감소"
    summary = f"{direction} — " + ", ".join(parts) + "."

    return ModuleResult(
        outputs={"measure_summary": summary_df, "total_variance": total_variance},
        render=Render(
            summary=summary,
            table=_display_table(summary_df, ratio_rows),
            key_value={
                "실적": f"{total_variance['actual_value']:,.0f}",
                "비교": f"{total_variance['compare_value']:,.0f}",
                "증감액": f"{total_variance['variance']:+,.0f}",
                "증감률": _fmt_pct(total_variance["rate"]),
            },
        ),
    )
