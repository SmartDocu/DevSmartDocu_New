"""공통 SQLAlchemy DB 엔진 — d2chat/d2insight 공유.

출처: pr_d2chat/mcp_core/mcp_server.py + pr_d2insight/src/data_source/generic_sql.py
"""
from __future__ import annotations

from typing import Optional
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


class DbEngine:
    """SQLAlchemy 엔진 래퍼 — 방언 감지 + 쿼리 실행."""

    def __init__(self, connection_url: str) -> None:
        self._engine: Engine = create_engine(
            connection_url,
            pool_pre_ping=True,
            connect_args={"timeout": 30},
        )
        self._dialect: str = self._engine.dialect.name

    @property
    def dialect(self) -> str:
        return self._dialect

    def execute_query(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """SQL 실행 → DataFrame (Timestamp 컬럼은 str 변환)."""
        try:
            with self._engine.connect() as conn:
                conn = conn.execution_options(timeout=30)
                df = pd.read_sql_query(text(sql), conn, params=params or {})
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].astype(str)
                elif df[col].dtype == "object":
                    df[col] = df[col].apply(
                        lambda x: x.isoformat() if hasattr(x, "isoformat") else x
                    )
            return df
        except Exception as exc:
            raise Exception(f"쿼리 실행 실패: {exc}") from exc

    def ping(self) -> str:
        with self._engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
        return "ok" if row else "fail"
