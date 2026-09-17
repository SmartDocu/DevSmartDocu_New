from typing import Optional
from urllib.parse import urlparse

from fastapi import Request

from utilsPrj.supabase_client import SUPABASE_SCHEMA


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def get_country_code(ip: str) -> Optional[str]:
    """ip-api.com으로 국가코드 조회 (2자리, 예: KR). 실패 시 None."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return None
    try:
        import httpx
        resp = httpx.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "countryCode"},
            timeout=3.0,
        )
        data = resp.json()
        return data.get("countryCode") or None
    except Exception:
        return None


def fmt_dt(raw) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


def get_tenantid(sb, user_id: str) -> Optional[str]:
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


def delete_storage_file(sb, url: str):
    try:
        parsed = urlparse(url)
        prefix = "/storage/v1/object/public/d2doc/"
        if prefix in parsed.path:
            path = parsed.path.split(prefix)[-1]
            sb.storage.from_("d2doc").remove([path])
    except Exception:
        pass
