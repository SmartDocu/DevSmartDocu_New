"""Settings router — Servers, Projects, Tenants, MyInfo"""
import json
import os
import uuid
from datetime import date, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, status
from postgrest.utils import sanitize_param
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client
from utilsPrj.credit_helper import CREDITCHARGECD_PRIORITY, upsert_ba_creditbucket, offset_negative_ba_bucket
from utilsPrj.notifications import create_notification
from utilsPrj.user_lookup import get_usernm_email
from utilsPrj.audit_log import log_work_action, snapshot_row, get_client_ip
from utilsPrj.private_storage import (
    resolve_user_accountuid, build_private_path, upload_private_file,
    delete_private_file, is_private_path, resolve_display_url,
)
from backend.app.routers.admin import _require_admin

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


def _save_tenant_icon(sb_service, file: UploadFile, accountuid: str, existing_url: Optional[str] = None) -> tuple:
    """기업 아이콘을 private storage(Users/{accountuid}/Master/tenant-icon/...)에 업로드하고 (파일명, 경로)를 반환."""
    if existing_url:
        if is_private_path(existing_url):
            delete_private_file(sb_service, existing_url)
        else:
            try:
                parsed = urlparse(existing_url)
                prefix = "/storage/v1/object/public/d2doc/"
                if prefix in parsed.path:
                    sb_service.storage.from_("d2doc").remove([parsed.path.split(prefix)[-1]])
            except Exception:
                pass
    ext = os.path.splitext(file.filename)[1]
    storage_path = build_private_path(accountuid, "Master", "tenant-icon", f"{uuid.uuid4()}{ext}")
    upload_private_file(sb_service, storage_path, file.file.read(), file.content_type)
    return file.filename, storage_path


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


_SERVER_SAFE_FIELDS = (
    "connuid", "connnm", "conntype", "dbtype", "server", "port", "db", "ssl_mode",
    "service_name", "sid", "tns", "timeout", "retry_count", "desc", "useyn",
    "tenantid", "creator", "createdts",
)


def _snapshot_server(sb, connuid: Optional[str]) -> Optional[dict]:
    """비밀번호/자격증명(secret_path)은 감사로그에 남기지 않음."""
    if not connuid:
        return None
    row = sb.schema(SUPABASE_SCHEMA).table("connectors").select(",".join(_SERVER_SAFE_FIELDS)).eq("connuid", connuid).execute().data
    return row[0] if row else None


@router.post("/servers")
def save_server(body: ServerSaveRequest, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    from utilsPrj.secrets_cache import save_connector_secret

    user = _get_user(token)
    sb = _sb(token)
    before = _snapshot_server(sb, body.connuid)

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
            log_work_action(
                useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
                actioncd="update", targettype="settings/servers", targetid=body.connuid,
                before=before, after=_snapshot_server(sb, body.connuid),
                ip=get_client_ip(request),
            )
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
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="create", targettype="settings/servers", targetid=connuid,
        after=_snapshot_server(sb, connuid),
        ip=get_client_ip(request),
    )
    return {"status": "inserted"}


@router.delete("/servers/{connuid}")
def delete_server(connuid: str, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    from utilsPrj.secrets_cache import delete_connector_secret

    user = _get_user(token)
    sb = _sb(token)

    in_use = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("datauid", count="exact").eq("connuid", connuid)
        .execute()
    )
    if (in_use.count or 0) > 0:
        raise HTTPException(status_code=400, detail="msg.server.in.use")

    before = _snapshot_server(sb, connuid)
    existing = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("secret_path").eq("connuid", connuid).execute().data
    )
    if existing and (existing[0].get("secret_path") or "") == "aws-sm":
        delete_connector_secret(tenantid, connuid)

    sb.schema(SUPABASE_SCHEMA).table("connectors").delete().eq("connuid", connuid).execute()
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="delete", targettype="settings/servers", targetid=connuid, before=before,
        ip=get_client_ip(request),
    )
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
        nm, _ = get_usernm_email(sb, row.get("creator"))
        row["creatornm"] = nm

    return {"projects": rows, "tenantnm": tenantnm}


class ProjectSaveRequest(BaseModel):
    projectid: Optional[str] = None
    projectnm: str
    projectdesc: Optional[str] = None
    useyn: bool = True
    servicecd: Optional[str] = None
    accountuid: Optional[str] = None


@router.post("/projects")
def save_project(body: ProjectSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    # 신규 생성 시 플랜 제한 체크
    is_new = not body.projectid
    if is_new and body.accountuid and body.servicecd:
        svc = sb.schema(SUPABASE_SCHEMA).table("accountservices") \
            .select("plancd").eq("accountuid", body.accountuid).eq("servicecd", body.servicecd) \
            .maybe_single().execute()
        plancd = svc.data.get("plancd") if svc and svc.data else None
        if plancd:
            cfg = sb.schema(SUPABASE_SCHEMA).table("config_plans") \
                .select("value").eq("configcd", "project_limit").eq("plancd", plancd).eq("servicecd", body.servicecd) \
                .maybe_single().execute()
            limit = int(cfg.data["value"]) if cfg and cfg.data and cfg.data.get("value") else None
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
    # 전체 테넌트 목록(복호화된 연락처 포함)이라 시스템 관리자(roleid=7)만 접근 가능해야 한다
    admin = _require_admin(token)
    sb = _sb(token)

    rows = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").order("createdts", desc=True).execute().data or []

    tenantids = [row["tenantid"] for row in rows if row.get("tenantid")]
    account_map = {}
    if tenantids:
        svc = get_service_client().schema(SUPABASE_SCHEMA)
        acc_rows = svc.table("accounts").select("tenantid, encemail, enctelno").in_("tenantid", tenantids).execute().data or []
        account_map = {a["tenantid"]: a for a in acc_rows}

    svc_client = get_service_client()
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"))
        nm, _ = get_usernm_email(sb, row.get("creator"))
        row["creatornm"] = nm
        acc = account_map.get(row.get("tenantid"))
        row["decemail"] = _decrypt(acc.get("encemail")) if acc else ""
        row["dectelno"] = _decrypt(acc.get("enctelno")) if acc else ""
        row["iconfileurl"] = resolve_display_url(svc_client, row.get("iconfileurl"))

    langs = sb.schema(SUPABASE_SCHEMA).table("languages").select("languagecd, languagenm").eq("useyn", True).order("languagenm").execute().data or []
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
    if existing and existing.data:
        svc.table("accounts").update(payload).eq("tenantid", tenantid).execute()
    else:
        payload.update({
            "accounttype": "T",
            "tenantid": tenantid,
            "accountstatus": "Active",
            "creator": creator,
        })
        svc.table("accounts").insert(payload).execute()


def _save_default_tenant_configs(tenantid: int, creator: str):
    """테넌트 생성 시 config_tenants 기본값을 심는다.

    MFA는 2026-08-25부터 시스템 테넌트를 제외한 개별(조직) 테넌트에 기본 제공(무료)으로 전환됐지만,
    생성 시점엔 항상 비활성 상태로 시작하고 테넌트 매니저가 /tenant-manage/mfa-config에서
    직접 켜고 끈다(더 이상 구매/취소 흐름이 아님 — products.mfa는 is_sales=False로 판매 카탈로그에서 제외됨).
    IP Whitelist/SSO는 계속 opt-in(구매 필요, 기본 False) 유지.
    """
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    rows = [
        {"tenantid": tenantid, "configcd": configcd, "value": False, "creator": creator}
        for configcd in ("Is_MFA", "Is_User_IP_Allow", "Is_Manager_IP_Allow", "Is_SSO_MS")
    ]
    svc.table("config_tenants").insert(rows).execute()


@router.post("/tenants")
async def save_tenant(
    request: Request,
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
    # 테넌트 생성/수정은 시스템 관리자(roleid=7)만 가능해야 한다
    user = _require_admin(token)
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
        existing = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", tenantid).execute().data
        if existing:
            svc_root = get_service_client()
            # 아이콘 업로드 전에 accounts row 존재를 보장해야 accountuid를 해석할 수 있다
            _save_tenant_contact(int(tenantid), email, telno, str(user.id))
            if iconfile and iconfile.filename:
                existing_url = existing[0].get("iconfileurl")
                accountuid = resolve_user_accountuid(svc_root, int(tenantid), str(user.id))
                if not accountuid:
                    raise HTTPException(status_code=400, detail="msg.required.account")
                icon_nm, icon_url = _save_tenant_icon(svc_root, iconfile, accountuid, existing_url)
                tenant_data["iconfilenm"] = icon_nm
                tenant_data["iconfileurl"] = icon_url
            sb.schema(SUPABASE_SCHEMA).table("tenants").update(tenant_data).eq("tenantid", tenantid).execute()
            after = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", tenantid).execute().data
            log_work_action(
                useruid=str(user.id), tenantid=int(tenantid), servicecd="Tenant",
                actioncd="update", targettype="settings/tenants", targetid=tenantid,
                before=existing[0], after=after[0] if after else None,
                ip=get_client_ip(request),
            )
            return {"status": "updated"}

    resp = sb.schema(SUPABASE_SCHEMA).table("tenants").insert({**tenant_data, "disptenantnm": tenantnm}).execute()
    new_tenantid = resp.data[0]["tenantid"] if resp.data else None
    if new_tenantid:
        svc_root = get_service_client()
        # 아이콘 업로드 전에 accounts row 존재를 보장해야 accountuid를 해석할 수 있다
        _save_tenant_contact(int(new_tenantid), email, telno, str(user.id))
        if iconfile and iconfile.filename:
            accountuid = resolve_user_accountuid(svc_root, int(new_tenantid), str(user.id))
            if not accountuid:
                raise HTTPException(status_code=400, detail="msg.required.account")
            icon_nm, icon_url = _save_tenant_icon(svc_root, iconfile, accountuid)
            sb.schema(SUPABASE_SCHEMA).table("tenants").update({
                "iconfilenm": icon_nm,
                "iconfileurl": icon_url,
            }).eq("tenantid", new_tenantid).execute()
        _save_default_tenant_configs(int(new_tenantid), str(user.id))
    after = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", new_tenantid).execute().data if new_tenantid else []
    log_work_action(
        useruid=str(user.id), tenantid=new_tenantid, servicecd="Tenant",
        actioncd="create", targettype="settings/tenants", targetid=new_tenantid,
        after=after[0] if after else None,
        ip=get_client_ip(request),
    )
    return {"status": "inserted"}


@router.delete("/tenants/{tenantid}")
def delete_tenant(tenantid: str, request: Request, token: str = Depends(get_token)):
    # 테넌트 삭제는 시스템 관리자(roleid=7)만 가능해야 한다
    user = _require_admin(token)
    sb = _sb(token)
    before = sb.schema(SUPABASE_SCHEMA).table("tenants").select("*").eq("tenantid", tenantid).execute().data
    sb.schema(SUPABASE_SCHEMA).table("tenants").delete().eq("tenantid", tenantid).execute()
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="delete", targettype="settings/tenants", targetid=tenantid,
        before=before[0] if before else None,
        ip=get_client_ip(request),
    )
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
    # offsetminutes는 _get_offsetminutes()를 다시 부르지 않고 위에서 이미 구한
    # effective_timezone으로 timezones 테이블만 1회 조회해서 구한다 — _get_offsetminutes가
    # 내부적으로 tenantusers/tenants를 처음부터 다시 조회하는 중복을 없앤 것.
    # (아주 드문 edge case: 현재 선택된 tenantid의 tenantuser 행이 useyn=False면
    # _get_offsetminutes는 그 행도 찾아 timezone을 썼지만, 여기 재사용하는
    # effective_timezone은 useyn=True인 tu_rows 기준이라 그 행을 건너뛴다 —
    # 비활성 소속 테넌트를 현재 테넌트로 선택할 수 없는 정상 흐름에서는 발생하지 않음.)
    offsetminutes = None
    if effective_timezone:
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes") \
            .eq("timezone", effective_timezone).maybe_single().execute()
        offsetminutes = tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None

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


@router.get("/myinfo-v2")
def get_myinfo_v2(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """get_myinfo()의 RPC 버전 — sdoc.fn_myinfo() 하나로 계산을 DB에서 끝내고
    API 왕복을 1회로 줄인다(myinfo_v2_rpc.sql 참고).

    get_myinfo()는 전부 sb(사용자 JWT)로 조회하는데, sb의 HTTP 클라이언트에는
    프로세스 전역 락이 걸려 있어(utilsPrj/supabase_client.py) 병렬화가 통하지
    않는다 — 그래서 병렬화 대신 RPC로 왕복 자체를 줄이는 방식을 택했다.

    ⚠ 검증 전용 엔드포인트. 화면은 아직 이걸 쓰지 않는다 — GET /myinfo와 같은
    조건(X-Tenant-ID)으로 호출해 응답이 동일한지 비교해본 뒤에만 전환할 것.
    myinfo_v2_rpc.sql을 Supabase에서 먼저 실행해 함수를 생성해야 동작한다.
    """
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    result = svc.rpc("fn_myinfo", {
        "p_user_id": user_id,
        "p_tenantid": int(tenantid) if tenantid else None,
    }).execute().data or {}

    offsetminutes = result.get("offsetminutes")
    tenant = result.get("tenant") or {}
    if tenant.get("createdts"):
        tenant["createdts"] = _fmt_dt(tenant["createdts"], offsetminutes)

    return {
        "user_info": result.get("user_info") or {},
        "tenantuser": result.get("tenantuser") or {},
        "tenant": tenant,
        "project_users": result.get("project_users") or [],
        "timezones": result.get("timezones") or [],
        "timezone": result.get("timezone"),
    }


class UpdateUsernameRequest(BaseModel):
    usernm: str


@router.post("/myinfo/username")
def update_username(body: UpdateUsernameRequest, request: Request, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    before = sb.schema(SUPABASE_SCHEMA).table("users").select("usernm").eq("useruid", user.id).maybe_single().execute()
    sb.schema(SUPABASE_SCHEMA).table("users").update({"usernm": body.usernm}).eq("useruid", user.id).execute()
    log_work_action(
        useruid=str(user.id), servicecd="Tenant",
        actioncd="update", targettype="settings/myinfo/username", targetid=str(user.id),
        before=before.data if before else None, after={"usernm": body.usernm},
        ip=get_client_ip(request),
    )
    return {"status": "ok"}


class UpdateMarketingRequest(BaseModel):
    marketingyn: str


@router.post("/myinfo/marketing")
def update_marketing(body: UpdateMarketingRequest, request: Request, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    before = sb.schema(SUPABASE_SCHEMA).table("users").select("marketingyn").eq("useruid", user.id).maybe_single().execute()
    sb.schema(SUPABASE_SCHEMA).table("users").update({"marketingyn": body.marketingyn}).eq("useruid", user.id).execute()
    log_work_action(
        useruid=str(user.id), servicecd="Tenant",
        actioncd="update", targettype="settings/myinfo/marketing", targetid=str(user.id),
        before=before.data if before else None, after={"marketingyn": body.marketingyn},
        ip=get_client_ip(request),
    )
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
        issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True
        if issystemtenant:
            acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
        else:
            acc = svc.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()
        if acc and acc.data:
            accountuid = acc.data["accountuid"]

    if not accountuid:
        return {"subscriptions": []}

    # 예약된 Pro 해지 중 이번 결제 주기가 끝난 건이 있으면 Free로 자동 전환(또는 Archived로 전이) 후 조회
    _apply_due_pro_downgrades(svc, accountuid)
    _apply_due_pro_archival(svc, accountuid)

    svcs = svc.table("accountservices").select(
        "productcd,plancd,servicecd,servicestatus,subscriptionuid"
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

    sub_ids = [s["subscriptionuid"] for s in svcs.data if s.get("subscriptionuid")]
    cancel_map = {}
    bucket_map = {}
    if sub_ids:
        cancel_rows = svc.table("subscriptions").select("subscriptionuid,canceldts").in_(
            "subscriptionuid", sub_ids
        ).execute().data or []
        cancel_map = {r["subscriptionuid"]: r.get("canceldts") for r in cancel_rows}

        bucket_rows = svc.table("creditbuckets").select("subscriptionuid,expiredts").in_(
            "subscriptionuid", sub_ids
        ).eq("creditchargecd", "Ba").execute().data or []
        bucket_map = {r["subscriptionuid"]: r.get("expiredts") for r in bucket_rows}

    offsetminutes = _get_offsetminutes(get_service_client(), user_id, tenantid)
    sorted_svcs = sorted(svcs.data, key=lambda s: order_map.get(s.get("servicecd", ""), 999))

    return {
        "subscriptions": [
            {
                "productcd": s["productcd"],
                "productnm": name_map.get(s["productcd"], s["productcd"]),
                "plancd": s.get("plancd", ""),
                "servicecd": s.get("servicecd", ""),
                "cancel_reserved": bool(cancel_map.get(s.get("subscriptionuid"))),
                "cancel_effective_date": (
                    _fmt_dt(bucket_map.get(s.get("subscriptionuid")), offsetminutes)
                    if cancel_map.get(s.get("subscriptionuid")) else None
                ),
            }
            for s in sorted_svcs
        ]
    }


@router.get("/myinfo/usage")
def get_myinfo_usage(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    servicecd: str = "Do",
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """로그인한 사용자 본인의 생성 사용량.

    - servicecd: 조회 대상 서비스. creditbuckets는 서비스 공통 구조라 그대로 필터링하면 되지만,
      daily/totals/credit_history는 genobjects/gendocs/genchapters 등 Do 서비스 전용 테이블에서
      나오는 값이라 servicecd != "Do"인 경우 해당 서비스의 생성 로직이 아직 없으므로 빈 값을 반환한다.
    - daily/totals: 문서 생성/챕터 생성은 genobjectlogs 기준 일자별 건수.
      genobjectlogs는 objectuid 단위 로그라 문서/챕터 생성 1건에 여러 행이 남는다.
      문서 생성은 gendocjobuid, 챕터 단독 생성(재작성 포함)은 genchapterjobuid 기준으로
      distinct 처리해 '실행 횟수'로 집계한다.
      날짜는 doc/chapter의 경우 gendoclogs/genchapterlogs.logdts(실제 완료 시점, 해당 job의
      최신값)로 재확정한다.
      단일 항목 재작성은 genobjectcounts(creator 컬럼 2026-08-17 추가)에서 시간당+인원별로
      이미 정확히 집계된 count를 그대로 합산한다 — genobjectlogs로 직접 세면 액션 1건당
      로그가 여러 줄 남는 문제(트리거/재upsert로 인한 중복)가 있어 부정확했음.
      genobjectcounts.creator는 2026-08-17 이전 데이터는 값이 없거나 부정확할 수 있다.
    - credit: 계정(테넌트) 공용 Do 서비스 크레딧 현황(충전/사용/잔여, 충전유형별) — 모든 인원 공통.
    - credit_history: creditbucketuses 중 본인(creator)이 생성한 문서/챕터로 인해 차감된 건 +
      본인의 genobjectcount_historys(단일 항목 재작성 배치 크레딧 차감, usetypecd='do')로 차감된
      건을 합친 개인 사용 내역. genobjectcounts는 sdoc.fn_apply_genobjectcount_credit()
      배치가 처리해야 genobjectcount_historys로 넘어가고 creditbucketuses가 생기므로,
      배치가 아직 안 돌았으면(is_applied=false로 남아있으면) 여기 안 잡힌다.
    """
    from datetime import datetime
    from concurrent.futures import ThreadPoolExecutor

    if not tenantid:
        return {"daily": [], "totals": {"doc_count": 0, "chapter_count": 0, "object_count": 0, "total": 0},
                "start_date": start_date, "end_date": end_date, "credit": None, "credit_history": []}

    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    today = datetime.now(timezone.utc).date()
    sd = start_date or (today - timedelta(days=29)).strftime("%Y-%m-%d")
    ed = end_date or today.strftime("%Y-%m-%d")
    offsetminutes = _get_offsetminutes(sb, user_id, tenantid)

    if offsetminutes is not None:
        sd_utc = datetime.strptime(sd, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(minutes=offsetminutes)
        ed_utc = datetime.strptime(ed, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1) - timedelta(minutes=offsetminutes)
    else:
        sd_utc = datetime.strptime(sd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        ed_utc = datetime.strptime(ed, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)

    # creditbuckets/creditbucketuses/genchapterlogs/gendoclogs는 RLS상 일반 인원이 못 볼 수 있어
    # service client 사용. 조회 범위는 반드시 아래에서 직접 accountuid/creator/jobuid로 좁힌다.
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    def _svc():
        # 병렬 조회(아래 ThreadPoolExecutor)에서는 client를 스레드 간에 공유하지 않도록
        # 태스크마다 새로 생성한다 — get_service_client()는 매 호출마다 새 client를 만들어
        # 반환하므로(전역 락 없음) worker 스레드 코드(chapter_making.py 등)와 동일한 방식.
        return get_service_client().schema(SUPABASE_SCHEMA)

    def _local_date(raw):
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d")

    def _in_range(raw):
        if not raw:
            return False
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return sd_utc <= dt < ed_utc

    def _in_list(values):
        return ",".join(sanitize_param(v) for v in values)

    # ── 1단계: 서로 의존관계 없는 조회 6개를 병렬로 실행(직렬이면 왕복 6회) ──
    # sb(get_thread_supabase)는 내부적으로 전역 락(_http_lock)으로 요청을 직렬화하지만
    # (utilsPrj/supabase_client.py 참고) 이 6개 중 sb를 쓰는 건 genobjectlogs 하나뿐이라
    # 이 엔드포인트 내부의 병렬 처리 효과에는 영향이 없다.
    def _fetch_genobjectlogs():
        if servicecd != "Do":
            return []
        return sb.schema(SUPABASE_SCHEMA).table("genobjectlogs").select(
            "createdts,gendocjobuid,genchapterjobuid"
        ).eq("creator", user_id).eq("tenantid", int(tenantid)).eq("is_success", True) \
            .gte("createdts", sd_utc.isoformat()).lt("createdts", ed_utc.isoformat()).execute().data or []

    def _fetch_genobjectcounts():
        if servicecd != "Do":
            return []
        return _svc().table("genobjectcounts").select("usedts,count") \
            .eq("tenantid", int(tenantid)).eq("creator", user_id) \
            .gte("usedts", sd_utc.isoformat()).lt("usedts", ed_utc.isoformat()).execute().data or []

    def _fetch_chap_rows():
        if servicecd != "Do":
            return []
        return _svc().table("genchapters").select("genchapteruid,chapteruid") \
            .eq("creator", user_id).eq("tenantid", int(tenantid)).execute().data or []

    def _fetch_doc_rows():
        if servicecd != "Do":
            return []
        return _svc().table("gendocs").select("gendocuid,gendocnm") \
            .eq("creator", user_id).eq("tenantid", int(tenantid)).execute().data or []

    def _fetch_oc_hist_rows():
        if servicecd != "Do":
            return []
        return _svc().table("genobjectcount_historys").select("countuid,logdts") \
            .eq("creator", user_id).eq("tenantid", int(tenantid)) \
            .gte("logdts", sd_utc.isoformat()).lt("logdts", ed_utc.isoformat()).execute().data or []

    def _fetch_account():
        return _get_tenant_and_account(_svc(), user_id, tenantid)

    with ThreadPoolExecutor(max_workers=6) as ex:
        fut_rows = ex.submit(_fetch_genobjectlogs)
        fut_oc_rows = ex.submit(_fetch_genobjectcounts)
        fut_chap_rows = ex.submit(_fetch_chap_rows)
        fut_doc_rows = ex.submit(_fetch_doc_rows)
        fut_oc_hist_rows = ex.submit(_fetch_oc_hist_rows)
        fut_account = ex.submit(_fetch_account)

        rows = fut_rows.result()
        oc_rows = fut_oc_rows.result()
        chap_rows = fut_chap_rows.result()
        doc_rows = fut_doc_rows.result()
        oc_hist_rows = fut_oc_hist_rows.result()
        _, accountuid = fut_account.result()

    # 본인이 생성한 챕터/문서 목록 — 아래 날짜 재확정과, 뒤쪽 credit_history 계산 양쪽에서 재사용
    # (예전엔 credit_history 쪽에서 동일 조회를 한 번 더 했었음 — 중복 제거).
    chapteruids = [c["genchapteruid"] for c in chap_rows]
    docuids = [d["gendocuid"] for d in doc_rows]
    chap_by_uid = {c["genchapteruid"]: c for c in chap_rows}
    doc_by_uid = {d["gendocuid"]: d for d in doc_rows}
    chapter_ids = list({c["chapteruid"] for c in chap_rows if c.get("chapteruid")})

    doc_jobs = {}      # gendocjobuid -> 가장 이른 로컬 날짜
    chapter_jobs = {}  # genchapterjobuid -> 가장 이른 로컬 날짜 (gendocjobuid 없는 것만 = 챕터 단독)
    for r in rows:
        d = _local_date(r.get("createdts"))
        gdju = r.get("gendocjobuid")
        gcju = r.get("genchapterjobuid")
        if gdju:
            if gdju not in doc_jobs or d < doc_jobs[gdju]:
                doc_jobs[gdju] = d
        elif gcju:
            if gcju not in chapter_jobs or d < chapter_jobs[gcju]:
                chapter_jobs[gcju] = d
        # gdju/gcju 둘 다 없는 행(단일 항목 재작성)은 여기선 무시 — genobjectcounts(creator 포함,
        # 2026-08-17 추가)가 이미 시간당+인원별로 정확히 집계해주므로 아래에서 그걸 직접 쓴다.
        # genobjectlogs로 직접 세면 액션 1건당 로그가 여러 줄 남는 문제가 있어 부정확했음.

    # 단일 항목 재작성 — genobjectcounts에서 creator+tenantid로 직접 집계(시간 버킷 → 로컬 날짜 합산)
    object_by_date = {}
    for r in oc_rows:
        d = _local_date(r.get("usedts"))
        object_by_date[d] = object_by_date.get(d, 0) + (r.get("count") or 0)
    object_total = sum(object_by_date.values())

    # ── 2단계: 1단계 결과에 의존하는 조회 4개를 다시 병렬로 실행 ──
    # gendoclogs/genchapterlogs는 "날짜 재확정"(job id 기준)과 뒤쪽 credit_history(문서/챕터
    # 소유 + is_credituse + 기간 기준) 양쪽에 필요해서, OR로 묶어 테이블당 한 번만 조회한다.
    # servicecd != "Do"면 doc_jobs/chapter_jobs/docuids/chapteruids/chapter_ids가 모두 비어있어
    # gdl/gcl/chapternm 조회는 실제 네트워크 호출 없이 빈 리스트를 반환한다.
    def _fetch_gdl_rows():
        or_parts = []
        if doc_jobs:
            or_parts.append(f"gendocjobuid.in.({_in_list(doc_jobs.keys())})")
        if docuids:
            or_parts.append(
                f"and(gendocuid.in.({_in_list(docuids)}),is_credituse.eq.true,"
                f"logdts.gte.{sd_utc.isoformat()},logdts.lt.{ed_utc.isoformat()})"
            )
        if not or_parts:
            return []
        return _svc().table("gendoclogs").select("loguid,gendocjobuid,gendocuid,logdts,is_credituse") \
            .or_(",".join(or_parts)).execute().data or []

    def _fetch_gcl_rows():
        or_parts = []
        if chapter_jobs:
            or_parts.append(f"genchapterjobuid.in.({_in_list(chapter_jobs.keys())})")
        if chapteruids:
            or_parts.append(
                f"and(genchapteruid.in.({_in_list(chapteruids)}),is_credituse.eq.true,"
                f"logdts.gte.{sd_utc.isoformat()},logdts.lt.{ed_utc.isoformat()})"
            )
        if not or_parts:
            return []
        return _svc().table("genchapterlogs").select("loguid,genchapterjobuid,genchapteruid,logdts,is_credituse") \
            .or_(",".join(or_parts)).execute().data or []

    def _fetch_bucket_rows():
        if not accountuid:
            return []
        now_iso = datetime.now(timezone.utc).isoformat()
        return _svc().table("creditbuckets").select(
            "creditchargecd,chargecredit,usecredit,remaincredit,granteddts,expiredts,startdt"
        ).eq("accountuid", accountuid).eq("servicecd", servicecd).gt("expiredts", now_iso) \
            .order("priorityno").execute().data or []

    def _fetch_chapternm_rows():
        if not chapter_ids:
            return []
        return _svc().table("chapters").select("chapteruid,chapternm").in_("chapteruid", chapter_ids).execute().data or []

    with ThreadPoolExecutor(max_workers=4) as ex:
        fut_gdl = ex.submit(_fetch_gdl_rows)
        fut_gcl = ex.submit(_fetch_gcl_rows)
        fut_bucket = ex.submit(_fetch_bucket_rows)
        fut_chapternm = ex.submit(_fetch_chapternm_rows)

        gdl_rows = fut_gdl.result()
        gcl_rows = fut_gcl.result()
        bucket_rows = fut_bucket.result()
        nm_rows = fut_chapternm.result()

    if doc_jobs:
        latest = {}
        for r in gdl_rows:
            jid, ld = r.get("gendocjobuid"), r.get("logdts")
            if jid and jid in doc_jobs and ld and (jid not in latest or ld > latest[jid]):
                latest[jid] = ld
        for jid, ld in latest.items():
            doc_jobs[jid] = _local_date(ld)

    if chapter_jobs:
        latest = {}
        for r in gcl_rows:
            jid, ld = r.get("genchapterjobuid"), r.get("logdts")
            if jid and jid in chapter_jobs and ld and (jid not in latest or ld > latest[jid]):
                latest[jid] = ld
        for jid, ld in latest.items():
            chapter_jobs[jid] = _local_date(ld)

    if servicecd == "Do":
        daily_map = {}

        def _bump(date_str, key, amount=1):
            e = daily_map.setdefault(date_str, {"date": date_str, "doc_count": 0, "chapter_count": 0, "object_count": 0})
            e[key] += amount

        for d in doc_jobs.values():
            _bump(d, "doc_count")
        for d in chapter_jobs.values():
            _bump(d, "chapter_count")
        for d, cnt in object_by_date.items():
            _bump(d, "object_count", cnt)

        daily = sorted(daily_map.values(), key=lambda x: x["date"])
        for e in daily:
            e["total"] = e["doc_count"] + e["chapter_count"] + e["object_count"]

        totals = {
            "doc_count": len(doc_jobs),
            "chapter_count": len(chapter_jobs),
            "object_count": object_total,
        }
        totals["total"] = totals["doc_count"] + totals["chapter_count"] + totals["object_count"]
    else:
        # servicecd != "Do" — 생성 활동 로그가 아직 없는 서비스라 건수 집계는 비워서 반환한다.
        daily = []
        totals = {"doc_count": 0, "chapter_count": 0, "object_count": 0, "total": 0}

    # ── 크레딧 현황(계정 공용) + 본인 소모 내역 ──────────────────────────────
    credit = None
    credit_history = []

    if accountuid:
        for b in bucket_rows:
            b["expiredts"] = _fmt_dt(b.get("expiredts"), offsetminutes)
            b["granteddts"] = _fmt_dt(b.get("granteddts"), offsetminutes)

        credit = {
            "buckets": bucket_rows,
            "total_charge": sum(b.get("chargecredit") or 0 for b in bucket_rows),
            "total_use": sum(b.get("usecredit") or 0 for b in bucket_rows),
            "total_remain": sum(b.get("remaincredit") or 0 for b in bucket_rows),
        }

        # credit_history는 genchapters/gendocs(Do 서비스 전용 테이블) 기준이라
        # 다른 서비스에는 해당 데이터 자체가 없다 — servicecd == "Do"일 때만 계산한다.
        if servicecd == "Do":
            # 본인이 생성한 챕터/문서만 대상 (단일 항목 재작성은 크레딧 미차감이라 대상 아님)
            # 날짜는 부모(genchapters/gendocs)의 createdts/createfiledts가 아니라
            # genchapterlogs/gendoclogs.logdts를 쓴다 — credit_helper._apply_credit_deduction에서
            # creditbucketuses.refuid로 쓰이는 로그가 바로 이 logdts 기준 최종 로그이므로
            # "실제 크레딧이 차감된 시점"에 가장 가깝다. 기간(sd_utc~ed_utc) 필터도 이 값으로 건다.
            # chap_rows/doc_rows/gcl_rows/gdl_rows/nm_rows는 위 1·2단계에서 이미 조회해둔 것을
            # 그대로 재사용한다(중복 조회 제거) — 아래에서 is_credituse/기간 조건만 다시 건다.
            loguid_map = {}  # loguid -> {"kind": doc/chapter, "name": ..., "date": raw logdts}
            chapternm_map = {r["chapteruid"]: r.get("chapternm") for r in nm_rows}

            if chapteruids:
                for r in gcl_rows:
                    if r.get("is_credituse") is not True or not _in_range(r.get("logdts")):
                        continue
                    chap = chap_by_uid.get(r.get("genchapteruid"))
                    if not chap:
                        continue
                    loguid_map[r["loguid"]] = {
                        "kind": "chapter",
                        "name": chapternm_map.get(chap.get("chapteruid")) or "",
                        "date": r.get("logdts"),
                    }

            if docuids:
                for r in gdl_rows:
                    if r.get("is_credituse") is not True or not _in_range(r.get("logdts")):
                        continue
                    doc = doc_by_uid.get(r.get("gendocuid"))
                    if not doc:
                        continue
                    loguid_map[r["loguid"]] = {
                        "kind": "doc",
                        "name": doc.get("gendocnm") or "",
                        "date": r.get("logdts"),
                    }

            # 단일 항목 재작성 배치 크레딧 차감 내역 — genobjectcounts가 처리되면
            # genobjectcount_historys로 이관되며(sdoc.fn_apply_genobjectcount_credit),
            # creditbucketuses.refuid에는 그 countuid가 usetypecd='do'로 기록된다.
            for r in oc_hist_rows:
                loguid_map[r["countuid"]] = {
                    "kind": "object",
                    "name": "",
                    "date": r.get("logdts"),
                }

            if loguid_map:
                use_rows = svc.table("creditbucketuses").select(
                    "refuid,usetypecd,beforecredit,usecredit,aftercredit"
                ).eq("accountuid", accountuid).in_("refuid", list(loguid_map.keys())).execute().data or []

                for u in use_rows:
                    meta = loguid_map.get(u.get("refuid"), {})
                    credit_history.append({
                        "date_raw": meta.get("date") or "",
                        "date": _fmt_dt(meta.get("date"), offsetminutes),
                        "kind": meta.get("kind"),
                        "name": meta.get("name") or "",
                        "beforecredit": u.get("beforecredit"),
                        "usecredit": u.get("usecredit"),
                        "aftercredit": u.get("aftercredit"),
                    })

                credit_history.sort(key=lambda x: x["date_raw"], reverse=True)
                for h in credit_history:
                    del h["date_raw"]

    return {"daily": daily, "totals": totals, "start_date": sd, "end_date": ed,
            "credit": credit, "credit_history": credit_history}


@router.get("/myinfo/usage-v2")
def get_myinfo_usage_v2(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    servicecd: str = "Do",
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """get_myinfo_usage()의 RPC 버전 — sdoc.fn_myinfo_usage() 하나로 계산을 DB에서
    끝내고 API 왕복을 1회로 줄인다(myusage_v2_rpc.sql 참고).

    ⚠ 검증 전용 엔드포인트. 화면은 아직 이걸 쓰지 않는다 — GET /myinfo/usage와
    같은 파라미터로 호출해 응답이 동일한지 비교해본 뒤에만 전환할 것.
    myusage_v2_rpc.sql을 Supabase에서 먼저 실행해 함수를 생성해야 동작한다.
    """
    if not tenantid:
        return {"daily": [], "totals": {"doc_count": 0, "chapter_count": 0, "object_count": 0, "total": 0},
                "start_date": start_date, "end_date": end_date, "credit": None, "credit_history": []}

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    result = svc.rpc("fn_myinfo_usage", {
        "p_user_id": user_id,
        "p_tenantid": int(tenantid),
        "p_servicecd": servicecd,
        "p_start_date": start_date,
        "p_end_date": end_date,
    }).execute().data or {}

    offsetminutes = result.get("offsetminutes")
    accountuid = result.get("accountuid")
    daily = result.get("daily") or []
    totals = result.get("totals") or {"doc_count": 0, "chapter_count": 0, "object_count": 0, "total": 0}

    credit = None
    credit_history = []

    if accountuid:
        buckets = result.get("credit_buckets") or []
        for b in buckets:
            b["expiredts"] = _fmt_dt(b.get("expiredts"), offsetminutes)
            b["granteddts"] = _fmt_dt(b.get("granteddts"), offsetminutes)

        credit = {
            "buckets": buckets,
            "total_charge": sum(b.get("chargecredit") or 0 for b in buckets),
            "total_use": sum(b.get("usecredit") or 0 for b in buckets),
            "total_remain": sum(b.get("remaincredit") or 0 for b in buckets),
        }

        # RPC에서 이미 logdts DESC로 정렬해서 내려준다.
        for h in result.get("credit_history") or []:
            credit_history.append({
                "date": _fmt_dt(h.get("date"), offsetminutes),
                "kind": h.get("kind"),
                "name": h.get("name") or "",
                "beforecredit": h.get("beforecredit"),
                "usecredit": h.get("usecredit"),
                "aftercredit": h.get("aftercredit"),
            })

    return {"daily": daily, "totals": totals, "start_date": result.get("sd"), "end_date": result.get("ed"),
            "credit": credit, "credit_history": credit_history}


@router.get("/upgrade-products")
def get_upgrade_products(
    servicecd: str,
    plancd: str = "Pr",
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """업그레이드 플랜 상품 목록 — servicecd + plancd 기준, orderno 정렬.

    Free/Pro(개인 계정용 플랜)는 systemtenant가 아니면 선택할 수 없다.
    """
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    if plancd in ("Fr", "Pr"):
        _, issystemtenant = _get_tenant_and_issystemtenant(svc, user_id, tenantid)
        if not issystemtenant:
            return {"products": []}

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
    _attach_prices(svc, rows, currencycd=_get_user_currencycd(svc, user_id, tenantid))
    return {"products": rows}


class UpgradePlanRequest(BaseModel):
    productcd: str
    servicecd: str


@router.post("/upgrade-plan")
def upgrade_plan(
    body: UpgradePlanRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """Free → Pro 업그레이드: subscriptions / accountservices / creditbuckets 처리.

    등록된 결제수단으로 상품 가격만큼 실제(테스트 채널 기준) 청구 후에만 반영한다.
    """
    from datetime import datetime, timezone, timedelta
    from dateutil.relativedelta import relativedelta

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    # tenantid & accountuid 조회
    tenantid, issystemtenant = _get_tenant_and_issystemtenant(svc, user_id, tenantid)
    if issystemtenant:
        acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = svc.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()
    if not acc or not acc.data:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")
    accountuid = acc.data["accountuid"]

    # 선택한 product 조회
    prod_row = svc.table("products").select(
        "productcd,productnm,plancd,servicecd,billingtermcd,users,credit,is_customeraikey"
    ).eq("productcd", body.productcd).maybe_single().execute()
    if not prod_row or not prod_row.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    product = prod_row.data

    # Free/Pro(개인 계정용 플랜)는 systemtenant가 아니면 선택할 수 없다.
    if not issystemtenant and product.get("plancd") in ("Fr", "Pr"):
        raise HTTPException(status_code=400, detail="Free/Pro 플랜은 선택할 수 없습니다.")

    # [과거_sub] 조회 — accountuid & servicecd 기반 최신 subscription. subscription_status는 이제
    # 정기 청구 실패 시 PastDue/Suspended로도 바뀌므로(payments.py의 _handle_billing_failure 참고),
    # "Paid"로 필터하면 결제 실패 중인 계정이 플랜을 다시 바꾸려 할 때 여기서 404로 막혀버린다 —
    # 상태와 무관하게 이 서비스의 가장 최근 구독 행을 찾는다.
    past_rows = svc.table("subscriptions").select(
        "subscriptionuid,productcd,plancd"
    ).eq("accountuid", accountuid).eq("servicecd", body.servicecd).order(
        "createdts", desc=True
    ).limit(1).execute().data or []
    if not past_rows:
        raise HTTPException(status_code=404, detail="기존 구독 정보를 찾을 수 없습니다.")
    past_sub = past_rows[0]

    _prev_accountservices_row = (
        svc.table("accountservices").select("*").eq("accountuid", accountuid).eq("servicecd", body.servicecd).maybe_single().execute()
    )
    previous_accountservices = (_prev_accountservices_row.data if _prev_accountservices_row else None)

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    account_billing = _lookup_account_billing(svc, accountuid)
    full_price = _get_current_price(svc, product["productcd"], product.get("billingtermcd"))
    if full_price is None:
        raise HTTPException(status_code=400, detail="가격 정보가 없어 구매할 수 없습니다.")
    charge_amount = (
        _calc_prorated_amount(full_price, today, date.fromisoformat(account_billing["next_billing_dt"]))
        if account_billing else full_price
    )

    charge_result = _require_payment_and_charge(
        svc, user_id, tenantid, accountuid, product["productcd"], product.get("billingtermcd"),
        product.get("productnm") or product["productcd"], override_amount=charge_amount,
    )

    # 결제는 이미 성공했으므로, 이 아래(구독 반영) 단계에서 무엇이 실패하든
    # (1) 이미 반영한 변경을 되돌리고 (2) 결제를 자동 환불한다.
    subscription_inserted = False
    accountservices_updated = False
    account_billing_bootstrapped = False
    new_subscriptionuid = None
    try:
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
            raise RuntimeError("구독 저장에 실패했습니다.")
        new_sub = new_sub_resp.data[0]
        new_subscriptionuid = new_sub["subscriptionuid"]
        subscription_inserted = True

        # ② accountservices 기존 행 갱신
        svc.table("accountservices").update({
            "old_subscriptionuid": past_sub["subscriptionuid"],
            "old_productcd": past_sub["productcd"],
            "old_plancd": past_sub["plancd"],
            "subscriptionuid": new_subscriptionuid,
            "productcd": product["productcd"],
            "plancd": product["plancd"],
            "is_customerAIKey": product.get("is_customeraikey", False),
            "billingfirstdt": (account_billing.get("last_billed_dt") or today.isoformat()) if account_billing else today.isoformat(),
            "billingday": account_billing["billingday"] if account_billing else today.day,
            "included_users": 1,
            "add_users": 0,
            "total_users": 1,
            "is_autotopup": False,
            "creator": user_id,
        }).eq("accountuid", accountuid).eq("servicecd", body.servicecd).execute()
        accountservices_updated = True

        if not account_billing:
            _bootstrap_account_billing(svc, accountuid, tenantid, user_id, today)
            account_billing_bootstrapped = True

        # ③ creditbuckets — 기존 Ba 버킷이 있으면 잔여 크레딧 병합 후 creditbucket_historys로 이관, 신규 Ba 버킷 발급
        # (Ba는 subscription_credits에 넣지 않는다 — Ba 갱신 여부는 subscriptions.subscription_status로만 판단)
        # 제품 구독으로 부여되는 크레딧의 만료일은 통합 결제일(다음 재청구일 전날)에 맞춘다 —
        # 그래야 다음 통합 청구 시점에 크레딧도 같이 갱신되어 "월 사용량 리셋"이 결제일과 어긋나지 않는다.
        _next_bill_dt = date.fromisoformat(account_billing["next_billing_dt"]) if account_billing else _next_billing_date(today.day, today)
        expiredts = (_next_bill_dt - timedelta(days=1)).isoformat()
        upsert_ba_creditbucket(
            svc,
            subscriptionuid=new_subscriptionuid,
            tenantid=int(tenantid),
            accountuid=accountuid,
            servicecd=product["servicecd"],
            chargecredit=product.get("credit", 0),
            granteddts=now_utc.isoformat(),
            expiredts=expiredts,
            startdt=today.isoformat(),
        )
    except Exception as e:
        if account_billing_bootstrapped:
            svc.table("account_billing").delete().eq("accountuid", accountuid).execute()
        if accountservices_updated and previous_accountservices:
            svc.table("accountservices").update(previous_accountservices).eq("accountuid", accountuid).eq("servicecd", body.servicecd).execute()
        if subscription_inserted:
            svc.table("subscriptions").delete().eq("subscriptionuid", new_subscriptionuid).execute()
        _compensate_and_raise(svc, user_id, charge_result, e, context="업그레이드")

    after_row = svc.table("accountservices").select("*").eq("accountuid", accountuid).eq("servicecd", body.servicecd).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="update", targettype="settings/upgrade-plan", targetid=accountuid,
        before=previous_accountservices, after=after_row.data if after_row else None,
        detail={"productcd": body.productcd},
        ip=get_client_ip(request),
    )
    return {"result": "success", "message": "업그레이드가 완료되었습니다."}


def _get_free_product(svc, servicecd: str) -> Optional[dict]:
    rows = svc.table("products").select(
        "productcd,plancd,servicecd,billingtermcd,users,credit,is_customeraikey"
    ).eq("servicecd", servicecd).eq("plancd", "Fr").eq("useyn", True).eq(
        "is_sales", True
    ).limit(1).execute().data or []
    return rows[0] if rows else None


def _apply_due_pro_downgrades(svc, accountuid: str) -> None:
    """예약된 Pro 해지(subscriptions.canceldts) 중 이번 결제 주기(Ba 크레딧버킷 expiredts)가
    끝난 건을 Free로 자동 전환한다. 별도 배치/스케줄러가 없어 /myinfo/subscriptions 조회
    시점에 지연 평가로 처리한다 — 정기결제 자동 재청구 자체가 아직 없어 갱신일 개념이
    없으므로, 해지 예약은 즉시 반영하지 않고 이 시점에만 적용한다."""
    from datetime import datetime, timezone as tz
    from dateutil.relativedelta import relativedelta
    from dateutil import parser as dtparser

    active_rows = svc.table("accountservices").select(
        "servicecd,productcd,plancd,subscriptionuid,tenantid"
    ).eq("accountuid", accountuid).eq("servicestatus", "Active").execute().data or []

    for row in active_rows:
        if row.get("plancd") == "Fr" or not row.get("subscriptionuid"):
            continue

        sub_row = svc.table("subscriptions").select(
            "subscriptionuid,canceldts,canceluseruid,cancel_typecd"
        ).eq("subscriptionuid", row["subscriptionuid"]).maybe_single().execute()
        sub = sub_row.data if sub_row else None
        if not sub or not sub.get("canceldts"):
            continue
        # ArchiveDelete/ImmediateDelete로 예약된 건은 Free 전환이 아니라 _apply_due_pro_archival()이
        # 처리해야 한다 — 여기서 그대로 두면 옵션1을 고른 사용자가 의도와 다르게 Free로 전환돼버린다.
        if sub.get("cancel_typecd") in ("ArchiveDelete", "ImmediateDelete"):
            continue

        bucket_row = svc.table("creditbuckets").select("expiredts").eq(
            "subscriptionuid", row["subscriptionuid"]
        ).eq("creditchargecd", "Ba").maybe_single().execute()
        expiredts = bucket_row.data.get("expiredts") if bucket_row and bucket_row.data else None
        if not expiredts:
            continue
        try:
            due = dtparser.parse(expiredts) <= datetime.now(tz.utc)
        except Exception:
            continue
        if not due:
            continue

        free_product = _get_free_product(svc, row["servicecd"])
        if not free_product:
            continue

        now_utc = datetime.now(tz.utc)
        today = now_utc.date()
        actor = sub.get("canceluseruid")

        new_sub_resp = svc.table("subscriptions").insert({
            "tenantid": row["tenantid"],
            "accountuid": accountuid,
            "productcd": free_product["productcd"],
            "plancd": free_product["plancd"],
            "servicecd": row["servicecd"],
            "billingtermcd": free_product.get("billingtermcd"),
            "old_productcd": row["productcd"],
            "subscription_status": "Paid",
            "creator": actor,
        }).execute()
        if not new_sub_resp.data:
            continue
        new_subscriptionuid = new_sub_resp.data[0]["subscriptionuid"]

        svc.table("accountservices").update({
            "old_subscriptionuid": row["subscriptionuid"],
            "old_productcd": row["productcd"],
            "old_plancd": row["plancd"],
            "subscriptionuid": new_subscriptionuid,
            "productcd": free_product["productcd"],
            "plancd": free_product["plancd"],
            "is_customerAIKey": free_product.get("is_customeraikey", False),
            "billingfirstdt": today.isoformat(),
            "billingday": today.day,
            "included_users": free_product.get("users", 1),
            "add_users": 0,
            "total_users": free_product.get("users", 1),
            "is_autotopup": False,
            "updater": actor,
        }).eq("accountuid", accountuid).eq("servicecd", row["servicecd"]).execute()

        expiredts_new = (today + relativedelta(months=1) - timedelta(days=1)).isoformat()
        upsert_ba_creditbucket(
            svc,
            subscriptionuid=new_subscriptionuid,
            tenantid=row["tenantid"],
            accountuid=accountuid,
            servicecd=row["servicecd"],
            chargecredit=free_product.get("credit", 0),
            granteddts=now_utc.isoformat(),
            expiredts=expiredts_new,
            startdt=today.isoformat(),
        )

        if actor:
            create_notification(
                svc, category="plan", status="info",
                title="요금제 변경", message=f"'{row['servicecd']}' 서비스 요금제가 무료(Free)로 전환되었습니다.",
                title_key="msg.notification.plan.downgraded.title", message_key="msg.notification.plan.downgraded.body",
                params={"servicecd": row["servicecd"]},
                target_object="accountservice", target_uid=accountuid, target_url="myinfo", target_useruid=actor,
            )


def _apply_due_pro_archival(svc, accountuid: str) -> None:
    """예약된 '90일 유예 후 삭제'(subscriptions.cancel_typecd='ArchiveDelete') 중 이번 결제
    주기(Ba 크레딧버킷 expiredts)가 끝난 건을 Archived로 전환한다. _apply_due_pro_downgrades()와
    동일한 지연 평가 패턴이지만, Free 전환이 아니라 읽기전용(Archived) 상태로 전이한다는 점만 다르다.

    여기서는 상태 전이만 하고 실제 하위 콘텐츠 물리삭제는 하지 않는다 — 파괴적 작업은
    반드시 별도 배치(content_purge.py의 run-purge-cycle)에서만 처리한다."""
    from datetime import datetime, timezone as tz
    from dateutil import parser as dtparser

    active_rows = svc.table("accountservices").select(
        "servicecd,subscriptionuid,tenantid"
    ).eq("accountuid", accountuid).eq("servicestatus", "Active").execute().data or []

    for row in active_rows:
        if not row.get("subscriptionuid"):
            continue

        sub_row = svc.table("subscriptions").select(
            "subscriptionuid,canceldts,canceluseruid,cancel_typecd"
        ).eq("subscriptionuid", row["subscriptionuid"]).maybe_single().execute()
        sub = sub_row.data if sub_row else None
        if not sub or not sub.get("canceldts") or sub.get("cancel_typecd") != "ArchiveDelete":
            continue

        bucket_row = svc.table("creditbuckets").select("expiredts").eq(
            "subscriptionuid", row["subscriptionuid"]
        ).eq("creditchargecd", "Ba").maybe_single().execute()
        expiredts = bucket_row.data.get("expiredts") if bucket_row and bucket_row.data else None
        if not expiredts:
            continue
        try:
            due = dtparser.parse(expiredts) <= datetime.now(tz.utc)
        except Exception:
            continue
        if not due:
            continue

        now_utc = datetime.now(tz.utc)
        actor = sub.get("canceluseruid")

        svc.table("accountservices").update({
            "servicestatus": "Archived",
            "archived_dt": now_utc.isoformat(),
            "purge_immediate": False,
            "updater": actor,
        }).eq("accountuid", accountuid).eq("servicecd", row["servicecd"]).execute()

        if actor:
            create_notification(
                svc, category="plan", status="info",
                title="서비스 보관 전환",
                message=f"'{row['servicecd']}' 서비스가 읽기전용으로 전환되었습니다. 90일 후 데이터가 삭제됩니다.",
                title_key="msg.notification.service.archived.title", message_key="msg.notification.service.archived.body",
                params={"servicecd": row["servicecd"]},
                target_object="accountservice", target_uid=accountuid, target_url="myinfo", target_useruid=actor,
            )


def _apply_due_feature_cancellations(svc, accountuid: str) -> None:
    """예약된 기타구독(User/Feature 부가상품) 해지 중, 구매일 기준 결제 주기(1개월)가 끝난 건을
    실제로 Cancelled 처리한다. 개인 Pro 해지(_apply_due_pro_downgrades)와 동일한 지연 평가 패턴 —
    이미 결제한 기간은 그대로 유지하고 주기가 끝난 시점에만 실제 접근 권한을 회수한다.
    별도 배치/스케줄러가 없어 '기타 구독' 목록 조회(/tenant-manage/other-subscriptions) 시점에 처리."""
    from datetime import datetime, timezone as tz
    from dateutil.relativedelta import relativedelta
    from dateutil import parser as dtparser

    rows = svc.table("subscription_features").select(
        "subscriptionuid,productcd,tenantid,quantity,createdts,canceldts,canceluseruid"
    ).eq("accountuid", accountuid).eq("subscriptionstatus", "Paid").execute().data or []

    now_utc = datetime.now(tz.utc)
    for row in rows:
        if not row.get("canceldts"):
            continue
        try:
            period_end = dtparser.parse(row["createdts"]) + relativedelta(months=1)
        except Exception:
            continue
        if now_utc < period_end:
            continue

        actor = row.get("canceluseruid")
        svc.table("subscription_features").update({
            "subscriptionstatus": "Cancelled",
            "updater": actor,
            "updatedts": now_utc.isoformat(),
        }).eq("subscriptionuid", row["subscriptionuid"]).execute()

        prod_row = svc.table("products").select(
            "productcd,productnm,servicecd,producttype,users"
        ).eq("productcd", row["productcd"]).maybe_single().execute()
        product = prod_row.data if prod_row else {}

        if product.get("producttype") == "User" and product.get("servicecd"):
            svcrow = svc.table("accountservices").select(
                "included_users,add_users"
            ).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).maybe_single().execute()
            accsvc = svcrow.data if svcrow else None
            if accsvc:
                removed_users = (product.get("users") or 0) * (row.get("quantity") or 1)
                new_add_users = max((accsvc.get("add_users") or 0) - removed_users, 0)
                new_total_users = (accsvc.get("included_users") or 0) + new_add_users
                svc.table("accountservices").update({
                    "add_users": new_add_users,
                    "total_users": new_total_users,
                    "updater": actor,
                }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()

                # 정원 축소 후 실제 활성 인원이 초과 상태인지 확인 — 자동 비활성화는 하지 않고
                # 관리자에게 알림만 보낸다(누구를 뺄지는 관리자가 직접 판단해야 하는 결정이라
                # invite/신규 활성화는 total_users 재조회 시점에 자동으로 막히지만, 이미 활성인
                # 기존 인원을 시스템이 임의로 골라 비활성화하지는 않는다).
                active_cnt = svc.table("serviceusers").select("useruid", count="exact").eq(
                    "accountuid", accountuid
                ).eq("servicecd", product["servicecd"]).eq("useyn", True).execute()
                active_count = active_cnt.count or 0
                if active_count > new_total_users and actor:
                    create_notification(
                        svc, category="plan", status="error",
                        title="인원 초과 안내",
                        message=(
                            f"'{product['servicecd']}' 서비스 정원이 {new_total_users}명으로 줄었지만 "
                            f"현재 활성 인원은 {active_count}명입니다. 인원을 비활성화해주세요."
                        ),
                        title_key="msg.notification.overcapacity.title", message_key="msg.notification.overcapacity.body",
                        params={"servicecd": product["servicecd"], "total_users": new_total_users, "active_count": active_count},
                        target_object="accountservice", target_uid=accountuid,
                        target_url="org/tenant-users", target_useruid=actor,
                    )

        remaining = svc.table("subscription_features").select("subscriptionuid").eq(
            "accountuid", accountuid
        ).eq("productcd", row["productcd"]).eq("subscriptionstatus", "Paid").execute().data or []
        if not remaining:
            svc.table("account_features").delete().eq("accountuid", accountuid).eq("productcd", row["productcd"]).execute()

        if row["productcd"] == "mfa":
            svc.table("config_tenants").update({"value": False}).eq("tenantid", row["tenantid"]).eq("configcd", "Is_MFA").execute()
        if row["productcd"] == "whitelist":
            svc.table("config_tenants").update({"value": False}).eq("tenantid", row["tenantid"]).in_(
                "configcd", ["Is_Manager_IP_Allow", "Is_User_IP_Allow"]
            ).execute()

        if actor:
            create_notification(
                svc, category="plan", status="info",
                title="구독 해지 완료",
                message=f"'{product.get('productnm') or row['productcd']}' 구독이 해지되었습니다.",
                title_key="msg.notification.feature.cancelled.title", message_key="msg.notification.feature.cancelled.body",
                params={"productnm": product.get("productnm") or row["productcd"]},
                target_object="subscription_feature", target_uid=row["subscriptionuid"],
                target_url="org/other-subscription-manage", target_useruid=actor,
            )


def _next_billing_date(billingday: int, today: date) -> date:
    """오늘(today) 기준, billingday(매월 결제일)의 다음 도래일을 계산한다.
    오늘이 billingday보다 이전이면 이번 달, 아니면(오늘이 billingday거나 지났으면) 다음 달.
    월말 초과(예: billingday=30인데 2월)는 그 달의 마지막 날로 보정한다."""
    import calendar

    def _clamp(y: int, m: int, d: int) -> date:
        last = calendar.monthrange(y, m)[1]
        return date(y, m, min(d, last))

    if today.day < billingday:
        return _clamp(today.year, today.month, billingday)
    y, m = today.year, today.month + 1
    if m > 12:
        y += 1
        m = 1
    return _clamp(y, m, billingday)


_OVERCAPACITY_REMINDER_COOLDOWN_HOURS = 24


def _recent_overcapacity_notification(svc, accountuid: str, servicecd: str, cooldown_hours: int = _OVERCAPACITY_REMINDER_COOLDOWN_HOURS) -> bool:
    """최근 cooldown_hours 이내에 이 계정+서비스로 인원초과 알림을 이미 보냈는지 확인한다.
    accountuid 하나가 서비스 여러 개에서 동시에 초과 상태일 수 있어 params.servicecd까지 대조한다."""
    from datetime import datetime, timedelta, timezone as tz

    cutoff = (datetime.now(tz.utc) - timedelta(hours=cooldown_hours)).isoformat()
    rows = (
        svc.table("notifications").select("params,createdts")
        .eq("target_object", "accountservice").eq("target_uid", accountuid)
        .eq("titlekey", "msg.notification.overcapacity.title")
        .gte("createdts", cutoff)
        .execute().data or []
    )
    return any((r.get("params") or {}).get("servicecd") == servicecd for r in rows)


def _apply_due_quantity_decreases(svc, accountuid: str) -> None:
    """Add User 등 producttype='User' 상품의 수량 감소 예약(pending_decrease_qty) 중,
    적용일(pending_decrease_applydt)이 도래한 건을 실제로 quantity에서 차감한다.
    증가(+)는 즉시 반영되지만 감소(-)는 다음 결제일까지 유예되는 지연 평가 패턴 —
    [[_apply_due_feature_cancellations]]와 동일하게 별도 스케줄러 없이 목록 조회 시점에 처리.

    신청 시점(change_add_user_quantity)에 이미 활성 인원 기준으로 사전 차단하지만, 신청 후
    적용일 사이에 인원이 다시 늘어나면 적용 시점에도 초과일 수 있다. 이 경우 감소를 적용하지
    않고(정원·청구 그대로 유지) 쿨다운을 둔 반복 알림만 보낸다 — 실제로 인원을 줄여야 감소가
    반영되도록, 다음 조회 시점에 이 함수가 다시 평가한다(옵션 B, 2026-09-03)."""
    from datetime import datetime, timezone as tz

    rows = (
        svc.table("subscription_features").select(
            "subscriptionuid,productcd,tenantid,quantity,pending_decrease_qty,pending_decrease_applydt,updater,creator"
        )
        .eq("accountuid", accountuid).eq("subscriptionstatus", "Paid")
        .gt("pending_decrease_qty", 0)
        .execute().data or []
    )
    if not rows:
        return

    today = date.today()
    now_iso = datetime.now(tz.utc).isoformat()
    for row in rows:
        applydt = row.get("pending_decrease_applydt")
        if not applydt or date.fromisoformat(applydt) > today:
            continue

        prod_row = svc.table("products").select(
            "productcd,servicecd,producttype,users"
        ).eq("productcd", row["productcd"]).maybe_single().execute()
        product = prod_row.data if prod_row else {}
        if product.get("producttype") != "User" or not product.get("servicecd"):
            # 상품이 이미 카탈로그에서 사라졌으면 감소분을 안전하게 quantity에서만 차감
            product = {"servicecd": None, "users": 1}

        decrease_qty = row["pending_decrease_qty"]
        new_quantity = (row.get("quantity") or 0) - decrease_qty
        removed_units = (row.get("quantity") or 0) if new_quantity <= 0 else decrease_qty

        # 적용 전에 먼저 "적용했을 때의 정원"을 미리 계산해 현재 활성 인원과 비교한다.
        # 신청 시점엔 안전했어도 그 사이 인원이 다시 늘었으면 여기서 걸린다.
        if product.get("servicecd"):
            svcrow = svc.table("accountservices").select(
                "included_users,add_users"
            ).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).maybe_single().execute()
            accsvc = svcrow.data if svcrow else None
            if accsvc:
                removed_users = (product.get("users") or 0) * removed_units
                future_add_users = max((accsvc.get("add_users") or 0) - removed_users, 0)
                future_total_users = (accsvc.get("included_users") or 0) + future_add_users
                active_cnt = svc.table("serviceusers").select("useruid", count="exact").eq(
                    "accountuid", accountuid
                ).eq("servicecd", product["servicecd"]).eq("useyn", True).execute()
                active_count = active_cnt.count or 0

                if active_count > future_total_users:
                    # 정원·청구 유지 — 감소를 적용하지 않고 다음 조회 시점에 다시 평가되도록 그대로 둔다.
                    target_useruid = row.get("updater") or row.get("creator")
                    if target_useruid and not _recent_overcapacity_notification(svc, accountuid, product["servicecd"]):
                        create_notification(
                            svc, category="plan", status="error",
                            title="인원 초과 안내",
                            message=(
                                f"'{product['servicecd']}' 서비스 정원을 {future_total_users}명으로 줄이려면 "
                                f"현재 활성 인원({active_count}명)을 먼저 비활성화해야 합니다. 인원을 정리할 때까지 "
                                f"기존 정원과 청구가 유지됩니다."
                            ),
                            title_key="msg.notification.overcapacity.title", message_key="msg.notification.overcapacity.pending_body",
                            params={"servicecd": product["servicecd"], "total_users": future_total_users, "active_count": active_count},
                            target_object="accountservice", target_uid=accountuid,
                            target_url="org/tenant-users", target_useruid=target_useruid,
                        )
                    continue

        if new_quantity <= 0:
            svc.table("subscription_features").update({
                "subscriptionstatus": "Cancelled",
                "quantity": 0,
                "pending_decrease_qty": 0,
                "pending_decrease_applydt": None,
                "updatedts": now_iso,
            }).eq("subscriptionuid", row["subscriptionuid"]).execute()
            svc.table("account_features").delete().eq(
                "accountuid", accountuid
            ).eq("productcd", row["productcd"]).execute()
        else:
            svc.table("subscription_features").update({
                "quantity": new_quantity,
                "pending_decrease_qty": 0,
                "pending_decrease_applydt": None,
                "updatedts": now_iso,
            }).eq("subscriptionuid", row["subscriptionuid"]).execute()

        if product.get("servicecd") and accsvc:
            svc.table("accountservices").update({
                "add_users": future_add_users,
                "total_users": future_total_users,
            }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()


def _calc_addon_users(svc, accountuid: str, servicecd: str) -> int:
    """해당 계정+서비스의 현재 활성(Paid) producttype='User' 부가상품(Add User) 보유 수량 합계.
    Add User는 플랜과 무관하게 유지되는 별도 구독이므로, 플랜 변경 시 accountservices.add_users를
    이 값으로 재계산해서 반영해야 한다 (과거엔 무조건 0으로 초기화하던 버그가 있었음)."""
    rows = (
        svc.table("subscription_features").select("productcd,quantity")
        .eq("accountuid", accountuid).eq("subscriptionstatus", "Paid")
        .execute().data or []
    )
    if not rows:
        return 0
    productcds = list({r["productcd"] for r in rows})
    products = (
        svc.table("products").select("productcd,servicecd,producttype,users")
        .in_("productcd", productcds).execute().data or []
    )
    prod_map = {p["productcd"]: p for p in products}
    total = 0
    for r in rows:
        p = prod_map.get(r["productcd"])
        if not p or p.get("producttype") != "User" or p.get("servicecd") != servicecd:
            continue
        total += (p.get("users") or 0) * (r.get("quantity") or 1)
    return total


def _get_personal_active_subscription(svc, user_id: str, tenantid: Optional[str], servicecd: str) -> tuple[str, dict]:
    """개인(시스템 테넌트) 계정의 특정 servicecd 활성 구독을 조회.

    반환: (accountuid, subscriptions 행). 조직 테넌트이거나 구독이 없으면 예외를 던진다.
    """
    _, issystemtenant = _get_tenant_and_issystemtenant(svc, user_id, tenantid)
    if not issystemtenant:
        raise HTTPException(status_code=400, detail="개인 요금제만 해지할 수 있습니다.")

    acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    if not acc or not acc.data:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")
    accountuid = acc.data["accountuid"]

    accsvc_row = svc.table("accountservices").select(
        "plancd,subscriptionuid"
    ).eq("accountuid", accountuid).eq("servicecd", servicecd).eq(
        "servicestatus", "Active"
    ).maybe_single().execute()
    accsvc = accsvc_row.data if accsvc_row else None
    if not accsvc or not accsvc.get("subscriptionuid"):
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")
    if accsvc.get("plancd") == "Fr":
        raise HTTPException(status_code=400, detail="이미 무료 요금제입니다.")

    sub_row = svc.table("subscriptions").select(
        "subscriptionuid,canceldts"
    ).eq("subscriptionuid", accsvc["subscriptionuid"]).maybe_single().execute()
    sub = sub_row.data if sub_row else None
    if not sub:
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")
    return accountuid, sub


_CANCEL_TYPECDS = {"Downgrade", "ArchiveDelete", "ImmediateDelete"}


def _validate_cancel_request(
    cancel_typecd: str, allowed_typecds: set, confirm_deletion_policy: bool, confirm_delete_phrase: Optional[str]
) -> None:
    """구독 해지 요청 공통 검증 — 개인(Pro)/기업 테넌트 양쪽에서 재사용한다."""
    if cancel_typecd not in allowed_typecds:
        raise HTTPException(status_code=400, detail="msg.cancel_typecd.invalid")
    if cancel_typecd != "Downgrade" and not confirm_deletion_policy:
        raise HTTPException(status_code=400, detail="msg.deletion.policy.confirm.required")
    # 즉시삭제는 결제기간을 안 채워주는 예외라 체크박스 외에 "DELETE" 확인 구문까지 요구한다.
    if cancel_typecd == "ImmediateDelete" and confirm_delete_phrase != "DELETE":
        raise HTTPException(status_code=400, detail="msg.deletion.confirm.phrase.required")


def _reserve_service_cancellation(
    svc, accountuid: str, servicecd: str, subscriptionuid: str, user_id: str,
    cancel_typecd: str, extra_fields: Optional[dict] = None,
) -> Optional[str]:
    """subscriptions에 해지를 예약(canceldts/cancel_typecd 기록)하고, ImmediateDelete면 accountservices를
    즉시 Archived+purge_immediate=True로 동기 전이한다(물리삭제는 이 안에서 안 함 — content_purge.py 배치가
    처리). 반환값은 실제 반영 예정일 — ArchiveDelete/Downgrade는 이번 결제 주기(Ba 크레딧버킷 expiredts),
    ImmediateDelete는 오늘. 개인(Pro)/기업 테넌트 양쪽에서 재사용한다."""
    from datetime import datetime, timezone as tz

    now_utc = datetime.now(tz.utc)
    payload = {
        "canceluseruid": user_id,
        "canceldts": now_utc.isoformat(),
        "cancel_typecd": cancel_typecd,
        "updater": user_id,
        "updatedts": now_utc.isoformat(),
    }
    if extra_fields:
        payload.update(extra_fields)
    svc.table("subscriptions").update(payload).eq("subscriptionuid", subscriptionuid).execute()

    if cancel_typecd == "ImmediateDelete":
        svc.table("accountservices").update({
            "servicestatus": "Archived",
            "archived_dt": now_utc.isoformat(),
            "purge_immediate": True,
            "updater": user_id,
        }).eq("accountuid", accountuid).eq("servicecd", servicecd).execute()
        return now_utc.date().isoformat()

    bucket_row = svc.table("creditbuckets").select("expiredts").eq(
        "subscriptionuid", subscriptionuid
    ).eq("creditchargecd", "Ba").maybe_single().execute()
    return bucket_row.data.get("expiredts") if bucket_row and bucket_row.data else None


def _undo_service_cancellation(svc, subscriptionuid: str, user_id: str) -> None:
    """예약된 해지 철회 — subscriptions의 해지 관련 필드를 초기화한다.
    개인(Pro)/기업 테넌트 양쪽에서 재사용한다."""
    from datetime import datetime, timezone as tz

    svc.table("subscriptions").update({
        "canceluseruid": None,
        "canceldts": None,
        "cancel_reasoncd": None,
        "cancel_reasondesc": None,
        "cancel_typecd": None,
        "updater": user_id,
        "updatedts": datetime.now(tz.utc).isoformat(),
    }).eq("subscriptionuid", subscriptionuid).execute()


class ProCancelRequest(BaseModel):
    servicecd: str
    cancel_reasoncd: str
    cancel_reasondesc: Optional[str] = None
    cancel_typecd: str = "Downgrade"
    confirm_deletion_policy: bool = False
    confirm_delete_phrase: Optional[str] = None


@router.post("/myinfo/pro-cancel")
def request_pro_cancel(
    body: ProCancelRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """개인(Pro) 요금제 해지 예약 — 3가지 처리 방식 중 하나를 고른다.

    - Downgrade(기본, 기존 동작): 즉시 다운그레이드하지 않고 이미 낸 결제는 그대로 두고
      현재 결제 주기가 끝나는 시점까지 Pro를 유지한 뒤 자동으로 Free로 전환한다.
    - ArchiveDelete(옵션1): Downgrade와 동일하게 결제 주기가 끝날 때까지 대기하지만,
      끝나는 시점에 Free 전환이 아니라 Archived(90일 읽기전용) 상태로 전이한다
      (_apply_due_pro_archival() 참고). 90일 후 실제 삭제는 배치(content_purge.py)가 처리.
    - ImmediateDelete(옵션2): 결제 주기를 기다리지 않고 요청 즉시 Archived+purge_immediate=True로
      전이한다(=이미 낸 결제 기간을 채워주지 않음. 사용자가 명시적으로 선택한 예외 케이스).
      실제 데이터 물리삭제는 이 요청 안에서 하지 않고 배치가 다음 실행 시 처리한다."""
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    _validate_cancel_request(body.cancel_typecd, _CANCEL_TYPECDS, body.confirm_deletion_policy, body.confirm_delete_phrase)

    accountuid, sub = _get_personal_active_subscription(svc, user_id, tenantid, body.servicecd)
    if sub.get("canceldts"):
        raise HTTPException(status_code=400, detail="이미 해지가 예약되어 있습니다.")

    request_dts = datetime.now(tz.utc).isoformat()
    effective_date = _reserve_service_cancellation(
        svc, accountuid, body.servicecd, sub["subscriptionuid"], user_id, body.cancel_typecd,
        extra_fields={"cancel_reasoncd": body.cancel_reasoncd, "cancel_reasondesc": body.cancel_reasondesc},
    )

    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="update", targettype="settings/myinfo/pro-cancel", targetid=sub["subscriptionuid"],
        before={"canceldts": sub.get("canceldts")}, after={"canceldts": request_dts},
        detail={
            "cancel_reasoncd": body.cancel_reasoncd,
            "cancel_typecd": body.cancel_typecd,
            "confirm_deletion_policy": body.confirm_deletion_policy,
        },
        ip=get_client_ip(request),
    )
    return {"result": "success", "effective_date": effective_date, "cancel_typecd": body.cancel_typecd}


class ProCancelUndoRequest(BaseModel):
    servicecd: str


@router.post("/myinfo/pro-cancel-undo")
def undo_pro_cancel(
    body: ProCancelUndoRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """예약된 Pro 해지 철회 — 결제 주기가 끝나기 전까지만 가능하다."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    accountuid, sub = _get_personal_active_subscription(svc, user_id, tenantid, body.servicecd)
    if not sub.get("canceldts"):
        raise HTTPException(status_code=400, detail="예약된 해지가 없습니다.")

    # ImmediateDelete는 신청 즉시 Archived로 동기 전이되므로 신청 순간부터 철회 불가.
    # ArchiveDelete/Downgrade는 결제 주기가 끝나기 전(=아직 Active)까지만 철회 가능(기존 규칙과 동일).
    accsvc_row = svc.table("accountservices").select("servicestatus").eq(
        "accountuid", accountuid
    ).eq("servicecd", body.servicecd).maybe_single().execute()
    accsvc_status = accsvc_row.data.get("servicestatus") if accsvc_row and accsvc_row.data else None
    if accsvc_status in ("Archived", "Deleted"):
        raise HTTPException(status_code=400, detail="이미 처리가 시작되어 철회할 수 없습니다.")

    _undo_service_cancellation(svc, sub["subscriptionuid"], user_id)

    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="update", targettype="settings/myinfo/pro-cancel-undo", targetid=sub["subscriptionuid"],
        before={"canceldts": sub.get("canceldts")}, after={"canceldts": None},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


class WithdrawAccountRequest(BaseModel):
    confirm_deletion_policy: bool = False
    reasoncd: Optional[str] = None
    reasondesc: Optional[str] = None


@router.post("/myinfo/withdraw")
def withdraw_personal_account(
    body: WithdrawAccountRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """개인(시스템 테넌트) 계정 탈퇴.

    1. 보유 중인 모든 활성 서비스(Do/Ch/In, Free 포함)를 90일 유예 삭제(ArchiveDelete)로
       일괄 예약한다 — 실제 콘텐츠 물리 삭제는 기존 배치(content_purge.py)가 처리한다.
    2. sdoc.users 행을 초기화한다: email/usernm은 공백(재가입을 허용하는 의도 — 결제/세금계산서
       등 법적 보존이 필요한 이메일은 accounts.encemail이 이미 암호화해 별도 보관 중이라 여기서
       따로 암호화 보존할 필요가 없다), isemailconfirm/default_tenantid/electronicfinancialtermsyn은
       null, useyn=False. termsofuseyn/userinfoyn/marketingyn(동의 이력)은 그대로 둔다.
    3. Supabase Auth(GoTrue) 사용자를 하드 삭제한다 — sdoc.users.useyn만 바꿔서는 로그인이
       막히지 않는다(어떤 라우터의 인증 흐름도 이 필드를 확인하지 않음, get_user()는 JWT
       유효성만 봄). 실제 재로그인 차단을 보장하려면 Auth 쪽도 반드시 같이 지워야 한다 —
       그래서 이 호출을 마지막에 둔다(이후 이 토큰으로는 어떤 API도 호출할 수 없게 됨)."""
    if not body.confirm_deletion_policy:
        raise HTTPException(status_code=400, detail="msg.withdraw.policy.confirm.required")

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, issystemtenant = _get_tenant_and_issystemtenant(svc, user_id, tenantid)
    if not issystemtenant:
        raise HTTPException(status_code=400, detail="msg.withdraw.system_tenant_only")

    # 지금 선택된 테넌트가 개인 테넌트여도, 이 사람이 다른 "기업" 테넌트의 관리자(rolecd='M')로
    # 등록돼 있으면 탈퇴를 막는다 — 관리자가 사라지면 그 테넌트가 고아 상태가 되기 때문.
    mgr_tenantids = [
        r["tenantid"] for r in (
            svc.table("tenantusers").select("tenantid")
            .eq("useruid", user_id).eq("useyn", True).eq("rolecd", "M").execute().data or []
        )
    ]
    if mgr_tenantids:
        org_tenants = svc.table("tenants").select("tenantid").in_(
            "tenantid", mgr_tenantids
        ).eq("issystemtenant", False).execute().data or []
        if org_tenants:
            raise HTTPException(status_code=400, detail="msg.withdraw.org_manager_blocked")

    acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    accountuid = acc.data["accountuid"] if acc and acc.data else None

    reserved_services: list[str] = []
    if accountuid:
        accsvcs = svc.table("accountservices").select(
            "servicecd,subscriptionuid"
        ).eq("accountuid", accountuid).eq("servicestatus", "Active").execute().data or []
        for row in accsvcs:
            subscriptionuid = row.get("subscriptionuid")
            if not subscriptionuid:
                continue
            sub_row = svc.table("subscriptions").select("canceldts").eq(
                "subscriptionuid", subscriptionuid
            ).maybe_single().execute()
            if sub_row and sub_row.data and sub_row.data.get("canceldts"):
                continue  # 이미 별도로 해지가 예약된 서비스는 건드리지 않는다
            _reserve_service_cancellation(
                svc, accountuid, row["servicecd"], subscriptionuid, user_id, "ArchiveDelete",
            )
            reserved_services.append(row["servicecd"])

    before_user = svc.table("users").select("*").eq("useruid", user_id).maybe_single().execute()
    svc.table("users").update({
        "email": "",
        "usernm": "",
        "isemailconfirm": None,
        "default_tenantid": None,
        "electronicfinancialtermsyn": None,
        "useyn": False,
    }).eq("useruid", user_id).execute()

    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="update", targettype="settings/myinfo/withdraw", targetid=user_id,
        before=before_user.data if before_user else None,
        after={"useyn": False, "reserved_services": reserved_services},
        detail={"reasoncd": body.reasoncd, "reasondesc": body.reasondesc},
        ip=get_client_ip(request),
    )

    get_service_client().auth.admin.delete_user(user_id)

    return {"result": "success", "reserved_services": reserved_services}


# ══════════════════════════════════════════════════════
#  TENANT MANAGE — 구독 관리 (좌: 현재 구독 / 우: Team·Enterprise 상품 선택)
# ══════════════════════════════════════════════════════

def _get_tenant_and_issystemtenant(svc, user_id: str, tenantid: Optional[str]) -> tuple[str, bool]:
    """tenantid와 issystemtenant 여부를 반환."""
    if not tenantid:
        tu = svc.table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).maybe_single().execute()
        if not tu or not tu.data:
            raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
        tenantid = str(tu.data["tenantid"])

    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True
    return tenantid, issystemtenant


def _get_tenant_and_account(svc, user_id: str, tenantid: Optional[str]) -> tuple[str, Optional[str]]:
    """tenantid와 accountuid를 반환."""
    if not tenantid:
        tu = svc.table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).maybe_single().execute()
        if not tu or not tu.data:
            raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
        tenantid = str(tu.data["tenantid"])

    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True

    if issystemtenant:
        acc = svc.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = svc.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()

    accountuid = str(acc.data["accountuid"]) if acc and acc.data else None
    return tenantid, accountuid


def _require_tenant_manager(svc, user_id: str, tenantid: str) -> None:
    """tenant-manage 화면 전용 엔드포인트 접근 제한: 해당 테넌트의 매니저(rolecd=M)만 허용."""
    tu = (
        svc.table("tenantusers").select("rolecd,useyn")
        .eq("useruid", user_id).eq("tenantid", int(tenantid))
        .maybe_single().execute()
    )
    if not tu or not tu.data or tu.data.get("rolecd") != "M" or tu.data.get("useyn") is not True:
        raise HTTPException(status_code=403, detail="테넌트 관리자만 접근할 수 있습니다.")


def _require_not_system_tenant(svc, tenantid: str) -> None:
    """조직/구독 관리 화면은 시스템(개인) 테넌트에서 의미가 없어 차단한다."""
    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    if t_row and t_row.data and t_row.data.get("issystemtenant"):
        raise HTTPException(status_code=403, detail="msg.org.feature.unavailable.system.tenant")


def _require_system_tenant(svc, tenantid: str) -> None:
    """개인 계정 전용 화면(예: 내 정보 크레딧 구매)은 조직 테넌트에서 의미가 없어 차단한다.
    (org/credit-manage와 반대 방향 가드 — 이쪽은 개인 계정 전용, 그쪽은 조직 전용으로 서로 겹치지 않게 분리)"""
    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    if not t_row or not t_row.data or not t_row.data.get("issystemtenant"):
        raise HTTPException(status_code=403, detail="msg.feature.unavailable.org.tenant")


@router.get("/tenant-manage/subscriptions")
def get_tenant_manage_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """구독 관리 화면 좌측: 서비스별 현재 구독 상품 목록."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    # 전체 서비스 목록 — 아직 구독하지 않은 서비스도 선택 가능하도록 항상 포함
    service_codes = (
        svc.table("codes").select("codevalue,orderno")
        .eq("codegroupcd", "servicecd").eq("useyn", True).order("orderno").execute().data or []
    )

    tenant_row = svc.table("tenants").select("cancel_requested_dt").eq(
        "tenantid", int(tenantid)
    ).maybe_single().execute()
    tenant_cancel_requested_dt = tenant_row.data.get("cancel_requested_dt") if tenant_row and tenant_row.data else None

    if not accountuid:
        return {
            "subscriptions": [
                {
                    "servicecd": c["codevalue"], "productcd": None, "productnm": None,
                    "plancd": None, "billingtermcd": None, "users": None, "credit": None,
                    "servicestatus": None, "included_users": None, "add_users": None,
                    "cancel_reserved": False, "cancel_effective_date": None,
                }
                for c in service_codes
            ],
            "accountuid": None,
            "tenant_cancel_requested": bool(tenant_cancel_requested_dt),
            "tenant_cancel_requested_dt": tenant_cancel_requested_dt,
        }

    # 예약된 서비스 해지(90일 유예삭제) 중 이번 결제 주기가 끝난 건이 있으면 Archived로 전이한 뒤 조회 —
    # 개인(Pro) 쪽 get_myinfo_subscriptions()와 동일한 지연평가 트리거 패턴. 기업 테넌트는 Downgrade
    # 예약 자체가 생기지 않으므로(아래 신규 엔드포인트가 ArchiveDelete/ImmediateDelete만 허용) 여기선
    # _apply_due_pro_downgrades()는 호출하지 않는다.
    _apply_due_pro_archival(svc, accountuid)

    rows = (
        svc.table("accountservices")
        .select("servicecd,productcd,plancd,servicestatus,included_users,add_users,subscriptionuid")
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

    # 서비스 해지 예약 여부/반영 예정일 — subscriptions.canceldts 존재 여부 + Ba 크레딧버킷 expiredts
    # (개인 get_myinfo_subscriptions()의 cancel_map/bucket_map 계산과 동일한 방식)
    sub_ids = [r["subscriptionuid"] for r in rows if r.get("subscriptionuid")]
    cancel_map = {}
    bucket_map = {}
    if sub_ids:
        cancel_rows = svc.table("subscriptions").select("subscriptionuid,canceldts").in_(
            "subscriptionuid", sub_ids
        ).execute().data or []
        cancel_map = {r["subscriptionuid"]: r.get("canceldts") for r in cancel_rows}

        bucket_rows = svc.table("creditbuckets").select("subscriptionuid,expiredts").in_(
            "subscriptionuid", sub_ids
        ).eq("creditchargecd", "Ba").execute().data or []
        bucket_map = {r["subscriptionuid"]: r.get("expiredts") for r in bucket_rows}

    offsetminutes = _get_offsetminutes(get_service_client(), user_id, tenantid)

    result = []
    for c in service_codes:
        scd = c["codevalue"]
        r = row_map.get(scd)
        if not r:
            result.append({
                "servicecd": scd, "productcd": None, "productnm": None,
                "plancd": None, "billingtermcd": None, "users": None, "credit": None,
                "servicestatus": None, "included_users": None, "add_users": None,
                "cancel_reserved": False, "cancel_effective_date": None,
            })
            continue
        p = prod_map.get(r.get("productcd"), {})
        sub_id = r.get("subscriptionuid")
        cancel_reserved = bool(cancel_map.get(sub_id))
        result.append({
            "servicecd": scd,
            "productcd": r.get("productcd"),
            "productnm": p.get("productnm", r.get("productcd")),
            "plancd": r.get("plancd"),
            "billingtermcd": p.get("billingtermcd"),
            "users": p.get("users"),
            "credit": p.get("credit"),
            "servicestatus": r.get("servicestatus"),
            "included_users": r.get("included_users"),
            "add_users": r.get("add_users"),
            "cancel_reserved": cancel_reserved,
            "cancel_effective_date": _fmt_dt(bucket_map.get(sub_id), offsetminutes) if cancel_reserved else None,
        })

    return {
        "subscriptions": result, "accountuid": accountuid,
        "tenant_cancel_requested": bool(tenant_cancel_requested_dt),
        "tenant_cancel_requested_dt": _fmt_dt(tenant_cancel_requested_dt, offsetminutes) if tenant_cancel_requested_dt else None,
    }


_TENANT_CANCEL_TYPECDS = {"ArchiveDelete", "ImmediateDelete"}


class TenantSubscriptionCancelRequest(BaseModel):
    servicecd: str
    cancel_reasoncd: str
    cancel_reasondesc: Optional[str] = None
    cancel_typecd: str
    confirm_deletion_policy: bool = False
    confirm_delete_phrase: Optional[str] = None


@router.post("/tenant-manage/subscription-cancel")
def request_tenant_subscription_cancel(
    body: TenantSubscriptionCancelRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """구독 관리 화면: 서비스 해지 예약 — 90일 유예삭제(ArchiveDelete) 또는 즉시삭제(ImmediateDelete)만
    허용한다. 개인 Pro의 Downgrade(Free 전환)에 해당하는 선택지는 기업 테넌트엔 없다 — 서비스가
    프로젝트의 상위 개념이라 해지는 곧 하위 프로젝트 데이터 보관정책 결정이지 요금제 다운그레이드가
    아니기 때문. 신청은 즉시 접수되고 실제 반영(Archived 전이)은 결제주기 종료 후라는 동작 자체는
    개인 Pro 해지와 동일 — _reserve_service_cancellation()/_apply_due_pro_archival()/content_purge.py를
    그대로 재사용한다(둘 다 accountuid+servicecd로만 스코프돼 테넌트 종류를 구분하지 않음)."""
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    _validate_cancel_request(body.cancel_typecd, _TENANT_CANCEL_TYPECDS, body.confirm_deletion_policy, body.confirm_delete_phrase)

    accsvc_row = svc.table("accountservices").select("subscriptionuid").eq(
        "accountuid", accountuid
    ).eq("servicecd", body.servicecd).eq("servicestatus", "Active").maybe_single().execute()
    accsvc = accsvc_row.data if accsvc_row else None
    if not accsvc or not accsvc.get("subscriptionuid"):
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")

    sub_row = svc.table("subscriptions").select("subscriptionuid,canceldts").eq(
        "subscriptionuid", accsvc["subscriptionuid"]
    ).maybe_single().execute()
    sub = sub_row.data if sub_row else None
    if not sub:
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")
    if sub.get("canceldts"):
        raise HTTPException(status_code=400, detail="이미 해지가 예약되어 있습니다.")

    request_dts = datetime.now(tz.utc).isoformat()
    effective_date = _reserve_service_cancellation(
        svc, accountuid, body.servicecd, sub["subscriptionuid"], user_id, body.cancel_typecd,
        extra_fields={"cancel_reasoncd": body.cancel_reasoncd, "cancel_reasondesc": body.cancel_reasondesc},
    )

    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/subscription-cancel", targetid=sub["subscriptionuid"],
        before={"canceldts": sub.get("canceldts")}, after={"canceldts": request_dts},
        detail={
            "cancel_reasoncd": body.cancel_reasoncd,
            "cancel_typecd": body.cancel_typecd,
            "confirm_deletion_policy": body.confirm_deletion_policy,
        },
        ip=get_client_ip(request),
    )
    return {"result": "success", "effective_date": effective_date, "cancel_typecd": body.cancel_typecd}


class TenantSubscriptionCancelUndoRequest(BaseModel):
    servicecd: str


@router.post("/tenant-manage/subscription-cancel-undo")
def undo_tenant_subscription_cancel(
    body: TenantSubscriptionCancelUndoRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """구독 관리 화면: 예약된 서비스 해지 철회 — 결제 주기가 끝나기 전(=아직 Active)까지만 가능하다."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    accsvc_row = svc.table("accountservices").select("subscriptionuid,servicestatus").eq(
        "accountuid", accountuid
    ).eq("servicecd", body.servicecd).maybe_single().execute()
    accsvc = accsvc_row.data if accsvc_row else None
    if not accsvc or not accsvc.get("subscriptionuid"):
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")
    if accsvc.get("servicestatus") in ("Archived", "Deleted"):
        raise HTTPException(status_code=400, detail="이미 처리가 시작되어 철회할 수 없습니다.")

    sub_row = svc.table("subscriptions").select("subscriptionuid,canceldts").eq(
        "subscriptionuid", accsvc["subscriptionuid"]
    ).maybe_single().execute()
    sub = sub_row.data if sub_row else None
    if not sub or not sub.get("canceldts"):
        raise HTTPException(status_code=400, detail="예약된 해지가 없습니다.")

    _undo_service_cancellation(svc, sub["subscriptionuid"], user_id)

    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/subscription-cancel-undo", targetid=sub["subscriptionuid"],
        before={"canceldts": sub.get("canceldts")}, after={"canceldts": None},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


def _all_services_already_cancelled(svc, accountuid: str) -> bool:
    """이 계정의 Active 서비스가 전부 이미 해지 예약(canceldts 존재)돼 있는지 확인한다.
    테넌트 해지는 매니저가 서비스를 미리 다 해지해둔 뒤에만 신청할 수 있다 — 개인 계정 탈퇴와
    반대 순서(탈퇴는 신청 즉시 서비스를 자동으로 해지시켜주지만, 테넌트 해지는 그 반대)."""
    active_rows = svc.table("accountservices").select("subscriptionuid").eq(
        "accountuid", accountuid
    ).eq("servicestatus", "Active").execute().data or []
    sub_ids = [r["subscriptionuid"] for r in active_rows if r.get("subscriptionuid")]
    if not sub_ids:
        return True
    cancel_rows = svc.table("subscriptions").select("subscriptionuid,canceldts").in_(
        "subscriptionuid", sub_ids
    ).execute().data or []
    canceled_ids = {r["subscriptionuid"] for r in cancel_rows if r.get("canceldts")}
    return set(sub_ids) <= canceled_ids


class TenantCancelRequest(BaseModel):
    cancel_reasoncd: Optional[str] = None
    cancel_reasondesc: Optional[str] = None
    confirm_deletion_policy: bool = False


@router.post("/tenant-manage/tenant-cancel")
def request_tenant_cancel(
    body: TenantCancelRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """테넌트(기업) 해지 신청 — 개인 계정 탈퇴와 순서가 반대다: 탈퇴는 신청 즉시 모든 서비스를
    자동으로 해지 예약해주지만, 테넌트 해지는 매니저가 이미 모든 서비스(Do/Ch/In)를 개별적으로
    해지해둔 상태여야만 신청할 수 있다(_all_services_already_cancelled로 검증 — 프론트도 미리
    막지만 여기서도 방어적으로 재검증한다).

    신청 자체는 tenants.cancel_requested_dt만 기록한다 — 각 서비스는 이미 예약된 자기 유예기간을
    그대로 다 채운 뒤 content_purge.py가 실제로 Deleted 처리하고, 그 마지막 서비스가 Deleted되는
    순간(_purge_accountservice_content 참고) 테넌트 전체가 잠긴다(tenants.useyn=False + 소속
    tenantusers.useyn=False 일괄 처리)."""
    if not body.confirm_deletion_policy:
        raise HTTPException(status_code=400, detail="msg.tenant_cancel.policy.confirm.required")

    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    tenant_row = svc.table("tenants").select("tenantnm,cancel_requested_dt,useyn").eq(
        "tenantid", int(tenantid)
    ).maybe_single().execute()
    tenant = tenant_row.data if tenant_row else None
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    if tenant.get("cancel_requested_dt"):
        raise HTTPException(status_code=400, detail="이미 해지가 신청되어 있습니다.")
    if not tenant.get("useyn", True):
        raise HTTPException(status_code=400, detail="이미 해지된 테넌트입니다.")

    if not _all_services_already_cancelled(svc, accountuid):
        raise HTTPException(status_code=400, detail="msg.tenant_cancel.services_not_cancelled")

    now_iso = datetime.now(tz.utc).isoformat()
    svc.table("tenants").update({
        "cancel_requested_dt": now_iso,
        "cancel_useruid": user_id,
        "cancel_reasoncd": body.cancel_reasoncd,
        "cancel_reasondesc": body.cancel_reasondesc,
    }).eq("tenantid", int(tenantid)).execute()

    # 인앱 알림은 매니저뿐 아니라 일반 멤버 전원에게 보낸다 — 나중에 유예기간이 끝나 테넌트가
    # 잠기는 순간 아무 예고도 못 받았던 사람이 생기지 않도록(2026-09-03 보완). 이메일은 아래에서
    # 매니저에게만 보낸다(전 멤버 대상 메일은 과할 수 있어 기존 범위 유지).
    member_rows = svc.table("tenantusers").select("useruid,rolecd").eq(
        "tenantid", int(tenantid)
    ).eq("useyn", True).execute().data or []
    member_useruids = [r["useruid"] for r in member_rows if r.get("useruid")]
    manager_useruids = [r["useruid"] for r in member_rows if r.get("useruid") and r.get("rolecd") == "M"]

    for member_uid in member_useruids:
        create_notification(
            svc, category="plan", status="warning",
            title="테넌트 해지 신청 접수",
            message=f"'{tenant.get('tenantnm')}' 테넌트의 해지가 신청되었습니다. 각 서비스의 유예기간이 끝나는 대로 완전히 삭제됩니다.",
            title_key="msg.notification.tenant_cancel.title", message_key="msg.notification.tenant_cancel.body",
            params={"tenantnm": tenant.get("tenantnm")},
            target_object="tenant", target_uid=accountuid,
            target_url="org/tenant-cancel", target_useruid=member_uid,
        )

    if manager_useruids:
        try:
            import smtplib
            from email.mime.text import MIMEText

            mgr_users = svc.schema("public").table("users").select("useruid,email").in_(
                "useruid", manager_useruids
            ).execute().data or []
            mgr_emails = [r["email"] for r in mgr_users if r.get("email")]
            if mgr_emails:
                login_user = settings.EMAIL_HOST_USER
                smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                smtp.login(login_user, settings.EMAIL_HOST_PASSWORD)
                try:
                    subject = f"[D2Doc] '{tenant.get('tenantnm')}' 테넌트 해지 신청 접수"
                    mail_body = (
                        f"안녕하세요,\n\n"
                        f"'{tenant.get('tenantnm')}' 테넌트의 해지가 신청되었습니다.\n\n"
                        f"이용 중인 각 서비스는 자체 유예기간이 끝날 때까지 계속 사용할 수 있으며, "
                        f"모든 서비스의 유예기간이 끝나면 테넌트가 완전히 삭제됩니다.\n\n"
                        f"착오로 신청하셨다면 유예기간이 끝나기 전까지 관리 화면에서 신청을 철회할 수 있습니다.\n\n"
                        f"감사합니다.\nD2Doc 팀"
                    )
                    for email in mgr_emails:
                        msg = MIMEText(mail_body, "plain", "utf-8")
                        msg["Subject"] = subject
                        msg["From"] = login_user
                        msg["To"] = email
                        smtp.sendmail(login_user, [email], msg.as_string())
                finally:
                    smtp.quit()
        except Exception:
            # 이메일 발송 실패가 해지 신청 자체를 막지는 않는다(인앱 알림은 이미 갔음) — create_notification과
            # 동일한 관용: 부가 채널 하나가 실패했다고 핵심 동작을 롤백할 이유는 없다.
            pass

    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/tenant-cancel", targetid=str(tenantid),
        before={"cancel_requested_dt": None}, after={"cancel_requested_dt": now_iso},
        detail={"cancel_reasoncd": body.cancel_reasoncd, "cancel_reasondesc": body.cancel_reasondesc},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


@router.post("/tenant-manage/tenant-cancel-undo")
def undo_tenant_cancel(
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """테넌트 해지 신청 철회 — 아직 완전히 잠기지 않은 동안(tenants.useyn=True)만 가능하다.
    개별 서비스들의 자체 해지 예약은 건드리지 않는다(원한다면 각자 구독 관리 화면에서 따로 철회)."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    tenant_row = svc.table("tenants").select("cancel_requested_dt,useyn").eq(
        "tenantid", int(tenantid)
    ).maybe_single().execute()
    tenant = tenant_row.data if tenant_row else None
    if not tenant or not tenant.get("cancel_requested_dt"):
        raise HTTPException(status_code=400, detail="신청된 해지가 없습니다.")
    if not tenant.get("useyn", True):
        raise HTTPException(status_code=400, detail="이미 처리가 완료되어 철회할 수 없습니다.")

    prev_requested_dt = tenant.get("cancel_requested_dt")
    svc.table("tenants").update({
        "cancel_requested_dt": None,
        "cancel_useruid": None,
        "cancel_reasoncd": None,
        "cancel_reasondesc": None,
    }).eq("tenantid", int(tenantid)).execute()

    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/tenant-cancel-undo", targetid=str(tenantid),
        before={"cancel_requested_dt": prev_requested_dt}, after={"cancel_requested_dt": None},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


def _get_user_currencycd(svc, user_id: str, tenantid: Optional[str] = None) -> str:
    """사용자 언어(languagecd) 기준 가격 통화 결정 — ko면 KRW, 그 외(en/ja 등)/미설정이면 USD.
    실제 결제(포트원)는 통화와 무관하게 항상 KRW로 진행되며, 여기서 정해지는 통화는 화면 표시 전용이다."""
    try:
        q = svc.table("tenantusers").select("languagecd,tenantid").eq("useruid", user_id)
        if tenantid:
            q = q.eq("tenantid", int(tenantid))
        else:
            q = q.eq("useyn", True)
        rows = q.limit(1).execute().data or []
        if not rows:
            return "KRW"
        tu_data = rows[0]
        lang = tu_data.get("languagecd")
        if not lang and tu_data.get("tenantid"):
            t = svc.table("tenants").select("languagecd").eq("tenantid", tu_data["tenantid"]).maybe_single().execute()
            if t and t.data:
                lang = t.data.get("languagecd")
        # 언어 미설정(lang=None)은 기존 사용자 대다수가 한국어라 KRW로 처리 — 명시적으로 ko가 아닌 언어일 때만 USD
        return "USD" if lang and lang != "ko" else "KRW"
    except Exception:
        return "KRW"


def _attach_prices(svc, rows: list, currencycd: str = "KRW") -> None:
    """products 행에 config_price 기준 현재 유효한 price/currencycd를 채운다 (in-place)."""
    productcds = [r["productcd"] for r in rows if r.get("productcd")]
    if not productcds:
        return
    today = date.today().isoformat()
    price_rows = (
        svc.table("config_price")
        .select("productcd,billingtermcd,price,currencycd,effectivefromdt,effectivetodt")
        .in_("productcd", productcds)
        .eq("currencycd", currencycd)
        .lte("effectivefromdt", today)
        .execute()
        .data or []
    )
    price_map = {}
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
        r["currencycd"] = price_row["currencycd"] if price_row else None


def _get_current_price(svc, productcd: str, billingtermcd: Optional[str], currencycd: str = "KRW"):
    """productcd의 오늘 기준 유효 가격(price)을 반환. 없으면 None."""
    rows = (
        svc.table("config_price").select("price")
        .eq("productcd", productcd).eq("currencycd", currencycd).eq("billingtermcd", billingtermcd)
        .lte("effectivefromdt", date.today().isoformat())
        .order("effectivefromdt", desc=True).limit(1)
        .execute().data or []
    )
    return rows[0]["price"] if rows else None


def _lookup_account_billing(svc, accountuid: str) -> Optional[dict]:
    """계정의 통합 결제일 앵커 행(account_billing) 조회. 없으면 None(=이 계정의 최초 유료 결제 시점)."""
    row = svc.table("account_billing").select("*").eq("accountuid", accountuid).maybe_single().execute()
    return row.data if row and row.data else None


def _bootstrap_account_billing(svc, accountuid: str, tenantid, user_id: str, today: date) -> None:
    """계정의 최초 유료 결제 성공 직후 호출 — 오늘을 기준으로 통합 결제일 앵커 행을 새로 만든다."""
    next_dt = _next_billing_date(today.day, today)
    svc.table("account_billing").insert({
        "accountuid": accountuid,
        "tenantid": int(tenantid),
        "billingday": today.day,
        "next_billing_dt": next_dt.isoformat(),
        "last_billed_dt": today.isoformat(),
        "billing_status": "Active",
        "creator": user_id,
    }).execute()


def _calc_prorated_amount(full_price: float, today: date, next_billing_dt: date) -> int:
    """오늘부터 next_billing_dt(통합 결제일) 직전까지 남은 일수만큼, 30일 기준 일할 계산한 금액.
    남은 일수가 0 이하이면 0원(다음 통합 결제 사이클에 자동으로 포함되므로 별도 청구 불필요)."""
    remaining_days = (next_billing_dt - today).days
    if remaining_days <= 0:
        return 0
    prorated = round(full_price * remaining_days / 30)
    return max(0, min(prorated, round(full_price)))


def _issue_invoice_for_purchase(
    svc, user_id: str, tenantid, accountuid: str, paymentuid: Optional[str],
    productcd: str, item_type: str, desc: str, quantity: int, price: float,
) -> None:
    """1회성 구매(플랜 변경/인원·기능 추가/크레딧 구매 등) 건에 대해 invoices/invoice_items 1건씩 발급한다.
    정기 자동 재청구(payments.py의 _process_account_billing_cycle)만 invoice를 남기고 이 경로들은
    payments 행만 남기던 것을 2026-08-31에 통일함 — 결제 게이트(_require_payment_and_charge)
    한 곳에서만 호출하므로 호출부마다 중복 구현할 필요 없다.

    tax-inclusive 총액(price)에서 부가세를 역산한다 — config_price.unit_price/unit_tax가 정확히
    price의 90%/10%로 등록돼 있는 것과 동일한 비율([[payment_schema_cleanup]] 참고)이라
    subtotal_amount = round(price*0.9), tax_amount = 나머지로 맞춰 반올림 오차 없이 합이 price와
    정확히 일치하게 한다. 일할 계산(override_amount)이 적용된 금액이 들어와도 이 비율은 그대로 유지된다.
    """
    today_iso = date.today().isoformat()
    subtotal_amount = round(price * 0.9)
    tax_amount = price - subtotal_amount

    invoice_no_rows = (
        svc.table("invoices").select("invoice_number").eq("tenantid", int(tenantid))
        .order("invoice_number", desc=True).limit(1).execute().data or []
    )
    next_invoice_number = (invoice_no_rows[0]["invoice_number"] + 1) if invoice_no_rows else 1

    inv_resp = svc.table("invoices").insert({
        "tenantid": int(tenantid), "accountuid": accountuid, "invoice_number": next_invoice_number,
        "invoice_status": "Paid",
        "billing_period_from": today_iso, "billing_period_to": today_iso,
        "invoice_date": today_iso, "due_date": today_iso,
        "currencycd": "KRW", "subtotal_amount": subtotal_amount, "tax_amount": tax_amount,
        "discount_amount": 0, "total_amount": price, "paid_amount": price,
        "creator": user_id,
    }).execute()
    invoiceuid = inv_resp.data[0]["invoiceuid"]

    svc.table("invoice_items").insert({
        "tenantid": int(tenantid), "invoiceuid": invoiceuid, "productcd": productcd,
        "item_type": item_type, "desc": desc, "quantity": quantity,
        "regular_price": subtotal_amount, "price": subtotal_amount,
        "regular_amount": price, "amount": price,
        "creator": user_id,
    }).execute()

    if paymentuid:
        svc.table("payments").update({"invoiceuid": invoiceuid}).eq("paymentuid", paymentuid).execute()


def _require_payment_and_charge(svc, user_id: str, tenantid, accountuid: str, productcd: str, billingtermcd: Optional[str], order_name: str, quantity: int = 1, override_amount: Optional[float] = None, item_type: str = "Subscription") -> dict:
    """
    실제 상품 구매(플랜 변경/인원·기능 추가/크레딧 구매 등) 공통 결제 게이트.
    가격 조회 → 계정 기본 결제수단 확인 → 그 결제수단으로 실제 청구 → 성공 시 invoice 1건 발급까지 수행한다.
    가격 미등록/결제수단 없음/청구 실패 시 적절한 HTTPException을 던진다.
    성공 시 execute_charge()의 반환값(paymentuid 포함)을 그대로 돌려준다.
    quantity: 단가 상품을 N개 단위로 한 번에 청구할 때(예: Add User 수량 구매) 사용 — 단가 × quantity가 청구된다.
    override_amount: 계산된 금액(예: 통합 결제일 기준 일할 계산액)을 그대로 청구하고 싶을 때 사용 —
      지정하면 unit_price × quantity 대신 이 금액을 청구한다(가격 미등록 여부 확인용으로 unit_price 조회는 그대로 수행).
    item_type: invoice_items.item_type — codes(codegroupcd='item_type') 값(Subscription/AddOn/Credit/Adjustment) 중 호출부가 지정.
    """
    from backend.app.routers.payments import execute_charge

    unit_price = _get_current_price(svc, productcd, billingtermcd)
    if unit_price is None:
        raise HTTPException(status_code=400, detail="가격 정보가 없어 구매할 수 없습니다.")
    price = override_amount if override_amount is not None else unit_price * quantity

    if price <= 0:
        return {"success": True, "paymentuid": None, "pgTxId": None, "skipped_zero_amount": True}

    method_row = (
        svc.table("payment_methods").select("*")
        .eq("accountuid", accountuid).eq("is_default", True).eq("payment_method_status", "Active")
        .maybe_single().execute()
    )
    if not method_row or not method_row.data:
        raise HTTPException(status_code=400, detail="msg.payment.method.required")

    charge_result = execute_charge(svc, user_id, int(tenantid), method_row.data, price, order_name, productcd=productcd, quantity=quantity)
    if not charge_result["success"]:
        raise HTTPException(status_code=400, detail=charge_result["message"])

    _issue_invoice_for_purchase(
        svc, user_id, tenantid, accountuid, charge_result.get("paymentuid"),
        productcd, item_type, order_name, quantity, price,
    )
    return charge_result


def _compensate_and_raise(svc, user_id: str, charge_result: dict, error: Exception, context: str) -> None:
    """상품 지급/처리 단계가 실패했을 때 방금 성공한 결제를 자동 환불하고 적절한 HTTPException을 던진다."""
    from backend.app.routers.payments import refund_charge

    refund_result = refund_charge(svc, user_id, charge_result["paymentuid"], f"{context} 실패로 자동 환불: {error}"[:500])
    if refund_result["success"]:
        raise HTTPException(
            status_code=500,
            detail=f"{context} 중 오류가 발생하여 결제를 자동 환불했습니다. 잠시 후 다시 시도해주세요.",
        )
    raise HTTPException(
        status_code=500,
        detail=f"{context} 중 오류가 발생했고 자동 환불도 실패했습니다. 고객센터에 문의해주세요. (결제ID: {charge_result['paymentuid']})",
    )


@router.get("/tenant-manage/team-products")
def get_tenant_manage_team_products(
    servicecd: str,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """구독 관리 화면 우측: 선택한 서비스의 Team/Enterprise 상품 목록."""
    user = _get_user(token)
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
    _attach_prices(svc, rows, currencycd=_get_user_currencycd(svc, str(user.id), tenantid))
    return {"products": rows}


class SubscriptionChangeRequest(BaseModel):
    servicecd: str
    productcd: str


@router.post("/tenant-manage/subscription-change")
def change_tenant_subscription(
    body: SubscriptionChangeRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """구독 관리 화면: 선택한 상품으로 구독 변경.

    등록된 결제수단으로 상품 가격만큼 실제(테스트 채널 기준) 청구 후에만 반영한다.
    """
    from datetime import datetime, timezone as tz, timedelta as td
    from dateutil.relativedelta import relativedelta

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    prod_row = svc.table("products").select(
        "productcd,productnm,plancd,servicecd,billingtermcd,users,credit,is_customeraikey"
    ).eq("productcd", body.productcd).maybe_single().execute()
    if not prod_row or not prod_row.data:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    product = prod_row.data

    # 새 플랜으로 바뀐 뒤의 정원(플랜 기본 인원 + 이미 보유 중인 Add User 부가상품 인원)보다
    # 현재 활성 사용자가 많으면 변경 자체를 차단한다. products.users(플랜 기본값)만 보면
    # Add User를 별도로 구매해둔 계정은 실제로는 정원이 남는데도 잘못 차단될 수 있어
    # _calc_addon_users()로 넘어오는 부가상품 인원까지 합산해서 판단한다.
    if product.get("users") is not None:
        new_total_users = product["users"] + _calc_addon_users(svc, accountuid, body.servicecd)
        active_user_count = len(
            svc.table("serviceusers").select("useruid")
            .eq("accountuid", accountuid).eq("servicecd", body.servicecd).eq("tenantid", int(tenantid))
            .eq("useyn", True).execute().data or []
        )
        if active_user_count > new_total_users:
            raise HTTPException(
                status_code=400,
                detail=f"현재 활성 사용자가 {active_user_count}명으로 변경하려는 플랜의 정원({new_total_users}명)을 초과합니다. 먼저 사용자를 비활성화해주세요.",
            )

    cur_row = svc.table("accountservices").select("*").eq("accountuid", accountuid).eq("servicecd", body.servicecd).maybe_single().execute()
    current = cur_row.data if cur_row else {}  # 없으면 해당 서비스 신규 구독

    now_utc = datetime.now(tz.utc)
    today = now_utc.date()

    account_billing = _lookup_account_billing(svc, accountuid)
    full_price = _get_current_price(svc, product["productcd"], product.get("billingtermcd"))
    if full_price is None:
        raise HTTPException(status_code=400, detail="가격 정보가 없어 구매할 수 없습니다.")
    charge_amount = (
        _calc_prorated_amount(full_price, today, date.fromisoformat(account_billing["next_billing_dt"]))
        if account_billing else full_price
    )

    charge_result = _require_payment_and_charge(
        svc, user_id, tenantid, accountuid, product["productcd"], product.get("billingtermcd"),
        product.get("productnm") or product["productcd"], override_amount=charge_amount,
    )

    # 결제는 이미 성공했으므로, 이 아래(구독 반영) 단계에서 무엇이 실패하든
    # (1) 이미 반영한 변경을 되돌리고 (2) 결제를 자동 환불한다.
    subscription_inserted = False
    accountservices_written = False
    account_billing_bootstrapped = False
    new_subscriptionuid = None
    try:
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
            raise RuntimeError("구독 저장에 실패했습니다.")
        new_subscriptionuid = new_sub_resp.data[0]["subscriptionuid"]
        subscription_inserted = True

        users = product.get("users") or 1
        # Add User 등 producttype='User' 부가상품은 플랜과 별개로 유지되는 구독이므로,
        # 플랜 변경 시 add_users를 0으로 초기화하지 않고 현재 활성(Paid) 보유분을 그대로 재계산해 반영한다
        # (예전엔 무조건 0으로 리셋해서, 이미 결제한 추가 인원이 플랜 변경할 때마다 사라지는 버그가 있었음).
        add_users = _calc_addon_users(svc, accountuid, product["servicecd"])
        accountservices_payload = {
            "old_subscriptionuid": current.get("subscriptionuid"),
            "old_productcd": current.get("productcd"),
            "old_plancd": current.get("plancd"),
            "subscriptionuid": new_subscriptionuid,
            "productcd": product["productcd"],
            "plancd": product["plancd"],
            "is_customerAIKey": product.get("is_customeraikey", False),
            "billingfirstdt": (account_billing.get("last_billed_dt") or today.isoformat()) if account_billing else today.isoformat(),
            "billingday": account_billing["billingday"] if account_billing else today.day,
            "included_users": users,
            "add_users": add_users,
            "total_users": users + add_users,
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
        accountservices_written = True

        if not account_billing:
            _bootstrap_account_billing(svc, accountuid, tenantid, user_id, today)
            account_billing_bootstrapped = True

        # Ba는 subscription_credits에 넣지 않는다 — Ba 갱신 여부는 subscriptions.subscription_status로만 판단
        # 제품 구독으로 부여되는 크레딧의 만료일은 통합 결제일(다음 재청구일 전날)에 맞춘다 —
        # 그래야 다음 통합 청구 시점에 크레딧도 같이 갱신되어 "월 사용량 리셋"이 결제일과 어긋나지 않는다.
        _next_bill_dt = date.fromisoformat(account_billing["next_billing_dt"]) if account_billing else _next_billing_date(today.day, today)
        expiredts = (_next_bill_dt - td(days=1)).isoformat()
        upsert_ba_creditbucket(
            svc,
            subscriptionuid=new_subscriptionuid,
            tenantid=int(tenantid),
            accountuid=accountuid,
            servicecd=product["servicecd"],
            chargecredit=product.get("credit", 0),
            granteddts=now_utc.isoformat(),
            expiredts=expiredts,
            startdt=today.isoformat(),
        )

        # 동일 서비스(servicecd) 상품을 24시간 이내에 다시 변경한 경우, 바로 직전 결제를 자동 환불한다
        # (예: BYOK로 바꿨다가 몇 분 뒤 일반으로 재변경 — 짧은 시간 안의 반복 변경으로 중복 청구되는 것 방지).
        # current.productcd는 이 servicecd의 직전 상품(구조상 항상 Service 타입)이므로 producttype 체크는 불필요.
        if current.get("productcd") and current["productcd"] != product["productcd"]:
            from dateutil import parser as dtparser
            prev_payments = (
                svc.table("payments").select("paymentuid,createdts")
                .eq("accountuid", accountuid).eq("productcd", current["productcd"])
                .eq("payment_status", "Success")
                .order("createdts", desc=True).limit(1).execute().data or []
            )
            if prev_payments:
                prev_dt = dtparser.parse(prev_payments[0]["createdts"])
                if now_utc - prev_dt <= td(hours=24):
                    from backend.app.routers.payments import refund_charge
                    refund_charge(
                        svc, user_id, prev_payments[0]["paymentuid"],
                        f"{product['servicecd']} 서비스 상품을 24시간 이내에 재변경하여 이전 결제를 자동 환불함",
                    )
    except Exception as e:
        if account_billing_bootstrapped:
            svc.table("account_billing").delete().eq("accountuid", accountuid).execute()
        if accountservices_written:
            if current:
                svc.table("accountservices").update(current).eq("accountuid", accountuid).eq("servicecd", body.servicecd).execute()
            else:
                svc.table("accountservices").delete().eq("accountuid", accountuid).eq("servicecd", body.servicecd).execute()
        if subscription_inserted:
            svc.table("subscriptions").delete().eq("subscriptionuid", new_subscriptionuid).execute()
        _compensate_and_raise(svc, user_id, charge_result, e, context="구독 변경")

    after_row = svc.table("accountservices").select("*").eq("accountuid", accountuid).eq("servicecd", body.servicecd).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/subscription-change", targetid=accountuid,
        before=current or None, after=after_row.data if after_row else None,
        detail={"new_subscriptionuid": new_subscriptionuid, "charge_amount": charge_amount},
        ip=get_client_ip(request),
    )
    return {"result": "success", "message": "구독이 변경되었습니다."}


@router.get("/tenant-manage/tenant-info")
def get_tenant_manage_tenant_info(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """테넌트 관리 화면 [테넌트 정보] 카드: 담당자 연락처 + 언어·타임존 표시 전용 조회."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    t_row = svc.table("tenants").select("disptenantnm,languagecd,timezone").eq("tenantid", int(tenantid)).maybe_single().execute()
    tenant = t_row.data if t_row else {}

    languagenm = None
    if tenant.get("languagecd"):
        l_row = svc.table("languages").select("languagenm").eq("languagecd", tenant["languagecd"]).maybe_single().execute()
        languagenm = l_row.data.get("languagenm") if l_row and l_row.data else None

    email, telno = "", ""
    is_whitelist_subscribed = False
    if accountuid:
        acc_row = svc.table("accounts").select("encemail,enctelno").eq("accountuid", accountuid).maybe_single().execute()
        acc = acc_row.data if acc_row else {}
        email = _decrypt(acc.get("encemail"))
        telno = _decrypt(acc.get("enctelno"))

        wl_row = svc.table("account_features").select("accountuid").eq(
            "accountuid", accountuid
        ).eq("productcd", "whitelist").maybe_single().execute()
        is_whitelist_subscribed = bool(wl_row and wl_row.data)

    return {
        "disptenantnm": tenant.get("disptenantnm"),
        "email": email,
        "telno": telno,
        "languagecd": tenant.get("languagecd"),
        "languagenm": languagenm,
        "timezone": tenant.get("timezone"),
        "is_whitelist_subscribed": is_whitelist_subscribed,
    }


@router.get("/tenant-manage/basic-info")
def get_tenant_manage_basic_info(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """[테넌트 기본 정보 설정] 화면: 아이콘·언어·타임존(tenants) + 담당자 연락처(accounts) 조회."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    t_row = svc.table("tenants").select("iconfilenm,iconfileurl,disptenantnm,languagecd,timezone").eq("tenantid", int(tenantid)).maybe_single().execute()
    tenant = t_row.data if t_row else {}

    email, telno = "", ""
    if accountuid:
        acc_row = svc.table("accounts").select("encemail,enctelno").eq("accountuid", accountuid).maybe_single().execute()
        acc = acc_row.data if acc_row else {}
        email = _decrypt(acc.get("encemail"))
        telno = _decrypt(acc.get("enctelno"))

    langs = svc.table("languages").select("languagecd,languagenm").eq("useyn", True).order("languagenm").execute().data or []
    timezones = [r["timezone"] for r in (svc.table("timezones").select("timezone").eq("useyn", True).execute().data or [])]

    return {
        "iconfilenm": tenant.get("iconfilenm"),
        "iconfileurl": resolve_display_url(get_service_client(), tenant.get("iconfileurl")),
        "disptenantnm": tenant.get("disptenantnm"),
        "languagecd": tenant.get("languagecd"),
        "timezone": tenant.get("timezone"),
        "email": email,
        "telno": telno,
        "languages": langs,
        "timezones": timezones,
    }


@router.post("/tenant-manage/basic-info")
async def save_tenant_manage_basic_info(
    request: Request,
    disptenantnm: Optional[str] = Form(None),
    languagecd: Optional[str] = Form(None),
    timezone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    telno: Optional[str] = Form(None),
    iconfile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """[테넌트 기본 정보 설정] 화면: tenants(아이콘·표현기업명·언어·타임존) + accounts(담당자 연락처) 저장."""
    user = _get_user(token)
    user_id = str(user.id)
    svc_root = get_service_client()
    svc = svc_root.schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    before_tenant = svc.table("tenants").select("iconfilenm,iconfileurl,disptenantnm,languagecd,timezone").eq("tenantid", int(tenantid)).maybe_single().execute()
    before_tenant = before_tenant.data if before_tenant else None

    tenant_payload = {}
    if disptenantnm:
        tenant_payload["disptenantnm"] = disptenantnm
    if languagecd:
        tenant_payload["languagecd"] = languagecd
    if timezone:
        tenant_payload["timezone"] = timezone
    if iconfile and iconfile.filename:
        if not accountuid:
            raise HTTPException(status_code=400, detail="msg.required.account")
        existing = svc.table("tenants").select("iconfileurl").eq("tenantid", int(tenantid)).maybe_single().execute()
        existing_url = existing.data.get("iconfileurl") if existing and existing.data else None
        icon_nm, icon_url = _save_tenant_icon(svc_root, iconfile, accountuid, existing_url)
        tenant_payload["iconfilenm"] = icon_nm
        tenant_payload["iconfileurl"] = icon_url
    if tenant_payload:
        svc.table("tenants").update(tenant_payload).eq("tenantid", int(tenantid)).execute()

    if accountuid and (email or telno):
        acc_payload = {}
        if email:
            acc_payload["encemail"] = _encrypt(email)
        if telno:
            acc_payload["enctelno"] = _encrypt(telno)
        svc.table("accounts").update(acc_payload).eq("accountuid", accountuid).execute()

    after_tenant = svc.table("tenants").select("iconfilenm,iconfileurl,disptenantnm,languagecd,timezone").eq("tenantid", int(tenantid)).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/basic-info", targetid=str(tenantid),
        before=before_tenant, after=after_tenant.data if after_tenant else None,
        detail={"email_changed": bool(email), "telno_changed": bool(telno)},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


@router.get("/tenant-manage/other-subscriptions")
def get_tenant_manage_other_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """기타 구독 관리 화면: 보유 중인 User/Feature 상품 + 구매 가능 상품 목록.

    조회(GET)는 사이드바/내정보 화면에서 모든 사용자가 '내 보유 기능' 확인용으로도 재사용하므로
    매니저/시스템테넌트 제한을 걸지 않는다 — 구매·취소(POST) 쪽에서만 제한한다.
    """
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)

    if accountuid:
        _apply_due_feature_cancellations(svc, accountuid)
        _apply_due_quantity_decreases(svc, accountuid)

    issystemtenant = True
    if tenantid:
        t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
        issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True

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
        .eq("is_sales", True)
        .order("orderno")
        .execute().data or []
    )
    prod_map = {p["productcd"]: p for p in all_products}
    # 이미 보유 중인 상품(User/Feature 공통)은 구매 목록에서 제외 — User 타입은 보유 후
    # 목록(owned)에서 수량(+/-)으로 조정하고, Feature 타입은 취소 전까지 1회만 구독 가능.
    # 테넌트 단위 보안 기능(MFA/Whitelist/SSO 등 servicecd='Tenant'인 Feature)은 시스템 테넌트(개인)엔
    # 애초에 "테넌트" 개념이 없으므로 구매 목록에서 노출하지 않는다.
    products = [
        p for p in all_products
        if p["productcd"] not in owned_productcds
        and (p["producttype"] == "Feature" or p["servicecd"] in subscribed_servicecds)
        and not (issystemtenant and p["producttype"] == "Feature" and p["servicecd"] == "Tenant")
    ]
    _attach_prices(svc, products, currencycd=_get_user_currencycd(svc, user_id, tenantid))

    owned = []
    if accountuid:
        from dateutil.relativedelta import relativedelta
        from dateutil import parser as dtparser

        currencycd = _get_user_currencycd(svc, user_id, tenantid)
        offsetminutes = _get_offsetminutes(get_service_client(), user_id, tenantid)
        rows = (
            svc.table("subscription_features").select(
                "subscriptionuid,productcd,quantity,pending_decrease_qty,pending_decrease_applydt,createdts,updatedts,canceldts"
            )
            .eq("accountuid", accountuid).eq("subscriptionstatus", "Paid")
            .order("createdts").execute().data or []
        )
        for r in rows:
            p = prod_map.get(r["productcd"], {})
            cancel_effective_date = None
            if r.get("canceldts"):
                try:
                    cancel_effective_date = _fmt_dt(
                        (dtparser.parse(r["createdts"]) + relativedelta(months=1)).isoformat(), offsetminutes
                    )
                except Exception:
                    cancel_effective_date = None
            unit_price = None
            if p.get("producttype") == "User":
                unit_price = _get_current_price(svc, r["productcd"], p.get("billingtermcd"), currencycd)
            # 적용일이 지났는데도 pending_decrease_qty가 안 비었으면 인원 초과로 보류 중인 것
            # (_apply_due_quantity_decreases 참고) — 화면에 "예정" 대신 "보류"로 구분해 보여준다.
            pending_decrease_blocked = False
            applydt = r.get("pending_decrease_applydt")
            if (r.get("pending_decrease_qty") or 0) > 0 and applydt:
                try:
                    pending_decrease_blocked = date.fromisoformat(applydt) <= date.today()
                except Exception:
                    pending_decrease_blocked = False
            owned.append({
                "subscriptionuid": r["subscriptionuid"],
                "productcd": r["productcd"],
                "productnm": p.get("productnm", r["productcd"]),
                "servicecd": p.get("servicecd"),
                "producttype": p.get("producttype"),
                "users": p.get("users"),
                "quantity": r.get("quantity") or 1,
                "pending_decrease_qty": r.get("pending_decrease_qty") or 0,
                "pending_decrease_applydt": r.get("pending_decrease_applydt"),
                "pending_decrease_blocked": pending_decrease_blocked,
                "unit_price": unit_price,
                "currencycd": currencycd if unit_price is not None else None,
                "createdts": _fmt_dt(r.get("createdts"), offsetminutes),
                "updatedts": _fmt_dt(r.get("updatedts") or r.get("createdts"), offsetminutes),
                "orderno": p.get("orderno", 999),
                "cancel_reserved": bool(r.get("canceldts")),
                "cancel_effective_date": cancel_effective_date,
            })
        owned.sort(key=lambda o: o["orderno"])

    return {"owned": owned, "products": products, "accountuid": accountuid}


class OtherSubscriptionPurchaseRequest(BaseModel):
    productcd: str
    quantity: int = 1


@router.post("/tenant-manage/other-subscription-purchase")
def purchase_tenant_manage_other_subscription(
    body: OtherSubscriptionPurchaseRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """기타 구독 관리 화면: User/Feature 상품 구매.

    등록된 결제수단으로 상품 가격만큼 실제(테스트 채널 기준) 청구 후에만 반영한다.
    Credit(producttype='Credit') 구매는 이번 범위에서 제외한다.
    quantity: producttype='User' 상품(예: Add User)만 1보다 클 수 있다 — 단가 × quantity 청구,
    이미 보유 중이면 이 엔드포인트가 아니라 /other-subscription-quantity로 조정한다.
    """
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    prod_row = svc.table("products").select(
        "productcd,productnm,servicecd,producttype,users,useyn,is_sales,billingtermcd"
    ).eq("productcd", body.productcd).maybe_single().execute()
    product = prod_row.data if prod_row else None
    if not product or product.get("producttype") not in ("User", "Feature"):
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    if not product.get("useyn") or not product.get("is_sales"):
        raise HTTPException(status_code=400, detail="더 이상 판매하지 않는 상품입니다.")

    quantity = body.quantity if product["producttype"] == "User" else 1
    if quantity < 1:
        raise HTTPException(status_code=400, detail="수량은 1개 이상이어야 합니다.")

    existing_feature = svc.table("account_features").select("accountuid").eq(
        "accountuid", accountuid
    ).eq("productcd", product["productcd"]).maybe_single().execute()
    if existing_feature and existing_feature.data:
        detail = "이미 구독 중인 기능입니다." if product["producttype"] == "Feature" else "이미 보유 중입니다. 목록에서 수량을 조정해주세요."
        raise HTTPException(status_code=400, detail=detail)

    accsvc = None
    if product["producttype"] == "User":
        svcrow = svc.table("accountservices").select(
            "included_users,add_users,total_users"
        ).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).maybe_single().execute()
        accsvc = svcrow.data if svcrow else None
        if not accsvc:
            raise HTTPException(status_code=400, detail="먼저 해당 서비스를 구독해야 합니다.")

    today = datetime.now(tz.utc).date()
    account_billing = _lookup_account_billing(svc, accountuid)
    unit_price = _get_current_price(svc, product["productcd"], product.get("billingtermcd"))
    if unit_price is None:
        raise HTTPException(status_code=400, detail="가격 정보가 없어 구매할 수 없습니다.")
    full_price = unit_price * quantity
    charge_amount = (
        _calc_prorated_amount(full_price, today, date.fromisoformat(account_billing["next_billing_dt"]))
        if account_billing else full_price
    )

    charge_result = _require_payment_and_charge(
        svc, user_id, tenantid, accountuid, product["productcd"], product.get("billingtermcd"),
        product.get("productnm") or product["productcd"], quantity=quantity, override_amount=charge_amount,
        item_type="AddOn",
    )

    # 결제는 이미 성공했으므로, 이 아래(상품 지급) 단계에서 무엇이 실패하든
    # (1) 이미 반영한 변경을 되돌리고 (2) 결제를 자동 환불한다.
    subscription_feature_id = str(uuid.uuid4())
    subscription_feature_inserted = False
    account_features_written = False
    previous_account_features = None
    accountservices_updated = False
    account_billing_bootstrapped = False
    config_tenants_touched: list[tuple[str, bool]] = []  # (configcd, previous_value)
    try:
        svc.table("subscription_features").insert({
            "subscriptionuid": subscription_feature_id,
            "productcd": product["productcd"],
            "tenantid": int(tenantid),
            "accountuid": accountuid,
            "quantity": quantity,
            "subscriptionstatus": "Paid",
            "creator": user_id,
        }).execute()
        subscription_feature_inserted = True

        existing_af = svc.table("account_features").select("*").eq(
            "accountuid", accountuid
        ).eq("productcd", product["productcd"]).maybe_single().execute()
        if existing_af and existing_af.data:
            previous_account_features = existing_af.data
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
        account_features_written = True

        if product["producttype"] == "User":
            new_add_users = (accsvc.get("add_users") or 0) + (product.get("users") or 0) * quantity
            new_total_users = (accsvc.get("included_users") or 0) + new_add_users
            svc.table("accountservices").update({
                "add_users": new_add_users,
                "total_users": new_total_users,
                "updater": user_id,
            }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()
            accountservices_updated = True

        if not account_billing:
            _bootstrap_account_billing(svc, accountuid, tenantid, user_id, today)
            account_billing_bootstrapped = True

        if product["productcd"] == "mfa":
            prev = svc.table("config_tenants").select("configcd,value").eq("tenantid", int(tenantid)).eq("configcd", "Is_MFA").execute().data or []
            svc.table("config_tenants").update({"value": True}).eq("tenantid", int(tenantid)).eq("configcd", "Is_MFA").execute()
            config_tenants_touched.extend((r["configcd"], r["value"]) for r in prev)

        if product["productcd"] == "whitelist":
            prev = svc.table("config_tenants").select("configcd,value").eq("tenantid", int(tenantid)).in_(
                "configcd", ["Is_Manager_IP_Allow", "Is_User_IP_Allow"]
            ).execute().data or []
            svc.table("config_tenants").update({"value": True}).eq("tenantid", int(tenantid)).in_(
                "configcd", ["Is_Manager_IP_Allow", "Is_User_IP_Allow"]
            ).execute()
            config_tenants_touched.extend((r["configcd"], r["value"]) for r in prev)
    except Exception as e:
        for configcd, prev_value in config_tenants_touched:
            svc.table("config_tenants").update({"value": prev_value}).eq("tenantid", int(tenantid)).eq("configcd", configcd).execute()
        if account_billing_bootstrapped:
            svc.table("account_billing").delete().eq("accountuid", accountuid).execute()
        if accountservices_updated:
            svc.table("accountservices").update({
                "add_users": accsvc.get("add_users") or 0,
                "total_users": accsvc.get("total_users") or 0,
            }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()
        if account_features_written:
            if previous_account_features:
                svc.table("account_features").update(previous_account_features).eq("accountuid", accountuid).eq("productcd", product["productcd"]).execute()
            else:
                svc.table("account_features").delete().eq("accountuid", accountuid).eq("productcd", product["productcd"]).execute()
        if subscription_feature_inserted:
            svc.table("subscription_features").delete().eq("subscriptionuid", subscription_feature_id).execute()
        _compensate_and_raise(svc, user_id, charge_result, e, context="상품 지급")

    after_af = svc.table("account_features").select("*").eq("accountuid", accountuid).eq("productcd", product["productcd"]).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="create", targettype="settings/tenant-manage/other-subscription-purchase", targetid=accountuid,
        before=previous_account_features, after=after_af.data if after_af else None,
        detail={"productcd": product["productcd"], "quantity": quantity, "charge_amount": charge_amount},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


class OtherSubscriptionCancelRequest(BaseModel):
    subscriptionuid: str
    cancel_reasoncd: str
    cancel_reasondesc: Optional[str] = None


@router.post("/tenant-manage/other-subscription-cancel")
def cancel_tenant_manage_other_subscription(
    body: OtherSubscriptionCancelRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """기타 구독 관리 화면: User/Feature 구매 건 해지 예약.

    개인 Pro 해지와 동일하게 즉시 취소하지 않는다 — 이미 결제한 기간(구매일+1개월)까지는
    그대로 이용 가능하게 두고, 실제 접근 권한 회수는 주기가 끝난 뒤
    _apply_due_feature_cancellations()가 지연 평가로 처리한다."""
    from datetime import datetime, timezone as tz
    from dateutil.relativedelta import relativedelta
    from dateutil import parser as dtparser

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    sf_row = svc.table("subscription_features").select(
        "subscriptionuid,productcd,accountuid,subscriptionstatus,createdts,canceldts"
    ).eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    sf = sf_row.data if sf_row else None
    if not sf or sf.get("accountuid") != accountuid:
        raise HTTPException(status_code=404, detail="구독 내역을 찾을 수 없습니다.")
    if sf.get("subscriptionstatus") == "Cancelled":
        raise HTTPException(status_code=400, detail="이미 취소된 구독입니다.")
    if sf.get("canceldts"):
        raise HTTPException(status_code=400, detail="이미 해지가 예약되어 있습니다.")

    _product_row = svc.table("products").select("producttype").eq("productcd", sf["productcd"]).maybe_single().execute()
    product = _product_row.data if _product_row else None
    if product and product.get("producttype") == "User":
        raise HTTPException(status_code=400, detail="msg.quantity.decrease.use_stepper")

    now_utc = datetime.now(tz.utc)
    svc.table("subscription_features").update({
        "canceluseruid": user_id,
        "canceldts": now_utc.isoformat(),
        "cancel_reasoncd": body.cancel_reasoncd,
        "cancel_reasondesc": body.cancel_reasondesc,
        "updater": user_id,
        "updatedts": now_utc.isoformat(),
    }).eq("subscriptionuid", body.subscriptionuid).execute()

    effective_date = (dtparser.parse(sf["createdts"]) + relativedelta(months=1)).isoformat()
    after_sf = svc.table("subscription_features").select("*").eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/other-subscription-cancel", targetid=body.subscriptionuid,
        before=sf, after=after_sf.data if after_sf else None,
        ip=get_client_ip(request),
    )
    return {"result": "success", "effective_date": effective_date}


class OtherSubscriptionCancelUndoRequest(BaseModel):
    subscriptionuid: str


@router.post("/tenant-manage/other-subscription-cancel-undo")
def undo_cancel_tenant_manage_other_subscription(
    body: OtherSubscriptionCancelUndoRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """기타 구독 관리 화면: 예약된 해지 철회 — 결제 주기가 끝나기 전까지만 가능."""
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    sf_row = svc.table("subscription_features").select(
        "subscriptionuid,accountuid,subscriptionstatus,canceldts"
    ).eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    sf = sf_row.data if sf_row else None
    if not sf or sf.get("accountuid") != accountuid:
        raise HTTPException(status_code=404, detail="구독 내역을 찾을 수 없습니다.")
    if not sf.get("canceldts"):
        raise HTTPException(status_code=400, detail="예약된 해지가 없습니다.")

    svc.table("subscription_features").update({
        "canceluseruid": None,
        "canceldts": None,
        "cancel_reasoncd": None,
        "cancel_reasondesc": None,
        "updater": user_id,
        "updatedts": datetime.now(tz.utc).isoformat(),
    }).eq("subscriptionuid", body.subscriptionuid).execute()

    after_sf = svc.table("subscription_features").select("*").eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/other-subscription-cancel-undo", targetid=body.subscriptionuid,
        before=sf, after=after_sf.data if after_sf else None,
        ip=get_client_ip(request),
    )
    return {"result": "success"}


class OtherSubscriptionQuantityRequest(BaseModel):
    subscriptionuid: str
    delta: int


@router.post("/tenant-manage/other-subscription-quantity")
def update_tenant_manage_other_subscription_quantity(
    body: OtherSubscriptionQuantityRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """기타 구독 관리 화면: 이미 보유 중인 producttype='User' 상품(Add User)의 수량을 조정한다.

    delta > 0(증가): 예약된 감소(pending_decrease_qty)가 있으면 우선 상쇄(무료)하고,
      상쇄하고 남는 만큼만 즉시 결제 후 quantity에 즉시 반영한다.
    delta < 0(감소): 결제/즉시 반영 없이 pending_decrease_qty에 누적 — 다음 결제일
      (accountservices.billingday 기준)이 되면 _apply_due_quantity_decreases()가 실제로 차감한다.
    """
    from datetime import datetime, timezone as tz

    if body.delta == 0:
        raise HTTPException(status_code=400, detail="변경할 수량을 입력해주세요.")

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    sf_row = svc.table("subscription_features").select(
        "subscriptionuid,productcd,accountuid,quantity,pending_decrease_qty,subscriptionstatus,canceldts"
    ).eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    sf = sf_row.data if sf_row else None
    if not sf or sf.get("accountuid") != accountuid:
        raise HTTPException(status_code=404, detail="구독 내역을 찾을 수 없습니다.")
    if sf.get("subscriptionstatus") != "Paid":
        raise HTTPException(status_code=400, detail="취소된 구독입니다.")
    if sf.get("canceldts"):
        raise HTTPException(status_code=400, detail="해지가 예약된 상품은 수량을 조정할 수 없습니다.")

    _product_row = svc.table("products").select(
        "productcd,productnm,servicecd,producttype,users,billingtermcd,useyn,is_sales"
    ).eq("productcd", sf["productcd"]).maybe_single().execute()
    product = _product_row.data if _product_row else None
    if not product or product.get("producttype") != "User":
        raise HTTPException(status_code=400, detail="수량 조정을 지원하지 않는 상품입니다.")

    quantity = sf.get("quantity") or 1
    pending = sf.get("pending_decrease_qty") or 0

    if body.delta > 0:
        offset = min(body.delta, pending)
        new_pending = pending - offset
        charge_qty = body.delta - offset

        charge_result = None
        account_billing_bootstrapped = False
        if charge_qty > 0:
            if not product.get("useyn") or not product.get("is_sales"):
                raise HTTPException(status_code=400, detail="더 이상 판매하지 않는 상품입니다.")
            today = datetime.now(tz.utc).date()
            account_billing = _lookup_account_billing(svc, accountuid)
            unit_price = _get_current_price(svc, product["productcd"], product.get("billingtermcd"))
            if unit_price is None:
                raise HTTPException(status_code=400, detail="가격 정보가 없어 구매할 수 없습니다.")
            full_price = unit_price * charge_qty
            charge_amount = (
                _calc_prorated_amount(full_price, today, date.fromisoformat(account_billing["next_billing_dt"]))
                if account_billing else full_price
            )
            charge_result = _require_payment_and_charge(
                svc, user_id, tenantid, accountuid, product["productcd"], product.get("billingtermcd"),
                product.get("productnm") or product["productcd"], quantity=charge_qty, override_amount=charge_amount,
                item_type="AddOn",
            )
            if not account_billing:
                _bootstrap_account_billing(svc, accountuid, tenantid, user_id, today)
                account_billing_bootstrapped = True

        new_quantity = quantity + charge_qty
        try:
            svc.table("subscription_features").update({
                "quantity": new_quantity,
                "pending_decrease_qty": new_pending,
                "pending_decrease_applydt": None if new_pending == 0 else sf.get("pending_decrease_applydt"),
                "updater": user_id,
                "updatedts": datetime.now(tz.utc).isoformat(),
            }).eq("subscriptionuid", body.subscriptionuid).execute()

            if charge_qty > 0:
                svcrow = svc.table("accountservices").select(
                    "included_users,add_users"
                ).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).maybe_single().execute()
                accsvc = svcrow.data if svcrow else None
                if accsvc:
                    new_add_users = (accsvc.get("add_users") or 0) + (product.get("users") or 0) * charge_qty
                    new_total_users = (accsvc.get("included_users") or 0) + new_add_users
                    svc.table("accountservices").update({
                        "add_users": new_add_users,
                        "total_users": new_total_users,
                        "updater": user_id,
                    }).eq("accountuid", accountuid).eq("servicecd", product["servicecd"]).execute()
        except Exception as e:
            if account_billing_bootstrapped:
                svc.table("account_billing").delete().eq("accountuid", accountuid).execute()
            if charge_result:
                _compensate_and_raise(svc, user_id, charge_result, e, context="수량 증가 반영")
            raise

        after_sf = svc.table("subscription_features").select("*").eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
        log_work_action(
            useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
            actioncd="update", targettype="settings/tenant-manage/other-subscription-quantity", targetid=body.subscriptionuid,
            before=sf, after=after_sf.data if after_sf else None,
            detail={"delta": body.delta, "charged_quantity": charge_qty},
            ip=get_client_ip(request),
        )
        return {
            "result": "success", "quantity": new_quantity, "pending_decrease_qty": new_pending,
            "charged_quantity": charge_qty,
        }

    # delta < 0 — 감소는 결제 없이 다음 결제일에 반영되도록 예약만 한다.
    decrease_qty = -body.delta
    if pending + decrease_qty > quantity:
        raise HTTPException(status_code=400, detail="현재 보유 수량보다 많이 줄일 수 없습니다.")

    svcrow = svc.table("accountservices").select("billingday,included_users,add_users").eq(
        "accountuid", accountuid
    ).eq("servicecd", product["servicecd"]).maybe_single().execute()
    accsvc = svcrow.data if svcrow else None
    billingday = (accsvc or {}).get("billingday")
    apply_dt = _next_billing_date(billingday, date.today()) if billingday else date.today()

    new_pending = pending + decrease_qty

    # 이 감소(pending 포함, 아직 적용 안 된 것까지)가 나중에 실제 적용됐을 때의 정원을 미리 계산해
    # 현재 활성 인원과 비교한다 — 실현 불가능한 감소를 예약해두지 않도록 요청 시점에 바로 막는다.
    if accsvc:
        future_removed_users = (product.get("users") or 0) * new_pending
        future_add_users = max((accsvc.get("add_users") or 0) - future_removed_users, 0)
        future_total_users = (accsvc.get("included_users") or 0) + future_add_users
        active_cnt = svc.table("serviceusers").select("useruid", count="exact").eq(
            "accountuid", accountuid
        ).eq("servicecd", product["servicecd"]).eq("useyn", True).execute()
        active_count = active_cnt.count or 0
        if active_count > future_total_users:
            raise HTTPException(
                status_code=400,
                detail=f"현재 활성 인원이 {active_count}명이라, 정원을 {future_total_users}명으로 줄일 수 없습니다. 먼저 사용자를 비활성화해주세요.",
            )
    svc.table("subscription_features").update({
        "pending_decrease_qty": new_pending,
        "pending_decrease_applydt": apply_dt.isoformat(),
        "updater": user_id,
        "updatedts": datetime.now(tz.utc).isoformat(),
    }).eq("subscriptionuid", body.subscriptionuid).execute()

    after_sf = svc.table("subscription_features").select("*").eq("subscriptionuid", body.subscriptionuid).maybe_single().execute()
    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/other-subscription-quantity", targetid=body.subscriptionuid,
        before=sf, after=after_sf.data if after_sf else None,
        detail={"delta": body.delta},
        ip=get_client_ip(request),
    )
    return {
        "result": "success", "quantity": quantity, "pending_decrease_qty": new_pending,
        "effective_date": apply_dt.isoformat(),
    }


# ─── MFA 활성/비활성 토글 (config_tenants.Is_MFA) ──────────────────────────────
# MFA는 더 이상 구매 상품이 아니라 시스템 테넌트 제외 전 테넌트에 기본 제공되는 무료 기능이다.
# 접근 권한 자체는 항상 열려 있고, 테넌트 매니저가 이 토글로 실제 사용 여부만 켜고 끈다.
# whitelists.py의 GET/POST /whitelists/config(Is_Manager_IP_Allow/Is_User_IP_Allow)와 동일한 패턴 —
# 다만 whitelist와 달리 구매(account_features) 여부를 검사하지 않는다(무료라 검사 대상 자체가 없음).

@router.get("/tenant-manage/mfa-config")
def get_tenant_manage_mfa_config(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, _ = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    row = svc.table("config_tenants").select("value").eq(
        "tenantid", int(tenantid)
    ).eq("configcd", "Is_MFA").maybe_single().execute()
    return {"is_mfa": bool(row.data.get("value")) if row and row.data else False}


class MfaConfigSaveRequest(BaseModel):
    is_mfa: bool


@router.post("/tenant-manage/mfa-config")
def save_tenant_manage_mfa_config(
    body: MfaConfigSaveRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, _ = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    existing = svc.table("config_tenants").select("tenantid,value").eq(
        "tenantid", int(tenantid)
    ).eq("configcd", "Is_MFA").maybe_single().execute()
    before_value = existing.data.get("value") if existing and existing.data else None
    if existing and existing.data:
        svc.table("config_tenants").update({"value": body.is_mfa}).eq(
            "tenantid", int(tenantid)
        ).eq("configcd", "Is_MFA").execute()
    else:
        svc.table("config_tenants").insert({
            "tenantid": int(tenantid), "configcd": "Is_MFA", "value": body.is_mfa, "creator": user_id,
        }).execute()

    log_work_action(
        useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
        actioncd="update", targettype="settings/tenant-manage/mfa-config", targetid=str(tenantid),
        before={"Is_MFA": before_value}, after={"Is_MFA": body.is_mfa},
        ip=get_client_ip(request),
    )
    return {"result": "success"}


def _get_credit_subscriptions_data(svc, user_id: str, tenantid: str, accountuid: Optional[str]) -> dict:
    """크레딧 구매 내역 + 구매 가능 상품 조회 — 조직(tenant-manage)/개인(myinfo) 화면 공용 로직."""
    subscribed_servicecds = set()
    if accountuid:
        # plancd='Fr'(Free 플랜) 또는 is_customerAIKey=true(BYOK — 고객 자체 AI 키)인 서비스는
        # 추가 크레딧 구매 대상에서 제외한다(BYOK는 크레딧을 소진할 일이 없음, 2026-08-13 추가).
        subscribed_servicecds = {
            r["servicecd"] for r in (
                svc.table("accountservices").select("servicecd,plancd,is_customerAIKey").eq("accountuid", accountuid).execute().data or []
            )
            if r.get("plancd") != "Fr" and not r.get("is_customerAIKey")
        }

    all_products = (
        svc.table("products").select(
            "productcd,productnm,servicecd,producttype,credit,expiremonths,billingtermcd,orderno"
        )
        .eq("producttype", "Credit")
        .eq("useyn", True)
        .eq("is_sales", True)
        .order("orderno")
        .execute().data or []
    )
    prod_map = {p["productcd"]: p for p in all_products}
    # 구독 중인 서비스의 크레딧 상품만 노출
    products = [p for p in all_products if p["servicecd"] in subscribed_servicecds]
    _attach_prices(svc, products, currencycd=_get_user_currencycd(svc, user_id, tenantid))

    owned = []
    if accountuid:
        offsetminutes = _get_offsetminutes(get_service_client(), user_id, tenantid)
        rows = (
            svc.table("subscription_credits").select("subscriptionuid,productcd,quantity,createdts,expiresdts")
            .eq("accountuid", accountuid).eq("creditchargecd", "Ma")
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


def _purchase_credit_subscription(svc, user_id: str, tenantid: str, accountuid: str, productcd: str, source: str = "settings", ip: Optional[str] = None) -> None:
    """크레딧 상품 구매 — 조직(tenant-manage)/개인(myinfo) 화면 공용 로직.

    결제 연동 전까지는 저장 즉시 subscription_credits / creditbuckets에 반영한다.
    추후 결제 게이트가 추가되면 결제 성공 콜백에서 이 로직을 호출하도록 변경해야 한다.
    """
    from datetime import datetime, timezone as tz
    from dateutil.relativedelta import relativedelta

    prod_row = svc.table("products").select(
        "productcd,productnm,servicecd,producttype,credit,billingtermcd"
    ).eq("productcd", productcd).maybe_single().execute()
    product = prod_row.data if prod_row else None
    if not product or product.get("producttype") != "Credit":
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    if product.get("servicecd"):
        svcrow = svc.table("accountservices").select("servicecd,plancd,is_customerAIKey").eq(
            "accountuid", accountuid
        ).eq("servicecd", product["servicecd"]).maybe_single().execute()
        if not svcrow or not svcrow.data:
            raise HTTPException(status_code=400, detail="먼저 해당 서비스를 구독해야 합니다.")
        if svcrow.data.get("plancd") == "Fr":
            raise HTTPException(status_code=400, detail="Free 플랜은 추가 크레딧을 구매할 수 없습니다.")
        if svcrow.data.get("is_customerAIKey"):
            raise HTTPException(status_code=400, detail="msg.credit.purchase.byok.blocked")

    # 등록된 결제수단으로 상품 가격만큼 실제(테스트 채널 기준) 청구 후에만 크레딧을 지급한다.
    charge_result = _require_payment_and_charge(
        svc, user_id, tenantid, accountuid, productcd, product.get("billingtermcd"), product.get("productnm") or productcd,
        item_type="Credit",
    )

    # 결제는 이미 성공했으므로, 이 아래(크레딧 지급) 단계에서 무엇이 실패하든
    # (1) 이미 만들어진 크레딧 레코드가 있으면 되돌리고 (2) 결제를 자동 환불한다.
    # ("결제는 됐는데 크레딧은 안 들어간" 상태 방지 — 진짜 DB 트랜잭션이 아니라 앱단 보정이라
    #  offset_negative_ba_bucket 내부에서 일부만 반영된 채 실패하는 경우까지는 못 되돌린다.)
    new_subscriptionuid = str(uuid.uuid4())
    credit_inserted = False
    bucket_inserted = False
    try:
        now_utc = datetime.now(tz.utc)
        # creditchargecd가 Ba가 아닌 크레딧은 구매 시점 + 1년 - 1일을 만료일로 고정
        expiresdts = (now_utc + relativedelta(years=1) - timedelta(days=1)).isoformat()
        credit = product.get("credit") or 0
        creditchargecd = "Ma"

        # creditbuckets.startdt는 같은 tenantid/accountuid/servicecd의 아직 유효한(만료 전) Ba 버킷 startdt를 그대로 이관
        ba_rows = (
            svc.table("creditbuckets").select("startdt")
            .eq("tenantid", int(tenantid)).eq("accountuid", accountuid)
            .eq("servicecd", product.get("servicecd")).eq("creditchargecd", "Ba")
            .gt("expiredts", now_utc.isoformat())
            .order("startdt", desc=True).limit(1)
            .execute().data or []
        )
        if not ba_rows:
            raise RuntimeError("기준이 되는 플랜 기본(Ba) 크레딧 정보를 찾을 수 없습니다.")
        startdt = ba_rows[0]["startdt"]

        svc.table("subscription_credits").insert({
            "subscriptionuid": new_subscriptionuid,
            "creditchargecd": creditchargecd,
            "creditdesc": product.get("productnm"),
            "productcd": product["productcd"],
            "tenantid": int(tenantid),
            "accountuid": accountuid,
            "servicecd": product.get("servicecd"),
            "quantity": credit,
            "expiresdts": expiresdts,
            "creator": user_id,
        }).execute()
        credit_inserted = True

        svc.table("creditbuckets").insert({
            "subscriptionuid": new_subscriptionuid,
            "tenantid": int(tenantid),
            "accountuid": accountuid,
            "servicecd": product.get("servicecd"),
            "chargecredit": credit,
            "creditchargecd": creditchargecd,
            "priorityno": CREDITCHARGECD_PRIORITY[creditchargecd],
            "usecredit": 0,
            "remaincredit": credit,
            "granteddts": now_utc.isoformat(),
            "expiredts": expiresdts,
            "startdt": startdt,
        }).execute()
        bucket_inserted = True

        # 기존 Ba(기본) 버킷이 마이너스 상태면, 이번에 새로 산 버킷에서 그 마이너스분만큼 차감해 상쇄한다
        # (Ba는 0으로 정리 — utilsPrj/credit_helper.offset_negative_ba_bucket 참고)
        offset_negative_ba_bucket(
            svc,
            tenantid=int(tenantid),
            accountuid=accountuid,
            servicecd=product.get("servicecd"),
            new_bucket_subscriptionuid=new_subscriptionuid,
        )

        after_bucket = svc.table("creditbuckets").select("*").eq("subscriptionuid", new_subscriptionuid).maybe_single().execute()
        log_work_action(
            useruid=user_id, tenantid=int(tenantid), servicecd="Tenant",
            actioncd="create", targettype=f"{source}/credit-purchase", targetid=new_subscriptionuid,
            after=after_bucket.data if after_bucket else None,
            detail={"productcd": productcd, "credit": credit},
            ip=ip,
        )
    except Exception as e:
        if bucket_inserted:
            svc.table("creditbuckets").delete().eq("subscriptionuid", new_subscriptionuid).execute()
        if credit_inserted:
            svc.table("subscription_credits").delete().eq("subscriptionuid", new_subscriptionuid).execute()
        _compensate_and_raise(svc, user_id, charge_result, e, context="크레딧 지급")


class CreditSubscriptionPurchaseRequest(BaseModel):
    productcd: str


@router.get("/tenant-manage/credit-subscriptions")
def get_tenant_manage_credit_subscriptions(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """크레딧 구매 관리 화면(조직 전용): 구매 내역 + 구매 가능 크레딧 상품 목록."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

    return _get_credit_subscriptions_data(svc, user_id, tenantid, accountuid)


@router.post("/tenant-manage/credit-subscription-purchase")
def purchase_tenant_manage_credit_subscription(
    body: CreditSubscriptionPurchaseRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """크레딧 구매 관리 화면(조직 전용): 크레딧 상품 구매."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    _purchase_credit_subscription(svc, user_id, tenantid, accountuid, body.productcd, source="settings/tenant-manage", ip=get_client_ip(request))
    return {"result": "success"}


@router.get("/myinfo/credit-purchase")
def get_myinfo_credit_purchase(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """개인(시스템 테넌트) 계정용 크레딧 구매 화면: 구매 내역 + 구매 가능 크레딧 상품 목록."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_system_tenant(svc, tenantid)

    return _get_credit_subscriptions_data(svc, user_id, tenantid, accountuid)


@router.post("/myinfo/credit-purchase")
def purchase_myinfo_credit(
    body: CreditSubscriptionPurchaseRequest,
    request: Request,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """개인(시스템 테넌트) 계정용 크레딧 구매 화면: 크레딧 상품 구매."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_system_tenant(svc, tenantid)
    if not accountuid:
        raise HTTPException(status_code=400, detail="accountuid를 확인할 수 없습니다.")

    _purchase_credit_subscription(svc, user_id, tenantid, accountuid, body.productcd, source="settings/myinfo", ip=get_client_ip(request))
    return {"result": "success"}


@router.get("/tenant-manage/overview")
def get_tenant_manage_overview(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """전체 현황 화면: 서비스별 프로젝트/인원/크레딧 현황."""
    from datetime import datetime, timezone as tz

    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(svc, user_id, tenantid)
    _require_tenant_manager(svc, user_id, tenantid)
    _require_not_system_tenant(svc, tenantid)

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
            svc.table("creditbuckets").select("servicecd,chargecredit,usecredit,expiredts")
            .eq("accountuid", accountuid).gt("expiredts", now_utc.isoformat()).execute().data or []
        )
        credit_totals = {}
        for r in cb_rows:
            scd = r["servicecd"]
            c = credit_totals.setdefault(scd, {"total_credit": 0, "used_credit": 0})
            c["total_credit"] += r.get("chargecredit") or 0
            c["used_credit"] += r.get("usecredit") or 0

        remain_rows = (
            svc.table("vw_creditbucketsums").select("servicecd,remaincredit")
            .eq("accountuid", accountuid).execute().data or []
        )
        remain_map = {}
        for r in remain_rows:
            scd = r["servicecd"]
            remain_map[scd] = remain_map.get(scd, 0) + (r.get("remaincredit") or 0)

        for scd, s in svc_map.items():
            credit = credit_totals.get(scd, {"total_credit": 0, "used_credit": 0})
            services.append({
                "servicecd": scd,
                "projects": project_counts.get(scd, 0),
                "total_users": s["total_users"],
                "used_users": used_user_counts.get(scd, 0),
                "total_credit": credit["total_credit"],
                "used_credit": credit["used_credit"],
                "remain_credit": remain_map.get(scd, 0),
            })
        code_rows = svc.table("codes").select("codevalue,orderno").eq("codegroupcd", "servicecd").execute().data or []
        order_map = {r["codevalue"]: r.get("orderno") if r.get("orderno") is not None else 999 for r in code_rows}
        services.sort(key=lambda s: order_map.get(s["servicecd"], 999))

    return {
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
        tu_row = (tu.data if tu else None) or {}
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
def create_tenant_subscription(body: TenantSubscriptionRequest, request: Request, token: str = Depends(get_token)):
    """신규 테넌트 셀프 생성: tenants(useyn=true) / tenantusers(rolecd=M) / accounts(accounttype=T) 동시 생성."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    tenant_data = {
        "tenantnm": body.tenantnm,
        "disptenantnm": body.tenantnm,
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

    _save_default_tenant_configs(new_tenantid, user_id)

    log_work_action(
        useruid=user_id, tenantid=new_tenantid, servicecd="Tenant",
        actioncd="create", targettype="settings/tenant-subscription", targetid=new_tenantid,
        after={"tenants": tenant_data, "tenantusers": tenantuser_data},
        ip=get_client_ip(request),
    )
    return {"tenantid": new_tenantid, "tenantnm": body.tenantnm}


@router.post("/myinfo/timezone")
def update_timezone(body: UpdateTimezoneRequest, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    before_q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone").eq("useruid", user.id)
    if tenantid:
        before_q = before_q.eq("tenantid", tenantid)
    before = before_q.execute().data
    q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").update({"timezone": body.timezone}).eq("useruid", user.id)
    if tenantid:
        q = q.eq("tenantid", tenantid)
    q.execute()
    offsetminutes = None
    if body.timezone:
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", body.timezone).maybe_single().execute()
        if tz_row and tz_row.data:
            offsetminutes = tz_row.data.get("offsetminutes")
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="update", targettype="settings/myinfo/timezone", targetid=str(user.id),
        before=before[0] if before else None, after={"timezone": body.timezone},
        ip=get_client_ip(request),
    )
    return {"status": "ok", "offsetminutes": offsetminutes}
