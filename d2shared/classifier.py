"""
classifier.py — LLM structured output 범용 분류기

d2chat  : QuestionClassification (어떤 DB 테이블을 쓸지)
d2insight: ReportClassification  (어떤 분석 툴/보고서 유형을 쓸지)
각 앱에서 Pydantic 스키마를 정의하고 classify_with_llm에 주입한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Type

from pydantic import BaseModel

from d2shared.llm_logger import log_llm_call


def classify_with_llm(
    prompt: str,
    llm,
    output_schema: Type[BaseModel],
    log_ctx: Optional[dict] = None,
    stepnm: str = 'classifier',
    steptitle: str = '질문 분류',
):
    """LLM structured output으로 범용 분류를 수행하고 파싱된 Pydantic 인스턴스를 반환한다.

    Args:
        prompt       : LLM에 전달할 분류 프롬프트
        llm          : LangChain LLM 객체 (with_structured_output 지원)
        output_schema: 결과를 담을 Pydantic BaseModel 서브클래스
        log_ctx      : llmchatlogs/llminsightlogs 기록용 컨텍스트 dict (없으면 로그 생략)
        stepnm       : 로그 step 이름
        steptitle    : 로그 step 제목
    Returns:
        output_schema 인스턴스 (parsed Pydantic model)
    """
    structured_llm = llm.with_structured_output(output_schema, include_raw=True)

    start = datetime.now()
    raw = structured_llm.invoke(prompt)
    end = datetime.now()

    result = raw.get('parsed') if isinstance(raw, dict) else raw
    raw_msg = raw.get('raw') if isinstance(raw, dict) else None
    usage = getattr(raw_msg, 'usage_metadata', None) or {}

    log_llm_call(
        log_ctx=log_ctx,
        stepnm=stepnm,
        steptitle=steptitle,
        llmmodelnm=getattr(llm, 'model', 'unknown'),
        inputtoken=usage.get('input_tokens', 0),
        outputtoken=usage.get('output_tokens', 0),
        is_success=True,
        startdts=start,
        enddts=end,
    )

    return result
