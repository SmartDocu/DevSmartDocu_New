from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()


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
        .select("datauid, datanm, datasourcecd")
        .eq("tenantid", tid).in_("datasourcecd", tenant_wide_types)
    )
    if issystemtenant:
        tenant_wide_query = tenant_wide_query.eq("creator", user_id)
    datas = tenant_wide_query.execute().data or []

    if issystemtenant:
        project_ids = _tenant_project_ids(sb, user_id, tid)
        if project_ids:
            datas += (
                sb.schema(SUPABASE_SCHEMA).table("datas")
                .select("datauid, datanm, datasourcecd")
                .eq("datasourcecd", "ex").in_("projectid", project_ids)
                .execute().data or []
            )

    datas.sort(key=lambda r: (r.get("datanm") or "").lower())
    return datas


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
    if not tid:
        return {"datasets": []}
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datasets")
        .select("*")
        .eq("tenantid", tid)
        .order("datasetnm")
        .execute().data or []
    )
    return {"datasets": rows}


# ── Dataset 저장 (create / update) ────────────────────────────────────────────

@router.post("")
def save_dataset(body: DatasetSaveRequest, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "tenantid":  tid,
        "datasetnm": body.datasetnm,
        "desc":      body.desc,
        "useyn":     body.useyn,
    }
    if body.datasetuid:
        sb.schema(SUPABASE_SCHEMA).table("datasets").update(record).eq("datasetuid", body.datasetuid).execute()
        return {"datasetuid": body.datasetuid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    resp = sb.schema(SUPABASE_SCHEMA).table("datasets").insert(record).execute()
    return {"datasetuid": resp.data[0]["datasetuid"], "message": "저장되었습니다."}


# ── Dataset 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{datasetuid}")
def delete_dataset(datasetuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("datasetmembers").delete().eq("datasetuid", datasetuid).execute()
    sb.schema(SUPABASE_SCHEMA).table("project_datasets").delete().eq("datasetuid", datasetuid).execute()
    resp = sb.schema(SUPABASE_SCHEMA).table("datasets").delete().eq("datasetuid", datasetuid).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="삭제할 데이터가 없습니다.")
    return {"message": "삭제되었습니다."}


# ── 테넌트 선택 가능 datas 목록 (신규 dataset용) ──────────────────────────────

@router.get("/available-datas")
def list_available_datas(token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    return {"datas": _tenant_datas_candidates(sb, tid, str(user.id))}


# ── 테넌트 프로젝트 목록 (신규 dataset용) ─────────────────────────────────────

@router.get("/available-projects")
def list_available_projects(token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    project_ids = _tenant_project_ids(sb, str(user.id), tid)
    projects = []
    if project_ids:
        projects = (
            sb.schema(SUPABASE_SCHEMA).table("projects")
            .select("projectid, projectnm, servicecd")
            .in_("projectid", project_ids)
            .eq("useyn", True)
            .order("projectnm")
            .execute().data or []
        )
    return {"projects": projects}


# ── Dataset 멤버 (datas) 조회 ─────────────────────────────────────────────────

@router.get("/{datasetuid}/members")
def get_dataset_members(datasetuid: str, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    datas = _tenant_datas_candidates(sb, tid, str(user.id))

    members = (
        sb.schema(SUPABASE_SCHEMA).table("datasetmembers")
        .select("datauid")
        .eq("datasetuid", datasetuid)
        .execute().data or []
    )
    member_uids = [m["datauid"] for m in members]
    return {"datas": datas, "member_datauids": member_uids}


# ── Dataset 멤버 저장 (전체 교체) ─────────────────────────────────────────────

@router.post("/{datasetuid}/members")
def save_dataset_members(datasetuid: str, body: MembersSaveRequest, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)


    sb.schema(SUPABASE_SCHEMA).table("datasetmembers").delete().eq("datasetuid", datasetuid).execute()
    if body.datauids:
        sb.schema(SUPABASE_SCHEMA).table("datasetmembers").insert([
            {"datasetuid": datasetuid, "datauid": uid, "tenantid": tid, "useyn": True, "creator": str(user.id)}
            for uid in body.datauids
        ]).execute()
    return {"message": "저장되었습니다."}


# ── Dataset 프로젝트 매핑 조회 ────────────────────────────────────────────────

@router.get("/{datasetuid}/projects")
def get_dataset_projects(datasetuid: str, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    project_ids = _tenant_project_ids(sb, str(user.id), tid)
    projects = []
    if project_ids:
        projects = (
            sb.schema(SUPABASE_SCHEMA).table("projects")
            .select("projectid, projectnm, servicecd")
            .in_("projectid", project_ids)
            .eq("useyn", True)
            .order("projectnm")
            .execute().data or []
        )
    mappings = (
        sb.schema(SUPABASE_SCHEMA).table("project_datasets")
        .select("projectid")
        .eq("datasetuid", datasetuid)
        .execute().data or []
    )
    mapped_ids = [m["projectid"] for m in mappings]
    return {"projects": projects, "mapped_projectids": mapped_ids}


# ── Dataset 프로젝트 매핑 저장 (전체 교체) ────────────────────────────────────

@router.post("/{datasetuid}/projects")
def save_dataset_projects(datasetuid: str, body: ProjectsSaveRequest, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)


    sb.schema(SUPABASE_SCHEMA).table("project_datasets").delete().eq("datasetuid", datasetuid).execute()
    if body.projectids:
        sb.schema(SUPABASE_SCHEMA).table("project_datasets").insert([
            {"projectid": pid, "datasetuid": datasetuid, "tenantid": tid, "useyn": True, "creator": str(user.id), "is_directdatauid": False}
            for pid in body.projectids
        ]).execute()
    return {"message": "저장되었습니다."}


# ── Dataset + 멤버 + 프로젝트 통합 저장 ──────────────────────────────────────

@router.post("/save-all")
def save_dataset_all(body: DatasetSaveAllRequest, token: str = Depends(get_token), tid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)


    # 1. dataset 기본 정보
    record = {"tenantid": tid, "datasetnm": body.datasetnm, "desc": body.desc, "useyn": body.useyn}
    if body.datasetuid:
        sb.schema(SUPABASE_SCHEMA).table("datasets").update(record).eq("datasetuid", body.datasetuid).execute()
        datasetuid = body.datasetuid
    else:
        record["creator"] = str(user.id)
        resp = sb.schema(SUPABASE_SCHEMA).table("datasets").insert(record).execute()
        datasetuid = resp.data[0]["datasetuid"]

    # 2. 멤버 (전체 교체)
    sb.schema(SUPABASE_SCHEMA).table("datasetmembers").delete().eq("datasetuid", datasetuid).execute()
    if body.datauids:
        sb.schema(SUPABASE_SCHEMA).table("datasetmembers").insert([
            {"datasetuid": datasetuid, "datauid": uid, "tenantid": tid, "useyn": True, "creator": str(user.id)}
            for uid in body.datauids
        ]).execute()

    # 3. 프로젝트 매핑 (전체 교체)
    sb.schema(SUPABASE_SCHEMA).table("project_datasets").delete().eq("datasetuid", datasetuid).execute()
    if body.projectids:
        sb.schema(SUPABASE_SCHEMA).table("project_datasets").insert([
            {"projectid": pid, "datasetuid": datasetuid, "tenantid": tid, "useyn": True, "creator": str(user.id), "is_directdatauid": False}
            for pid in body.projectids
        ]).execute()

    return {"datasetuid": datasetuid, "message": "저장되었습니다."}
