"""Org router — Tenant Users, Tenant LLMs, Projects, Project Users, Invite Members"""
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()



def _get_offsetminutes(sb, user_id: str) -> Optional[int]:
    try:
        tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id).maybe_single().execute()
        if not tu.data:
            return None
        tz = tu.data.get("timezone")
        if not tz and tu.data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu.data["tenantid"]).maybe_single().execute()
            if t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row.data else None
    except Exception:
        return None


def _fmt_dt(raw, offsetminutes: Optional[int] = None) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


def _get_usernm_email(sb, useruid: str):
    """public.users에서 이름/이메일 조회"""
    try:
        rows = sb.schema("public").table("users").select("full_name,email").eq("useruid", useruid).execute().data
        if rows:
            return rows[0].get("full_name", ""), rows[0].get("email", "")
    except Exception:
        pass
    return "", ""


# ══════════════════════════════════════════════════════
#  TENANT USERS
# ══════════════════════════════════════════════════════

@router.get("/tenant-users")
def list_tenant_users(
    tenantid: Optional[str] = Query(None),
    accountuid: Optional[str] = Query(None),
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id))

    # tenantid 결정: Query 파라미터 > X-Tenant-ID 헤더
    if not tenantid:
        tenantid = header_tenantid
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    # 기업명 조회
    t_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantnm").eq("tenantid", tenantid).execute().data
    tenantnm = t_rows[0]["tenantnm"] if t_rows else ""

    # 계정이 구독 중인 서비스 목록 (서비스 조건 radio 옵션)
    available_servicecds = []
    if accountuid:
        svc_rows = sb.schema(SUPABASE_SCHEMA).table("accountservices").select("servicecd").eq("accountuid", accountuid).execute().data or []
        available_servicecds = [r["servicecd"] for r in svc_rows if r.get("servicecd")]

    # 사용자별 가입 서비스 매핑 (서비스 조건 필터링용)
    su_rows = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("useruid,servicecd").eq("tenantid", tenantid).execute().data or []
    svc_map = {}
    for r in su_rows:
        svc_map.setdefault(r["useruid"], []).append(r["servicecd"])

    # tenantusers 조회
    tu_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("*").eq("tenantid", tenantid).order("useruid", desc=True).execute().data or []
    for row in tu_rows:
        nm, email = _get_usernm_email(sb, row.get("useruid", ""))
        row["usernm"] = nm
        row["email"] = email
        if row.get("creator"):
            cnm, _ = _get_usernm_email(sb, row["creator"])
            row["creatornm"] = cnm
        else:
            row["creatornm"] = ""
        row["createdts"] = _fmt_dt(row.get("createdts"), offsetminutes)
        row["servicecds"] = svc_map.get(row.get("useruid"), [])

    all_users = tu_rows
    # 이메일 기준 정렬
    all_users.sort(key=lambda x: (x.get("email") or "").lower())

    return {
        "tenantid": tenantid,
        "tenantnm": tenantnm,
        "users": all_users,
        "available_servicecds": available_servicecds,
    }


class TenantUserSaveRequest(BaseModel):
    tenantid: str
    useruid: Optional[str] = None
    email: str
    rolecd: str = "U"
    useyn: bool = True
    servicecds: list[str] = []
    accountuid: Optional[str] = None


@router.post("/tenant-users")
def save_tenant_user(body: TenantUserSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id
    tenantid = int(body.tenantid)

    if not body.accountuid or not body.servicecds:
        raise HTTPException(status_code=400, detail="서비스를 선택해야 합니다.")

    # 이메일로 사용자 조회
    pub_users = sb.schema("public").table("users").select("*").eq("email", body.email).execute().data
    if not pub_users:
        raise HTTPException(status_code=400, detail="존재하지 않는 이메일입니다.")

    target_user = pub_users[0]
    useruid = target_user["useruid"]

    # SmartDoc 테넌트 id 조회
    sd_tenant = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid").eq("issystemtenant", True).execute().data
    other_tenantid = int(sd_tenant[0]["tenantid"]) if sd_tenant else None

    # 선택된 서비스 집합을 사용자의 가입 상태로 동기화 (신규 가입 / 유지 / 탈퇴 구분)
    current_su_rows = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("servicecd").eq("accountuid", body.accountuid).eq("useruid", useruid).execute().data or []
    current_servicecds = {r["servicecd"] for r in current_su_rows}
    desired_servicecds = set(body.servicecds)
    to_add = desired_servicecds - current_servicecds
    to_remove = current_servicecds - desired_servicecds

    # 신규로 추가되는 서비스만 인원 제한 검사
    for scd in to_add:
        acc_svc = sb.schema(SUPABASE_SCHEMA).table("accountservices").select("total_users").eq("accountuid", body.accountuid).eq("servicecd", scd).maybe_single().execute()
        total_users = acc_svc.data.get("total_users") if acc_svc.data else None
        if total_users is not None:
            cnt = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("useruid", count="exact").eq("accountuid", body.accountuid).eq("servicecd", scd).execute()
            if (cnt.count or 0) >= total_users:
                raise HTTPException(status_code=400, detail=f"{scd} 서비스는 최대 {total_users}명까지 가입할 수 있습니다.")

    # 기존 tenantusers 레코드 확인
    existing_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("*").eq("tenantid", tenantid).eq("useruid", useruid).execute().data
    existing = existing_rows[0] if existing_rows else None

    save_data = {
        "tenantid": tenantid,
        "useruid": useruid,
        "useyn": body.useyn,
        "rolecd": body.rolecd,
    }

    if existing:
        sb.schema(SUPABASE_SCHEMA).table("tenantusers").update(save_data).eq("tenantid", tenantid).eq("useruid", useruid).execute()
    else:
        save_data["creator"] = user_id
        sb.schema(SUPABASE_SCHEMA).table("tenantusers").insert(save_data).execute()

    # serviceusers 동기화: 신규 가입 insert / 유지 서비스 useyn update / 탈퇴 서비스 delete
    for scd in to_add:
        sb.schema(SUPABASE_SCHEMA).table("serviceusers").insert({
            "accountuid": body.accountuid,
            "servicecd": scd,
            "useruid": useruid,
            "tenantid": tenantid,
            "useyn": body.useyn,
            "creator": user_id,
        }).execute()
    for scd in (desired_servicecds & current_servicecds):
        sb.schema(SUPABASE_SCHEMA).table("serviceusers").update({"useyn": body.useyn}).eq("accountuid", body.accountuid).eq("servicecd", scd).eq("useruid", useruid).execute()
    for scd in to_remove:
        sb.schema(SUPABASE_SCHEMA).table("serviceusers").delete().eq("accountuid", body.accountuid).eq("servicecd", scd).eq("useruid", useruid).execute()

    return {"result": "success", "message": "사용자가 성공적으로 저장되었습니다."}


class TenantUserDeleteRequest(BaseModel):
    tenantid: str
    useruid: str
    accountuid: Optional[str] = None


@router.delete("/tenant-users")
def delete_tenant_user(body: TenantUserDeleteRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    tenantid = body.tenantid
    useruid = body.useruid

    # tenantusers에서 삭제
    sb.schema(SUPABASE_SCHEMA).table("tenantusers").delete().eq("tenantid", tenantid).eq("useruid", useruid).execute()

    # 해당 tenant의 projectusers에서도 삭제
    projects = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("tenantid", tenantid).execute().data or []
    for p in projects:
        pid = p.get("projectid")
        if pid:
            sb.schema(SUPABASE_SCHEMA).table("projectusers").delete().eq("projectid", pid).eq("useruid", useruid).execute()

    # 해당 계정의 서비스 가입 정보 전체 삭제 (모든 servicecd)
    if body.accountuid:
        sb.schema(SUPABASE_SCHEMA).table("serviceusers").delete().eq("accountuid", body.accountuid).eq("useruid", useruid).execute()

    return {"result": "success", "message": "사용자 및 관련 프로젝트 사용자 정보가 모두 삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  TENANT LLMs
# ══════════════════════════════════════════════════════

def _get_llmmodel_info(sb, llmmodelnm: str) -> dict:
    """llmmodels 테이블에서 활성 여부 조회"""
    if not llmmodelnm:
        return {"llmmodelfullnm": "", "llmmodelactiveyn": False}
    try:
        rows = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("useyn").eq("llmmodelnm", llmmodelnm).execute().data
        if rows:
            return {"llmmodelfullnm": llmmodelnm, "llmmodelactiveyn": rows[0].get("useyn", False)}
    except Exception:
        pass
    return {"llmmodelfullnm": llmmodelnm, "llmmodelactiveyn": False}


@router.get("/tenant-llms")
def list_tenant_llms(
    token: str = Depends(get_token),
    accountuid: Optional[str] = None,
):
    import traceback as _tb
    try:
     return _list_tenant_llms_impl(token, accountuid)
    except Exception:
     print("[tenant-llms 500]\n" + _tb.format_exc())
     raise

def _list_tenant_llms_impl(token: str, accountuid: Optional[str]):
    sb = _sb(token)
    if not accountuid:
        return {"projects": [], "llmmodels": [], "account_projects": []}

    # 프로젝트 목록 (accountuid 기준)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("projects")
        .select("projectid,projectnm,projectdesc,servicecd,llmmodelnm,encapikey")
        .eq("accountuid", accountuid)
        .order("projectnm")
        .execute()
        .data or []
    )
    projects = []
    for p in rows:
        if p.get("llmmodelnm"):
            info = _get_llmmodel_info(sb, p["llmmodelnm"])
            p["llmmodelfullnm"] = info["llmmodelfullnm"]
            p["llmmodelactiveyn"] = info["llmmodelactiveyn"]
        else:
            p["llmmodelfullnm"] = ""
            p["llmmodelactiveyn"] = False
        p.pop("encapikey", None)
        projects.append(p)

    # LLM 모델 목록 (드롭다운용)
    llmmodels = (
        sb.schema(SUPABASE_SCHEMA)
        .table("llmmodels")
        .select("llmmodelnm,useyn")
        .eq("useyn", True)
        .order("llmmodelnm")
        .execute()
        .data or []
    )

    # 우측 셀렉트박스용 — 동일 데이터에서 파생
    account_projects = [
        {
            "projectid": p["projectid"],
            "projectnm": p["projectnm"],
            "projectdesc": p.get("projectdesc") or "",
            "servicecd": p.get("servicecd") or "",
        }
        for p in projects
    ]

    return {
        "projects": projects,
        "llmmodels": llmmodels,
        "account_projects": account_projects,
    }


class TenantLlmSaveRequest(BaseModel):
    projectid: Optional[str] = None
    llmmodelnm: Optional[str] = None
    apikey: Optional[str] = None  # 빈 문자열이면 기존 키 유지


@router.post("/tenant-llms")
def save_tenant_llm(body: TenantLlmSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    if not body.projectid:
        raise HTTPException(status_code=400, detail="projectid가 필요합니다.")

    from utilsPrj.crypto_helper import encrypt_value, decrypt_value

    apikey = (body.apikey or "").strip()

    # API Key 가 비어 있으면 기존 키 유지
    if not apikey:
        row = sb.schema(SUPABASE_SCHEMA).table("projects").select("encapikey").eq("projectid", body.projectid).execute().data
        if row and row[0].get("encapikey"):
            apikey = decrypt_value(row[0]["encapikey"])

    encapikey = encrypt_value(apikey) if apikey else None
    llmmodelnm = body.llmmodelnm or None

    # API Key가 없으면 llmmodelnm도 초기화
    if not apikey:
        llmmodelnm = None
        encapikey = None

    data = {"projectid": body.projectid, "llmmodelnm": llmmodelnm, "encapikey": encapikey}
    sb.schema(SUPABASE_SCHEMA).table("projects").upsert(data).execute()

    return {"result": "success", "message": "성공적으로 저장되었습니다."}


class TenantLlmDeleteRequest(BaseModel):
    projectid: Optional[str] = None


@router.delete("/tenant-llms")
def delete_tenant_llm(body: TenantLlmDeleteRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    if not body.projectid:
        raise HTTPException(status_code=400, detail="projectid가 필요합니다.")

    data = {"projectid": body.projectid, "llmmodelnm": None, "encapikey": None}
    sb.schema(SUPABASE_SCHEMA).table("projects").upsert(data).execute()

    return {"result": "success", "message": "LLM 정보가 삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  PROJECTS
# ══════════════════════════════════════════════════════

@router.get("/projects")
def list_org_projects(
    tenantid: Optional[str] = Query(None),
    accountuid: Optional[str] = Query(None),
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id))

    if not tenantid:
        tenantid = header_tenantid
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    t_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantnm").eq("tenantid", tenantid).execute().data
    tenantnm = t_rows[0]["tenantnm"] if t_rows else ""

    rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("tenantid", tenantid).order("createdts", desc=True).execute().data or []
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"), offsetminutes)
        if row.get("creator"):
            nm, _ = _get_usernm_email(sb, row["creator"])
            row["creatornm"] = nm
        else:
            row["creatornm"] = ""

    available_servicecds = []
    if accountuid:
        svc_rows = sb.schema(SUPABASE_SCHEMA).table("accountservices").select("servicecd").eq("accountuid", accountuid).execute().data or []
        available_servicecds = [r["servicecd"] for r in svc_rows if r.get("servicecd")]

    return {"projects": rows, "tenantnm": tenantnm, "tenantid": tenantid, "available_servicecds": available_servicecds}


class OrgProjectSaveRequest(BaseModel):
    projectid: Optional[str] = None
    tenantid: Optional[str] = None
    projectnm: str
    projectdesc: Optional[str] = None
    useyn: bool = True
    servicecd: Optional[str] = None
    accountuid: Optional[str] = None


@router.post("/projects")
def save_org_project(body: OrgProjectSaveRequest, token: str = Depends(get_token), header_tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    tenantid = body.tenantid or header_tenantid
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    if not body.projectnm:
        raise HTTPException(status_code=400, detail="프로젝트명은 필수입니다.")

    # 신규 생성 시 플랜 제한 체크
    is_new = not body.projectid
    if is_new and body.accountuid and body.servicecd:
        svc = sb.schema(SUPABASE_SCHEMA).table("accountservices") \
            .select("plancd").eq("accountuid", body.accountuid).eq("servicecd", body.servicecd) \
            .maybe_single().execute()
        plancd = svc.data.get("plancd") if svc.data else None
        if plancd:
            cfg = sb.schema(SUPABASE_SCHEMA).table("config_plans") \
                .select("value").eq("configcd", "project_limit").eq("plancd", plancd).eq("servicecd", body.servicecd) \
                .maybe_single().execute()
            limit = int(cfg.data["value"]) if cfg.data and cfg.data.get("value") else None
            if limit is not None:
                cnt = sb.schema(SUPABASE_SCHEMA).table("projects") \
                    .select("projectid", count="exact") \
                    .eq("accountuid", body.accountuid).eq("servicecd", body.servicecd) \
                    .execute()
                if (cnt.count or 0) >= limit:
                    raise HTTPException(status_code=400, detail=f"프로젝트는 최대 {limit}개까지 생성할 수 있습니다.")

    data = {
        "projectnm": body.projectnm,
        "projectdesc": body.projectdesc,
        "useyn": body.useyn,
        "tenantid": tenantid,
        "creator": user.id,
        "servicecd": body.servicecd,
        "accountuid": body.accountuid,
    }

    if body.projectid:
        existing = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("projectid", body.projectid).execute().data
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("projects").update(data).eq("projectid", body.projectid).execute()
            return {"result": "success", "message": "프로젝트가 성공적으로 저장되었습니다."}

    sb.schema(SUPABASE_SCHEMA).table("projects").insert(data).execute()
    return {"result": "success", "message": "프로젝트가 성공적으로 저장되었습니다."}


@router.delete("/projects/{projectid}")
def delete_org_project(projectid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("projects").delete().eq("projectid", projectid).execute()
    return {"result": "success", "message": "프로젝트가 성공적으로 삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  PROJECT USERS
# ══════════════════════════════════════════════════════

@router.get("/project-users")
def list_project_users(
    projects: Optional[str] = Query(None),   # projectid
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id
    offsetminutes = _get_offsetminutes(sb, str(user_id))

    # ── 프로젝트 목록 (드롭다운용) ──────────────────────────────
    # tenantmanager=Y → 기업 전체 프로젝트 / 그 외 → 사용자가 속한 프로젝트(manager)
    tu_q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("rolecd,tenantid").eq("useruid", user_id).eq("useyn", True)
    if tenantid:
        tu_q = tu_q.eq("tenantid", tenantid)
    tu_rows = tu_q.execute().data or []
    is_tenant_manager = any(r.get("rolecd") == "M" for r in tu_rows)

    if is_tenant_manager and tenantid:
        proj_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid,projectnm").eq("tenantid", tenantid).order("projectnm").execute().data or []
    else:
        pu_rows = sb.schema(SUPABASE_SCHEMA).table("projectusers").select("projectid").eq("useruid", user_id).execute().data or []
        pids = [r["projectid"] for r in pu_rows if r.get("projectid")]
        proj_rows = []
        for pid in pids:
            p = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid,projectnm").eq("projectid", pid).execute().data
            if p:
                proj_rows.append(p[0])

    projectid = projects  # URL 파라미터

    if not projectid:
        return {"projects": proj_rows, "projectid": None, "projectusers": [], "tenantusers": []}

    # ── 선택된 프로젝트 사용자 ──────────────────────────────────
    pu_rows = sb.schema(SUPABASE_SCHEMA).table("projectusers").select("*").eq("projectid", projectid).order("useruid", desc=True).execute().data or []
    for row in pu_rows:
        row["createdts"] = _fmt_dt(row.get("createdts"), offsetminutes)
        nm, email = _get_usernm_email(sb, row.get("useruid", ""))
        row["usernm"] = nm
        row["email"] = email
        if row.get("creator"):
            cnm, _ = _get_usernm_email(sb, row["creator"])
            row["creatornm"] = cnm
        else:
            row["creatornm"] = ""

    # ── 해당 프로젝트에 없는 기업 사용자 (조회 Modal용) ───────────
    existing_uuids = {r["useruid"] for r in pu_rows if r.get("useruid")}
    if tenantid:
        all_tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("useruid").eq("tenantid", tenantid).eq("useyn", True).execute().data or []
    else:
        all_tu = []

    tenantusers_modal = []
    for tu in all_tu:
        uid = tu.get("useruid")
        if uid and uid not in existing_uuids:
            nm, email = _get_usernm_email(sb, uid)
            tenantusers_modal.append({"useruid": uid, "usernm": nm, "email": email})

    return {
        "projects": proj_rows,
        "projectid": projectid,
        "projectusers": pu_rows,
        "tenantusers": tenantusers_modal,
    }


class ProjectUserSaveRequest(BaseModel):
    projectid: str
    email: str
    rolecd: str = "U"
    useyn: bool = True
    useruid: Optional[str] = None


@router.post("/project-users")
def save_project_user(body: ProjectUserSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)

    pub_users = sb.schema("public").table("users").select("useruid").eq("email", body.email).execute().data
    if not pub_users:
        raise HTTPException(status_code=400, detail="존재하지 않는 이메일입니다.")
    useruid = pub_users[0]["useruid"]

    existing = sb.schema(SUPABASE_SCHEMA).table("projectusers").select("*").eq("projectid", body.projectid).eq("useruid", useruid).execute().data
    existing = existing[0] if existing else None

    data = {
        "projectid": body.projectid,
        "useruid": useruid,
        "useyn": body.useyn,
        "rolecd": body.rolecd,
    }

    if existing:
        sb.schema(SUPABASE_SCHEMA).table("projectusers").update(data).eq("projectid", body.projectid).eq("useruid", useruid).execute()
    else:
        data["creator"] = user.id
        sb.schema(SUPABASE_SCHEMA).table("projectusers").insert(data).execute()

    return {"result": "success", "message": "사용자가 성공적으로 저장되었습니다."}


class ProjectUserDeleteRequest(BaseModel):
    projectid: str
    useruid: str


@router.delete("/project-users")
def delete_project_user(body: ProjectUserDeleteRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("projectusers").delete().eq("projectid", body.projectid).eq("useruid", body.useruid).execute()
    return {"result": "success", "message": "사용자가 성공적으로 삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  INVITE MEMBERS (테넌트 매니저 전용)
# ══════════════════════════════════════════════════════

def _get_tenant_manager_tenantid(user_id: str) -> int:
    """로그인 사용자가 매니저인 tenantid 반환. 권한 없으면 403."""
    svc = get_service_client()
    tu_rows = (
        svc.schema(SUPABASE_SCHEMA)
        .table("tenantusers")
        .select("rolecd,tenantid")
        .eq("useruid", user_id)
        .eq("useyn", True)
        .execute()
        .data or []
    )
    manager_row = next((r for r in tu_rows if r.get("rolecd") == "M"), None)
    if not manager_row:
        raise HTTPException(status_code=403, detail="테넌트 매니저 권한이 필요합니다.")
    return int(manager_row["tenantid"])


@router.get("/invite-members")
def list_invite_members(token: str = Depends(get_token)):
    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _get_tenant_manager_tenantid(user_id)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    offsetminutes = _get_offsetminutes(svc, user_id)

    rows = (
        sd.table("userregreqs")
        .select("*")
        .eq("tenantid", tenantid)
        .order("createdts", desc=True)
        .execute()
        .data or []
    )
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"), offsetminutes)

    return {"invitations": rows, "tenantid": str(tenantid)}


class InviteMembersRequest(BaseModel):
    emails: list[str]
    servicecd: str


@router.post("/invite-members")
def invite_member(body: InviteMembersRequest, token: str = Depends(get_token)):
    import smtplib
    from email.mime.text import MIMEText

    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _get_tenant_manager_tenantid(user_id)

    seen = set()
    emails = [e.strip() for e in body.emails if e and e.strip()]
    emails = [e for e in emails if not (e in seen or seen.add(e))]
    if not emails:
        raise HTTPException(status_code=400, detail="초대할 이메일을 입력해주세요.")

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    # 테넌트명 / accountuid 조회 (기존 llmkeys.py의 tenantid→accountuid 해석 패턴과 동일)
    t_row = sd.table("tenants").select("tenantnm,issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    tenantnm = t_row.data.get("tenantnm", "") if t_row.data else ""
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True
    if issystemtenant:
        acc = sd.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = sd.table("accounts").select("accountuid").eq("tenantid", tenantid).maybe_single().execute()
    accountuid = acc.data["accountuid"] if acc and acc.data else None

    # 이미 public.users에 가입된 이메일 → useruid 매핑
    user_rows = svc.schema("public").table("users").select("useruid,email").in_("email", emails).execute().data or []
    email_to_useruid = {r["email"]: r["useruid"] for r in user_rows}
    existing_useruids = {u for u in email_to_useruid.values() if u}

    # 해당 서비스에 대한 기존 serviceusers 행 전부 조회 (active/inactive 구분 위해 useyn 필터 없이)
    su_by_useruid = {}
    if existing_useruids:
        su_rows = (
            sd.table("serviceusers")
            .select("useruid,useyn")
            .eq("tenantid", tenantid)
            .eq("servicecd", body.servicecd)
            .in_("useruid", list(existing_useruids))
            .execute()
            .data or []
        )
        for r in su_rows:
            su_by_useruid[r["useruid"]] = r["useyn"]

    skipped = []      # 이미 해당 서비스에 가입되어 있음
    auto_added = []   # 계정은 있으나 이 서비스엔 미가입 → 자동으로 테넌트/서비스 등록
    to_invite = []    # 계정 자체가 없음 → 기존 회원가입 초대 메일 발송
    sent, failed = [], []

    for email in emails:
        useruid = email_to_useruid.get(email)
        if not useruid:
            to_invite.append(email)
            continue

        if su_by_useruid.get(useruid):
            skipped.append(email)
            continue

        # 계정은 있지만 이 서비스엔 미가입 → 초대한 테넌트/서비스에 바로 등록
        try:
            existing_tu = sd.table("tenantusers").select("useruid").eq("tenantid", tenantid).eq("useruid", useruid).execute().data
            if not existing_tu:
                sd.table("tenantusers").insert({
                    "tenantid": tenantid,
                    "useruid": useruid,
                    "rolecd": "U",
                    "useyn": True,
                    "creator": user_id,
                }).execute()

            if not accountuid:
                failed.append({"email": email, "error": "계정(accountuid)을 확인할 수 없어 서비스 등록에 실패했습니다."})
                continue

            if useruid in su_by_useruid:
                # 과거 탈퇴(useyn=False) 이력이 있으면 재활성화
                sd.table("serviceusers").update({"useyn": True}).eq("accountuid", accountuid).eq("servicecd", body.servicecd).eq("useruid", useruid).execute()
            else:
                sd.table("serviceusers").insert({
                    "accountuid": accountuid,
                    "servicecd": body.servicecd,
                    "useruid": useruid,
                    "tenantid": tenantid,
                    "useyn": True,
                    "creator": user_id,
                }).execute()
            auto_added.append(email)
        except Exception as e:
            failed.append({"email": email, "error": str(e)})

    if not to_invite:
        message = ""
        if auto_added:
            message += f"{len(auto_added)}명은 이미 가입된 계정이라 바로 서비스에 등록했습니다. "
        if skipped:
            message += f"{len(skipped)}명은 이미 가입되어 있어 제외했습니다. "
        if failed:
            message += f"{len(failed)}건 처리 실패."
        return {
            "ok": len(failed) == 0, "sent": [], "failed": failed, "skipped": skipped, "auto_added": auto_added,
            "message": message.strip() or "처리할 이메일이 없습니다.",
        }

    # 서비스명 조회
    code_rows = (
        sd.table("codes")
        .select("default_name")
        .eq("codegroupcd", "servicecd")
        .eq("codevalue", body.servicecd)
        .execute()
        .data
    )
    service_name = code_rows[0].get("default_name", body.servicecd) if code_rows else body.servicecd

    login_user = settings.EMAIL_HOST_USER
    try:
        smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        smtp.login(login_user, settings.EMAIL_HOST_PASSWORD)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메일 서버 연결 실패: {str(e)}")

    try:
        for email in to_invite:
            try:
                result = sd.table("userregreqs").insert({
                    "tenantid": tenantid,
                    "email": email,
                    "servicecd": body.servicecd,
                    "creator": user_id,
                }).execute()
                if not result.data:
                    failed.append({"email": email, "error": "초대 요청 저장에 실패했습니다."})
                    continue

                regreqsuid = result.data[0].get("userregrequid", "")
                invite_link = f"https://dev-smart-doc.azurewebsites.net/register-invite?req={regreqsuid}"

                subject = f"[D2Doc] {tenantnm} 서비스 초대"
                mail_body = (
                    f"안녕하세요,\n\n"
                    f"{tenantnm}의 관리자로부터 D2Doc 서비스에 초대되었습니다.\n\n"
                    f"초대된 서비스: {service_name}\n\n"
                    f"아래 링크를 클릭하여 회원가입을 완료해주세요:\n"
                    f"{invite_link}\n\n"
                    f"감사합니다.\nD2Doc 팀"
                )
                msg = MIMEText(mail_body, "plain", "utf-8")
                msg["Subject"] = subject
                msg["From"] = login_user
                msg["To"] = email
                smtp.sendmail(login_user, [email], msg.as_string())
                sent.append(email)
            except Exception as e:
                failed.append({"email": email, "error": str(e)})
    finally:
        smtp.quit()

    message = f"{len(sent)}명에게 초대 메일이 발송되었습니다."
    if auto_added:
        message += f" (이미 가입된 계정 {len(auto_added)}명은 바로 서비스에 등록됨)"
    if skipped:
        message += f" (이미 가입되어 제외 {len(skipped)}건)"
    if failed:
        message += f" ({len(failed)}건 실패)"

    return {"ok": len(failed) == 0, "sent": sent, "failed": failed, "skipped": skipped, "auto_added": auto_added, "message": message}
