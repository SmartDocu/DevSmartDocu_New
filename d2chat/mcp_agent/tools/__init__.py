"""
d2chat tools 등록 — query_tool은 d2shared에서, rag_tool은 d2chat 전용.
"""
from d2chat.mcp_agent.classifier import classify_question_and_table
from d2chat.mcp_agent.tools.date_tool import create_date_tool
from d2chat.mcp_agent.tools.rag_tool import create_rag_tool
from d2shared.tools.query_tool import create_query_tool


def create_all_tools(agent) -> list:
    tools = [
        create_date_tool(),
        create_query_tool(agent, classifier_fn=classify_question_and_table),
    ]
    rag_tool = create_rag_tool(agent.rag_server)
    if rag_tool:
        tools.append(rag_tool)
    return tools
