from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()


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


_FETCH_CAP = 1000  # 병합 대상 전체를 파이썬에서 정렬/필터링하기 위한 상한


def _fetch_merged_notifications(sb, uid: str):
    """notifications(단일 대상) + notification_users(다중 대상)를 병합해 최신순으로 반환.

    deleted_yn/is_onetarget이 NULL인 row는 DB단 .eq()/.neq()로 걸러내면 제외돼버리므로
    (Postgres에서 NULL = true / NULL <> true 는 둘 다 unknown → row 자체가 안 걸림)
    일단 target_useruid로만 가져온 뒤 파이썬에서 NULL-safe하게 필터링한다.
    """
    own_rows_raw = (
        sb.schema(SUPABASE_SCHEMA).table("notifications").select("*")
        .eq("target_useruid", uid)
        .order("createdts", desc=True).limit(_FETCH_CAP)
        .execute().data or []
    )
    own_rows = [r for r in own_rows_raw if r.get("is_onetarget") is not False and not r.get("deleted_yn")]
    for r in own_rows:
        r["is_read"] = bool(r.get("is_read"))

    # 다중 대상 — notification_users(나)로 먼저 대상 여부를 RLS 스코프로 확인한 뒤,
    # 그 notificationuid들의 실제 내용은 service role로 조회 (notifications의
    # 단일대상용 RLS 정책과 무관하게, 이미 notification_users로 자격이 증명됐으므로)
    nu_rows_raw = (
        sb.schema(SUPABASE_SCHEMA).table("notification_users").select("*")
        .eq("target_useruid", uid)
        .order("createdts", desc=True).limit(_FETCH_CAP)
        .execute().data or []
    )
    nu_rows = [r for r in nu_rows_raw if not r.get("deleted_yn")]
    shared_rows = []
    if nu_rows:
        nu_map = {r["notificationuid"]: r for r in nu_rows}
        sb_svc = get_service_client()
        notif_rows = (
            sb_svc.schema(SUPABASE_SCHEMA).table("notifications").select("*")
            .in_("notificationuid", list(nu_map.keys()))
            .execute().data or []
        )
        for n in notif_rows:
            if n.get("deleted_yn"):
                continue
            nu = nu_map[n["notificationuid"]]
            n["is_read"] = bool(nu.get("is_read"))
            n["readts"] = nu.get("readdts")
            shared_rows.append(n)

    rows = own_rows + shared_rows
    rows.sort(key=lambda r: r.get("createdts") or "", reverse=True)
    return rows


@router.get("")
def list_notifications(
    unread_only: bool = False,
    read_status: Optional[str] = None,  # 'unread' | 'read' | None(전체)
    category: Optional[str] = None,
    notification_status: Optional[str] = None,  # 'info' | 'error' | None(전체)
    search: Optional[str] = None,  # title/message 텍스트 검색
    offset: int = 0,
    limit: int = 50,
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    uid = str(user.id)
    offsetminutes = _get_offsetminutes(sb, uid)

    rows = _fetch_merged_notifications(sb, uid)
    unread_count = sum(1 for r in rows if not r.get("is_read"))

    if unread_only:
        read_status = "unread"
    if read_status == "unread":
        rows = [r for r in rows if not r.get("is_read")]
    elif read_status == "read":
        rows = [r for r in rows if r.get("is_read")]
    if category:
        rows = [r for r in rows if r.get("notificationcategory") == category]
    if notification_status:
        rows = [r for r in rows if r.get("notificationstatus") == notification_status]
    if search:
        s = search.lower()
        rows = [r for r in rows if s in (r.get("title") or "").lower() or s in (r.get("message") or "").lower()]

    total_count = len(rows)
    rows = rows[offset:offset + limit]
    for row in rows:
        row["createdts"] = _fmt_dt(row.get("createdts"), offsetminutes)

    return {"notifications": rows, "unread_count": unread_count, "total_count": total_count}


@router.post("/{notificationuid}/read")
def mark_notification_read(notificationuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    uid = str(user.id)
    now_iso = datetime.now(timezone.utc).isoformat()

    # 다중 대상(notification_users)부터 시도, 대상 아니면 단일 대상(notifications)으로
    nu_result = (
        sb.schema(SUPABASE_SCHEMA).table("notification_users")
        .update({"is_read": True, "readdts": now_iso})
        .eq("notificationuid", notificationuid).eq("target_useruid", uid)
        .execute()
    )
    if not nu_result.data:
        sb.schema(SUPABASE_SCHEMA).table("notifications").update({
            "is_read": True,
            "readts": now_iso,
        }).eq("notificationuid", notificationuid).eq("target_useruid", uid).execute()
    return {"message": "읽음 처리되었습니다."}


@router.post("/read-all")
def mark_all_notifications_read(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    uid = str(user.id)
    now_iso = datetime.now(timezone.utc).isoformat()

    # is_read가 NULL인 row는 .eq("is_read", False)로 걸면 제외되므로 무조건 업데이트(멱등적이라 안전)
    sb.schema(SUPABASE_SCHEMA).table("notifications").update({
        "is_read": True,
        "readts": now_iso,
    }).eq("target_useruid", uid).execute()
    sb.schema(SUPABASE_SCHEMA).table("notification_users").update({
        "is_read": True,
        "readdts": now_iso,
    }).eq("target_useruid", uid).execute()
    return {"message": "전체 읽음 처리되었습니다."}


@router.post("/{notificationuid}/delete")
def delete_notification(notificationuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    uid = str(user.id)
    now_iso = datetime.now(timezone.utc).isoformat()

    # 다중 대상(notification_users)부터 시도, 대상 아니면 단일 대상(notifications)으로
    nu_result = (
        sb.schema(SUPABASE_SCHEMA).table("notification_users")
        .update({"deleted_yn": True, "deleteddts": now_iso})
        .eq("notificationuid", notificationuid).eq("target_useruid", uid)
        .execute()
    )
    if not nu_result.data:
        sb.schema(SUPABASE_SCHEMA).table("notifications").update({
            "deleted_yn": True,
            "deleteddts": now_iso,
        }).eq("notificationuid", notificationuid).eq("target_useruid", uid).execute()
    return {"message": "삭제되었습니다."}
