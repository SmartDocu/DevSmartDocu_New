"""Supabase 기반 대화 저장소 (service role key 사용 — RLS 우회)."""
import json
from typing import Optional, Tuple


def _sb():
    from utilsPrj.supabase_client import get_service_client
    from backend.app.config import settings
    return get_service_client().schema(settings.SUPABASE_SCHEMA)


def _q(table: str):
    return _sb().table(table)


def _parse_answer(answer_raw: Optional[str]) -> dict:
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


# ── 사용자 / 프로젝트 정보 ─────────────────────────────────────────

def get_project_info(user_uid: str) -> Tuple[Optional[int], Optional[int]]:
    try:
        res = _q("projects").select("tenantid,projectid").eq("creator", user_uid).execute()
        if res.data:
            row = res.data[0]
            return row.get("tenantid"), row.get("projectid")
    except Exception:
        pass
    return None, None


def get_users_same_tenant(tenant_id: int, exclude_uid: str, project_id: int = None) -> list:
    try:
        proj_res = (
            _q("projects")
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
            user_res = _q("users").select("creator,email,usernm").in_("creator", uids).execute()
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


# ── 세션 ──────────────────────────────────────────────────────────

def create_session(user_uid: str, tenant_id: Optional[int], project_id: Optional[int]) -> str:
    res = _q("chat_sessions").insert({
        "tenantid":        tenant_id,
        "projectid":       project_id,
        "sessiontitles":   "",
        "sessionstatuscd": "Active",
        "creator":         user_uid,
    }).execute()
    return res.data[0]["sessionuid"]


def update_session_title(session_uid: str, title: str) -> None:
    _q("chat_sessions").update({"sessiontitles": title}).eq("sessionuid", session_uid).execute()


def get_session_info(session_uid: str) -> dict:
    try:
        res = _q("chat_sessions").select("tenantid,projectid").eq("sessionuid", session_uid).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return {}


def delete_session(session_uid: str, creator: str) -> bool:
    _q("chat_sessions").update({"sessionstatuscd": "Archived"}).eq("sessionuid", session_uid).eq("creator", creator).execute()
    return True


# ── Q&A ───────────────────────────────────────────────────────────

def append_qa(
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

    res = _q("chat_qas").insert(payload).execute()
    if is_first:
        update_session_title(session_uid, question[:50])
    return res.data[0]["qauid"]


def get_qa_count(session_uid: str) -> int:
    try:
        res = _q("chat_qas").select("qauid", count="exact").eq("sessionuid", session_uid).execute()
        return res.count or 0
    except Exception:
        return 0


def get_history_by_date(creator: str) -> dict:
    sess_res = (
        _q("chat_sessions")
        .select("sessionuid,sessiontitles,createdt,createdts")
        .eq("creator", creator)
        .eq("sessionstatuscd", "Active")
        .neq("sessiontitles", "")
        .order("createdts", desc=True)
        .execute()
    )
    fav_res = (
        _q("chat_favorites")
        .select("sessionuid")
        .eq("creator", creator)
        .execute()
    )
    fav_uids = {r["sessionuid"] for r in (fav_res.data or [])}

    result: dict = {}
    for row in (sess_res.data or []):
        d = str(row["createdt"])
        result.setdefault(d, []).append({
            "session_id":  row["sessionuid"],
            "title":       row["sessiontitles"] or "",
            "created_at":  row["createdts"],
            "is_favorite": row["sessionuid"] in fav_uids,
        })
    return result


def get_session_messages(session_uid: str) -> dict:
    res = (
        _q("chat_qas")
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


# ── 즐겨찾기 ─────────────────────────────────────────────────────

def add_favorite_qa(qauid: str, creator: str) -> None:
    existing = _q("chat_favorites").select("favoriteuid").eq("qauid", qauid).eq("creator", creator).execute()
    if existing.data:
        return
    qa_res = _q("chat_qas").select("*").eq("qauid", qauid).execute()
    if not qa_res.data:
        return
    qa = qa_res.data[0]
    _q("chat_favorites").insert({
        "tenantid":   qa.get("tenantid"),
        "projectid":  qa.get("projectid"),
        "sessionuid": qa.get("sessionuid"),
        "qauid":      qauid,
        "question":   qa["question"],
        "answer":     qa["answer"],
        "dataset":    qa.get("dataset"),
        "creator":    creator,
    }).execute()
    _q("chat_qas").update({"favoriteyn": True}).eq("qauid", qauid).execute()


def remove_favorite_qa(qauid: str, creator: str) -> None:
    _q("chat_favorites").delete().eq("qauid", qauid).eq("creator", creator).execute()
    _q("chat_qas").update({"favoriteyn": False}).eq("qauid", qauid).execute()


def get_favorites(creator: str) -> list:
    res = (
        _q("chat_favorites")
        .select("favoriteuid,qauid,sessionuid,question,answer,dataset,createdt,createdts")
        .eq("creator", creator)
        .order("createdts", desc=True)
        .execute()
    )
    result = []
    for row in (res.data or []):
        ans = _parse_answer(row.get("answer"))
        result.append({
            "qauid":              row["qauid"],
            "session_id":         row["sessionuid"],
            "question":           row["question"],
            "answer":             ans["text"],
            "visualization_type": ans["visualization_type"],
            "table_html":         ans["table_html"],
            "chart_image":        ans["chart_image"],
            "create_dt":          str(row.get("createdt", "")),
        })
    return result


# ── 공유 ──────────────────────────────────────────────────────────

def share_session(
    session_uid: str,
    target_user_uids: list,
    tenant_id: Optional[int],
    project_id: Optional[int],
    session_titles: str,
    creator: str,
) -> str:
    share_res = _q("chat_session_shares").insert({
        "sessionuid":     session_uid,
        "tenantid":       tenant_id,
        "projectid":      project_id,
        "sessiontitles":  session_titles,
        "targetuseruids": json.dumps(target_user_uids),
        "isdeleted":      False,
        "creator":        creator,
    }).execute()
    share_uid = share_res.data[0]["shareuid"]

    for uid in target_user_uids:
        _q("chat_session_share_users").insert({
            "shareuid":      share_uid,
            "sessionuid":    session_uid,
            "tenantid":      tenant_id,
            "projectid":     project_id,
            "sessiontitles": session_titles,
            "targetuseruid": uid,
            "isdeleted":     False,
            "creator":       creator,
        }).execute()

    qa_res = _q("chat_qas").select("*").eq("sessionuid", session_uid).order("createdts").execute()
    for qa in (qa_res.data or []):
        _q("chat_snapshots").insert({
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


def delete_share(share_uid: str, creator: str) -> None:
    _q("chat_session_shares").update({"isdeleted": True}).eq("shareuid", share_uid).eq("creator", creator).execute()


def delete_share_received(share_uid: str, target_user_uid: str) -> None:
    _q("chat_session_share_users").update({"isdeleted": True}).eq("shareuid", share_uid).eq("targetuseruid", target_user_uid).execute()


def get_shares_sent(creator: str) -> list:
    res = (
        _q("chat_session_shares")
        .select("shareuid,sessionuid,sessiontitles,targetuseruids,createdt,createdts")
        .eq("creator", creator)
        .or_("isdeleted.is.false,isdeleted.is.null")
        .order("createdts", desc=True)
        .execute()
    )
    return res.data or []


def get_shares_received(target_user_uid: str) -> list:
    res = (
        _q("chat_session_share_users")
        .select("shareuid,sessionuid,sessiontitles,creator,createdt,createdts")
        .eq("targetuseruid", target_user_uid)
        .or_("isdeleted.is.false,isdeleted.is.null")
        .order("createdts", desc=True)
        .execute()
    )
    return res.data or []


def get_snapshot_messages(share_uid: str) -> dict:
    res = (
        _q("chat_snapshots")
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
