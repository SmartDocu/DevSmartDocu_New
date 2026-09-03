"""
tools/excel_query_tool.py
업로드된 엑셀/CSV/API 데이터에 대한 자연어 질의 실행 Tool
"""
import json
import traceback
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from d2shared.visualization import detect_suspicious_uniform_ratio
from d2shared.table_classifier import classify_question_and_table

_VALID_VIZ_TYPES = {"table", "chart", "none"}


class ExcelQueryInput(BaseModel):
    question: str = Field(description="사용자의 자연어 질문")
    current_date_info: Optional[str] = Field(
        default=None,
        description="get_current_date 결과 (JSON 문자열)"
    )
    for_visualization: bool = Field(
        default=True,
        description=(
            "이 조회 결과를 최종 표/그래프로 그릴 주(主) 데이터로 쓸 것이면 True(기본값). "
            "이미 얻은 결과의 조언/비교 근거를 보강하기 위해 추가로 조회하는 것뿐이라면(예: 비교 대상 전체 데이터 확인) "
            "False로 설정하세요. False로 호출한 결과는 표/그래프에 반영되지 않고 답변 텍스트의 근거로만 사용됩니다."
        )
    )
    visualization_type: str = Field(
        default="chart",
        description=(
            "이 조회 결과를 'table'(표) | 'chart'(그래프) | 'none'(시각화 불필요) 중 무엇으로 보여줄지. "
            "사용자의 원래 요청 문구를 보고 직접 판단하세요 — '표로'/'테이블로'라고 했으면 'table', "
            "'그래프로'/'차트로'/'그려줘' 등 시각적 표현을 요청했으면 'chart'. "
            "사용자가 표와 그래프를 동시에 여러 개 요청했다면, 이 도구를 그 개수만큼 나눠 호출하면서 "
            "호출마다 해당 조회에 맞는 값을 각각 지정하세요. for_visualization=False인 근거 보강 조회에서는 무시됩니다."
        )
    )
    chart_type_hint: Optional[str] = Field(
        default=None,
        description=(
            "visualization_type='chart'일 때, 참고용으로 예상되는 차트 종류(bar/line/pie 등)를 적어도 됩니다. "
            "최종 차트 종류는 실제 조회 결과 데이터를 보고 별도로 정확히 결정되므로, 이 값은 진단용 참고 정보일 뿐입니다."
        )
    )


def create_excel_query_tool(agent) -> StructuredTool:
    """
    execute_excel_query tool 인스턴스 생성
    agent: MCPAgent 인스턴스 (excel_server, llm 참조)
    """

    def execute_excel_query_tool(
        question: str,
        current_date_info: Optional[str] = None,
        for_visualization: bool = True,
        visualization_type: str = "chart",
        chart_type_hint: Optional[str] = None,
    ) -> str:
        try:
            date_info_dict = json.loads(current_date_info) if current_date_info else None
            log_ctx = getattr(agent, '_current_log_ctx', None)
            session_id = getattr(agent, '_current_session_id', None) or 'default'

            agent.current_question = question

            resolved_viz_type = visualization_type if visualization_type in _VALID_VIZ_TYPES else "chart"
            if for_visualization:
                agent.current_data = None
                agent.current_visualization_type = resolved_viz_type
                agent.current_chart_type = chart_type_hint

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

            if result.get('status') == 'success' and result.get('data') and for_visualization:
                agent.current_data = result.get('data')

            if isinstance(result, dict):
                result['visualization_type'] = agent.current_visualization_type
                result['chart_type'] = agent.current_chart_type
                result['for_visualization'] = for_visualization
                if result.get('status') == 'success' and result.get('data'):
                    warning = detect_suspicious_uniform_ratio(result['data'])
                    if warning:
                        result['data_quality_warning'] = warning
                        print(f"[data_quality_warning] execute_excel_query: {warning}")

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            # print(f"Tool 실행 오류: {str(e)}")
            traceback.print_exc()
            return json.dumps({
                "status": "error",
                "message": f"Tool 실행 중 오류 발생: {str(e)}",
                "visualization_type": "none"
            }, ensure_ascii=False)

    return StructuredTool(
        name="execute_excel_query",
        description=(
            "업로드된 엑셀/CSV 데이터를 대상으로 자연어 질문을 pandas 연산으로 변환하여 실행. 업로드 모드 세션에서 데이터 조회, 집계, 통계 분석 등에 사용. "
            "비교/조언형 질문에서 1차 조회 결과만으로 근거가 부족하면 추가로 호출해도 되며, 근거 보강용 추가 조회는 "
            "for_visualization=False로 호출해 표/그래프 데이터가 바뀌지 않도록 하세요."
        ),
        func=execute_excel_query_tool,
        args_schema=ExcelQueryInput
    )
