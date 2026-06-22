"""범용 SQL DataSource — d2shared.mcp_server 방언 분기 패턴 기반.

지원 DB (d2shared/mcp_server.py 방언 분기와 동일):
  - MSSQL / Azure SQL  → [dbo].[view_name], TOP
  - MySQL / PostgreSQL / SQLite → view_name, LIMIT
  - Oracle             → schema.view_name, FETCH FIRST

연결 방식:
  1. connection_url 직접 전달 (SQLAlchemy URL 문자열)
  2. None 이면 backend.app.config.settings 의 Azure SQL 설정으로 자동 구성
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from d2insight.data_source.base import DataSource, MonthRange
from d2insight.data_source import meta_loader


def _build_azure_url() -> str:
    from d2shared import meta_loader as shared_meta
    url = shared_meta.get_connection_url()
    if not url:
        raise RuntimeError("Supabase에서 DB 연결 URL을 가져오지 못했습니다.")
    return url


def _table_ref(dialect: str, schema: str, view_name: str) -> str:
    """d2shared/mcp_server.py 방언 분기와 동일한 테이블 참조 문자열 생성."""
    if "mssql" in dialect:
        return f"[{schema}].[{view_name}]"
    elif dialect in ("mysql", "postgresql", "sqlite"):
        return view_name          # 스키마 접두어 사용 금지
    elif "oracle" in dialect:
        return f"{schema}.{view_name}"
    else:
        return view_name


def _date_filter_sql(dialect: str, time_col: str) -> str:
    """방언별 날짜 필터 WHERE 절 반환."""
    if "mssql" in dialect:
        return f"WHERE [{time_col}] >= :start AND [{time_col}] < :end"
    else:
        return f"WHERE {time_col} >= :start AND {time_col} < :end"


class GenericSqlSource(DataSource):
    """메타데이터를 참조해 임의의 뷰/테이블을 조회하는 범용 SQL DataSource.

    d2shared/mcp_server.py 의 연결·방언 감지 패턴을 그대로 따른다.
    NL→SQL 변환은 하지 않으며, fetch() 인터페이스만 제공한다.
    """

    def __init__(self, connection_url: str | None = None) -> None:
        url = connection_url or _build_azure_url()
        self._engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"timeout": 30},
        )
        self._dialect: str = self._engine.dialect.name

    # ── 매출 전용 인터페이스 (base 요구사항 충족) ──────────────────────────
    def fetch_monthly_sales(self, months: MonthRange) -> pd.DataFrame:
        raise NotImplementedError(
            "GenericSqlSource 는 fetch() 를 사용하세요. "
            "매출 파이프라인에는 AzureSqlSource 를 사용하세요."
        )

    # ── 범용 조회 ────────────────────────────────────────────────────────
    def fetch(
        self,
        view_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """view_name 에 해당하는 뷰/테이블을 조회한다.

        메타데이터에서 schema 와 default_time_column 을 자동으로 읽고
        방언에 맞는 SQL 문법을 적용한다.
        """
        meta = meta_loader.get(view_name) or {}
        schema: str = meta.get("schema") or "dbo"
        time_col: str = kwargs.get("time_column") or meta.get("default_time_column", "")

        table = _table_ref(self._dialect, schema, view_name)

        if start_date and end_date and time_col:
            where = _date_filter_sql(self._dialect, time_col)
            sql = f"SELECT * FROM {table} {where}"
            params: dict = {"start": start_date, "end": end_date}
        else:
            sql = f"SELECT * FROM {table}"
            params = {}

        return self._execute_query(sql, params)

    def _execute_query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        try:
            with self._engine.connect() as conn:
                conn = conn.execution_options(timeout=30)
                df = pd.read_sql_query(text(sql), conn, params=params or {})
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].astype(str)
            return df
        except Exception as exc:
            raise Exception(f"쿼리 실행 실패: {exc}") from exc

    def ping(self) -> str:
        with self._engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
        return "ok" if row else "fail"
