"""execute_query 툴 — SqlGenerator를 통해 자연어 질문을 SQL로 변환 후 실행."""
from __future__ import annotations

import threading
from typing import Optional

from langchain_core.tools import tool

from d2insight.data_source import meta_loader
from d2insight.report.sql_generator import SqlGenerator


class _DataStore:
    """쿼리 결과 원본을 보관한다.

    결론 생성 시 md_body(Markdown 테이블 + Base64 이미지) 대신
    compact 원본 데이터를 Opus에 전달하기 위해 사용한다.
    """

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
    all_meta = meta_loader.all_metadata()
    if table_name and table_name in all_meta:
        table_metadata = {table_name: all_meta[table_name]}
        # 관련 테이블(부모/자식)도 같이 넣어준다 — 안 그러면 날짜처럼 다른 뷰에 있는 컬럼이
        # 이 테이블엔 없다는 걸 LLM이 몰라서, 있지도 않은 컬럼을 지어내 SQL을 쓰게 된다
        # (예: view_SalesOrderDetail만 주면 OrderDate가 view_SalesOrderHeader에 있다는 걸 몰라
        # 조인 없이 잘못 참조함 — 2026-08-18 오류로 확인됨). d2chat/mcp_agent.py와 동일한 패턴.
        reference = all_meta[table_name].get("reference", {})
        if isinstance(reference, dict):
            child = reference.get("child_table")
            parent = reference.get("parent_table")
            if child and child in all_meta:
                table_metadata[child] = all_meta[child]
            elif parent and parent in all_meta:
                table_metadata[parent] = all_meta[parent]
    else:
        table_metadata = all_meta
    gen = SqlGenerator()
    result = gen.execute_natural_language_query(
        question=question,
        table_name=table_name,
        table_metadata=table_metadata,
    )
    _data_store.add(question, result)
    return result
