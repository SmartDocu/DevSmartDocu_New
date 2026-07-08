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
)
from d2shared.llm_logger import log_llm_call
from d2chat.mcp_agent.tools import create_all_tools


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
            print(f"[MCPAgent] LLM 초기화 실패 (ask() 호출 시 재시도): {_e}")
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

        style_guide = """
**답변 스타일 - 매우 중요:**

1. 자연스러운 대화체 사용
- 마크다운 형식(**굵게**, ##제목, -리스트, 테이블 등)의 문법을 사용하지 않습니다.
- 일반 텍스트로 자연스럽게 작성
- HTML 태그를 절대 답변에 포함하지 마세요 (테이블, 차트는 자동으로 하단에 표시됨)

2. 시각화 요청 판단
- "표로", "테이블로", "그래프로", "차트로" 등 명시적 키워드가 있을 때만 시각화
- **명시적 요청이 없으면 텍스트의 의미를 파악하여 시각화가 필요하면 시각화하여 결과를 보여줍니다.**

3. 텍스트 답변 형식 (시각화 요청 없을 때)
- '완벽합니다!', '성공' 같은 평가 표현 사용하지 않기
- 중요 쟁점 한두 개를 간략히 기술

4. 시각화 답변 형식 (표/그래프 요청 있을 때)
- 결과가 1건인 경우 텍스트로만 답변

**이전 대화 데이터 처리:**
- 이전 대화에 `<q_data>` 블록이 있으면 그것은 시스템이 자동 삽입한 쿼리 결과 메타데이터입니다.
- `<q_data>...</q_data>` 블록을 절대 답변에 출력하지 마세요.
- 데이터 조회 결과 JSON 배열을 답변 텍스트에 직접 포함하지 마세요.
- `<q_data>` 데이터를 새 질문의 답변 데이터로 재사용하지 마세요. 항상 {query_tool}을 새로 호출해 최신 데이터를 조회하세요.

**절대 하지 말아야 할 것:**
- 마크다운 문법 사용 (**굵게**, ##제목, -리스트, |표|)
- 불필요하게 표나 그래프 자동 생성
- `<q_data>` 태그 또는 JSON 데이터 배열을 답변에 출력
"""

        if mode == "external":
            datasets = self.excel_server.get_session_datasets(self._current_session_id)
            available_data_list = [
                f"- {name} ({info.get('description', name)}): {info.get('purpose', '업로드된 데이터 조회')}"
                for name, info in datasets.items()
            ]
            available_data_text = '\n'.join(available_data_list) or "(등록된 데이터 없음)"

            content = f"""당신은 데이터 분석 전문 AI 어시스턴트입니다.

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
""" + style_guide.replace("{query_tool}", "execute_excel_query")
        else:
            available_data_list = [
                f"- {table_name} ({info.get('description', table_name)}): {info.get('purpose', '데이터 저장')}"
                for table_name, info in self.tables_metadata.items()
            ]
            available_data_text = '\n'.join(available_data_list)

            content = f"""당신은 데이터 분석 전문 AI 어시스턴트입니다.

**현재 접근 가능한 데이터베이스 테이블:**
{', '.join(self.tables_metadata.keys())}

**제공 가능한 정보:**
{available_data_text}

**사용 가능한 도구:**
1. get_current_date: 현재 날짜/시간 조회
2. execute_query: 데이터베이스 쿼리 실행
3. search_rag: 내부 문서 검색 (규정/지침/SOP/법률 관련)

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
""" + style_guide.replace("{query_tool}", "execute_query")

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

    def trim_session_history(self, session_id: str, keep_last: int = 5):
        if session_id in self.session_histories:
            history = self.session_histories[session_id]
            if len(history) > keep_last:
                self.session_histories[session_id] = history[-keep_last:]


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
                current_data = None

                executor = self.stateless_executor
                config = {"recursion_limit": 30}

                history = self.get_session_history(session_id)
                history_messages = []
                for h in history:
                    history_messages.append(HumanMessage(content=h["question"]))
                    history_messages.append(AIMessage(content=h["answer"]))
                input_messages = history_messages + [HumanMessage(content=question)]

                print(f"\n{'='*60}")
                print(f"[LLM 입력] 총 메시지 수: {len(input_messages)}")
                for i, msg in enumerate(input_messages):
                    role = type(msg).__name__
                    content = msg.content + "..." if len(msg.content) > 200 else msg.content
                    print(f"  [{i+1}] {role}: {content}")
                print(f"{'='*60}\n")
                result = executor.invoke({"messages": input_messages}, config=config)
                answer_text = strip_markdown(result["messages"][-1].content)
                answer_text = re.sub(r'<q_data>.*?</q_data>', '', answer_text, flags=re.DOTALL).strip()

                for msg in result["messages"]:
                    if type(msg).__name__ == 'ToolMessage' and getattr(msg, 'name', None) in ('execute_query', 'execute_excel_query'):
                        try:
                            tool_result = json.loads(msg.content)
                            if tool_result.get('status') == 'success' and tool_result.get('data'):
                                current_data = tool_result['data']
                            if tool_result.get('conditions', {}).get('generated_sql'):
                                query = tool_result['conditions']['generated_sql']
                                current_query = query
                                current_queries.append({"question": question, "query": query})
                        except Exception as e:
                            print(f"[WARN] tool result 파싱 오류: {e}")

                viz_result = detect_visualization_type_with_llm(question, self.llm, log_ctx=log_ctx)
                current_visualization_type = viz_result['visualization_type']

                # 환각 방지 안전장치: LLM이 도구(execute_query/execute_excel_query)를 호출하지 않은 경우,
                # 시각화 요청 여부와 무관하게 항상 데이터 질문인지 판별해 직접 조회를 강제 실행한다.
                # 이 경로로 얻은 답변은 최초 LLM 답변(근거 없이 생성됐을 수 있음)을 버리고
                # 실제 데이터만 근거로 _answer_from_data()에서 새로 생성한다.
                if current_data is None and not current_queries:
                    from d2chat.mcp_agent.classifier import classify_question_and_table
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
                        print(f"[FORCE QUERY] 직접 실행 실패: {e}")
                        direct_result = None

                    if direct_result is not None:
                        status = direct_result.get('status')
                        if status == 'success' and direct_result.get('data'):
                            current_data = direct_result['data']
                            query = direct_result.get('conditions', {}).get('generated_sql')
                            if query:
                                current_query = query
                                current_queries.append({"question": question, "query": query})
                            try:
                                answer_text = self._answer_from_data(question, current_data, log_ctx)
                            except Exception as e:
                                print(f"[FORCE QUERY] 데이터 기반 답변 재생성 실패: {e}")
                            print(f"[FORCE QUERY] 직접 실행 성공: {len(current_data)}건")
                        elif status in ('no_data', 'error', 'no_dataset'):
                            # 데이터 질문인 건 확인됐는데 데이터가 없거나 조회에 실패한 경우 —
                            # 지어낸 답변 대신 모른다고 명확히 답변
                            answer_text = (
                                direct_result.get('message')
                                or "죄송합니다, 현재 등록된 데이터로는 답변할 수 없습니다."
                            )
                            print(f"[FORCE QUERY] 데이터 없음/실패({status}) — 답변을 안내 문구로 대체")
                        # status == 'not_answerable' (분류기가 데이터 질문이 아니라고 판단, 예: 메타 질문/피드백)이면
                        # direct_result를 만들었더라도 answer_text를 덮어쓰지 않고 원래 LLM 답변을 그대로 유지한다.

                if current_data and len(current_data) == 1:
                    current_visualization_type = "none"

                response = {
                    "answer": answer_text,
                    "query": current_query,
                    "queries": current_queries,
                    "visualization_type": current_visualization_type or "none",
                    "total_inputtoken": self._token_input,
                    "total_outputtoken": self._token_output,
                }

                history_answer = answer_text

                if current_visualization_type in ["table", "chart"] and current_data:
                    try:
                        df = pd.DataFrame(current_data)
                        if not df.empty:
                            if current_visualization_type == "table":
                                table_html, data_json = dataframe_to_html_table(df)
                                response["table_html"] = table_html
                                if data_json:
                                    response["table_data"] = json.loads(data_json)
                                    history_answer = f"{answer_text}\n<q_data>{data_json}</q_data>"
                            elif current_visualization_type == "chart":
                                chart_image, data_json = dataframe_to_chart_image(df, question, self.current_chart_type)
                                if chart_image:
                                    response["chart_image"] = chart_image
                                if data_json:
                                    response["chart_data"] = json.loads(data_json)
                                    history_answer = f"{answer_text}\n<q_data>{data_json}</q_data>"
                    except Exception as e:
                        print(f"시각화 생성 오류: {e}")
                        traceback.print_exc()

                self.add_to_history(session_id, question, history_answer, current_query)
                self.trim_session_history(session_id, keep_last=20)

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
