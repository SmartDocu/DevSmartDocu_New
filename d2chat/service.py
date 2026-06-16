"""MCP 채팅 서비스 — MCPAgent 싱글톤 관리."""
import json
from typing import Dict
from urllib.parse import quote_plus


class MCPChatService:
    _instance = None
    _agent = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> None:
        if self._initialized:
            return
        try:
            from backend.app.config import settings
            from d2chat.mcp_agent.mcp_agent import MCPAgent
            from d2chat.config import DEFAULT_LLM_MODEL

            DB_DRIVER = settings.DB_DRIVER
            DB_SERVER = settings.DB_SERVER
            DB_DATABASE = settings.DB_DATABASE
            DB_USERNAME = settings.DB_USERNAME
            DB_PASSWORD = settings.DB_PASSWORD

            if not all([DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD]):
                raise ValueError("DB 연결 정보가 설정되지 않았습니다. (DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD)")

            conn_str = (
                f"Driver={{{DB_DRIVER or 'ODBC Driver 17 for SQL Server'}}};"
                f"Server={DB_SERVER},1433;"
                f"Database={DB_DATABASE};"
                f"UID={DB_USERNAME};"
                f"PWD={DB_PASSWORD};"
                "Encrypt=yes;"
                "TrustServerCertificate=no;"
                "Connection Timeout=30;"
            )
            db_connection = f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"

            # data_metas 테이블에서 테이블 메타데이터 로드 (Supabase)
            from utilsPrj.supabase_client import get_service_client
            sb = get_service_client().schema(settings.SUPABASE_SCHEMA)
            rows = sb.table("data_metas").select("json").execute().data

            tables_metadata: Dict = {}
            for row in rows:
                meta = json.loads(row["json"]) if isinstance(row["json"], str) else row["json"]
                key = meta.get("physical_name") or meta.get("logical_name")
                if key:
                    tables_metadata[key] = meta

            self._agent = MCPAgent(
                db_connection=db_connection,
                llm_model=DEFAULT_LLM_MODEL,
                tables_metadata=tables_metadata,
            )
            self._initialized = True

        except Exception as e:
            print(f"[d2chat] MCP 서비스 초기화 실패: {e}")
            raise

    def ask(self, question: str, session_id: str = "default", log_ctx: dict = None) -> Dict:
        if not self._initialized or self._agent is None:
            raise RuntimeError("MCP 서비스가 초기화되지 않았습니다.")
        try:
            return self._agent.ask(question, session_id=session_id, log_ctx=log_ctx)
        except Exception as e:
            return {
                "answer":             f"오류가 발생했습니다: {e}",
                "query":              None,
                "visualization_type": "none",
            }

    def seed_session_history(self, session_id: str, question: str, answer: str) -> None:
        if self._agent is not None:
            self._agent.add_to_history(session_id, question, answer)

    def get_data_info(self) -> dict:
        if not self._initialized or self._agent is None:
            raise RuntimeError("MCP 서비스가 초기화되지 않았습니다.")
        return {
            "tables": list(self._agent.tables_metadata.keys()),
            "dialect": self._agent.mcp.dialect,
        }


mcp_service = MCPChatService()
