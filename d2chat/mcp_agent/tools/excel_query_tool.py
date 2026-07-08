"""
tools/excel_query_tool.py
업로드된 엑셀/CSV/API 데이터에 대한 자연어 질의 실행 Tool
"""
import json
import traceback
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from d2shared.visualization import detect_visualization_type_with_llm
from d2chat.mcp_agent.classifier import classify_question_and_table


class ExcelQueryInput(BaseModel):
    question: str = Field(description="사용자의 자연어 질문")
    current_date_info: Optional[str] = Field(
        default=None,
        description="get_current_date 결과 (JSON 문자열)"
    )


def create_excel_query_tool(agent) -> StructuredTool:
    """
    execute_excel_query tool 인스턴스 생성
    agent: MCPAgent 인스턴스 (excel_server, llm 참조)
    """

    def execute_excel_query_tool(question: str, current_date_info: Optional[str] = None) -> str:
        try:
            date_info_dict = json.loads(current_date_info) if current_date_info else None
            log_ctx = getattr(agent, '_current_log_ctx', None)
            session_id = getattr(agent, '_current_session_id', None) or 'default'

            agent.current_question = question
            agent.current_data = None

            viz_result = detect_visualization_type_with_llm(question, agent.llm, log_ctx=log_ctx)
            agent.current_visualization_type = viz_result['visualization_type']
            agent.current_chart_type = viz_result.get('chart_type')

            if not agent.excel_server.has_datasets(session_id):
                return json.dumps({
                    "status": "not_answerable",
                    "message": "업로드된 데이터가 없습니다. 먼저 엑셀 또는 CSV 파일을 업로드해주세요.",
                    "visualization_type": "none",
                }, ensure_ascii=False)

            result = agent.excel_server.execute_natural_language_query(
                question=question,
                session_id=session_id,
                llm=agent.llm,
                classifier_fn=classify_question_and_table,
                current_date_info=date_info_dict,
                log_ctx=log_ctx,
            )

            if result.get('conditions', {}).get('generated_sql'):
                code = result['conditions']['generated_sql']
                agent.current_query = code
                agent.current_queries.append({
                    "question": question,
                    "query": code,
                    "table": result['conditions'].get('table_name'),
                })

            if result.get('status') == 'success' and result.get('data'):
                agent.current_data = result.get('data')

            if isinstance(result, dict):
                result['visualization_type'] = agent.current_visualization_type

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            print(f"Tool 실행 오류: {str(e)}")
            traceback.print_exc()
            return json.dumps({
                "status": "error",
                "message": f"Tool 실행 중 오류 발생: {str(e)}",
                "visualization_type": "none"
            }, ensure_ascii=False)

    return StructuredTool(
        name="execute_excel_query",
        description="업로드된 엑셀/CSV 데이터를 대상으로 자연어 질문을 pandas 연산으로 변환하여 실행. 업로드 모드 세션에서 데이터 조회, 집계, 통계 분석 등에 사용",
        func=execute_excel_query_tool,
        args_schema=ExcelQueryInput
    )
