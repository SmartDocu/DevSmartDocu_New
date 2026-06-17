"""
llm_logger.py — LLM API 호출 로그 저장 (llm_api_logs 테이블)
d2chat, d2insight 공통 사용.
"""
from datetime import datetime
from typing import Optional

from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA


def _q(table: str):
    return get_supabase_client().schema(SUPABASE_SCHEMA).table(table)


def log_llm_call(
    log_ctx: Optional[dict],
    stepnm: str,
    steptitle: str,
    llmmodelnm: str,
    inputtoken: int,
    outputtoken: int,
    status: str = 'C',
    errorcd: Optional[str] = None,
    errormessage: Optional[str] = None,
    startdts: Optional[datetime] = None,
    enddts: Optional[datetime] = None,
) -> None:
    """llm_api_logs에 한 행 삽입. log_ctx가 없거나 실패해도 예외를 전파하지 않음."""
    if not log_ctx:
        return
    try:
        _q("llm_api_logs").insert({
            "qauid":          log_ctx.get("qauid"),
            "servicecd":      log_ctx.get("servicecd", "C"),
            "questiontypecd": log_ctx.get("questiontypecd", "S"),
            "tenantid":       log_ctx.get("tenant_id"),
            "projectid":      log_ctx.get("project_id"),
            "sessionuid":     log_ctx.get("session_uid"),
            "stepnm":         stepnm,
            "steptitle":      steptitle,
            "llmmodelnm":     llmmodelnm,
            "inputtoken":     inputtoken,
            "outputtoken":    outputtoken,
            "status":         status,
            "errorcd":        errorcd,
            "errormessage":   errormessage,
            "creator":        log_ctx.get("creator"),
            "startdts":       startdts.isoformat() if startdts else None,
            "enddts":         enddts.isoformat() if enddts else None,
        }).execute()
    except Exception as e:
        print(f"[llm_logger] 로그 저장 실패: {e}")
