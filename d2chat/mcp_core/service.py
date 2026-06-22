"""
service.py MCP 채팅 서비스 - 싱글톤 패턴으로 MCPAgent 관리
"""
from typing import Dict

from d2chat.mcp_agent.mcp_agent import MCPAgent
from d2chat.config import DEFAULT_LLM_MODEL
from d2shared import meta_loader


class MCPChatService:
    """MCPAgent를 싱글톤으로 관리하는 서비스 클래스"""

    _instance = None
    _agent = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self):
        if self._initialized:
            return

        try:
            tables_metadata = meta_loader.load()
            db_connection = meta_loader.get_connection_url()

            if not db_connection:
                raise ValueError("Supabase에서 DB 연결 정보를 가져오지 못했습니다 (data_metas → datas → connectors 경로 확인 필요).")

            self._agent = MCPAgent(
                db_connection=db_connection,
                llm_model=DEFAULT_LLM_MODEL,
                tables_metadata=tables_metadata,
            )

            self._initialized = True

        except Exception as e:
            print(f"MCP 서비스 초기화 실패: {str(e)}")
            raise

    def ask(self, question: str, session_id: str = "default", log_ctx: dict = None) -> Dict:
        """사용자 질문에 답변"""
        if not self._initialized or self._agent is None:
            raise RuntimeError("MCP 서비스가 초기화되지 않았습니다.")

        try:
            return self._agent.ask(question, session_id=session_id, log_ctx=log_ctx)
        except Exception as e:
            return {
                "answer": f"오류가 발생했습니다: {str(e)}",
                "query": None,
                "visualization_type": "none"
            }

    def seed_session_history(self, session_id: str, question: str, answer: str) -> None:
        """이어하기: 에이전트 인메모리 히스토리에 이전 Q&A 주입"""
        if self._agent is not None:
            self._agent.add_to_history(session_id, question, answer)

    def get_data_info(self, table_name: str = None) -> dict:
        """데이터 정보 조회"""
        if not self._initialized or self._agent is None:
            raise RuntimeError("MCP 서비스가 초기화되지 않았습니다.")

        try:
            return self._agent.get_data_info(table_name=table_name)
        except Exception as e:
            return {"error": str(e)}


# 전역 서비스 인스턴스 (싱글톤)
mcp_service = MCPChatService()
