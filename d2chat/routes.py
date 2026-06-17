import json
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from d2chat.mcp_core.service import mcp_service
from d2chat.questions import get_questions
from d2chat.history import supabase_storage as storage

router = APIRouter()


# ── 요청 모델 ─────────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

class InjectRequest(BaseModel):
    session_id: Optional[str] = None
    question: str
    answer: str
    query: Optional[str] = None
    visualization_type: str = "none"
    table_html: Optional[str] = None
    chart_image: Optional[str] = None

class FavoriteQARequest(BaseModel):
    qauid: str

class ShareRequest(BaseModel):
    session_id: str
    session_titles: str
    target_user_uids: List[str]


# ── 질문/답변 (세션 없으면 첫 전송 시 자동 생성) ─────────────────

@router.post("/ask")
def ask_question(body: QuestionRequest, token: str = Depends(get_token)):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문을 입력해주세요.")

    user = _get_user(token)
    user_id = str(user.id)
    sb = _sb(token)
    session_id = body.session_id

    # qauid 사전 생성 (LLM 로그와 QA 저장에 동일 ID 사용)
    pre_qauid = str(uuid.uuid4())

    new_session_id = None
    if not session_id or session_id == "default":
        tenant_id, project_id = storage.get_project_info(sb, user_id)
        session_id = storage.create_session(sb, user_id, tenant_id, project_id)
        new_session_id = session_id
        info = {"tenantid": tenant_id, "projectid": project_id}
        qa_count = 0
    else:
        info = storage.get_session_info(sb, session_id)
        qa_count = storage.get_qa_count(sb, session_id)

    log_ctx = {
        "qauid":          pre_qauid,
        "servicecd":      "C",
        "questiontypecd": "S",
        "creator":        user_id,
        "tenant_id":      info.get("tenantid"),
        "project_id":     info.get("projectid"),
        "session_uid":    session_id,
    }

    try:
        result = mcp_service.ask(question, session_id=session_id, log_ctx=log_ctx)
        response = {
            "question":           question,
            "answer":             result.get("answer", ""),
            "query":              result.get("query"),
            "queries":            result.get("queries", []),
            "visualization_type": result.get("visualization_type", "none"),
            "status":             "success",
        }
        if new_session_id:
            response["session_id"] = new_session_id
        if result.get("table_html"):
            response["table_html"] = result["table_html"]
        if result.get("chart_image"):
            response["chart_image"] = result["chart_image"]

        viz = result.get("visualization_type", "none")
        answer_json = json.dumps({
            "answer":             result.get("answer", ""),
            "visualization_type": viz,
            "table_html":         result.get("table_html"),
            "chart_image":        result.get("chart_image"),
        }, ensure_ascii=False)

        dataset = None
        if viz != "none":
            dataset = json.dumps({
                "table_data": result.get("table_data"),
                "chart_data": result.get("chart_data"),
            })

        storage.append_qa(
            sb,
            session_uid=session_id,
            tenant_id=info.get("tenantid"),
            project_id=info.get("projectid"),
            question=question,
            answer=answer_json,
            dataset=dataset,
            creator=user_id,
            is_first=(qa_count == 0),
            qauid=pre_qauid,
            inputtoken=result.get("total_inputtoken"),
            outputtoken=result.get("total_outputtoken"),
        )
        response["qauid"] = pre_qauid

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 이어하기 ─────────────────────────────────────────────────────

@router.post("/session/inject")
def inject_qa(body: InjectRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    user_id = str(user.id)
    sb = _sb(token)
    session_id = body.session_id
    new_session_id = None

    # 활성 세션이 없으면 자동 생성
    if not session_id:
        tenant_id, project_id = storage.get_project_info(sb, user_id)
        session_id = storage.create_session(sb, user_id, tenant_id, project_id)
        new_session_id = session_id

    info     = storage.get_session_info(sb, session_id)
    qa_count = storage.get_qa_count(sb, session_id)

    answer_json = json.dumps({
        "answer":             body.answer,
        "visualization_type": body.visualization_type,
        "table_html":         body.table_html,
        "chart_image":        body.chart_image,
    }, ensure_ascii=False)

    storage.append_qa(
        sb,
        session_uid=session_id,
        tenant_id=info.get("tenantid"),
        project_id=info.get("projectid"),
        question=body.question,
        answer=answer_json,
        dataset=None,
        creator=user_id,
        is_first=(qa_count == 0),
    )
    mcp_service.seed_session_history(session_id, body.question, body.answer)

    res = {"ok": True}
    if new_session_id:
        res["session_id"] = new_session_id
    return res


# ── 히스토리 ─────────────────────────────────────────────────────

@router.get("/history")
def get_history(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    return storage.get_history_by_date(sb, str(user.id))


@router.get("/history/{session_id}")
def get_session(session_id: str, token: str = Depends(get_token)):
    sb = _sb(token)
    data = storage.get_session_messages(sb, session_id)
    if not data["messages"]:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return data


@router.delete("/history/{session_id}")
def delete_session(session_id: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.delete_session(sb, session_id, str(user.id))
    return {"ok": True}


# ── 즐겨찾기 (Q&A 단위) ──────────────────────────────────────────

@router.get("/favorites")
def get_favorites(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    return storage.get_favorites(sb, str(user.id))


@router.post("/favorite/qa")
def add_favorite_qa(body: FavoriteQARequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.add_favorite_qa(sb, body.qauid, str(user.id))
    return {"ok": True}


@router.delete("/favorite/qa/{qauid}")
def remove_favorite_qa(qauid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.remove_favorite_qa(sb, qauid, str(user.id))
    return {"ok": True}


# ── 공유 ─────────────────────────────────────────────────────────

@router.post("/share")
def share_session(body: ShareRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    info = storage.get_session_info(sb, body.session_id)
    share_uid = storage.share_session(
        sb,
        session_uid=body.session_id,
        target_user_uids=body.target_user_uids,
        tenant_id=info.get("tenantid"),
        project_id=info.get("projectid"),
        session_titles=body.session_titles,
        creator=str(user.id),
    )
    return {"ok": True, "share_uid": share_uid}


@router.get("/shares/sent")
def get_shares_sent(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    return storage.get_shares_sent(sb, str(user.id))


@router.delete("/shares/sent/{share_uid}")
def delete_share(share_uid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.delete_share(sb, share_uid, str(user.id))
    return {"ok": True}


@router.get("/shares/received")
def get_shares_received(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    return storage.get_shares_received(sb, str(user.id))


@router.delete("/shares/received/{share_uid}")
def delete_share_received(share_uid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.delete_share_received(sb, share_uid, str(user.id))
    return {"ok": True}


@router.get("/snapshots/{share_uid}")
def get_snapshot(share_uid: str, token: str = Depends(get_token)):
    sb = _sb(token)
    data = storage.get_snapshot_messages(sb, share_uid)
    if not data["messages"]:
        raise HTTPException(status_code=404, detail="스냅샷을 찾을 수 없습니다.")
    return data


# ── 공유 대상 사용자 목록 ─────────────────────────────────────────

@router.get("/users/same-tenant")
def get_users_same_tenant(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    tenant_id, project_id = storage.get_project_info(sb, user_id)
    if tenant_id is None:
        return []
    return storage.get_users_same_tenant(sb, tenant_id, user_id, project_id)


# ── 기타 ─────────────────────────────────────────────────────────

@router.get("/questions")
def get_questions_api():
    return {"questions": get_questions()}


@router.get("/info")
def get_data_info(token: str = Depends(get_token)):
    try:
        return mcp_service.get_data_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
