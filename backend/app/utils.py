from typing import Optional
from urllib.parse import urlparse

from utilsPrj.supabase_client import SUPABASE_SCHEMA


def fmt_dt(raw) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        return dt.strftime("%y-%m-%d %H:%M")
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
        prefix = "/storage/v1/object/public/smartdoc/"
        if prefix in parsed.path:
            path = parsed.path.split(prefix)[-1]
            sb.storage.from_("smartdoc").remove([path])
    except Exception:
        pass
