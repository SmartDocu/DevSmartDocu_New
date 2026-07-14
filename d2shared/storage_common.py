"""
storage_common.py — d2chat · d2insight 공통 Supabase 저장소 함수

각 앱의 storage 모듈에서 import하여 사용한다.
  d2chat   : table="chat_sessions", qa_table="chat_qas", fav_table="chat_favorites"
  d2insight: table="insight_sessions", qa_table="insight_qas", fav_table="insight_favorites"

모든 함수는 호출자(라우터)가 토큰 기반으로 생성한 Supabase 클라이언트(sb)를 인자로 받는다.
RLS(auth.uid())가 신원을 보장하므로 creator/user_uid는 별도 인증 검증 없이 전달받는다.
"""
from __future__ import annotations

import json
from typing import Optional

from backend.app.config import settings


def _q(sb, table: str):
    return sb.schema(settings.SUPABASE_SCHEMA).table(table)


# ── 공통 유틸 ──────────────────────────────────────────────────────

def get_project_info(sb, user_uid: str) -> tuple[int | None, int | None]:
    """projects 테이블에서 tenantid, projectid 반환."""
    try:
        res = _q(sb, "projects").select("tenantid,projectid").eq("creator", user_uid).execute()
        if res.data:
            row = res.data[0]
            return row.get("tenantid"), row.get("projectid")
    except Exception:
        pass
    return None, None


def get_offsetminutes(sb, user_id: str | None) -> int | None:
    """tenantusers.timezone → tenants.timezone → timezones.offsetminutes 순으로 조회."""
    if not user_id:
        return None
    try:
        rows = (
            _q(sb, "tenantusers").select("timezone,tenantid")
            .eq("useruid", user_id).eq("useyn", True).limit(1).execute().data or []
        )
        if not rows:
            return None
        tz = rows[0].get("timezone")
        if not tz and rows[0].get("tenantid"):
            t = _q(sb, "tenants").select("timezone").eq("tenantid", rows[0]["tenantid"]).maybe_single().execute()
            if t and t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = _q(sb, "timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None
    except Exception:
        return None


def fmt_dt(raw, offsetminutes: int | None = None) -> str:
    if not raw:
        return ""
    try:
        from datetime import timedelta, timezone as _tz
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(_tz.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


def parse_answer(answer_raw: str | None) -> dict:
    """answer 컬럼(JSON 또는 plain text)에서 text와 시각화 데이터 추출."""
    if not answer_raw:
        return {"text": "", "visualization_type": "none", "table_html": None, "chart_image": None}
    try:
        data = json.loads(answer_raw)
        if isinstance(data, dict):
            return {
                "text":               data.get("answer", ""),
                "visualization_type": data.get("visualization_type", "none"),
                "table_html":         data.get("table_html"),
                "chart_image":        data.get("chart_image"),
            }
    except Exception:
        pass
    return {"text": answer_raw, "visualization_type": "none", "table_html": None, "chart_image": None}


# ── 세션 ──────────────────────────────────────────────────────────

def create_session(
    sb,
    tenant_id: int | None,
    project_id: int | None,
    creator: str | None,
    *,
    table: str,
) -> str:
    """세션 레코드를 생성하고 sessionuid를 반환한다."""
    res = _q(sb, table).insert({
        "tenantid":        tenant_id or None,
        "projectid":       project_id or None,
        "sessiontitles":   "",
        "sessionstatuscd": "Active",
        "creator":         creator or None,
    }).execute()
    return res.data[0]["sessionuid"]


def delete_session(sb, session_uid: str, creator: str, *, table: str) -> bool:
    """세션 소프트 삭제 — sessionstatuscd를 Archived로 변경."""
    _q(sb, table).update({"sessionstatuscd": "Archived"}).eq("sessionuid", session_uid).eq("creator", creator).execute()
    return True


def get_qa_count(sb, session_uid: str, *, table: str) -> int:
    """세션의 QA 건수 반환."""
    try:
        res = _q(sb, table).select("qauid", count="exact").eq("sessionuid", session_uid).execute()
        return res.count or 0
    except Exception:
        return 0


def get_history_by_date(
    sb,
    creator: str,
    *,
    session_table: str,
    fav_table: str | None = None,
    offsetminutes: int | None = None,
) -> dict:
    """날짜별로 그룹화된 세션 목록 반환.

    fav_table 지정 시 각 세션에 is_favorite 필드 포함 (d2chat 전용).
    """
    try:
        res = (
            _q(sb, session_table)
            .select("sessionuid,sessiontitles,createdts")
            # .select("sessionuid,sessiontitles,createdt,createdts")
            .eq("creator", creator)
            .eq("sessionstatuscd", "Active")
            .neq("sessiontitles", "")
            .order("createdts", desc=True)
            .execute()
        )

        fav_uids: set = set()
        if fav_table:
            fav_res = _q(sb, fav_table).select("sessionuid").eq("creator", creator).execute()
            fav_uids = {r["sessionuid"] for r in (fav_res.data or [])}

        grouped: dict = {}
        for row in (res.data or []):
            formatted = fmt_dt(row.get("createdts", ""), offsetminutes)
            date_key = formatted[:10]
            item: dict = {
                "session_id": row["sessionuid"],
                "title":      row.get("sessiontitles", ""),
                "created_at": formatted,
            }
            if fav_table:
                item["is_favorite"] = row["sessionuid"] in fav_uids
            grouped.setdefault(date_key, []).append(item)

        return grouped
    except Exception:
        return {}


# ── 즐겨찾기 ─────────────────────────────────────────────────────

def add_favorite_qa(
    sb,
    qauid: str,
    creator: str,
    *,
    qa_table: str,
    fav_table: str,
    extra_fav_fields: list[str] | None = None,
) -> bool:
    """QA를 즐겨찾기 테이블에 복사하고 원본 qa_table.favoriteyn = True 설정.

    extra_fav_fields: QA 레코드에서 즐겨찾기 레코드로 함께 복사할 추가 컬럼.
      d2chat  : ["dataset"]
      d2insight: ["filenm", "fileurl"]
    """
    existing = (
        _q(sb, fav_table)
        .select("favoriteuid")
        .eq("qauid", qauid)
        .eq("creator", creator)
        .execute()
    )
    if existing.data:
        return True  # 이미 등록됨

    qa_res = _q(sb, qa_table).select("*").eq("qauid", qauid).execute()
    if not qa_res.data:
        return False
    qa = qa_res.data[0]

    row: dict = {
        "tenantid":   qa.get("tenantid"),
        "projectid":  qa.get("projectid"),
        "sessionuid": qa.get("sessionuid"),
        "qauid":      qauid,
        "question":   qa.get("question", ""),
        "answer":     qa.get("answer"),
        "creator":    creator or None,
    }
    if extra_fav_fields:
        for field in extra_fav_fields:
            row[field] = qa.get(field)

    _q(sb, fav_table).insert(row).execute()
    _q(sb, qa_table).update({"favoriteyn": True}).eq("qauid", qauid).execute()
    return True


def remove_favorite_qa(
    sb,
    qauid: str,
    creator: str,
    *,
    qa_table: str,
    fav_table: str,
) -> bool:
    """즐겨찾기 해제 — fav_table 삭제 + qa_table.favoriteyn = False."""
    try:
        _q(sb, fav_table).delete().eq("qauid", qauid).eq("creator", creator).execute()
        _q(sb, qa_table).update({"favoriteyn": False}).eq("qauid", qauid).execute()
        return True
    except Exception:
        return False


def get_favorites(
    sb,
    creator: str,
    *,
    fav_table: str,
    include_viz: bool = False,
    extra_fields: list[str] | None = None,
    offsetminutes: int | None = None,
) -> list[dict]:
    """즐겨찾기 목록 반환.

    include_viz=True : parse_answer()의 시각화 데이터 포함 (d2chat).
    extra_fields      : 직접 컬럼으로 읽을 추가 필드 (d2insight: ["filenm", "fileurl"]).
    """
    select = "favoriteuid,qauid,sessionuid,question,answer,createdts"
    if extra_fields:
        select += "," + ",".join(extra_fields)

    try:
        res = (
            _q(sb, fav_table)
            .select(select)
            .eq("creator", creator)
            .order("createdts", desc=True)
            .execute()
        )
        result = []
        for row in (res.data or []):
            ans = parse_answer(row.get("answer"))
            item: dict = {
                "favoriteuid": row.get("favoriteuid"),
                "qauid":       row["qauid"],
                "session_id":  row.get("sessionuid"),
                "question":    row.get("question", ""),
                "answer":      ans["text"],
                "created_at":  fmt_dt(row.get("createdts"), offsetminutes),
            }
            if include_viz:
                item["visualization_type"] = ans["visualization_type"]
                item["table_html"]         = ans["table_html"]
                item["chart_image"]        = ans["chart_image"]
            if extra_fields:
                for f in extra_fields:
                    item[f] = row.get(f)
            result.append(item)
        return result
    except Exception:
        return []
