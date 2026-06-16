"""Supabase 기반 세션 관리."""
from __future__ import annotations

from d2insight.history import insight_storage


def get_or_create(session_id: str | None, user_id: str | None = None) -> tuple[str, list[dict]]:
    creator = user_id or None
    if session_id:
        session = insight_storage.get_session(session_id)
        if session:
            hist = insight_storage.get_session_messages(session_id)
            return session_id, hist
    tenant_id, project_id = insight_storage.get_project_info(creator) if creator else (None, None)
    sid = insight_storage.create_session(tenant_id, project_id, creator)
    return sid, []


def append_qa(
    session_id: str,
    question: str,
    answer_json: dict,
    user_id: str | None = None,
    filenm: str | None = None,
    fileurl: str | None = None,
    inputtoken: int | None = None,
    outputtoken: int | None = None,
    servicecd: str = "I",
) -> str:
    creator = user_id or None
    tenant_id, project_id = insight_storage.get_project_info(creator) if creator else (None, None)
    return insight_storage.append_qa(
        session_uid=session_id,
        tenant_id=tenant_id,
        project_id=project_id,
        question=question,
        answer_json=answer_json,
        creator=creator,
        filenm=filenm,
        fileurl=fileurl,
        inputtoken=inputtoken,
        outputtoken=outputtoken,
        servicecd=servicecd,
    )
