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

    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        if row.get("creator"):
            try:
                u = sb.schema(SUPABASE_SCHEMA).table("users").select("usernm").eq("useruid", row["creator"]).execute().data
                row["creatornm"] = u[0]["usernm"] if u else ""
            except Exception:
                row["creatornm"] = ""

    langs = sb.schema(SUPABASE_SCHEMA).table("languages").select("languagecd, languagenm").order("languagenm").execute().data or []
    timezones = [r["timezone"] for r in (sb.schema(SUPABASE_SCHEMA).table("timezones").select("*").eq("useyn", True).execute().data or [])]
    return {"tenants": rows, "languages": langs, "timezones": timezones}


@router.post("/tenants")
async def save_tenant(
    tenantid: Optional[str] = Form(None),
    tenantnm: str = Form(...),
    useyn: str = Form("true"),
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
    offsetminutes = _get_offsetminutes(sb, str(user_id))
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
