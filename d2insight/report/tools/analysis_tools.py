"""범용 분석 툴 — 특정 뷰/컬럼명 하드코딩 금지. LLM이 메타정보로 컬럼을 결정."""
from __future__ import annotations

from typing import Optional

import pandas as pd
from langchain_core.tools import tool


@tool
def run_stats(data: list, columns: Optional[list] = None) -> dict:
    """수치 컬럼의 기술통계(mean/std/min/max/사분위수)를 계산합니다.

    Args:
        data: 분석할 데이터 (records 형식). execute_query 결과의 'data' 필드.
        columns: 분석할 컬럼명 목록. 미지정 시 모든 수치 컬럼 사용.
    """
    df = pd.DataFrame(data)
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    num = df.select_dtypes(include="number")
    if num.empty:
        return {"error": "수치 컬럼이 없습니다.", "total_records": len(df)}
    return {
        "total_records": len(df),
        "stats": num.describe().round(3).to_dict(),
    }


@tool
def run_trend(data: list, time_col: str, value_col: str) -> dict:
    """시계열 데이터를 일별로 집계하여 추세·피크·합계를 반환합니다.

    Args:
        data: 분석할 데이터 (records 형식).
        time_col: 날짜/시간 컬럼명.
        value_col: 집계할 수치 컬럼명.
    """
    df = pd.DataFrame(data)
    if time_col not in df.columns:
        return {"error": f"시간 컬럼 '{time_col}'이 없습니다."}
    if value_col not in df.columns:
        return {"error": f"값 컬럼 '{value_col}'이 없습니다."}

    try:
        df[time_col] = pd.to_datetime(df[time_col])
    except Exception as exc:
        return {"error": f"날짜 변환 실패: {exc}"}

    daily = df.groupby(df[time_col].dt.date)[value_col].sum().reset_index()
    daily.columns = ["date", "value"]
    daily["date"] = daily["date"].astype(str)
    daily["value"] = daily["value"].round(2)

    peak_row = daily.loc[daily["value"].idxmax()]
    return {
        "daily": daily.to_dict(orient="records"),
        "peak": {"date": peak_row["date"], "value": float(peak_row["value"])},
        "total": round(float(daily["value"].sum()), 2),
        "avg_daily": round(float(daily["value"].mean()), 2),
    }


@tool
def run_outlier(data: list, column: str, method: str = "iqr", sigma: float = 3.0) -> dict:
    """IQR 또는 z-score 기반으로 이상치를 감지합니다.

    Args:
        data: 분석할 데이터 (records 형식).
        column: 이상치를 탐지할 수치 컬럼명.
        method: iqr (기본) | zscore
        sigma: zscore 방식일 때 사용할 표준편차 배수 (기본 3.0). 예: 사용자가 "±5σ" 요청 시 5.0 전달.
    """
    df = pd.DataFrame(data)
    if column not in df.columns:
        return {"error": f"컬럼 '{column}'이 없습니다."}

    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return {"error": f"'{column}' 컬럼에 수치 데이터가 없습니다."}

    if method == "iqr":
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        mask = (df[column] < q1 - 1.5 * iqr) | (df[column] > q3 + 1.5 * iqr)
    else:
        z = (series - series.mean()) / series.std()
        mask = z.abs() > sigma

    outliers = df[mask]
    return {
        "outlier_count": int(len(outliers)),
        "outlier_rate_pct": round(len(outliers) / len(df) * 100, 1),
        "method": method,
        "sigma_used": sigma if method == "zscore" else None,
        "outliers": outliers.head(20).to_dict(orient="records"),
    }


ALL_ANALYSIS_TOOLS = [run_stats, run_trend, run_outlier]
