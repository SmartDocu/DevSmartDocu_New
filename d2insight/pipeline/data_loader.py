"""Data loading pipeline: resolves the configured DataSource and builds rolling windows."""
from __future__ import annotations

from datetime import date

import pandas as pd

from d2insight import config


def get_data_source():
    raise ValueError(
        "판매분석 파이프라인은 별도 DB 설정이 필요합니다. "
        "SUPABASE_DB_URL로 대체되지 않습니다."
    )


def get_generic_source(connection_url: str | None = None):
    """범용 뷰/테이블 조회용 SqlGenerator 반환."""
    from backend.app.config import settings
    from d2shared.sql_generator import SqlGenerator
    url = connection_url or settings.SUPABASE_DB_URL
    db_schema = settings.SUPABASE_SCHEMA
    return SqlGenerator(connection_url=url, db_schema=db_schema)


def _parse_month(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    return date(total // 12, (total % 12) + 1, 1)


def rolling_window(target_month: str, months_back: int = 5) -> tuple[date, date]:
    target = _parse_month(target_month)
    start = _add_months(target, -(months_back - 1))
    end = _add_months(target, 1)
    return start, end


def load_monthly_sales(target_month: str, months_back: int = 5) -> pd.DataFrame:
    """매출 전용 파이프라인용 — 별도 DB 설정 없으면 빈 DataFrame 반환."""
    try:
        return get_data_source()
    except Exception:
        return pd.DataFrame()


def load_view_data(
    view_name: str,
    start_date: date | None = None,
    end_date: date | None = None,
    connection_url: str | None = None,
    **kwargs,
) -> pd.DataFrame:
    """범용 뷰/테이블 조회."""
    try:
        src = get_generic_source(connection_url)
        result = src.execute_query(f'SELECT * FROM "{view_name}"')
        if isinstance(result, dict) and "data" in result:
            return pd.DataFrame(result["data"])
        return pd.DataFrame()
    except Exception as e:
        print(f"[data_loader] load_view_data 실패 ({view_name}): {e}")
        return pd.DataFrame()
