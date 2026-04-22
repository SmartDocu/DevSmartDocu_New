import os
import uuid
from typing import Optional, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from backend.app.schemas.auth import MessageResponse
from utilsPrj.supabase_client import SUPABASE_SCHEMA
from backend.app.schemas.docs import (
    DocItem,
    DocSaveResponse,
    DocSelectRequest,
    DocSelectResponse,
    DocsListResponse,
    ProjectItem,
    ProjectsResponse,
)

router = APIRouter()




# ─── 프로젝트 목록 (문서 생성 폼용) ──────────────────────────────────────────

@router.get("/projects", response_model=ProjectsResponse)
def list_projects(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager", {"p_useruid": str(user.id)})
        .execute()
        .data or []
    )
    # 활성 프로젝트만
    active_ids = {
        p["projectid"]
        for p in (
            sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("useyn", True).execute().data or []
        )
    }
    return ProjectsResponse(
        projects=[
            ProjectItem(projectid=r["projectid"], projectnm=r["projectnm"])
            for r in rows
            if r["projectid"] in active_ids
        ]
    )


# ─── 문서 목록 (문서 선택 모달용) ─────────────────────────────────────────────

@router.get("", response_model=DocsListResponse)
def list_docs(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    # 1. 사용자가 열람 가능한 문서 목록 (Django: fn_docs_filtered__r_user_viewer)
    docs_data = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_docs_filtered__r_user_viewer", {"p_useruid": user_id})
        .execute()
        .data or []
    )

    if not docs_data:
        return DocsListResponse(docs=[])

    docids = [d["docid"] for d in docs_data if d.get("docid")]

    # 2. docs 테이블에서 상세 정보 조회
    docs_details = (
        sb.schema(SUPABASE_SCHEMA)
        .table("docs")
        .select("docid, docdesc, createdts, projectid, sampleyn, basetemplatenm, basetemplateurl, docnm")
        .in_("docid", docids)
        .execute()
        .data or []
    )
    doc_map = {d["docid"]: d for d in docs_details}

    # 3. 프로젝트 정보 조회 (useyn=True만)
    project_ids = list({d.get("projectid") for d in docs_details if d.get("projectid")})
    project_map = {}
    tenant_map = {}
    if project_ids:
        projects_data = (
            sb.schema(SUPABASE_SCHEMA)
            .table("projects")
            .select("projectid, projectnm, tenantid, useyn")
            .in_("projectid", project_ids)
            .eq("useyn", True)
            .execute()
            .data or []
        )
        project_map = {p["projectid"]: p for p in projects_data}

        # 4. 테넌트 정보 조회
        tenant_ids = list({p["tenantid"] for p in projects_data if p.get("tenantid")})
        if tenant_ids:
            tenants_data = (
                sb.schema(SUPABASE_SCHEMA)
                .table("tenants")
                .select("tenantid, tenantnm")
                .in_("tenantid", tenant_ids)
                .execute()
                .data or []
            )
            tenant_map = {t["tenantid"]: t["tenantnm"] for t in tenants_data}

    # 5. 각 문서에 상세 정보 합산
    from datetime import datetime
    result_list = []
    for doc in docs_data:
        docid = doc.get("docid")
        details = doc_map.get(docid, {})
        projectid = details.get("projectid")

        if projectid not in project_map:
            continue

        project = project_map[projectid]
        tenantid = project.get("tenantid")
        sampleyn = details.get("sampleyn", False)

        result_list.append({
            "docid": docid,
            "docnm": details.get("docnm", ""),
            "docdesc": details.get("docdesc", ""),
            "projectid": projectid,
            "projectnm": project.get("projectnm", ""),
            "tenantnm": tenant_map.get(tenantid, ""),
            "basetemplatenm": details.get("basetemplatenm"),
            "basetemplateurl": details.get("basetemplateurl"),
            "sampleyn": sampleyn,
            "createdts": details.get("createdts", ""),
        })

    # 6. 정렬: 샘플 우선, 최신순
    def sort_key(d):
        try:
            ts = datetime.fromisoformat(d["createdts"]).timestamp() if d.get("createdts") else 0
        except Exception:
            ts = 0
        return (0 if d.get("sampleyn") else 1, -ts)

    result_list.sort(key=sort_key)

    return DocsListResponse(
        docs=[
            DocItem(
                docid=d["docid"],
                docnm=d["docnm"],
                docdesc=d.get("docdesc"),
                projectid=d["projectid"],
                projectnm=d.get("projectnm"),
                tenantnm=d.get("tenantnm"),
                basetemplatenm=d.get("basetemplatenm"),
                basetemplateurl=d.get("basetemplateurl"),
                sampleyn=d.get("sampleyn", False),
                editbuttonyn="Y",
            )
            for d in result_list
        ]
    )


# ─── 문서 선택 저장 (Django docs_save에 해당) ─────────────────────────────────

@router.post("/select", response_model=DocSelectResponse)
def select_doc(body: DocSelectRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    docid = body.docid
    docnm = body.docnm

    if not docid:
        raise HTTPException(status_code=400, detail="docid가 필요합니다.")

    # 1. docs 테이블 조회
    docs_rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("*").eq("docid", docid).execute().data
    if not docs_rows:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    projectid = str(docs_rows[0]["projectid"])
    sampleyn = docs_rows[0].get("sampleyn", False)

    # 2. projects 테이블 조회
    projects_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("projectid", projectid).execute().data
    if not projects_rows:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    tenantid = str(projects_rows[0]["tenantid"])

    # 3. projectusers — 프로젝트 매니저 여부
    user_projects = (
        sb.schema(SUPABASE_SCHEMA)
        .table("projectusers")
        .select("*")
        .eq("projectid", projectid)
        .eq("useruid", user_id)
        .execute()
        .data or []
    )
    projectmanager = "Y" if any(p.get("rolecd") == "M" for p in user_projects) else "N"

    # 4. tenantusers — 테넌트 매니저 여부
    user_tenant = (
        sb.schema(SUPABASE_SCHEMA)
        .table("tenantusers")
        .select("*")
        .eq("tenantid", tenantid)
        .eq("useruid", user_id)
        .execute()
        .data or []
    )
    tenantmanager = "Y" if any(t.get("rolecd") == "M" for t in user_tenant) else "N"

    # 5. roleid 조회
    user_row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user_id).maybe_single().execute()
    roleid = user_row.data.get("roleid") if user_row.data else None

    # 6. editbuttonyn / sampledocyn 결정
    if not sampleyn:
        editbuttonyn = "Y"
        sampledocyn = "N"
    elif sampleyn and roleid == 7:
        editbuttonyn = "Y"
        sampledocyn = "Y"
    else:
        editbuttonyn = "N"
        sampledocyn = "Y"

    # 7. users 테이블 mydocid 업데이트
    sb.schema(SUPABASE_SCHEMA).table("users").update({"mydocid": docid}).eq("useruid", user_id).execute()

    return DocSelectResponse(
        docid=docid,
        docnm=docnm,
        projectid=projectid,
        tenantid=tenantid,
        tenantmanager=tenantmanager,
        projectmanager=projectmanager,
        editbuttonyn=editbuttonyn,
        sampledocyn=sampledocyn,
    )


# ─── 문서 저장 (신규/수정) ────────────────────────────────────────────────────

@router.post("", response_model=DocSaveResponse)
async def save_doc(
    projectid: int = Form(...),
    docnm: str = Form(...),
    docdesc: Optional[str] = Form(None),
    docid: Optional[int] = Form(None),
    templatefile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    # 프로젝트 편집 권한 확인
    allowed = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager", {"p_useruid": user_id})
        .execute()
        .data or []
    )
    allowed_ids = [r["projectid"] for r in allowed]
    if projectid not in allowed_ids:
        raise HTTPException(status_code=400, detail="해당 Project는 편집 불가능한 Project 입니다.")

    # 기존 문서 조회
    existing = None
    if docid:
        rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("*").eq("docid", docid).execute().data
        existing = rows[0] if rows else None

    # 중복명 확인
    dup = sb.schema(SUPABASE_SCHEMA).table("docs").select("docid").eq("docnm", docnm).execute().data or []
    dup = [d for d in dup if docid is None or d["docid"] != docid]
    if dup:
        raise HTTPException(status_code=400, detail=f"이미 동일한 이름({docnm})의 문서가 존재합니다.")

    record: dict = {"projectid": projectid, "docnm": docnm, "docdesc": docdesc}

    if templatefile and templatefile.filename:
        # 기존 파일 삭제
        if existing and existing.get("basetemplateurl"):
            _delete_storage_file(sb, existing["basetemplateurl"])

        ext = os.path.splitext(templatefile.filename)[1]
        path = f"template/basetemplate/{uuid.uuid4()}{ext}"
        content = await templatefile.read()
        sb.storage.from_("smartdoc").upload(path, content, {"content-type": templatefile.content_type})
        record["basetemplatenm"] = templatefile.filename
        record["basetemplateurl"] = sb.storage.from_("smartdoc").get_public_url(path).split("?")[0]

    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("docs").update(record).eq("docid", docid).execute()
            return DocSaveResponse(result="success", docid=docid)
        else:
            record["creator"] = user_id
            res = sb.schema(SUPABASE_SCHEMA).table("docs").insert(record).execute()
            new_id = res.data[0]["docid"] if res.data else None
            return DocSaveResponse(result="success", docid=new_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 문서 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{docid}", response_model=MessageResponse)
def delete_doc(docid: int, token: str = Depends(get_token)):
    sb = _sb(token)

    rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("*").eq("docid", docid).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    doc = rows[0]

    if doc.get("basetemplateurl"):
        _delete_storage_file(sb, doc["basetemplateurl"])

    # 연관 gendocs 삭제
    gendocs = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocuid").eq("docid", docid).execute().data or []
    for gd in gendocs:
        sb.schema(SUPABASE_SCHEMA).table("gendocs").delete().eq("gendocuid", gd["gendocuid"]).execute()

    sb.schema(SUPABASE_SCHEMA).table("dataparams").delete().eq("docid", docid).execute()
    res = sb.schema(SUPABASE_SCHEMA).table("docs").delete().eq("docid", docid).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="문서 삭제 실패.")

    return MessageResponse(ok=True, message="문서가 삭제되었습니다.")


# ─── 매개변수(dataparams) CRUD ────────────────────────────────────────────────

class ParamSaveRequest(BaseModel):
    paramuid: Optional[str] = None
    docid: int
    paramnm: str
    orderno: Optional[int] = None
    samplevalue: Optional[str] = None
    operator: Optional[str] = "="
    datasetyn: Optional[str] = "N"
    datauid: Optional[str] = None
    dataset_key: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_order: Optional[str] = None


@router.get("/{docid}/params")
def list_params(docid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("dataparams")
        .select("*").eq("docid", docid).order("orderno")
        .execute().data or []
    )
    return {"params": rows}


@router.post("/params")
def save_param(body: ParamSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)
    payload = {
        "docid": body.docid,
        "paramnm": body.paramnm,
        "orderno": body.orderno,
        "samplevalue": body.samplevalue,
        "operator": body.operator or "=",
        "datasetyn": body.datasetyn or "N",
        "datauid": body.datauid,
        "dataset_key": body.dataset_key,
        "dataset_name": body.dataset_name,
        "dataset_order": body.dataset_order,
    }
    if body.paramuid:
        res = (
            sb.schema(SUPABASE_SCHEMA).table("dataparams")
            .update(payload).eq("paramuid", body.paramuid).execute()
        )
    else:
        res = sb.schema(SUPABASE_SCHEMA).table("dataparams").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="저장 실패")
    return {"ok": True, "param": res.data[0]}


@router.delete("/params/{paramuid}")
def delete_param(paramuid: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("dataparams").delete().eq("paramuid", paramuid).execute()
    return {"ok": True}


# ─── 매개변수 설정(dataparamdtls) ─────────────────────────────────────────────

@router.get("/{docid}/doc-params")
def get_doc_params(docid: int, token: str = Depends(get_token)):
    """문서 매개변수 설정 초기 데이터 (datas, datacols, dataparams, dataparamdtls)"""
    sb = _sb(token)
    from utilsPrj.supabase_client import get_service_client
    sb_svc = get_service_client()

    # 문서 → projectid
    doc_row = sb_svc.schema(SUPABASE_SCHEMA).table("docs").select("docid, docnm, projectid") \
        .eq("docid", docid).execute().data or []
    if not doc_row:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    doc = doc_row[0]
    projectid = doc["projectid"]

    # 프로젝트의 데이터 목록
    datas = sb_svc.schema(SUPABASE_SCHEMA).table("datas").select("datauid, datanm") \
        .eq("projectid", projectid).order("datanm").execute().data or []

    # 모든 datacols (orderno 순)
    all_datacols = sb_svc.schema(SUPABASE_SCHEMA).table("datacols").select(
        "datauid, querycolnm, dispcolnm, orderno"
    ).order("orderno").execute().data or []

    # datauid 기준 그룹핑
    col_map = {}
    for col in all_datacols:
        col_map.setdefault(col["datauid"], []).append(col)

    # 문서 매개변수
    dataparams = sb_svc.schema(SUPABASE_SCHEMA).table("dataparams").select("*") \
        .eq("docid", docid).order("orderno").execute().data or []

    # 기존 매핑 (dataparamdtls)
    dataparamdtls = sb_svc.schema(SUPABASE_SCHEMA).table("dataparamdtls").select("*") \
        .eq("docid", docid).execute().data or []

    # dataparam_map: { datauid: { querycolnm: paramuid } }
    dataparam_map: dict = {}
    for d in dataparamdtls:
        dataparam_map.setdefault(d["datauid"], {})[d["querycolnm"]] = d["paramuid"]

    return {
        "doc": doc,
        "datas": datas,
        "col_map": col_map,
        "dataparams": dataparams,
        "dataparam_map": dataparam_map,
    }


class DocParamSaveRequest(BaseModel):
    records: list[dict]   # [{ datauid, querycolnm, paramuid, docid }]


@router.post("/{docid}/doc-params")
def save_doc_params(docid: int, body: DocParamSaveRequest, token: str = Depends(get_token)):
    """dataparamdtls 저장 (datauid 기준 upsert)"""
    sb = _sb(token)
    user_id = str(_get_user(token).id)

    records = body.records
    if not records:
        raise HTTPException(status_code=400, detail="저장할 데이터가 없습니다.")

    datauids = list({r["datauid"] for r in records})
    sb.schema(SUPABASE_SCHEMA).table("dataparamdtls").delete().in_("datauid", datauids).execute()

    insert_data = [
        {
            "paramuid": r["paramuid"],
            "datauid": r["datauid"],
            "querycolnm": r["querycolnm"],
            "docid": docid,
            "creator": user_id,
        }
        for r in records
    ]
    sb.schema(SUPABASE_SCHEMA).table("dataparamdtls").insert(insert_data).execute()
    return {"ok": True}


class DocParamDeleteRequest(BaseModel):
    datauids: list[str]


@router.delete("/{docid}/doc-params")
def delete_doc_params(docid: int, body: DocParamDeleteRequest, token: str = Depends(get_token)):
    """datauid 목록으로 dataparamdtls 삭제"""
    sb = _sb(token)
    if not body.datauids:
        raise HTTPException(status_code=400, detail="datauids 필요")
    sb.schema(SUPABASE_SCHEMA).table("dataparamdtls").delete().in_("datauid", body.datauids).execute()
    return {"ok": True}


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _delete_storage_file(sb, url: str):
    try:
        parsed = urlparse(url)
        prefix = "/storage/v1/object/public/smartdoc/"
        if prefix in parsed.path:
            path = parsed.path.split(prefix)[-1]
            sb.storage.from_("smartdoc").remove([path])
    except Exception:
        pass
