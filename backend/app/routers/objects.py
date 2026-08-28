from datetime import timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user, require_doc_read, require_doc_write
from backend.app.schemas.objects import (
    ObjectItem, ObjectsListResponse, ObjectSaveRequest,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA
from utilsPrj.audit_log import log_work_action, snapshot_row, get_client_ip

router = APIRouter()


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


@router.get("", dependencies=[Depends(require_doc_read)])
def list_objects(chapteruid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id), tenantid)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_objects__r", {"p_chapteruid": chapteruid})
        .execute().data or []
    )

    for obj in rows:
        obj["createdts"] = _fmt_dt(obj.get("createdts"), offsetminutes)
        nm = obj.get("objecttypenm") or ""
        gcd = obj.get("gentypecd") or ""
        obj["objecttypenm_full"] = f"{nm} ({gcd})" if nm else ""

    rows.sort(key=lambda x: x.get("orderno") or 0)
    return {"objects": rows}


@router.post("", dependencies=[Depends(require_doc_write)])
def save_object(body: ObjectSaveRequest, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    # 신규 생성 시 objectnm 필수
    if not body.objectuid and not body.objectnm:
        raise HTTPException(status_code=400, detail="항목명(objectnm)은 필수입니다.")

    before = snapshot_row(sb, "objects", "objectuid", body.objectuid) if body.objectuid else None

    transdata = {
        "chapteruid": body.chapteruid,
        "objectuid": body.objectuid or None,
        "objectdesc": body.objectdesc,
        "objecttypecd": body.objecttypecd,
        "useyn": body.useyn,
        "orderno": body.orderno,
    }
    if body.objectnm:
        transdata["objectnm"] = body.objectnm

    # If type changed, clear old content
    if body.objectuid and body.objecttypecd != body.objecttypecd_orig:
        for tbl in ("tables", "charts", "sentences"):
            sb.schema(SUPABASE_SCHEMA).table(tbl).delete().eq("objectuid", body.objectuid).execute()
        transdata["objectsettingyn"] = False

    res = sb.schema(SUPABASE_SCHEMA).table("objects").upsert(transdata).execute()
    after = res.data[0] if res.data else snapshot_row(sb, "objects", "objectuid", body.objectuid)
    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Do",
        actioncd="update" if body.objectuid else "create",
        targettype="objects", targetid=(after or {}).get("objectuid") if after else body.objectuid,
        before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"message": "저장되었습니다."}


@router.delete("/{objectuid}", dependencies=[Depends(require_doc_write)])
def delete_object(objectuid: str, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    before = snapshot_row(sb, "objects", "objectuid", objectuid)
    sb.schema(SUPABASE_SCHEMA).table("objects").delete().eq("objectuid", objectuid).execute()
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Do",
        actioncd="delete", targettype="objects", targetid=objectuid, before=before,
        ip=get_client_ip(request),
    )
    return {"message": "삭제되었습니다."}
