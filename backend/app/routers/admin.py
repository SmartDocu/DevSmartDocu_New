"""Admin router — roleid=7 전용 (사용자 관리, 샘플 프롬프트, LLM 관리 등)"""
import sys
import uuid
import traceback

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
from utilsPrj.user_lookup import get_usernm_email
from utilsPrj.audit_log import log_admin_action, snapshot_row, get_client_ip

router = APIRouter()

VALID_ROLE_IDS = {1, 5, 7}


def _role_options(sb):
    """codes 테이블(codegroupcd='userroleid')에서 역할 목록을 조회한다. 다국어는 프론트에서 term_key로 처리."""
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("codes")
        .select("codevalue,default_name")
        .eq("codegroupcd", "userroleid")
        .eq("useyn", True)
        .order("orderno")
        .execute().data or []
    )
    return [
        {"value": int(r["codevalue"]), "term_key": f"cod.userroleid_{r['codevalue']}", "default_name": r.get("default_name")}
        for r in rows
    ]


def _sb_service():
    return get_service_client()


def _get_user(token: str):
    try:
        sb = get_sb(token)
        resp = sb.auth.get_user(token)
        if not resp or not resp.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
        return resp.user
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "expired" in err_msg or "invalid jwt" in err_msg or "invalid claims" in err_msg:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰이 만료되었습니다.")
        # print(f"[admin._get_user] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"인증 오류: {str(e)}")


def _require_admin(token: str):
    """roleid=7 인지 확인"""
    try:
        user = _get_user(token)
        sb = _sb_service()
        row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user.id).execute().data
        roleid = row[0].get("roleid") if row else None
        if roleid != 7:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다.")
        return user
    except HTTPException:
        raise
    except Exception as e:
        # print(f"[admin._require_admin] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"관리자 확인 오류: {str(e)}")


# ══════════════════════════════════════════════════════
#  USER ROLE (사용자 권한 관리)
# ══════════════════════════════════════════════════════

@router.get("/user-role")
def list_user_roles(request: Request, token: str = Depends(get_token)):
    admin = _require_admin(token)
    sb = _sb_service()

    role_options = _role_options(sb)
    role_map = {r["value"]: r["default_name"] for r in role_options}

    rows = sb.schema(SUPABASE_SCHEMA).table("users").select("useruid,roleid,email").order("email").execute().data or []
    for u in rows:
        u["role_name"] = role_map.get(u.get("roleid", 1), "User")

    log_admin_action(
        useruid=str(admin.id), roleid=7, actioncd="view_user",
        targettype="users", detail={"count": len(rows)},
        ip=get_client_ip(request),
    )
    return {"users": rows, "role_options": role_options}


class UserRoleSaveRequest(BaseModel):
    useruid: str
    roleid: int


@router.post("/user-role")
def save_user_role(body: UserRoleSaveRequest, request: Request, token: str = Depends(get_token)):
    admin = _require_admin(token)
    sb = _sb_service()

    if body.roleid not in VALID_ROLE_IDS:
        raise HTTPException(status_code=400, detail="유효하지 않은 역할입니다.")

    before = snapshot_row(sb, "users", "useruid", body.useruid)
    sb.schema(SUPABASE_SCHEMA).table("users").update({"roleid": body.roleid}).eq("useruid", body.useruid).execute()
    after = snapshot_row(sb, "users", "useruid", body.useruid)
    log_admin_action(
        useruid=str(admin.id), roleid=7, actioncd="permission_change",
        targettype="users", targetid=body.useruid, before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"result": "success", "message": "권한이 변경되었습니다."}


# ══════════════════════════════════════════════════════
#  SAMPLE PROMPTS (샘플 프롬프트 관리)
# ══════════════════════════════════════════════════════

OBJECT_TYPES = [
    {"value": "CA", "label": "차트 (Chart)"},
    {"value": "SA", "label": "문장 (Sentence)"},
    {"value": "TA", "label": "테이블 (Table)"},
]
CHART_TYPES = [
    {"value": "bar", "label": "Bar Chart"},
    {"value": "line", "label": "Line Chart"},
    {"value": "pie", "label": "Pie Chart"},
    {"value": "scatter", "label": "Scatter"},
    {"value": "boxplot", "label": "Box Plot"},
    {"value": "histogram", "label": "Histogram"},
    {"value": "dual_axis", "label": "Dual Axis"},
    {"value": "heatmap", "label": "Heatmap"},
    {"value": "subplot", "label": "Subplot"},
]
SENTENCE_TYPES = [
    {"value": "simple_question", "label": "단순 질의"},
    {"value": "summary", "label": "요약"},
    {"value": "report", "label": "보고서"},
    {"value": "predict", "label": "예측"},
]
TABLE_TYPES = [
    {"value": "table", "label": "테이블"},
]


@router.get("/sample-prompts")
def list_sample_prompts(
    object_type: str = Query("CA"),
    displaytype: Optional[str] = Query(None),
    token: str = Depends(get_token),
):
    try:
        _require_admin(token)
        sb = _sb_service()

        # prompts 조회
        q = sb.schema(SUPABASE_SCHEMA).table("prompts").select("*").eq("objecttypecd", object_type)
        if displaytype:
            q = q.eq("displaytype", displaytype)
        rows = q.order("orderno").execute().data or []

        # datas 목록 (미리보기용 데이터 선택)
        datas = sb.schema(SUPABASE_SCHEMA).table("datas").select("datauid,datanm").order("datanm").execute().data or []

        return {
            "prompts": rows,
            "datas": datas,
            "object_types": OBJECT_TYPES,
            "chart_types": CHART_TYPES,
            "sentence_types": SENTENCE_TYPES,
            "table_types": TABLE_TYPES,
        }
    except HTTPException:
        raise
    except Exception as e:
        # print(f"[admin.list_sample_prompts] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"샘플 프롬프트 조회 오류: {str(e)}")


class SamplePromptSaveRequest(BaseModel):
    promptuid: Optional[str] = None
    objecttypecd: str
    datauid: Optional[str] = None
    promptnm: str
    prompt: Optional[str] = None
    promptdesc: Optional[str] = None
    displaytype: Optional[str] = None
    force_update: bool = False


@router.post("/sample-prompts")
def save_sample_prompt(body: SamplePromptSaveRequest, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    if not body.promptnm.strip():
        raise HTTPException(status_code=400, detail="프롬프트 이름을 입력해주세요.")

    if body.promptuid:
        # 기존 수정 — force_update=False이면 confirm 응답
        if not body.force_update:
            return {
                "success": False,
                "error": "confirm_update",
                "message": "샘플 프롬프트가 수정되었습니다. 저장할까요?",
                "promptuid": body.promptuid,
            }
        before = snapshot_row(sb, "prompts", "promptuid", body.promptuid)
        sb.schema(SUPABASE_SCHEMA).table("prompts").update({
            "promptnm": body.promptnm.strip(),
            "prompt": body.prompt,
            "desc": body.promptdesc,
            "displaytype": body.displaytype,
        }).eq("promptuid", body.promptuid).execute()
        after = snapshot_row(sb, "prompts", "promptuid", body.promptuid)
        log_admin_action(
            useruid=str(user.id), roleid=7, actioncd="update",
            targettype="prompts", targetid=body.promptuid, before=before, after=after,
            ip=get_client_ip(request),
        )
        return {"success": True, "message": "수정되었습니다."}

    # 신규 저장
    new_uid = str(uuid.uuid4())
    sb.schema(SUPABASE_SCHEMA).table("prompts").insert({
        "promptuid": new_uid,
        "objecttypecd": body.objecttypecd,
        "datauid": body.datauid or None,
        "promptnm": body.promptnm.strip(),
        "prompt": body.prompt,
        "desc": body.promptdesc,
        "displaytype": body.displaytype,
        "creator": user.id,
    }).execute()
    after = snapshot_row(sb, "prompts", "promptuid", new_uid)
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="update",
        targettype="prompts", targetid=new_uid, after=after,
        ip=get_client_ip(request),
    )
    return {"success": True, "message": "저장되었습니다."}


@router.delete("/sample-prompts/{promptuid}")
def delete_sample_prompt(promptuid: str, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    if not promptuid:
        raise HTTPException(status_code=400, detail="삭제할 프롬프트를 선택해주세요.")

    before = snapshot_row(sb, "prompts", "promptuid", promptuid)
    sb.schema(SUPABASE_SCHEMA).table("prompts").delete().eq("promptuid", promptuid).execute()
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="delete",
        targettype="prompts", targetid=promptuid, before=before,
        ip=get_client_ip(request),
    )
    return {"success": True, "message": "삭제되었습니다."}


# ── 샘플 프롬프트 미리보기 ────────────────────────────────────────────────────

class SamplePromptPreviewRequest(BaseModel):
    prompt: str
    objecttypecd: str          # CA / SA / TA
    datauid: Optional[str] = None
    displaytype: Optional[str] = None
    account_uid: Optional[str] = None  # 프론트 authStore에서 전달 (get_llm_info의 serviceusers 조회 생략용)


@router.post("/sample-prompts/preview")
def sample_prompt_preview(body: SamplePromptPreviewRequest, token: str = Depends(get_token)):
    """샘플 프롬프트 미리보기 — chapteruid/objectnm 없이 datauid+prompt 만으로 실행"""
    _require_admin(token)

    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="프롬프트를 입력해주세요.")
    if not body.datauid:
        raise HTTPException(status_code=400, detail="데이터를 선택해주세요.")

    from utilsPrj.process_data import process_data
    from utilsPrj.ai_chain import (
        get_charts_prompt, get_sentences_prompt, get_tables_prompt,
        get_full_chain, get_llm_info, build_langchain_llm,
    )
    from backend.app.routers.llm import FakeLlmRequest, _get_user_info

    sb_user = get_sb(token)
    user_id, _ = _get_user_info(sb_user, token)
    sb_svc = get_service_client()

    # ── datas 조회: projectid, tenantid, datasourcecd, sourcedatauid 확인 ──
    data_rows = sb_svc.schema(SUPABASE_SCHEMA).table("datas").select(
        "projectid, datasourcecd, sourcedatauid"
    ).eq("datauid", body.datauid).execute().data or []

    projectid = data_rows[0].get("projectid") if data_rows else None
    tenantid = None
    if projectid:
        proj_rows = sb_svc.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq(
            "projectid", projectid
        ).execute().data or []
        if proj_rows:
            tenantid = proj_rows[0].get("tenantid")

    col_datauid = body.datauid
    if data_rows and data_rows[0].get("datasourcecd") == "df":
        col_datauid = data_rows[0].get("sourcedatauid") or body.datauid

    req = FakeLlmRequest(token, user_id, projectid=projectid, tenantid=tenantid, docid=None)

    try:
        result_df = process_data(req, body.datauid, None, all=True)
    except Exception as e:
        tb = traceback.format_exc()
        # print(f"[sample-prompt/preview] process_data 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=400, detail=f"데이터 조회 오류: {str(e)}")

    try:
        datacols = sb_svc.schema(SUPABASE_SCHEMA).table("datacols").select(
            "querycolnm, dispcolnm"
        ).eq("datauid", col_datauid).execute().data or []
    except Exception:
        datacols = []
    column_dict = {r["querycolnm"]: r["dispcolnm"] for r in datacols}

    ot = body.objecttypecd
    if ot == "CA":
        prompt = get_charts_prompt(result_df, column_dict, body.prompt)
    elif ot == "SA":
        prompt = get_sentences_prompt(result_df, column_dict, body.prompt)
    elif ot == "TA":
        prompt = get_tables_prompt(result_df, column_dict, body.prompt)
    else:
        raise HTTPException(status_code=400, detail="잘못된 objecttypecd")

    try:
        _llm_model_nm, _dec_api_key, _vendor_name, is_customeraikey, account_uid = get_llm_info(
            project_id=projectid, tenant_id=tenantid, user_uid=user_id,
            account_uid=body.account_uid, service_code="Do",
        )
        llm = build_langchain_llm(_vendor_name, _dec_api_key, _llm_model_nm)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 모델 로드 오류: {str(e)}")

    from d2shared.llm_logger import log_doc_llm_call

    def _write_doc_log(is_success, errormessage, inputtoken, outputtoken, start_dts, end_dts):
        log_doc_llm_call(
            log_ctx={
                "tenant_id":         tenantid,
                "account_uid":       account_uid,
                "project_id":        projectid,
                "gencontenttypecd":  None,  # 단독(Definition) — admin 샘플 프롬프트 테스트
                "objectuid":         None,
                "is_customeraikey":  is_customeraikey,
                "creator":           user_id,
            },
            llmmodelnm=getattr(llm, "model", None) or getattr(llm, "model_name", None) or "",
            inputtoken=inputtoken,
            outputtoken=outputtoken,
            is_success=is_success,
            errormessage=errormessage,
            startdts=start_dts,
            enddts=end_dts,
        )

    full_chain = get_full_chain(llm, result_df, prompt, body.prompt, column_dict, ot)
    from datetime import datetime, timezone
    _llm_start_dts = datetime.now(timezone.utc)
    try:
        response = full_chain.invoke({"question": body.prompt, "column_dict": column_dict})
    except Exception as e:
        _write_doc_log(False, str(e), 0, 0, _llm_start_dts, datetime.now(timezone.utc))
        raise HTTPException(status_code=500, detail=f"LLM 실행 오류: {str(e)}")
    _llm_end_dts = datetime.now(timezone.utc)

    if not isinstance(response, dict):
        _write_doc_log(False, "LLM 응답 형식 오류", 0, 0, _llm_start_dts, _llm_end_dts)
        raise HTTPException(status_code=500, detail="LLM 응답 형식 오류")

    status_val = response.get("status")

    _tokens = response.get("tokens", {})
    _is_success = status_val in ("chart_drawn", "analysis_comment", "data_table")
    _write_doc_log(
        _is_success,
        None if _is_success else str(response.get("error") or status_val),
        _tokens.get("input_tokens", 0),
        _tokens.get("output_tokens", 0),
        _llm_start_dts,
        _llm_end_dts,
    )

    if status_val == "chart_drawn":
        return {"message_type": "image", "image_data": response["image_bytes"],
                "question": response.get("question", "")}
    elif status_val == "analysis_comment":
        return {"message_type": "text", "message": response.get("result", "")}
    elif status_val == "data_table":
        return {"message_type": "table", "message": "",
                "data": response.get("result", ""),
                "table_header_json": response.get("table_header_json", ""),
                "table_data_json": response.get("table_data_json", "")}
    else:
        error_msg = response.get("error", "알 수 없는 응답 형식입니다.")
        return {"message_type": "error", "message": error_msg}


# ══════════════════════════════════════════════════════
#  HELPS (도움말 관리)
# ══════════════════════════════════════════════════════

class HelpSaveRequest(BaseModel):
    helpuid: Optional[str] = None
    help: str
    url: Optional[str] = None
    desc: Optional[str] = None
    languagecd: str = "en"


@router.get("/helps/search")
def search_help(url: str = Query(...), languagecd: str = Query(default="en")):
    """URL + 언어로 도움말 검색 (인증 불필요). 없으면 영어 fallback."""
    sb = _sb_service()
    rows = sb.schema(SUPABASE_SCHEMA).table("helps").select("*").eq("url", url).eq("languagecd", languagecd).execute().data or []
    if not rows and languagecd != "en":
        rows = sb.schema(SUPABASE_SCHEMA).table("helps").select("*").eq("url", url).eq("languagecd", "en").execute().data or []
    return {"help": rows[0] if rows else None}


@router.get("/helps")
def list_helps(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    rows = sb.schema(SUPABASE_SCHEMA).table("helps").select("*").order("url").order("languagecd").execute().data or []
    for row in rows:
        nm, _ = get_usernm_email(sb, row.get("creator"))
        row["createuser"] = nm
    return {"helps": rows}


@router.post("/helps")
def save_help(body: HelpSaveRequest, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    payload = {
        "helpuid": body.helpuid or str(uuid.uuid4()),
        "help": body.help,
        "url": body.url or "",
        "desc": body.desc or "",
        "languagecd": body.languagecd or "en",
        "creator": str(user.id),
    }
    before = snapshot_row(sb, "helps", "helpuid", body.helpuid) if body.helpuid else None
    sb.schema(SUPABASE_SCHEMA).table("helps").upsert(payload).execute()
    after = snapshot_row(sb, "helps", "helpuid", payload["helpuid"])
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="update",
        targettype="helps", targetid=payload["helpuid"], before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"ok": True, "helpuid": payload["helpuid"]}


@router.delete("/helps/{helpuid}")
def delete_help(helpuid: str, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    before = snapshot_row(sb, "helps", "helpuid", helpuid)
    sb.schema(SUPABASE_SCHEMA).table("helps").delete().eq("helpuid", helpuid).execute()
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="delete",
        targettype="helps", targetid=helpuid, before=before,
        ip=get_client_ip(request),
    )
    return {"ok": True}


# ══════════════════════════════════════════════════════
#  PROMPTS (샘플 프롬프트 마스터)
# ══════════════════════════════════════════════════════

class PromptSaveRequest(BaseModel):
    promptkey: str
    prompttypecd: str
    tag1: Optional[str] = None
    tag2: Optional[str] = None
    default_message: Optional[str] = None
    desc: Optional[str] = None
    datauid: Optional[str] = None
    useyn: bool = True
    orderno: Optional[int] = None
    is_new: bool = False


class PromptTranslationSaveRequest(BaseModel):
    languagecd: str
    translated_title: Optional[str] = None
    translated_text1: Optional[str] = None
    translated_text2: Optional[str] = None


@router.get("/prompts/sample-datas")
def list_prompt_sample_datas(token: str = Depends(get_token)):
    """샘플 문서에서 사용 중인 데이터 목록"""
    _require_admin(token)
    sb = _sb_service()
    doc_rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("docid").execute().data or []
    docids = [r["docid"] for r in doc_rows]
    if not docids:
        return {"datas": []}
    doc_data_rows = sb.schema(SUPABASE_SCHEMA).table("doc_datas").select("datauid").in_("docid", docids).execute().data or []
    datauids = list({r["datauid"] for r in doc_data_rows if r.get("datauid")})
    if not datauids:
        return {"datas": []}
    data_rows = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").in_("datauid", datauids).order("datanm").execute().data or []
    return {"datas": data_rows}


@router.get("/prompts")
def list_prompts(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("prompts").select("*")
        .order("orderno").order("promptkey")
        .execute().data or []
    )
    return {"prompts": rows}


@router.post("/prompts")
def save_prompt(body: PromptSaveRequest, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    try:
        payload = {
            "promptkey": body.promptkey,
            "prompttypecd": body.prompttypecd,
            "tag1": body.tag1 or None,
            "tag2": body.tag2 or None,
            "default_message": body.default_message or None,
            "desc": body.desc or None,
            "datauid": body.datauid or None,
            "useyn": body.useyn,
            "orderno": body.orderno,
        }
        before = None if body.is_new else snapshot_row(sb, "prompts", "promptkey", body.promptkey)
        if body.is_new:
            payload["creator"] = str(user.id)
            sb.schema(SUPABASE_SCHEMA).table("prompts").insert(payload).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("prompts").update(payload).eq("promptkey", body.promptkey).execute()
        after = snapshot_row(sb, "prompts", "promptkey", body.promptkey)
        log_admin_action(
            useruid=str(user.id), roleid=7, actioncd="update",
            targettype="prompts", targetid=body.promptkey, before=before, after=after,
            ip=get_client_ip(request),
        )
        return {"ok": True, "promptkey": body.promptkey}
    except Exception as e:
        # print(f"[save_prompt] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/prompts/{promptkey}")
def delete_prompt(promptkey: str, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    before = snapshot_row(sb, "prompts", "promptkey", promptkey)
    translations = sb.schema(SUPABASE_SCHEMA).table("prompt_translations").select("*").eq("promptkey", promptkey).execute().data or []
    sb.schema(SUPABASE_SCHEMA).table("prompt_translations").delete().eq("promptkey", promptkey).execute()
    sb.schema(SUPABASE_SCHEMA).table("prompts").delete().eq("promptkey", promptkey).execute()
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="delete",
        targettype="prompts", targetid=promptkey, before=before,
        detail={"cascaded_translations": translations} if translations else None,
        ip=get_client_ip(request),
    )
    return {"ok": True}


@router.get("/prompts/{promptkey}/translations")
def list_prompt_translations(promptkey: str, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("prompt_translations").select("*")
        .eq("promptkey", promptkey).execute().data or []
    )
    return {"translations": rows}


@router.post("/prompts/{promptkey}/translations")
def save_prompt_translation(promptkey: str, body: PromptTranslationSaveRequest, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    payload = {
        "promptkey": promptkey,
        "languagecd": body.languagecd,
        "translated_title": body.translated_title or None,
        "translated_text1": body.translated_text1 or None,
        "translated_text2": body.translated_text2 or None,
        "creator": str(user.id),
    }
    target_id = f"{promptkey}/{body.languagecd}"
    before = (
        sb.schema(SUPABASE_SCHEMA).table("prompt_translations").select("*")
        .eq("promptkey", promptkey).eq("languagecd", body.languagecd).maybe_single().execute()
    )
    before = before.data if before else None
    sb.schema(SUPABASE_SCHEMA).table("prompt_translations").upsert(
        payload, on_conflict="promptkey,languagecd"
    ).execute()
    after = (
        sb.schema(SUPABASE_SCHEMA).table("prompt_translations").select("*")
        .eq("promptkey", promptkey).eq("languagecd", body.languagecd).maybe_single().execute()
    )
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="update",
        targettype="prompt_translations", targetid=target_id, before=before, after=after.data if after else None,
        ip=get_client_ip(request),
    )
    return {"ok": True}


@router.delete("/prompts/{promptkey}/translations/{languagecd}")
def delete_prompt_translation(promptkey: str, languagecd: str, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    before = (
        sb.schema(SUPABASE_SCHEMA).table("prompt_translations").select("*")
        .eq("promptkey", promptkey).eq("languagecd", languagecd).maybe_single().execute()
    )
    before = before.data if before else None
    (
        sb.schema(SUPABASE_SCHEMA).table("prompt_translations").delete()
        .eq("promptkey", promptkey).eq("languagecd", languagecd).execute()
    )
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="delete",
        targettype="prompt_translations", targetid=f"{promptkey}/{languagecd}", before=before,
        ip=get_client_ip(request),
    )
    return {"ok": True}


# ══════════════════════════════════════════════════════
#  UI TERMS (UI 용어 조회/검색 — 읽기 전용)
# ══════════════════════════════════════════════════════

@router.get("/ui-terms")
def list_ui_terms(
    search: Optional[str] = Query(None),
    token: str = Depends(get_token),
):
    _require_admin(token)
    sb = _sb_service()

    terms: list = []
    offset = 0
    while True:
        batch = (
            sb.schema(SUPABASE_SCHEMA)
            .table("ui_terms")
            .select("*")
            .order("term_key")
            .range(offset, offset + 999)
            .execute()
            .data or []
        )
        terms.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    translations: list = []
    offset = 0
    while True:
        batch = (
            sb.schema(SUPABASE_SCHEMA)
            .table("ui_term_translations")
            .select("*")
            .range(offset, offset + 999)
            .execute()
            .data or []
        )
        translations.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    trans_map: dict = {}
    for tr in translations:
        key = tr["term_key"]
        if key not in trans_map:
            trans_map[key] = []
        trans_map[key].append({"language_cd": tr["language_cd"], "translated_text": tr["translated_text"]})

    result = [
        {**term, "translations": trans_map.get(term["term_key"], [])}
        for term in terms
    ]

    if search:
        s = search.lower()
        result = [
            item for item in result
            if (
                s in (item.get("term_key") or "").lower()
                or s in (item.get("term_group") or "").lower()
                or s in (item.get("default_text") or "").lower()
                or any(s in (tr.get("translated_text") or "").lower() for tr in item["translations"])
            )
        ]

    return {"items": result, "total": len(result)}


# ══════════════════════════════════════════════════════
#  PRODUCTS (상품/가격 관리)
# ══════════════════════════════════════════════════════

PRODUCT_TAX_RATE = 0.1  # unit_tax = price의 10%, unit_price = price의 90%


def _attach_current_prices(sb, rows: list, currencycd: str = "KRW") -> None:
    """products 행에 config_price 기준 오늘 날짜에 유효한 price/unit_price/unit_tax를 채운다 (in-place)."""
    productcds = [r["productcd"] for r in rows if r.get("productcd")]
    if not productcds:
        return
    today = date.today().isoformat()
    price_rows = (
        sb.schema(SUPABASE_SCHEMA).table("config_price")
        .select("productcd,billingtermcd,price,unit_price,unit_tax,currencycd,effectivefromdt,effectivetodt")
        .in_("productcd", productcds)
        .eq("currencycd", currencycd)
        .lte("effectivefromdt", today)
        .execute().data or []
    )
    price_map: dict = {}
    for p in price_rows:
        if p.get("effectivetodt") and p["effectivetodt"] < today:
            continue
        key = (p["productcd"], p["billingtermcd"])
        existing = price_map.get(key)
        if not existing or p["effectivefromdt"] > existing["effectivefromdt"]:
            price_map[key] = p

    for r in rows:
        price_row = price_map.get((r.get("productcd"), r.get("billingtermcd")))
        r["price"] = price_row["price"] if price_row else None
        r["unit_price"] = price_row["unit_price"] if price_row else None
        r["unit_tax"] = price_row["unit_tax"] if price_row else None
        r["currencycd"] = price_row["currencycd"] if price_row else None
        r["effectivefromdt"] = price_row["effectivefromdt"] if price_row else None


@router.get("/products")
def list_admin_products(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("products").select("*")
        .order("servicecd").order("orderno")
        .execute().data or []
    )
    _attach_current_prices(sb, rows)
    return {"products": rows}


class ProductSaveRequest(BaseModel):
    productcd: str
    productnm: Optional[str] = None
    servicecd: Optional[str] = None
    plancd: Optional[str] = None
    producttype: Optional[str] = None
    billingtermcd: Optional[str] = None
    users: Optional[int] = None
    credit: Optional[int] = None
    useyn: bool = True
    is_sales: bool = True
    is_customeraikey: bool = False
    orderno: Optional[int] = None
    expiremonths: Optional[int] = None


@router.post("/products")
def create_admin_product(body: ProductSaveRequest, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    existing = sb.schema(SUPABASE_SCHEMA).table("products").select("productcd").eq("productcd", body.productcd).execute().data
    if existing:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 상품코드입니다: {body.productcd}")

    record = body.model_dump()
    record["creator"] = str(user.id)
    sb.schema(SUPABASE_SCHEMA).table("products").insert(record).execute()
    after = snapshot_row(sb, "products", "productcd", body.productcd)
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="update",
        targettype="products", targetid=body.productcd, after=after,
        ip=get_client_ip(request),
    )
    return {"result": "success", "productcd": body.productcd}


@router.put("/products/{productcd}")
def update_admin_product(productcd: str, body: ProductSaveRequest, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    existing = sb.schema(SUPABASE_SCHEMA).table("products").select("productcd").eq("productcd", productcd).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    before = snapshot_row(sb, "products", "productcd", productcd)
    record = body.model_dump()
    record.pop("productcd", None)
    sb.schema(SUPABASE_SCHEMA).table("products").update(record).eq("productcd", productcd).execute()
    after = snapshot_row(sb, "products", "productcd", productcd)
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="update",
        targettype="products", targetid=productcd, before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"result": "success", "productcd": productcd}


@router.delete("/products/{productcd}")
def delete_admin_product(productcd: str, request: Request, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    existing = sb.schema(SUPABASE_SCHEMA).table("products").select("productcd").eq("productcd", productcd).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    before = snapshot_row(sb, "products", "productcd", productcd)
    price_rows = sb.schema(SUPABASE_SCHEMA).table("config_price").select("*").eq("productcd", productcd).execute().data or []
    sb.schema(SUPABASE_SCHEMA).table("config_price").delete().eq("productcd", productcd).execute()
    sb.schema(SUPABASE_SCHEMA).table("products").delete().eq("productcd", productcd).execute()
    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="delete",
        targettype="products", targetid=productcd, before=before,
        detail={"cascaded_config_price": price_rows} if price_rows else None,
        ip=get_client_ip(request),
    )
    return {"result": "success", "message": "상품이 삭제되었습니다."}


class ProductPriceSaveRequest(BaseModel):
    price: float
    currencycd: str = "KRW"
    effectivefromdt: Optional[str] = None  # "YYYY-MM-DD", 생략 시 오늘


@router.post("/products/{productcd}/price")
def save_admin_product_price(productcd: str, body: ProductPriceSaveRequest, request: Request, token: str = Depends(get_token)):
    """
    productcd의 지정일(기본 오늘)자 가격을 등록/수정한다. unit_price(90%)/unit_tax(10%)는 자동 계산한다.
    같은 날짜의 기존 행이 있으면 그 행을 덮어쓰고, 없으면 새 이력을 추가하면서 그 직전까지
    열려있던(effectivetodt IS NULL) 행의 종료일을 하루 전으로 닫아 기간이 겹치지 않게 한다.
    """
    from datetime import timedelta

    user = _require_admin(token)
    sb = _sb_service()

    prod_row = sb.schema(SUPABASE_SCHEMA).table("products").select("billingtermcd").eq("productcd", productcd).maybe_single().execute()
    if not prod_row or not prod_row.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    billingtermcd = prod_row.data.get("billingtermcd")
    if not billingtermcd:
        raise HTTPException(status_code=400, detail="상품에 결제주기(billingtermcd)가 설정되어 있지 않습니다.")

    effectivefromdt = body.effectivefromdt or date.today().isoformat()
    unit_tax = round(body.price * PRODUCT_TAX_RATE)
    unit_price = round(body.price - unit_tax)

    record = {
        "productcd": productcd,
        "currencycd": body.currencycd,
        "billingtermcd": billingtermcd,
        "effectivefromdt": effectivefromdt,
        "price": body.price,
        "unit_price": unit_price,
        "unit_tax": unit_tax,
        "creator": str(user.id),
    }

    before = (
        sb.schema(SUPABASE_SCHEMA).table("config_price").select("*")
        .eq("productcd", productcd).eq("currencycd", body.currencycd)
        .eq("billingtermcd", billingtermcd).eq("effectivefromdt", effectivefromdt)
        .execute().data
    )
    before = before[0] if before else None
    existing = before
    if existing:
        record.pop("creator", None)
        sb.schema(SUPABASE_SCHEMA).table("config_price").update(record).eq("productcd", productcd).eq(
            "currencycd", body.currencycd
        ).eq("billingtermcd", billingtermcd).eq("effectivefromdt", effectivefromdt).execute()
    else:
        # 직전까지 열려있던 이전 이력을 새 시작일 하루 전으로 닫는다
        open_rows = (
            sb.schema(SUPABASE_SCHEMA).table("config_price").select("effectivefromdt")
            .eq("productcd", productcd).eq("currencycd", body.currencycd).eq("billingtermcd", billingtermcd)
            .is_("effectivetodt", "null").lt("effectivefromdt", effectivefromdt)
            .execute().data or []
        )
        if open_rows:
            close_dt = (date.fromisoformat(effectivefromdt) - timedelta(days=1)).isoformat()
            for r in open_rows:
                sb.schema(SUPABASE_SCHEMA).table("config_price").update({"effectivetodt": close_dt}).eq(
                    "productcd", productcd
                ).eq("currencycd", body.currencycd).eq("billingtermcd", billingtermcd).eq(
                    "effectivefromdt", r["effectivefromdt"]
                ).execute()
        sb.schema(SUPABASE_SCHEMA).table("config_price").insert(record).execute()

    log_admin_action(
        useruid=str(user.id), roleid=7, actioncd="config_change",
        targettype="config_price", targetid=f"{productcd}/{body.currencycd}/{billingtermcd}/{effectivefromdt}",
        before=before, after=record,
        ip=get_client_ip(request),
    )
    return {"result": "success", "unit_price": unit_price, "unit_tax": unit_tax}


@router.get("/products/{productcd}/price-history")
def list_admin_product_price_history(productcd: str, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("config_price").select("*")
        .eq("productcd", productcd)
        .order("billingtermcd").order("effectivefromdt", desc=True)
        .execute().data or []
    )
    return {"history": rows}
