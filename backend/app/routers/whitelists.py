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
    _require_whitelist_subscription(tenantid)
    sb = _sb(token)
    user = _get_user(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id))

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

    record["creator"] = str(_get_user(token).id)
    res = sb.schema(SUPABASE_SCHEMA).table("whitelists").insert(record).execute()
    new_id = res.data[0]["whitelistuid"] if res.data else None
    return {"result": "inserted", "whitelistuid": new_id}


@router.delete("/{whitelistuid}")
def delete_whitelist(whitelistuid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    _require_whitelist_subscription(tenantid)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("whitelists").delete().eq("whitelistuid", whitelistuid).eq("tenantid", int(tenantid)).execute()
    return {"ok": True}
