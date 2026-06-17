"""
supabase_storage.py — Supabase 기반 대화 저장소 (d2chat)
공통 패턴(세션/즐겨찾기 등)은 d2shared.storage_common 사용.
모든 함수는 라우터가 토큰으로 생성한 Supabase 클라이언트(sb)를 인자로 받는다 (RLS 적용).
"""
import json
from typing import Optional

from d2shared.storage_common import (
    _q,
    get_project_info,
    parse_answer as _parse_answer,
    create_session as _create_session,
    delete_session as _delete_session,
    get_qa_count as _get_qa_count,
    get_history_by_date as _get_history_by_date,
    add_favorite_qa as _add_favorite_qa,
    remove_favorite_qa as _remove_favorite_qa,
    get_favorites as _get_favorites,
)

_SESSION_TABLE = "chat_sessions"
_QA_TABLE = "chat_qas"
_FAV_TABLE = "chat_favorites"


# ── 사용자 / 프로젝트 정보 ────────────────────────────────────────

def get_users_same_tenant(sb, tenant_id: int, exclude_uid: str, project_id: int = None) -> list:
    """같은 tenant의 사용자 목록 (projects 테이블에서 직접 조회).
    테스트 중: tenantid 기준 조회.
    운영 시: projectid 기준 조회 (아래 주석 참고).
    """
    try:
        # [운영] projectid가 같은 사용자만 조회
        # proj_res = (
        #     _q(sb, "projects")
        #     .select("creator,projectnm")
        #     .eq("tenantid", tenant_id)
        #     .eq("projectid", project_id)
        #     .neq("creator", exclude_uid)
        #     .execute()
        # )

        # [테스트] tenantid가 같은 사용자 모두 조회
        proj_res = (
            _q(sb, "projects")
            .select("creator,projectnm")
            .eq("tenantid", tenant_id)
            .neq("creator", exclude_uid)
            .execute()
        )

        seen = set()
        uids = []
        fallback = {}
        for r in (proj_res.data or []):
            uid = r.get("creator")
            if uid and uid not in seen:
                seen.add(uid)
                uids.append(uid)
                fallback[uid] = r.get("projectnm", uid)

        if not uids:
            return []

        try:
            user_res = (
                _q(sb, "users")
                .select("creator,email,usernm")
                .in_("creator", uids)
                .execute()
            )
            user_map = {u["creator"]: u for u in (user_res.data or [])}
        except Exception:
            user_map = {}

        result = []
        for uid in uids:
            u = user_map.get(uid)
            if u:
                label = u.get("usernm") or u.get("email") or fallback[uid]
                result.append({"creator": uid, "email": label})
            else:
                result.append({"creator": uid, "email": fallback[uid]})
        return result
    except Exception:
        return []


# ── 세션 ─────────────────────────────────────────────────────────

def create_session(sb, user_uid: str, tenant_id: Optional[int], project_id: Optional[int]) -> str:
    return _create_session(sb, tenant_id, project_id, user_uid, table=_SESSION_TABLE)


def update_session_title(sb, session_uid: str, title: str) -> None:
    _q(sb, _SESSION_TABLE).update({"sessiontitles": title}).eq("sessionuid", session_uid).execute()


def get_session_info(sb, session_uid: str) -> dict:
    """세션의 tenantid, projectid 반환."""
    try:
        res = _q(sb, _SESSION_TABLE).select("tenantid,projectid").eq("sessionuid", session_uid).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return {}


def delete_session(sb, session_uid: str, creator: str) -> bool:
    return _delete_session(sb, session_uid, creator, table=_SESSION_TABLE)


# ── Q&A ──────────────────────────────────────────────────────────

def append_qa(
    sb,
    session_uid: str,
    tenant_id: Optional[int],
    project_id: Optional[int],
    question: str,
    answer: str,
    dataset: Optional[str],
    creator: str,
    is_first: bool = False,
    qauid: Optional[str] = None,
    inputtoken: Optional[int] = None,
    outputtoken: Optional[int] = None,
) -> str:
    payload = {
        "tenantid":   tenant_id,
        "projectid":  project_id,
        "sessionuid": session_uid,
        "question":   question,
        "answer":     answer,
        "dataset":    dataset,
        "favoriteyn": False,
        "creator":    creator,
    }
    if qauid:
        payload["qauid"] = qauid
    if inputtoken is not None:
        payload["inputtoken"] = inputtoken
    if outputtoken is not None:
        payload["outputtoken"] = outputtoken

    res = _q(sb, _QA_TABLE).insert(payload).execute()

    if is_first:
        update_session_title(sb, session_uid, question[:50])

    return res.data[0]["qauid"]


def get_qa_count(sb, session_uid: str) -> int:
    return _get_qa_count(sb, session_uid, table=_QA_TABLE)


def get_history_by_date(sb, creator: str) -> dict:
    """날짜 → 세션 요약 목록. 즐겨찾기 여부 포함."""
    return _get_history_by_date(sb, creator, session_table=_SESSION_TABLE, fav_table=_FAV_TABLE)


def get_session_messages(sb, session_uid: str) -> dict:
    """chat_qas → HistoryView 호환 messages 형식."""
    res = (
        _q(sb, _QA_TABLE)
        .select("*")
        .eq("sessionuid", session_uid)
        .order("createdts")
        .execute()
    )

    messages = []
    for qa in (res.data or []):
        messages.append({
            "role":      "user",
            "content":   qa["question"],
            "timestamp": qa["createdts"],
            "qauid":     qa["qauid"],
        })
        ans = _parse_answer(qa.get("answer"))
        messages.append({
            "role":               "assistant",
            "content":            ans["text"],
            "timestamp":          qa["createdts"],
            "query":              None,
            "visualization_type": ans["visualization_type"],
            "table_html":         ans["table_html"],
            "chart_image":        ans["chart_image"],
        })

    return {"session_id": session_uid, "messages": messages}


# ── 즐겨찾기 (chat_favorites 기반, chat_qas.favoriteyn 동기) ─────

def add_favorite_qa(sb, qauid: str, creator: str) -> None:
    """chat_favorites에 Q&A 복사(중복 방지) + chat_qas.favoriteyn = True."""
    _add_favorite_qa(sb, qauid, creator, qa_table=_QA_TABLE, fav_table=_FAV_TABLE, extra_fav_fields=["dataset"])


def remove_favorite_qa(sb, qauid: str, creator: str) -> None:
    """chat_favorites에서 Q&A 삭제 + chat_qas.favoriteyn = False."""
    _remove_favorite_qa(sb, qauid, creator, qa_table=_QA_TABLE, fav_table=_FAV_TABLE)


def get_favorites(sb, creator: str) -> list:
    """즐겨찾기 Q&A 목록 — chat_favorites (최신순)."""
    return _get_favorites(sb, creator, fav_table=_FAV_TABLE, include_viz=True, extra_fields=["dataset"])


# ── 공유 ─────────────────────────────────────────────────────────

def share_session(
    sb,
    session_uid: str,
    target_user_uids: list,
    tenant_id: Optional[int],
    project_id: Optional[int],
    session_titles: str,
    creator: str,
) -> str:
    # 1. chat_session_shares
    share_res = _q(sb, "chat_session_shares").insert({
        "sessionuid":      session_uid,
        "tenantid":        tenant_id,
        "projectid":       project_id,
        "sessiontitles":   session_titles,
        "targetuseruids":  json.dumps(target_user_uids),
        "isdeleted":       False,
        "creator":         creator,
    }).execute()
    share_uid = share_res.data[0]["shareuid"]

    # 2. chat_session_share_users (한 명씩)
    for uid in target_user_uids:
        _q(sb, "chat_session_share_users").insert({
            "shareuid":       share_uid,
            "sessionuid":     session_uid,
            "tenantid":       tenant_id,
            "projectid":      project_id,
            "sessiontitles":  session_titles,
            "targetuseruid":  uid,
            "isdeleted":      False,
            "creator":        creator,
        }).execute()

    # 3. chat_snapshots (공유 시점 Q&A 복사)
    qa_res = (
        _q(sb, _QA_TABLE)
        .select("*")
        .eq("sessionuid", session_uid)
        .order("createdts")
        .execute()
    )
    for qa in (qa_res.data or []):
        _q(sb, "chat_snapshots").insert({
            "shareuid":   share_uid,
            "qauid":      qa["qauid"],
            "tenantid":   tenant_id,
            "projectid":  project_id,
            "sessionuid": session_uid,
            "question":   qa["question"],
            "answer":     qa["answer"],
            "dataset":    qa["dataset"],
            "creator":    creator,
        }).execute()

    return share_uid


def delete_share(sb, share_uid: str, creator: str) -> None:
    """발신자 소프트 삭제: chat_session_shares만 isdeleted = True. 수신자 rows는 유지."""
    _q(sb, "chat_session_shares").update({"isdeleted": True}).eq("shareuid", share_uid).eq("creator", creator).execute()


def delete_share_received(sb, share_uid: str, target_user_uid: str) -> None:
    """수신자 소프트 삭제: 해당 사용자의 chat_session_share_users row만 isdeleted = True."""
    (
        _q(sb, "chat_session_share_users")
        .update({"isdeleted": True})
        .eq("shareuid", share_uid)
        .eq("targetuseruid", target_user_uid)
        .execute()
    )


def get_shares_sent(sb, creator: str) -> list:
    res = (
        _q(sb, "chat_session_shares")
        .select("shareuid,sessionuid,sessiontitles,targetuseruids,createdts")
        # .select("shareuid,sessionuid,sessiontitles,targetuseruids,createdt,createdts")
        .eq("creator", creator)
        .or_("isdeleted.is.false,isdeleted.is.null")
        .order("createdts", desc=True)
        .execute()
    )
    return res.data or []


def get_shares_received(sb, target_user_uid: str) -> list:
    res = (
        _q(sb, "chat_session_share_users")
        .select("shareuid,sessionuid,sessiontitles,creator,createdts")
        # .select("shareuid,sessionuid,sessiontitles,creator,createdt,createdts")
        .eq("targetuseruid", target_user_uid)
        .or_("isdeleted.is.false,isdeleted.is.null")
        .order("createdts", desc=True)
        .execute()
    )
    return res.data or []


def get_snapshot_messages(sb, share_uid: str) -> dict:
    """chat_snapshots → HistoryView 호환 messages 형식."""
    res = (
        _q(sb, "chat_snapshots")
        .select("*")
        .eq("shareuid", share_uid)
        .order("createdts")
        .execute()
    )

    messages = []
    for snap in (res.data or []):
        messages.append({
            "role":      "user",
            "content":   snap["question"],
            "timestamp": snap["createdts"],
        })
        ans = _parse_answer(snap.get("answer"))
        messages.append({
            "role":               "assistant",
            "content":            ans["text"],
            "timestamp":          snap["createdts"],
            "query":              None,
            "visualization_type": ans["visualization_type"],
            "table_html":         ans["table_html"],
            "chart_image":        ans["chart_image"],
        })

    return {"share_uid": share_uid, "messages": messages}
