"""Settings router — Servers, Projects, Tenants, MyInfo"""
import json
import os
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()

DB_TYPES = ["Oracle", "Oracle(TNS)", "mssql", "postgres", "supabase"]
BILLING_MODELS = ["Fr", "Pr", "Te", "En"]


def _get_tenantid(sb, user_id: str) -> Optional[str]:
    rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).execute().data
    return rows[0]["tenantid"] if rows else None


def _decrypt(val: str) -> str:
    if not val:
        return ""
    try:
        from utilsPrj.crypto_helper import decrypt_value
        return decrypt_value(val)
    except Exception:
        return ""


def _encrypt(val: str) -> Optional[str]:
    if not val:
        return None
    try:
        from utilsPrj.crypto_helper import encrypt_value
        return encrypt_value(val)
    except Exception:
        return None


def _fmt_dt(raw) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        return dt.strftime("%y-%m-%d %H:%M")
    except Exception:
        return str(raw)


def _save_iconfile(sb, file: UploadFile, folder: str, existing_url: Optional[str] = None) -> tuple:
    """아이콘 파일을 Supabase Storage에 업로드하고 (파일명, URL)을 반환."""
    if existing_url:
        try:
            parsed = urlparse(existing_url)
            prefix = "/storage/v1/object/public/sdoc/"
            if prefix in parsed.path:
                path_to_delete = parsed.path.split(prefix)[-1]
                sb.storage.from_("sdoc").remove([path_to_delete])
        except Exception:
            pass
    ext = os.path.splitext(file.filename)[1]
    uuid_name = f"{uuid.uuid4()}{ext}"
    storage_path = f"{folder}/{uuid_name}"
    sb.storage.from_("sdoc").upload(
        storage_path,
        file.file.read(),
        {"content-type": file.content_type},
    )
    public_url = sb.storage.from_("sdoc").get_public_url(storage_path).split("?")[0]
    return file.filename, public_url


# ══════════════════════════════════════════════════════
#  SERVERS (connectors, conntype='db')
# ══════════════════════════════════════════════════════

def _parse_secret(secret_json: Optional[str]) -> dict:
    if not secret_json:
        return {}
    try:
        return json.loads(secret_json) or {}
    except Exception:
        return {}


def _fetch_db_secret(secret_path: Optional[str], tenantid: Optional[str], connuid: Optional[str] = None) -> dict:
    """aws-sm 마커이면 AWS SM 조회, 아니면 레거시 JSON 파싱."""
    if not secret_path:
        return {}
    if secret_path == "aws-sm":
        from utilsPrj.secrets_cache import get_connector_secret
        try:
            return get_connector_secret(tenantid, connuid)
        except Exception:
            return {}
    return _parse_secret(secret_path)


@router.get("/servers")
def list_servers(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

    rows = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("*").eq("tenantid", tenantid).eq("conntype", "db")
        .order("createdts").execute().data or []
    )
    for row in rows:
        s = _fetch_db_secret(row.get("secret_path"), tenantid, row.get("connuid"))
        row["username"] = s.get("username", "")
        row.pop("secret_path", None)

    return {"connectors": rows, "dbtypes": DB_TYPES}


class ServerSaveRequest(BaseModel):
    connuid: Optional[str] = None
    connnm: str
    dbtype: str
    server: Optional[str] = None
    port: Optional[str] = None
    db: Optional[str] = None
    ssl_mode: bool = False
    service_name: Optional[str] = None
    sid: Optional[str] = None
    tns: Optional[str] = None
    timeout: Optional[int] = None
    retry_count: Optional[int] = None
    desc: Optional[str] = None
    useyn: bool = True
    username: Optional[str] = None
    password: Optional[str] = None


@router.post("/servers")
def save_server(body: ServerSaveRequest, token: str = Depends(get_token)):
    from utilsPrj.secrets_cache import save_connector_secret

    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

    if body.connuid:
        existing = (
            sb.schema(SUPABASE_SCHEMA).table("connectors")
            .select("connuid, secret_path").eq("connuid", body.connuid).execute().data
        )
        if existing:
            existing_sp = existing[0].get("secret_path") or ""

            # 기존 자격증명 조회 후 신규 값 병합
            merged = _fetch_db_secret(existing_sp, tenantid, body.connuid)
            if body.username is not None:
                merged["username"] = body.username
            if body.password:
                merged["password"] = body.password

            if merged:
                save_connector_secret(tenantid, body.connuid, merged)

            update_fields = {
                "connnm": body.connnm,
                "dbtype": body.dbtype,
                "server": body.server,
                "port": body.port,
                "db": body.db,
                "ssl_mode": body.ssl_mode,
                "service_name": body.service_name,
                "sid": body.sid,
                "tns": body.tns,
                "timeout": body.timeout,
                "retry_count": body.retry_count,
                "desc": body.desc,
                "useyn": body.useyn,
                "secret_path": "aws-sm",
            }
            sb.schema(SUPABASE_SCHEMA).table("connectors").update(update_fields).eq("connuid", body.connuid).execute()
            return {"status": "updated"}

    # INSERT — Python에서 UUID 생성
    connuid = str(uuid.uuid4())
    creds: dict = {}
    if body.username is not None:
        creds["username"] = body.username
    if body.password:
        creds["password"] = body.password

    if creds:
        save_connector_secret(tenantid, connuid, creds)

    insert_fields = {
        "connuid": connuid,
        "connnm": body.connnm,
        "conntype": "db",
        "dbtype": body.dbtype,
        "server": body.server,
        "port": body.port,
        "db": body.db,
        "ssl_mode": body.ssl_mode,
        "service_name": body.service_name,
        "sid": body.sid,
        "tns": body.tns,
        "timeout": body.timeout,
        "retry_count": body.retry_count,
        "desc": body.desc,
        "useyn": body.useyn,
        "secret_path": "aws-sm" if creds else None,
        "tenantid": tenantid,
        "creator": str(user.id),
    }
    sb.schema(SUPABASE_SCHEMA).table("connectors").insert(insert_fields).execute()
    return {"status": "inserted"}


@router.delete("/servers/{connuid}")
def delete_server(connuid: str, token: str = Depends(get_token)):
    from utilsPrj.secrets_cache import delete_connector_secret

    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("secret_path").eq("connuid", connuid).execute().data
    )
    if existing and (existing[0].get("secret_path") or "") == "aws-sm":
        delete_connector_secret(tenantid, connuid)

    sb.schema(SUPABASE_SCHEMA).table("connectors").delete().eq("connuid", connuid).execute()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════
#  PROJECTS
# ══════════════════════════════════════════════════════

@router.get("/projects")
def list_projects(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

    rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("tenantid", tenantid).order("createdts", desc=True).execute().data or []
    tenant_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantnm").eq("tenantid", tenantid).execute().data
    tenantnm = tenant_row[0]["tenantnm"] if tenant_row else ""

    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        if row.get("creator"):
            try:
                u = sb.schema(SUPABASE_SCHEMA).table("users").select("usernm").eq("useruid", row["creator"]).execute().data
                row["creatornm"] = u[0]["usernm"] if u else ""
            except Exception:
                row["creatornm"] = ""

    return {"projects": rows, "tenantnm": tenantnm}


class ProjectSaveRequest(BaseModel):
    projectid: Optional[str] = None
    projectnm: str
    projectdesc: Optional[str] = None
    useyn: bool = True


@router.post("/projects")
def save_project(body: ProjectSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

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
            return {"status": "updated"}

    sb.schema(SUPABASE_SCHEMA).table("projects").insert(data).execute()
    return {"status": "inserted"}


@router.delete("/projects/{projectid}")
def delete_project(projectid: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("projects").delete().eq("projectid", projectid).execute()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════
#  TENANTS
# ══════════════════════════════════════════════════════

@router.get("/tenants")
def list_tenants(token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").order("createdts", desc=True).execute().data or []
    bills = sb.schema(SUPABASE_SCHEMA).table("billmasters").select("*").execute().data or []
    bill_map = {b["tenantid"]: b for b in bills}

    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        if row.get("creator"):
            try:
                u = sb.schema(SUPABASE_SCHEMA).table("users").select("usernm").eq("useruid", row["creator"]).execute().data
                row["creatornm"] = u[0]["usernm"] if u else ""
            except Exception:
                row["creatornm"] = ""
        bill = bill_map.get(row.get("tenantid"))
        if bill:
            row["decemail"] = _decrypt(bill.get("encemail", ""))
            row["dectelno"] = _decrypt(bill.get("enctelno", ""))
        else:
            row["decemail"] = ""
            row["dectelno"] = ""

    langs = sb.schema(SUPABASE_SCHEMA).table("languages").select("languagecd, languagenm").order("languagenm").execute().data or []
    timezones = [r["timezone"] for r in (sb.schema(SUPABASE_SCHEMA).table("timezone").select("*").eq("useyn", True).execute().data or [])]
    return {"tenants": rows, "billing_models": BILLING_MODELS, "languages": langs, "timezones": timezones}


@router.post("/tenants")
async def save_tenant(
    tenantid: Optional[str] = Form(None),
    tenantnm: str = Form(...),
    useyn: str = Form("true"),
    billingmodelcd: str = Form("Fr"),
    billingusercnt: Optional[str] = Form(None),
    llmlimityn: str = Form("false"),
    email: Optional[str] = Form(None),
    telno: Optional[str] = Form(None),
    languagecd: Optional[str] = Form(None),
    timezone: Optional[str] = Form(None),
    issystemtenant: str = Form("false"),
    iconfile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)

    useyn_bool = useyn.lower() not in ("false", "0", "")
    llmlimityn_bool = llmlimityn.lower() not in ("false", "0", "")
    issystemtenant_bool = issystemtenant.lower() not in ("false", "0", "")
    billingusercnt_int = int(billingusercnt) if billingusercnt and billingusercnt.strip() else None

    tenant_data = {
        "tenantnm": tenantnm,
        "useyn": useyn_bool,
        "billingmodelcd": billingmodelcd or "Fr",
        "billingusercnt": billingusercnt_int,
        "llmlimityn": llmlimityn_bool,
        "issystemtenant": issystemtenant_bool,
        "creator": user.id,
    }
    if languagecd:
        tenant_data["languagecd"] = languagecd
    if timezone:
        tenant_data["timezone"] = timezone

    if tenantid:
        existing = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid, iconfileurl").eq("tenantid", tenantid).execute().data
        if existing:
            if iconfile and iconfile.filename:
                existing_url = existing[0].get("iconfileurl")
                icon_nm, icon_url = _save_iconfile(sb, iconfile, "iconfiles/tenants", existing_url)
                tenant_data["iconfilenm"] = icon_nm
                tenant_data["iconfileurl"] = icon_url
            sb.schema(SUPABASE_SCHEMA).table("tenants").update(tenant_data).eq("tenantid", tenantid).execute()
            return {"status": "updated"}

    resp = sb.schema(SUPABASE_SCHEMA).table("tenants").insert(tenant_data).execute()
    new_tenantid = resp.data[0]["tenantid"] if resp.data else None
    if new_tenantid:
        if iconfile and iconfile.filename:
            icon_nm, icon_url = _save_iconfile(sb, iconfile, "iconfiles/tenants")
            sb.schema(SUPABASE_SCHEMA).table("tenants").update({
                "iconfilenm": icon_nm,
                "iconfileurl": icon_url,
            }).eq("tenantid", new_tenantid).execute()
        from datetime import date
        bill_data = {
            "billtargetcd": "T",
            "tenantid": new_tenantid,
            "billingmodelcd": billingmodelcd or "Fr",
            "billingfirstdt": date.today().isoformat(),
            "useyn": True,
            "encemail": _encrypt(email or ""),
            "enctelno": _encrypt(telno or ""),
            "creator": user.id,
        }
        sb.schema(SUPABASE_SCHEMA).table("billmasters").insert(bill_data).execute()
    return {"status": "inserted"}


@router.delete("/tenants/{tenantid}")
def delete_tenant(tenantid: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("billmasters").delete().eq("tenantid", tenantid).execute()
    sb.schema(SUPABASE_SCHEMA).table("tenants").delete().eq("tenantid", tenantid).execute()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════
#  MY INFO
# ══════════════════════════════════════════════════════

@router.get("/myinfo")
def get_myinfo(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id

    # smartdoc users
    user_info = sb.schema(SUPABASE_SCHEMA).table("users").select("*").eq("useruid", user_id).execute().data
    user_info = user_info[0] if user_info else {}

    # tenantusers
    tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("*").eq("useruid", user_id).execute().data
    tenantuser = tu[0] if tu else {}
    tenantid = tenantuser.get("tenantid")

    # tenant
    tenant = {}
    if tenantid:
        t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", tenantid).execute().data
        tenant = t[0] if t else {}

    # projects the user belongs to
    pu_rows = sb.schema(SUPABASE_SCHEMA).table("projectusers").select("*").eq("useruid", user_id).execute().data or []
    if pu_rows and tenantid:
        projects = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("tenantid", tenantid).execute().data or []
        proj_map = {p["projectid"]: p for p in projects}
        for pu in pu_rows:
            pid = pu.get("projectid")
            pu["projectnm"] = proj_map[pid]["projectnm"] if pid in proj_map else ""
        project_users = [pu for pu in pu_rows if pu.get("projectnm")]
    else:
        project_users = []

    # tenantnewusers (기업 변경 이력 — 최신 1건)
    tenant_change = None
    tnu_rows = sb.schema(SUPABASE_SCHEMA).table("tenantnewusers").select("*").eq("useruid", user_id).order("createdts", desc=True).limit(1).execute().data or []
    if tnu_rows:
        tnu = tnu_rows[0]
        new_tenantid = tnu.get("tenantid")
        if new_tenantid and str(new_tenantid) != str(tenantid):
            new_tenant_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid,tenantnm").eq("tenantid", new_tenantid).execute().data or []
            new_tenantnm = new_tenant_rows[0]["tenantnm"] if new_tenant_rows else ""
            tenant_change = {
                "tenantnm": new_tenantnm,
                "approvecd": tnu.get("approvecd"),
                "approvenote": tnu.get("approvenote", ""),
            }

    return {
        "user_info": user_info,
        "tenantuser": tenantuser,
        "tenant": tenant,
        "project_users": project_users,
        "tenant_change": tenant_change,
    }


class UpdateUsernameRequest(BaseModel):
    usernm: str


@router.post("/myinfo/username")
def update_username(body: UpdateUsernameRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("users").update({"usernm": body.usernm}).eq("useruid", user.id).execute()
    return {"status": "ok"}
