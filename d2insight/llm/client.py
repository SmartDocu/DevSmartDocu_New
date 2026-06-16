"""LLM SDK 래퍼 — 호출별 모델 등급 라우팅 (Anthropic / OpenAI)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from d2insight.report import token_tracker

Grade = Literal["fast", "balanced", "quality"]

ANTHROPIC_MODELS: dict[str, str] = {
    "fast":     "claude-haiku-4-5-20251001",
    "balanced": "claude-sonnet-4-6",
    "quality":  "claude-opus-4-7",
}
OPENAI_MODELS: dict[str, str] = {
    "fast":     "gpt-5.4-mini",
    "balanced": "gpt-5.4",
    "quality":  "gpt-5.5",
}


def chat(
    messages: list[dict],
    *,
    grade: Grade = "balanced",
    system: str | None = None,
    max_tokens: int = 8192,
    label: str = "",
    is_report: bool = False,
    stepnm: str = "",
    steptitle: str = "",
    call_type: str = "",
    provider: str | None = None,
) -> str:
    from backend.app.config import settings
    _provider = provider or "anthropic"

    lc_messages = []
    if system:
        lc_messages.append(SystemMessage(content=system))
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    if _provider == "anthropic":
        model_id = ANTHROPIC_MODELS[grade]
        model = ChatAnthropic(
            model=model_id,
            max_tokens=max_tokens,
            api_key=settings.CLAUDE_API_KEY,
        )
    elif _provider == "openai":
        model_id = OPENAI_MODELS[grade]
        model = ChatOpenAI(
            model=model_id,
            max_tokens=max_tokens,
            api_key=settings.OPENAI_API_KEY,
        )
    else:
        raise ValueError(f"지원하지 않는 LLM provider: {_provider!r}")

    print(f"[LLM] provider={_provider}  model={model_id}  grade={grade}  label={label or '-'}")
    _start = datetime.now()
    resp = model.invoke(lc_messages)
    _end = datetime.now()

    um = getattr(resp, "usage_metadata", None) or {}
    input_tokens = um.get("input_tokens", 0)
    output_tokens = um.get("output_tokens", 0)
    if not input_tokens and not output_tokens:
        rm = resp.response_metadata.get("usage", {}) if hasattr(resp, "response_metadata") else {}
        input_tokens = rm.get("input_tokens", 0) or rm.get("prompt_tokens", 0)
        output_tokens = rm.get("output_tokens", 0) or rm.get("completion_tokens", 0)

    token_tracker.add(
        input_tokens, output_tokens,
        grade=grade, label=label, is_report=is_report,
        stepnm=stepnm, steptitle=steptitle, call_type=call_type,
        model_id=model_id, provider=_provider,
        startdts=_start, enddts=_end,
    )

    content = resp.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
            if not isinstance(block, dict) or block.get("type") == "text"
        )
    return str(content)
