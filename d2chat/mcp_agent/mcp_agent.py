"""MCP Agent — LangGraph ReAct 기반 데이터 Q&A."""
from __future__ import annotations

import json
import re
import traceback
from typing import Optional, Dict, List

import pandas as pd
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from d2shared.visualization import (
    strip_markdown,
    detect_visualization_type_with_llm,
    dataframe_to_html_table,
    dataframe_to_chart_image,
)
from d2chat.mcp_agent.tools import create_all_tools


class MCPAgent:
    """동적 쿼리 생성 기반 MCP Agent."""

    def __init__(
        self,
        db_connection: str,
        llm_model: str,
        db_schema: str = "",
        temperature: float = 0,
        tables_metadata: Optional[Dict[str, Dict]] = None,
    ) -> None:
        self.current_question = None
        self.current_query = None
        self.current_queries: List[dict] = []
        self.current_visualization_type = None
        self.current_chart_type = None
        self.current_data = None
        self.llm_model = llm_model
        self._current_log_ctx = None
        self._token_input = 0
        self._token_output = 0

        from d2shared.sql_generator import SqlGenerator
        self.mcp = SqlGenerator(
            connection_url=db_connection,
            db_schema=db_schema,
            model=llm_model,
        )

        from backend.app.config import settings
        self.llm = ChatAnthropic(model=self.llm_model, temperature=temperature, api_key=settings.CLAUDE_API_KEY)
        self.memory = MemorySaver()
        self.tables_metadata = self._normalize_tables_metadata(tables_metadata or {})
        self.tools = create_all_tools(self)

        self.stateless_executor = self._create_agent()
        self.session_histories: Dict[str, List[Dict]] = {}

    def _normalize_tables_metadata(self, meta: Dict[str, Dict]) -> Dict[str, Dict]:
        normalized = {}
        for table, m in meta.items():
            normalized[table] = {
                "schema":              m.get("schema", ""),
                "physical_name":       m.get("physical_name", ""),
                "logical_name":        m.get("logical_name", ""),
                "aliases":             m.get("aliases", ""),
                "source_type":         m.get("source_type", ""),
                "description":         m.get("description", ""),
                "primary_key":         m.get("primary_key", ""),
                "grain":               m.get("grain", ""),
                "default_time_column": m.get("default_time_column", ""),
                "reference":           m.get("reference", ""),
                "purpose":             m.get("purpose", ""),
                "query_examples":      m.get("query_examples", ""),
                "columns":             m.get("columns", {}),
                "query":               m.get("query", ""),
            }
        return normalized

    def _create_system_message(self) -> SystemMessage:
        available_data_list = [
            f"- {name} ({info.get('description', name)}): {info.get('purpose', '데이터 저장')}"
            for name, info in self.tables_metadata.items()
        ]
        content = f"""당신은 데이터 분석 전문 AI 어시스턴트입니다.

**현재 접근 가능한 데이터베이스 테이블:**
{', '.join(self.tables_metadata.keys())}

**제공 가능한 정보:**
{chr(10).join(available_data_list)}

**사용 가능한 도구:**
1. get_current_date: 현재 날짜/시간 조회
2. execute_query: 데이터베이스 쿼리 실행

**핵심 규칙:**
- 데이터 수치 관련 질문 → execute_query 사용
- 상대적 날짜("오늘", "어제" 등)가 있으면 먼저 get_current_date 호출
- 새 질문이 데이터 조회/집계를 요청하면 이전 대화의 <q_data> 데이터와 무관하게 반드시 execute_query를 새로 호출

**답변 스타일:**
- 마크다운 문법(**굵게**, ##제목, -리스트, 테이블 등) 사용 금지
- 일반 텍스트로 자연스럽게 작성
- HTML 태그를 절대 답변에 포함하지 마세요 (테이블, 차트는 자동으로 하단에 표시됨)
- 결과가 1건인 경우 텍스트로만 답변

**이전 대화 데이터 처리:**
- `<q_data>` 블록을 절대 답변에 출력하지 마세요
- `<q_data>` 데이터를 새 질문의 답변 데이터로 재사용하지 마세요
"""
        return SystemMessage(content=content)

    def _create_agent(self):
        tool_node = ToolNode(self.tools)

        def call_model(state: MessagesState, config=None):
            from datetime import datetime
            from d2chat.history.llm_logger import log_llm_call
            system_msg = self._create_system_message()
            messages = [system_msg] + state["messages"]
            start = datetime.now()
            response = self.llm.bind_tools(self.tools).invoke(messages)
            end = datetime.now()
            usage = getattr(response, "usage_metadata", None) or {}
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            self._token_input += in_tok
            self._token_output += out_tok
            log_llm_call(
                log_ctx=self._current_log_ctx,
                stepnm="agent",
                steptitle="에이전트 응답",
                llmmodelnm=self.llm_model,
                inputtoken=in_tok,
                outputtoken=out_tok,
                startdts=start,
                enddts=end,
            )
            return {"messages": [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)
        workflow.add_edge(START, "agent")

        def should_continue(state: MessagesState):
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return END

        workflow.add_conditional_edges("agent", should_continue, ["tools", END])
        workflow.add_edge("tools", "agent")
        return workflow.compile()

    # ── 세션 히스토리 ───────────────────────────────────────────────

    def get_session_history(self, session_id: str) -> List[Dict]:
        return self.session_histories.get(session_id, [])

    def add_to_history(self, session_id: str, question: str, answer: str, query: str = None) -> None:
        self.session_histories.setdefault(session_id, []).append(
            {"question": question, "answer": answer}
        )

    def clear_session_history(self, session_id: str) -> None:
        self.session_histories[session_id] = []

    def trim_session_history(self, session_id: str, keep_last: int = 20) -> None:
        history = self.session_histories.get(session_id, [])
        if len(history) > keep_last:
            self.session_histories[session_id] = history[-keep_last:]

    # ── 메인 질문 처리 ──────────────────────────────────────────────

    def ask(self, question: str, session_id: str = "default", max_retries: int = 2, log_ctx: dict = None) -> Dict:
        self._current_log_ctx = log_ctx
        self._token_input = 0
        self._token_output = 0
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                self.current_query = None
                self.current_queries = []
                self.current_visualization_type = None
                self.current_data = None

                history = self.get_session_history(session_id)
                history_messages = []
                for h in history:
                    history_messages.append(HumanMessage(content=h["question"]))
                    history_messages.append(AIMessage(content=h["answer"]))
                input_messages = history_messages + [HumanMessage(content=question)]

                result = self.stateless_executor.invoke(
                    {"messages": input_messages},
                    config={"recursion_limit": 30},
                )
                answer_text = strip_markdown(result["messages"][-1].content)
                answer_text = re.sub(r"<q_data>.*?</q_data>", "", answer_text, flags=re.DOTALL).strip()

                current_query = self.current_query
                current_queries = list(self.current_queries)
                current_data = self.current_data

                for msg in result["messages"]:
                    if type(msg).__name__ == "ToolMessage" and getattr(msg, "name", None) == "execute_query":
                        try:
                            tr = json.loads(msg.content)
                            if tr.get("status") == "success" and tr.get("data"):
                                current_data = tr["data"]
                            if tr.get("conditions", {}).get("generated_sql"):
                                q = tr["conditions"]["generated_sql"]
                                current_query = q
                                current_queries.append({"question": question, "query": q})
                        except Exception:
                            pass

                from d2chat.history.llm_logger import log_llm_call as _log_fn
                viz_result = detect_visualization_type_with_llm(
                    question, self.llm, log_ctx=log_ctx, log_fn=_log_fn
                )
                current_visualization_type = viz_result["visualization_type"]

                # 강제 쿼리: LLM이 execute_query 미호출 + 시각화 요청
                if (current_data is None and not current_queries
                        and current_visualization_type in ("table", "chart")):
                    try:
                        from d2chat.mcp_agent.classifier import classify_question_and_table
                        cls = classify_question_and_table(question, self.llm, self.tables_metadata, log_ctx=log_ctx)
                        if cls.get("is_answerable"):
                            table_name = cls["table"]
                            metadata = {table_name: self.tables_metadata[table_name]}
                            ref = self.tables_metadata[table_name].get("reference", {})
                            if isinstance(ref, dict):
                                child = ref.get("child_table")
                                parent = ref.get("parent_table")
                                if child and child in self.tables_metadata:
                                    metadata[child] = self.tables_metadata[child]
                                elif parent and parent in self.tables_metadata:
                                    metadata[parent] = self.tables_metadata[parent]
                            dr = self.mcp.execute_natural_language_query(
                                question=question,
                                table_name=table_name,
                                table_metadata=metadata,
                                current_date_info=None,
                                log_fn=_log_fn,
                                log_ctx=log_ctx,
                            )
                            if dr.get("status") == "success" and dr.get("data"):
                                current_data = dr["data"]
                                q = dr.get("conditions", {}).get("generated_sql")
                                if q:
                                    current_query = q
                                    current_queries.append({"question": question, "query": q})
                    except Exception as e:
                        print(f"[FORCE QUERY] 직접 쿼리 실패: {e}")

                if current_data and len(current_data) == 1:
                    current_visualization_type = "none"

                response = {
                    "answer":              answer_text,
                    "query":               current_query,
                    "queries":             current_queries,
                    "visualization_type":  current_visualization_type or "none",
                    "total_inputtoken":    self._token_input,
                    "total_outputtoken":   self._token_output,
                }

                history_answer = answer_text
                if current_visualization_type in ("table", "chart") and current_data:
                    try:
                        df = pd.DataFrame(current_data)
                        if not df.empty:
                            if current_visualization_type == "table":
                                table_html, data_json = dataframe_to_html_table(df)
                                response["table_html"] = table_html
                                if data_json:
                                    response["table_data"] = json.loads(data_json)
                                    history_answer = f"{answer_text}\n<q_data>{data_json}</q_data>"
                            else:
                                chart_image, data_json = dataframe_to_chart_image(
                                    df, question, self.current_chart_type
                                )
                                if chart_image:
                                    response["chart_image"] = chart_image
                                if data_json:
                                    response["chart_data"] = json.loads(data_json)
                                    history_answer = f"{answer_text}\n<q_data>{data_json}</q_data>"
                    except Exception as e:
                        print(f"[WARN] 시각화 생성 오류: {e}")
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
            "answer":             f"일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n(오류: {last_error})",
            "query":              None,
            "queries":            [],
            "visualization_type": "none",
        }
