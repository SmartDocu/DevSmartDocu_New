"""Settings router — Servers, Projects, Tenants, MyInfo"""
import json
import os
import uuid
from datetime import timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()


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


def _get_offsetminutes(sb, user_id: str, tenantid: Optional[str] = None) -> Optional[int]:
    try:
        q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id)
        if tenantid:
            q = q.eq("tenantid", int(tenantid))
        else:
            q = q.eq("useyn", True)
        rows = q.limit(1).execute().data or []
        if not rows:
            return None
        tu_data = rows[0]
        tz = tu_data.get("timezone")
        if not tz and tu_data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu_data["tenantid"]).maybe_single().execute()
            if t and t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None
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
def list_servers(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    rows = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("*").eq("tenantid", tenantid).eq("conntype", "db")
        .order("createdts").execute().data or []
    )
    for row in rows:
        s = _fetch_db_secret(row.get("secret_path"), tenantid, row.get("connuid"))
        row["username"] = s.get("username", "")
        row.pop("secret_path", None)

    code_rows = (
        sb.schema(SUPABASE_SCHEMA).table("codes")
        .select("default_name").eq("codegroupcd", "dbtype").eq("useyn", True)
        .order("orderno").execute().data or []
    )
    db_types = [r["default_name"] for r in code_rows if r.get("default_name")]

    return {"connectors": rows, "dbtypes": db_types}


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
def save_server(body: ServerSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    from utilsPrj.secrets_cache import save_connector_secret

    user = _get_user(token)
    sb = _sb(token)

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
def delete_server(connuid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    from utilsPrj.secrets_cache import delete_connector_secret

    user = _get_user(token)
    sb = _sb(token)

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
def list_projects(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

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
def save_project(body: ProjectSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

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

    tenantids = [row["tenantid"] for row in rows if row.get("tenantid")]
    account_map = {}
    if tenantids:
        svc = get_service_client().schema(SUPABASE_SCHEMA)
        acc_rows = svc.table("accounts").select("tenantid, encemail, enctelno").in_("tenantid", tenantids).execute().data or []
        account_map = {a["tenantid"]: a for a in acc_rows}

    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        if row.get("creator"):
            try:
                u = sb.schema(SUPABASE_SCHEMA).table("users").select("usernm").eq("useruid", row["creator"]).execute().data
                row["creatornm"] = u[0]["usernm"] if u else ""
            except Exception:
                row["creatornm"] = ""
        acc = account_map.get(row.get("tenantid"))
        row["decemail"] = _decrypt(acc.get("encemail")) if acc else ""
        row["dectelno"] = _decrypt(acc.get("enctelno")) if acc else ""

    langs = sb.schema(SUPABASE_SCHEMA).table("languages").select("languagecd, languagenm").order("languagenm").execute().data or []
    timezones = [r["timezone"] for r in (sb.schema(SUPABASE_SCHEMA).table("timezones").select("*").eq("useyn", True).execute().data or [])]
    return {"tenants": rows, "languages": langs, "timezones": timezones}


def _save_tenant_contact(tenantid: int, email: Optional[str], telno: Optional[str], creator: str):
    if not email and not telno:
        return
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    payload = {}
    if email:
        payload["encemail"] = _encrypt(email)
    if telno:
        payload["enctelno"] = _encrypt(telno)

    existing = svc.table("accounts").select("accountuid").eq("tenantid", tenantid).maybe_single().execute()
    if existing.data:
        svc.table("accounts").update(payload).eq("tenantid", tenantid).execute()
    else:
        payload.update({
            "accounttype": "T",
            "tenantid": tenantid,
            "accountstatus": "Active",
            "creator": creator,
        })
        svc.table("accounts").insert(payload).execute()


@router.post("/tenants")
async def save_tenant(
    tenantid: Optional[str] = Form(None),
    tenantnm: str = Form(...),
    useyn: str = Form("true"),
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
    issystemtenant_bool = issystemtenant.lower() not in ("false", "0", "")

    tenant_data = {
        "tenantnm": tenantnm,
        "useyn": useyn_bool,
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
            _save_tenant_contact(int(tenantid), email, telno, str(user.id))
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
        _save_tenant_contact(int(new_tenantid), email, telno, str(user.id))
    return {"status": "inserted"}


@router.delete("/tenants/{tenantid}")
def delete_tenant(tenantid: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("tenants").delete().eq("tenantid", tenantid).execute()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════
#  MY INFO
# ══════════════════════════════════════════════════════

@router.get("/myinfo")
def get_myinfo(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = user.id

    # smartdoc users
    user_info = sb.schema(SUPABASE_SCHEMA).table("users").select("*").eq("useruid", user_id).execute().data
    user_info = user_info[0] if user_info else {}

    # tenantusers — 내 모든 테넌트 (현재 테넌트 필터 제거)
    tu_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("tenantid,rolecd").eq("useruid", user_id).eq("useyn", True).execute().data or []
    my_tenantids = [r["tenantid"] for r in tu_rows]
    tu_map = {r["tenantid"]: r for r in tu_rows}

    # 현재 선택 테넌트 기준 단일값 (timezone 등 기존 호환용)
    tenantuser = tu_map.get(int(tenantid)) if tenantid else {}
    tenant = {}
    if tenantid:
        t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", tenantid).execute().data
        tenant = t[0] if t else {}

    # 내 모든 테넌트 정보
    all_tenants = {}
    if my_tenantids:
        t_rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid,tenantnm").in_("tenantid", my_tenantids).execute().data or []
        all_tenants = {r["tenantid"]: r for r in t_rows}

    # projects — 내 모든 테넌트의 프로젝트
    pu_rows = sb.schema(SUPABASE_SCHEMA).table("projectusers").select("projectid,rolecd").eq("useruid", user_id).execute().data or []
    project_users = []
    if pu_rows and my_tenantids:
        proj_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid,projectnm,tenantid").in_("tenantid", my_tenantids).execute().data or []
        proj_map = {p["projectid"]: p for p in proj_rows}
        for pu in pu_rows:
            pid = pu.get("projectid")
            proj = proj_map.get(pid)
            if proj:
                tid = proj["tenantid"]
                project_users.append({
                    "projectid": pid,
                    "projectnm": proj["projectnm"],
                    "rolecd": pu.get("rolecd"),
                    "tenantid": tid,
                    "tenantnm": all_tenants.get(tid, {}).get("tenantnm", ""),
                    "tenant_rolecd": tu_map.get(tid, {}).get("rolecd"),
                })

    # timezones 목록 (useyn=true)
    tz_rows = sb.schema(SUPABASE_SCHEMA).table("timezones").select("timezone").eq("useyn", True).execute().data or []
    timezones = [r["timezone"] for r in tz_rows]

    # 유효 timezone: tenantusers → tenants 순으로 fallback
    effective_timezone = tenantuser.get("timezone") or tenant.get("timezone") or None

    # tenant.createdts timezone 적용 포맷
    offsetminutes = _get_offsetminutes(sb, str(user_id), tenantid)
    if tenant.get("createdts"):
        tenant["createdts"] = _fmt_dt(tenant["createdts"], offsetminutes)

    return {
        "user_info": user_info,
        "tenantuser": tenantuser,
        "tenant": tenant,
        "project_users": project_users,
        "timezones": timezones,
        "timezone": effective_timezone,
    }


class UpdateUsernameRequest(BaseModel):
    usernm: str


@router.post("/myinfo/username")
def update_username(body: UpdateUsernameRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("users").update({"usernm": body.usernm}).eq("useruid", user.id).execute()
    return {"status": "ok"}


class UpdateTimezoneRequest(BaseModel):
    timezone: Optional[str] = None


@router.get("/myinfo/subscriptions")
def get_myinfo_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    # issystemtenant 에 따라 accountuid 조회 기준 분기
    accountuid = None
    if tenantid:
        t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
        issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True
        if issystemtenant:
            acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
        else:
            acc = svc.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()
        if acc and acc.data:
            accountuid = acc.data["accountuid"]

    if not accountuid:
        return {"subscriptions": []}

    svcs = svc.table("accountservices").select(
        "productcd,plancd,servicecd,servicestatus"
    ).eq("accountuid", accountuid).eq("servicestatus", "Active").execute()
    if not svcs.data:
        return {"subscriptions": []}

    # servicecd 정렬 순서 — codes 테이블 orderno 기준
    code_order = svc.table("codes").select("codevalue,orderno").eq(
        "codegroupcd", "servicecd"
    ).execute().data or []
    order_map = {r["codevalue"]: r.get("orderno", 999) for r in code_order}

    productcds = [s["productcd"] for s in svcs.data]
    prods = svc.table("products").select("productcd,productnm").in_("productcd", productcds).execute()
    name_map = {p["productcd"]: p.get("productnm", p["productcd"]) for p in (prods.data or [])}

    sorted_svcs = sorted(svcs.data, key=lambda s: order_map.get(s.get("servicecd", ""), 999))

    return {
        "subscriptions": [
            {
                "productcd": s["productcd"],
                "productnm": name_map.get(s["productcd"], s["productcd"]),
                "plancd": s.get("plancd", ""),
                "servicecd": s.get("servicecd", ""),
            }
            for s in sorted_svcs
        ]
    }


@router.get("/upgrade-products")
def get_upgrade_products(
    servicecd: str,
    plancd: str = "Pr",
    token: str = Depends(get_token),
):
    """업그레이드 플랜 상품 목록 — servicecd + plancd 기준, orderno 정렬."""
    _get_user(token)
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    rows = (
        svc.table("products")
        .select("productcd,productnm,plancd,servicecd,billingtermcd,users,credit,is_customeraikey,orderno,useyn")
        .eq("servicecd", servicecd)
        .eq("plancd", plancd)
        .eq("useyn", True)
        .order("orderno")
        .execute()
        .data or []
    )
    return {"products": rows}


class UpgradePlanRequest(BaseModel):
    productcd: str
    servicecd: str


@router.post("/upgrade-plan")
def upgrade_plan(
    body: UpgradePlanRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """Free → Pro 업그레이드: subscriptions / accountservices / subscription_credits / creditbuckets 처리."""
    from datetime import datetime, timezone, timedelta
    from dateutil.relativedelta import relativedelta

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    # tenantid & accountuid 조회
    if not tenantid:
        tu = svc.table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).maybe_single().execute()
        if not tu.data:
            raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
        tenantid = str(tu.data["tenantid"])

    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True
    if issystemtenant:
        acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = svc.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()
    if not acc or not acc.data:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")
    accountuid = acc.data["accountuid"]

    # 선택한 product 조회
    prod_row = svc.table("products").select(
        "productcd,plancd,servicecd,billingtermcd,users,credit,is_customeraikey"
    ).eq("productcd", body.productcd).maybe_single().execute()
    if not prod_row.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    product = prod_row.data

    # [과거_sub] 조회 — accountuid & servicecd 기반 최신 Paid subscription
    past_rows = svc.table("subscriptions").select(
        "subscriptionuid,productcd,plancd"
    ).eq("accountuid", accountuid).eq("servicecd", body.servicecd).eq(
        "subscription_status", "Paid"
    ).order("createdts", desc=True).limit(1).execute().data or []
    if not past_rows:
        raise HTTPException(status_code=404, detail="기존 구독 정보를 찾을 수 없습니다.")
    past_sub = past_rows[0]

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    # ① subscriptions 신규 행 삽입 ([갱신_sub])
    new_sub_resp = svc.table("subscriptions").insert({
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "productcd": product["productcd"],
        "plancd": product["plancd"],
        "servicecd": product["servicecd"],
        "billingtermcd": product.get("billingtermcd"),
        "old_productcd": past_sub["productcd"],
        "subscription_status": "Paid",
        "creator": user_id,
    }).execute()
    if not new_sub_resp.data:
        raise HTTPException(status_code=500, detail="구독 저장에 실패했습니다.")
    new_sub = new_sub_resp.data[0]
    new_subscriptionuid = new_sub["subscriptionuid"]

    # ② accountservices 기존 행 갱신
    svc.table("accountservices").update({
        "old_subscriptionuid": past_sub["subscriptionuid"],
        "old_productcd": past_sub["productcd"],
        "old_plancd": past_sub["plancd"],
        "subscriptionuid": new_subscriptionuid,
        "productcd": product["productcd"],
        "plancd": product["plancd"],
        "is_customerAIKey": product.get("is_customeraikey", False),
        "billingfirstdt": today.isoformat(),
        "billingday": today.day,
        "included_users": 1,
        "add_users": 0,
        "total_users": 1,
        "is_autotopup": False,
        "creator": user_id,
    }).eq("accountuid", accountuid).eq("servicecd", body.servicecd).execute()

    # ③ subscription_credits 신규 행 삽입
    svc.table("subscription_credits").insert({
        "subscriptionuid": new_subscriptionuid,
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "productcd": product["productcd"],
        "servicecd": product["servicecd"],
        "quantity": product.get("credit", 0),
        "credittypecd": "SC",
        "creditdesc": "Subscription Credit",
        "creator": user_id,
    }).execute()

    # ④ creditbuckets — [과거_sub] 기존 행 만료 처리 (status 컬럼이 없어 expiredts를 현재 시각으로 당겨서 만료시킴)
    svc.table("creditbuckets").update({
        "expiredts": now_utc.isoformat(),
    }).eq("subscriptionuid", past_sub["subscriptionuid"]).execute()

    # creditbuckets 신규 행 삽입
    expiredts = (today + relativedelta(months=1) - timedelta(days=1)).isoformat()
    svc.table("creditbuckets").insert({
        "subscriptionuid": new_subscriptionuid,
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "servicecd": product["servicecd"],
        "chargecredit": product.get("credit", 0),
        "creditchargecd": "Ba",
        "priorityno": 1,
        "usecredit": 0,
        "remaincredit": product.get("credit", 0),
        "granteddts": now_utc.isoformat(),
        "expiredts": expiredts,
        "startdt": today.isoformat(),
    }).execute()

    return {"result": "success", "message": "업그레이드가 완료되었습니다."}


# ══════════════════════════════════════════════════════
#  TENANT MANAGE — 구독 관리 (좌: 현재 구독 / 우: Team·Enterprise 상품 선택)
# ══════════════════════════════════════════════════════

def _get_tenant_and_account(svc, user_id: str, tenantid: Optional[str]) -> tuple[str, Optional[str]]:
    """tenantid와 accountuid를 반환."""
    if not tenantid:
        tu = svc.table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).maybe_single().execute()
        if not tu.data:
            raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
        tenantid = str(tu.data["tenantid"])

    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True

    if issystemtenant:
        acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = svc.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()

    accountuid = str(acc.data["accountuid"]) if acc and acc.data else None
    return tenantid, accountuid


@router.get("/tenant-manage/subscriptions")
def get_tenant_manage_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """구독 관리 화면 좌측: 서비스별 현재 구독 상품 목록."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    _, accountuid = _get_tenant_and_account(svc, user_id, tenantid)

    # 전체 서비스 목록 — 아직 구독하지 않은 서비스도 선택 가능하도록 항상 포함
    service_codes = (
        svc.table("codes").select("codevalue,orderno")
        .eq("codegroupcd", "servicecd").eq("useyn", True).order("orderno").execute().data or []
    )

    if not accountuid:
        return {
            "subscriptions": [
                {
                    "servicecd": c["codevalue"], "productcd": None, "productnm": None,
                    "plancd": None, "billingtermcd": None, "users": None, "credit": None,
                    "servicestatus": None,
                }
                for c in service_codes
            ],
            "accountuid": None,
        }

    rows = (
        svc.table("accountservices")
        .select("servicecd,productcd,plancd,servicestatus")
        .eq("accountuid", accountuid)
        .execute()
        .data or []
    )
    row_map = {r["servicecd"]: r for r in rows}

    productcds = [r["productcd"] for r in rows if r.get("productcd")]
    prods = (
        svc.table("products").select("productcd,productnm,billingtermcd,users,credit")
        .in_("productcd", productcds).execute().data or []
    ) if productcds else []
    prod_map = {p["productcd"]: p for p in prods}

    result = []
    for c in service_codes:
        scd = c["codevalue"]
        r = row_map.get(scd)
        if not r:
            result.append({
                "servicecd": scd, "productcd": None, "productnm": None,
                "plancd": None, "billingtermcd": None, "users": None, "credit": None,
                "servicestatus": None,
            })
            continue
        p = prod_map.get(r.get("productcd"), {})
        result.append({
            "servicecd": scd,
            "productcd": r.get("productcd"),
            "productnm": p.get("productnm", r.get("productcd")),
            "plancd": r.get("plancd"),
            "billingtermcd": p.get("billingtermcd"),
            "users": p.get("users"),
            "credit": p.get("credit"),
            "servicestatus": r.get("servicestatus"),
        })

    return {"subscriptions": result, "accountuid": accountuid}


@router.get("/tenant-manage/team-products")
def get_tenant_manage_team_products(servicecd: str, token: str = Depends(get_token)):
    """구독 관리 화면 우측: 선택한 서비스의 Team/Enterprise 상품 목록."""
    _get_user(token)
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    rows = (
        svc.table("products")
        .select("productcd,productnm,plancd,servicecd,billingtermcd,users,credit,is_customeraikey,orderno")
        .eq("servicecd", servicecd)
        .eq("producttype", "Service")
        .in_("plancd", ["Te", "En"])
        .eq("useyn", True)
        .order("orderno")
        .execute()
        .data or []
    )
    return {"products": rows}


class SubscriptionChangeRequest(BaseModel):
    servicecd: str
    productcd: str


@router.post("/tenant-manage/subscription-change")
def change_tenant_subscription(
    body: SubscriptionChangeRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """구독 관리 화면: 선택한 상품으로 구독 변경.

    결제 연동 전까지는 저장 즉시 accountservices에 반영한다.
    추후 결제 게이트가 추가되면 결제 성공 콜백에서 이 로직을 호출하도록 변경해야 한다.
    """
    from datetime import datetime, timezone as tz, timedelta as td
    from dateutil.relativedelta import relativedelta

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    prod_row = svc.table("products").select(
        "productcd,plancd,servicecd,billingtermcd,users,credit,is_customeraikey"
    ).eq("productcd", body.productcd).maybe_single().execute()
    if not prod_row.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    product = prod_row.data

    cur_row = svc.table("accountservices").select(
        "subscriptionuid,productcd,plancd"
    ).eq("accountuid", accountuid).eq("servicecd", body.servicecd).maybe_single().execute()
    current = cur_row.data if cur_row else {}  # 없으면 해당 서비스 신규 구독

    now_utc = datetime.now(tz.utc)
    today = now_utc.date()

    new_sub_resp = svc.table("subscriptions").insert({
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "productcd": product["productcd"],
        "plancd": product["plancd"],
        "servicecd": product["servicecd"],
        "billingtermcd": product.get("billingtermcd"),
        "old_productcd": current.get("productcd"),
        "subscription_status": "Paid",
        "creator": user_id,
    }).execute()
    if not new_sub_resp.data:
        raise HTTPException(status_code=500, detail="구독 저장에 실패했습니다.")
    new_subscriptionuid = new_sub_resp.data[0]["subscriptionuid"]

    users = product.get("users") or 1
    accountservices_payload = {
        "old_subscriptionuid": current.get("subscriptionuid"),
        "old_productcd": current.get("productcd"),
        "old_plancd": current.get("plancd"),
        "subscriptionuid": new_subscriptionuid,
        "productcd": product["productcd"],
        "plancd": product["plancd"],
        "is_customerAIKey": product.get("is_customeraikey", False),
        "billingfirstdt": today.isoformat(),
        "billingday": today.day,
        "included_users": users,
        "add_users": 0,
        "total_users": users,
        "is_autotopup": False,
        "creator": user_id,
    }
    if current:
        svc.table("accountservices").update(accountservices_payload).eq(
            "accountuid", accountuid
        ).eq("servicecd", body.servicecd).execute()
    else:
        # 해당 서비스 최초 구독 — accountservices 신규 행 생성
        svc.table("accountservices").insert({
            **accountservices_payload,
            "accountuid": accountuid,
            "servicecd": body.servicecd,
            "tenantid": int(tenantid),
            "servicestatus": "Active",
            "is_postpaid": False,
        }).execute()

    svc.table("subscription_credits").insert({
        "subscriptionuid": new_subscriptionuid,
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "productcd": product["productcd"],
        "servicecd": product["servicecd"],
        "quantity": product.get("credit", 0),
        "credittypecd": "SC",
        "creditdesc": "Subscription Credit",
        "creator": user_id,
    }).execute()

    if current.get("subscriptionuid"):
        svc.table("creditbuckets").update({
            "expiredts": now_utc.isoformat(),
        }).eq("subscriptionuid", current["subscriptionuid"]).execute()

    expiredts = (today + relativedelta(months=1) - td(days=1)).isoformat()
    svc.table("creditbuckets").insert({
        "subscriptionuid": new_subscriptionuid,
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "servicecd": product["servicecd"],
        "chargecredit": product.get("credit", 0),
        "creditchargecd": "Ba",
        "priorityno": 1,
        "usecredit": 0,
        "remaincredit": product.get("credit", 0),
        "granteddts": now_utc.isoformat(),
        "expiredts": expiredts,
        "startdt": today.isoformat(),
    }).execute()

    return {"result": "success", "message": "구독이 변경되었습니다."}


@router.get("/tenant-manage/lang-timezone")
def get_tenant_manage_lang_timezone(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """구독 관리 화면 좌측: 테넌트 전체 기본 언어·타임존 조회."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, _ = _get_tenant_and_account(svc, user_id, tenantid)

    t_row = svc.table("tenants").select("languagecd,timezone").eq("tenantid", int(tenantid)).maybe_single().execute()
    tenant = t_row.data if t_row else {}

    langs = svc.table("languages").select("languagecd,languagenm").order("languagenm").execute().data or []
    timezones = [r["timezone"] for r in (svc.table("timezones").select("timezone").eq("useyn", True).execute().data or [])]

    return {
        "languagecd": tenant.get("languagecd"),
        "timezone": tenant.get("timezone"),
        "languages": langs,
        "timezones": timezones,
    }


class TenantLangTimezoneRequest(BaseModel):
    languagecd: Optional[str] = None
    timezone: Optional[str] = None


@router.post("/tenant-manage/lang-timezone")
def update_tenant_manage_lang_timezone(
    body: TenantLangTimezoneRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """구독 관리 화면 좌측: 테넌트 전체 기본 언어·타임존 저장."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, _ = _get_tenant_and_account(svc, user_id, tenantid)

    payload = {}
    if body.languagecd:
        payload["languagecd"] = body.languagecd
    if body.timezone:
        payload["timezone"] = body.timezone
    if not payload:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다.")

    svc.table("tenants").update(payload).eq("tenantid", int(tenantid)).execute()
    return {"result": "success"}


@router.get("/tenant-manage/other-subscriptions")
def get_tenant_manage_other_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """기타 구독 관리 화면: 보유 중인 User/Feature 상품 + 구매 가능 상품 목록."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)

    subscribed_servicecds = set()
    owned_productcds = set()
    if accountuid:
        subscribed_servicecds = {
            r["servicecd"] for r in (
                svc.table("accountservices").select("servicecd").eq("accountuid", accountuid).execute().data or []
            )
        }
        owned_productcds = {
            r["productcd"] for r in (
                svc.table("account_features").select("productcd").eq("accountuid", accountuid).execute().data or []
            )
        }

    all_products = (
        svc.table("products").select(
            "productcd,productnm,servicecd,producttype,users,billingtermcd,orderno"
        )
        .in_("producttype", ["User", "Feature"])
        .eq("useyn", True)
        .order("orderno")
        .execute().data or []
    )
    prod_map = {p["productcd"]: p for p in all_products}
    # User 타입은 구독 중인 서비스의 상품만 노출 (Feature는 서비스 무관, 반복 구매 가능)
    # Feature 타입은 취소 전까지 1회만 구독 가능 — 이미 보유 중이면 목록에서 제외
    products = [
        p for p in all_products
        if not (p["producttype"] == "Feature" and p["productcd"] in owned_productcds)
        and (p["producttype"] == "Feature" or p["servicecd"] in subscribed_servicecds)
    ]

    owned = []
    if accountuid:
        offsetminutes = _get_offsetminutes(get_service_client(), user_id, tenantid)
        rows = (
            svc.table("subscription_features").select("subscriptionuid,productcd,createdts")
            .eq("accountuid", accountuid).eq("subscriptionstatus", "Paid")
            .order("createdts").execute().data or []
        )
        for r in rows:
            p = prod_map.get(r["productcd"], {})
            owned.append({
                "subscriptionuid": r["subscriptionuid"],
                "productcd": r["productcd"],
                "productnm": p.get("productnm", r["productcd"]),
                "servicecd": p.get("servicecd"),
                "producttype": p.get("producttype"),
                "users": p.get("users"),
                "createdts": _fmt_dt(r.get("createdts"), offsetminutes),
                "orderno": p.get("orderno", 999),
            })
        owned.sort(key=lambda o: o["orderno"])

    return {"owned": owned, "products": products, "accountuid": accountuid}


class OtherSubscriptionPurchaseRequest(BaseModel):
    productcd: str


@router.post("/tenant-manage/other-subscription-purchase")
def purchase_tenant_manage_other_subscription(
    body: OtherSubscriptionPurchaseRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """기타 구독 관리 화면: User/Feature 상품 구매.

    결제 연동 전까지는 저장 즉시 accountservices/account_features에 반영한다.
    Credit(producttype='Credit') 구매는 이번 범위에서 제외한다.
    """
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    prod_row = svc.table("products").select(
        "productcd,productnm,servicecd,producttype,users,useyn"
    ).eq("productcd", body.productcd).maybe_single().execute()
    product = prod_row.data if prod_row else None
    if not product or product.get("producttype") not in ("User", "Feature"):
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    if product["producttype"] == "Feature":
        existing_feature = svc.table("account_features").select("accountuid").eq(
            "accountuid", accountuid
        ).eq("productcd", product["productcd"]).maybe_single().execute()
        if existing_feature and existing_feature.data:
            raise HTTPException(status_code=400, detail="이미 구독 중인 기능입니다.")

    accsvc = None
    if product["producttype"] == "User":
        svcrow = svc.table("accountservices").select(
            "included_users,add_users"
        ).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).maybe_single().execute()
        accsvc = svcrow.data if svcrow else None
        if not accsvc:
            raise HTTPException(status_code=400, detail="먼저 해당 서비스를 구독해야 합니다.")

    svc.table("subscription_features").insert({
        "subscriptionuid": str(uuid.uuid4()),
        "productcd": product["productcd"],
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "quantity": 1,
        "subscriptionstatus": "Paid",
        "creator": user_id,
    }).execute()

    existing_af = svc.table("account_features").select("accountuid").eq(
        "accountuid", accountuid
    ).eq("productcd", product["productcd"]).maybe_single().execute()
    if existing_af and existing_af.data:
        svc.table("account_features").update({
            "updater": user_id,
            "updatedts": datetime.now(tz.utc).isoformat(),
        }).eq("accountuid", accountuid).eq("productcd", product["productcd"]).execute()
    else:
        svc.table("account_features").insert({
            "accountuid": accountuid,
            "productcd": product["productcd"],
            "tenantid": int(tenantid),
            "creator": user_id,
        }).execute()

    if product["producttype"] == "User":
        new_add_users = (accsvc.get("add_users") or 0) + (product.get("users") or 0)
        new_total_users = (accsvc.get("included_users") or 0) + new_add_users
        svc.table("accountservices").update({
            "add_users": new_add_users,
            "total_users": new_total_users,
            "updater": user_id,
        }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()

    return {"result": "success"}


class OtherSubscriptionCancelRequest(BaseModel):
    subscriptionuid: str
    cancel_reasoncd: str
    cancel_reasondesc: Optional[str] = None


@router.post("/tenant-manage/other-subscription-cancel")
def cancel_tenant_manage_other_subscription(
    body: OtherSubscriptionCancelRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """기타 구독 관리 화면: User/Feature 구매 건 취소."""
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    sf_row = svc.table("subscription_features").select(
        "subscriptionuid,productcd,accountuid,subscriptionstatus"
    ).eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    sf = sf_row.data if sf_row else None
    if not sf or sf.get("accountuid") != accountuid:
        raise HTTPException(status_code=404, detail="구독 내역을 찾을 수 없습니다.")
    if sf.get("subscriptionstatus") == "Cancelled":
        raise HTTPException(status_code=400, detail="이미 취소된 구독입니다.")

    prod_row = svc.table("products").select(
        "productcd,servicecd,producttype,users"
    ).eq("productcd", sf["productcd"]).maybe_single().execute()
    product = prod_row.data if prod_row else {}

    now_utc = datetime.now(tz.utc)
    svc.table("subscription_features").update({
        "subscriptionstatus": "Cancelled",
        "canceluseruid": user_id,
        "canceldts": now_utc.isoformat(),
        "cancel_reasoncd": body.cancel_reasoncd,
        "cancel_reasondesc": body.cancel_reasondesc,
        "updater": user_id,
        "updatedts": now_utc.isoformat(),
    }).eq("subscriptionuid", body.subscriptionuid).execute()

    if product.get("producttype") == "User" and product.get("servicecd"):
        svcrow = svc.table("accountservices").select(
            "included_users,add_users"
        ).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).maybe_single().execute()
        accsvc = svcrow.data if svcrow else None
        if accsvc:
            new_add_users = max((accsvc.get("add_users") or 0) - (product.get("users") or 0), 0)
            new_total_users = (accsvc.get("included_users") or 0) + new_add_users
            svc.table("accountservices").update({
                "add_users": new_add_users,
                "total_users": new_total_users,
                "updater": user_id,
            }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()

    remaining = svc.table("subscription_features").select("subscriptionuid").eq(
        "accountuid", accountuid
    ).eq("productcd", sf["productcd"]).eq("subscriptionstatus", "Paid").execute().data or []
    if not remaining:
        svc.table("account_features").delete().eq("accountuid", accountuid).eq("productcd", sf["productcd"]).execute()

    return {"result": "success"}


@router.get("/tenant-manage/credit-subscriptions")
def get_tenant_manage_credit_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """크레딧 구매 관리 화면: 구매 내역 + 구매 가능 크레딧 상품 목록."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)

    subscribed_servicecds = set()
    if accountuid:
        subscribed_servicecds = {
            r["servicecd"] for r in (
                svc.table("accountservices").select("servicecd").eq("accountuid", accountuid).execute().data or []
            )
        }

    all_products = (
        svc.table("products").select(
            "productcd,productnm,servicecd,producttype,credit,expiremonths,orderno"
        )
        .eq("producttype", "Credit")
        .eq("useyn", True)
        .order("orderno")
        .execute().data or []
    )
    prod_map = {p["productcd"]: p for p in all_products}
    # 구독 중인 서비스의 크레딧 상품만 노출
    products = [p for p in all_products if p["servicecd"] in subscribed_servicecds]

    owned = []
    if accountuid:
        offsetminutes = _get_offsetminutes(get_service_client(), user_id, tenantid)
        rows = (
            svc.table("subscription_credits").select("subscriptionuid,productcd,quantity,createdts,expiresdts")
            .eq("accountuid", accountuid).eq("credittypecd", "MT")
            .is_("canceldts", "null")
            .order("createdts").execute().data or []
        )
        for r in rows:
            p = prod_map.get(r["productcd"], {})
            owned.append({
                "subscriptionuid": r["subscriptionuid"],
                "productcd": r["productcd"],
                "productnm": p.get("productnm", r["productcd"]),
                "servicecd": p.get("servicecd"),
                "quantity": r.get("quantity"),
                "createdts": _fmt_dt(r.get("createdts"), offsetminutes),
                "expiresdts": _fmt_dt(r.get("expiresdts"), offsetminutes),
                "orderno": p.get("orderno", 999),
            })
        owned.sort(key=lambda o: o["orderno"])

    return {"owned": owned, "products": products, "accountuid": accountuid}


class CreditSubscriptionPurchaseRequest(BaseModel):
    productcd: str


@router.post("/tenant-manage/credit-subscription-purchase")
def purchase_tenant_manage_credit_subscription(
    body: CreditSubscriptionPurchaseRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """크레딧 구매 관리 화면: 크레딧 상품 구매.

    결제 연동 전까지는 저장 즉시 subscription_credits에 반영한다.
    creditbuckets(실사용 가능 잔여크레딧) 반영은 이번 범위에서 제외한다.
    """
    from datetime import datetime, timezone as tz
    from dateutil.relativedelta import relativedelta

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    prod_row = svc.table("products").select(
        "productcd,productnm,servicecd,producttype,credit,expiremonths"
    ).eq("productcd", body.productcd).maybe_single().execute()
    product = prod_row.data if prod_row else None
    if not product or product.get("producttype") != "Credit":
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    if product.get("servicecd"):
        svcrow = svc.table("accountservices").select("servicecd").eq(
            "accountuid", accountuid
        ).eq("servicecd", product["servicecd"]).maybe_single().execute()
        if not svcrow or not svcrow.data:
            raise HTTPException(status_code=400, detail="먼저 해당 서비스를 구독해야 합니다.")

    now_utc = datetime.now(tz.utc)
    expiremonths = product.get("expiremonths")
    expiresdts = (now_utc + relativedelta(months=expiremonths)).isoformat() if expiremonths else None

    svc.table("subscription_credits").insert({
        "subscriptionuid": str(uuid.uuid4()),
        "credittypecd": "MT",
        "creditdesc": product.get("productnm"),
        "productcd": product["productcd"],
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "quantity": product.get("credit") or 0,
        "expiresdts": expiresdts,
        "creator": user_id,
    }).execute()

    return {"result": "success"}


@router.get("/tenant-manage/overview")
def get_tenant_manage_overview(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """전체 현황 화면: 서비스별 프로젝트/인원/크레딧 현황 + 테넌트 총 인원."""
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)

    total_users = len(
        svc.table("tenantusers").select("useruid").eq("tenantid", int(tenantid)).eq("useyn", True).execute().data or []
    )

    services = []
    if accountuid:
        accsvc_rows = (
            svc.table("accountservices").select("servicecd,total_users")
            .eq("accountuid", accountuid).execute().data or []
        )
        svc_map = {r["servicecd"]: {"servicecd": r["servicecd"], "total_users": r.get("total_users") or 0} for r in accsvc_rows}

        proj_rows = (
            svc.table("projects").select("servicecd")
            .eq("accountuid", accountuid).eq("useyn", True).execute().data or []
        )
        project_counts = {}
        for r in proj_rows:
            project_counts[r["servicecd"]] = project_counts.get(r["servicecd"], 0) + 1

        su_rows = (
            svc.table("serviceusers").select("servicecd")
            .eq("accountuid", accountuid).eq("useyn", True).execute().data or []
        )
        used_user_counts = {}
        for r in su_rows:
            used_user_counts[r["servicecd"]] = used_user_counts.get(r["servicecd"], 0) + 1

        now_utc = datetime.now(tz.utc)
        cb_rows = (
            svc.table("creditbuckets").select("servicecd,chargecredit,usecredit,remaincredit,expiredts")
            .eq("accountuid", accountuid).gt("expiredts", now_utc.isoformat()).execute().data or []
        )
        credit_totals = {}
        for r in cb_rows:
            scd = r["servicecd"]
            c = credit_totals.setdefault(scd, {"total_credit": 0, "used_credit": 0, "remain_credit": 0})
            c["total_credit"] += r.get("chargecredit") or 0
            c["used_credit"] += r.get("usecredit") or 0
            c["remain_credit"] += r.get("remaincredit") or 0

        for scd, s in svc_map.items():
            credit = credit_totals.get(scd, {"total_credit": 0, "used_credit": 0, "remain_credit": 0})
            services.append({
                "servicecd": scd,
                "projects": project_counts.get(scd, 0),
                "total_users": s["total_users"],
                "used_users": used_user_counts.get(scd, 0),
                "total_credit": credit["total_credit"],
                "used_credit": credit["used_credit"],
                "remain_credit": credit["remain_credit"],
            })
        services.sort(key=lambda s: s["servicecd"])

    return {
        "total_users": total_users,
        "services": services,
    }


# ══════════════════════════════════════════════════════
#  TENANT SUBSCRIPTION (신규 테넌트 셀프 생성)
# ══════════════════════════════════════════════════════

@router.get("/tenant-subscription/init")
def get_tenant_subscription_init(
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """신규 테넌트 생성 화면 초기값 — languages/timezones 목록 + 현재 tenantuser의 languagecd/timezone 기본값."""
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    tu_row = {}
    if tenantid:
        tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("languagecd,timezone").eq("useruid", user_id).eq("tenantid", tenantid).maybe_single().execute()
        tu_row = tu.data or {}
    if not tu_row:
        tu_rows = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("languagecd,timezone").eq("useruid", user_id).eq("useyn", True).limit(1).execute().data or []
        tu_row = tu_rows[0] if tu_rows else {}

    languages = sb.schema(SUPABASE_SCHEMA).table("languages").select("languagecd,languagenm").eq("useyn", True).order("orderno").execute().data or []
    timezones = [r["timezone"] for r in (sb.schema(SUPABASE_SCHEMA).table("timezones").select("timezone").eq("useyn", True).execute().data or [])]

    return {
        "languages": languages,
        "timezones": timezones,
        "default_languagecd": tu_row.get("languagecd"),
        "default_timezone": tu_row.get("timezone"),
    }


class TenantSubscriptionRequest(BaseModel):
    tenantnm: str
    languagecd: Optional[str] = None
    timezone: Optional[str] = None


@router.post("/tenant-subscription")
def create_tenant_subscription(body: TenantSubscriptionRequest, token: str = Depends(get_token)):
    """신규 테넌트 셀프 생성: tenants(useyn=true) / tenantusers(rolecd=M) / accounts(accounttype=T) 동시 생성."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenant_data = {
        "tenantnm": body.tenantnm,
        "useyn": True,
        "issystemtenant": False,
        "creator": user_id,
    }
    if body.languagecd:
        tenant_data["languagecd"] = body.languagecd
    if body.timezone:
        tenant_data["timezone"] = body.timezone

    tenant_resp = svc.table("tenants").insert(tenant_data).execute()
    if not tenant_resp.data:
        raise HTTPException(status_code=500, detail="테넌트 저장에 실패했습니다.")
    new_tenantid = tenant_resp.data[0]["tenantid"]

    tenantuser_data = {
        "tenantid": new_tenantid,
        "useruid": user_id,
        "rolecd": "M",
        "useyn": True,
        "creator": user_id,
    }
    if body.languagecd:
        tenantuser_data["languagecd"] = body.languagecd
    if body.timezone:
        tenantuser_data["timezone"] = body.timezone
    svc.table("tenantusers").insert(tenantuser_data).execute()

    svc.table("accounts").insert({
        "accounttype": "T",
        "tenantid": new_tenantid,
        "accountstatus": "Active",
        "creator": user_id,
    }).execute()

    return {"tenantid": new_tenantid, "tenantnm": body.tenantnm}


@router.post("/myinfo/timezone")
def update_timezone(body: UpdateTimezoneRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").update({"timezone": body.timezone}).eq("useruid", user.id)
    if tenantid:
        q = q.eq("tenantid", tenantid)
    q.execute()
    offsetminutes = None
    if body.timezone:
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", body.timezone).maybe_single().execute()
        if tz_row.data:
            offsetminutes = tz_row.data.get("offsetminutes")
    return {"status": "ok", "offsetminutes": offsetminutes}
