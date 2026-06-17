"""SqlGenerator — d2shared.MCPServer 위임형 SQL 생성/실행 래퍼.

d2chat과 d2insight가 동일한 SQL 생성 로직(d2shared.mcp_server.MCPServer)을
공유하도록 하고, d2insight 보고서 작성에 필요한 두 가지만 이 클래스에서 추가한다:
  - 집계 강제 규칙(_AGG_RULES)을 extra_rules로 주입해 로그성/대용량 뷰에서
    SELECT * 류의 토큰 폭발을 방지
  - MCPServer의 표준 응답을 ReportAgent 툴(query_tool)이 기대하는
    {data, columns, row_count, truncated, generated_sql} 형태로 재구성
"""
from __future__ import annotations

from typing import Dict, Optional

from d2insight.config import ANTHROPIC_MODELS
from d2insight.data_source.generic_sql import _build_azure_url
from d2shared.mcp_server import MCPServer

_AGG_RULES = (
    "🔥 집계 규칙 (필수):\n"
    "- 반드시 GROUP BY 집계 쿼리 사용 (COUNT/SUM/AVG/MAX/MIN)\n"
    "- SELECT * 또는 개별 행 나열 조회는 절대 금지\n"
    "- 집계 결과는 100행 이내로 제한 (해당 DB 문법의 TOP/LIMIT/FETCH FIRST 사용)"
)

_MAX_ROWS = 500


class SqlGenerator:
    """자연어 질문을 집계 SQL로 변환·실행하는 d2insight 전용 래퍼."""

    def __init__(self, connection_url: Optional[str] = None) -> None:
        self._server = MCPServer(connection_url or _build_azure_url())

    def execute_natural_language_query(
        self,
        question: str,
        table_name: Optional[str] = None,
        table_metadata: Optional[Dict] = None,
    ) -> Dict:
        """자연어 질문을 SQL로 변환·실행하고 query_tool 기대 형태로 반환한다."""
        raw = self._server.execute_natural_language_query(
            question=question,
            table_name=table_name,
            model=ANTHROPIC_MODELS["fast"],
            table_metadata=table_metadata,
            extra_rules=_AGG_RULES,
        )

        generated_sql = (raw.get("conditions") or {}).get("generated_sql", "")

        if raw["status"] == "error":
            error = raw["data"].get("error", raw["message"]) if isinstance(raw["data"], dict) else raw["message"]
            return {
                "error": error,
                "data": [],
                "columns": [],
                "row_count": 0,
                "generated_sql": generated_sql,
            }

        rows = raw["data"] if isinstance(raw["data"], list) else []
        truncated = len(rows) > _MAX_ROWS
        if truncated:
            rows = rows[:_MAX_ROWS]

        return {
            "data": rows,
            "columns": list(rows[0].keys()) if rows else [],
            "row_count": len(rows),
            "truncated": truncated,
            "generated_sql": generated_sql,
        }
