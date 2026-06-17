"""
query_tool.py — 자연어 → SQL 쿼리 실행 Tool (d2chat · d2insight 공통)

create_query_tool(agent, classifier_fn) 으로 생성한다.
  classifier_fn : 앱별 분류 함수를 주입
    d2chat   → classify_question_and_table  (어떤 DB 테이블을 쿼리할지)
    d2insight → classify_report_intent      (어떤 분석 툴을 실행할지)
"""
from __future__ import annotations

import json
import traceback
from typing import Optional, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from d2shared.visualization import detect_visualization_type_with_llm


class QueryInput(BaseModel):
    question: str = Field(description="사용자의 자연어 질문")
    current_date_info: Optional[str] = Field(
        default=None,
        description="get_current_date 결과 (JSON 문자열)"
    )


def create_query_tool(agent, classifier_fn: Callable) -> StructuredTool:
    """
    query tool 인스턴스 생성.

    Args:
        agent        : MCPAgent 인스턴스 (mcp, llm, tables_metadata 등 보유)
        classifier_fn: 분류 함수 — (question, llm, metadata, log_ctx) → dict
                       반드시 'is_answerable', 'table', 'suggestion', 'reasoning' 키를 포함한 dict 반환
    """

    def execute_query_tool(question: str, current_date_info: Optional[str] = None) -> str:
        try:
            date_info_dict = None
            if current_date_info:
                date_info_dict = json.loads(current_date_info)

            log_ctx = getattr(agent, '_current_log_ctx', None)
            agent.current_question = question
            agent.current_data = None

            viz_result = detect_visualization_type_with_llm(question, agent.llm, log_ctx=log_ctx)
            agent.current_visualization_type = viz_result['visualization_type']
            agent.current_chart_type = viz_result.get('chart_type')

            classification = classifier_fn(question, agent.llm, agent.tables_metadata, log_ctx=log_ctx)

            if not classification['is_answerable']:
                return json.dumps({
                    "status": "not_answerable",
                    "message": classification.get('suggestion') or "해당 질문에 답변할 수 없습니다.",
                    "reasoning": classification.get('reasoning', ''),
                    "visualization_type": agent.current_visualization_type,
                }, ensure_ascii=False)

            table_name = classification['table']
            metadata = {table_name: agent.tables_metadata[table_name]}

            reference = agent.tables_metadata[table_name].get("reference", {})
            if isinstance(reference, dict):
                child = reference.get("child_table")
                parent = reference.get("parent_table")
                if child and child in agent.tables_metadata:
                    metadata[child] = agent.tables_metadata[child]
                elif parent and parent in agent.tables_metadata:
                    metadata[parent] = agent.tables_metadata[parent]

            result = agent.mcp.execute_natural_language_query(
                question=question,
                table_name=table_name,
                model=agent.llm_model,
                table_metadata=metadata,
                current_date_info=date_info_dict,
                log_ctx=log_ctx,
            )

            if result.get('conditions', {}).get('generated_sql'):
                query = result['conditions']['generated_sql']
                agent.current_query = query
                agent.current_queries.append({"question": question, "query": query, "table": table_name})

            if result.get('status') == 'success' and result.get('data'):
                agent.current_data = result['data']

            if isinstance(result, dict):
                result['visualization_type'] = agent.current_visualization_type

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            print(f"Tool 실행 오류: {str(e)}")
            traceback.print_exc()
            return json.dumps({
                "status": "error",
                "message": f"Tool 실행 중 오류 발생: {str(e)}",
                "visualization_type": "none",
            }, ensure_ascii=False)

    return StructuredTool(
        name="execute_query",
        description="자연어 질문을 데이터베이스 쿼리로 변환하여 실행. 데이터 조회, 집계, 통계 분석 등 모든 종류의 질문에 사용",
        func=execute_query_tool,
        args_schema=QueryInput,
    )
