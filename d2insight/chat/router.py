"""Insight Chat API router."""
from __future__ import annotations

import io
import json
import re
import uuid as _uuid
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urlparse

import pandas as pd
from requests import exceptions as requests_exceptions

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.dependencies import get_token, get_user as _get_user, require_insight_read, require_insight_write
from d2insight.chat.intent_parser import parse_intent
from d2insight.chat.pipeline_runner import run_tool, run_report_from_spec
from d2insight.chat import session as _session
from d2insight.chat import report_spec as _spec_mod
from d2insight.chat import schedule_spec as _sched_mod
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
    # service_code="In"이면 models가 문자열이 아니라 {"fast":.., "balanced":.., "quality":..} dict다.
    models, api_key, vendor, _, _ = get_llm_info(
        project_id=project_id, tenant_id=tenant_id,
        user_uid=user_uid, account_uid=account_uid, service_code="In",
    )
    return build_langchain_llm(vendor, api_key, models["fast"])


# ── 요청 모델 ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    account_uid: str | None = None  # 프론트 authStore에서 전달 (serviceusers 조회 생략용)
    # 옵션 패널 "이대로 작성" 클릭 시 preview에서 확정된 시나리오·스텝 목록 (실행 강제).
    # 없으면 기존 자유 계획(LLM). 202608061005 방식의 inline_options와 동일 개념.
    options: dict | None = None


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


class ScheduleRegisterRequest(BaseModel):
    """정기 보고서로 등록할 보고서 1건(qauid)을 지정한다. 등록하면 이 세션을 건드리지 않고
    전용 세션을 새로 만들어 그 세션에만 결과가 쌓인다(pr_module_insight와 동일 원칙) —
    session_id를 직접 받지 않는 이유는 원래 대화 세션 전체가 정기 보고서로 바뀌어 대화
    목록에서 사라지고 그 세션의 다른 보고서까지 회차로 섞여 들어가는 문제가 있었기 때문."""
    qauid: str
    user_id: str
    project_id: int | None = None
    day_of_month: int
    hour: int = 9
    minute: int = 0


class ScheduleUpdateRequest(BaseModel):
    user_id: str
    day_of_month: int
    hour: int = 9
    minute: int = 0


class ScheduleShareRequest(BaseModel):
    user_id: str


class ScheduledRunRequest(BaseModel):
    template_uid: str
    run_date: str | None = None


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
    applied_steps: list | None = None


# ── 채팅 ─────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_insight_write)])
def chat_endpoint(req: ChatRequest, token: str = Depends(get_token)) -> ChatResponse:
    _check_owner(token, req.user_id)
    token_tracker.reset()

    try:
        sid, hist = _session.get_or_create(req.session_id, user_id=req.user_id, project_id=req.project_id)
    except Exception as e:
        # print(f"[session] get_or_create 실패 (fallback): {e}")
        pass
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
    active_sched = _sched_mod.get_spec(sid)
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

    # ── 대화형 정기 보고서 등록 진행 중("이 보고서 매달 5일에 작성해주세요") ───────
    # 대화 목록(history) 화면은 입력창이 없어 이 경로를 탈 수 없다 — 실시간 대화 중에만
    # 도달한다. 등록 자체는 오른쪽 패널 버튼과 같은 _register_schedule_for_qa를 공유한다.
    elif active_sched:
        updated_sched, bot_response = _sched_mod.advance_set_spec(
            sid, req.message, project_id=_project_id, tenant_id=_tenant_id,
            user_uid=req.user_id, account_uid=req.account_uid,
        )
        if bot_response == "__SAVE_SCHEDULE__":
            try:
                reg = _register_schedule_for_qa(
                    updated_sched["qauid"], req.user_id, _project_id,
                    updated_sched["day_of_month"],
                    updated_sched.get("hour") if updated_sched.get("hour") is not None else 9,
                    updated_sched.get("minute") if updated_sched.get("minute") is not None else 0,
                )
                answer = (
                    f"정기 보고서 '{reg['template_nm']}'를 등록했습니다.\n"
                    f"결과는 '{reg['template_nm']}' 세션에 쌓입니다."
                )
            except HTTPException as e:
                answer = e.detail
            _sched_mod.clear_spec(sid)
            result = {
                "answer": answer,
                "visualization_type": "none", "table_html": None,
                "chart_image": None, "report_path": None,
            }
        elif bot_response == "__CANCEL__":
            result = {
                "answer": "정기 보고서 등록을 취소했습니다.",
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
        # 옵션 패널 "이대로 작성"에서 온 preview 확정 옵션 — pipeline_runner가 report 실행 시
        # step plan을 이걸로 강제 (LLM 자유 계획 대신).
        if req.options:
            intent["scenario_options"] = req.options
            # preview에서 시나리오가 확정됐으면 tool=report, report_type을 시나리오 이름으로 세팅.
            if req.options.get("scenario"):
                intent["tool"] = "report"
                intent["report_type"] = req.options["scenario"]
        tool = intent.get("tool", "chat")
        target_month = intent.get("target_month")
        months_back = intent.get("months_back", 3)

        if tool == "report" and (intent.get("mode") == "start" or not target_month):
            spec = _spec_mod.create_spec(
                target_month=target_month,
                report_type=intent.get("report_type"),
                scenario_options=intent.get("scenario_options"),
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

        elif tool == "schedule_set":
            # 옵션 JSON 개념이 없는 앱이라(엔진 미도입) pr_module_insight처럼 붙여넣은 JSON을
            # 찾지 않는다 — 항상 "이 세션에서 방금 만든 보고서"를 대상으로 삼는다.
            last_report = storage.get_last_report_qa(sid)
            if not last_report:
                result = {
                    "answer": "정기 보고서로 등록할 보고서가 이 대화에는 아직 없습니다. 먼저 보고서를 작성해주세요.",
                    "visualization_type": "none", "table_html": None,
                    "chart_image": None, "report_path": None,
                }
            else:
                origin_period = storage._parse_target_period(last_report.get("filenm"))
                sched_spec = _sched_mod.create_set_spec(last_report["qauid"], origin_period)
                _sched_mod.save_spec(sid, sched_spec)
                updated_sched, bot_response = _sched_mod.advance_set_spec(
                    sid, req.message, project_id=_project_id, tenant_id=_tenant_id,
                    user_uid=req.user_id, account_uid=req.account_uid,
                )
                if bot_response == "__SAVE_SCHEDULE__":
                    try:
                        reg = _register_schedule_for_qa(
                            updated_sched["qauid"], req.user_id, _project_id,
                            updated_sched["day_of_month"],
                            updated_sched.get("hour") if updated_sched.get("hour") is not None else 9,
                            updated_sched.get("minute") if updated_sched.get("minute") is not None else 0,
                        )
                        answer = (
                            f"정기 보고서 '{reg['template_nm']}'를 등록했습니다.\n"
                            f"결과는 '{reg['template_nm']}' 세션에 쌓입니다."
                        )
                    except HTTPException as e:
                        answer = e.detail
                    _sched_mod.clear_spec(sid)
                    result = {
                        "answer": answer,
                        "visualization_type": "none", "table_html": None,
                        "chart_image": None, "report_path": None,
                    }
                elif bot_response == "__CANCEL__":
                    result = {
                        "answer": "정기 보고서 등록을 취소했습니다.",
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
            "applied_steps": result.get("applied_steps"),
            "analytic_uid": result.get("analytic_uid"),
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
        # print(f"[session] append_qa 실패 (저장 건너뜀): {e}")
        pass

    if qauid and (tokens["input"] or tokens["output"]):
        token_tracker.record_turn(sid, qauid, tokens)
    token_tracker.set_log_ctx(None)

    return ChatResponse(session_id=sid, qauid=qauid, **result)


# ── 데이터셋 업로드: 엑셀/CSV 업로드, API 연결 (세션의 report 생성이 이 데이터를 사용) ──

@router.post("/upload-dataset", dependencies=[Depends(require_insight_write)])
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

    # engine 역할 추론(resolve_upload_meta_columns → d2insight.engine._llm.chat)이 어느
    # 프로젝트/테넌트 소속인지 알아야 그 소속의 LLM 키를 찾는다 — /chat과 동일하게 여기서도
    # 표시해둔다.
    token_tracker.set_log_ctx(log_ctx)

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

            from d2insight.engine.upload_meta import resolve_upload_meta_columns
            meta_columns, info = resolve_upload_meta_columns(df, dataset_name=key)
            excel_server.session_datasets[sid][key]["engine_meta"] = {
                "meta_columns": meta_columns, "info": info,
            }

    token_tracker.set_log_ctx(None)

    if not previews:
        raise HTTPException(status_code=400, detail="유효한 데이터가 없는 파일입니다.")

    return {"status": "success", "session_id": sid, "datasets": previews}


@router.post("/upload-dataset-url", dependencies=[Depends(require_insight_write)])
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

@router.post("/session/inject", dependencies=[Depends(require_insight_write)])
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
        # print(f"[inject] append_qa 실패: {e}")
        pass

    return {"ok": True, "session_id": sid}


# ── 정기 보고서 (스케줄) ───────────────────────────────────────────
# 실제 스케줄 트리거는 본프로젝트 Schedule(UserScheduleMasters 등)이 담당한다. 여기서는
# "무엇을 어떤 조건으로 반복 생성할지"를 analytictemplates에 기록하고, /scheduled/run으로
# 호출되면 실행하는 것까지만 담당한다. 등록 화면은 현재 월 단위(grain="month")만 지원한다.

def _resolve_schedule_origin(qauid: str) -> tuple[dict, dict, str]:
    """등록 대상 보고서(qauid)를 조회하고 중복 등록 여부를 확인한다.

    반환: (qa 원본 행, 그 answer 컬럼을 파싱한 dict, 템플릿 이름). 템플릿 이름은
    f"{scenario_nm} 정기 보고서" — scenario_nm은 그 보고서 실행 시 Analytics.ScenarioNm에
    기록된 report_type(record_analytics 참조)이다. 세션 제목이나 프론트가 보낸 임의 문자열이
    아니라 그 보고서 자체의 유형에서 이름을 뽑는다(pr_module_insight와 동일 원칙).
    """
    qa = storage.get_qa(qauid)
    if not qa or not qa.get("filenm"):
        raise HTTPException(status_code=400, detail="정기 보고서로 등록할 보고서를 찾을 수 없습니다.")
    if storage.is_report_already_scheduled(qa["filenm"]):
        raise HTTPException(status_code=409, detail="이 보고서는 이미 정기 보고서로 등록되어 있습니다.")
    try:
        answer_json = json.loads(qa["answer"])
        if not isinstance(answer_json, dict):
            answer_json = {}
    except (json.JSONDecodeError, TypeError):
        answer_json = {}
    scenario_nm = storage.get_analytic_scenario_nm(answer_json.get("analytic_uid"))
    template_nm = f"{scenario_nm or '보고서'} 정기 보고서"
    return qa, answer_json, template_nm


def _next_schedule_run(qa: dict, day_of_month: int, hour: int, minute: int) -> datetime:
    """다음 실행 시각 — qa(등록 기준 원본 보고서)의 대상월과 겹치면 한 주기 미룬다
    (중복 방지, schedule_spec.next_run_avoiding_period 참조). 미리보기/등록 양쪽이 같은
    시각을 보도록 이 함수 하나로 공유한다.
    """
    origin_period = storage._parse_target_period(qa.get("filenm"))
    return _sched_mod.next_run_avoiding_period(origin_period, day_of_month, hour, minute)


def _register_schedule_for_qa(
    qauid: str, user_id: str, project_id: int | None,
    day_of_month: int, hour: int, minute: int,
) -> dict:
    """보고서(qauid) 하나를 정기 보고서로 등록한다 — REST 버튼 경로와 대화(챗) 경로가 공유하는
    핵심 로직. 스케줄마다 전용 세션을 새로 만든다 — 원래 대화 세션은 건드리지 않는다(등록 시
    원래 세션 전체가 대화 목록에서 사라지고 그 세션의 다른 보고서까지 회차로 섞여 들어가던
    문제의 원인이었다). 등록 기준이 된 원본 보고서를 그 전용 세션의 첫 기록으로 남긴다.
    """
    qa, answer_json, template_nm = _resolve_schedule_origin(qauid)

    tenant_id, db_project_id = storage.get_project_info(user_id)
    resolved_project_id = project_id if project_id is not None else db_project_id

    intent = parse_intent(qa.get("question") or "", project_id=resolved_project_id,
                          tenant_id=tenant_id, user_uid=user_id)
    report_type = intent.get("report_type") or "보고서"
    months_back = intent.get("months_back") or 3

    cron = _sched_mod.compose_cron("month", day_of_month, None, hour, minute)
    next_dt = _next_schedule_run(qa, day_of_month, hour, minute)

    dedicated_sid = storage.create_session(tenant_id, resolved_project_id, user_id)
    storage.update_session_title(dedicated_sid, template_nm)

    templateuid = storage.create_analytic_template(
        tenant_id=tenant_id,
        project_id=resolved_project_id,
        session_uid=dedicated_sid,
        template_nm=template_nm,
        period_json={"grain": "month", "offset": -1, "report_type": report_type, "months_back": months_back},
        global_json={},
        steps_json=answer_json.get("applied_steps"),
        schedule_cron=cron,
        schedule_start_dt=next_dt.isoformat(),
        creator=user_id,
        analytic_uid=answer_json.get("analytic_uid"),
    )

    try:
        storage.append_qa(
            session_uid=dedicated_sid, tenant_id=tenant_id, project_id=resolved_project_id,
            question=f"{storage.SCHEDULE_ORIGIN_MARKER} {template_nm}",
            answer_json=answer_json,
            creator=user_id,
            filenm=qa.get("filenm"), fileurl=qa.get("fileurl"),
            servicecd="In",
        )
    except Exception as e:
        # print(f"[schedule] 원본 보고서 기록 실패: {e}")
        pass

    return {"ok": True, "template_uid": templateuid, "session_id": dedicated_sid, "template_nm": template_nm}


@router.post("/schedule/register-preview", dependencies=[Depends(require_insight_write)])
def preview_register_schedule(body: ScheduleRegisterRequest, token: str = Depends(get_token)):
    """정기 보고서 등록 전 확인 문구(중복 등록 여부 + 다음 실행 예정일시)를 반환한다."""
    _check_owner(token, body.user_id)
    qa, _answer_json, _template_nm = _resolve_schedule_origin(body.qauid)
    next_dt = _next_schedule_run(qa, body.day_of_month, body.hour, body.minute)
    message = _sched_mod.build_register_message(next_dt, "month", body.day_of_month, None, body.hour, body.minute)
    return {"message": message}


@router.post("/schedule/register", dependencies=[Depends(require_insight_write)])
def register_schedule(body: ScheduleRegisterRequest, token: str = Depends(get_token)):
    """지정한 보고서(qauid) 하나를 정기 보고서로 등록한다(오른쪽 패널의 버튼 경로)."""
    _check_owner(token, body.user_id)
    return _register_schedule_for_qa(
        body.qauid, body.user_id, body.project_id, body.day_of_month, body.hour, body.minute,
    )


@router.get("/schedule/{session_id}/turns", dependencies=[Depends(require_insight_read)])
def get_schedule_turns(session_id: str, token: str = Depends(get_token)):
    """정기 보고서 세션의 실행 턴 목록(회차별, 최근순) 반환 — 사이드바가 펼쳐서 보여준다."""
    return storage.get_schedule_turns(session_id)


@router.delete("/schedule/turn/{qauid}/{user_id}", dependencies=[Depends(require_insight_write)])
def delete_schedule_turn(qauid: str, user_id: str, token: str = Depends(get_token)):
    """정기 보고서 회차 하나를 하드 삭제한다 — 되돌릴 수 없다(프런트에서 확인 후 호출)."""
    _check_owner(token, user_id)
    storage.delete_qa(qauid, user_id)
    return {"ok": True}


@router.get("/schedule/{session_id}/settings", dependencies=[Depends(require_insight_read)])
def get_schedule_settings(session_id: str, token: str = Depends(get_token)):
    """등록된 정기 보고서의 현재 요일/일자/시간 설정 반환 — 수정 폼 초기값으로 쓴다."""
    template = storage.get_active_template_by_session(session_id)
    if not template:
        raise HTTPException(status_code=404, detail="등록된 정기 보고서가 없습니다.")
    settings = _sched_mod.parse_cron(template["schedulecron"])
    settings["template_uid"] = template["templateuid"]
    return settings


@router.post("/schedule/{session_id}/update-preview", dependencies=[Depends(require_insight_write)])
def preview_schedule_update(session_id: str, body: ScheduleUpdateRequest, token: str = Depends(get_token)):
    """일정 변경 전 확인 문구(효력발생일 안내)를 반환한다."""
    _check_owner(token, body.user_id)
    template = storage.get_active_template_by_session(session_id)
    if not template:
        raise HTTPException(status_code=404, detail="등록된 정기 보고서가 없습니다.")
    old_settings = _sched_mod.parse_cron(template["schedulecron"])
    new_settings = {"grain": old_settings["grain"], "day_of_month": body.day_of_month,
                    "weekday": None, "hour": body.hour, "minute": body.minute}
    decision = _sched_mod.compute_schedule_update(old_settings, new_settings, datetime.now(tz=_sched_mod.KST))
    message = _sched_mod.build_update_message(decision, new_settings)
    return {
        "message": message,
        "immediate_run": decision["immediate_run"],
        "effective": decision["effective"],
        "effective_start": decision["effective_start"].isoformat(),
    }


@router.post("/schedule/{session_id}/update", dependencies=[Depends(require_insight_write)])
def apply_schedule_update(session_id: str, body: ScheduleUpdateRequest, token: str = Depends(get_token)):
    """확인된 일정 변경을 실제로 적용한다(즉시 실행은 하지 않음 — 본프로젝트 Schedule 트리거 몫)."""
    _check_owner(token, body.user_id)
    template = storage.get_active_template_by_session(session_id)
    if not template:
        raise HTTPException(status_code=404, detail="등록된 정기 보고서가 없습니다.")
    old_settings = _sched_mod.parse_cron(template["schedulecron"])
    new_settings = {"grain": old_settings["grain"], "day_of_month": body.day_of_month,
                    "weekday": None, "hour": body.hour, "minute": body.minute}
    decision = _sched_mod.compute_schedule_update(old_settings, new_settings, datetime.now(tz=_sched_mod.KST))
    new_cron = _sched_mod.compose_cron(new_settings["grain"], body.day_of_month, None, body.hour, body.minute)
    storage.update_analytic_template_schedule(template["templateuid"], new_cron, decision["effective_start"].isoformat())
    return {
        "ok": True,
        "immediate_run": decision["immediate_run"],
        "effective": decision["effective"],
        "effective_start": decision["effective_start"].isoformat(),
    }


@router.post("/schedule/{session_id}/share", dependencies=[Depends(require_insight_write)])
def share_schedule(session_id: str, body: ScheduleShareRequest, token: str = Depends(get_token)):
    """정기 보고서 세션을 같은 project 내 다른 사용자에게 공유한다."""
    _check_owner(token, body.user_id)
    tenant_id, project_id = storage.get_project_info(body.user_id)
    share_uid = storage.share_schedule_session(session_id, tenant_id, project_id, body.user_id)
    return {"ok": True, "share_uid": share_uid}


@router.delete("/schedule/share/{share_uid}/{user_id}", dependencies=[Depends(require_insight_write)])
def unshare_schedule(share_uid: str, user_id: str, token: str = Depends(get_token)):
    """공유를 종료한다(공유자·수신자 모두 호출 가능 — 세션 전체 공유라 소유자 제한을 두지 않는다)."""
    _check_owner(token, user_id)
    storage.end_schedule_share(share_uid, datetime.now(tz=_sched_mod.KST).isoformat())
    return {"ok": True}


@router.get("/schedule/shares/sent/{user_id}", dependencies=[Depends(require_insight_read)])
def get_schedule_shares_sent(user_id: str, token: str = Depends(get_token)):
    """내가 공유한 정기 보고서 목록(활성만) 반환."""
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_schedule_shares_sent(user_id, offsetminutes)


@router.get("/schedule/shares/received/{user_id}", dependencies=[Depends(require_insight_read)])
def get_schedule_shares_received(user_id: str, token: str = Depends(get_token)):
    """같은 project에서 내가 받은 정기 보고서 공유 목록(활성만) 반환."""
    _check_owner(token, user_id)
    _, project_id = storage.get_project_info(user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_schedule_shares_received(project_id, user_id, offsetminutes)


@router.delete("/schedule/shares/received/{share_uid}/{user_id}", dependencies=[Depends(require_insight_write)])
def delete_schedule_share_received(share_uid: str, user_id: str, token: str = Depends(get_token)):
    """공유받은 목록에서 제거한다 — 세션 전체 공유라 실제로는 공유 자체를 종료한다."""
    _check_owner(token, user_id)
    storage.end_schedule_share(share_uid, datetime.now(tz=_sched_mod.KST).isoformat())
    return {"ok": True}


@router.get("/schedule/shares/{share_uid}/turns", dependencies=[Depends(require_insight_read)])
def get_schedule_share_turns(share_uid: str, token: str = Depends(get_token)):
    """공유받은 정기 보고서의 회차 목록 — 공유 종료 시점 이후 회차는 제외한다."""
    share = storage.get_schedule_share(share_uid)
    if not share:
        raise HTTPException(status_code=404, detail="공유를 찾을 수 없습니다.")
    return storage.get_schedule_turns(share["sessionuid"], until=share.get("enddts"))


@router.post("/scheduled/run")
def run_scheduled(body: ScheduledRunRequest):
    """템플릿 1건을 무인 실행한다 — 트리거 연동은 범위 밖(본프로젝트 Schedule 시스템이 호출)."""
    from d2insight.chat.scheduled_runner import run_scheduled_template
    run_date = date.fromisoformat(body.run_date) if body.run_date else None
    return run_scheduled_template(body.template_uid, run_date)


# ── 초기 로딩 통합 (bootstrap) ────────────────────────────────────

@router.get("/bootstrap/{user_id}", dependencies=[Depends(require_insight_read)])
def get_bootstrap(user_id: str, token: str = Depends(get_token)):
    """사이드바 초기 로딩에 필요한 데이터를 한 번에 반환.

    _check_owner·offsetminutes를 1회만 수행해 즐겨찾기/히스토리/공유(2)/정기보고서
    공유(2) 총 6개를 개별 호출할 때 생기는 중복 조회를 없앤다. 개별 액션 후 부분
    갱신에는 기존 엔드포인트를 그대로 사용한다.
    """
    _check_owner(token, user_id)
    _, project_id = storage.get_project_info(user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return {
        "favorites": storage.get_favorites(user_id, offsetminutes),
        "history": storage.get_history_by_date(user_id, offsetminutes),
        "shares_sent": storage.get_shares_sent(user_id, offsetminutes),
        "shares_received": storage.get_shares_received(project_id, user_id, offsetminutes),
        "schedule_shares_sent": storage.get_schedule_shares_sent(user_id, offsetminutes),
        "schedule_shares_received": storage.get_schedule_shares_received(project_id, user_id, offsetminutes),
    }


# ── 히스토리 ─────────────────────────────────────────────────────

@router.get("/history/{user_id}", dependencies=[Depends(require_insight_read)])
def get_history(user_id: str, token: str = Depends(get_token)):
    """날짜별로 그룹화된 세션 목록 반환."""
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_history_by_date(user_id, offsetminutes)


@router.get("/history/{user_id}/{session_id}", dependencies=[Depends(require_insight_read)])
def get_session_messages(user_id: str, session_id: str, token: str = Depends(get_token)):
    """세션의 Q&A 메시지 목록 반환.

    메시지가 0건인 것과 세션 자체가 없는 것을 구분한다 — 정기 보고서 전용 세션은 등록
    직후 아직 실행 이력이 없어도(QA 0건) 정상 세션이다. 메시지 유무로 404를 판단하면
    등록 직후 그 세션을 열었을 때 "찾을 수 없음"으로 잘못 뜬다.
    """
    _check_owner(token, user_id)
    if not storage.get_session(session_id):
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    messages = storage.get_session_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/history/{user_id}/{session_id}", dependencies=[Depends(require_insight_write)])
def delete_session(user_id: str, session_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.delete_session(session_id, user_id)
    return {"ok": True}


# ── 즐겨찾기 ─────────────────────────────────────────────────────

@router.get("/favorites/{user_id}", dependencies=[Depends(require_insight_read)])
def get_favorites(user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_favorites(user_id, offsetminutes)


@router.post("/favorite/qa", dependencies=[Depends(require_insight_write)])
def add_favorite_qa(body: FavoriteQARequest, token: str = Depends(get_token)):
    _check_owner(token, body.user_id)
    ok = storage.add_favorite_qa(body.qauid, body.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/favorite/qa/{user_id}/{qauid}", dependencies=[Depends(require_insight_write)])
def remove_favorite_qa(user_id: str, qauid: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.remove_favorite_qa(qauid, user_id)
    return {"ok": True}


# ── 폴더 ─────────────────────────────────────────────────────────

@router.get("/folders/{user_id}", dependencies=[Depends(require_insight_read)])
def get_folders(user_id: str, token: str = Depends(get_token)):
    """폴더 목록 반환. 폴더가 없으면 샘플 폴더를 자동 생성한다."""
    _check_owner(token, user_id)
    tenant_id, _ = storage.get_project_info(user_id)
    storage.seed_sample_folders(tenant_id, user_id)
    return storage.get_folders(tenant_id)


# ── 공유 ─────────────────────────────────────────────────────────

@router.post("/share", dependencies=[Depends(require_insight_write)])
def share_qa(body: ShareRequest, token: str = Depends(get_token)):
    """QA를 같은 tenant의 모든 사용자와 공유한다."""
    _check_owner(token, body.user_id)
    ok = storage.share_qa(body.qauid, body.user_id, body.folder_uid)
    if not ok:
        raise HTTPException(status_code=404, detail="QA를 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/shares/sent/{user_id}", dependencies=[Depends(require_insight_read)])
def get_shares_sent(user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_shares_sent(user_id, offsetminutes)


@router.delete("/shares/sent/{share_qauid}/{user_id}", dependencies=[Depends(require_insight_write)])
def delete_share_sent(share_qauid: str, user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.delete_share_sent(share_qauid, user_id)
    return {"ok": True}


@router.delete("/shares/received/{share_qauid}/{user_id}", dependencies=[Depends(require_insight_write)])
def delete_share_received(share_qauid: str, user_id: str, token: str = Depends(get_token)):
    _check_owner(token, user_id)
    storage.delete_share_received(share_qauid, user_id)
    return {"ok": True}


@router.get("/shares/received/{user_id}", dependencies=[Depends(require_insight_read)])
def get_shares_received(user_id: str, token: str = Depends(get_token)):
    """같은 project에서 내가 만들지 않은 공유 보고서 목록 반환."""
    _check_owner(token, user_id)
    _, project_id = storage.get_project_info(user_id)
    offsetminutes = storage.get_offsetminutes(user_id)
    return storage.get_shares_received(project_id, user_id, offsetminutes)


@router.get("/shares/{share_qauid}", dependencies=[Depends(require_insight_read)])
def get_share_detail(share_qauid: str, token: str = Depends(get_token)):
    """공유된 QA 내용 조회 (로그인한 사용자면 누구나 조회 가능 — 공유 링크 특성상 소유자 검증 없음)."""
    _get_user(token)
    row = storage.get_share(share_qauid)
    if not row:
        raise HTTPException(status_code=404, detail="공유 내역을 찾을 수 없습니다.")
    return row


# ── 카탈로그 (읽기 전용) ─────────────────────────────────────────────
# 시나리오·스텝·모듈·툴 정의를 프론트에 노출한다. 옵션 패널이 이 응답 하나로
# "무엇을 고를 수 있는지"를 채운다. 순수 데이터라 인증 없이 반환한다.

def _module_spec_to_dict(spec) -> dict:
    """ModuleSpec(dataclass) → JSON 직렬화 가능한 dict.

    `run`(실행 함수, Callable)은 프론트가 쓸 일이 없고 JSON으로 직렬화도 안 되므로 제외한다.
    """
    return {
        "module_id": spec.module_id,
        "purpose": spec.purpose,
        "kind": spec.kind,
        "requires": list(spec.requires),
        "produces": list(spec.produces),
        "params": spec.params,
        "tools": spec.tools,
        "model_tier": spec.model_tier,
        "narrative_hint": spec.narrative_hint,
        "layout": list(spec.layout),
    }


@router.get("/catalog")
def get_catalog() -> dict:
    """d2insight 카탈로그(시나리오/스텝/모듈/툴) 조회 — 프론트 옵션 패널용."""
    from d2insight.engine.catalog.scenarios import SCENARIO_REGISTRY
    from d2insight.engine.catalog.steps import STEP_REGISTRY
    from d2insight.engine.catalog.modules import MODULE_REGISTRY
    from d2insight.engine.catalog.tools import TOOL_REGISTRY
    return {
        "scenarios": SCENARIO_REGISTRY,
        "steps": STEP_REGISTRY,
        "modules": {mid: _module_spec_to_dict(spec) for mid, spec in MODULE_REGISTRY.items()},
        "tools": TOOL_REGISTRY,
    }


# ── 보고서 preview (engine.entry의 match_scenario/preview_report_plan 직접 호출) ──
# 2026-08-20까지는 이 로직을 로컬로 재구현해서 썼는데, 그러면 entry.py가 이미 제공하는
# extract_operations/apply_operations(사용자가 문장으로 "OO는 빼줘/top 5개만" 같은 편집을
# 지시하는 기능)와 inline_options(옵션 JSON 붙여넣기)가 반영되지 않았다. entry.py를 그대로
# 호출하도록 바꿔 이 기능들이 자동으로 살아나게 한다(단독앱 pr_module_insight/app/chat/
# router.py의 /report/preview와 동일한 패턴).

class ReportPreviewRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    account_uid: str | None = None


def _resolve_report_project(user_id: str | None, project_id: int | None) -> tuple[int | None, int | None]:
    """user_id로 tenant_id/project_id를 채운다. 반환: (tenant_id, resolved_project_id)."""
    tenant_id: int | None = None
    resolved_project_id = project_id
    if user_id:
        try:
            tenant_id, pid = storage.get_project_info(user_id)
            if resolved_project_id is None:
                resolved_project_id = pid
        except Exception:
            pass
    return tenant_id, resolved_project_id


def _resolve_report_source(session_id: str | None, resolved_project_id: int | None) -> tuple[str | None, str | None]:
    """세션의 업로드/DB 데이터소스를 판별한다. 반환: (upload_dataset_key, source_id)."""
    from d2insight.chat.pipeline_runner import _upload_engine_target

    has_upload = bool(session_id and get_excel_server().has_datasets(session_id))
    upload_dataset_key = _upload_engine_target(session_id) if has_upload else None
    if upload_dataset_key:
        return upload_dataset_key, None

    from d2insight.engine.pipeline.db_meta import DbMetaError, resolve_source_cluster
    try:
        source_id = "+".join(c["datauid"] for c in resolve_source_cluster(resolved_project_id))
    except DbMetaError:
        return None, None
    return None, source_id


@router.post("/report/preview", dependencies=[Depends(require_insight_write)])
def preview_report(req: ReportPreviewRequest, token: str = Depends(get_token)) -> dict:
    """보고서 요청 문장 → 시나리오 매칭 + 스텝·모듈·툴 트리 반환(실행 X).

    프론트 옵션 패널이 이 응답으로 preview 표시 → "이대로 작성" 버튼 클릭 시 /chat 실행.
    """
    _check_owner(token, req.user_id)
    from d2insight.engine.catalog.modules import MODULE_REGISTRY
    from d2insight.engine.catalog.scenarios import SCENARIO_REGISTRY
    from d2insight.engine.entry import extract_inline_options, match_scenario, preview_report_plan

    tenant_id, resolved_project_id = _resolve_report_project(req.user_id, req.project_id)

    # entry.py 안의 _llm.py::chat()은 project_id/tenant_id를 인자로 안 받고 이 log_ctx를
    # 읽어 프로젝트/테넌트별 LLM을 고른다(/chat 엔드포인트와 동일 패턴) — 빠뜨리면 시나리오
    # 매칭·편집연산 추출이 테넌트 설정을 무시하고 기본 LLM으로 돈다.
    token_tracker.set_log_ctx({
        "qauid": None,
        "servicecd": "In",
        "tenant_id": tenant_id,
        "project_id": resolved_project_id,
        "session_uid": None,
        "creator": req.user_id,
        "account_uid": req.account_uid,
    })

    inline_options = extract_inline_options(req.message)
    matched = match_scenario(req.message)

    upload_dataset_key, source_id = _resolve_report_source(req.session_id, resolved_project_id)
    if not upload_dataset_key and source_id is None:
        return {"scenario": None, "report_title": "", "applied_steps": []}

    # target_month는 이 트리 조립(스텝·모듈 구성) 자체엔 반영되지 않는다(실행 시점에
    # run_engine_report가 실제 값으로 다시 받음) — 여기선 필수 인자라 오늘 날짜로 채운다.
    today = datetime.now()
    try:
        result = preview_report_plan(
            message=req.message,
            target_month=f"{today.year:04d}-{today.month:02d}",
            # matched가 없으면(JSON만 있는 경우) report_type을 아예 안 넘긴다 — 굳이 임의의
            # 시나리오 이름으로 채우지 않아도 preview_report_plan() 자체에 중립적인 기본값이
            # 있다(entry.py). matched가 있으면 그 이름을 그대로 report_type으로도 쓴다.
            **({"report_type": matched} if matched else {}),
            source_id=source_id,
            upload_session_id=req.session_id if upload_dataset_key else None,
            upload_dataset_key=upload_dataset_key,
            matched_scenario=matched,
            inline_options=inline_options,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"옵션 미리보기 실패: {type(e).__name__}: {e}")

    applied_steps = result.get("applied_steps") or []
    for step in applied_steps:
        for m in step.get("modules", []):
            mdef = MODULE_REGISTRY.get(m.get("module_id"))
            if mdef is not None:
                m["purpose"] = mdef.purpose

    scenario = result.get("scenario") or matched
    return {
        "scenario": scenario,
        "report_title": SCENARIO_REGISTRY.get(scenario, {}).get("report_title", ""),
        "applied_steps": applied_steps,
    }


class ValidateStepsRequest(BaseModel):
    steps: list[dict]
    scenario: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    account_uid: str | None = None
    global_: dict = Field(default_factory=dict, alias="global")


@router.post("/report/validate_steps", dependencies=[Depends(require_insight_write)])
def validate_steps(req: ValidateStepsRequest, token: str = Depends(get_token)) -> dict:
    """스텝 JSON을 스키마 기준으로 재검증(LLM 호출 없음). 미리보기 JSON 편집 저장 시 사용."""
    _check_owner(token, req.user_id)
    from d2insight.engine.catalog.modules import MODULE_REGISTRY
    from d2insight.engine.entry import _upload_schema
    from d2insight.engine.options import OptionsError, global_to_meta, options_to_plan
    from d2insight.engine.planner import PlannerError, data_digest

    _, resolved_project_id = _resolve_report_project(req.user_id, req.project_id)
    upload_dataset_key, source_id = _resolve_report_source(req.session_id, resolved_project_id)
    if not upload_dataset_key and source_id is None:
        return {"applied_steps": req.steps}

    upload_schema = _upload_schema(req.session_id if upload_dataset_key else None, upload_dataset_key)
    schema, _ = data_digest(source_id, schema=upload_schema)
    meta = global_to_meta({"global": req.global_})

    try:
        plan, notes = options_to_plan(
            {"scenario": req.scenario, "steps": req.steps}, schema, global_measure=meta.get("measure"),
        )
    except (PlannerError, OptionsError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    applied_steps = plan.get("steps") or []
    for step in applied_steps:
        for m in step.get("modules", []):
            mdef = MODULE_REGISTRY.get(m.get("module_id"))
            if mdef is not None:
                m["purpose"] = mdef.purpose

    return {"applied_steps": applied_steps, "notes": notes}


# ── 기타 ─────────────────────────────────────────────────────────

@router.get("/health")
def api_health() -> dict:
    return {"status": "ok"}
