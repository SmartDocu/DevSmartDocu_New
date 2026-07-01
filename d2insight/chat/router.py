"""Insight Chat API router."""
from __future__ import annotations

import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from d2insight.chat.intent_parser import parse_intent
from d2insight.chat.pipeline_runner import run_tool, run_report_from_spec
from d2insight.chat import session as _session
from d2insight.chat import report_spec as _spec_mod
from d2insight.db import insight_storage as storage
from d2insight import token_tracker

router = APIRouter()


# ── 요청 모델 ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    account_uid: str | None = None  # 프론트 authStore에서 전달 (serviceusers 조회 생략용)


class FavoriteQARequest(BaseModel):
    user_id: str
    qauid: str


class ShareRequest(BaseModel):
    user_id: str
    qauid: str
    folder_uid: Optional[str] = None


class InjectRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    question: str
    answer: str
    visualization_type: str = "none"
    table_html: str | None = None
    report_path: str | None = None


# ── 응답 모델 ─────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    answer: str
    session_id: str
    visualization_type: str = "none"
    table_html: str | None = None
    chart_image: str | None = None
    report_path: str | None = None
    fileurl: str | None = None
    qauid: str | None = None


# ── 채팅 ─────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    token_tracker.reset()

    try:
        sid, hist = _session.get_or_create(req.session_id, user_id=req.user_id, project_id=req.project_id)
    except Exception as e:
        print(f"[session] get_or_create 실패 (fallback): {e}")
        sid = req.session_id or str(_uuid.uuid4())
        hist = []

    # project_id/tenant_id 확보 (LLM 조회에 사용)
    _project_id = req.project_id
    _tenant_id: int | None = None
    if req.user_id:
        try:
            _tenant_id, _pid = storage.get_project_info(req.user_id)
            if _project_id is None:
                _project_id = _pid
        except Exception:
            pass

    # 파이프라인 실행 전 log_ctx 설정 — token_tracker.add()에서 LLM 호출마다 즉시 DB 기록
    token_tracker.set_log_ctx({
        "qauid": None,
        "servicecd": "In",
        "tenant_id": _tenant_id,
        "project_id": _project_id,
        "session_uid": sid,
        "creator": req.user_id,
        "account_uid": req.account_uid,
    })

    # ── 대화형 보고서 작성 진행 중 ───────────────────────────────────────
    active_spec = _spec_mod.get_spec(sid)
    if active_spec:
        updated_spec, bot_response = _spec_mod.advance_spec(
            sid, req.message, history=hist, project_id=_project_id, tenant_id=_tenant_id,
            user_uid=req.user_id, account_uid=req.account_uid,
        )
        if bot_response == "__EXECUTE__":
            result = run_report_from_spec(updated_spec, req.user_id,
                                          project_id=_project_id, tenant_id=_tenant_id,
                                          account_uid=req.account_uid)
            _spec_mod.clear_spec(sid)
        elif bot_response == "__CANCEL__":
            result = {
                "answer": "보고서 작성을 취소했습니다. 다른 작업을 도와드릴까요?",
                "visualization_type": "none", "table_html": None,
                "chart_image": None, "report_path": None,
            }
        else:
            result = {
                "answer": bot_response,
                "visualization_type": "none", "table_html": None,
                "chart_image": None, "report_path": None,
            }
    else:
        # ── 기존 플로우 ────────────────────────────────────────────────────
        intent = parse_intent(req.message, project_id=_project_id, tenant_id=_tenant_id,
                              user_uid=req.user_id, account_uid=req.account_uid)
        intent["original_message"] = req.message
        tool = intent.get("tool", "chat")
        target_month = intent.get("target_month")
        months_back = intent.get("months_back", 3)

        if tool == "report" and (intent.get("mode") == "start" or not target_month):
            spec = _spec_mod.create_spec(
                target_month=target_month,
                report_type=intent.get("report_type"),
            )
            if target_month:
                spec["entry_asked"] = True
                answer = _spec_mod.ENTRY_QUESTION
            else:
                answer = "어느 기간의 보고서인가요? (예: 2013년 11월)"
            _spec_mod.save_spec(sid, spec)
            result = {
                "answer": answer,
                "visualization_type": "none", "table_html": None,
                "chart_image": None, "report_path": None,
            }
        else:
            result = run_tool(tool, target_month, months_back, history=hist, intent=intent,
                              user_id=req.user_id, project_id=_project_id, tenant_id=_tenant_id,
                              user_uid=req.user_id, account_uid=req.account_uid)

    tokens = token_tracker.get()

    qauid: Optional[str] = None
    calls = tokens.get("calls", [])
    questiontypecd = "R" if any(c.get("is_report") for c in calls) else "S"
    try:
        answer_json = {
            "answer": result.get("answer", ""),
            "visualization_type": result.get("visualization_type", "none"),
            "table_html": result.get("table_html"),
        }
        qauid = _session.append_qa(
            sid, req.message, answer_json,
            user_id=req.user_id,
            project_id=req.project_id,
            filenm=result.get("report_path"),
            fileurl=result.get("fileurl"),
            inputtoken=tokens["input"] or None,
            outputtoken=tokens["output"] or None,
            servicecd="In",
        )
    except Exception as e:
        print(f"[session] append_qa 실패 (저장 건너뜀): {e}")

    if qauid and (tokens["input"] or tokens["output"]):
        token_tracker.record_turn(sid, qauid, tokens)
    token_tracker.set_log_ctx(None)

    return ChatResponse(session_id=sid, qauid=qauid, **result)


# ── 이어가기 ─────────────────────────────────────────────────────

@router.post("/session/inject")
def inject_qa(body: InjectRequest):
    """과거 Q&A를 현재(또는 새) 세션에 이어붙인다."""
    try:
        sid, _ = _session.get_or_create(body.session_id, user_id=body.user_id, project_id=body.project_id)
    except Exception:
        sid = body.session_id or str(_uuid.uuid4())

    try:
        answer_json = {
            "answer": body.answer,
            "visualization_type": body.visualization_type,
            "table_html": body.table_html,
        }
        _session.append_qa(sid, body.question, answer_json, user_id=body.user_id, project_id=body.project_id, filenm=body.report_path)
    except Exception as e:
        print(f"[inject] append_qa 실패: {e}")

    return {"ok": True, "session_id": sid}


# ── 히스토리 ─────────────────────────────────────────────────────

@router.get("/history/{user_id}")
def get_history(user_id: str):
    """날짜별로 그룹화된 세션 목록 반환."""
    return storage.get_history_by_date(user_id)


@router.get("/history/{user_id}/{session_id}")
def get_session_messages(user_id: str, session_id: str):
    """세션의 Q&A 메시지 목록 반환."""
    messages = storage.get_session_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"session_id": session_id, "messages": messages}


@router.delete("/history/{user_id}/{session_id}")
def delete_session(user_id: str, session_id: str):
    storage.delete_session(session_id, user_id)
    return {"ok": True}


# ── 즐겨찾기 ─────────────────────────────────────────────────────

@router.get("/favorites/{user_id}")
def get_favorites(user_id: str):
    return storage.get_favorites(user_id)


@router.post("/favorite/qa")
def add_favorite_qa(body: FavoriteQARequest):
    ok = storage.add_favorite_qa(body.qauid, body.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/favorite/qa/{user_id}/{qauid}")
def remove_favorite_qa(user_id: str, qauid: str):
    storage.remove_favorite_qa(qauid, user_id)
    return {"ok": True}


# ── 폴더 ─────────────────────────────────────────────────────────

@router.get("/folders/{user_id}")
def get_folders(user_id: str):
    """폴더 목록 반환. 폴더가 없으면 샘플 폴더를 자동 생성한다."""
    tenant_id, _ = storage.get_project_info(user_id)
    storage.seed_sample_folders(tenant_id, user_id)
    return storage.get_folders(tenant_id)


# ── 공유 ─────────────────────────────────────────────────────────

@router.post("/share")
def share_qa(body: ShareRequest):
    """QA를 같은 tenant의 모든 사용자와 공유한다."""
    ok = storage.share_qa(body.qauid, body.user_id, body.folder_uid)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/shares/sent/{user_id}")
def get_shares_sent(user_id: str):
    return storage.get_shares_sent(user_id)


@router.delete("/shares/sent/{share_qauid}/{user_id}")
def delete_share_sent(share_qauid: str, user_id: str):
    storage.delete_share_sent(share_qauid, user_id)
    return {"ok": True}


@router.delete("/shares/received/{share_qauid}/{user_id}")
def delete_share_received(share_qauid: str, user_id: str):
    storage.delete_share_received(share_qauid, user_id)
    return {"ok": True}


@router.get("/shares/received/{user_id}")
def get_shares_received(user_id: str):
    """같은 project의 모든 공유 보고서 목록 반환."""
    _, project_id = storage.get_project_info(user_id)
    return storage.get_all_shares(project_id)


@router.get("/shares/{share_qauid}")
def get_share_detail(share_qauid: str):
    """공유된 QA 내용 조회."""
    row = storage.get_share(share_qauid)
    if not row:
        raise HTTPException(status_code=404, detail="공유 내역을 찾을 수 없습니다.")
    return row


# ── 기타 ─────────────────────────────────────────────────────────

@router.get("/health")
def api_health() -> dict:
    return {"status": "ok"}
