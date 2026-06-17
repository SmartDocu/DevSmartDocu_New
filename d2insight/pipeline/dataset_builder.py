"""보고서작성방안.md §2~§6 DataSet 빌더.

흐름:
  1. build_actual_compare_datasets() — DB에서 당월/비교월 집계 DataFrame 취득
  2. build_summary_dataset()         — §3 전체 Measure 증감 요약
  3. build_by_item_dataset()         — §4 차원×항목별 증감 + 파레토 플래그
  4. build_by_item_summary_dataset() — §5 차원별 통계(Impact, Z, HHI, Shapley, DVI)
  5. build_by_item_count_dataset()   — §6 제품/고객 신규·손실 항목수
  6. build_sales_bridge()            — §13 Sales Bridge 분해
  7. build_all_datasets()            — 1~6 통합 실행

비교 기간:
  compare_type="MoM" → 전월
  compare_type="YoY" → 전년동월
  compare_type="QoQ" → 전분기(3개월 전)
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.app.config import settings
import d2insight.config as config
from d2insight.pipeline.shapley import shapley_exact, _value_fn_factory


# ── 상수 ─────────────────────────────────────────────────────────────────────

DIMENSION_COLS: list[str] = [
    "채널",
    "고객번호",
    "지역_대륙",
    "지역_국가",
    "지역명",
    "제품대분류",
    "제품중분류",
    "제품모델",
    "제품",
]

KEY_MEASURE   = "매출"
MEASURE_COLS  = ["매출", "수량", "할인액"]   # 단가(ASP) = 매출/수량, 별도 계산

COUNT_DIMS    = ["제품", "고객번호"]          # By_Item_Count 대상

PARETO_THRESHOLD: float = config.PARETO_THRESHOLD          # 0.80
ANOMALY_SIGMA:    float = getattr(config, "ANOMALY_SIGMA", 3.0)


# ── 반환 타입 ─────────────────────────────────────────────────────────────────

class SalesDatasets(NamedTuple):
    target_month:      str
    compare_type:      str
    actual_df:         pd.DataFrame   # 당월 집계
    compare_df:        pd.DataFrame   # 비교월 집계
    summary_df:        pd.DataFrame   # §3
    byitem_df:         pd.DataFrame   # §4
    byitem_summary_df: pd.DataFrame   # §5
    byitem_count_df:   pd.DataFrame   # §6
    sales_bridge:      dict           # §13


# ── 집계 SQL ──────────────────────────────────────────────────────────────────

_SQL_AGG = """
SELECT
    CASE h.OnlineOrderFlag
        WHEN 1 THEN N'온라인' ELSE N'오프라인' END      AS [채널],
    h.AccountNumber                                       AS [고객번호],
    ISNULL(h.Continent,     N'미분류')                   AS [지역_대륙],
    ISNULL(h.Country,       N'미분류')                   AS [지역_국가],
    ISNULL(h.TerritoryName, N'미분류')                   AS [지역명],
    ISNULL(d.categoryname,    N'미분류')                 AS [제품대분류],
    ISNULL(d.subcategoryname, N'미분류')                 AS [제품중분류],
    ISNULL(d.modelname,       N'미분류')                 AS [제품모델],
    ISNULL(d.productname,     N'미분류')                 AS [제품],
    SUM(d.OrderQty)                                       AS [수량],
    SUM(d.UnitPrice * d.UnitPriceDiscount * d.OrderQty)  AS [할인액],
    SUM(d.LineTotal)                                      AS [매출]
FROM  [dbo].[view_SalesOrderHeader] h
INNER JOIN [dbo].[view_SalesOrderDetail] d
    ON h.SalesOrderID = d.SalesOrderID
WHERE h.OrderDate >= :start_date
  AND h.OrderDate <  :end_date
GROUP BY
    h.OnlineOrderFlag, h.AccountNumber,
    h.Continent, h.Country, h.TerritoryName,
    d.categoryname, d.subcategoryname, d.modelname, d.productname
"""


# ── DB Engine ─────────────────────────────────────────────────────────────────

def _build_engine() -> Engine:
    odbc = (
        f"Driver={{{settings.DB_DRIVER}}};"
        f"Server={settings.DB_SERVER},1433;"
        f"Database={settings.DB_DATABASE};"
        f"UID={settings.DB_USERNAME};"
        f"PWD={settings.DB_PASSWORD};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    url = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"
    return create_engine(url, pool_pre_ping=True)


# ── 날짜 유틸 ─────────────────────────────────────────────────────────────────

def _month_first(yyyymm: str) -> date:
    y, m = map(int, yyyymm.split("-"))
    return date(y, m, 1)


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    return date(total // 12, (total % 12) + 1, 1)


def _actual_range(target_month: str) -> tuple[date, date]:
    start = _month_first(target_month)
    return start, _add_months(start, 1)


def _compare_range(target_month: str, compare_type: str) -> tuple[date, date]:
    base = _month_first(target_month)
    if compare_type == "YoY":
        start = _add_months(base, -12)
    elif compare_type == "QoQ":
        start = _add_months(base, -3)
    else:                               # MoM (default)
        start = _add_months(base, -1)
    return start, _add_months(start, 1)


# ── §2: Actual + Compare DataFrames ─────────────────────────────────────────

def build_actual_compare_datasets(
    target_month: str,
    compare_type: str = "MoM",
    engine: Engine | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """당월(Actual) + 비교월(Compare) 집계 DataFrame 반환."""
    if engine is None:
        engine = _build_engine()

    a_start, a_end = _actual_range(target_month)
    c_start, c_end = _compare_range(target_month, compare_type)

    with engine.connect() as conn:
        actual_df  = pd.read_sql_query(
            text(_SQL_AGG), conn,
            params={"start_date": a_start, "end_date": a_end},
        )
        compare_df = pd.read_sql_query(
            text(_SQL_AGG), conn,
            params={"start_date": c_start, "end_date": c_end},
        )

    print(f"[dataset_builder] Actual({target_month}): {len(actual_df):,}행  "
          f"Compare({compare_type}): {len(compare_df):,}행")
    return actual_df, compare_df


# ── §3: Summary_DataSet ───────────────────────────────────────────────────────

def build_summary_dataset(
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
) -> pd.DataFrame:
    """§3 Summary_DataSet: Measure별 Comparison / Actual / Variance / Rate."""
    rows = []

    for col in MEASURE_COLS:
        if col not in actual_df.columns:
            continue
        a_val = float(actual_df[col].sum())
        c_val = float(compare_df[col].sum()) if col in compare_df.columns else 0.0
        var   = a_val - c_val
        rate  = var / c_val if c_val else 0.0
        rows.append({
            "Physical_Name":    col,
            "Logical_Name":     col,
            "Comparison_Value": round(c_val, 2),
            "Actual_Value":     round(a_val, 2),
            "Variance":         round(var,   2),
            "Rate":             round(rate,  4),
        })

    # ASP(단가) = 매출 / 수량 — 별도 계산
    a_qty = float(actual_df["수량"].sum())  if "수량" in actual_df.columns  else 0.0
    c_qty = float(compare_df["수량"].sum()) if "수량" in compare_df.columns else 0.0
    a_asp = actual_df["매출"].sum()  / a_qty if a_qty else 0.0
    c_asp = compare_df["매출"].sum() / c_qty if c_qty else 0.0
    asp_var  = a_asp - c_asp
    asp_rate = asp_var / c_asp if c_asp else 0.0
    rows.append({
        "Physical_Name":    "단가",
        "Logical_Name":     "단가(ASP)",
        "Comparison_Value": round(c_asp,     2),
        "Actual_Value":     round(a_asp,     2),
        "Variance":         round(asp_var,   2),
        "Rate":             round(asp_rate,  4),
    })

    return pd.DataFrame(rows)


# ── §4: By_Item_DataSet ───────────────────────────────────────────────────────

def _pareto_flag(values: pd.Series, threshold: float) -> np.ndarray:
    """상위 threshold 누적 비율에 도달하는 항목들에 1 표시 (내림차순 기준).

    파레토 80%: 누적합이 80%에 도달하기 전까지의 항목을 Is_Main = 1로 표시.
    경계 항목(80%를 처음 넘는 항목)도 포함한다.
    """
    total = values.sum()
    if total <= 0:
        return np.zeros(len(values), dtype=int)

    order    = np.argsort(values.values)[::-1]          # 내림차순 인덱스
    cumsum   = np.cumsum(values.values[order])
    prev_cum = np.concatenate([[0.0], cumsum[:-1]])      # 직전 누적합
    flag     = (prev_cum / total < threshold).astype(int)

    result = np.zeros(len(values), dtype=int)
    result[order] = flag
    return result


def build_by_item_dataset(
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    pareto_threshold: float = PARETO_THRESHOLD,
) -> pd.DataFrame:
    """§4 By_Item_DataSet: 모든 차원 × 항목별 Key_Measure 증감 + 파레토 플래그."""
    parts: list[pd.DataFrame] = []

    for dim in DIMENSION_COLS:
        if dim not in actual_df.columns:
            continue

        agg_a = actual_df.groupby(dim)[KEY_MEASURE].sum().rename("Actual_Value")
        agg_c = (compare_df.groupby(dim)[KEY_MEASURE].sum().rename("Comparison_Value")
                 if dim in compare_df.columns else pd.Series(dtype=float, name="Comparison_Value"))

        merged = (
            pd.concat([agg_a, agg_c], axis=1)
            .fillna(0.0)
            .reset_index()
            .rename(columns={dim: "Item_Name"})
        )

        merged["Variance"] = merged["Actual_Value"] - merged["Comparison_Value"]
        merged["Rate"] = merged.apply(
            lambda r: r["Variance"] / r["Comparison_Value"] if r["Comparison_Value"] else 0.0,
            axis=1,
        )
        merged["New_Lost_Flag"] = merged.apply(
            lambda r: "New"  if r["Comparison_Value"] == 0 and r["Actual_Value"] > 0
                 else "Lost" if r["Actual_Value"] == 0     and r["Comparison_Value"] > 0
                 else "",
            axis=1,
        )

        merged["Is_Comparison_Main"] = _pareto_flag(merged["Comparison_Value"], pareto_threshold)
        merged["Is_Actual_Main"]     = _pareto_flag(merged["Actual_Value"],     pareto_threshold)
        merged["Is_Main"] = ((merged["Is_Comparison_Main"] == 1) | (merged["Is_Actual_Main"] == 1)).astype(int)

        merged.insert(0, "Dimension_Logical_Name", dim)
        merged.insert(1, "Measure_Logical_Name",   KEY_MEASURE)

        parts.append(merged[[
            "Dimension_Logical_Name", "Measure_Logical_Name", "Item_Name",
            "Comparison_Value", "Actual_Value", "Variance", "Rate",
            "New_Lost_Flag", "Is_Comparison_Main", "Is_Actual_Main", "Is_Main",
        ]])

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ── §5: By_Item_Summary_DataSet ───────────────────────────────────────────────

def _shapley_for_dims(
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    dim_cols: list[str],
) -> dict[str, float]:
    """기존 shapley_exact 재활용 — value fn은 Σ|Δ_g| 기준."""
    avail = [d for d in dim_cols if d in actual_df.columns and d in compare_df.columns]
    if not avail:
        return {d: 0.0 for d in dim_cols}

    # _value_fn_factory는 "매출" 컬럼을 사용 — KEY_MEASURE와 동일
    value_fn = _value_fn_factory(actual_df, compare_df)
    raw      = shapley_exact(value_fn, avail)

    total = sum(abs(v) for v in raw.values())
    share = {d: (v / total if total else 0.0) for d, v in raw.items()}

    # avail에 없는 차원은 0
    return {d: round(share.get(d, 0.0), 4) for d in dim_cols}


def build_by_item_summary_dataset(
    byitem_df: pd.DataFrame,
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
) -> pd.DataFrame:
    """§5 By_Item_Summary_DataSet: 차원별 통계 + Shapley + HHI + DVI."""
    if byitem_df.empty:
        return pd.DataFrame()

    dim_cols      = byitem_df["Dimension_Logical_Name"].unique().tolist()
    shapley_share = _shapley_for_dims(actual_df, compare_df, dim_cols)

    rows = []
    for dim in dim_cols:
        # New 항목 제외
        sub = byitem_df[
            (byitem_df["Dimension_Logical_Name"] == dim)
            & (byitem_df["New_Lost_Flag"] != "New")
        ]
        if sub.empty:
            continue

        rates     = sub["Rate"].values.astype(float)
        variances = sub["Variance"].values.astype(float)

        n            = len(sub)
        rate_mean    = float(np.mean(rates))
        rate_median  = float(np.median(rates))
        sigma        = float(np.std(rates, ddof=1)) if n > 1 else 0.0
        impact_score = float(np.sum(np.abs(variances)))

        z_scores  = (rates - rate_mean) / sigma if sigma > 0 else np.zeros(n)
        avg_z     = float(np.mean(np.abs(z_scores)))

        # HHI = Σ (|Δi| / Impact_Score)²  — 임팩트 집중도
        hhi = float(np.sum((np.abs(variances) / impact_score) ** 2)) if impact_score > 0 else 0.0

        # DVI = Impact × HHI × Average_Z
        dvi = impact_score * hhi * avg_z

        rows.append({
            "Dimension_Logical_Name": dim,
            "Measure_Logical_Name":   KEY_MEASURE,
            "Count":         n,
            "Rate_Mean":     round(rate_mean,   4),
            "Rate_Median":   round(rate_median, 4),
            "σ":             round(sigma,       4),
            "Impact_Score":  round(impact_score, 2),
            "Shapley_Value": shapley_share.get(dim, 0.0),
            "-3σ":           round(rate_mean - 3 * sigma, 4),
            "-2σ":           round(rate_mean - 2 * sigma, 4),
            "-1σ":           round(rate_mean - 1 * sigma, 4),
            "+1σ":           round(rate_mean + 1 * sigma, 4),
            "+2σ":           round(rate_mean + 2 * sigma, 4),
            "+3σ":           round(rate_mean + 3 * sigma, 4),
            "Average_Z":     round(avg_z, 4),
            "HHI":           round(hhi,   4),
            "DVI":           round(dvi,   2),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Shapley_Value", ascending=False).reset_index(drop=True)
    return df


# ── §6: By_Item_Count_DataSet ─────────────────────────────────────────────────

def build_by_item_count_dataset(byitem_df: pd.DataFrame) -> pd.DataFrame:
    """§6 By_Item_Count_DataSet: 제품·고객 신규/손실 항목수."""
    if byitem_df.empty:
        return pd.DataFrame()

    rows = []
    for dim in COUNT_DIMS:
        sub = byitem_df[byitem_df["Dimension_Logical_Name"] == dim]
        if sub.empty:
            continue
        rows.append({
            "Dimension_Logical_Name": dim,
            "Comparison_Item_Count":  int((sub["Comparison_Value"] > 0).sum()),
            "Actual_Item_Count":      int((sub["Actual_Value"] > 0).sum()),
            "New_Item_Count":         int((sub["New_Lost_Flag"] == "New").sum()),
            "Lost_Item_Count":        int((sub["New_Lost_Flag"] == "Lost").sum()),
        })
    return pd.DataFrame(rows)


# ── §13: Sales Bridge ─────────────────────────────────────────────────────────

def build_sales_bridge(
    summary_df: pd.DataFrame,
    byitem_df: pd.DataFrame,
) -> dict:
    """§13 Sales Bridge 분해: 수량·ASP·할인·신규상품·단종·신규고객·이탈 효과."""
    s = summary_df.set_index("Physical_Name")

    def _get(col: str, field: str, default: float = 0.0) -> float:
        try:
            return float(s.at[col, field])
        except KeyError:
            return default

    a_rev  = _get("매출",   "Actual_Value")
    c_rev  = _get("매출",   "Comparison_Value")
    a_qty  = _get("수량",   "Actual_Value")
    c_qty  = _get("수량",   "Comparison_Value")
    a_disc = _get("할인액", "Actual_Value")
    c_disc = _get("할인액", "Comparison_Value")

    c_asp = c_rev / c_qty if c_qty else 0.0
    a_asp = a_rev / a_qty if a_qty else 0.0

    total_variance    = round(a_rev - c_rev, 2)
    qty_effect        = round((a_qty - c_qty) * c_asp, 2)
    asp_effect        = round((a_asp - c_asp) * a_qty, 2)
    discount_effect   = round(-(a_disc - c_disc), 2)

    def _dim_effect(dim: str, flag: str, val_col: str) -> float:
        sub = byitem_df[
            (byitem_df["Dimension_Logical_Name"] == dim)
            & (byitem_df["New_Lost_Flag"] == flag)
        ]
        return round(float(sub[val_col].sum()), 2)

    return {
        "total_variance":       total_variance,
        "qty_effect":           qty_effect,
        "asp_effect":           asp_effect,
        "discount_effect":      discount_effect,
        "new_product_effect":   _dim_effect("제품",    "New",  "Actual_Value"),
        "lost_product_effect":  _dim_effect("제품",    "Lost", "Comparison_Value") * -1,
        "new_customer_effect":  _dim_effect("고객번호", "New",  "Actual_Value"),
        "lost_customer_effect": _dim_effect("고객번호", "Lost", "Comparison_Value") * -1,
    }


# ── 통합 실행 ──────────────────────────────────────────────────────────────────

def build_all_datasets(
    target_month: str,
    compare_type: str = "MoM",
    engine: Engine | None = None,
) -> SalesDatasets:
    """§2~§6 DataSet + Sales Bridge 전체 빌드."""
    if engine is None:
        engine = _build_engine()

    actual_df, compare_df = build_actual_compare_datasets(target_month, compare_type, engine)

    summary_df        = build_summary_dataset(actual_df, compare_df)
    byitem_df         = build_by_item_dataset(actual_df, compare_df)
    byitem_summary_df = build_by_item_summary_dataset(byitem_df, actual_df, compare_df)
    byitem_count_df   = build_by_item_count_dataset(byitem_df)
    sales_bridge      = build_sales_bridge(summary_df, byitem_df)

    return SalesDatasets(
        target_month      = target_month,
        compare_type      = compare_type,
        actual_df         = actual_df,
        compare_df        = compare_df,
        summary_df        = summary_df,
        byitem_df         = byitem_df,
        byitem_summary_df = byitem_summary_df,
        byitem_count_df   = byitem_count_df,
        sales_bridge      = sales_bridge,
    )
