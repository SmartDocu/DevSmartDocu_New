"""Settings router — Servers, Projects, Tenants, MyInfo"""
import json
import os
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from backend.app.dependencies import get_token

router = APIRouter()

DB_TYPES = ["MSSQL", "SUPABASE", "ORACLE"]
BILLING_MODELS = ["Fr", "Pr", "Te", "En"]


def _sb(token: str):
    from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA
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
            prefix = "/storage/v1/object/public/smartdoc/"
            if prefix in parsed.path:
                path_to_delete = parsed.path.split(prefix)[-1]
                sb.storage.from_("smartdoc").remove([path_to_delete])
        except Exception:
            pass
    ext = os.path.splitext(file.filename)[1]
    uuid_name = f"{uuid.uuid4()}{ext}"
    storage_path = f"{folder}/{uuid_name}"
    sb.storage.from_("smartdoc").upload(
        storage_path,
        file.file.read(),
        {"content-type": file.content_type},
    )
    public_url = sb.storage.from_("smartdoc").get_public_url(storage_path).split("?")[0]
    return file.filename, public_url


# ══════════════════════════════════════════════════════
#  SERVERS (dbconnectors)
# ══════════════════════════════════════════════════════

@router.get("/servers")
def list_servers(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

    rows = sb.schema(SUPABASE_SCHEMA).table("dbconnectors").select("*").eq("tenantid", tenantid).order("orderno").execute().data or []
    for row in rows:
        row["decendpoint"] = _decrypt(row.get("encendpoint", ""))
        row["decdatabase"] = _decrypt(row.get("encaccessdb", ""))
        row["decuserid"] = _decrypt(row.get("encaccessuserid", ""))

    return {"connectors": rows, "dbtypes": DB_TYPES}


class ServerSaveRequest(BaseModel):
    connectid: Optional[int] = None
    connectnm: str
    connecttype: str
    orderno: Optional[int] = None
    useyn: bool = True
    encendpoint: str = ""
    encdatabase: str = ""
    encaccessuserid: str = ""
    password: Optional[str] = None


@router.post("/servers")
def save_server(body: ServerSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    tenantid = _get_tenantid(sb, user.id)

    update_fields = {
        "connectnm": body.connectnm,
        "connecttype": body.connecttype,
        "orderno": body.orderno,
        "useyn": body.useyn,
        "encendpoint": _encrypt(body.encendpoint),
    }
    if body.encdatabase:
        update_fields["encaccessdb"] = _encrypt(body.encdatabase)
    if body.encaccessuserid:
        update_fields["encaccessuserid"] = _encrypt(body.encaccessuserid)
    if body.password:
        update_fields["encaccesspassword"] = _encrypt(body.password)

    if body.connectid:
        existing = sb.schema(SUPABASE_SCHEMA).table("dbconnectors").select("connectid").eq("connectid", body.connectid).execute().data
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("dbconnectors").update(update_fields).eq("connectid", body.connectid).execute()
            return {"status": "updated"}

    update_fields["tenantid"] = tenantid
    update_fields["creator"] = user.id
    sb.schema(SUPABASE_SCHEMA).table("dbconnectors").insert(update_fields).execute()
    return {"status": "inserted"}


@router.delete("/servers/{connectid}")
def delete_server(connectid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("dbconnectors").delete().eq("connectid", connectid).execute()
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

    return {"tenants": rows, "billing_models": BILLING_MODELS}


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
    iconfile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)

    useyn_bool = useyn.lower() not in ("false", "0", "")
    llmlimityn_bool = llmlimityn.lower() not in ("false", "0", "")
    billingusercnt_int = int(billingusercnt) if billingusercnt and billingusercnt.strip() else None

    tenant_data = {
        "tenantnm": tenantnm,
        "useyn": useyn_bool,
        "llmlimityn": llmlimityn_bool,
        "creator": user.id,
    }

    if tenantid:
        existing = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid, iconfileurl").eq("tenantid", tenantid).execute().data
        if existing:
            if iconfile and iconfile.filename:
                existing_url = existing[0].get("iconfileurl")
                icon_nm, icon_url = _save_iconfile(sb, iconfile, "iconfiles/tenants", existing_url)
                tenant_data["iconfilenm"] = icon_nm
                tenant_data["iconfileurl"] = icon_url
            sb.schema(SUPABASE_SCHEMA).table("tenants").update(tenant_data).eq("tenantid", tenantid).execute()
            bill_data = {
                "billingmodelcd": billingmodelcd,
                "billingusercnt": billingusercnt_int,
            }
            if email is not None:
                bill_data["encemail"] = _encrypt(email)
            if telno is not None:
                bill_data["enctelno"] = _encrypt(telno)
            existing_bill = sb.schema(SUPABASE_SCHEMA).table("billmasters").select("tenantid").eq("tenantid", tenantid).execute().data
            if existing_bill:
                sb.schema(SUPABASE_SCHEMA).table("billmasters").update(bill_data).eq("tenantid", tenantid).execute()
            else:
                bill_data["tenantid"] = tenantid
                sb.schema(SUPABASE_SCHEMA).table("billmasters").insert(bill_data).execute()
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
        bill_data = {
            "tenantid": new_tenantid,
            "billingmodelcd": billingmodelcd,
            "billingusercnt": billingusercnt_int,
            "encemail": _encrypt(email or ""),
            "enctelno": _encrypt(telno or ""),
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

    return {
        "user_info": user_info,
        "tenantuser": tenantuser,
        "tenant": tenant,
        "project_users": project_users,
    }


class UpdateUsernameRequest(BaseModel):
    usernm: str


@router.post("/myinfo/username")
def update_username(body: UpdateUsernameRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("users").update({"usernm": body.usernm}).eq("useruid", user.id).execute()
    return {"status": "ok"}
