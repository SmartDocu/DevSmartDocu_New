"""execute_query 툴 — SqlGenerator를 통해 자연어 질문을 SQL로 변환 후 실행."""
from __future__ import annotations

import threading
from typing import Optional

from langchain_core.tools import tool

from d2insight.report import token_tracker
from d2insight.report import meta_loader

_PROVIDER_TO_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5.4-mini",
}


class _DataStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict] = []

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()

    def add(self, question: str, result: dict, max_rows: int = 30) -> None:
        with self._lock:
            if not result.get("data") or not result.get("columns"):
                return
            self._entries.append({
                "question": question,
                "columns": result["columns"],
                "data": result["data"][:max_rows],
                "row_count": result.get("row_count", len(result["data"])),
            })

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(self._entries)


_data_store = _DataStore()


@tool
def execute_query(question: str, table_name: Optional[str] = None) -> dict:
    """분석하고 싶은 내용을 자연어 질문으로 전달하면 SQL을 자동 생성하여 DB에서 데이터를 조회합니다.
    SQL을 직접 작성하지 마세요 — 자연어로 분석 목적을 설명하세요.
    반드시 집계 데이터(GROUP BY + COUNT/SUM/AVG 등)를 요청하세요.

    Args:
        question: 분석하고 싶은 내용을 자연어로 설명. 분석 기간과 집계 방식을 포함할 것.
                  예: '2025년 1월 서버별 오류 발생 건수를 집계해줘'
        table_name: 조회할 뷰 이름 (메타정보에서 선택). 생략하면 전체 뷰 대상.
    """
    from backend.app.config import settings
    from d2shared.sql_generator import SqlGenerator

    all_meta = meta_loader.all_metadata()
    if table_name and table_name in all_meta:
        table_metadata = {table_name: all_meta[table_name]}
    else:
        table_metadata = all_meta

    provider = token_tracker.get_provider()
    model = _PROVIDER_TO_MODEL.get(provider, "claude-haiku-4-5-20251001")
    gen = SqlGenerator(
        connection_url=settings.SUPABASE_DB_URL,
        db_schema=settings.SUPABASE_SCHEMA,
        model=model,
    )
    result = gen.execute_natural_language_query(
        question=question,
        table_name=table_name,
        table_metadata=table_metadata,
        force_aggregate=True,
    )
    _data_store.add(question, result)
    return result
