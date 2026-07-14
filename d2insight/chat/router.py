"""Insight Chat API router."""
from __future__ import annotations

import io
import re
import uuid as _uuid
from typing import List, Optional
from urllib.parse import urlparse

import pandas as pd
from requests import exceptions as requests_exceptions

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_user as _get_user
from d2insight.chat.intent_parser import parse_intent
from d2insight.chat.pipeline_runner import run_tool, run_report_from_spec
from d2insight.chat import session as _session
from d2insight.chat import report_spec as _spec_mod
from d2insight.db import insight_storage as storage
from d2insight import token_tracker
from d2insight.report.excel_registry import get_excel_server
from d2shared.api_dataset import fetch_json, json_to_dataframe

router = APIRouter()

MAX_UPLOAD_TOTAL_BYTES = 500 * 1024 * 1024  # 한 번에 업로드하는 전체 파일 합산 용량 제한 (500MB)


def _check_owner(token: str, user_id: str | None) -> None:
    """토큰의 실제 사용자와 요청 파라미터의 user_id가 일치하는지 검증한다."""
    user = _get_user(token)
    if user_id and str(user.id) != user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 조회할 수 있습니다.")


def _sanitize_dataset_key(name: str) -> str:
    """파일명/데이터셋명을 데이터셋 키(테이블명 대용)로 사용하기 위해 정리"""
    name = re.sub(r"\.(csv|xlsx|xls)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^0-9A-Za-z가-힣_]+", "_", name).strip("_")
    return name or "dataset"


def _dataset_preview(key: str, df: pd.DataFrame, filename: str, metadata: dict) -> dict:
    return {
        "dataset_key": key,
        "filename": filename,
        "columns": list(df.columns.astype(str)),
        "row_count": int(len(df)),
        "description": metadata.get("description"),
    }


def _get_llm(project_id=None, tenant_id=None, user_uid=None, account_uid=None):
    from utilsPrj.ai_chain import build_langchain_llm, get_llm_info
    from d2insight.config import LLM_MODELS
    _, api_key, vendor, _, _ = get_llm_info(
        project_id=project_id, tenant_id=tenant_id,
        user_uid=user_uid, account_uid=account_uid, service_code="In",
    )
    return build_langchain_llm(vendor, api_key, LLM_MODELS[vendor]["fast"])


# ── 요청 모델 ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    account_uid: str | None = None  # 프론트 authStore에서 전달 (serviceusers 조회 생략용)


class ApiDatasetRequest(BaseModel):
    url: str
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    account_uid: str | None = None
    dataset_name: str | None = None
    header_name: str | None = None
    header_value: str | None = None


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
def chat_endpoint(req: ChatRequest, token: str = Depends(get_token)) -> ChatResponse:
    _check_owner(token, req.user_id)
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
                                          account_uid=req.account_uid, session_id=sid)
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
                              user_uid=req.user_id, account_uid=req.account_uid, session_id=sid)

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


# ── 데이터셋 업로드: 엑셀/CSV 업로드, API 연결 (세션의 report 생성이 이 데이터를 사용) ──

@router.post("/upload-dataset")
async def upload_dataset(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    project_id: Optional[int] = Form(None),
    account_uid: Optional[str] = Form(None),
    token: str = Depends(get_token),
):
    _check_owner(token, user_id)
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

    sid, _hist = _session.get_or_create(session_id, user_id=user_id, project_id=project_id)
    tenant_id, db_project_id = storage.get_project_info(user_id) if user_id else (None, None)
    resolved_project_id = project_id if project_id is not None else db_project_id
    log_ctx = {
        "qauid": None,
        "servicecd": "In",
        "tenant_id": tenant_id,
        "project_id": resolved_project_id,
        "session_uid": sid,
        "creator": user_id,
        "account_uid": account_uid,
    }
    llm = _get_llm(project_id=resolved_project_id, tenant_id=tenant_id, user_uid=user_id, account_uid=account_uid)
    excel_server = get_excel_server()

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
            key, metadata = excel_server.register_dataset(
                session_id=sid,
                dataset_key=dataset_key,
                df=df,
                filename=filename,
                sheet_name=dataset_key,
                llm=llm,
                log_ctx=log_ctx,
            )
            previews.append(_dataset_preview(key, df, filename, metadata))

    if not previews:
        raise HTTPException(status_code=400, detail="유효한 데이터가 없는 파일입니다.")

    return {"status": "success", "session_id": sid, "datasets": previews}


@router.post("/upload-dataset-url")
def upload_dataset_url(body: ApiDatasetRequest, token: str = Depends(get_token)):
    _check_owner(token, body.user_id)
    try:
        raw = fetch_json(body.url, header_name=body.header_name, header_value=body.header_value)
        df = json_to_dataframe(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests_exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"API 호출에 실패했습니다: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="응답에 유효한 데이터가 없습니다.")

    sid, _hist = _session.get_or_create(body.session_id, user_id=body.user_id, project_id=body.project_id)
    tenant_id, db_project_id = storage.get_project_info(body.user_id) if body.user_id else (None, None)
    resolved_project_id = body.project_id if body.project_id is not None else db_project_id
    log_ctx = {
        "qauid": None,
        "servicecd": "In",
        "tenant_id": tenant_id,
        "project_id": resolved_project_id,
        "session_uid": sid,
        "creator": body.user_id,
        "account_uid": body.account_uid,
    }
    llm = _get_llm(project_id=resolved_project_id, tenant_id=tenant_id, user_uid=body.user_id, account_uid=body.account_uid)
    excel_server = get_excel_server()

    # 데이터셋 이름/설명에는 URL을 절대 그대로 쓰지 않는다 (쿼리스트링에 apiKey가 포함될 수 있고,
    # /share 기능으로 다른 사용자에게 노출될 수 있음). 사용자가 지정한 이름 또는 호스트명만 사용한다.
    host = urlparse(body.url).hostname or "api"
    display_name = body.dataset_name or host
    dataset_key = _sanitize_dataset_key(display_name)

    key, metadata = excel_server.register_dataset(
        session_id=sid,
        dataset_key=dataset_key,
        df=df,
        filename=display_name,
        sheet_name=None,
        llm=llm,
        log_ctx=log_ctx,
    )

    return {
        "status": "success",
        "session_id": sid,
        "datasets": [_dataset_preview(key, df, display_name, metadata)],
    }


# ── 이어가기 ─────────────────────────────────────────────────────

@router.post("/session/inject")
def inject_qa(body: InjectRequest, token: str = Depends(get_token)):
    """과거 Q&A를 현재(또는 새) 세션에 이어붙인다."""
    _check_owner(token, body.user_id)
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
def get_history(user_id: str, token: str = Depends(get_token)):
    """날짜별로 그룹화된 세션 목록 반환."""
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_history_by_date(user_id, offsetminutes)


@router.get("/history/{user_id}/{session_id}")
def get_session_messages(user_id: str, session_id: str, token: str = Depends(get_token)):
    """세션의 Q&A 메시지 목록 반환."""
    _check_owner(token, user_id)
    messages = storage.get_session_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"session_id": session_id, "messages": messages}


@router.delete("/history/{user_id}/{session_id}")
def delete_session(user_id: str, session_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.delete_session(session_id, user_id)
    return {"ok": True}


# ── 즐겨찾기 ─────────────────────────────────────────────────────

@router.get("/favorites/{user_id}")
def get_favorites(user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_favorites(user_id, offsetminutes)


@router.post("/favorite/qa")
def add_favorite_qa(body: FavoriteQARequest, token: str = Depends(get_token)):
    _check_owner(token, body.user_id)
    ok = storage.add_favorite_qa(body.qauid, body.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/favorite/qa/{user_id}/{qauid}")
def remove_favorite_qa(user_id: str, qauid: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.remove_favorite_qa(qauid, user_id)
    return {"ok": True}


# ── 폴더 ─────────────────────────────────────────────────────────

@router.get("/folders/{user_id}")
def get_folders(user_id: str, token: str = Depends(get_token)):
    """폴더 목록 반환. 폴더가 없으면 샘플 폴더를 자동 생성한다."""
    _check_owner(token, user_id)
    tenant_id, _ = storage.get_project_info(user_id)
    storage.seed_sample_folders(tenant_id, user_id)
    return storage.get_folders(tenant_id)


# ── 공유 ─────────────────────────────────────────────────────────

@router.post("/share")
def share_qa(body: ShareRequest, token: str = Depends(get_token)):
    """QA를 같은 tenant의 모든 사용자와 공유한다."""
    _check_owner(token, body.user_id)
    ok = storage.share_qa(body.qauid, body.user_id, body.folder_uid)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/shares/sent/{user_id}")
def get_shares_sent(user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_shares_sent(user_id, offsetminutes)


@router.delete("/shares/sent/{share_qauid}/{user_id}")
def delete_share_sent(share_qauid: str, user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.delete_share_sent(share_qauid, user_id)
    return {"ok": True}


@router.delete("/shares/received/{share_qauid}/{user_id}")
def delete_share_received(share_qauid: str, user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.delete_share_received(share_qauid, user_id)
    return {"ok": True}


@router.get("/shares/received/{user_id}")
def get_shares_received(user_id: str, token: str = Depends(get_token)):
    """같은 project의 모든 공유 보고서 목록 반환."""
    _check_owner(token, user_id)
    _, project_id = storage.get_project_info(user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_all_shares(project_id, offsetminutes)


@router.get("/shares/{share_qauid}")
def get_share_detail(share_qauid: str, token: str = Depends(get_token)):
    """공유된 QA 내용 조회 (로그인한 사용자면 누구나 조회 가능 — 공유 링크 특성상 소유자 검증 없음)."""
    _get_user(token)
    row = storage.get_share(share_qauid)
    if not row:
        raise HTTPException(status_code=404, detail="공유 내역을 찾을 수 없습니다.")
    return row


# ── 기타 ─────────────────────────────────────────────────────────

@router.get("/health")
def api_health() -> dict:
    return {"status": "ok"}
