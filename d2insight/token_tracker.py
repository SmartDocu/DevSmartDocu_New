"""LLM 토큰 사용량 추적기.

사용 흐름:
  1. 요청 시작  — router.py: token_tracker.reset()
  2. LLM 호출마다 — agent / sql_generator: token_tracker.add(...)
  3. 요청 완료  — router.py: token_tracker.get() → 답변 끝에 토큰 표시
  4. QA 저장 후 — router.py: token_tracker.record_turn(session_id, qa_id, tokens)

세션 합계 조회:
  token_tracker.get_session_total(session_id)
  → calls 목록 포함 (is_report 플래그로 보고서/일반 구분)

DB 열 준비 시:
  record_turn() 안의 TODO 블록을 활성화하면 Supabase에 직접 기록된다.
"""
from __future__ import annotations

import threading
from contextvars import ContextVar

# ── 요청 단위 누산 (스레드-로컬) ─────────────────────────────────────────

_local = threading.local()

# asyncio.run_in_executor (LangGraph ToolNode) 스레드에도 provider 값이 전파되도록 ContextVar 사용
_provider_var: ContextVar[str] = ContextVar("llm_provider", default="")

# LLM 즉시 로깅용 컨텍스트 — ThreadPoolExecutor 워커 스레드에도 자동 복사됨
_log_ctx_var: ContextVar[dict | None] = ContextVar("llm_log_ctx", default=None)


def set_log_ctx(ctx: dict | None) -> None:
    """요청 시작 시 호출 — log_llm_call에 전달할 컨텍스트를 설정한다."""
    _log_ctx_var.set(ctx)


def get_log_ctx() -> dict | None:
    return _log_ctx_var.get()


def reset() -> None:
    """요청 시작 시 호출 — 현재 스레드의 카운터와 호출 목록을 초기화한다."""
    _local.input_tokens = 0
    _local.output_tokens = 0
    _local.calls = []
    _local.current_section = ""
    _local.provider = ""


def set_provider(provider: str) -> None:
    """현재 요청의 LLM provider를 스레드-로컬과 ContextVar에 저장한다."""
    _local.provider = provider or ""
    _provider_var.set(provider or "")


def get_provider() -> str:
    """현재 요청의 LLM provider를 반환한다. 미설정 시 'anthropic'.

    ContextVar를 우선 확인 — LangGraph ToolNode가 run_in_executor로 호출하는
    새 스레드에서도 asyncio가 ContextVar 값을 복사하므로 올바른 provider가 반환된다.
    """
    cv = _provider_var.get()
    if cv:
        return cv
    return getattr(_local, "provider", "") or "anthropic"


def add(
    input_tokens: int,
    output_tokens: int,
    grade: str = "balanced",
    label: str = "",
    is_report: bool = False,
    stepnm: str = "",
    steptitle: str = "",
    call_type: str = "",
    model_id: str = "",
    provider: str = "",
    startdts=None,
    enddts=None,
) -> None:
    """LLM 호출 완료 후 호출 — 누산 카운터에 더하고 호출 목록에 기록한다.

    grade: "fast" | "balanced" | "quality"
    label: 폴백용 항목명 (call_type 없을 때 표에 표시)
    is_report: 보고서 작성에 사용된 호출이면 True (보고서 합계 산출 기준)
    stepnm: 보고서 스텝명 (예: "섹션 계획", "본문", "종합")
    steptitle: 섹션 타이틀 (예: "월별 매출 추이")
    call_type: 호출 유형 (예: "툴 호출", "쿼리 생성", "항목 작성(차트)")
    model_id: 실제 모델 ID (예: "claude-haiku-4-5-20251001") — llm_api_logs.llmmodelnm 저장용
    provider: "anthropic" | "openai" — 표시명 분기 및 로그 기록용
    startdts / enddts: LLM 호출 시작·완료 datetime (datetime.now() 기준)
    """
    if not hasattr(_local, "input_tokens"):
        reset()
    _local.input_tokens += input_tokens
    _local.output_tokens += output_tokens

    _prov = provider or getattr(_local, "provider", "") or "anthropic"

    _local.calls.append({
        "label": label or model_id or grade,
        "model": model_id or grade,
        "model_id": model_id,
        "provider": _prov,
        "input": input_tokens,
        "output": output_tokens,
        "is_report": is_report,
        "stepnm": stepnm,
        "steptitle": steptitle,
        "call_type": call_type,
        "startdts": startdts,
        "enddts": enddts,
    })

    # 즉시 로깅 — ContextVar가 설정된 경우 각 LLM 호출 완료 시점에 DB에 기록
    _ctx = _log_ctx_var.get()
    if _ctx:
        try:
            from d2shared.llm_logger import log_llm_call
            log_llm_call(
                log_ctx={**_ctx, "questiontypecd": "R" if is_report else "S"},
                stepnm=stepnm,
                steptitle=steptitle,
                llmmodelnm=model_id or grade,
                inputtoken=input_tokens,
                outputtoken=output_tokens,
                startdts=startdts,
                enddts=enddts,
            )
        except Exception as _e:
            print(f"[token_tracker] llm_api_logs 즉시 로깅 실패 (건너뜀): {_e}")


def get() -> dict:
    """현재 요청(스레드)의 누적 합계와 호출 목록을 반환한다."""
    return {
        "input": getattr(_local, "input_tokens", 0),
        "output": getattr(_local, "output_tokens", 0),
        "calls": list(getattr(_local, "calls", [])),
    }


def merge_calls(calls: list[dict]) -> None:
    """Worker 스레드의 call 기록을 현재(메인) 스레드 tracker에 병합한다."""
    if not hasattr(_local, "calls"):
        reset()
    for call in calls:
        _local.calls.append(call)
        _local.input_tokens = getattr(_local, "input_tokens", 0) + call.get("input", 0)
        _local.output_tokens = getattr(_local, "output_tokens", 0) + call.get("output", 0)


def set_current_section(name: str) -> None:
    """섹션 루프 진입 시 호출 — 현재 작성 중인 섹션명을 스레드-로컬에 저장한다."""
    _local.current_section = name


def get_current_section() -> str:
    """현재 작성 중인 섹션명을 반환한다. 없으면 빈 문자열."""
    return getattr(_local, "current_section", "")


# ── 세션별 턴 기록 (인메모리) ─────────────────────────────────────────────
# 구조: {session_id: [{qa_id: {"input": N, "output": N, "calls": [...]}}, ...]}

_lock = threading.Lock()
_session_tokens: dict[str, list[dict]] = {}


def record_turn(session_id: str, qa_id: str, tokens: dict) -> None:
    """QA 한 턴의 토큰 정보를 세션 딕셔너리에 기록한다.

    tokens: {"input": N, "output": N, "calls": [...]}
    """
    with _lock:
        if session_id not in _session_tokens:
            _session_tokens[session_id] = []
        _session_tokens[session_id].append({qa_id: tokens})

    # TODO: DB 열 준비 시 아래 블록 활성화
    # from app.db import insight_storage
    # insight_storage.update_qa_tokens(
    #     qa_id=qa_id,
    #     input_tokens=tokens["input"],
    #     output_tokens=tokens["output"],
    # )


def get_session_total(session_id: str) -> dict | None:
    """세션 전체 토큰 합계와 호출 목록을 반환한다. 기록 없으면 None."""
    with _lock:
        turns = _session_tokens.get(session_id, [])
    if not turns:
        return None

    all_calls: list[dict] = []
    for turn in turns:
        qa_data = list(turn.values())[0]
        all_calls.extend(qa_data.get("calls", []))

    total_in = sum(c["input"] for c in all_calls)
    total_out = sum(c["output"] for c in all_calls)
    return {
        "input": total_in,
        "output": total_out,
        "turns": len(turns),
        "calls": all_calls,
    }
