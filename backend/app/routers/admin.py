"""Admin router — roleid=7 전용 (사용자 관리, 샘플 프롬프트, LLM 관리 등)"""
import sys
import uuid
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.app.dependencies import get_token

router = APIRouter()

ROLE_MAP = {1: "일반유저", 5: "Power User", 7: "관리자"}
ROLE_OPTIONS = [
    {"value": 1, "label": "일반유저"},
    {"value": 5, "label": "Power User"},
    {"value": 7, "label": "관리자"},
]


def _sb_user(token: str):
    """일반 사용자 Supabase 클라이언트"""
    from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA
    return get_thread_supabase(access_token=token)


def _sb_service():
    """서비스 클라이언트 (RLS 우회, 관리자 전용)"""
    from utilsPrj.supabase_client import get_service_client
    return get_service_client()


def _get_user(token: str):
    try:
        sb = _sb_user(token)
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
        print(f"[admin._get_user] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
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
        print(f"[admin._require_admin] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"관리자 확인 오류: {str(e)}")


# ══════════════════════════════════════════════════════
#  USER ROLE (사용자 권한 관리)
# ══════════════════════════════════════════════════════

@router.get("/user-role")
def list_user_roles(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    rows = sb.schema(SUPABASE_SCHEMA).table("users").select("useruid,roleid,email").order("email").execute().data or []
    for u in rows:
        u["role_name"] = ROLE_MAP.get(u.get("roleid", 1), "일반유저")

    return {"users": rows, "role_options": ROLE_OPTIONS}


class UserRoleSaveRequest(BaseModel):
    useruid: str
    roleid: int


@router.post("/user-role")
def save_user_role(body: UserRoleSaveRequest, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    if body.roleid not in ROLE_MAP:
        raise HTTPException(status_code=400, detail="유효하지 않은 역할입니다.")

    sb.schema(SUPABASE_SCHEMA).table("users").update({"roleid": body.roleid}).eq("useruid", body.useruid).execute()
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
        print(f"[admin.list_sample_prompts] 오류: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
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
def save_sample_prompt(body: SamplePromptSaveRequest, token: str = Depends(get_token)):
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
        sb.schema(SUPABASE_SCHEMA).table("prompts").update({
            "promptnm": body.promptnm.strip(),
            "prompt": body.prompt,
            "desc": body.promptdesc,
            "displaytype": body.displaytype,
        }).eq("promptuid", body.promptuid).execute()
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
    return {"success": True, "message": "저장되었습니다."}


@router.delete("/sample-prompts/{promptuid}")
def delete_sample_prompt(promptuid: str, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    if not promptuid:
        raise HTTPException(status_code=400, detail="삭제할 프롬프트를 선택해주세요.")

    sb.schema(SUPABASE_SCHEMA).table("prompts").delete().eq("promptuid", promptuid).execute()
    return {"success": True, "message": "삭제되었습니다."}


# ── 샘플 프롬프트 미리보기 ────────────────────────────────────────────────────

class SamplePromptPreviewRequest(BaseModel):
    prompt: str
    objecttypecd: str          # CA / SA / TA
    datauid: Optional[str] = None
    displaytype: Optional[str] = None


@router.post("/sample-prompts/preview")
def sample_prompt_preview(body: SamplePromptPreviewRequest, token: str = Depends(get_token)):
    """샘플 프롬프트 미리보기 — chapteruid/objectnm 없이 datauid+prompt 만으로 실행"""
    _require_admin(token)

    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="프롬프트를 입력해주세요.")
    if not body.datauid:
        raise HTTPException(status_code=400, detail="데이터를 선택해주세요.")

    from utilsPrj.supabase_client import get_thread_supabase, get_service_client
    from utilsPrj.process_data import process_data
    from llm.ai_chain import (
        get_charts_prompt, get_sentences_prompt, get_tables_prompt,
        get_full_chain, get_llm_model,
    )
    from backend.app.routers.llm import FakeLlmRequest, _get_user_info

    sb_user = get_thread_supabase(access_token=token)
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
        result_df = process_data(req, body.datauid, None)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[sample-prompt/preview] process_data 오류:\n{tb}", file=sys.stderr, flush=True)
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
        llm = get_llm_model(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 모델 로드 오류: {str(e)}")

    full_chain = get_full_chain(llm, result_df, prompt, body.prompt, column_dict, ot)
    try:
        response = full_chain.invoke({"question": body.prompt, "column_dict": column_dict})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 실행 오류: {str(e)}")

    if not isinstance(response, dict):
        raise HTTPException(status_code=500, detail="LLM 응답 형식 오류")

    status_val = response.get("status")
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
        return {"message_type": "error", "message": "알 수 없는 응답 형식입니다."}


# ══════════════════════════════════════════════════════
#  LLMs (LLM 모델 관리)
# ══════════════════════════════════════════════════════

def _fmt_dt(raw) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        return dt.strftime("%y-%m-%d %H:%M")
    except Exception:
        return str(raw)


@router.get("/llms")
def list_llms(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    rows = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("*").order("llmmodelnm").execute().data or []
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        # API Key 는 보안상 제거 (유무만 표시)
        row["has_apikey"] = bool(row.get("encapikey"))
        row.pop("encapikey", None)
        if row.get("creator"):
            try:
                u = sb.schema("public").table("users").select("full_name").eq("useruid", row["creator"]).execute().data
                row["createuser"] = u[0]["full_name"] if u else ""
            except Exception:
                row["createuser"] = ""
        else:
            row["createuser"] = ""

    return {"llmmodels": rows}


class LlmSaveRequest(BaseModel):
    llmmodelnm: str
    llmvendornm: Optional[str] = None
    llmmodelnicknm: Optional[str] = None
    useyn: bool = True
    isdefault: bool = False
    apikey: Optional[str] = None   # 빈 문자열이면 기존 키 유지


@router.post("/llms")
def save_llm(body: LlmSaveRequest, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    from utilsPrj.crypto_helper import encrypt_value, decrypt_value

    apikey = (body.apikey or "").strip()

    # API Key 비어 있으면 기존 키 유지
    if not apikey:
        existing = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("encapikey").eq("llmmodelnm", body.llmmodelnm).execute().data
        if existing and existing[0].get("encapikey"):
            apikey = decrypt_value(existing[0]["encapikey"])

    encapikey = encrypt_value(apikey) if apikey else None

    data = {
        "llmmodelnm": body.llmmodelnm,
        "llmvendornm": body.llmvendornm,
        "llmmodelnicknm": body.llmmodelnicknm,
        "useyn": body.useyn,
        "isdefault": body.isdefault,
        "encapikey": encapikey,
        "creator": user.id,
    }

    sb.schema(SUPABASE_SCHEMA).table("llmmodels").upsert(data).execute()
    return {"result": "success", "message": "성공적으로 저장되었습니다."}


@router.delete("/llms/{llmmodelnm}")
def delete_llm(llmmodelnm: str, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    if not llmmodelnm:
        raise HTTPException(status_code=400, detail="LLM 모델명은 필수입니다.")

    sb.schema(SUPABASE_SCHEMA).table("llmmodels").delete().eq("llmmodelnm", llmmodelnm).execute()
    return {"result": "success", "message": "삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  LLM APIs (LLM API 관리)
# ══════════════════════════════════════════════════════

USE_TYPE_MAP = {"R": "Round", "D": "Direct", "N": "No"}


@router.get("/llmapis")
def list_llmapis(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    # 사용 중인 LLM 모델 목록 (드롭다운용)
    llmmodels = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("llmmodelnm,llmvendornm").eq("useyn", True).order("llmvendornm").order("llmmodelnm").execute().data or []
    llmmodel_ids = [m["llmmodelnm"] for m in llmmodels]

    # LLM API 목록
    llmapis = []
    if llmmodel_ids:
        llmapis = sb.schema(SUPABASE_SCHEMA).table("llmapis").select("*").in_("llmmodelnm", llmmodel_ids).order("llmmodelnm").order("usetypecd").execute().data or []
    for row in llmapis:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        row["usetypenm"] = USE_TYPE_MAP.get(row.get("usetypecd", ""), "")
        row["has_apikey"] = bool(row.get("encapikey"))
        row.pop("encapikey", None)
        if row.get("creator"):
            try:
                u = sb.schema("public").table("users").select("full_name").eq("useruid", row["creator"]).execute().data
                row["createuser"] = u[0]["full_name"] if u else ""
            except Exception:
                row["createuser"] = ""
        else:
            row["createuser"] = ""

    # 기업 목록 (비고 드롭다운용, SmartDoc 제외)
    tenants = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantnm").eq("useyn", True).or_("issytemtenant.is.null,issytemtenant.eq.false").order("tenantid").execute().data or []

    return {"llmapis": llmapis, "llmmodels": llmmodels, "tenants": tenants}


class LlmApiSaveRequest(BaseModel):
    llmapiuid: Optional[str] = None
    llmmodelnm: str
    apikey: Optional[str] = None
    usetypecd: str
    desc: Optional[str] = None


@router.post("/llmapis")
def save_llmapi(body: LlmApiSaveRequest, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()

    from utilsPrj.crypto_helper import encrypt_value, decrypt_value

    apikey = (body.apikey or "").strip()

    # 기존 레코드 수정 시 API Key 비어 있으면 유지
    if body.llmapiuid and not apikey:
        existing = sb.schema(SUPABASE_SCHEMA).table("llmapis").select("encapikey").eq("llmapiuid", body.llmapiuid).execute().data
        if existing and existing[0].get("encapikey"):
            apikey = decrypt_value(existing[0]["encapikey"])

    encapikey = encrypt_value(apikey) if apikey else None

    upsert_data = {
        "llmmodelnm": body.llmmodelnm,
        "encapikey": encapikey,
        "usetypecd": body.usetypecd,
        "desc": body.desc if body.usetypecd == "D" else None,
        "creator": user.id,
    }
    if body.llmapiuid:
        upsert_data["llmapiuid"] = body.llmapiuid

    sb.schema(SUPABASE_SCHEMA).table("llmapis").upsert(upsert_data).execute()
    return {"result": "success", "message": "성공적으로 저장되었습니다."}


@router.delete("/llmapis/{llmapiuid}")
def delete_llmapi(llmapiuid: str, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    if not llmapiuid:
        raise HTTPException(status_code=400, detail="LLM API 선택은 필수입니다.")

    sb.schema(SUPABASE_SCHEMA).table("llmapis").delete().eq("llmapiuid", llmapiuid).execute()
    return {"result": "success", "message": "삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  TENANT REQUESTS (기업 생성 요청 관리, 조회 전용)
# ══════════════════════════════════════════════════════

@router.get("/tenant-requests")
def list_tenant_requests(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()

    from utilsPrj.crypto_helper import decrypt_value

    rows = sb.schema(SUPABASE_SCHEMA).table("tenantreqs").select("*").order("createdts", desc=True).execute().data or []
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        if row.get("encemail"):
            try:
                row["email"] = decrypt_value(row["encemail"])
            except Exception:
                row["email"] = ""
        else:
            row["email"] = ""
        if row.get("enctelno"):
            try:
                row["telno"] = decrypt_value(row["enctelno"])
            except Exception:
                row["telno"] = ""
        else:
            row["telno"] = ""
        # 보안상 암호화 필드 제거
        row.pop("encemail", None)
        row.pop("enctelno", None)

    return {"tenantreqs": rows}


# ══════════════════════════════════════════════════════
#  HELPS (도움말 관리)
# ══════════════════════════════════════════════════════

class HelpSaveRequest(BaseModel):
    helpuid: Optional[str] = None
    help: str
    url: Optional[str] = None
    desc: Optional[str] = None


class HelpDeleteRequest(BaseModel):
    helpuid: str


@router.get("/helps")
def list_helps(token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    rows = sb.schema(SUPABASE_SCHEMA).table("helps").select("*").order("createdts", desc=True).execute().data or []
    # creator uuid → full_name
    for row in rows:
        if row.get("creator"):
            try:
                user_rows = sb.schema("public").table("users").select("full_name").eq("useruid", row["creator"]).execute().data
                row["createuser"] = user_rows[0]["full_name"] if user_rows else ""
            except Exception:
                row["createuser"] = ""
        else:
            row["createuser"] = ""
    return {"helps": rows}


@router.post("/helps")
def save_help(body: HelpSaveRequest, token: str = Depends(get_token)):
    user = _require_admin(token)
    sb = _sb_service()
    payload = {
        "helpuid": body.helpuid or str(uuid.uuid4()),
        "help": body.help,
        "url": body.url or "",
        "desc": body.desc or "",
        "creator": str(user.id),
    }
    sb.schema(SUPABASE_SCHEMA).table("helps").upsert(payload).execute()
    return {"ok": True, "helpuid": payload["helpuid"]}


@router.delete("/helps/{helpuid}")
def delete_help(helpuid: str, token: str = Depends(get_token)):
    _require_admin(token)
    sb = _sb_service()
    sb.schema(SUPABASE_SCHEMA).table("helps").delete().eq("helpuid", helpuid).execute()
    return {"ok": True}


@router.get("/helps/search")
def search_help(url: str = Query(...)):
    """URL로 도움말 검색 (인증 불필요)"""
    sb = _sb_service()
    rows = sb.schema(SUPABASE_SCHEMA).table("helps").select("*").eq("url", url).execute().data or []
    return {"helps": rows}
