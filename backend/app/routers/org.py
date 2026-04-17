"""Org router — Tenant Users, Tenant LLMs, Projects, Project Users"""
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.app.dependencies import get_token
from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


def _get_user(token: str):
    sb = _sb(token)
    resp = sb.auth.get_user(token)
    if not resp or not resp.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    return resp.user


def _get_tenantid(sb, user_id: str) -> Optional[str]:
    rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).execute().data
    return rows[0]["tenantid"] if rows else None


def _fmt_dt(raw) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        return dt.strftime("%y-%m-%d %H:%M")
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
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id

    # tenantid 결정: 파라미터 > 세션 tenantid
    if not tenantid:
        tenantid = _get_tenantid(sb, user_id)
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
    sd_tenant = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid").eq("issytemtenant", True).execute().data
    other_tenantid = int(sd_tenant[0]["tenantid"]) if sd_tenant else None

    # 기존 tenantusers 레코드 확인
    existing_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("*").eq("tenantid", tenantid).eq("useruid", useruid).execute().data
    existing = existing_rows[0] if existing_rows else None

    # 사용자 수 제한 체크 (신규 등록 or 비활성→활성 전환)
    today = datetime.utcnow().date().isoformat()
    useyn_old = existing["useyn"] if existing else None
    is_new_or_activate = not existing or (useyn_old is False and body.useyn is True)

    if is_new_or_activate and other_tenantid != tenantid:
        billdts_res = (
            sb.schema(SUPABASE_SCHEMA).table("billdts").select("*")
            .lte("billstartdt", today).gte("billenddt", today)
            .eq("tenantid", tenantid).execute()
        )
        if not billdts_res.data:
            raise HTTPException(status_code=400, detail="현재 사용 가능한 결제 기간이 존재하지 않습니다.")
        billstartdt = billdts_res.data[0]["billstartdt"]

        tum_res = (
            sb.schema(SUPABASE_SCHEMA).table("tenantusermonths").select("*")
            .eq("tenantid", tenantid).eq("billstartdt", billstartdt).execute()
        )
        current_count = len(tum_res.data)
        tenant_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("billingusercnt").eq("tenantid", tenantid).execute().data
        max_cnt = tenant_row[0]["billingusercnt"] if tenant_row else 0
        if max_cnt and max_cnt <= current_count:
            raise HTTPException(status_code=400, detail="해당 요금제의 사용 가능 인원이 모두 찼습니다.")
        sb.schema(SUPABASE_SCHEMA).table("tenantusermonths").insert({
            "billstartdt": billstartdt,
            "tenantid": tenantid,
            "useruid": useruid,
            "recordtypecd": "N",
            "creator": user_id,
        }).execute()

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
        # 다른 기업 소속 확인
        other_check = (
            sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("*")
            .neq("tenantid", other_tenantid).eq("useruid", useruid).execute()
        )
        if other_check.data:
            raise HTTPException(status_code=400, detail="해당 사용자는 다른 기업에 이미 소속되어 있습니다.")

        # tenantnewusers 확인
        sep = body.sep
        tenantnewuid = body.tenantnewuid
        tn_res = sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").select("tenantnewuid").eq("useruid", useruid).eq("tenantid", tenantid).eq("approvecd", "A").execute()
        if tn_res.data:
            tenantnewuid = tn_res.data[0]["tenantnewuid"]
            sep = "newusers"

        save_data["creator"] = user_id
        sb.schema(SUPABASE_SCHEMA).table("tenantusers").insert(save_data).execute()

        # billingmodelcd 업데이트
        bm_res = sb.schema(SUPABASE_SCHEMA).table("tenants").select("billingmodelcd").eq("tenantid", tenantid).execute().data
        bm = bm_res[0]["billingmodelcd"] if bm_res else None
        if bm:
            sb.schema(SUPABASE_SCHEMA).table("users").update({"billingmodelcd": bm}).eq("useruid", useruid).execute()

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

        # SmartDoc 공용 테넌트에서 제거
        if other_tenantid and other_tenantid != tenantid:
            sb.schema(SUPABASE_SCHEMA).table("tenantusers").delete().eq("tenantid", other_tenantid).eq("useruid", useruid).execute()
            pub_proj = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("tenantid", other_tenantid).eq("projectnm", "public").execute().data
            if pub_proj:
                sb.schema(SUPABASE_SCHEMA).table("projectusers").delete().eq("projectid", pub_proj[0]["projectid"]).eq("useruid", useruid).execute()
            email_proj = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("tenantid", other_tenantid).eq("projectnm", body.email).execute().data
            if email_proj:
                ep_id = email_proj[0]["projectid"]
                sb.schema(SUPABASE_SCHEMA).table("projectusers").delete().eq("projectid", ep_id).eq("useruid", useruid).execute()
                sb.schema(SUPABASE_SCHEMA).table("docs").delete().eq("projectid", ep_id).execute()
                sb.schema(SUPABASE_SCHEMA).table("projects").delete().eq("projectid", ep_id).execute()

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
    """llmmodels 테이블에서 닉네임/활성 여부 조회"""
    if not llmmodelnm:
        return {"llmmodelnicknm": "", "llmmodelactiveyn": False}
    try:
        rows = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("llmmodelnicknm,useyn").eq("llmmodelnm", llmmodelnm).execute().data
        if rows:
            return {"llmmodelnicknm": rows[0].get("llmmodelnicknm", llmmodelnm), "llmmodelactiveyn": rows[0].get("useyn", False)}
    except Exception:
        pass
    return {"llmmodelnicknm": llmmodelnm, "llmmodelactiveyn": False}


@router.get("/tenant-llms")
def list_tenant_llms(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id

    tenantid = _get_tenantid(sb, user_id)
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    # 기업 정보
    t_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", tenantid).execute().data
    tenant = t_rows[0] if t_rows else {}
    if tenant.get("llmmodelnm"):
        info = _get_llmmodel_info(sb, tenant["llmmodelnm"])
        tenant["llmmodelnicknm"] = info["llmmodelnicknm"]
        tenant["llmmodelactiveyn"] = info["llmmodelactiveyn"]
    else:
        tenant["llmmodelnicknm"] = ""
        tenant["llmmodelactiveyn"] = False
    # llmmodeluseyn: 고객사 키 사용 여부 (encapikey 유무로 판단)
    tenant["llmmodeluseyn"] = bool(tenant.get("encapikey"))
    tenant.pop("encapikey", None)  # 보안상 제거

    # 프로젝트 목록
    projects = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("tenantid", tenantid).order("projectnm").execute().data or []
    for p in projects:
        if p.get("llmmodelnm"):
            info = _get_llmmodel_info(sb, p["llmmodelnm"])
            p["llmmodelnicknm"] = info["llmmodelnicknm"]
            p["llmmodelactiveyn"] = info["llmmodelactiveyn"]
        else:
            p["llmmodelnicknm"] = ""
            p["llmmodelactiveyn"] = False
        p.pop("encapikey", None)  # 보안상 제거

    # LLM 모델 목록 (드롭다운용)
    llmmodels = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("llmmodelnm,llmmodelnicknm,useyn").order("llmmodelnm").execute().data or []

    return {
        "tenant": tenant,
        "projects": projects,
        "llmmodels": llmmodels,
    }


class TenantLlmSaveRequest(BaseModel):
    tenantid: Optional[str] = None
    projectid: Optional[str] = None
    llmmodelnm: Optional[str] = None
    apikey: Optional[str] = None  # 빈 문자열이면 기존 키 유지


@router.post("/tenant-llms")
def save_tenant_llm(body: TenantLlmSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    if not body.tenantid and not body.projectid:
        raise HTTPException(status_code=400, detail="tenantid 또는 projectid가 필요합니다.")

    from utilsPrj.crypto_helper import encrypt_value, decrypt_value

    apikey = (body.apikey or "").strip()

    # API Key 가 비어 있으면 기존 키 유지
    if not apikey:
        if body.tenantid:
            row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("encapikey").eq("tenantid", body.tenantid).execute().data
        else:
            row = sb.schema(SUPABASE_SCHEMA).table("projects").select("encapikey").eq("projectid", body.projectid).execute().data
        if row and row[0].get("encapikey"):
            apikey = decrypt_value(row[0]["encapikey"])

    encapikey = encrypt_value(apikey) if apikey else None
    llmmodelnm = body.llmmodelnm or None

    # API Key가 없으면 llmmodelnm도 초기화
    if not apikey:
        llmmodelnm = None
        encapikey = None

    data = {"llmmodelnm": llmmodelnm, "encapikey": encapikey}

    if body.tenantid:
        data["tenantid"] = body.tenantid
        sb.schema(SUPABASE_SCHEMA).table("tenants").upsert(data).execute()
    else:
        data["projectid"] = body.projectid
        sb.schema(SUPABASE_SCHEMA).table("projects").upsert(data).execute()

    return {"result": "success", "message": "성공적으로 저장되었습니다."}


class TenantLlmDeleteRequest(BaseModel):
    tenantid: Optional[str] = None
    projectid: Optional[str] = None


@router.delete("/tenant-llms")
def delete_tenant_llm(body: TenantLlmDeleteRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    if not body.tenantid and not body.projectid:
        raise HTTPException(status_code=400, detail="tenantid 또는 projectid가 필요합니다.")

    data = {"llmmodelnm": None, "encapikey": None}

    if body.tenantid:
        data["tenantid"] = body.tenantid
        sb.schema(SUPABASE_SCHEMA).table("tenants").upsert(data).execute()
    else:
        data["projectid"] = body.projectid
        sb.schema(SUPABASE_SCHEMA).table("projects").upsert(data).execute()

    return {"result": "success", "message": "LLM 정보가 삭제되었습니다."}


# ══════════════════════════════════════════════════════
#  PROJECTS
# ══════════════════════════════════════════════════════

@router.get("/projects")
def list_org_projects(
    tenantid: Optional[str] = Query(None),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)

    if not tenantid:
        tenantid = _get_tenantid(sb, user.id)
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

    return {"projects": rows, "tenantnm": tenantnm, "tenantid": tenantid}


class OrgProjectSaveRequest(BaseModel):
    projectid: Optional[str] = None
    tenantid: Optional[str] = None
    projectnm: str
    projectdesc: Optional[str] = None
    useyn: bool = True


@router.post("/projects")
def save_org_project(body: OrgProjectSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)

    tenantid = body.tenantid or _get_tenantid(sb, user.id)
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")

    if not body.projectnm:
        raise HTTPException(status_code=400, detail="프로젝트명은 필수입니다.")

    data = {
        "projectnm": body.projectnm,
        "projectdesc": body.projectdesc,
        "useyn": body.useyn,
        "tenantid": tenantid,
        "creator": user.id,
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
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id

    tenantid = _get_tenantid(sb, user_id)

    # ── 프로젝트 목록 (드롭다운용) ──────────────────────────────
    # tenantmanager=Y → 기업 전체 프로젝트 / 그 외 → 사용자가 속한 프로젝트(manager)
    tu_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("rolecd,tenantid").eq("useruid", user_id).eq("useyn", True).execute().data or []
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
