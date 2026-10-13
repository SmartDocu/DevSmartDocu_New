"""문서/챕터 생성 실패 이력 — 일반 사용자용 (소속별 범위 제한, traceback 원문 비노출).

시스템 관리자(roleid=7) 전체 조회는 auditlogs.py의 /auditlogs/gen-failures. 여기는 로그인 사용자의
소속에 따라 볼 수 있는 범위가 서버에서 정해진다(클라이언트가 보낸 projectid는 소속 검증에만 쓴다):

  - 시스템 기업        : 본인이 구성원인 프로젝트들(여러 개면 합쳐서)
  - 회사 기업 매니저   : 해당 기업의 모든 프로젝트
  - 그 외 회사 구성원  : 현재 선택된 프로젝트 한 곳(본인이 구성원이어야 함)
  - 프로젝트 역할      : 프로젝트 매니저(M)는 그 프로젝트 전체, 일반(U)은 본인이 실행한 실패만

응답에는 errormessage(traceback 원문)를 넣지 않는다 — 서버 경로 등 내부 정보 노출 방지.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies import get_token, get_tenantid, get_user, require_doc_read
from backend.app.routers.auditlogs import (
    _attach_target_names, _attach_user_info, _default_dates, _fmt_dt, _get_offsetminutes,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()


def _resolve_scope(sd, user_id: str, tenantid: Optional[str], projectid: Optional[int]) -> tuple[list[int], list[int]]:
    """(전체 조회 가능 projectid 목록, 본인 실패만 조회 가능한 projectid 목록)을 구한다."""
    if not tenantid:
        raise HTTPException(status_code=403, detail="msg.service.read.forbidden")
    tid = int(tenantid)
    S = SUPABASE_SCHEMA

    tu = sd.schema(S).table("tenantusers").select("rolecd").eq("tenantid", tid).eq("useruid", user_id).eq("useyn", True).limit(1).execute().data or []
    if not tu:
        raise HTTPException(status_code=403, detail="msg.service.read.forbidden")
    tenant = sd.schema(S).table("tenants").select("issystemtenant").eq("tenantid", tid).limit(1).execute().data or []
    is_system = bool(tenant and tenant[0].get("issystemtenant"))

    tenant_projects = {p["projectid"] for p in (sd.schema(S).table("projects").select("projectid").eq("tenantid", tid).execute().data or [])}
    if not tenant_projects:
        return [], []

    if not is_system and tu[0].get("rolecd") == "M":
        return sorted(tenant_projects), []   # 회사 기업 매니저 — 기업 전체

    pu = sd.schema(S).table("projectusers").select("projectid,rolecd").eq("useruid", user_id).eq("useyn", True) \
        .in_("projectid", list(tenant_projects)).execute().data or []
    role_by_project = {r["projectid"]: r.get("rolecd") for r in pu}
    if not is_system:
        # 회사 일반 구성원 — 현재 선택된 프로젝트 하나로 한정(소속이 아니면 아무것도 못 본다)
        role_by_project = {pid: role for pid, role in role_by_project.items() if pid == projectid}

    all_ids = sorted(pid for pid, role in role_by_project.items() if role == "M")
    own_ids = sorted(pid for pid, role in role_by_project.items() if role != "M")
    return all_ids, own_ids


@router.get("", dependencies=[Depends(require_doc_read)])
def list_my_gen_failures(
    kind: str = Query("doc", pattern="^(doc|chapter)$"),
    projectid: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    errorcd: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = get_user(token)
    user_id = str(user.id)
    sd = get_service_client()   # 범위는 아래 _resolve_scope가 소속으로 직접 제한한다
    S = SUPABASE_SCHEMA
    empty = {"items": [], "total": 0, "page": page, "page_size": page_size}

    all_pids, own_pids = _resolve_scope(sd, user_id, tenantid, projectid)
    pids = all_pids + own_pids
    if not pids:
        return empty

    docs = sd.schema(S).table("docs").select("docid,projectid").in_("projectid", pids).execute().data or []
    proj_of_doc = {d["docid"]: d["projectid"] for d in docs}
    all_docids = [d for d, p in proj_of_doc.items() if p in all_pids]
    own_docids = [d for d, p in proj_of_doc.items() if p in own_pids]
    conds = []
    if all_docids:
        conds.append(f"docid.in.({','.join(map(str, all_docids))})")
    if own_docids:
        conds.append(f"and(docid.in.({','.join(map(str, own_docids))}),creator.eq.{user_id})")
    if not conds:
        return empty

    sdate, edate = _default_dates(start_date, end_date)
    table = "gendocs_realtimes" if kind == "doc" else "genchapters_realtimes"
    q = (
        sd.schema(S).table(table).select("*", count="exact")
        .not_.is_("errorcd", "null")
        .gte("startdts", sdate)
        .lt("startdts", (date.fromisoformat(edate) + timedelta(days=1)).isoformat())
        .or_(",".join(conds))
    )
    if errorcd:
        q = q.eq("errorcd", errorcd)
    offset = (page - 1) * page_size
    res = q.order("startdts", desc=True).range(offset, offset + page_size - 1).execute()
    items, total = res.data or [], res.count or 0

    _attach_target_names(sd, items, kind)
    items = _attach_user_info(sd, items, key="creator")

    # 프로젝트명 보강(여러 프로젝트가 섞일 수 있는 시스템/기업 매니저 화면용)
    proj_ids = list({proj_of_doc.get(r.get("docid")) for r in items if proj_of_doc.get(r.get("docid")) is not None})
    proj_nm = {}
    if proj_ids:
        rows = sd.schema(S).table("projects").select("projectid,projectnm").in_("projectid", proj_ids).execute().data or []
        proj_nm = {r["projectid"]: r["projectnm"] for r in rows}

    offsetminutes = _get_offsetminutes(sd, user_id, tenantid)
    out = []
    for r in items:
        out.append({
            "jobuid": r.get("gendocjobuid") if kind == "doc" else r.get("genchapterjobuid"),
            "startdts": _fmt_dt(r.get("startdts"), offsetminutes),
            "usernm": r.get("usernm"), "email": r.get("email"),
            "projectnm": proj_nm.get(proj_of_doc.get(r.get("docid")), ""),
            "docnm": r.get("gendocnm") if kind == "doc" else r.get("docnm"),
            "chapternm": r.get("chapternm") if kind == "chapter" else r.get("failed_chapternm"),
            "errorcd": r.get("errorcd"),
        })
    return {"items": out, "total": total, "page": page, "page_size": page_size}
