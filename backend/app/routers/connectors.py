"""Connectors router — API connector management"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()

AUTH_TYPES    = ["NONE", "API_KEY", "BASIC", "OAUTH2"]
HTTP_METHODS  = ["GET", "POST"]
KEY_LOCATIONS = ["header", "query", "body"]
GRANT_TYPES   = ["client_credentials", "authorization_code", "password", "implicit"]


def _get_tenantid(sb, user_id: str) -> Optional[int]:
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("tenantusers")
        .select("tenantid")
        .eq("useruid", user_id)
        .eq("useyn", True)
        .execute()
        .data
    )
    return rows[0]["tenantid"] if rows else None


def _parse_secret(secret_json: Optional[str]) -> dict:
    if not secret_json:
        return {}
    try:
        data = json.loads(secret_json)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_secret_json(authtype: str, body, existing_json: Optional[str] = None) -> Optional[str]:
    """authtype에 맞는 시크릿 필드를 JSON으로 조합. 비밀번호 계열은 기존 값과 병합."""
    existing = _parse_secret(existing_json)
    secret: dict = {}

    if authtype == "API_KEY":
        # api_key_value: 빈 문자열이면 기존 값 유지
        secret["api_key_value"] = body.api_key_value if body.api_key_value else existing.get("api_key_value")

    elif authtype == "BASIC":
        secret["username"] = body.username if body.username is not None else existing.get("username")
        # password: 빈 값이면 기존 값 유지
        secret["password"] = body.password if body.password else existing.get("password")

    elif authtype == "OAUTH2":
        # oauth_client_secret: 빈 값이면 기존 값 유지
        secret["oauth_client_secret"] = body.oauth_client_secret if body.oauth_client_secret else existing.get("oauth_client_secret")
        secret["refresh_token"] = body.refresh_token if body.refresh_token is not None else existing.get("refresh_token")

    secret = {k: v for k, v in secret.items() if v is not None}
    return json.dumps(secret, ensure_ascii=False) if secret else None


class ConnectorSaveRequest(BaseModel):
    # connectors
    connuid:            Optional[str]  = None
    connnm:             str
    desc:               Optional[str]  = None
    useyn:              bool           = True
    # conn_apis (apitype 항상 REST — 프론트에서 노출 불필요)
    baseurl:            Optional[str]  = None
    authtype:           Optional[str]  = "NONE"
    health:             Optional[str]  = None
    health_method:      Optional[str]  = "GET"
    authtest:           Optional[str]  = None
    authtest_method:    Optional[str]  = "GET"
    # conn_api_credentials (비시크릿 필드)
    credentialuid:      Optional[str]  = None
    api_key_name:       Optional[str]  = None
    api_key_locationcd: Optional[str]  = None
    oauth_client_id:    Optional[str]  = None
    token_endpoint:     Optional[str]  = None
    authorization_type: Optional[str]  = None
    redirect_url:       Optional[str]  = None
    scope:              Optional[str]  = None
    grant_type:         Optional[str]  = None
    is_active:          bool           = True
    # 시크릿 필드 — secret_path JSON으로 조합됨
    api_key_value:       Optional[str] = None   # API_KEY
    username:            Optional[str] = None   # BASIC
    password:            Optional[str] = None   # BASIC
    oauth_client_secret: Optional[str] = None   # OAUTH2
    refresh_token:       Optional[str] = None   # OAUTH2


@router.get("")
def list_connectors(token: str = Depends(get_token)):
    sb   = _sb(token)
    user = _get_user(token)
    tenantid = _get_tenantid(sb, user.id)

    conns = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("*")
        .eq("tenantid", tenantid)
        .eq("conntype", "api")
        .order("createdts")
        .execute()
        .data
    ) or []

    meta = {
        "authtypes":    AUTH_TYPES,
        "httpmethods":  HTTP_METHODS,
        "keylocations": KEY_LOCATIONS,
        "granttypes":   GRANT_TYPES,
    }

    if not conns:
        return {"connectors": [], **meta}

    conn_uids = [c["connuid"] for c in conns]

    apis = {
        r["connuid"]: r
        for r in (
            sb.schema(SUPABASE_SCHEMA).table("conn_apis")
            .select("*").in_("connuid", conn_uids).execute().data or []
        )
    }
    creds = {
        r["connuid"]: r
        for r in (
            sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials")
            .select("*").in_("connuid", conn_uids).execute().data or []
        )
    }

    NON_SECRET_CRED_FIELDS = (
        "credentialuid", "api_key_name", "api_key_locationcd",
        "oauth_client_id", "token_endpoint", "authorization_type",
        "redirect_url", "scope", "grant_type", "is_active",
        "auth_statuscd", "last_error_message",
    )
    result = []
    for c in conns:
        uid = c["connuid"]
        row = dict(c)
        api = apis.get(uid, {})
        cred = creds.get(uid, {})

        for k, v in api.items():
            if k not in ("connuid", "tenantid", "creator", "createdts"):
                row[k] = v

        for k in NON_SECRET_CRED_FIELDS:
            row[k] = cred.get(k)

        # secret_path JSON → 개별 필드로 분해
        secrets = _parse_secret(cred.get("secret_path"))
        row["api_key_value"]       = secrets.get("api_key_value")
        row["username"]            = secrets.get("username")
        row["password"]            = secrets.get("password")
        row["oauth_client_secret"] = secrets.get("oauth_client_secret")
        row["refresh_token"]       = secrets.get("refresh_token")

        result.append(row)

    return {"connectors": result, **meta}


@router.post("")
def save_connector(body: ConnectorSaveRequest, token: str = Depends(get_token)):
    sb   = _sb(token)
    user = _get_user(token)
    tenantid = _get_tenantid(sb, user.id)

    # ── connectors ──────────────────────────────────────────────────────────
    if body.connuid:
        sb.schema(SUPABASE_SCHEMA).table("connectors").update(
            {"connnm": body.connnm, "desc": body.desc, "useyn": body.useyn}
        ).eq("connuid", body.connuid).eq("tenantid", tenantid).execute()
        connuid = body.connuid
    else:
        res = sb.schema(SUPABASE_SCHEMA).table("connectors").insert({
            "tenantid": tenantid,
            "connnm":   body.connnm,
            "conntype": "api",
            "desc":     body.desc,
            "useyn":    body.useyn,
            "creator":  user.id,
        }).execute()
        connuid = res.data[0]["connuid"]

    # ── conn_apis ────────────────────────────────────────────────────────────
    api_payload = {
        "connuid":         connuid,
        "tenantid":        tenantid,
        "apitype":         "REST",
        "baseurl":         body.baseurl,
        "authtype":        body.authtype,
        "health":          body.health,
        "health_method":   body.health_method,
        "authtest":        body.authtest,
        "authtest_method": body.authtest_method,
        "creator":         user.id,
    }
    existing_api = (
        sb.schema(SUPABASE_SCHEMA).table("conn_apis")
        .select("connuid").eq("connuid", connuid).execute().data
    )
    if existing_api:
        sb.schema(SUPABASE_SCHEMA).table("conn_apis").update(
            {k: v for k, v in api_payload.items() if k not in ("connuid", "tenantid", "creator")}
        ).eq("connuid", connuid).execute()
    else:
        sb.schema(SUPABASE_SCHEMA).table("conn_apis").insert(api_payload).execute()

    # ── conn_api_credentials ─────────────────────────────────────────────────
    if body.authtype and body.authtype != "NONE":
        # 기존 secret_path 조회 (비밀번호 계열 병합용)
        existing_cred_rows = (
            sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials")
            .select("credentialuid, secret_path")
            .eq("connuid", connuid)
            .execute()
            .data
        )
        existing_cred = existing_cred_rows[0] if existing_cred_rows else None
        existing_secret_json = existing_cred["secret_path"] if existing_cred else None

        secret_path = _build_secret_json(body.authtype, body, existing_secret_json)

        cred_payload = {
            "connuid":            connuid,
            "apitype":            "REST",
            "secret_path":        secret_path,
            "api_key_name":       body.api_key_name,
            "api_key_locationcd": body.api_key_locationcd,
            "oauth_client_id":    body.oauth_client_id,
            "token_endpoint":     body.token_endpoint,
            "authorization_type": body.authorization_type,
            "redirect_url":       body.redirect_url,
            "scope":              body.scope,
            "grant_type":         body.grant_type,
            "is_active":          body.is_active,
            "creator":            user.id,
        }
        cred_update = {k: v for k, v in cred_payload.items() if k not in ("connuid", "creator")}

        if existing_cred:
            sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials").update(
                cred_update
            ).eq("connuid", connuid).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials").insert(cred_payload).execute()

    return {"connuid": connuid}


@router.delete("/{connuid}")
def delete_connector(connuid: str, token: str = Depends(get_token)):
    sb   = _sb(token)
    user = _get_user(token)
    tenantid = _get_tenantid(sb, user.id)

    exists = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("connuid").eq("connuid", connuid).eq("tenantid", tenantid).execute().data
    )
    if not exists:
        raise HTTPException(status_code=404, detail="커넥터를 찾을 수 없습니다.")

    sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials").delete().eq("connuid", connuid).execute()
    sb.schema(SUPABASE_SCHEMA).table("conn_apis").delete().eq("connuid", connuid).execute()
    sb.schema(SUPABASE_SCHEMA).table("connectors").delete().eq("connuid", connuid).eq("tenantid", tenantid).execute()

    return {"ok": True}


def _build_url(baseurl: str, path: str) -> str:
    return baseurl.rstrip("/") + ("" if path.startswith("/") else "/") + path


def _verify_connector(sb, connuid: str, tenantid) -> None:
    exists = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("connuid").eq("connuid", connuid).eq("tenantid", tenantid).execute().data
    )
    if not exists:
        raise HTTPException(status_code=404, detail="커넥터를 찾을 수 없습니다.")


@router.post("/{connuid}/test-health")
def test_health(connuid: str, token: str = Depends(get_token)):
    sb   = _sb(token)
    user = _get_user(token)
    _verify_connector(sb, connuid, _get_tenantid(sb, user.id))

    api_rows = (
        sb.schema(SUPABASE_SCHEMA).table("conn_apis")
        .select("baseurl, health, health_method")
        .eq("connuid", connuid)
        .execute()
        .data
    )
    if not api_rows:
        raise HTTPException(status_code=400, detail="API 설정이 없습니다.")

    api = api_rows[0]
    if not api.get("baseurl"):
        raise HTTPException(status_code=400, detail="Base URL이 설정되지 않았습니다.")
    if not api.get("health"):
        raise HTTPException(status_code=400, detail="Health 경로가 설정되지 않았습니다.")

    from utilsPrj.api_helper import call_no_auth
    return call_no_auth(_build_url(api["baseurl"], api["health"]), api.get("health_method", "GET"))


@router.post("/{connuid}/test-auth")
def test_auth(connuid: str, token: str = Depends(get_token)):
    sb   = _sb(token)
    user = _get_user(token)
    _verify_connector(sb, connuid, _get_tenantid(sb, user.id))

    api_rows = (
        sb.schema(SUPABASE_SCHEMA).table("conn_apis")
        .select("*").eq("connuid", connuid).execute().data
    )
    if not api_rows:
        raise HTTPException(status_code=400, detail="API 설정이 없습니다.")

    cred_rows = (
        sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials")
        .select("*").eq("connuid", connuid).execute().data
    )

    api  = api_rows[0]
    cred = cred_rows[0] if cred_rows else {}

    baseurl      = api.get("baseurl", "")
    authtest_path = api.get("authtest", "")
    method       = api.get("authtest_method", "GET")
    authtype     = api.get("authtype", "NONE")

    if not baseurl:
        raise HTTPException(status_code=400, detail="Base URL이 설정되지 않았습니다.")
    if not authtest_path:
        raise HTTPException(status_code=400, detail="Auth Test 경로가 설정되지 않았습니다.")

    url     = _build_url(baseurl, authtest_path)
    secrets = _parse_secret(cred.get("secret_path"))

    from utilsPrj import api_helper as ah

    if authtype == "NONE":
        return ah.call_no_auth(url, method)

    if authtype == "API_KEY":
        key_value = secrets.get("api_key_value", "")
        if not key_value:
            raise HTTPException(status_code=400, detail="API Key가 설정되지 않았습니다.")
        return ah.call_api_key(
            url, method,
            cred.get("api_key_name", ""),
            key_value,
            cred.get("api_key_locationcd", "header"),
        )

    if authtype == "BASIC":
        username = secrets.get("username", "")
        password = secrets.get("password", "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username 또는 Password가 설정되지 않았습니다.")
        return ah.call_basic_auth(url, method, username, password)

    if authtype == "OAUTH2":
        client_id     = cred.get("oauth_client_id", "")
        client_secret = secrets.get("oauth_client_secret", "")
        token_endpoint = cred.get("token_endpoint", "")
        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="OAuth2 Client ID/Secret이 설정되지 않았습니다.")
        if not token_endpoint:
            raise HTTPException(status_code=400, detail="Token Endpoint가 설정되지 않았습니다.")
        return ah.call_oauth2(
            url, method, token_endpoint, client_id, client_secret,
            grant_type=cred.get("grant_type", "client_credentials"),
            scope=cred.get("scope"),
            authorization_type=cred.get("authorization_type") or "Bearer",
        )

    raise HTTPException(status_code=400, detail=f"지원하지 않는 인증 방식: {authtype}")
