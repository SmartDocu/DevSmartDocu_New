"""Audit Log 뷰어 router — roleid=7 전용.

privacy_consent_logs / admin_action_logs / work_logs / login_logs 4개
append-only 테이블을 조회 전용으로 노출한다. 쓰기(수정/삭제) 엔드포인트는
의도적으로 만들지 않는다 — DB 트리거가 이미 append-only를 강제하고 있고,
이 화면은 조회 전용이어야 하기 때문.
"""
from datetime import date, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import get_token, get_tenantid
from backend.app.routers.admin import _require_admin, _sb_service
from utilsPrj.supabase_client import SUPABASE_SCHEMA
from utilsPrj.user_lookup import get_usernm_email_map

router = APIRouter()


def _default_dates(start_date: Optional[str], end_date: Optional[str]) -> tuple[str, str]:
    today = date.today()
    sd = start_date or (today - timedelta(days=30)).isoformat()
    ed = end_date or today.isoformat()
    return sd, ed


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


def _fmt_dt(val, offsetminutes: Optional[int] = None) -> str:
    if not val:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(val) if isinstance(val, str) else val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(val)


def _apply_offset(rows: list, date_field: str, offsetminutes: Optional[int]) -> list:
    for r in rows:
        r[date_field] = _fmt_dt(r.get(date_field), offsetminutes)
    return rows


def _search_useruids(sb, email: Optional[str]):
    """email 검색어로 useruid 목록을 찾는다. email 없으면 None(필터 없음), 매칭 없으면 빈 리스트."""
    if not email:
        return None
    rows = sb.schema("public").table("users").select("useruid").ilike("email", f"%{email}%").execute().data or []
    return [r["useruid"] for r in rows]


def _attach_user_info(sb, rows: list, key: str = "useruid") -> list:
    user_map = get_usernm_email_map(sb, [r.get(key) for r in rows])
    for r in rows:
        nm, email = user_map.get(r.get(key), ("", ""))
        r["usernm"] = nm
        r["email"] = email
    return rows


def _list_audit_table(sb, table: str, date_col: str, sd: str, ed: str, useruids, page: int, page_size: int, extra_eq: dict):
    q = (
        sb.schema(SUPABASE_SCHEMA).table(table).select("*", count="exact")
        .gte(date_col, sd)
        .lt(date_col, (date.fromisoformat(ed) + timedelta(days=1)).isoformat())
    )
    if useruids is not None:
        q = q.in_("useruid", useruids)
    for k, v in extra_eq.items():
        if v is not None:
            q = q.eq(k, v)
    offset = (page - 1) * page_size
    res = q.order(date_col, desc=True).range(offset, offset + page_size - 1).execute()
    return res.data or [], res.count or 0


# ══════════════════════════════════════════════════════
#  1. 개인정보 동의 로그
# ══════════════════════════════════════════════════════

@router.get("/privacy-consent")
def list_privacy_consent_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email: Optional[str] = None,
    consenttypecd: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    admin = _require_admin(token)
    sb = _sb_service()
    offsetminutes = _get_offsetminutes(sb, str(admin.id), tenantid)
    sd, ed = _default_dates(start_date, end_date)
    useruids = _search_useruids(sb, email)
    if useruids == []:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items, total = _list_audit_table(
        sb, "privacy_consent_logs", "createdts", sd, ed, useruids, page, page_size,
        {"consenttypecd": consenttypecd},
    )
    items = _apply_offset(_attach_user_info(sb, items), "createdts", offsetminutes)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ══════════════════════════════════════════════════════
#  2. 보안/관리자 로그
# ══════════════════════════════════════════════════════

@router.get("/admin-actions")
def list_admin_action_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email: Optional[str] = None,
    actioncd: Optional[str] = None,
    targettype: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    admin = _require_admin(token)
    sb = _sb_service()
    offsetminutes = _get_offsetminutes(sb, str(admin.id), tenantid)
    sd, ed = _default_dates(start_date, end_date)
    useruids = _search_useruids(sb, email)
    if useruids == []:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items, total = _list_audit_table(
        sb, "admin_action_logs", "createdts", sd, ed, useruids, page, page_size,
        {"actioncd": actioncd, "targettype": targettype},
    )
    items = _apply_offset(_attach_user_info(sb, items), "createdts", offsetminutes)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ══════════════════════════════════════════════════════
#  3. 접속/작업 로그
# ══════════════════════════════════════════════════════

@router.get("/work")
def list_work_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email: Optional[str] = None,
    servicecd: Optional[str] = None,
    actioncd: Optional[str] = None,
    targettype: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    admin = _require_admin(token)
    sb = _sb_service()
    offsetminutes = _get_offsetminutes(sb, str(admin.id), tenantid)
    sd, ed = _default_dates(start_date, end_date)
    useruids = _search_useruids(sb, email)
    if useruids == []:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items, total = _list_audit_table(
        sb, "work_logs", "createdts", sd, ed, useruids, page, page_size,
        {"servicecd": servicecd, "actioncd": actioncd, "targettype": targettype},
    )
    items = _apply_offset(_attach_user_info(sb, items), "createdts", offsetminutes)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ══════════════════════════════════════════════════════
#  4. 문서/챕터 생성 실패 이력 (gendocs_realtimes / genchapters_realtimes)
# ══════════════════════════════════════════════════════

@router.get("/gen-failures")
def list_gen_failures(
    kind: str = Query("doc", pattern="^(doc|chapter)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email: Optional[str] = None,
    errorcd: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """errorcd가 기록된 문서/챕터 생성 작업(시스템 관리자 전용). errormessage(traceback 원문)를 그대로 반환한다."""
    admin = _require_admin(token)
    sb = _sb_service()
    offsetminutes = _get_offsetminutes(sb, str(admin.id), tenantid)
    sd, ed = _default_dates(start_date, end_date)
    creators = _search_useruids(sb, email)
    if creators == []:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    table = "gendocs_realtimes" if kind == "doc" else "genchapters_realtimes"
    q = (
        sb.schema(SUPABASE_SCHEMA).table(table).select("*", count="exact")
        .not_.is_("errorcd", "null")
        .gte("startdts", sd)
        .lt("startdts", (date.fromisoformat(ed) + timedelta(days=1)).isoformat())
    )
    if creators is not None:
        q = q.in_("creator", creators)
    if errorcd:
        q = q.eq("errorcd", errorcd)
    offset = (page - 1) * page_size
    res = q.order("startdts", desc=True).range(offset, offset + page_size - 1).execute()
    items, total = res.data or [], res.count or 0

    # 대상 이름 보강 — 문서: gendocnm은 이미 있음 / 챕터: chapters.chapternm + docs.docnm
    if kind == "chapter":
        chapteruids = list({r["chapteruid"] for r in items if r.get("chapteruid")})
        docids = list({r["docid"] for r in items if r.get("docid") is not None})
        chap_map = {}
        if chapteruids:
            rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select("chapteruid,chapternm").in_("chapteruid", chapteruids).execute().data or []
            chap_map = {r["chapteruid"]: r["chapternm"] for r in rows}
        doc_map = {}
        if docids:
            rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("docid,docnm").in_("docid", docids).execute().data or []
            doc_map = {r["docid"]: r["docnm"] for r in rows}
        for r in items:
            r["chapternm"] = chap_map.get(r.get("chapteruid"), "")
            r["docnm"] = doc_map.get(r.get("docid"), "")

    # 문서 단위 실패 사유가 "챕터 처리 실패: <genchapteruid>" 형태로 저장된 건은 챕터명을 찾아 같이 내려준다
    if kind == "doc":
        import re
        # "챕터 처리 실패: <uid>"(워커 전파 메시지)와 "챕터 <uid> 데이터 로드 실패"(병합 단계) 두 형태 모두
        uid_re = re.compile(r"챕터(?: 처리 실패:)? ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
        found = {}
        for r in items:
            m = uid_re.search(r.get("errormessage") or "")
            if m:
                found[r["gendocjobuid"]] = m.group(1)
        if found:
            gc_rows = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("genchapteruid,chapteruid") \
                .in_("genchapteruid", list(set(found.values()))).execute().data or []
            gc_to_chap = {x["genchapteruid"]: x["chapteruid"] for x in gc_rows}
            ch_rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select("chapteruid,chapternm") \
                .in_("chapteruid", list(set(gc_to_chap.values()))).execute().data or [] if gc_to_chap else []
            ch_nm = {x["chapteruid"]: x["chapternm"] for x in ch_rows}
            for r in items:
                guid = found.get(r["gendocjobuid"])
                if guid:
                    r["failed_genchapteruid"] = guid
                    r["failed_chapternm"] = ch_nm.get(gc_to_chap.get(guid), "")

    items = _attach_user_info(sb, items, key="creator")
    for r in items:
        r["startdts"] = _fmt_dt(r.get("startdts"), offsetminutes)
        r["enddts"] = _fmt_dt(r.get("enddts"), offsetminutes)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/login")
def list_login_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email: Optional[str] = None,
    eventtypecd: Optional[str] = None,
    is_success: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    admin = _require_admin(token)
    sb = _sb_service()
    offsetminutes = _get_offsetminutes(sb, str(admin.id), tenantid)
    sd, ed = _default_dates(start_date, end_date)
    useruids = _search_useruids(sb, email)
    if useruids == []:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items, total = _list_audit_table(
        sb, "login_logs", "logindts", sd, ed, useruids, page, page_size,
        {"eventtypecd": eventtypecd, "is_success": is_success},
    )
    items = _apply_offset(_attach_user_info(sb, items), "logindts", offsetminutes)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
