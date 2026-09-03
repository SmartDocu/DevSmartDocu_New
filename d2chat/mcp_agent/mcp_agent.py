"""
mcp_agent.py
MCP Agent - 핵심 클래스만 포함
"""
import json
import re
import traceback
from typing import Optional, Dict, List

import pandas as pd
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from utilsPrj.ai_chain import build_langchain_llm, get_llm_info
from d2shared.visualization import (
    strip_markdown,
    detect_visualization_type_with_llm,
    dataframe_to_html_table,
    dataframe_to_chart_image,
    decide_chart_type,
    audit_chart_type_mismatch,
    split_by_magnitude,
    split_by_unit,
)
from d2shared.llm_logger import log_llm_call
from d2chat.mcp_agent.tools import create_all_tools
from d2chat.config import TARGET_TURNS, THRESHOLD_TURNS

MAX_VISUALIZATIONS = 3  # 한 답변(말풍선)에 함께 그릴 수 있는 차트/표의 최대 개수

num_to_text = """
**숫자를 한글 화폐 단위(억/조 등)로 쓸 때 - 반드시 지킬 것:**

- 조회 결과에 "{컬럼명}_한글" 형태의 필드가 있으면(예: "판매금액": 68146317, "판매금액_한글": "6,815만원"),
  본문에서 그 금액을 언급할 때 반드시 그 "_한글" 필드의 문자열을 그대로 옮겨 쓰세요.
  절대 원본 숫자(예: 68146317)를 보고 직접 암산해서 억/조 단위로 바꾸지 마세요.
  실제 반복된 사고: 68,146,317원(실제 약 6,815만원)을 "68억 1천만원"으로 100배 부풀려 잘못 표기.
- "_한글" 필드가 없는 숫자(예: 답변 중 직접 계산해서 새로 만든 값)를 한글 단위로 표현해야 한다면,
  콤마를 지우고 자릿수를 직접 센 뒤 단위를 붙이세요. 확신이 안 서면 억/조로 축약하지 말고
  콤마 찍은 원래 숫자("68,146,317원")를 그대로 쓰세요 — 틀린 단위보다 정확한 원 단위가 낫습니다.
  자신이 없으면 format_krw_amount 도구를 호출해서 나온 문자열을 그대로 사용하세요.
"""


class MCPAgent:
    """동적 쿼리 생성 기반 MCP Agent"""

    def __init__(
        self,
        db_connection: str,
        llm_model: str,
        temperature: float = 0,
        tables_metadata: Optional[Dict[str, Dict]] = None,
        rag_server=None,
    ):
        self.current_question = None
        self.current_query = None
        self.current_queries = []
        self.current_visualization_type = None
        self.current_chart_type = None
        self.current_data = None
        self.llm_model = llm_model
        self.rag_server = rag_server
        self._current_log_ctx = None
        self._token_input = 0
        self._token_output = 0
        self._current_session_id = None
        self._current_session_mode = "db"
        self.session_mode: Dict[str, str] = {}

        from d2shared.mcp_server import MCPServer
        self.mcp = MCPServer(db_connection=db_connection)

        from d2shared.excel_server import ExcelServer
        self.excel_server = ExcelServer()

        # LLM 초기화 실패 시 ask() 첫 호출에서 재시도
        try:
            _model, _api_key, _vendor, _, _ = get_llm_info()
            self.llm_model = _model
            self._api_key = _api_key
            self._vendor = _vendor
            self.llm = build_langchain_llm(self._vendor, self._api_key, self.llm_model)
        except Exception as _e:
            # print(f"[MCPAgent] LLM 초기화 실패 (ask() 호출 시 재시도): {_e}")
            self.llm_model = None
            self._api_key = None
            self._vendor = None
            self.llm = None
        self.memory = MemorySaver()
        self.tables_metadata = self._normalize_tables_metadata(tables_metadata or {})
        self.tools = create_all_tools(self)   # ← tools/__init__.py에서 일괄 생성

        self.agent_executor = self._create_agent(use_memory=True)
        self.stateless_executor = self._create_agent(use_memory=False)
        self.session_histories = {}


    def _normalize_tables_metadata(self, meta: Dict[str, Dict]) -> Dict[str, Dict]:
        normalized = {}
        for table, m in meta.items():
            normalized[table] = {
                "schema": m.get("schema", ""),
                "physical_name": m.get("physical_name", ""),
                "logical_name": m.get("logical_name", ""),
                "aliases": m.get("aliases", ""),
                "source_type": m.get("source_type", ""),
                "description": m.get("description", ""),
                "primary_key": m.get("primary_key", ""),
                "grain": m.get("grain", ""),
                "default_time_column": m.get("default_time_column", ""),
                "reference": m.get("reference", ""),
                "purpose": m.get("purpose", ""),
                "query_examples": m.get("query_examples", ""),
                "columns": m.get("columns", {}),
                "query": m.get("query", ""),
            }
        return normalized


    def _create_system_message(self) -> SystemMessage:
        """동적으로 System Message 생성 (세션 모드에 따라 db/external 분기)
        external = 파일 업로드 또는 API 연결로 세션에 등록된 외부 데이터(DataFrame)를 대상으로 하는 모드"""
        mode = self.session_mode.get(self._current_session_id, "db")

        # 프롬프트 맨 앞에 두는 이유: 이 규칙이 style_guide 뒤쪽(중간~후반부)에도 상세히
        # 들어있지만, 대화 이력이 실제 HumanMessage/AIMessage로 그대로 함께 들어가는 구조상
        # "대화를 자연스럽게 이어가려는" LLM의 기본 성향이 후반부 지침보다 강하게 작용해
        # 이전 질문의 시기/브랜드 등 조건이 새 질문에 계속 묻어나오는 문제가 반복됐다.
        # 지침의 위치를 프롬프트 맨 앞으로 옮기면 우선순위가 명확해진다.
        context_independence_rule = """
**⚠️ 가장 먼저 지켜야 할 규칙 — 이전 대화 참조 여부:**
- 사용자의 새 질문에 답할 때, 원칙적으로 이전 대화를 참조하지 않습니다.
- 특히 시기·기간·연도, 브랜드·쇼핑몰·제품 등 조건은 새 질문에 명시적으로 없으면 이전 대화에서 이어받지 않습니다.
- 다만 문맥상 이전 대화와 관련 있음이 명확할 때만(예: "그럼 같은 시기의", "위의 대화 중 'OO' 관련해서", "이 브랜드들은", "앞서 분석한 것에서") 이전 대화의 조건이나 데이터를 참조합니다.
- 관련이 있는지 애매하면 이어받지 말고, 새 질문만을 기준으로 독립적으로 답하세요.
"""

        style_guide = """
**답변 스타일 - 매우 중요:**

1. 자연스러운 대화체 사용
- 마크다운 형식(**굵게**, ##제목, -리스트, 테이블 등)의 문법을 사용하지 않습니다.
- 일반 텍스트로 자연스럽게 작성
- HTML 태그를 절대 답변에 포함하지 마세요 (테이블, 차트는 자동으로 하단에 표시됨)

2. 시각화 요청 판단
- "표로", "테이블로", "그래프로", "차트로" 등 명시적 키워드가 있을 때만 시각화
- **명시적 요청이 없으면 텍스트의 의미를 파악하여 시각화가 필요하면 시각화하여 결과를 보여줍니다.**

3. 문단 나누기 - 매우 중요 (채팅 말풍선에 표시되므로 가독성이 중요합니다):
- 모든 내용을 한 문단에 몰아 쓰지 마세요. 다루는 대상(브랜드/쇼핑몰 등)이나 화제가 바뀌면 반드시 빈 줄로 문단을 나누세요.
- 이건 마크다운이 아닙니다 - 목록 기호(-, *, 1.)나 제목(#)을 쓰지 말라는 것이지, 문단 사이 줄바꿈까지 없애라는 뜻이 아닙니다. 줄바꿈 자체는 자유롭게 사용하세요.
- 기준 예시: (도입/핵심 요약) 한 문단 → (대상1 관련 내용) 한 문단 → (대상2 관련 내용) 한 문단 → (결론/조언) 한 문단. 대상이 여러 개면 대상마다 문단을 나누세요.

4. 텍스트 답변 형식
- 중요 쟁점 한두 개를 간략히 기술 (시각화 요청 없을 때)

5. 시각화 답변 형식 (표/그래프 요청 있을 때)
- 결과가 1건인 경우 텍스트로만 답변
- 사용자가 서로 다른 대상/관점의 표나 그래프를 여러 개 요청하면(예: "차트도 보여주고 표로도 보여줘", "A 그래프와 B 그래프를 각각") {query_tool}을 그 개수만큼 각각 for_visualization=True로 호출하세요. 한 턴에 최대 3개까지 함께 표시할 수 있습니다. 단순히 하나의 표/그래프면 1번만 호출하세요.
- {query_tool}을 for_visualization=True로 호출할 때는 반드시 visualization_type 파라미터에 그 조회에 맞는 값('table' 또는 'chart')을 직접 지정하세요. 사용자가 "표로"/"테이블로" 요청한 조회는 'table', "그래프로"/"차트로" 요청한 조회는 'chart'로 지정합니다. "표도 보여주고 그래프도 보여줘"처럼 혼합 요청이면, 두 번 호출하면서 각 호출의 visualization_type을 서로 다르게(하나는 'table', 하나는 'chart') 지정하세요.
- 대상(브랜드/쇼핑몰/그룹 등)별로 여러 지표(예: 매출·수수료·배송비, 매출·수수료율·배송비율)를 비교하거나 구성을 보여주는 그래프가 필요하면, 지표마다 따로 조회하지 마세요. 지표별로 총계 하나씩 따로 조회하면 지표 개수만큼 차트가 쪼개져서 나옵니다. 대상을 행으로, 필요한 지표를 모두 열로 포함하는 하나의 조회로 {query_tool}을 1회만 for_visualization=True로 호출하고, 그 결과 하나로 그래프를 그리세요.
- 여러 대상(브랜드/쇼핑몰 등)의 추이를 비교하는 선그래프가 필요하면, 대상마다 {query_tool}을 따로 호출하지 마세요. 대상별로 나눠 조회하면 대상 수만큼 차트가 쪼개지거나 하나로 합쳐지지 않습니다. 하나의 조회로 모든 대상의 기간별 값을 함께 가져와(예: 행=기간, 열=대상별 값) 한 번만 시각화하세요.
- 금액 지표와 비율(%) 지표(예: 매출액과 수수료율)를 함께 비교해야 하면, 두 지표를 따로 조회해서 차트 두 개로 나누지 마세요. 하나의 조회에 두 지표를 모두 열로 포함시켜 한 번만 호출하면 이중축 그래프로 자동 표시됩니다.

**복합 질문(비교/원인분석/조언) 처리 - 매우 중요:**
- 질문이 단순 조회가 아니라 "조언해줘", "어떤 게 나을지", "왜 그런지", "비교해줘"처럼 판단·추천을 요구하면:
  1. 먼저 그 판단에 실제로 어떤 데이터가 근거로 필요한지 생각합니다 (예: "수수료 싼 쇼핑몰로 옮기는 게 나을지" → 해당 브랜드 데이터뿐 아니라 다른 쇼핑몰들의 수수료율 데이터도 필요).
  2. 조회 결과에서 평균과 크게 다른 값, 추세 변화, 예외 케이스를 먼저 찾으세요. 단순히 정렬·나열만 하지 말고 "왜 이 값이 눈에 띄는지"를 해석한 뒤 조언에 반영하세요.
  3. 1차 {query_tool} 결과가 그 근거를 포함하지 않으면, 답변을 만들기 전에 같은 턴 안에서 {query_tool}을 추가로 호출해 부족한 근거 데이터를 더 조회하세요. 질문 1개당 조회 1회로 제한하지 마세요.
  4. 이때 사용자가 보고 싶어하는 표/그래프의 대상(예: 특정 5개 브랜드)을 조회하는 호출만 for_visualization=True(기본값)로 두고, 그 근거를 보강하기 위한 추가 조회(예: 전체 비교 대상 데이터)는 반드시 for_visualization=False로 호출하세요. 그렇지 않으면 사용자가 요청한 것과 다른 데이터가 그래프로 표시됩니다.
  5. 여러 대상(브랜드/그룹 등)을 다루는 질문이면, 대상마다 상황이 다를 수 있으므로 하나의 결론으로 뭉뚱그리지 말고 대상별로 실제 조회한 수치에 근거해 다르게 답하세요.
  6. 조언은 추상적으로 말하지 말고, 조회한 구체적 수치를 근거로 제시하세요. 조언 뒤에는 예상 효과(수치 또는 방향성)를 함께 제시하세요.

**데이터 근거와 일반 지식을 구분하기 - 매우 중요:**
- 프로모션 전략, 고객 성향, 채널 이미지처럼 우리 데이터베이스에 없는 내용(고객 행동/심리 데이터는 테이블에 없음)을 조언에 포함해야 한다면, 그것이 조회 데이터가 아니라 일반적인 가정/상식이라는 것을 문장에서 드러내세요 (예: "일반적으로 ~하는 경향이 있어" 같은 표현). 조회한 데이터에서 나온 사실인 것처럼 단정적으로 말하지 마세요.
- 특히 "이 채널 고객은 ~한 성향이다"처럼 데이터베이스에 없는 고객 특성을 마치 조회 결과인 양 단정하지 마세요.
- 조언은 최대한 실제로 조회한 수치(예: 어느 채널의 감소율이 가장 큰지, 수수료율이 얼마인지)에 근거하고, 근거 없는 일반론은 꼭 필요한 경우에만 짧게 덧붙이세요.

**기간 처리 규칙:**
1. 질문에 기간이 명시된 경우: 해당 기간만 사용하세요.
2. 질문에 기간이 명시되지 않은 경우: 데이터 전체 기간을 기준으로 분석하고, 답변 첫 줄에 "전체 기간(YYYY-MM ~ YYYY-MM) 기준으로 분석했습니다"라고 명시하세요.
3. 이전 대화의 기간을 자동으로 이어받지 마세요. 각 질문은 독립적으로 기간을 판단합니다. 단, 사용자가 "앞의 분석에서", "위 결과 기준으로"처럼 명시적으로 이전 분석을 참조하면 그 기간을 이어받아도 됩니다.
4. "요즘", "최근", "올해" 같은 상대적 표현은 데이터에서 가장 최근 기간으로 처리하고, "데이터 기준 최근 기간(YYYY-MM ~ YYYY-MM)으로 분석했습니다"라고 명시하세요.
5. 기간이 모호하여 판단이 어려우면 추측하지 말고 사용자에게 확인하세요 (예: "비교할 기간을 알려주시겠어요? (예: 2025년 전체 vs 2026년 전체)").

**이전 대화 데이터 처리:**
- 이전 대화에 `<q_data>` 블록이 있으면 그것은 시스템이 자동 삽입한 쿼리 결과 메타데이터입니다.
- `<q_data>...</q_data>` 블록을 절대 답변에 출력하지 마세요.
- 데이터 조회 결과 JSON 배열을 답변 텍스트에 직접 포함하지 마세요.
- `<q_data>` 데이터를 새 질문의 답변 데이터로 재사용하지 마세요. 항상 {query_tool}을 새로 호출해 최신 데이터를 조회하세요.
- 각 질문은 원칙적으로 독립적으로 처리하세요. 새 질문에 명시적으로 언급되지 않은 이전 질문의 조건(연도, 브랜드, 쇼핑몰, 기간 등 필터)을 새 질문에 임의로 이어붙이지 마세요. 새 질문이 특정 브랜드/연도 등을 언급하지 않으면 전체 데이터를 대상으로 조회하세요. 새 질문이 이전 질문과 다른 주제/범위를 다루면(예: 이전엔 특정 브랜드, 이번엔 "전체") 이전 조건은 완전히 무시하세요.
- "위에서", "앞에서", "방금 분석한", "그 결과에서", "이 브랜드들", "저 채널들"처럼 이전 결과를 가리키는 표현이 있을 때만 이전 맥락을 참조하세요. 이전 맥락을 이어받을 때는 답변 시작 부분에 "앞서 분석한 OO 기준으로 이어서 분석합니다"처럼 명시하세요.
- 이전 대화 없이 "이 브랜드들에 대해", "저 채널들은" 처럼 무엇을 가리키는지 알 수 없는 지시 표현이 나오면, 추측하지 말고 "어떤 브랜드(또는 채널)를 말씀하시는 건가요?"처럼 사용자에게 확인하세요.

**"전체", "비중", "%를 차지" 계산 시 - 매우 중요:**
- 이미 조회한 결과(예: 상위 5개, 하위 5개)의 합을 "전체"라고 착각하지 마세요. "전체"라는 표현을 답변에 쓰려면, 필터/그룹화 없이 전체 대상을 통째로 집계하는 조회를 별도로(for_visualization=False) 실행해서 확인한 값만 "전체"로 사용하세요.
- 비중(%)을 계산할 때는 분자와 분모가 서로 같은 조회 범위에서 나온 값인지 반드시 확인한 뒤 계산하세요.
- 비중(%)만으로 심각도나 우선순위를 단정하지 마세요. 대상마다 규모(매출액 등) 차이가 크면, 비중이 높아도 절대 금액은 작고, 비중이 낮아도 절대 금액은 클 수 있습니다. 여러 대상의 비중을 비교하는 답변에는 항상 각 대상의 절대 금액도 함께 언급해서, 비중만 보고 실제 영향 크기를 오해하지 않게 하세요(예: "A는 비중이 10.8%지만 배송비 자체는 225만원, B는 비중이 8.2%지만 배송비는 2억 5천만원으로 A의 100배가 넘습니다" 처럼 비율과 절대값을 함께 제시).

**도구 결과의 data_quality_warning 처리:**
- {query_tool} 결과에 `data_quality_warning` 필드가 있으면, 계산이 잘못됐을 가능성이 있다는 신호입니다. 그 경고를 무시하지 말고, 조회 조건을 재확인하거나 다시 조회한 뒤 답변하세요. 원인을 못 찾으면 수치에 불확실성이 있다는 점을 답변에 솔직히 밝히세요.

**도구 결과의 dataset_context 활용:**
- {query_tool} 결과에 `dataset_context`(description/grain)가 있으면, 이 데이터가 무엇에 대한 것이고 1행이 무엇을 의미하는지 참고해서 집계 결과를 해석하세요. 예를 들어 grain이 "쇼핑몰×브랜드×월당 1행"이면, 여러 행을 단순 합산할 때 중복 집계가 아닌지 이 정보로 확인하세요.

**절대 하지 말아야 할 것:**
- 마크다운 문법 사용 (**굵게**, ##제목, -리스트, |표|)
- 불필요하게 표나 그래프 자동 생성
- `<q_data>` 태그 또는 JSON 데이터 배열을 답변에 출력
- '완벽합니다', '성공했습니다' 같은 자기 평가/감탄 표현 사용 (시각화 요청 여부와 무관하게 항상 금지)
- 지금 무엇을 하고 있는지/하려는지 실황중계하듯 서술 ("이제 ~하겠습니다", "먼저 ~보여드리겠습니다", "다음으로 ~살펴보겠습니다" 등). 도구 호출 과정을 설명하지 말고, 곧바로 결과와 결론만 답하세요.
- 여러 대상을 다룰 때 항목마다 같은 문장 틀("A는 ~합니다. B는 ~합니다.")을 기계적으로 반복하기. 대상별로 가장 중요한 결론을 먼저 말하고, 근거는 필요한 만큼만 간결하게 붙이세요.
- 10억 이상인 숫자를 "OO억원"/"OO조원"처럼 직접 암산해서 답변 문장에 쓰기. 이 규칙은 중요하니 숫자를 한글로 변환 후 꼭 확인해주세요.
- "~할 수 있습니다", "~을 고려해보세요" 수준의 추상적인 제안만 하고 끝내기. 구체적으로 무엇을, 얼마나 하라는 것인지까지 말하세요.
- 조회 결과에 없는 수치를 추정해서 사실인 것처럼 제시하기. 근거가 없으면 없다고 말하세요.
- 기간이 불명확한데 임의로 특정 기간을 가정하고 진행하기 (위 "기간 처리 규칙" 참고).
- 수치만 나열하고 해석·조언 없이 답변을 끝내기.
"""

        if mode == "external":
            datasets = self.excel_server.get_session_datasets(self._current_session_id)
            available_data_list = [
                f"- {name} ({info.get('description', name)}): {info.get('purpose', '업로드된 데이터 조회')}"
                for name, info in datasets.items()
            ]
            available_data_text = '\n'.join(available_data_list) or "(등록된 데이터 없음)"

            content = f"""{context_independence_rule}
당신은 데이터 분석 전문 AI 어시스턴트입니다.

이 세션은 사용자가 업로드하거나 외부 API로 가져온 데이터를 대상으로 답변하는 모드입니다. 데이터베이스 조회는 사용하지 않습니다.

**현재 등록된 데이터셋:** {', '.join(datasets.keys()) or '없음'}

**제공 가능한 정보:**
{available_data_text}

**사용 가능한 도구:**
1. get_current_date: 현재 날짜/시간 조회
2. execute_excel_query: 등록된 데이터 조회/집계/분석

**핵심 규칙:**
- 데이터 관련 질문 → execute_excel_query 사용
- 상대적 날짜("오늘", "어제" 등)가 있으면 먼저 get_current_date 호출
- 새 질문이 데이터 조회/집계를 요청하면 이전 대화의 <q_data> 데이터와 무관하게 반드시 execute_excel_query를 새로 호출

**질문 종류 구분 — 중요:**
- "데이터 관련 질문"이란 데이터의 실제 값·수치·집계를 묻는 질문입니다 (예: "오류율은?", "매출 얼마?").
- 반면 이전 답변/그래프의 표현 방식에 대한 피드백이나 지적, "왜 그렇게 했냐", "이렇게 그려달라" 같은 요청, 시스템 사용법에 대한 질문은 데이터 조회 질문이 **아닙니다**. 이런 질문에는 execute_excel_query를 억지로 호출할 필요 없이, 사용자의 말을 이해하고 대화로 직접 답변하세요.
- 이런 메타 질문에 대해 "조회된 데이터에 없어서 답변할 수 없습니다" 같은 회피성 답변을 하지 마세요 — 애초에 데이터에서 찾을 내용이 아닙니다.

**요청한 것만 정확히 — 중요:**
- 사용자가 특정 지표 하나만 요청했다면(예: "오류율만 그래프로") 그 지표만 보여주세요. 참고가 될 것 같다는 이유로 요청하지 않은 지표(예: 오류 건수)를 임의로 추가하지 마세요.

**환각 금지 — 절대 규칙:**
- 데이터 관련 질문에는 반드시 execute_excel_query를 호출하고, 그 결과에 실제로 있는 값만 답변에 사용하세요.
- execute_excel_query를 호출하지 않았거나, 호출 결과에 데이터가 없거나 오류인 경우, 절대로 임의의 수치·연도·항목을 지어내지 마세요.
- 이 경우 "현재 등록된 데이터로는 답변할 수 없습니다" 또는 "해당 데이터를 찾을 수 없습니다"처럼 모른다고 명확히 답변하세요. 그럴듯하게 지어낸 답변은 심각한 문제를 일으킵니다.
- 단, 이 규칙은 위 "데이터 관련 질문"에만 적용됩니다. 메타 질문/피드백까지 이 규칙으로 회피하지 마세요.
- {num_to_text}
""" + style_guide.replace("{query_tool}", "execute_excel_query")
        else:
            available_data_list = [
                f"- {table_name} ({info.get('description', table_name)}): {info.get('purpose', '데이터 저장')}"
                for table_name, info in self.tables_metadata.items()
            ]
            available_data_text = '\n'.join(available_data_list)

            content = f"""{context_independence_rule}
당신은 데이터 분석 전문 AI 어시스턴트입니다.

**현재 접근 가능한 데이터베이스 테이블:**
{', '.join(self.tables_metadata.keys())}

**제공 가능한 정보:**
{available_data_text}

**사용 가능한 도구:**
1. get_current_date: 현재 날짜/시간 조회
2. execute_query: 데이터베이스 쿼리 실행
3. search_rag: 내부 문서 검색 (규정/지침/SOP/법률 관련)
4. format_krw_amount: 숫자를 억/조 등 한글 화폐 단위로 정확하게 변환

**핵심 규칙:**
- 데이터 수치 관련 질문 → execute_query 사용
- 규정/지침/매뉴얼/법률 관련 질문 → search_rag 사용
- 상대적 날짜("오늘", "어제" 등)가 있으면 먼저 get_current_date 호출
- 새 질문이 데이터 조회/집계를 요청하면 이전 대화의 <q_data> 데이터와 무관하게 반드시 execute_query를 새로 호출

**질문 종류 구분 — 중요:**
- "데이터 수치 관련 질문"이란 데이터의 실제 값·수치·집계를 묻는 질문입니다 (예: "오류 건수는?", "매출 얼마?").
- 반면 이전 답변/그래프의 표현 방식에 대한 피드백이나 지적, "왜 그렇게 했냐", "이렇게 그려달라" 같은 요청, 시스템 사용법에 대한 질문은 데이터 조회 질문이 **아닙니다**. 이런 질문에는 execute_query를 억지로 호출할 필요 없이, 사용자의 말을 이해하고 대화로 직접 답변하세요.
- 이런 메타 질문에 대해 "조회된 데이터에 없어서 답변할 수 없습니다" 같은 회피성 답변을 하지 마세요 — 애초에 데이터에서 찾을 내용이 아닙니다.

**요청한 것만 정확히 — 중요:**
- 사용자가 특정 지표 하나만 요청했다면(예: "오류율만 그래프로") 그 지표만 보여주세요. 참고가 될 것 같다는 이유로 요청하지 않은 지표를 임의로 추가하지 마세요.

**환각 금지 — 절대 규칙:**
- 데이터 수치 관련 질문에는 반드시 execute_query를 호출하고, 그 결과에 실제로 있는 값만 답변에 사용하세요.
- execute_query를 호출하지 않았거나, 호출 결과에 데이터가 없거나 오류인 경우, 절대로 임의의 수치·연도·항목을 지어내지 마세요.
- 이 경우 "현재 데이터베이스로는 답변할 수 없습니다" 또는 "해당 데이터를 찾을 수 없습니다"처럼 모른다고 명확히 답변하세요. 그럴듯하게 지어낸 답변은 심각한 문제를 일으킵니다.
- 단, 이 규칙은 위 "데이터 수치 관련 질문"에만 적용됩니다. 메타 질문/피드백까지 이 규칙으로 회피하지 마세요.
- {num_to_text}
""" + style_guide.replace("{query_tool}", "execute_query")

        # 프롬프트 캐싱(Anthropic 전용): 시스템 프롬프트(테이블 메타데이터 포함)는 세션 모드가
        # 같으면 내용이 거의 항상 동일하므로 캐시 대상으로 지정한다. langchain_anthropic은
        # content를 블록 리스트로 주고 그 블록에 cache_control을 붙여야 캐시가 걸린다(원본
        # Anthropic SDK의 top-level 자동 캐싱과 다름). 다른 벤더(OpenAI/Google)는 이 필드를
        # 인식하지 못하므로 일반 문자열 content로 그대로 둔다.
        if self._vendor == "Anthropic":
            return SystemMessage(content=[
                {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
            ])
        return SystemMessage(content=content)


    def _create_agent(self, use_memory=False):
        """Agent 생성"""
        tool_node = ToolNode(self.tools)

        def call_model(state: MessagesState, config=None):
            from datetime import datetime
            system_message = self._create_system_message()
            messages = [system_message] + state["messages"]
            start = datetime.now()
            response = self.llm.bind_tools(self.tools).invoke(messages)
            end = datetime.now()
            usage = getattr(response, 'usage_metadata', None) or {}
            in_tok = usage.get('input_tokens', 0)
            out_tok = usage.get('output_tokens', 0)
            self._token_input += in_tok
            self._token_output += out_tok
            # 캐시 히트율 모니터링(Anthropic 전용): response_metadata.usage에 원본 필드명
            # (cache_creation_input_tokens / cache_read_input_tokens)이 그대로 들어있음.
            raw_usage = (getattr(response, 'response_metadata', None) or {}).get('usage') or {}
            cache_read = raw_usage.get('cache_read_input_tokens', 0)
            cache_write = raw_usage.get('cache_creation_input_tokens', 0)
            if cache_read or cache_write:
                print(f"[CACHE] read={cache_read} write={cache_write} "
                      f"(read는 정가의 0.1배, write는 1.25배 과금 - read가 클수록 절감)")
            log_llm_call(
                log_ctx=self._current_log_ctx,
                stepnm='agent',
                steptitle='에이전트 응답',
                llmmodelnm=self.llm_model,
                inputtoken=in_tok,
                outputtoken=out_tok,
                is_success=True,
                startdts=start,
                enddts=end,
            )
            return {"messages": [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)
        workflow.add_edge(START, "agent")

        def should_continue(state: MessagesState):
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END

        workflow.add_conditional_edges("agent", should_continue, ["tools", END])
        workflow.add_edge("tools", "agent")

        return workflow.compile(checkpointer=self.memory) if use_memory else workflow.compile()


    # ========================================
    # 세션 관리
    # ========================================

    def get_session_history(self, session_id: str) -> List[Dict]:
        return self.session_histories.get(session_id, [])

    def add_to_history(self, session_id: str, question: str, answer: str, query: str = None):
        if session_id not in self.session_histories:
            self.session_histories[session_id] = []
        self.session_histories[session_id].append({"question": question, "answer": answer})

    def clear_session_history(self, session_id: str):
        if session_id in self.session_histories:
            self.session_histories[session_id] = []

    def trim_session_history(self, session_id: str, target: int = TARGET_TURNS, threshold: int = THRESHOLD_TURNS):
        """버퍼 트림: threshold를 넘기 전까지는 자르지 않고 계속 누적하다가, 넘는 순간
        한 번에 target 턴만 남긴다.
        (매 턴 target으로 슬라이딩하면 프롬프트 캐싱의 히스토리 시작 지점이 매 턴 바뀌어
        캐시가 계속 무효화되므로, 트림을 threshold 시점 1번으로 몰아서 캐시 유지 구간을 늘린다.
        OpenAI/Google 등 캐시 미지원 벤더에서도 트림 자체는 안전하게 동작한다.)"""
        if session_id in self.session_histories:
            history = self.session_histories[session_id]
            if len(history) > threshold:
                print(f"[TRIM] session={session_id}: {len(history)}턴 → {target}턴으로 정리 "
                      f"(threshold={threshold} 초과)")
                self.session_histories[session_id] = history[-target:]


    def _resolve_llm(self, log_ctx: dict = None) -> None:
        """LLM 선택 우선순위(프로젝트→테넌트→기본값)에 따라 self.llm을 초기화/갱신한다.
        ask()와 register_excel_dataset() 양쪽에서 공통으로 사용."""
        _project_id = (log_ctx or {}).get("project_id")
        _tenant_id = (log_ctx or {}).get("tenant_id")
        _user_uid = (log_ctx or {}).get("creator")
        _account_uid = (log_ctx or {}).get("account_uid")
        _model, _api_key, _vendor, _is_customeraikey, _resolved_account_uid = get_llm_info(
            project_id=_project_id, tenant_id=_tenant_id,
            user_uid=_user_uid, account_uid=_account_uid, service_code="Ch",
        )
        self.llm_model = _model
        self._api_key = _api_key
        self._vendor = _vendor
        self.llm = build_langchain_llm(_vendor, _api_key, _model)

        # log_ctx는 이후 모든 log_llm_call(log_ctx=self._current_log_ctx, ...) 호출에서 재사용됨
        if log_ctx is not None:
            log_ctx["is_customeraikey"] = _is_customeraikey
            if not log_ctx.get("account_uid"):
                log_ctx["account_uid"] = _resolved_account_uid


    def _answer_from_data(self, question: str, data: List[Dict], log_ctx: dict = None) -> str:
        """환각 방지: 도구를 거치지 않고 생성된 최초 답변은 근거가 없으므로 폐기하고,
        강제로 조회한 실제 데이터만 근거로 답변 문장을 새로 생성한다."""
        from datetime import datetime
        preview = json.dumps(data[:50], ensure_ascii=False, default=str)
        prompt = f"""다음은 사용자 질문에 대해 실제로 조회한 데이터입니다.
이 데이터에 있는 값만 사용해서 질문에 자연스러운 한국어 문장으로 답변하세요.
데이터에 없는 수치·연도·항목을 절대 추가하거나 지어내지 마세요. 마크다운 문법을 사용하지 마세요.

질문: {question}

조회된 데이터(JSON, 최대 50건): {preview}

답변:"""
        start = datetime.now()
        response = self.llm.invoke(prompt)
        end = datetime.now()
        usage = getattr(response, 'usage_metadata', None) or {}
        log_llm_call(
            log_ctx=log_ctx,
            stepnm='force_ground_answer',
            steptitle='실데이터 기반 답변 재생성 (환각 방지)',
            llmmodelnm=self.llm_model,
            inputtoken=usage.get('input_tokens', 0),
            outputtoken=usage.get('output_tokens', 0),
            is_success=True,
            startdts=start,
            enddts=end,
        )
        return strip_markdown(response.content.strip())


    def register_excel_dataset(
        self, session_id: str, dataset_key: str, df: pd.DataFrame,
        filename: str, sheet_name: Optional[str] = None, log_ctx: dict = None,
    ):
        """업로드된 파일 또는 API로 가져온 DataFrame을 세션에 등록하고,
        해당 세션을 external(외부 데이터) 모드로 전환한다."""
        self._current_log_ctx = log_ctx
        self._resolve_llm(log_ctx)

        key, metadata = self.excel_server.register_dataset(
            session_id=session_id,
            dataset_key=dataset_key,
            df=df,
            filename=filename,
            sheet_name=sheet_name,
            llm=self.llm,
            log_ctx=log_ctx,
        )
        self.session_mode[session_id] = "external"
        return key, metadata


    # ========================================
    # 메인 질문 처리
    # ========================================

    def ask(self, question: str, session_id: str = "default", max_retries: int = 2, log_ctx: dict = None) -> Dict:
        last_error = None
        self._current_log_ctx = log_ctx
        self._current_session_id = session_id
        self._current_session_mode = self.session_mode.get(session_id, "db")
        self._token_input = 0
        self._token_output = 0

        self._resolve_llm(log_ctx)

        for attempt in range(1, max_retries + 1):
            try:
                current_query = None
                current_queries = []
                current_visualization_type = None

                executor = self.stateless_executor
                config = {"recursion_limit": 30}

                history = self.get_session_history(session_id)
                history_messages = []
                for h in history:
                    history_messages.append(HumanMessage(content=h["question"]))
                    history_messages.append(AIMessage(content=h["answer"]))

                # 프롬프트 캐싱(Anthropic 전용) breakpoint: 히스토리의 마지막 메시지에
                # cache_control을 붙인다. 턴이 진행될수록 "마지막 메시지"가 자연히 뒤로
                # 이동하므로, 매 턴 여기서 다시 계산해서 붙이면 캐시 지점이 그때그때 최신
                # 히스토리 끝으로 이동하는 효과가 난다 (신규 질문 자체에는 붙이지 않음).
                if history_messages and self._vendor == "Anthropic":
                    last_hist_msg = history_messages[-1]
                    last_hist_msg.content = [
                        {"type": "text", "text": last_hist_msg.content, "cache_control": {"type": "ephemeral"}}
                    ]

                input_messages = history_messages + [HumanMessage(content=question)]

                # print(f"\n{'='*60}")
                # print(f"[LLM 입력] 총 메시지 수: {len(input_messages)}")
                result = executor.invoke({"messages": input_messages}, config=config)
                for _m in result["messages"]:
                    if type(_m).__name__ == 'ToolMessage' and getattr(_m, 'name', None) in ('execute_query', 'execute_excel_query'):
                        print(f"[TOOL 결과] {_m.name}: {_m.content[:500]}")
                # print(f"{'='*60}\n")

                answer_text = strip_markdown(result["messages"][-1].content)
                answer_text = re.sub(r'<q_data>.*?</q_data>', '', answer_text, flags=re.DOTALL).strip()

                # for_visualization=True로 호출된 결과만 시각화 후보로 모은다 (근거 보강용 추가
                # 조회는 for_visualization=False라 제외됨). 한 턴에 최대 MAX_VISUALIZATIONS개까지
                # 차트/표를 함께 그릴 수 있다 (예: 차트1, 차트2, 표1).
                viz_candidates = []
                any_tool_called = False
                for msg in result["messages"]:
                    if type(msg).__name__ == 'ToolMessage' and getattr(msg, 'name', None) in ('execute_query', 'execute_excel_query'):
                        any_tool_called = True
                        try:
                            tool_result = json.loads(msg.content)
                            is_for_viz = tool_result.get('for_visualization', True)
                            query = tool_result.get('conditions', {}).get('generated_sql')
                            if query:
                                current_queries.append({"question": question, "query": query})
                            if (is_for_viz and tool_result.get('status') == 'success' and tool_result.get('data')
                                    and len(viz_candidates) < MAX_VISUALIZATIONS):
                                viz_candidates.append({
                                    "data": tool_result['data'],
                                    "visualization_type": tool_result.get('visualization_type') or 'none',
                                    "chart_type": tool_result.get('chart_type'),
                                    "sub_question": tool_result.get('conditions', {}).get('question') or question,
                                    "query": query,
                                })
                        except Exception as e:
                            # print(f"[WARN] tool result 파싱 오류: {e}")
                            pass

                viz_result = detect_visualization_type_with_llm(question, self.llm, log_ctx=log_ctx)
                current_visualization_type = viz_result['visualization_type']

                # 각 execute_query/execute_excel_query 호출은 이제 LLM이 그 조회 시점에 원본 질문
                # 맥락을 보고 직접 지정한 visualization_type을 그대로 갖고 있다. 예전처럼 최상위
                # 판단으로 모든 후보를 일괄 override하지 않는다 — 그러면 "표도 보여주고 그래프도
                # 보여줘" 같은 혼합 요청에서 한쪽이 다른 쪽으로 덮여써진다. 최상위 판단은 안전망으로만
                # 쓴다: 후보가 있는데 전부 'none'으로 비어있고 최상위 판단이 table/chart이면 그때만 적용.
                if (viz_candidates and all(c["visualization_type"] == "none" for c in viz_candidates)
                        and current_visualization_type in ("table", "chart")):
                    for _c in viz_candidates:
                        _c["visualization_type"] = current_visualization_type

                # 환각 방지 안전장치: LLM이 도구(execute_query/execute_excel_query)를 단 한 번도
                # 호출하지 않은 경우, 시각화 요청 여부와 무관하게 항상 데이터 질문인지 판별해 직접
                # 조회를 강제 실행한다. 이 경로로 얻은 답변은 최초 LLM 답변(근거 없이 생성됐을 수
                # 있음)을 버리고 실제 데이터만 근거로 _answer_from_data()에서 새로 생성한다.
                if not any_tool_called:
                    from d2shared.table_classifier import classify_question_and_table
                    direct_result = None
                    try:
                        if self._current_session_mode == "external":
                            if self.excel_server.has_datasets(session_id):
                                direct_result = self.excel_server.execute_natural_language_query(
                                    question=question,
                                    session_id=session_id,
                                    llm=self.llm,
                                    classifier_fn=classify_question_and_table,
                                    current_date_info=None,
                                    log_ctx=log_ctx,
                                )
                            else:
                                direct_result = {
                                    "status": "no_dataset",
                                    "message": "등록된 데이터가 없습니다. 먼저 파일을 업로드하거나 API를 연결해주세요.",
                                    "conditions": {},
                                }
                        else:
                            classification = classify_question_and_table(question, self.llm, self.tables_metadata, log_ctx=log_ctx)
                            if classification.get('is_answerable'):
                                table_name = classification['table']
                                metadata = {table_name: self.tables_metadata[table_name]}
                                reference = self.tables_metadata[table_name].get("reference", {})
                                if isinstance(reference, dict):
                                    child = reference.get("child_table")
                                    parent = reference.get("parent_table")
                                    if child and child in self.tables_metadata:
                                        metadata[child] = self.tables_metadata[child]
                                    elif parent and parent in self.tables_metadata:
                                        metadata[parent] = self.tables_metadata[parent]
                                direct_result = self.mcp.execute_natural_language_query(
                                    question=question,
                                    table_name=table_name,
                                    model=self.llm_model,
                                    table_metadata=metadata,
                                    current_date_info=None,
                                    log_ctx=log_ctx,
                                    api_key=self._api_key,
                                    vendor_name=self._vendor,
                                )
                            # is_answerable=False(현재 데이터와 무관한 질문일 가능성, 예: 인사말)인 경우
                            # direct_result를 None으로 두어 원래 답변을 그대로 유지한다 (오탐으로 인한 UX 저하 방지).
                    except Exception as e:
                        # print(f"[FORCE QUERY] 직접 실행 실패: {e}")
                        direct_result = None

                    if direct_result is not None:
                        status = direct_result.get('status')
                        if status == 'success' and direct_result.get('data'):
                            data = direct_result['data']
                            query = direct_result.get('conditions', {}).get('generated_sql')
                            if query:
                                current_queries.append({"question": question, "query": query})
                            try:
                                answer_text = self._answer_from_data(question, data, log_ctx)
                            except Exception as e:
                                # print(f"[FORCE QUERY] 데이터 기반 답변 재생성 실패: {e}")
                                pass
                            if current_visualization_type in ("table", "chart") and len(viz_candidates) < MAX_VISUALIZATIONS:
                                viz_candidates.append({
                                    "data": data,
                                    "visualization_type": current_visualization_type,
                                    "chart_type": viz_result.get('chart_type'),
                                    "sub_question": question,
                                    "query": query,
                                })
                            # print(f"[FORCE QUERY] 직접 실행 성공: {len(data)}건")
                        elif status in ('no_data', 'error', 'no_dataset'):
                            # 데이터 질문인 건 확인됐는데 데이터가 없거나 조회에 실패한 경우 —
                            # 지어낸 답변 대신 모른다고 명확히 답변
                            answer_text = (
                                direct_result.get('message')
                                or "죄송합니다, 현재 등록된 데이터로는 답변할 수 없습니다."
                            )
                            # print(f"[FORCE QUERY] 데이터 없음/실패({status}) — 답변을 안내 문구로 대체")
                        # status == 'not_answerable' (분류기가 데이터 질문이 아니라고 판단, 예: 메타 질문/피드백)이면
                        # direct_result를 만들었더라도 answer_text를 덮어쓰지 않고 원래 LLM 답변을 그대로 유지한다.

                # 결과가 1건뿐인 후보는 시각화 의미가 없으므로 제외 (텍스트로만 답변).
                # 필터링 전에 로그로 남겨서, 의도된 필터링인지 집계 오류로 우연히 1건이 된 것인지
                # 나중에 구분할 수 있게 한다.
                dropped_single_row = [
                    c for c in viz_candidates
                    if c["data"] and len(c["data"]) == 1 and c["visualization_type"] in ("table", "chart")
                ]
                for _c in dropped_single_row:
                    print(f"[INFO] 시각화 제외(결과 1건): {_c['sub_question']!r}")
                viz_candidates = [c for c in viz_candidates if not (c["data"] and len(c["data"]) == 1)]

                current_query = viz_candidates[0]["query"] if viz_candidates else current_query
                current_visualization_type = viz_candidates[0]["visualization_type"] if viz_candidates else (current_visualization_type or "none")

                response = {
                    "answer": answer_text,
                    "query": current_query,
                    "queries": current_queries,
                    "visualization_type": current_visualization_type or "none",
                    "total_inputtoken": self._token_input,
                    "total_outputtoken": self._token_output,
                }

                history_answer = answer_text
                visualizations = []
                q_data_blocks = []
                visualization_errors = []
                chart_idx = 0
                table_idx = 0

                for candidate in viz_candidates:
                    viz_type = candidate["visualization_type"]
                    if viz_type not in ("table", "chart"):
                        continue
                    try:
                        df = pd.DataFrame(candidate["data"])
                        if df.empty:
                            continue
                        # "_한글" 보조 필드(예: "판매금액_한글")는 텍스트 답변에서 LLM이 옮겨 쓰라고
                        # 추가한 것이지 표/그래프의 별도 시리즈가 아니다. 표/그래프는 원본 숫자만 쓴다.
                        # (문자열 컬럼이 뒤에 붙어 있으면 "마지막 컬럼이 숫자인가"로 판단하는 피벗
                        # 자동 감지 로직도 오작동하므로 반드시 여기서 먼저 제거해야 한다.)
                        df = df[[c for c in df.columns if not str(c).endswith('_한글')]]
                        if df.empty or len(df.columns) < 1:
                            continue
                        if viz_type == "table":
                            table_html, data_json = dataframe_to_html_table(df)
                            table_idx += 1
                            item = {"type": "table", "title": f"표{table_idx}", "table_html": table_html}
                            if data_json:
                                item["table_data"] = json.loads(data_json)
                                q_data_blocks.append(data_json)
                            visualizations.append(item)
                        elif viz_type == "chart":
                            # chart_type은 쿼리 실행 전 질문 텍스트만 보고 낸 추정치(candidate에 담김)일
                            # 뿐이다. 이제 실제 데이터프레임이 나왔으니, 그걸 보고 최종 확정한다.
                            # 하위 질문(sub_question)만 보면 원래 질문의 의도("~얼마나 떼이는지",
                            # "소수가 대부분을 차지" 등)가 paraphrase 과정에서 사라질 수 있어 최상위
                            # 질문과 합쳐서 의미 판단 근거로 쓴다.
                            combined_question = f"{question} {candidate['sub_question']}"
                            resolved_chart_type = decide_chart_type(
                                df, combined_question, hint=candidate["chart_type"]
                            )
                            mismatch = audit_chart_type_mismatch(combined_question, resolved_chart_type)
                            if mismatch:
                                print(mismatch)

                            sub_dfs = [df]
                            sub_chart_types = [resolved_chart_type]
                            labels_suffix = None

                            if resolved_chart_type == "stacked":
                                # 누적(stacked) 차트인데 대상별 규모가 극심하게 다르면, 100%로
                                # 정규화하는 대신 상위/하위 그룹으로 나눠 각각 절대금액으로 그린다
                                # (그룹 내에서는 실제 규모도 보이고 작은 대상이 안 가려짐).
                                split = split_by_magnitude(df)
                                if len(split) > 1:
                                    sub_dfs = split
                                    sub_chart_types = [resolved_chart_type] * len(split)
                                    labels_suffix = ["(상위)", "(하위)"]
                            elif resolved_chart_type in ("bar", "dual_axis"):
                                # 금액(절대값)과 비율(%)이 섞여 있으면 억지로 이중축 하나에 우겨넣지
                                # 않고, 단위별 단일 지표 막대 차트 여러 개로 분리한다.
                                split = split_by_unit(df)
                                if len(split) > 1:
                                    sub_dfs = split
                                    sub_chart_types = ["bar"] * len(split)
                                    labels_suffix = ["(금액)", "(비율)"]

                            for sub_idx, sub_df in enumerate(sub_dfs):
                                if len(visualizations) >= MAX_VISUALIZATIONS:
                                    break
                                sub_chart_type = sub_chart_types[sub_idx] if sub_idx < len(sub_chart_types) else resolved_chart_type
                                chart_image, data_json, chart_err = dataframe_to_chart_image(
                                    sub_df, candidate["sub_question"], sub_chart_type
                                )
                                if chart_err:
                                    print(f"[ERROR] 차트 생성 실패({sub_chart_type}): {chart_err}")
                                    visualization_errors.append(chart_err)
                                if chart_image:
                                    chart_idx += 1
                                    title = f"차트{chart_idx}"
                                    if labels_suffix and sub_idx < len(labels_suffix):
                                        title += " " + labels_suffix[sub_idx]
                                    item = {"type": "chart", "title": title, "chart_image": chart_image}
                                    if data_json:
                                        item["chart_data"] = json.loads(data_json)
                                        q_data_blocks.append(data_json)
                                    visualizations.append(item)
                    except Exception as e:
                        # print(f"시각화 생성 오류: {e}")
                        traceback.print_exc()

                # 결과 1건이라 후보에서 제외됐는데 결국 아무 시각화도 만들지 못한 경우, 텍스트로만
                # 답변하는 이유를 사용자에게도 알린다 (예전에는 조용히 텍스트만 나갔다).
                if dropped_single_row and not visualizations:
                    answer_text += "\n\n(조회 결과가 1건이라 표/그래프 대신 텍스트로 답변합니다.)"
                    history_answer = answer_text

                if visualizations:
                    response["visualizations"] = visualizations
                    # 하위 호환: 기존 단수 필드(table_html/chart_image 등)는 첫 번째 시각화로 채운다
                    first = visualizations[0]
                    if first["type"] == "table":
                        response["table_html"] = first["table_html"]
                        if "table_data" in first:
                            response["table_data"] = first["table_data"]
                    else:
                        response["chart_image"] = first["chart_image"]
                        if "chart_data" in first:
                            response["chart_data"] = first["chart_data"]
                    history_answer = answer_text + "".join(f"\n<q_data>{block}</q_data>" for block in q_data_blocks)

                if visualization_errors:
                    response["visualization_error"] = "; ".join(visualization_errors)

                # answer_text가 위 두 분기 중 하나에서 바뀌었을 수 있으므로 response에 다시 반영한다
                # (response["answer"]는 dict 생성 시점의 문자열 값을 복사해 가진 것이라 자동 반영되지 않음).
                response["answer"] = answer_text

                self.add_to_history(session_id, question, history_answer, current_query)
                self.trim_session_history(session_id)  # config.py의 TARGET_TURNS/THRESHOLD_TURNS 버퍼 트림

                return response

            except Exception as e:
                last_error = e
                print(f"[attempt {attempt}/{max_retries}] ask 오류: {e}")
                traceback.print_exc()
                if attempt < max_retries:
                    import time
                    time.sleep(attempt * 1.5)

        return {
            "answer": f"일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n(오류: {str(last_error)})",
            "query": None,
            "queries": [],
            "visualization_type": "none"
        }
