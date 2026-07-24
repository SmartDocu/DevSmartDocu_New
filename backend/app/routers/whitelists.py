"""Whitelists router — Tenant IP whitelist management"""
import ipaddress
from datetime import timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()

IPTYPES = ("IP", "CIDR", "RANGE")


def _require_whitelist_subscription(tenantid: Optional[str]) -> None:
    if not tenantid:
        raise HTTPException(status_code=400, detail="msg.tenant.required")
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    row = (
        svc.table("account_features").select("accountuid")
        .eq("tenantid", int(tenantid)).eq("productcd", "whitelist")
        .maybe_single().execute()
    )
    if not row.data:
        raise HTTPException(status_code=403, detail="msg.whitelist.subscription.required")


def _require_tenant_manager(user_id: str, tenantid: Optional[str]) -> None:
    """테넌트 관리 화면 전용 엔드포인트 접근 제한: 해당 테넌트의 매니저(rolecd=M)만 허용."""
    if not tenantid:
        raise HTTPException(status_code=400, detail="msg.tenant.required")
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    tu = (
        svc.table("tenantusers").select("rolecd,useyn")
        .eq("useruid", user_id).eq("tenantid", int(tenantid))
        .maybe_single().execute()
    )
    if not tu.data or tu.data.get("rolecd") != "M" or tu.data.get("useyn") is not True:
        raise HTTPException(status_code=403, detail="테넌트 관리자만 접근할 수 있습니다.")


def _require_not_system_tenant(tenantid: Optional[str]) -> None:
    """조직/구독 관리 화면은 시스템(개인) 테넌트에서 의미가 없어 차단한다."""
    if not tenantid:
        raise HTTPException(status_code=400, detail="msg.tenant.required")
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    if t_row.data and t_row.data.get("issystemtenant"):
        raise HTTPException(status_code=403, detail="msg.org.feature.unavailable.system.tenant")


def _get_offsetminutes(sb, user_id: str, tenantid: Optional[str] = None) -> Optional[int]:
    """tenantid를 주면 그 테넌트 기준으로, 없으면(다중 테넌트일 때 모호해질 수 있어) 활성(useyn=True) 소속 행을 사용."""
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


def _ip_to_int(ip: str) -> int:
    return int(ipaddress.IPv4Address(ip))


def _calc_ip_range(iptype: str, ipvalue: str) -> tuple[int, int]:
    """iptype에 따라 ipvalue를 검증하고 start_ip_num/end_ip_num을 계산한다."""
    value = (ipvalue or "").strip()
    try:
        if iptype == "IP":
            n = _ip_to_int(value)
            return n, n
        if iptype == "CIDR":
            net = ipaddress.IPv4Network(value, strict=False)
            return int(net.network_address), int(net.broadcast_address)
        if iptype == "RANGE":
            start_s, end_s = value.split("~", 1)
            start_n, end_n = _ip_to_int(start_s.strip()), _ip_to_int(end_s.strip())
            if start_n > end_n:
                raise ValueError
            return start_n, end_n
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
        pass
    raise HTTPException(status_code=400, detail="msg.whitelist.ipvalue.invalid")


@router.get("")
def list_whitelists(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    _require_tenant_manager(str(user.id), tenantid)
    _require_not_system_tenant(tenantid)
    _require_whitelist_subscription(tenantid)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id), tenantid)

    rows = (
        sb.schema(SUPABASE_SCHEMA).table("whitelists")
        .select("*")
        .eq("tenantid", tenantid)
        .order("createdts", desc=True)
        .execute().data or []
    )
    for r in rows:
        r["createdts"] = _fmt_dt(r.get("createdts"), offsetminutes)
    return {"whitelists": rows}


class WhitelistSaveRequest(BaseModel):
    whitelistuid: Optional[str] = None
    iptype: str
    ipvalue: str
    desc: Optional[str] = None
    useyn: bool = True


@router.post("")
def save_whitelist(
    body: WhitelistSaveRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    _require_tenant_manager(str(user.id), tenantid)
    _require_not_system_tenant(tenantid)
    _require_whitelist_subscription(tenantid)
    if body.iptype not in IPTYPES:
        raise HTTPException(status_code=400, detail="msg.whitelist.iptype.invalid")

    start_ip_num, end_ip_num = _calc_ip_range(body.iptype, body.ipvalue)

    sb = _sb(token)
    record = {
        "tenantid": int(tenantid),
        "iptype": body.iptype,
        "ipvalue": body.ipvalue.strip(),
        "start_ip_num": start_ip_num,
        "end_ip_num": end_ip_num,
        "desc": body.desc,
        "useyn": body.useyn,
    }

    if body.whitelistuid:
        sb.schema(SUPABASE_SCHEMA).table("whitelists").update(record).eq("whitelistuid", body.whitelistuid).execute()
        return {"result": "updated", "whitelistuid": body.whitelistuid}

    record["creator"] = str(user.id)
    res = sb.schema(SUPABASE_SCHEMA).table("whitelists").insert(record).execute()
    new_id = res.data[0]["whitelistuid"] if res.data else None
    return {"result": "inserted", "whitelistuid": new_id}


@router.delete("/{whitelistuid}")
def delete_whitelist(whitelistuid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    _require_tenant_manager(str(user.id), tenantid)
    _require_not_system_tenant(tenantid)
    _require_whitelist_subscription(tenantid)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("whitelists").delete().eq("whitelistuid", whitelistuid).eq("tenantid", int(tenantid)).execute()
    return {"ok": True}


# ─── IP 제한 적용 설정 (config_tenants.Is_Manager_IP_Allow / Is_User_IP_Allow) ──

_IP_ALLOW_CONFIGCDS = ("Is_Manager_IP_Allow", "Is_User_IP_Allow")


@router.get("/config")
def get_whitelist_config(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    _require_tenant_manager(str(user.id), tenantid)
    _require_not_system_tenant(tenantid)
    _require_whitelist_subscription(tenantid)

    svc = get_service_client().schema(SUPABASE_SCHEMA)
    rows = (
        svc.table("config_tenants").select("configcd,value")
        .eq("tenantid", int(tenantid)).in_("configcd", _IP_ALLOW_CONFIGCDS)
        .execute().data or []
    )
    cfg = {r["configcd"]: r["value"] for r in rows}
    return {
        "is_manager_ip_allow": bool(cfg.get("Is_Manager_IP_Allow")),
        "is_user_ip_allow": bool(cfg.get("Is_User_IP_Allow")),
    }


class WhitelistConfigSaveRequest(BaseModel):
    is_manager_ip_allow: bool
    is_user_ip_allow: bool


@router.post("/config")
def save_whitelist_config(
    body: WhitelistConfigSaveRequest,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    _require_tenant_manager(str(user.id), tenantid)
    _require_not_system_tenant(tenantid)
    _require_whitelist_subscription(tenantid)

    svc = get_service_client().schema(SUPABASE_SCHEMA)
    values = {
        "Is_Manager_IP_Allow": body.is_manager_ip_allow,
        "Is_User_IP_Allow": body.is_user_ip_allow,
    }
    for configcd, value in values.items():
        existing = (
            svc.table("config_tenants").select("tenantid")
            .eq("tenantid", int(tenantid)).eq("configcd", configcd)
            .maybe_single().execute()
        )
        if existing and existing.data:
            svc.table("config_tenants").update({"value": value}).eq("tenantid", int(tenantid)).eq("configcd", configcd).execute()
        else:
            svc.table("config_tenants").insert({
                "tenantid": int(tenantid), "configcd": configcd, "value": value, "creator": str(user.id),
            }).execute()

    return {"result": "success"}
