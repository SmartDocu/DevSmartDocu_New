"""insight_sessions + insight_qas CRUD (pr_d2chat supabase_storage.py 패턴)."""
from __future__ import annotations

import json
from typing import Optional

from d2insight.db import supabase_client as _sc
from d2insight.db.supabase_client import build_shares_path, delete_from_storage


# ── 사용자 / 프로젝트 정보 ────────────────────────────────────────

def get_project_info(user_uid: str) -> tuple[int | None, int | None]:
    """projects 테이블에서 tenantid, projectid 반환 (pr_d2chat 패턴)."""
    try:
        res = _sc.table("projects").select("tenantid,projectid").eq("creator", user_uid).execute()
        if res.data:
            row = res.data[0]
            return row.get("tenantid"), row.get("projectid")
    except Exception:
        pass
    return None, None


# ── 세션 ──────────────────────────────────────────────────────────

def create_session(tenant_id: int | None, project_id: int | None, creator: str | None) -> str:
    """insight_sessions 레코드를 생성하고 sessionuid를 반환한다."""
    res = _sc.table("insight_sessions").insert({
        "tenantid": tenant_id or None,
        "projectid": project_id or None,
        "sessiontitles": "",
        "sessionstatuscd": "Active",
        "creator": creator or None,
    }).execute()
    return res.data[0]["sessionuid"]


def get_session(session_uid: str) -> dict | None:
    res = (
        _sc.table("insight_sessions")
        .select("*")
        .eq("sessionuid", session_uid)
        .execute()
    )
    return res.data[0] if res.data else None


def update_session_title(session_uid: str, title: str) -> None:
    _sc.table("insight_sessions").update({"sessiontitles": title}).eq("sessionuid", session_uid).execute()


def delete_session(session_uid: str, creator: str) -> bool:
    """소프트 삭제 — sessionstatuscd를 Archived로 변경."""
    _sc.table("insight_sessions").update({"sessionstatuscd": "Archived"}).eq("sessionuid", session_uid).eq("creator", creator).execute()
    return True


def get_history_by_date(creator: str) -> dict:
    """날짜별로 그룹화된 세션 목록을 반환한다."""
    try:
        q = (
            _sc.table("insight_sessions")
            .select("sessionuid, sessiontitles, createdts")
            .eq("sessionstatuscd", "Active")
            .neq("sessiontitles", "")
            .order("createdts", desc=True)
        )
        if creator:
            q = q.eq("creator", creator)
        res = q.execute()
        grouped: dict = {}
        for row in (res.data or []):
            date_key = str(row.get("createdts", ""))[:10]
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append({
                "session_id": row["sessionuid"],
                "title": row.get("sessiontitles", ""),
                "created_at": row.get("createdts", ""),
            })
        return grouped
    except Exception:
        return {}


# ── Q&A ──────────────────────────────────────────────────────────

def append_qa(
    session_uid: str,
    tenant_id: int | None,
    project_id: int | None,
    question: str,
    answer_json: dict,
    creator: str | None,
    filenm: str | None = None,
    fileurl: str | None = None,
    inputtoken: int | None = None,
    outputtoken: int | None = None,
    servicecd: str = "In",
) -> str:
    """QA를 insight_qas에 저장하고 qauid를 반환한다.

    첫 QA 저장 시 세션 제목을 질문 앞 50자로 자동 설정한다.
    """
    row: dict = {
        "sessionuid": session_uid,
        "tenantid": tenant_id or None,
        "projectid": project_id or None,
        "question": question,
        "answer": json.dumps(answer_json, ensure_ascii=False),
        "creator": creator or None,
        "favoriteyn": False,
        "servicecd": servicecd,
    }
    if filenm:
        row["filenm"] = filenm
    if fileurl:
        row["fileurl"] = fileurl
    if inputtoken is not None:
        row["inputtoken"] = inputtoken
    if outputtoken is not None:
        row["outputtoken"] = outputtoken

    res = _sc.table("insight_qas").insert(row).execute()
    qauid: str = res.data[0]["qauid"]

    session = get_session(session_uid)
    if session and not session.get("sessiontitles"):
        update_session_title(session_uid, question[:50])

    return qauid


def get_session_messages(session_uid: str) -> list[dict]:
    """LLM 컨텍스트 + 히스토리 뷰용 메시지 배열 반환."""
    res = (
        _sc.table("insight_qas")
        .select("qauid, question, answer, filenm, fileurl")
        .eq("sessionuid", session_uid)
        .order("createdts", desc=False)
        .execute()
    )
    messages: list[dict] = []
    for row in res.data:
        messages.append({"role": "user", "content": row["question"], "qauid": row["qauid"]})
        try:
            obj = json.loads(row["answer"])
            answer_text = obj.get("answer", "") if isinstance(obj, dict) else str(obj)
        except (json.JSONDecodeError, TypeError):
            answer_text = row["answer"] or ""
        messages.append({
            "role": "assistant",
            "content": answer_text,
            "reportPath": row.get("filenm"),
            "fileurl": row.get("fileurl"),
            "qauid": row["qauid"],
        })
    return messages


def get_qa(qauid: str) -> dict | None:
    res = _sc.table("insight_qas").select("*").eq("qauid", qauid).execute()
    return res.data[0] if res.data else None


def get_qa_count(session_uid: str) -> int:
    res = (
        _sc.table("insight_qas")
        .select("qauid", count="exact")
        .eq("sessionuid", session_uid)
        .execute()
    )
    return res.count or 0


def insert_llm_api_logs(
    calls: list[dict],
    qauid: str,
    session_uid: str,
    tenant_id: int | None,
    project_id: int | None,
    creator: str | None,
    questiontypecd: str,
) -> None:
    """LLM 호출 명세를 llm_api_logs에 일괄 삽입한다."""
    if not calls:
        return
    rows = []
    for c in calls:
        _start = c.get("startdts")
        _end = c.get("enddts")
        rows.append({
            "qauid": qauid,
            "servicecd": "In",
            "questiontypecd": questiontypecd,
            "tenantid": tenant_id or None,
            "projectid": project_id or None,
            "sessionuid": session_uid,
            "stepnm": c.get("stepnm") or None,
            "steptitle": c.get("steptitle") or None,
            "llmmodelnm": c.get("model_id") or c.get("model") or None,
            "inputtoken": c.get("input", 0),
            "outputtoken": c.get("output", 0),
            "status": "C",
            "creator": creator or None,
            "startdts": _start.isoformat() if _start else None,
            "enddts": _end.isoformat() if _end else None,
        })
    try:
        _sc.table("llm_api_logs").insert(rows).execute()
    except Exception as e:
        print(f"[insight_storage] insert_llm_api_logs 오류: {e}")


# ── 즐겨찾기 ─────────────────────────────────────────────────────

def add_favorite_qa(qauid: str, creator: str) -> bool:
    """QA를 insight_favorites에 복사한다."""
    qa = get_qa(qauid)
    if not qa:
        return False
    try:
        _sc.table("insight_favorites").insert({
            "tenantid": qa.get("tenantid"),
            "projectid": qa.get("projectid"),
            "sessionuid": qa.get("sessionuid"),
            "qauid": qauid,
            "question": qa.get("question"),
            "answer": qa.get("answer"),
            "fileurl": qa.get("fileurl"),
            "filenm": qa.get("filenm"),
            "creator": creator or None,
        }).execute()
        _sc.table("insight_qas").update({"favoriteyn": True}).eq("qauid", qauid).execute()
        return True
    except Exception:
        return False


def remove_favorite_qa(qauid: str, creator: str) -> bool:
    """insight_favorites에서 삭제하고 원본 QA의 favoriteyn을 False로 설정한다."""
    try:
        _sc.table("insight_favorites").delete().eq("qauid", qauid).eq("creator", creator).execute()
        _sc.table("insight_qas").update({"favoriteyn": False}).eq("qauid", qauid).execute()
        return True
    except Exception:
        return False


def get_favorites(creator: str) -> list[dict]:
    """내 즐겨찾기 목록을 반환한다."""
    try:
        res = (
            _sc.table("insight_favorites")
            .select("favoriteuid, qauid, sessionuid, question, answer, filenm, createdts")
            .eq("creator", creator)
            .order("createdts", desc=True)
            .execute()
        )
        result = []
        for row in (res.data or []):
            answer_text = ""
            try:
                obj = json.loads(row.get("answer") or "{}")
                answer_text = obj.get("answer", "") if isinstance(obj, dict) else ""
            except Exception:
                pass
            result.append({
                "favoriteuid": row["favoriteuid"],
                "qauid": row["qauid"],
                "session_id": row.get("sessionuid"),
                "question": row.get("question", ""),
                "answer": answer_text,
                "filenm": row.get("filenm"),
                "fileurl": row.get("fileurl"),
                "created_at": row.get("createdts"),
            })
        return result
    except Exception:
        return []


# ── 폴더 ─────────────────────────────────────────────────────────

def get_folders(tenant_id: int | None) -> list[dict]:
    """insight_folders에서 폴더 목록 반환 (삭제되지 않은 것만)."""
    try:
        q = (
            _sc.table("insight_folders")
            .select("folderuid, foldernm, folderlevel, parent_folderuid, orderno")
            .neq("is_deleted", True)
            .order("folderlevel")
            .order("orderno")
        )
        if tenant_id is not None:
            q = q.or_(f"tenantid.eq.{tenant_id},tenantid.is.null")
        res = q.execute()
        return res.data or []
    except Exception as e:
        print(f"[insight_storage] get_folders 오류: {e}")
        return []


def seed_sample_folders(tenant_id: int | None, creator: str | None) -> None:
    """폴더가 없으면 샘플 폴더를 삽입한다."""
    try:
        if get_folders(tenant_id):
            return

        safe_creator = creator if creator and creator != "undefined" else None
        base = {"tenantid": tenant_id, "creator": safe_creator}

        sales_res = _sc.table("insight_folders").insert(
            {**base, "foldernm": "판매", "folderlevel": 1, "orderno": 1}
        ).execute()
        sales_uid = sales_res.data[0]["folderuid"]

        _sc.table("insight_folders").insert([
            {**base, "foldernm": "서버로그",       "folderlevel": 1, "orderno": 2},
            {**base, "foldernm": "인터페이스로그", "folderlevel": 1, "orderno": 3},
        ]).execute()

        _sc.table("insight_folders").insert(
            {**base, "foldernm": "지역", "folderlevel": 2, "orderno": 1,
             "parent_folderuid": sales_uid}
        ).execute()

        print(f"[insight_storage] 샘플 폴더 생성 완료 (tenant_id={tenant_id})")
    except Exception as e:
        print(f"[insight_storage] seed_sample_folders 오류: {e}")


# ── 공유 ─────────────────────────────────────────────────────────

def share_qa(qauid: str, creator: str, folder_uid: str | None = None) -> bool:
    """QA를 insight_qa_shares에 복사해 같은 tenant에 공유한다."""
    qa = get_qa(qauid)
    if not qa:
        return False
    tenant_id, project_id = get_project_info(creator)
    try:
        src_fileurl = qa.get("fileurl") or ""
        filenm = qa.get("filenm") or ""

        if src_fileurl.endswith(".pdf"):
            share_fileurl = src_fileurl[:-4] + ".md"
        else:
            share_fileurl = src_fileurl

        row: dict = {
            "tenantid": tenant_id,
            "projectid": project_id,
            "sessionuid": qa.get("sessionuid"),
            "question": qa.get("question"),
            "answer": qa.get("answer"),
            "fileurl": share_fileurl,
            "filenm": filenm,
            "creator": creator or None,
        }
        if folder_uid:
            row["folderuid"] = folder_uid
        _sc.table("insight_qa_shares").insert(row).execute()
        return True
    except Exception as e:
        print(f"[insight_storage] share_qa 오류: {e}")
        return False


def get_shares_sent(creator: str) -> list[dict]:
    """내가 공유한 QA 목록을 반환한다."""
    try:
        res = (
            _sc.table("insight_qa_shares")
            .select("qauid, sessionuid, question, answer, filenm, fileurl, createdts")
            .eq("creator", creator)
            .order("createdts", desc=True)
            .execute()
        )
        return _format_share_rows(res.data or [])
    except Exception:
        return []


def delete_share_sent(share_qauid: str, creator: str) -> bool:
    """내가 공유한 레코드를 삭제하고 공유 스토리지 파일도 함께 삭제한다."""
    try:
        row = get_share(share_qauid)
        if not row:
            return False
        if row.get("creator") != creator:
            return False

        fileurl: str = row.get("fileurl") or ""
        filenm: str = row.get("filenm") or ""
        if fileurl and filenm:
            try:
                tenant_id, project_id = get_project_info(creator)
                pdf_filename = filenm.replace(".md", ".pdf")
                storage_path = build_shares_path(tenant_id, project_id, pdf_filename)
                delete_from_storage(storage_path)
            except Exception as se:
                print(f"[insight_storage] 공유 스토리지 파일 삭제 실패: {se}")

        _sc.table("insight_qa_shares").delete().eq("qauid", share_qauid).execute()
        return True
    except Exception as e:
        print(f"[insight_storage] delete_share_sent 오류: {e}")
        return False


def get_all_shares(project_id: int | None) -> list[dict]:
    """같은 project의 모든 공유 보고서 반환."""
    try:
        q = (
            _sc.table("insight_qa_shares")
            .select("qauid, sessionuid, question, answer, filenm, fileurl, creator, createdts, folderuid")
            .order("createdts", desc=True)
        )
        if project_id is not None:
            q = q.or_(f"projectid.eq.{project_id},projectid.is.null")
        else:
            q = q.is_("projectid", "null")
        res = q.execute()
        return _format_share_rows(res.data or [])
    except Exception:
        return []


def get_shares_received(project_id: int | None, my_creator: str) -> list[dict]:
    """같은 projectid에서 내가 creator가 아닌 공유 QA 목록을 반환한다."""
    try:
        q = (
            _sc.table("insight_qa_shares")
            .select("qauid, sessionuid, question, answer, filenm, fileurl, creator, createdts")
            .neq("creator", my_creator)
            .order("createdts", desc=True)
        )
        if project_id is not None:
            q = q.or_(f"projectid.eq.{project_id},projectid.is.null")
        else:
            q = q.is_("projectid", "null")
        res = q.execute()
        return _format_share_rows(res.data or [])
    except Exception:
        return []


def delete_share_received(share_qauid: str, creator: str) -> bool:
    """공유받은 항목을 목록에서 제거한다."""
    try:
        _sc.table("insight_qa_shares").delete().eq("qauid", share_qauid).execute()
        return True
    except Exception:
        return False


def get_share(share_qauid: str) -> dict | None:
    """공유된 단일 QA 조회."""
    try:
        res = _sc.table("insight_qa_shares").select("*").eq("qauid", share_qauid).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def _format_share_rows(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        answer_text = ""
        try:
            obj = json.loads(row.get("answer") or "{}")
            answer_text = obj.get("answer", "") if isinstance(obj, dict) else ""
        except Exception:
            pass
        result.append({
            "share_qauid": row["qauid"],
            "session_id": row.get("sessionuid"),
            "question": row.get("question", ""),
            "answer": answer_text,
            "filenm": row.get("filenm"),
            "fileurl": row.get("fileurl"),
            "folder_uid": row.get("folderuid"),
            "creator": row.get("creator"),
            "created_at": row.get("createdts"),
        })
    return result
