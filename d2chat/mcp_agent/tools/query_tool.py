"""자연어 → SQL 쿼리 실행 Tool."""
import json
import traceback
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from d2chat.mcp_agent.classifier import classify_question_and_table, _build_available_data_summary
from d2shared.visualization import detect_visualization_type_with_llm


class QueryInput(BaseModel):
    question: str = Field(description="사용자의 자연어 질문")
    current_date_info: Optional[str] = Field(
        default=None,
        description="get_current_date 결과 (JSON 문자열)",
    )


def create_query_tool(agent) -> StructuredTool:

    def execute_query_tool(question: str, current_date_info: Optional[str] = None) -> str:
        try:
            date_info_dict = json.loads(current_date_info) if current_date_info else None
            log_ctx = getattr(agent, "_current_log_ctx", None)

            agent.current_question = question
            agent.current_data = None

            from d2chat.history.llm_logger import log_llm_call as _log_fn
            viz_result = detect_visualization_type_with_llm(
                question, agent.llm, log_ctx=log_ctx, log_fn=_log_fn
            )
            agent.current_visualization_type = viz_result["visualization_type"]
            agent.current_chart_type = viz_result.get("chart_type")

            classification = classify_question_and_table(
                question, agent.llm, agent.tables_metadata, log_ctx=log_ctx
            )

            if not classification["is_answerable"]:
                return json.dumps({
                    "status":             "not_answerable",
                    "message":            classification["suggestion"] or
                                          f"죄송합니다. 현재는 {_build_available_data_summary(agent.tables_metadata)}만 제공 가능합니다.",
                    "reasoning":          classification["reasoning"],
                    "visualization_type": agent.current_visualization_type,
                }, ensure_ascii=False)

            table_name = classification["table"]
            table_metadata = agent.tables_metadata[table_name]
            metadata = {table_name: table_metadata}

            reference = table_metadata.get("reference", {})
            if not isinstance(reference, dict):
                reference = {}
            child_table = reference.get("child_table")
            parent_table = reference.get("parent_table")
            if child_table and child_table in agent.tables_metadata:
                metadata[child_table] = agent.tables_metadata[child_table]
            elif parent_table and parent_table in agent.tables_metadata:
                metadata[parent_table] = agent.tables_metadata[parent_table]

            result = agent.mcp.execute_natural_language_query(
                question=question,
                table_name=table_name,
                table_metadata=metadata,
                current_date_info=date_info_dict,
                log_fn=_log_fn,
                log_ctx=log_ctx,
            )

            if result.get("conditions", {}).get("generated_sql"):
                query = result["conditions"]["generated_sql"]
                agent.current_query = query
                agent.current_queries.append({"question": question, "query": query, "table": table_name})

            if result.get("status") == "success" and result.get("data"):
                agent.current_data = result["data"]

            if isinstance(result, dict):
                result["visualization_type"] = agent.current_visualization_type

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            traceback.print_exc()
            return json.dumps({
                "status":             "error",
                "message":            f"Tool 실행 중 오류 발생: {e}",
                "visualization_type": "none",
            }, ensure_ascii=False)

    return StructuredTool(
        name="execute_query",
        description="자연어 질문을 데이터베이스 쿼리로 변환하여 실행. 데이터 조회, 집계, 통계 분석 등 모든 종류의 질문에 사용",
        func=execute_query_tool,
        args_schema=QueryInput,
    )
