"""Org router — Tenant Users, Tenant LLMs, Projects, Project Users, Invite Members"""
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()



def _fmt_dt(raw) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
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
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id

    # tenantid 결정: Query 파라미터 > X-Tenant-ID 헤더
    if not tenantid:
        tenantid = header_tenantid
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    # 기업명 조회
    t_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantnm").eq("tenantid", tenantid).execute().data
    tenantnm = t_rows[0]["tenantnm"] if t_rows else ""

    # tenantusers 조회
    tu_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("*").eq("tenantid", tenantid).order("useruid", desc=True).execute().data or []
    for row in tu_rows:
        row["sep"] = "users"
        nm, email = _get_usernm_email(sb, row.get("useruid", ""))
        row["usernm"] = nm
        row["email"] = email
        if row.get("creator"):
            cnm, _ = _get_usernm_email(sb, row["creator"])
            row["creatornm"] = cnm
        else:
            row["creatornm"] = ""
        row["createdts"] = _fmt_dt(row.get("createdts"))

    # tenantnewusers (미승인 대기) 조회
    tn_rows = sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").select("*").eq("tenantid", tenantid).eq("approvecd", "A").execute().data or []
    for row in tn_rows:
        row["sep"] = "newusers"
        row["rolecd"] = "U"
        nm, email = _get_usernm_email(sb, row.get("useruid", ""))
        row["usernm"] = nm
        row["email"] = email
        if row.get("creator"):
            cnm, _ = _get_usernm_email(sb, row["creator"])
            row["creatornm"] = cnm
        else:
            row["creatornm"] = ""
        row["useyn"] = False
        row["createdts"] = _fmt_dt(row.get("createdts"))

    all_users = tu_rows + tn_rows
    # 이메일 기준 정렬
    all_users.sort(key=lambda x: (x.get("email") or "").lower())

    return {
        "tenantid": tenantid,
        "tenantnm": tenantnm,
        "users": all_users,
    }


class TenantUserSaveRequest(BaseModel):
    sep: Optional[str] = None
    tenantnewuid: Optional[str] = None
    tenantid: str
    useruid: Optional[str] = None
    email: str
    rolecd: str = "U"
    useyn: bool = True


@router.post("/tenant-users")
def save_tenant_user(body: TenantUserSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id
    tenantid = int(body.tenantid)

    # 이메일로 사용자 조회
    pub_users = sb.schema("public").table("users").select("*").eq("email", body.email).execute().data
    if not pub_users:
        raise HTTPException(status_code=400, detail="존재하지 않는 이메일입니다.")

    target_user = pub_users[0]
    useruid = target_user["useruid"]

    # SmartDoc 테넌트 id 조회
    sd_tenant = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid").eq("issystemtenant", True).execute().data
    other_tenantid = int(sd_tenant[0]["tenantid"]) if sd_tenant else None

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
        if body.sep == "newusers" and body.tenantnewuid:
            sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").upsert({
                "tenantnewuid": body.tenantnewuid,
                "approvecd": "S",
                "approveuseruid": user_id,
                "approvedts": datetime.now().isoformat(),
            }).execute()
    else:
        # tenantnewusers 확인
        sep = body.sep
        tenantnewuid = body.tenantnewuid
        tn_res = sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").select("tenantnewuid").eq("useruid", useruid).eq("tenantid", tenantid).eq("approvecd", "A").execute()
        if tn_res.data:
            tenantnewuid = tn_res.data[0]["tenantnewuid"]
            sep = "newusers"

        save_data["creator"] = user_id
        sb.schema(SUPABASE_SCHEMA).table("tenantusers").insert(save_data).execute()

        # public 프로젝트에 추가
        proj_res = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("tenantid", tenantid).eq("projectnm", "public").execute().data
        if proj_res:
            sb.schema(SUPABASE_SCHEMA).table("projectusers").insert({
                "projectid": proj_res[0]["projectid"],
                "useruid": useruid,
                "rolecd": body.rolecd,
                "useyn": body.useyn,
                "creator": user_id,
            }).execute()

        if sep == "newusers" and tenantnewuid:
            sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").upsert({
                "tenantnewuid": tenantnewuid,
                "approvecd": "S",
                "approveuseruid": user_id,
                "approvedts": datetime.now().isoformat(),
            }).execute()

    return {"result": "success", "message": "사용자가 성공적으로 저장되었습니다."}


class TenantUserDeleteRequest(BaseModel):
    sep: Optional[str] = None
    tenantnewuid: Optional[str] = None
    tenantid: str
    useruid: str
    approvenote: Optional[str] = None


@router.delete("/tenant-users")
def delete_tenant_user(body: TenantUserDeleteRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id
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

    # tenantnewusers 처리
    if body.tenantnewuid:
        sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").upsert({
            "tenantnewuid": body.tenantnewuid,
            "approvecd": "D",
            "approvenote": body.approvenote,
            "approveuseruid": user_id,
            "approvedts": datetime.now().isoformat(),
        }).execute()

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

    if not tenantid:
        tenantid = header_tenantid
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    t_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantnm").eq("tenantid", tenantid).execute().data
    tenantnm = t_rows[0]["tenantnm"] if t_rows else ""

    rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("tenantid", tenantid).order("createdts", desc=True).execute().data or []
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
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
                .select("value").eq("configcd", "project_limit").eq("plancd", plancd) \
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
        row["createdts"] = _fmt_dt(row.get("createdts"))
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

    rows = (
        sd.table("userregreqs")
        .select("*")
        .eq("tenantid", tenantid)
        .order("createdts", desc=True)
        .execute()
        .data or []
    )
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        scds = row.get("servicecds")
        if isinstance(scds, str):
            try:
                row["servicecds"] = json.loads(scds)
            except Exception:
                row["servicecds"] = []

    return {"invitations": rows, "tenantid": str(tenantid)}


class InviteMembersRequest(BaseModel):
    email: str
    servicecds: list[str]


@router.post("/invite-members")
def invite_member(body: InviteMembersRequest, token: str = Depends(get_token)):
    import smtplib
    from email.mime.text import MIMEText

    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _get_tenant_manager_tenantid(user_id)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    # userregreqs 삽입
    result = sd.table("userregreqs").insert({
        "tenantid": tenantid,
        "email": body.email,
        "servicecds": body.servicecds,
        "creator": user_id,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="초대 요청 저장에 실패했습니다.")

    regreqsuid = result.data[0].get("userregreqsuid") or result.data[0].get("id", "")

    # 테넌트명 조회
    t_row = sd.table("tenants").select("tenantnm").eq("tenantid", tenantid).maybe_single().execute()
    tenantnm = t_row.data.get("tenantnm", "") if t_row.data else ""

    # 서비스명 조회
    service_names = []
    for scd in body.servicecds:
        code_rows = (
            sd.table("codes")
            .select("default_name")
            .eq("codegroupcd", "servicecd")
            .eq("codevalue", scd)
            .execute()
            .data
        )
        service_names.append(code_rows[0].get("default_name", scd) if code_rows else scd)

    invite_link = f"https://dev-smart-doc.azurewebsites.net/register-invite?req={regreqsuid}"

    subject = f"[D2Doc] {tenantnm} 서비스 초대"
    mail_body = (
        f"안녕하세요,\n\n"
        f"{tenantnm}의 관리자로부터 D2Doc 서비스에 초대되었습니다.\n\n"
        f"초대된 서비스: {', '.join(service_names)}\n\n"
        f"아래 링크를 클릭하여 회원가입을 완료해주세요:\n"
        f"{invite_link}\n\n"
        f"감사합니다.\nD2Doc 팀"
    )

    login_user = settings.EMAIL_HOST_USER
    try:
        msg = MIMEText(mail_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = login_user
        msg["To"] = body.email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(login_user, settings.EMAIL_HOST_PASSWORD)
            smtp.sendmail(login_user, [body.email], msg.as_string())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메일 전송 실패: {str(e)}")

    return {"ok": True, "message": "초대 메일이 발송되었습니다."}
