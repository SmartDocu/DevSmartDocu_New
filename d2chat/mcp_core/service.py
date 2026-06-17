"""
service.py MCP 채팅 서비스 - 싱글톤 패턴으로 MCPAgent 관리
"""
from urllib.parse import quote_plus
from typing import Dict

from backend.app.config import settings
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
            DB_DRIVER = settings.DB_DRIVER
            DB_SERVER = settings.DB_SERVER
            DB_DATABASE = settings.DB_DATABASE
            DB_USERNAME = settings.DB_USERNAME
            DB_PASSWORD = settings.DB_PASSWORD

            if not all([DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD]):
                raise ValueError("DB 연결 정보가 config에 설정되지 않았습니다.")

            conn_str = (
                f"Driver={{{DB_DRIVER}}};"
                f"Server={DB_SERVER},1433;"
                f"Database={DB_DATABASE};"
                f"UID={DB_USERNAME};"
                f"PWD={DB_PASSWORD};"
                "Encrypt=yes;"
                "TrustServerCertificate=no;"
                "Connection Timeout=30;"
            )

            params = quote_plus(conn_str)
            db_connection = f"mssql+pyodbc:///?odbc_connect={params}"

            tables_metadata = meta_loader.load()

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
