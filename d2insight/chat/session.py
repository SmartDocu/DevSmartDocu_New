"""Supabase 기반 세션 관리 (insight_sessions + insight_qas)."""
from __future__ import annotations

from d2insight.db import insight_storage


def get_or_create(
    session_id: str | None,
    user_id: str | None = None,
    project_id: int | None = None,
) -> tuple[str, list[dict]]:
    """세션 ID가 있으면 DB에서 히스토리를 로드하고, 없으면 새 세션을 생성한다."""
    creator = user_id or None
    if session_id:
        session = insight_storage.get_session(session_id)
        if session:
            hist = insight_storage.get_session_messages(session_id)
            return session_id, hist
    tenant_id, db_project_id = insight_storage.get_project_info(creator) if creator else (None, None)
    sid = insight_storage.create_session(tenant_id, project_id if project_id is not None else db_project_id, creator)
    return sid, []


def append_qa(
    session_id: str,
    question: str,
    answer_json: dict,
    user_id: str | None = None,
    project_id: int | None = None,
    filenm: str | None = None,
    fileurl: str | None = None,
    inputtoken: int | None = None,
    outputtoken: int | None = None,
    servicecd: str = "In",
) -> str:
    """QA 한 쌍을 insight_qas에 저장하고 qauid를 반환한다."""
    creator = user_id or None
    tenant_id, db_project_id = insight_storage.get_project_info(creator) if creator else (None, None)
    return insight_storage.append_qa(
        session_uid=session_id,
        tenant_id=tenant_id,
        project_id=project_id if project_id is not None else db_project_id,
        question=question,
        answer_json=answer_json,
        creator=creator,
        filenm=filenm,
        fileurl=fileurl,
        inputtoken=inputtoken,
        outputtoken=outputtoken,
        servicecd=servicecd,
    )
