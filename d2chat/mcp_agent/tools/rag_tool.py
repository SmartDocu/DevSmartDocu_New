"""
tools/rag_tool.py
RAG 문서 검색 Tool
"""
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class RAGInput(BaseModel):
    question: str = Field(description="사용자의 자연어 질문")
    projectid: int = Field(
        default=1,
        description="프로젝트 ID. 제약/의약품 관련 질문이면 1, 법률/규정 관련 질문이면 3"
    )


def create_rag_tool(rag_server) -> Optional[StructuredTool]:
    if rag_server is None:
        return None

    def search_rag_tool(question: str, projectid: int = 1) -> str:
        try:
            return rag_server.search(question=question, projectid=projectid)
        except Exception as e:
            return f"RAG 검색 중 오류 발생: {str(e)}"

    return StructuredTool(
        name="search_rag",
        description=(
            "내부 문서에서 정보를 검색하는 Tool. "
            "DB 쿼리로 답할 수 없는 질문, 규정/지침/매뉴얼/SOP 관련 질문에 사용. "
            "projectid 선택 규칙: "
            "1 = 제약·의약품·GMP·SOP·품질관리·임상·원료·완제품 관련 질문. "
            "3 = 법률·근로기준법·계약·소송·판례 관련 질문. "
            "반드시 질문 내용에 맞는 projectid를 선택할 것."
        ),
        func=search_rag_tool,
        args_schema=RAGInput
    )
