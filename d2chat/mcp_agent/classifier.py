"""질문 적합성 및 테이블 분류."""
from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class QuestionClassification(BaseModel):
    is_answerable: bool = Field(description="DB로 답변 가능한 질문인지 여부")
    table: Optional[str] = Field(default=None, description="선택된 테이블 이름")
    confidence: float = Field(description="신뢰도 (0.0~1.0)", ge=0.0, le=1.0)
    reasoning: str = Field(description="판단 이유")
    suggestion: Optional[str] = Field(default=None, description="답변 불가 시 안내 메시지")


def _build_tables_description_with_relationships(tables_info: Dict[str, Dict]) -> str:
    descriptions = []
    for idx, (table_name, info) in enumerate(tables_info.items(), 1):
        parts = [f"{idx}. **{table_name}** ({info.get('description', '데이터 테이블')})"]
        if info.get("purpose"):
            parts.append(f"   - 용도: {info['purpose']}")
        if info.get("primary_key"):
            parts.append(f"   - Primary Key: {', '.join(info['primary_key'])}")
        if info.get("foreign_keys"):
            refs = set(v["references"] for v in info["foreign_keys"].values())
            parts.append(f"   - 조인 가능: {', '.join(refs)}")
        if info.get("provides"):
            p = info["provides"]
            if p.get("dimensions"):
                parts.append(f"   - 제공 차원: {', '.join(p['dimensions'][:5])}")
            if p.get("measures"):
                parts.append(f"   - 제공 측정값: {', '.join(p['measures'])}")
        if info.get("keywords"):
            parts.append(f"   - 관련 키워드: {', '.join(info['keywords'])}")
        if info.get("examples"):
            parts.append("   - 답변 가능 예시:")
            for ex in info["examples"][:2]:
                parts.append(f'     * "{ex}"')
        descriptions.append("\n".join(parts))
    return "\n\n".join(descriptions)


def _build_available_data_summary(tables_info: Dict[str, Dict]) -> str:
    summaries = [info.get("description", name) for name, info in tables_info.items()]
    if len(summaries) == 1:
        return summaries[0]
    elif len(summaries) == 2:
        return f"{summaries[0]}와 {summaries[1]}"
    return ", ".join(summaries[:-1]) + f" 및 {summaries[-1]}"


def classify_question_and_table(
    question: str,
    llm,
    available_tables: Dict[str, Dict],
    log_ctx: dict = None,
) -> dict:
    if not question:
        first_table = list(available_tables.keys())[0] if available_tables else None
        return {"is_answerable": True, "table": first_table, "confidence": 1.0,
                "reasoning": "기본값", "suggestion": None}

    structured_llm = llm.with_structured_output(QuestionClassification, include_raw=True)
    tables_description = _build_tables_description_with_relationships(available_tables)
    available_data_summary = _build_available_data_summary(available_tables)
    table_names = list(available_tables.keys())

    prompt = f"""다음 질문을 분석하여:
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

**답변 불가 시:**
- is_answerable: false
- suggestion: "현재 제공 가능한 정보는 {available_data_summary}입니다"

**답변 가능 시:**
- is_answerable: true
- table: 반드시 {', '.join(table_names)} 중 하나 (정확한 이름 사용)
- confidence: 신뢰도
- reasoning: 선택 이유
"""

    from d2chat.history.llm_logger import log_llm_call

    start = datetime.now()
    raw = structured_llm.invoke(prompt)
    end = datetime.now()

    result = raw.get("parsed") if isinstance(raw, dict) else raw
    raw_msg = raw.get("raw") if isinstance(raw, dict) else None
    usage = getattr(raw_msg, "usage_metadata", None) or {}
    log_llm_call(
        log_ctx=log_ctx,
        stepnm="classifier",
        steptitle="질문 분류",
        llmmodelnm=getattr(llm, "model", "unknown"),
        inputtoken=usage.get("input_tokens", 0),
        outputtoken=usage.get("output_tokens", 0),
        startdts=start,
        enddts=end,
    )

    return {
        "is_answerable": result.is_answerable,
        "table":         result.table,
        "confidence":    result.confidence,
        "reasoning":     result.reasoning,
        "suggestion":    result.suggestion,
    }
