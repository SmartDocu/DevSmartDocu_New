from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client
from utilsPrj.audit_log import log_work_action, snapshot_row, get_client_ip

router = APIRouter()


def _dataset_access(user_id: str, tenantid: Optional[str]) -> dict:
    """데이터셋 그룹 관리 접근 권한 확인. 반환: {"tenantid", "issystem", "is_manager"}

    - 기업 테넌트: 해당 테넌트의 매니저(rolecd=M)만 허용.
    - 개인(시스템) 테넌트: 활성 구성원이면 누구나 허용하되, 일반 구성원(rolecd=U)은
      본인이 만든 그룹/본인 프로젝트/본인 데이터 범위로만 제한된다(호출부에서 처리).
      시스템 테넌트는 여러 개인 계정이 하나의 tenantid를 공유하기 때문.

    과거엔 이 체크가 전혀 없어서 X-Tenant-ID 헤더만 바꾸면 인증된 사용자 누구나 다른
    조직의 데이터셋 그룹을 조회·생성·수정·삭제할 수 있었다(2026-09-08 발견·수정)."""
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    tu = svc.table("tenantusers").select("rolecd,useyn").eq("useruid", user_id).eq("tenantid", int(tenantid)).maybe_single().execute()
    if not tu or not tu.data or tu.data.get("useyn") is not True:
        raise HTTPException(status_code=403, detail="테넌트 관리자만 접근할 수 있습니다.")
    is_manager = tu.data.get("rolecd") == "M"
    t_row = svc.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    issystem = bool(t_row and t_row.data and t_row.data.get("issystemtenant"))
    if not is_manager and not issystem:
        raise HTTPException(status_code=403, detail="테넌트 관리자만 접근할 수 있습니다.")
    return {"tenantid": tenantid, "issystem": issystem, "is_manager": is_manager}


def _is_own_scope_only(access: dict) -> bool:
    """개인(시스템) 테넌트의 일반 구성원 — 본인 소유 범위로만 제한해야 하는지."""
    return access["issystem"] and not access["is_manager"]


def _require_dataset_tenant_manager(user_id: str, datasetuid: str) -> dict:
    """datasetuid의 실제 소속 테넌트를 서버에서 조회해 접근 권한을 검증한다
    (클라이언트가 보낸 tid 헤더를 신뢰하지 않음 — datasetuid가 다른 조직 소유일 수 있음).
    개인 테넌트의 일반 구성원은 본인이 만든 그룹만 허용."""
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    row = svc.table("datasets").select("tenantid,creator").eq("datasetuid", datasetuid).maybe_single().execute()
    if not row or not row.data:
        raise HTTPException(status_code=404, detail="데이터셋을 찾을 수 없습니다.")
    access = _dataset_access(user_id, str(row.data["tenantid"]))
    if _is_own_scope_only(access) and row.data.get("creator") != user_id:
        raise HTTPException(status_code=403, detail="본인이 만든 데이터셋만 접근할 수 있습니다.")
    return access


def _validate_own_selection(sb, access: dict, user_id: str, datauids: list[str], projectids: list[int]) -> None:
    """저장하는 프로젝트는 Do 서비스 프로젝트여야 하고, 개인 테넌트 일반 구성원은 멤버/프로젝트가 본인 소유 범위 안이어야 한다."""
    tid = access["tenantid"]
    if projectids:
        do_ids = {p["projectid"] for p in _selectable_projects(sb, user_id, tid)}
        if not set(projectids) <= do_ids and not access["is_manager"]:
            raise HTTPException(status_code=403, detail="선택할 수 없는 프로젝트가 포함되어 있습니다.")
        if access["is_manager"]:
            non_do = (
                sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid")
                .in_("projectid", projectids).neq("servicecd", "Do").execute().data or []
            )
            if non_do:
                raise HTTPException(status_code=400, detail="문서(Do) 서비스 프로젝트만 연결할 수 있습니다.")
    if not _is_own_scope_only(access):
        return
    if datauids:
        allowed = {d["datauid"] for d in _tenant_datas_candidates(sb, tid, user_id)}
        if not set(datauids) <= allowed:
            raise HTTPException(status_code=403, detail="선택할 수 없는 데이터가 포함되어 있습니다.")
    if projectids:
        allowed_p = set(_tenant_project_ids(sb, user_id, tid))
        if not set(projectids) <= allowed_p:
            raise HTTPException(status_code=403, detail="선택할 수 없는 프로젝트가 포함되어 있습니다.")


def _tenant_project_ids(sb, user_id: str, tid: Optional[str]) -> list[int]:
    """사용자가 매니저/뷰어인 프로젝트 중 현재 테넌트(tid) 소속만 필터링."""
    if not tid:
        return []
    proj_rows = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager_viewer", {"p_useruid": user_id})
        .execute().data or []
    )
    ids = [p["projectid"] for p in proj_rows]
    if not ids:
        return []
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("projects")
        .select("projectid")
        .in_("projectid", ids).eq("tenantid", int(tid))
        .execute().data or []
    )
    return [r["projectid"] for r in rows]


def _selectable_projects(sb, user_id: str, tid: Optional[str]) -> list[dict]:
    """데이터셋 그룹에 연결할 수 있는 프로젝트: 현재 테넌트에서 사용자가 접근 가능한 프로젝트 중 Do(문서) 서비스만."""
    project_ids = _tenant_project_ids(sb, user_id, tid)
    if not project_ids:
        return []
    return (
        sb.schema(SUPABASE_SCHEMA).table("projects")
        .select("projectid, projectnm, servicecd")
        .in_("projectid", project_ids)
        .eq("useyn", True).eq("servicecd", "Do")
        .order("projectnm")
        .execute().data or []
    )


def _replace_project_mappings(svc, datasetuid: str, tid: Optional[str], user_id: str, projectids: list[int]) -> None:
    """그룹의 프로젝트 연결을 교체한다. 화면에 노출되지 않는 Do 외 서비스(Ch/In) 프로젝트의
    기존 연결은 건드리지 않고 보존한다(전체 삭제 후 재삽입 시 조용히 사라지는 것 방지)."""
    table = svc.schema(SUPABASE_SCHEMA).table("project_datasets")
    existing = svc.schema(SUPABASE_SCHEMA).table("project_datasets").select("projectid").eq("datasetuid", datasetuid).execute().data or []
    existing_ids = [r["projectid"] for r in existing]
    keep_ids: set = set()
    if existing_ids:
        proj_rows = (
            svc.schema(SUPABASE_SCHEMA).table("projects").select("projectid, servicecd")
            .in_("projectid", existing_ids).execute().data or []
        )
        keep_ids = {r["projectid"] for r in proj_rows if r.get("servicecd") != "Do"}
    delete_ids = [pid for pid in existing_ids if pid not in keep_ids]
    if delete_ids:
        table.delete().eq("datasetuid", datasetuid).in_("projectid", delete_ids).execute()
    new_rows = [
        {"projectid": pid, "datasetuid": datasetuid, "tenantid": tid, "useyn": True, "creator": user_id, "is_directdatauid": False}
        for pid in projectids if pid not in keep_ids
    ]
    if new_rows:
        svc.schema(SUPABASE_SCHEMA).table("project_datasets").insert(new_rows).execute()


def _tenant_datas_candidates(sb, tid: Optional[str], user_id: str) -> list[dict]:
    """데이터셋에 담을 수 있는 후보 데이터 목록.

    db/api(+ 기업 테넌트의 ex)는 프로젝트 연결과 무관하게 테넌트 소속이면 전부 후보이고
    (datas.py list_source_datas와 동일한 기준), 개인/시스템 테넌트의 ex만 프로젝트 기준을 유지한다.
    단, 시스템 테넌트는 여러 개인 계정이 tenantid를 공유하므로 db/api도 creator로 추가 제한한다.
    """
    if not tid:
        return []

    issystemtenant = True
    t_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("issystemtenant").eq("tenantid", int(tid)).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True

    tenant_wide_types = ["db", "api"] if issystemtenant else ["db", "api", "ex"]
    tenant_wide_query = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("datauid, datanm, datasourcecd, projectid")
        .eq("tenantid", tid).in_("datasourcecd", tenant_wide_types)
    )
    if issystemtenant:
        tenant_wide_query = tenant_wide_query.eq("creator", user_id)
    datas = tenant_wide_query.execute().data or []

    if issystemtenant:
        # 개인 테넌트의 ex: 사용자가 접근 가능한 Do 프로젝트의 것만
        do_project_ids = [p["projectid"] for p in _selectable_projects(sb, user_id, tid)]
        if do_project_ids:
            datas += (
                sb.schema(SUPABASE_SCHEMA).table("datas")
                .select("datauid, datanm, datasourcecd, projectid")
                .eq("datasourcecd", "ex").in_("projectid", do_project_ids)
                .execute().data or []
            )
    else:
        # 기업 테넌트의 ex: Do 외 서비스(Ch/In) 프로젝트에 속한 행은 제외 (프로젝트 없는 ex는 유지)
        pids = list({d["projectid"] for d in datas if d.get("projectid")})
        if pids:
            proj_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid, servicecd").in_("projectid", pids).execute().data or []
            non_do = {r["projectid"] for r in proj_rows if r.get("servicecd") != "Do"}
            datas = [d for d in datas if d.get("projectid") not in non_do]

    # datas 뷰는 ex 데이터를 프로젝트별로 한 행씩 돌려주므로 datauid 기준으로 중복 제거
    unique: dict = {}
    for d in datas:
        unique.setdefault(d["datauid"], {"datauid": d["datauid"], "datanm": d["datanm"], "datasourcecd": d["datasourcecd"]})
    result = list(unique.values())
    result.sort(key=lambda r: (r.get("datanm") or "").lower())
    return result


class DatasetSaveRequest(BaseModel):
    datasetuid: Optional[str] = None
    datasetnm: str
    desc: Optional[str] = None
    useyn: bool = True


class MembersSaveRequest(BaseModel):
    datauids: list[str]


class ProjectsSaveRequest(BaseModel):
    projectids: list[int]


class DatasetSaveAllRequest(BaseModel):
    datasetuid: Optional[str] = None
    datasetnm: str
    desc: Optional[str] = None
    useyn: bool = True
    datauids: list[str] = []
    projectids: list[int] = []


# ── Dataset 목록 ───────────────────────────────────────────────────────────────

@router.get("")
def list_datasets(token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    if not tid:
        return {"datasets": []}
    access = _dataset_access(str(user.id), tid)
    q = svc.schema(SUPABASE_SCHEMA).table("datasets").select("*").eq("tenantid", tid)
    if _is_own_scope_only(access):
        q = q.eq("creator", str(user.id))
    rows = q.order("datasetnm").execute().data or []
    return {"datasets": rows}


# ── Dataset 저장 (create / update) ────────────────────────────────────────────

@router.post("")
def save_dataset(body: DatasetSaveRequest, request: Request, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    if body.datasetuid:
        _require_dataset_tenant_manager(str(user.id), body.datasetuid)
    else:
        _dataset_access(str(user.id), tid)
    record = {
        "tenantid":  tid,
        "datasetnm": body.datasetnm,
        "desc":      body.desc,
        "useyn":     body.useyn,
    }
    if body.datasetuid:
        before = snapshot_row(svc, "datasets", "datasetuid", body.datasetuid)
        svc.schema(SUPABASE_SCHEMA).table("datasets").update(record).eq("datasetuid", body.datasetuid).execute()
        after = snapshot_row(svc, "datasets", "datasetuid", body.datasetuid)
        log_work_action(
            useruid=str(user.id), tenantid=int(tid) if tid else None, servicecd="Do",
            actioncd="update", targettype="datasets", targetid=body.datasetuid, before=before, after=after,
            ip=get_client_ip(request),
        )
        return {"datasetuid": body.datasetuid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    resp = svc.schema(SUPABASE_SCHEMA).table("datasets").insert(record).execute()
    log_work_action(
        useruid=str(user.id), tenantid=int(tid) if tid else None, servicecd="Do",
        actioncd="create", targettype="datasets", targetid=resp.data[0]["datasetuid"], after=resp.data[0],
        ip=get_client_ip(request),
    )
    return {"datasetuid": resp.data[0]["datasetuid"], "message": "저장되었습니다."}


# ── Dataset 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{datasetuid}")
def delete_dataset(datasetuid: str, request: Request, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    _require_dataset_tenant_manager(str(user.id), datasetuid)
    before = {
        "datasets": snapshot_row(svc, "datasets", "datasetuid", datasetuid),
        "datasetmembers": svc.schema(SUPABASE_SCHEMA).table("datasetmembers").select("*").eq("datasetuid", datasetuid).execute().data or [],
        "project_datasets": svc.schema(SUPABASE_SCHEMA).table("project_datasets").select("*").eq("datasetuid", datasetuid).execute().data or [],
    }
    svc.schema(SUPABASE_SCHEMA).table("datasetmembers").delete().eq("datasetuid", datasetuid).execute()
    svc.schema(SUPABASE_SCHEMA).table("project_datasets").delete().eq("datasetuid", datasetuid).execute()
    resp = svc.schema(SUPABASE_SCHEMA).table("datasets").delete().eq("datasetuid", datasetuid).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="삭제할 데이터가 없습니다.")
    log_work_action(
        useruid=str(user.id), tenantid=int(tid) if tid else None, servicecd="Do",
        actioncd="delete", targettype="datasets", targetid=datasetuid, before=before,
        ip=get_client_ip(request),
    )
    return {"message": "삭제되었습니다."}


# ── 테넌트 선택 가능 datas 목록 (신규 dataset용) ──────────────────────────────

@router.get("/available-datas")
def list_available_datas(token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    _dataset_access(str(user.id), tid)
    return {"datas": _tenant_datas_candidates(sb, tid, str(user.id))}


# ── 테넌트 프로젝트 목록 (신규 dataset용) ─────────────────────────────────────

@router.get("/available-projects")
def list_available_projects(token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    _dataset_access(str(user.id), tid)
    return {"projects": _selectable_projects(sb, str(user.id), tid)}


# ── Dataset 멤버 (datas) 조회 ─────────────────────────────────────────────────

@router.get("/{datasetuid}/members")
def get_dataset_members(datasetuid: str, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    _require_dataset_tenant_manager(str(user.id), datasetuid)

    datas = _tenant_datas_candidates(sb, tid, str(user.id))

    members = (
        svc.schema(SUPABASE_SCHEMA).table("datasetmembers")
        .select("datauid")
        .eq("datasetuid", datasetuid)
        .execute().data or []
    )
    member_uids = [m["datauid"] for m in members]
    return {"datas": datas, "member_datauids": member_uids}


# ── Dataset 멤버 저장 (전체 교체) ─────────────────────────────────────────────

@router.post("/{datasetuid}/members")
def save_dataset_members(datasetuid: str, body: MembersSaveRequest, request: Request, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    access = _require_dataset_tenant_manager(str(user.id), datasetuid)
    _validate_own_selection(sb, access, str(user.id), body.datauids, [])

    before = svc.schema(SUPABASE_SCHEMA).table("datasetmembers").select("*").eq("datasetuid", datasetuid).execute().data or []
    svc.schema(SUPABASE_SCHEMA).table("datasetmembers").delete().eq("datasetuid", datasetuid).execute()
    if body.datauids:
        svc.schema(SUPABASE_SCHEMA).table("datasetmembers").insert([
            {"datasetuid": datasetuid, "datauid": uid, "tenantid": tid, "useyn": True, "creator": str(user.id)}
            for uid in body.datauids
        ]).execute()
    after = svc.schema(SUPABASE_SCHEMA).table("datasetmembers").select("*").eq("datasetuid", datasetuid).execute().data or []
    log_work_action(
        useruid=str(user.id), tenantid=int(tid) if tid else None, servicecd="Do",
        actioncd="update", targettype="datasets/members", targetid=datasetuid, before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"message": "저장되었습니다."}


# ── Dataset 프로젝트 매핑 조회 ────────────────────────────────────────────────

@router.get("/{datasetuid}/projects")
def get_dataset_projects(datasetuid: str, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    _require_dataset_tenant_manager(str(user.id), datasetuid)

    projects = _selectable_projects(sb, str(user.id), tid)
    mappings = (
        svc.schema(SUPABASE_SCHEMA).table("project_datasets")
        .select("projectid")
        .eq("datasetuid", datasetuid)
        .execute().data or []
    )
    mapped_ids = [m["projectid"] for m in mappings]
    return {"projects": projects, "mapped_projectids": mapped_ids}


# ── Dataset 프로젝트 매핑 저장 (전체 교체) ────────────────────────────────────

@router.post("/{datasetuid}/projects")
def save_dataset_projects(datasetuid: str, body: ProjectsSaveRequest, request: Request, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    access = _require_dataset_tenant_manager(str(user.id), datasetuid)
    _validate_own_selection(sb, access, str(user.id), [], body.projectids)

    before = svc.schema(SUPABASE_SCHEMA).table("project_datasets").select("*").eq("datasetuid", datasetuid).execute().data or []
    _replace_project_mappings(svc, datasetuid, tid, str(user.id), body.projectids)
    after = svc.schema(SUPABASE_SCHEMA).table("project_datasets").select("*").eq("datasetuid", datasetuid).execute().data or []
    log_work_action(
        useruid=str(user.id), tenantid=int(tid) if tid else None, servicecd="Do",
        actioncd="update", targettype="datasets/projects", targetid=datasetuid, before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"message": "저장되었습니다."}


# ── Dataset + 멤버 + 프로젝트 통합 저장 ──────────────────────────────────────

def _snapshot_dataset_all(svc, datasetuid: Optional[str]) -> dict:
    if not datasetuid:
        return {"datasets": None, "datasetmembers": [], "project_datasets": []}
    return {
        "datasets": snapshot_row(svc, "datasets", "datasetuid", datasetuid),
        "datasetmembers": svc.schema(SUPABASE_SCHEMA).table("datasetmembers").select("*").eq("datasetuid", datasetuid).execute().data or [],
        "project_datasets": svc.schema(SUPABASE_SCHEMA).table("project_datasets").select("*").eq("datasetuid", datasetuid).execute().data or [],
    }


@router.post("/save-all")
def save_dataset_all(body: DatasetSaveAllRequest, request: Request, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    svc = get_service_client()
    if body.datasetuid:
        access = _require_dataset_tenant_manager(str(user.id), body.datasetuid)
    else:
        access = _dataset_access(str(user.id), tid)
    _validate_own_selection(sb, access, str(user.id), body.datauids, body.projectids)

    is_new = not body.datasetuid
    before = _snapshot_dataset_all(svc, body.datasetuid)

    # 1. dataset 기본 정보
    record = {"tenantid": tid, "datasetnm": body.datasetnm, "desc": body.desc, "useyn": body.useyn}
    if body.datasetuid:
        svc.schema(SUPABASE_SCHEMA).table("datasets").update(record).eq("datasetuid", body.datasetuid).execute()
        datasetuid = body.datasetuid
    else:
        record["creator"] = str(user.id)
        resp = svc.schema(SUPABASE_SCHEMA).table("datasets").insert(record).execute()
        datasetuid = resp.data[0]["datasetuid"]

    # 2. 멤버 (전체 교체)
    svc.schema(SUPABASE_SCHEMA).table("datasetmembers").delete().eq("datasetuid", datasetuid).execute()
    if body.datauids:
        svc.schema(SUPABASE_SCHEMA).table("datasetmembers").insert([
            {"datasetuid": datasetuid, "datauid": uid, "tenantid": tid, "useyn": True, "creator": str(user.id)}
            for uid in body.datauids
        ]).execute()

    # 3. 프로젝트 매핑 (Do 프로젝트만 교체, Ch/In 기존 연결은 보존)
    _replace_project_mappings(svc, datasetuid, tid, str(user.id), body.projectids)

    after = _snapshot_dataset_all(svc, datasetuid)
    log_work_action(
        useruid=str(user.id), tenantid=int(tid) if tid else None, servicecd="Do",
        actioncd="create" if is_new else "update", targettype="datasets/save-all", targetid=datasetuid,
        before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"datasetuid": datasetuid, "message": "저장되었습니다."}
