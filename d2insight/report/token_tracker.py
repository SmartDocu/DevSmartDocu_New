"""LLM 토큰 사용량 추적기."""
from __future__ import annotations

import threading
from contextvars import ContextVar

_local = threading.local()
_provider_var: ContextVar[str] = ContextVar("llm_provider", default="")


def reset() -> None:
    _local.input_tokens = 0
    _local.output_tokens = 0
    _local.calls = []
    _local.current_section = ""
    _local.provider = ""


def set_provider(provider: str) -> None:
    _local.provider = provider or ""
    _provider_var.set(provider or "")


def get_provider() -> str:
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


def get() -> dict:
    return {
        "input": getattr(_local, "input_tokens", 0),
        "output": getattr(_local, "output_tokens", 0),
        "calls": list(getattr(_local, "calls", [])),
    }


def set_current_section(name: str) -> None:
    _local.current_section = name


def get_current_section() -> str:
    return getattr(_local, "current_section", "")


_lock = threading.Lock()
_session_tokens: dict[str, list[dict]] = {}


def record_turn(session_id: str, qa_id: str, tokens: dict) -> None:
    with _lock:
        if session_id not in _session_tokens:
            _session_tokens[session_id] = []
        _session_tokens[session_id].append({qa_id: tokens})


def get_session_total(session_id: str) -> dict | None:
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
