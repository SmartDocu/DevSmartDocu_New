"""
query_tool.py — 자연어 → SQL 쿼리 실행 Tool (d2chat · d2insight 공통)

create_query_tool(agent, classifier_fn) 으로 생성한다.
  classifier_fn : 앱별 분류 함수를 주입
    d2chat   → classify_question_and_table  (어떤 DB 테이블을 쿼리할지)
    d2insight → classify_report_intent      (어떤 분석 툴을 실행할지)

visualization_type 판단 방식(2026-08, pr_d2chat에서 이식):
개별 호출마다 detect_visualization_type_with_llm()을 따로 불러 판단하면, 같은 "그래프로
보여주세요" 요청도 도구 호출 시점의 하위 질문 문구에 따라 매번 결과가 흔들릴 수 있었다.
이제는 LLM이 이 도구를 호출하는 시점에 원본 질문을 보고 visualization_type/for_visualization을
직접 지정하게 하고(agent.py의 최상위 판단은 후보가 전부 비어있을 때의 안전망으로만 사용),
그 값을 그대로 신뢰한다.
"""
from __future__ import annotations

import json
import traceback
from typing import Optional, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from d2shared.visualization import detect_suspicious_uniform_ratio

_VALID_VIZ_TYPES = {"table", "chart", "none"}


class QueryInput(BaseModel):
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


def create_query_tool(agent, classifier_fn: Callable) -> StructuredTool:
    """
    query tool 인스턴스 생성.

    Args:
        agent        : MCPAgent 인스턴스 (mcp, llm, tables_metadata 등 보유)
        classifier_fn: 분류 함수 — (question, llm, metadata, log_ctx) → dict
                       반드시 'is_answerable', 'table', 'suggestion', 'reasoning' 키를 포함한 dict 반환
    """

    def execute_query_tool(
        question: str,
        current_date_info: Optional[str] = None,
        for_visualization: bool = True,
        visualization_type: str = "chart",
        chart_type_hint: Optional[str] = None,
    ) -> str:
        try:
            date_info_dict = None
            if current_date_info:
                date_info_dict = json.loads(current_date_info)

            log_ctx = getattr(agent, '_current_log_ctx', None)
            agent.current_question = question

            resolved_viz_type = visualization_type if visualization_type in _VALID_VIZ_TYPES else "chart"
            if for_visualization:
                agent.current_data = None
                agent.current_visualization_type = resolved_viz_type
                agent.current_chart_type = chart_type_hint

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

            if result.get('status') == 'success' and result.get('data') and for_visualization:
                agent.current_data = result['data']

            if isinstance(result, dict):
                result['visualization_type'] = agent.current_visualization_type
                result['chart_type'] = agent.current_chart_type
                result['for_visualization'] = for_visualization
                if result.get('status') == 'success' and result.get('data'):
                    warning = detect_suspicious_uniform_ratio(result['data'])
                    if warning:
                        result['data_quality_warning'] = warning
                        print(f"[data_quality_warning] execute_query: {warning}")

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            # print(f"Tool 실행 오류: {str(e)}")
            traceback.print_exc()
            return json.dumps({
                "status": "error",
                "message": f"Tool 실행 중 오류 발생: {str(e)}",
                "visualization_type": "none",
            }, ensure_ascii=False)

    return StructuredTool(
        name="execute_query",
        description=(
            "자연어 질문을 데이터베이스 쿼리로 변환하여 실행. 데이터 조회, 집계, 통계 분석 등 모든 종류의 질문에 사용. "
            "비교/조언형 질문에서 1차 조회 결과만으로 근거가 부족하면, 부족한 근거를 겨냥한 별도 질문으로 이 도구를 다시 호출해도 됩니다. "
            "이때 근거 보강용 추가 조회는 for_visualization=False로 호출해 표/그래프 데이터가 바뀌지 않도록 하세요."
        ),
        func=execute_query_tool,
        args_schema=QueryInput,
    )
