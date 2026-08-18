"""Data loading pipeline: resolves the configured DataSource and builds rolling windows."""
from __future__ import annotations

from datetime import date

import pandas as pd

import d2insight.config as config
from d2insight.data_source.azure_sql import AzureSqlSource
from d2insight.data_source.base import DataSource, MonthRange


def get_data_source() -> DataSource:
    """매출 전용 파이프라인용 DataSource 반환."""
    src = (config.DATA_SOURCE or "db").lower()
    if src == "db":
        return AzureSqlSource()
    raise ValueError(
        f"Unsupported DATA_SOURCE='{src}'. Supported: 'db' (Phase 7 will add 'csv'/'excel')."
    )


def get_generic_source(connection_url: str | None = None):
    """범용 뷰 조회용 GenericSqlSource 반환.

    connection_url 이 None 이면 backend.app.config.settings 의 Azure SQL 설정 사용.
    다른 DB 연결 시 SQLAlchemy URL 을 직접 전달한다.
    """
    from d2insight.data_source.generic_sql import GenericSqlSource
    return GenericSqlSource(connection_url=connection_url)


def _parse_month(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    return date(total // 12, (total % 12) + 1, 1)


def rolling_window(target_month: str, months_back: int = 5) -> MonthRange:
    """Window of `months_back` months ending inclusively at target_month."""
    target = _parse_month(target_month)
    start = _add_months(target, -(months_back - 1))
    end = _add_months(target, 1)  # exclusive
    return MonthRange(start=start, end=end)


def load_monthly_sales(target_month: str, months_back: int = 5) -> pd.DataFrame:
    """매출 전용 파이프라인용 고정 컬럼 DataFrame 반환."""
    return get_data_source().fetch_monthly_sales(rolling_window(target_month, months_back))


def load_view_data(
    view_name: str,
    start_date: date | None = None,
    end_date: date | None = None,
    connection_url: str | None = None,
    **kwargs,
) -> pd.DataFrame:
    """범용 뷰/테이블 조회 — 로그·기타 데이터 소스에 사용.

    Args:
        view_name:      조회할 뷰 이름 (메타데이터 키와 동일).
        start_date:     시작일 (inclusive). None 이면 전체.
        end_date:       종료일 (exclusive). None 이면 전체.
        connection_url: None 이면 backend.app.config.settings 의 Azure SQL 사용, 다른 DB 는 SQLAlchemy URL 전달.
        **kwargs:       time_column 오버라이드 등 추가 파라미터.

    Returns:
        뷰 네이티브 컬럼 그대로의 DataFrame.
    """
    src = get_generic_source(connection_url)
    return src.fetch(view_name, start_date=start_date, end_date=end_date, **kwargs)
