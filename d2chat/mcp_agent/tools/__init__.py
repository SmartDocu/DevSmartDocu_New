"""Tool 등록 진입점. RAG 제거됨."""
from d2chat.mcp_agent.tools.date_tool import create_date_tool
from d2chat.mcp_agent.tools.query_tool import create_query_tool


def create_all_tools(agent) -> list:
    return [
        create_date_tool(),
        create_query_tool(agent),
    ]
