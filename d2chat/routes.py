import io
import json
import re
import uuid
from urllib.parse import urlparse

import pandas as pd
from requests import exceptions as requests_exceptions
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user, require_chat_read, require_chat_write
from d2chat.mcp_core.service import mcp_service
from d2chat.questions import get_questions
from d2chat.history import supabase_storage as storage
from d2shared.api_dataset import fetch_json, json_to_dataframe

router = APIRouter()

MAX_UPLOAD_TOTAL_BYTES = 500 * 1024 * 1024  # 한 번에 업로드하는 전체 파일 합산 용량 제한 (500MB)


def _sanitize_dataset_key(name: str) -> str:
    """파일명/데이터셋명을 데이터셋 키(테이블명 대용)로 사용하기 위해 정리"""
    name = re.sub(r"\.(csv|xlsx|xls)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^0-9A-Za-z가-힣_]+", "_", name).strip("_")
    return name or "dataset"


# ── 요청 모델 ─────────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    project_id: Optional[int] = None
    account_uid: Optional[str] = None  # 프론트 authStore에서 전달 (serviceusers 조회 생략용)

class InjectRequest(BaseModel):
    session_id: Optional[str] = None
    project_id: Optional[int] = None
    question: str
    answer: str
    query: Optional[str] = None
    visualization_type: str = "none"
    table_html: Optional[str] = None
    chart_image: Optional[str] = None
    visualizations: Optional[List[dict]] = None
    visualization_error: Optional[str] = None

class ApiDatasetRequest(BaseModel):
    url: str
    session_id: Optional[str] = None
    project_id: Optional[int] = None
    account_uid: Optional[str] = None
    dataset_name: Optional[str] = None
    header_name: Optional[str] = None
    header_value: Optional[str] = None

class FavoriteQARequest(BaseModel):
    qauid: str

class ShareRequest(BaseModel):
    session_id: str
    session_titles: str
    target_user_uids: List[str]


# ── 질문/답변 (세션 없으면 첫 전송 시 자동 생성) ─────────────────

@router.post("/ask", dependencies=[Depends(require_chat_write)])
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
        if body.project_id is not None:
            project_id = body.project_id
        session_id = storage.create_session(sb, user_id, tenant_id, project_id)
        new_session_id = session_id
        info = {"tenantid": tenant_id, "projectid": project_id}
        qa_count = 0
    else:
        info = storage.get_session_info(sb, session_id)
        qa_count = storage.get_qa_count(sb, session_id)

    log_ctx = {
        "qauid":          pre_qauid,
        "servicecd":      "Ch",
        "questiontypecd": "S",
        "creator":        user_id,
        "tenant_id":      info.get("tenantid"),
        "project_id":     info.get("projectid"),
        "session_uid":    session_id,
        "account_uid":    body.account_uid,
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
        if result.get("visualizations"):
            response["visualizations"] = result["visualizations"]
        if result.get("visualization_error"):
            response["visualization_error"] = result["visualization_error"]

        viz = result.get("visualization_type", "none")
        answer_json = json.dumps({
            "answer":               result.get("answer", ""),
            "visualization_type":   viz,
            "table_html":           result.get("table_html"),
            "chart_image":          result.get("chart_image"),
            "visualizations":       result.get("visualizations"),
            "visualization_error":  result.get("visualization_error"),
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


# ── 외부 데이터 연동: 엑셀/CSV 업로드, API 연결 (세션을 external 모드로 전환) ──

def _get_or_create_session(sb, user_id: str, session_id: Optional[str], project_id: Optional[int]):
    """/ask와 동일한 세션 확보 로직 — 없으면 새로 생성."""
    if not session_id or session_id == "default":
        tenant_id, resolved_project_id = storage.get_project_info(sb, user_id)
        if project_id is not None:
            resolved_project_id = project_id
        new_session_id = storage.create_session(sb, user_id, tenant_id, resolved_project_id)
        return new_session_id, new_session_id, {"tenantid": tenant_id, "projectid": resolved_project_id}
    info = storage.get_session_info(sb, session_id)
    return session_id, None, info


def _dataset_preview(key: str, df: pd.DataFrame, filename: str, metadata: dict) -> dict:
    return {
        "dataset_key": key,
        "filename": filename,
        "columns": list(df.columns.astype(str)),
        "row_count": int(len(df)),
        "description": metadata.get("description"),
    }


@router.post("/upload-dataset", dependencies=[Depends(require_chat_write)])
async def upload_dataset(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    project_id: Optional[int] = Form(None),
    account_uid: Optional[str] = Form(None),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    user_id = str(user.id)
    sb = _sb(token)

    file_entries = []  # (filename, ext, content)
    total_size = 0
    for file in files:
        filename = file.filename or "uploaded"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ("csv", "xlsx", "xls"):
            raise HTTPException(status_code=400, detail=f"{filename}: csv, xlsx, xls 파일만 업로드할 수 있습니다.")

        content = await file.read()
        total_size += len(content)
        if total_size > MAX_UPLOAD_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"업로드 파일 전체 용량은 {MAX_UPLOAD_TOTAL_BYTES // (1024 * 1024)}MB를 초과할 수 없습니다.",
            )
        file_entries.append((filename, ext, content))

    session_id, new_session_id, info = _get_or_create_session(sb, user_id, session_id, project_id)
    log_ctx = {
        "qauid": str(uuid.uuid4()),
        "servicecd": "Ch",
        "creator": user_id,
        "tenant_id": info.get("tenantid"),
        "project_id": info.get("projectid"),
        "session_uid": session_id,
        "account_uid": account_uid,
    }

    previews = []
    for filename, ext, content in file_entries:
        try:
            if ext == "csv":
                sheets = {_sanitize_dataset_key(filename): pd.read_csv(io.BytesIO(content))}
            else:
                sheets_raw = pd.read_excel(io.BytesIO(content), sheet_name=None)
                sheets = {
                    _sanitize_dataset_key(f"{filename}_{sheet_name}"): sheet_df
                    for sheet_name, sheet_df in sheets_raw.items()
                }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"{filename}: 파일을 읽을 수 없습니다: {e}")

        for dataset_key, df in sheets.items():
            if df.empty:
                continue
            key, metadata = mcp_service.upload_excel_dataset(
                session_id=session_id,
                dataset_key=dataset_key,
                df=df,
                filename=filename,
                sheet_name=dataset_key,
                log_ctx=log_ctx,
            )
            previews.append(_dataset_preview(key, df, filename, metadata))

    if not previews:
        raise HTTPException(status_code=400, detail="유효한 데이터가 없는 파일입니다.")

    response = {"status": "success", "session_id": session_id, "datasets": previews}
    if new_session_id:
        response["session_id"] = new_session_id
    return response


@router.post("/upload-dataset-url", dependencies=[Depends(require_chat_write)])
def upload_dataset_url(body: ApiDatasetRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    user_id = str(user.id)
    sb = _sb(token)

    try:
        raw = fetch_json(body.url, header_name=body.header_name, header_value=body.header_value)
        df = json_to_dataframe(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests_exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"API 호출에 실패했습니다: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="응답에 유효한 데이터가 없습니다.")

    session_id, new_session_id, info = _get_or_create_session(sb, user_id, body.session_id, body.project_id)
    log_ctx = {
        "qauid": str(uuid.uuid4()),
        "servicecd": "Ch",
        "creator": user_id,
        "tenant_id": info.get("tenantid"),
        "project_id": info.get("projectid"),
        "session_uid": session_id,
        "account_uid": body.account_uid,
    }

    # 데이터셋 이름/설명에는 URL을 절대 그대로 쓰지 않는다 (쿼리스트링에 apiKey가 포함될 수 있고,
    # /share 기능으로 다른 사용자에게 노출될 수 있음). 사용자가 지정한 이름 또는 호스트명만 사용한다.
    host = urlparse(body.url).hostname or "api"
    display_name = body.dataset_name or host
    dataset_key = _sanitize_dataset_key(display_name)

    key, metadata = mcp_service.upload_excel_dataset(
        session_id=session_id,
        dataset_key=dataset_key,
        df=df,
        filename=display_name,
        sheet_name=None,
        log_ctx=log_ctx,
    )

    response = {
        "status": "success",
        "session_id": session_id,
        "datasets": [_dataset_preview(key, df, display_name, metadata)],
    }
    if new_session_id:
        response["session_id"] = new_session_id
    return response


# ── 이어하기 ─────────────────────────────────────────────────────

@router.post("/session/inject", dependencies=[Depends(require_chat_write)])
def inject_qa(body: InjectRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    user_id = str(user.id)
    sb = _sb(token)
    session_id = body.session_id
    new_session_id = None

    # 활성 세션이 없으면 자동 생성
    if not session_id:
        tenant_id, project_id = storage.get_project_info(sb, user_id)
        if body.project_id is not None:
            project_id = body.project_id
        session_id = storage.create_session(sb, user_id, tenant_id, project_id)
        new_session_id = session_id

    info     = storage.get_session_info(sb, session_id)
    qa_count = storage.get_qa_count(sb, session_id)

    answer_json = json.dumps({
        "answer":               body.answer,
        "visualization_type":   body.visualization_type,
        "table_html":           body.table_html,
        "chart_image":          body.chart_image,
        "visualizations":       body.visualizations,
        "visualization_error":  body.visualization_error,
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


# ── 초기 로딩 통합 (bootstrap) ────────────────────────────────────

@router.get("/bootstrap", dependencies=[Depends(require_chat_read)])
def get_bootstrap(token: str = Depends(get_token)):
    """사이드바 초기 로딩에 필요한 데이터를 한 번에 반환.

    offsetminutes를 1회만 조회해 /favorites, /history, /shares/sent,
    /shares/received 4개를 개별 호출할 때 생기는 중복 조회를 없앤다.
    개별 액션 후 부분 갱신에는 기존 4개 엔드포인트를 그대로 사용한다.
    """
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    return {
        "favorites": storage.get_favorites(sb, str(user.id), offsetminutes),
        "history": storage.get_history_by_date(sb, str(user.id), offsetminutes),
        "shares_sent": storage.get_shares_sent(sb, str(user.id), offsetminutes),
        "shares_received": storage.get_shares_received(sb, str(user.id), offsetminutes),
    }


# ── 히스토리 ─────────────────────────────────────────────────────

@router.get("/history", dependencies=[Depends(require_chat_read)])
def get_history(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    return storage.get_history_by_date(sb, str(user.id), offsetminutes)


@router.get("/history/{session_id}", dependencies=[Depends(require_chat_read)])
def get_session(session_id: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    data = storage.get_session_messages(sb, session_id, offsetminutes)
    if not data["messages"]:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return data


@router.delete("/history/{session_id}", dependencies=[Depends(require_chat_write)])
def delete_session(session_id: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.delete_session(sb, session_id, str(user.id))
    return {"ok": True}


# ── 즐겨찾기 (Q&A 단위) ──────────────────────────────────────────

@router.get("/favorites", dependencies=[Depends(require_chat_read)])
def get_favorites(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    return storage.get_favorites(sb, str(user.id), offsetminutes)


@router.post("/favorite/qa", dependencies=[Depends(require_chat_write)])
def add_favorite_qa(body: FavoriteQARequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.add_favorite_qa(sb, body.qauid, str(user.id))
    return {"ok": True}


@router.delete("/favorite/qa/{qauid}", dependencies=[Depends(require_chat_write)])
def remove_favorite_qa(qauid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.remove_favorite_qa(sb, qauid, str(user.id))
    return {"ok": True}


# ── 공유 ─────────────────────────────────────────────────────────

@router.post("/share", dependencies=[Depends(require_chat_write)])
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


@router.get("/shares/sent", dependencies=[Depends(require_chat_read)])
def get_shares_sent(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    return storage.get_shares_sent(sb, str(user.id), offsetminutes)


@router.delete("/shares/sent/{share_uid}", dependencies=[Depends(require_chat_write)])
def delete_share(share_uid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.delete_share(sb, share_uid, str(user.id))
    return {"ok": True}


@router.get("/shares/received", dependencies=[Depends(require_chat_read)])
def get_shares_received(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    return storage.get_shares_received(sb, str(user.id), offsetminutes)


@router.delete("/shares/received/{share_uid}", dependencies=[Depends(require_chat_write)])
def delete_share_received(share_uid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    storage.delete_share_received(sb, share_uid, str(user.id))
    return {"ok": True}


@router.get("/snapshots/{share_uid}", dependencies=[Depends(require_chat_read)])
def get_snapshot(share_uid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = storage.get_offsetminutes(sb, str(user.id))
    data = storage.get_snapshot_messages(sb, share_uid, offsetminutes)
    if not data["messages"]:
        raise HTTPException(status_code=404, detail="스냅샷을 찾을 수 없습니다.")
    return data


# ── 공유 대상 사용자 목록 ─────────────────────────────────────────

@router.get("/users/same-tenant", dependencies=[Depends(require_chat_read)])
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


@router.get("/info", dependencies=[Depends(require_chat_read)])
def get_data_info(token: str = Depends(get_token)):
    try:
        return mcp_service.get_data_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
