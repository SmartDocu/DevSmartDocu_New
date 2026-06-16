"""D2Insight Chat API 라우터."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token
from d2insight.report.intent_parser import parse_intent
from d2insight.report.pipeline_runner import run_tool, run_report_from_spec
from d2insight.report import session as _session
from d2insight.report import report_spec as _spec_mod
from d2insight.history import insight_storage as storage
from d2insight.report import token_tracker

router = APIRouter()


# ── 요청 모델 ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    provider: str | None = None  # anthropic | openai


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
def chat_endpoint(req: ChatRequest, token: str = Depends(get_token)) -> ChatResponse:
    token_tracker.reset()
    import uuid as _uuid
    try:
        sid, hist = _session.get_or_create(req.session_id, user_id=req.user_id)
    except Exception as e:
        print(f"[d2insight/session] get_or_create 실패 (fallback): {e}")
        sid = req.session_id or str(_uuid.uuid4())
        hist = []

    provider = req.provider or None

    active_spec = _spec_mod.get_spec(sid)
    if active_spec:
        updated_spec, bot_response = _spec_mod.advance_spec(sid, req.message, history=hist, provider=provider)
        if bot_response == "__EXECUTE__":
            result = run_report_from_spec(updated_spec, req.user_id, provider=provider)
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
        intent = parse_intent(req.message, provider=provider)
        intent["original_message"] = req.message
        tool = intent.get("tool", "chat")
        target_month = intent.get("target_month")
        months_back = intent.get("months_back", 5)

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
            result = run_tool(
                tool, target_month, months_back,
                history=hist, intent=intent, user_id=req.user_id, provider=provider,
            )

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
            filenm=result.get("report_path"),
            fileurl=result.get("fileurl"),
            inputtoken=tokens["input"] or None,
            outputtoken=tokens["output"] or None,
            servicecd="I",
        )
    except Exception as e:
        print(f"[d2insight/session] append_qa 실패 (저장 건너뜀): {e}")

    if qauid and (tokens["input"] or tokens["output"]):
        token_tracker.record_turn(sid, qauid, tokens)

    if qauid and calls:
        try:
            tenant_id, project_id = storage.get_project_info(req.user_id) if req.user_id else (None, None)
            storage.insert_llm_api_logs(
                calls=calls,
                qauid=qauid,
                session_uid=sid,
                tenant_id=tenant_id,
                project_id=project_id,
                creator=req.user_id,
                questiontypecd=questiontypecd,
            )
        except Exception as e:
            print(f"[d2insight/session] insert_llm_api_logs 실패 (저장 건너뜀): {e}")

    return ChatResponse(session_id=sid, qauid=qauid, **result)


# ── 이어가기 ──────────────────────────────────────────────────────

@router.post("/session/inject")
def inject_qa(body: InjectRequest, token: str = Depends(get_token)):
    import uuid as _uuid
    try:
        sid, _ = _session.get_or_create(body.session_id, user_id=body.user_id)
    except Exception:
        sid = body.session_id or str(_uuid.uuid4())

    try:
        answer_json = {
            "answer": body.answer,
            "visualization_type": body.visualization_type,
            "table_html": body.table_html,
        }
        _session.append_qa(sid, body.question, answer_json, user_id=body.user_id, filenm=body.report_path)
    except Exception as e:
        print(f"[d2insight/inject] append_qa 실패: {e}")

    return {"ok": True, "session_id": sid}


# ── 히스토리 ─────────────────────────────────────────────────────

@router.get("/history/{user_id}")
def get_history(user_id: str, token: str = Depends(get_token)):
    return storage.get_history_by_date(user_id)


@router.get("/history/{user_id}/{session_id}")
def get_session_messages(user_id: str, session_id: str, token: str = Depends(get_token)):
    messages = storage.get_session_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"session_id": session_id, "messages": messages}


@router.delete("/history/{user_id}/{session_id}")
def delete_session(user_id: str, session_id: str, token: str = Depends(get_token)):
    storage.delete_session(session_id, user_id)
    return {"ok": True}


# ── 즐겨찾기 ─────────────────────────────────────────────────────

@router.get("/favorites/{user_id}")
def get_favorites(user_id: str, token: str = Depends(get_token)):
    return storage.get_favorites(user_id)


@router.post("/favorite/qa")
def add_favorite_qa(body: FavoriteQARequest, token: str = Depends(get_token)):
    ok = storage.add_favorite_qa(body.qauid, body.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/favorite/qa/{user_id}/{qauid}")
def remove_favorite_qa(user_id: str, qauid: str, token: str = Depends(get_token)):
    storage.remove_favorite_qa(qauid, user_id)
    return {"ok": True}


# ── 폴더 ─────────────────────────────────────────────────────────

@router.get("/folders/{user_id}")
def get_folders(user_id: str, token: str = Depends(get_token)):
    tenant_id, _ = storage.get_project_info(user_id)
    storage.seed_sample_folders(tenant_id, user_id)
    return storage.get_folders(tenant_id)


# ── 공유 ─────────────────────────────────────────────────────────

@router.post("/share")
def share_qa(body: ShareRequest, token: str = Depends(get_token)):
    ok = storage.share_qa(body.qauid, body.user_id, body.folder_uid)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/shares/sent/{user_id}")
def get_shares_sent(user_id: str, token: str = Depends(get_token)):
    return storage.get_shares_sent(user_id)


@router.delete("/shares/sent/{share_qauid}/{user_id}")
def delete_share_sent(share_qauid: str, user_id: str, token: str = Depends(get_token)):
    storage.delete_share_sent(share_qauid, user_id)
    return {"ok": True}


@router.delete("/shares/received/{share_qauid}/{user_id}")
def delete_share_received(share_qauid: str, user_id: str, token: str = Depends(get_token)):
    storage.delete_share_received(share_qauid, user_id)
    return {"ok": True}


@router.get("/shares/received/{user_id}")
def get_shares_received(user_id: str, token: str = Depends(get_token)):
    tenant_id, _ = storage.get_project_info(user_id)
    return storage.get_all_shares(tenant_id)


@router.get("/shares/{share_qauid}")
def get_share_detail(share_qauid: str, token: str = Depends(get_token)):
    row = storage.get_share(share_qauid)
    if not row:
        raise HTTPException(status_code=404, detail="공유 내역을 찾을 수 없습니다.")
    return row


# ── 헬스 체크 ─────────────────────────────────────────────────────

@router.get("/health")
def api_health() -> dict:
    return {"status": "ok"}
