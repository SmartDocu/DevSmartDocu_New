"""execute_excel_query 툴 — 업로드/API로 등록된 데이터셋을 pandas 코드 실행으로 조회.

d2chat/mcp_agent/tools/excel_query_tool.py와 달리 앱 전역에 살아있는 agent 객체가 없으므로
(ReportAgent는 보고서 생성 요청마다 새로 생성되는 인스턴스), session_id/llm을 팩토리 인자로
직접 받는 클로저 패턴을 쓴다.
"""
from __future__ import annotations

import traceback

from langchain_core.tools import tool

from d2insight.report.classifier import classify_question_and_table
from d2insight.report.excel_registry import get_excel_server


def _to_query_tool_shape(excel_result: dict) -> dict:
    """excel_server 응답({status, data, message, conditions, data_type})을
    execute_query 응답({data, columns, row_count, generated_sql, error?})과 동일한 shape으로 재구성한다.

    시스템 프롬프트의 기존 "조회 결과가 비어 있거나 row_count=0이면 섹션을 작성하지 말고
    바로 종료하세요" 지시가 업로드 모드에서도 그대로 작동하려면 row_count가 반드시 있어야 한다.
    """
    status = excel_result.get("status")
    conditions = excel_result.get("conditions") or {}
    generated_sql = conditions.get("generated_sql")

    if status == "success" and excel_result.get("data"):
        rows = excel_result["data"]
        return {
            "data": rows,
            "columns": list(rows[0].keys()) if rows else [],
            "row_count": len(rows),
            "generated_sql": generated_sql,
        }

    return {
        "data": [],
        "columns": [],
        "row_count": 0,
        "generated_sql": generated_sql,
        "error": excel_result.get("message") or "조회 결과가 없습니다.",
    }


def create_excel_query_tool(session_id: str, llm):
    """execute_excel_query 툴 인스턴스 생성.

    Args:
        session_id: 현재 보고서 생성 세션 ID (ReportAgent 인스턴스별로 고정)
        llm: ReportAgent의 self._llm (pandas 코드 생성/데이터셋 분류에 사용)
    """

    @tool
    def execute_excel_query(question: str) -> dict:
        """업로드된 엑셀/CSV/API 데이터셋을 대상으로 자연어 질문을 pandas 연산으로 변환하여 실행합니다.
        SQL을 직접 작성하지 마세요 — 자연어로 분석 목적을 설명하세요.
        반드시 집계 데이터를 요청하세요: "~별 건수/합계/평균" 형태로 질문하세요.
        question에 분석 기간을 반드시 포함하세요.

        Args:
            question: 분석하고 싶은 내용을 자연어로 설명. 분석 기간과 집계 방식을 포함할 것.
        """
        from d2insight.report.tools.query_tool import _data_store

        try:
            excel_server = get_excel_server()
            if not excel_server.has_datasets(session_id):
                return {"data": [], "columns": [], "row_count": 0, "error": "등록된 데이터셋이 없습니다."}

            raw = excel_server.execute_natural_language_query(
                question=question,
                session_id=session_id,
                llm=llm,
                classifier_fn=classify_question_and_table,
            )
            result = _to_query_tool_shape(raw)
            _data_store.add(question, result)
            return result
        except Exception as e:
            traceback.print_exc()
            return {"data": [], "columns": [], "row_count": 0, "error": f"조회 중 오류 발생: {e}"}

    return execute_excel_query
