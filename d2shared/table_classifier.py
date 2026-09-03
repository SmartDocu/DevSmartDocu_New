"""table_classifier.py — 질문 → 등록된 데이터(테이블) 선택 (d2chat · d2insight 공유)

등록된 메타(data_chatmetas)만 보고 그 질문에 맞는 PRIMARY 테이블을 고른다. 어느 것으로도
답할 수 없으면 그 사실과 안내 문구를 돌려준다.

LLM structured output 호출/로깅은 d2shared.classifier.classify_with_llm을 쓴다.
(2026-09-02, d2chat/mcp_agent/classifier.py에서 옮겨옴 — d2insight도 같은 선택을 해야 한다.)
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from d2shared.classifier import classify_with_llm


class QuestionClassification(BaseModel):
    """질문 적합성 및 테이블 분류 결과"""
    is_answerable: bool = Field(description="DB로 답변 가능한 질문인지 여부")
    table: Optional[str] = Field(default=None, description="답변 가능한 경우 선택된 테이블 이름")
    confidence: float = Field(description="신뢰도 (0.0 ~ 1.0)", ge=0.0, le=1.0)
    reasoning: str = Field(description="판단 이유")
    suggestion: Optional[str] = Field(default=None, description="답변 불가능한 경우 안내 메시지")


class ReportTableSelection(BaseModel):
    """보고서 한 건에 필요한 테이블 전체"""
    is_answerable: bool = Field(description="등록된 데이터로 이 보고서를 작성할 수 있는지")
    tables: List[str] = Field(default_factory=list, description="이 보고서에 필요한 테이블 이름 전부")
    reasoning: str = Field(description="각 테이블이 왜 필요한지")
    suggestion: Optional[str] = Field(default=None, description="작성 불가능한 경우 안내 메시지")


def _build_tables_description_with_relationships(tables_info: Dict[str, Dict]) -> str:
    """테이블 정보를 프롬프트용 텍스트로 변환"""
    descriptions = []
    for idx, (table_name, info) in enumerate(tables_info.items(), 1):
        parts = [f"{idx}. **{table_name}** ({info.get('description', '데이터 테이블')})"]
        if info.get('purpose'):
            parts.append(f"   - 용도: {info['purpose']}")
        if info.get('primary_key'):
            parts.append(f"   - Primary Key: {', '.join(info['primary_key'])}")
        if info.get('foreign_keys'):
            refs = set(v['references'] for v in info['foreign_keys'].values())
            parts.append(f"   - 조인 가능: {', '.join(refs)}")
        if info.get('provides'):
            p = info['provides']
            if p.get('dimensions'):
                parts.append(f"   - 제공 차원: {', '.join(p['dimensions'][:5])}")
            if p.get('measures'):
                parts.append(f"   - 제공 측정값: {', '.join(p['measures'])}")
        if info.get('keywords'):
            parts.append(f"   - 관련 키워드: {', '.join(info['keywords'])}")
        if info.get('examples'):
            parts.append("   - 답변 가능 예시:")
            for ex in info['examples'][:2]:
                parts.append(f'     * "{ex}"')
        descriptions.append('\n'.join(parts))
    return '\n\n'.join(descriptions)


def _build_available_data_summary(tables_info: Dict[str, Dict]) -> str:
    """사용 가능한 데이터의 간단한 요약"""
    summaries = [info.get('description', name) for name, info in tables_info.items()]
    if len(summaries) == 1:
        return summaries[0]
    elif len(summaries) == 2:
        return f"{summaries[0]}와 {summaries[1]}"
    else:
        return ", ".join(summaries[:-1]) + f" 및 {summaries[-1]}"


def classify_question_and_table(question: str, llm, available_tables: Dict[str, Dict], log_ctx: dict = None) -> dict:
    """질문이 DB로 답변 가능한지 판단하고 PRIMARY 테이블 선택"""
    if not question:
        first_table = list(available_tables.keys())[0] if available_tables else None
        return {"is_answerable": bool(first_table), "table": first_table, "confidence": 1.0,
                "reasoning": "기본값", "suggestion": None}

    tables_description = _build_tables_description_with_relationships(available_tables)
    available_data_summary = _build_available_data_summary(available_tables)
    table_names = list(available_tables.keys())

    classification_prompt = f"""다음 질문을 분석하여:
1. 현재 사용 가능한 데이터베이스로 답변 가능한 질문인지 판단
2. 답변 가능하다면 **PRIMARY(주요) 테이블** 선택

**현재 사용 가능한 데이터베이스:**
{tables_description}

**사용자 질문:**
{question}

**PRIMARY 테이블 선택 규칙:**
1. 질문에서 요구하는 컬럼들(필터/집계/그룹화)을 파악
2. 해당 컬럼이 가장 많이 있는 테이블을 PRIMARY로 선택
3. 선택 우선순위: 집계 대상 컬럼 > 그룹화 차원 컬럼 > 조인 용이성

예시:
- "북미의 카테고리별 매출" → PRIMARY: view_SalesOrderDetail (categoryname, LineTotal 보유)
- "2024년 지역별 주문 건수" → PRIMARY: view_SalesOrderHeader (OrderDate, TerritoryName 보유)

**답변 불가 시:**
- is_answerable: false
- suggestion: "현재 제공 가능한 정보는 {available_data_summary}입니다"

**답변 가능 시:**
- is_answerable: true
- table: 반드시 {', '.join(table_names)} 중 하나 (정확한 이름 사용)
- confidence: 신뢰도
- reasoning: 선택 이유
"""

    result = classify_with_llm(
        prompt=classification_prompt,
        llm=llm,
        output_schema=QuestionClassification,
        log_ctx=log_ctx,
        stepnm='classifier',
        steptitle='질문 분류',
    )

    return {
        "is_answerable": result.is_answerable,
        "table": result.table,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "suggestion": result.suggestion,
    }


def classify_tables_for_report(request: str, llm, available_tables: Dict[str, Dict],
                               log_ctx: dict = None) -> dict:
    """보고서 요청 → 그 보고서에 필요한 테이블 **전부**.

    한 질문에 답하는 classify_question_and_table과 목적이 다르다. 보고서는 목차(스텝)마다
    다른 데이터를 볼 수 있어 한 테이블로 끝나지 않는다(경영분석은 판매, 생산지수는 생산).
    스텝별 쿼리는 여기서 고른 목록 안에서 만들어진다.
    """
    if not request:
        return {"is_answerable": bool(available_tables),
                "tables": list(available_tables.keys()), "reasoning": "기본값", "suggestion": None}

    tables_description = _build_tables_description_with_relationships(available_tables)
    available_data_summary = _build_available_data_summary(available_tables)
    table_names = list(available_tables.keys())

    prompt = f"""다음 보고서 요청을 분석하여, 이 보고서를 작성하는 데 **필요한 테이블을 전부** 고르세요.

**현재 사용 가능한 데이터베이스:**
{tables_description}

**보고서 요청:**
{request}

**선택 규칙:**
1. 보고서는 여러 목차로 이뤄지고, 목차마다 다른 데이터를 볼 수 있습니다. 하나만 고르지 마세요.
2. 요청이 다루는 주제에 실제로 쓰이는 테이블만 고르세요. 관련 없는 테이블을 넣지 마세요.
3. 고른 테이블과 조인해야 값이 완성되는 테이블(헤더/상세 관계 등)이 있으면 함께 고르세요.
4. 어느 테이블로도 이 보고서를 만들 수 없으면 is_answerable을 false로 하고,
   suggestion에 "현재 제공 가능한 정보는 {available_data_summary}입니다"를 넣으세요.

**tables:** 반드시 {', '.join(table_names)} 중에서 정확한 이름으로 고르세요.
**reasoning:** 각 테이블이 이 보고서의 어느 부분에 쓰이는지 한 줄씩 적으세요.
"""

    result = classify_with_llm(
        prompt=prompt,
        llm=llm,
        output_schema=ReportTableSelection,
        log_ctx=log_ctx,
        stepnm='report_tables',
        steptitle='보고서 데이터 선택',
    )

    return {
        "is_answerable": result.is_answerable,
        "tables": [t for t in result.tables if t in available_tables],
        "reasoning": result.reasoning,
        "suggestion": result.suggestion,
    }
