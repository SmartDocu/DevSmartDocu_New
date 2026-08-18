"""엔진 전용 LLM 호출 shim.

스냅샷(pr_module_insight_202608061005)의 `src/llm/client.py`를 대체한다 — 자체
Anthropic/OpenAI 키·모델 관리 대신, d2insight/chat 라우터가 이미 쓰는
`utilsPrj.ai_chain`(프로젝트/테넌트별 LLM 선택) + `d2insight.token_tracker`(비동기 컨텍스트
인식 토큰 기록)를 그대로 재사용한다.

엔진 쪽 호출부(entry.py, catalog/*.py, chat_options.py 등)는 시그니처만 같으면 되므로
`from src.llm.client import chat` → `from d2insight.engine._llm import chat`로 바꿔치기만
했다. 엔진 함수들은 project_id/tenant_id 등을 인자로 받지 않으므로, 여기서는 router.py가
요청 시작 시 `token_tracker.set_log_ctx()`로 남겨둔 값을 읽어 LLM을 고른다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

Grade = Literal["fast", "balanced", "quality"]


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
    """단일 턴 LLM 호출. assistant 텍스트를 반환한다."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from d2insight import token_tracker
    from utilsPrj.ai_chain import build_langchain_llm, get_llm_info

    log_ctx = token_tracker.get_log_ctx() or {}
    project_id = log_ctx.get("project_id")
    tenant_id = log_ctx.get("tenant_id")
    user_uid = log_ctx.get("creator")
    account_uid = log_ctx.get("account_uid")

    # service_code="In"이면 models가 문자열이 아니라 {"fast":.., "balanced":.., "quality":..} dict다.
    models, api_key, vendor, _, _ = get_llm_info(
        project_id=project_id, tenant_id=tenant_id,
        user_uid=user_uid, account_uid=account_uid, service_code="In",
    )
    model_id = models[grade] if isinstance(models, dict) else models
    llm = build_langchain_llm(vendor, api_key, model_id)

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

    print(f"[engine LLM] vendor={vendor}  model={model_id}  grade={grade}  label={label or '-'}")
    _start = datetime.now()
    resp = llm.invoke(lc_messages)
    _end = datetime.now()

    # 토큰 추출: usage_metadata 우선 (LangChain 통일 형식), fallback → response_metadata
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
        model_id=model_id, provider=(provider or vendor or ""),
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
