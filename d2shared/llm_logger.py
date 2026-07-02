"""
llm_logger.py — LLM API 호출 로그 저장.
d2doc → sdoc.llmdoclogs, d2chat → sdoc.llmchatlogs, d2insight → sdoc.llminsightlogs
(기존 단일 테이블 sdoc.llm_api_logs를 서비스별로 분리)
"""
from datetime import datetime
from typing import Optional

from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA

_SERVICE_TABLE = {"Ch": "llmchatlogs", "In": "llminsightlogs"}


def _q(table: str):
    return get_supabase_client().schema(SUPABASE_SCHEMA).table(table)


def log_llm_call(
    log_ctx: Optional[dict],
    stepnm: str,
    steptitle: str,
    llmmodelnm: str,
    inputtoken: int,
    outputtoken: int,
    is_success: bool = False,
    errorcd: Optional[str] = None,
    errormessage: Optional[str] = None,
    startdts: Optional[datetime] = None,
    enddts: Optional[datetime] = None,
) -> None:
    """d2chat/d2insight 공통 — log_ctx["servicecd"]("Ch"/"In")에 따라
    llmchatlogs/llminsightlogs에 한 행 삽입. log_ctx가 없거나 실패해도 예외를 전파하지 않음.

    is_success는 과금 기준(성공만 과금)이므로 호출부가 실제 생성 결과를 보고
    명시적으로 판별해 전달해야 한다. 기본값은 False — 값을 깜빡 전달하지 않았을 때
    성공으로 잘못 집계되는 것(과다 과금 위험)보다 누락되는 편이 안전하다.
    """
    if not log_ctx:
        return
    table = _SERVICE_TABLE.get(log_ctx.get("servicecd"))
    if not table:
        print(f"[llm_logger] 알 수 없는 servicecd={log_ctx.get('servicecd')!r} — 로그 생략")
        return
    try:
        _q(table).insert({
            "qauid":             log_ctx.get("qauid"),
            "questiontypecd":    log_ctx.get("questiontypecd", "S"),
            "tenantid":          log_ctx.get("tenant_id"),
            "accountuid":        log_ctx.get("account_uid"),
            "projectid":         log_ctx.get("project_id"),
            "sessionuid":        log_ctx.get("session_uid"),
            "stepnm":            stepnm,
            "steptitle":         steptitle,
            "llmmodelnm":        llmmodelnm,
            "inputtoken":        inputtoken,
            "outputtoken":       outputtoken,
            "is_success":        is_success,
            "errorcd":           errorcd,
            "errormessage":      errormessage,
            "is_customeraikey":  log_ctx.get("is_customeraikey"),
            "creator":           log_ctx.get("creator"),
            "startdts":          startdts.isoformat() if startdts else None,
            "enddts":            enddts.isoformat() if enddts else None,
        }).execute()
    except Exception as e:
        print(f"[llm_logger] 로그 저장 실패: {e}")


def log_doc_llm_call(
    log_ctx: Optional[dict],
    llmmodelnm: str,
    inputtoken: int,
    outputtoken: int,
    is_success: bool = False,
    errorcd: Optional[str] = None,
    errormessage: Optional[str] = None,
    startdts: Optional[datetime] = None,
    enddts: Optional[datetime] = None,
) -> None:
    """d2doc 전용 — sdoc.llmdoclogs에 한 행 삽입.

    log_ctx 키:
      tenant_id, account_uid, project_id, is_customeraikey, creator,
      gencontenttypecd ("D"=문서 전체, "C"=챕터, "O"=단일 항목, None=단독/Definition),
      gendocjobuid, genchapterjobuid, genobjectuid, objectuid
    log_ctx가 없거나 실패해도 예외를 전파하지 않음.

    is_success는 과금 기준(성공만 과금)이므로 호출부가 실제 생성 결과를 보고
    명시적으로 판별해 전달해야 한다. 기본값은 False — 값을 깜빡 전달하지 않았을 때
    성공으로 잘못 집계되는 것(과다 과금 위험)보다 누락되는 편이 안전하다.
    """
    if not log_ctx:
        return
    try:
        _q("llmdoclogs").insert({
            "tenantid":          log_ctx.get("tenant_id"),
            "accountuid":        log_ctx.get("account_uid"),
            "projectid":         log_ctx.get("project_id"),
            "gencontenttypecd":  log_ctx.get("gencontenttypecd"),
            "gendocjobuid":      log_ctx.get("gendocjobuid"),
            "genchapterjobuid":  log_ctx.get("genchapterjobuid"),
            "genobjectuid":      log_ctx.get("genobjectuid"),
            "objectuid":         log_ctx.get("objectuid"),
            "llmmodelnm":        llmmodelnm,
            "inputtoken":        inputtoken,
            "outputtoken":       outputtoken,
            "is_success":        is_success,
            "errorcd":           errorcd,
            "errormessage":      errormessage,
            "is_customeraikey":  log_ctx.get("is_customeraikey"),
            "creator":           log_ctx.get("creator"),
            "startdts":          startdts.isoformat() if startdts else None,
            "enddts":            enddts.isoformat() if enddts else None,
        }).execute()
    except Exception as e:
        print(f"[llm_logger] 로그 저장 실패(doc): {e}")
