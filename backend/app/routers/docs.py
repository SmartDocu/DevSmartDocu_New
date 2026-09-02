import os
import uuid
from datetime import timedelta, timezone
from typing import Optional, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user, require_doc_read, require_doc_write
from backend.app.schemas.auth import MessageResponse
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client
from utilsPrj.audit_log import log_work_action, snapshot_row, get_client_ip
from utilsPrj.private_storage import (
    resolve_user_accountuid, build_private_path, upload_private_file,
    delete_private_file, is_private_path, resolve_display_url,
)
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


def _get_offsetminutes(sb, user_id: str, tenantid: Optional[str] = None) -> Optional[int]:
    """tenantid를 주면 그 테넌트 기준으로, 없으면(다중 테넌트일 때 모호해질 수 있어) 활성(useyn=True) 소속 행을 사용."""
    try:
        q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id)
        if tenantid:
            q = q.eq("tenantid", int(tenantid))
        else:
            q = q.eq("useyn", True)
        rows = q.limit(1).execute().data or []
        if not rows:
            return None
        tu_data = rows[0]
        tz = tu_data.get("timezone")
        if not tz and tu_data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu_data["tenantid"]).maybe_single().execute()
            if t and t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None
    except Exception:
        return None


def _fmt_dt(raw, offsetminutes: Optional[int] = None) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


# ─── 프로젝트 목록 (문서 생성 폼용) ──────────────────────────────────────────

@router.get("/projects", response_model=ProjectsResponse, dependencies=[Depends(require_doc_read)])
def list_projects(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager", {"p_useruid": str(user.id)})
        .execute()
        .data or []
    )
    # 활성 프로젝트 + 현재 테넌트 소속만. projectnm은 RPC가 붙이는 "(테넌트명)" 구분 표기 없이
    # projects 테이블 원본 값을 그대로 사용한다(이미 테넌트로 필터링돼 있어 구분 표기가 불필요).
    rpc_ids = {r["projectid"] for r in rows}
    q = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid, projectnm, servicecd").eq("useyn", True).eq("servicecd", "Do")
    if tenantid:
        q = q.eq("tenantid", int(tenantid))
    active_rows = [p for p in (q.execute().data or []) if p["projectid"] in rpc_ids]
    return ProjectsResponse(
        projects=[
            ProjectItem(projectid=p["projectid"], projectnm=p["projectnm"], servicecd=p["servicecd"])
            for p in active_rows
        ]
    )


# ─── 문서 목록 (문서 선택 모달용) ─────────────────────────────────────────────

@router.get("", response_model=DocsListResponse, dependencies=[Depends(require_doc_read)])
def list_docs(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    offsetminutes = _get_offsetminutes(sb, user_id, tenantid)

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
        .select("docid, docdesc, createdts, projectid, basetemplatenm, basetemplateurl, docnm, docgroupid")
        .in_("docid", docids)
        .execute()
        .data or []
    )
    doc_map = {d["docid"]: d for d in docs_details}

    # 2-1. docgroup 이름 조회
    docgroup_ids = list({d["docgroupid"] for d in docs_details if d.get("docgroupid")})
    docgroup_map: dict = {}
    if docgroup_ids:
        dg_rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("docgroups")
            .select("docgroupid, docgroupnm")
            .in_("docgroupid", docgroup_ids)
            .execute()
            .data or []
        )
        docgroup_map = {r["docgroupid"]: r["docgroupnm"] for r in dg_rows}

    # 3. 프로젝트 정보 조회 (useyn=True만)
    project_ids = list({d.get("projectid") for d in docs_details if d.get("projectid")})
    project_map = {}
    tenant_map = {}
    manager_project_ids: set = set()
    manager_tenant_ids: set = set()
    if project_ids:
        q = (
            sb.schema(SUPABASE_SCHEMA)
            .table("projects")
            .select("projectid, projectnm, tenantid, useyn")
            .in_("projectid", project_ids)
            .eq("useyn", True)
        )
        if tenantid:
            q = q.eq("tenantid", tenantid)
        projects_data = q.execute().data or []
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

        # 5. 편집 권한 조회
        pu_rows = (
            sb.schema(SUPABASE_SCHEMA).table("projectusers")
            .select("projectid").in_("projectid", project_ids)
            .eq("useruid", user_id).eq("rolecd", "M")
            .execute().data or []
        )
        manager_project_ids = {r["projectid"] for r in pu_rows}

        tu_rows = (
            sb.schema(SUPABASE_SCHEMA).table("tenantusers")
            .select("tenantid").in_("tenantid", tenant_ids)
            .eq("useruid", user_id).eq("rolecd", "M")
            .execute().data or []
        ) if tenant_ids else []
        manager_tenant_ids = {r["tenantid"] for r in tu_rows}

    # 5. 각 문서에 상세 정보 합산
    from datetime import datetime

    from utilsPrj.service_status import get_service_permission
    tenant_write_ok: dict = {}

    result_list = []
    for doc in docs_data:
        docid = doc.get("docid")
        details = doc_map.get(docid, {})
        projectid = details.get("projectid")

        if projectid not in project_map:
            continue

        project = project_map[projectid]
        tenantid = project.get("tenantid")
        is_manager = (projectid in manager_project_ids) or (tenantid in manager_tenant_ids)

        if tenantid not in tenant_write_ok:
            try:
                tenant_write_ok[tenantid] = get_service_permission(sb, tenantid, user_id, "Do")["can_write"]
            except Exception:
                tenant_write_ok[tenantid] = True

        editbuttonyn = "Y" if (is_manager and tenant_write_ok[tenantid]) else "N"

        dgid = details.get("docgroupid")
        basetemplateurl = resolve_display_url(get_service_client(), details.get("basetemplateurl"))
        result_list.append({
            "docid": docid,
            "docnm": details.get("docnm", ""),
            "docdesc": details.get("docdesc", ""),
            "projectid": projectid,
            "projectnm": project.get("projectnm", ""),
            "tenantnm": tenant_map.get(tenantid, ""),
            "basetemplatenm": details.get("basetemplatenm"),
            "basetemplateurl": basetemplateurl,
            "createdts": _fmt_dt(details.get("createdts"), offsetminutes),
            "editbuttonyn": editbuttonyn,
            "docgroupid": dgid,
            "docgroupnm": docgroup_map.get(dgid) if dgid else None,
        })

    # 6. 정렬: 샘플 우선, 최신순
    def sort_key(d):
        try:
            ts = datetime.fromisoformat(d["createdts"]).timestamp() if d.get("createdts") else 0
        except Exception:
            ts = 0
        return -ts

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
                editbuttonyn=d.get("editbuttonyn", "N"),
                docgroupid=d.get("docgroupid"),
                docgroupnm=d.get("docgroupnm"),
            )
            for d in result_list
        ]
    )


# ─── 문서 선택 저장 (Django docs_save에 해당) ─────────────────────────────────

@router.post("/select", response_model=DocSelectResponse, dependencies=[Depends(require_doc_write)])
def select_doc(body: DocSelectRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    docid = body.docid
    docnm = body.docnm

    if not docid:
        raise HTTPException(status_code=400, detail="msg.required.docid")

    # 1. docs 테이블 조회
    docs_rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("*").eq("docid", docid).execute().data
    if not docs_rows:
        raise HTTPException(status_code=404, detail="msg.doc.not.found")

    projectid = str(docs_rows[0]["projectid"])

    # 2. projects 테이블 조회
    projects_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("*").eq("projectid", projectid).execute().data
    if not projects_rows:
        raise HTTPException(status_code=404, detail="msg.project.not.found")
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

    # 6. editbuttonyn 결정 — servicestatus(Do 서비스) write 권한도 함께 확인
    try:
        from utilsPrj.service_status import get_service_permission
        can_write_service = get_service_permission(sb, tenantid, user_id, "Do")["can_write"]
    except Exception:
        can_write_service = True
    editbuttonyn = "Y" if ((projectmanager == "Y" or tenantmanager == "Y") and can_write_service) else "N"

    # 7. users 테이블 mydocid 업데이트 (D2DOC 서비스 행만)
    # serviceusers는 (useruid, servicecd) 조합이 테넌트별로 행이 나뉘므로 tenantid로 반드시 제한
    # (안 그러면 다른 테넌트의 "마지막 선택 문서" 행까지 이 docid로 덮어써버림)
    sb.schema(SUPABASE_SCHEMA).table("serviceusers").update({"mydocid": docid}) \
        .eq("useruid", user_id).eq("servicecd", "Do").eq("tenantid", int(tenantid)).execute()

    return DocSelectResponse(
        docid=docid,
        docnm=docnm,
        projectid=projectid,
        tenantid=tenantid,
        tenantmanager=tenantmanager,
        projectmanager=projectmanager,
        editbuttonyn=editbuttonyn,
    )


# ─── 문서 저장 (신규/수정) ────────────────────────────────────────────────────

@router.post("", response_model=DocSaveResponse, dependencies=[Depends(require_doc_write)])
async def save_doc(
    request: Request,
    projectid: int = Form(...),
    docnm: str = Form(...),
    docdesc: Optional[str] = Form(None),
    docid: Optional[int] = Form(None),
    docgroupid: Optional[int] = Form(None),
    templatefile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
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
        raise HTTPException(status_code=400, detail="msg.doc.no.permission")

    # 기존 문서 조회
    existing = None
    if docid:
        rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("*").eq("docid", docid).execute().data
        existing = rows[0] if rows else None

    # 중복명 확인
    dup = sb.schema(SUPABASE_SCHEMA).table("docs").select("docid").eq("docnm", docnm).execute().data or []
    dup = [d for d in dup if docid is None or d["docid"] != docid]
    if dup:
        raise HTTPException(status_code=400, detail="msg.doc.name.duplicate")

    record: dict = {"projectid": projectid, "docnm": docnm, "docdesc": docdesc, "docgroupid": docgroupid}

    # 템플릿 파일은 private 버킷(d2doc-private, Users/{accountuid}/Doc/{docid}/source/...)에 저장한다.
    # 신규 문서는 docid가 INSERT 이후에야 확정되므로, 파일 내용만 먼저 읽어두고
    # 실제 업로드는 docid가 정해진 뒤(update 시점 or insert 직후)에 수행한다.
    template_content: Optional[bytes] = None
    template_ext = ""
    if templatefile and templatefile.filename:
        template_ext = os.path.splitext(templatefile.filename)[1]
        template_content = await templatefile.read()

    def _upload_template(target_docid: int, old_url: Optional[str]) -> str:
        accountuid = resolve_user_accountuid(get_service_client(), int(tenantid), user_id) if tenantid else None
        if not accountuid:
            raise HTTPException(status_code=400, detail="msg.required.tenantid")
        if old_url:
            _delete_storage_file(sb, old_url, expected_accountuid=accountuid)
        path = build_private_path(accountuid, "Doc", str(target_docid), "source", f"{uuid.uuid4()}{template_ext}")
        upload_private_file(get_service_client(), path, template_content, templatefile.content_type)
        return path

    try:
        if existing:
            if template_content is not None:
                record["basetemplatenm"] = templatefile.filename
                record["basetemplateurl"] = _upload_template(docid, existing.get("basetemplateurl"))

            sb.schema(SUPABASE_SCHEMA).table("docs").update(record).eq("docid", docid).execute()
            after = snapshot_row(sb, "docs", "docid", docid)
            log_work_action(
                useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Do",
                actioncd="update", targettype="docs", targetid=docid, before=existing, after=after,
                ip=get_client_ip(request),
            )
            return DocSaveResponse(result="success", docid=docid)
        else:
            record["creator"] = user_id
            res = sb.schema(SUPABASE_SCHEMA).table("docs").insert(record).execute()
            new_id = res.data[0]["docid"] if res.data else None

            if template_content is not None and new_id:
                sb.schema(SUPABASE_SCHEMA).table("docs").update({
                    "basetemplatenm": templatefile.filename,
                    "basetemplateurl": _upload_template(new_id, None),
                }).eq("docid", new_id).execute()

            after = snapshot_row(sb, "docs", "docid", new_id) if new_id else (res.data[0] if res.data else None)
            log_work_action(
                useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Do",
                actioncd="create", targettype="docs", targetid=new_id, after=after,
                ip=get_client_ip(request),
            )
            return DocSaveResponse(result="success", docid=new_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="msg.save.error")


# ─── 문서 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{docid}", response_model=MessageResponse, dependencies=[Depends(require_doc_write)])
def delete_doc(docid: int, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("*").eq("docid", docid).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="msg.doc.not.found")
    doc = rows[0]

    # 프로젝트 편집 권한 확인 (save_doc과 동일 — docid만으로 다른 프로젝트 문서를 삭제할 수 없게)
    allowed = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager", {"p_useruid": user_id})
        .execute()
        .data or []
    )
    allowed_ids = [r["projectid"] for r in allowed]
    if doc.get("projectid") not in allowed_ids:
        raise HTTPException(status_code=400, detail="msg.doc.no.permission")

    if doc.get("basetemplateurl"):
        accountuid = resolve_user_accountuid(get_service_client(), int(tenantid), user_id) if tenantid else None
        _delete_storage_file(sb, doc["basetemplateurl"], expected_accountuid=accountuid)

    # 연관 gendocs 삭제
    gendocs = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocuid").eq("docid", docid).execute().data or []
    for gd in gendocs:
        sb.schema(SUPABASE_SCHEMA).table("gendocs").delete().eq("gendocuid", gd["gendocuid"]).execute()

    docparams = sb.schema(SUPABASE_SCHEMA).table("docparams").select("*").eq("docid", docid).execute().data or []
    sb.schema(SUPABASE_SCHEMA).table("docparams").delete().eq("docid", docid).execute()
    res = sb.schema(SUPABASE_SCHEMA).table("docs").delete().eq("docid", docid).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="msg.delete.error")

    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Do",
        actioncd="delete", targettype="docs", targetid=docid,
        before={"docs": doc, "docparams": docparams, "gendocs": gendocs},
        ip=get_client_ip(request),
    )

    return MessageResponse(ok=True, message="msg.delete.success")


# ─── 매개변수(docparams) CRUD ────────────────────────────────────────────────

class ParamSaveRequest(BaseModel):
    paramuid: Optional[str] = None
    docid: int
    paramnm: str
    orderno: Optional[int] = None
    samplevalue: Optional[str] = None
    operator: Optional[str] = "="
    datauid: Optional[str] = None
    keycolnm: Optional[str] = None
    keycoldatatypecd: Optional[str] = None
    nmcolnm: Optional[str] = None
    ordercolnm: Optional[str] = None


@router.get("/{docid}/params", dependencies=[Depends(require_doc_read)])
def list_params(docid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("docparams")
        .select("*").eq("docid", docid).order("orderno")
        .execute().data or []
    )
    data_ids = list({r["datauid"] for r in rows if r.get("datauid")})
    if data_ids:
        datas = (
            sb.schema(SUPABASE_SCHEMA).table("datas")
            .select("datauid, datanm").in_("datauid", data_ids).execute().data or []
        )
        nm_map = {d["datauid"]: d["datanm"] for d in datas}
        for r in rows:
            r["datanm"] = nm_map.get(r.get("datauid"), "")
    return {"params": rows}


@router.post("/params", dependencies=[Depends(require_doc_write)])
def save_param(body: ParamSaveRequest, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    payload = {
        "docid": body.docid,
        "paramnm": body.paramnm,
        "orderno": body.orderno,
        "samplevalue": body.samplevalue,
        "operator": body.operator or "=",
        "datauid": body.datauid,
        "keycolnm": body.keycolnm,
        "keycoldatatypecd": body.keycoldatatypecd,
        "nmcolnm": body.nmcolnm,
        "ordercolnm": body.ordercolnm,
    }
    if body.paramuid:
        before = snapshot_row(sb, "docparams", "paramuid", body.paramuid)
        res = (
            sb.schema(SUPABASE_SCHEMA).table("docparams")
            .update(payload).eq("paramuid", body.paramuid).execute()
        )
        actioncd = "update"
    else:
        before = None
        payload["creator"] = str(user.id)
        res = sb.schema(SUPABASE_SCHEMA).table("docparams").insert(payload).execute()
        actioncd = "create"
    if not res.data:
        raise HTTPException(status_code=500, detail="msg.save.error")
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Do",
        actioncd=actioncd, targettype="docs/params", targetid=res.data[0].get("paramuid"),
        before=before, after=res.data[0],
        ip=get_client_ip(request),
    )
    return {"ok": True, "param": res.data[0]}


@router.delete("/params/{paramuid}", dependencies=[Depends(require_doc_write)])
def delete_param(paramuid: str, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    before = snapshot_row(sb, "docparams", "paramuid", paramuid)
    sb.schema(SUPABASE_SCHEMA).table("docparams").delete().eq("paramuid", paramuid).execute()
    log_work_action(
        useruid=str(user.id), tenantid=int(tenantid) if tenantid else None, servicecd="Do",
        actioncd="delete", targettype="docs/params", targetid=paramuid, before=before,
        ip=get_client_ip(request),
    )
    return {"ok": True}


@router.get("/{docid}/condition-datas", dependencies=[Depends(require_doc_read)])
def list_condition_datas(docid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    doc = (
        sb.schema(SUPABASE_SCHEMA).table("docs")
        .select("projectid").eq("docid", docid).execute().data or []
    )
    if not doc:
        raise HTTPException(status_code=404, detail="msg.doc.not.found")
    projectid = doc[0]["projectid"]

    datas = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("datauid, datanm, datasourcecd")
        .eq("projectid", projectid).not_.in_("datasourcecd", ["df", "dfv"])
        .order("datanm").execute().data or []
    )

    data_ids = [d["datauid"] for d in datas]
    col_map: dict = {}
    if data_ids:
        cols = (
            sb.schema(SUPABASE_SCHEMA).table("datacols")
            .select("datauid, querycolnm, dispcolnm, datatypecd")
            .in_("datauid", data_ids).order("orderno").execute().data or []
        )
        for c in cols:
            col_map.setdefault(c["datauid"], []).append(c)

    return {"datas": datas, "col_map": col_map}


# ─── 매개변수 설정(docparamdtls) ─────────────────────────────────────────────

@router.get("/{docid}/doc-params", dependencies=[Depends(require_doc_read)])
def get_doc_params(docid: int, token: str = Depends(get_token)):
    """문서 데이터셋 관리 초기 데이터 (datas, datacols, docparams, doc_datas, docparamdtls)"""
    from utilsPrj.supabase_client import get_service_client
    sb_svc = get_service_client()

    # 문서 → projectid
    doc_row = sb_svc.schema(SUPABASE_SCHEMA).table("docs").select("docid, docnm, projectid") \
        .eq("docid", docid).execute().data or []
    if not doc_row:
        raise HTTPException(status_code=404, detail="msg.doc.not.found")
    projectid = doc_row[0]["projectid"]

    # 프로젝트의 데이터 목록 (db/ex)
    base_datas = sb_svc.schema(SUPABASE_SCHEMA).table("datas") \
        .select("datauid, datanm, datasourcecd") \
        .eq("projectid", projectid).in_("datasourcecd", ["db", "ex", "api"]) \
        .order("datanm").execute().data or []

    # doc_datas에 이미 등록된 df도 후보에 포함 (문서 전환 시 기존 선택 유지용)
    doc_data_uids = [d["datauid"] for d in sb_svc.schema(SUPABASE_SCHEMA).table("doc_datas") \
        .select("datauid").eq("docid", docid).eq("useyn", True).execute().data or []]
    df_datas = []
    if doc_data_uids:
        df_datas = sb_svc.schema(SUPABASE_SCHEMA).table("datas") \
            .select("datauid, datanm, datasourcecd") \
            .eq("datasourcecd", "df") \
            .in_("datauid", doc_data_uids) \
            .order("datanm").execute().data or []

    # 데이터 그룹(project_datasets) 매핑: is_directdatauid=true면 datauid 직접, false면 datasetmembers 경유
    pd_rows = sb_svc.schema(SUPABASE_SCHEMA).table("project_datasets") \
        .select("datasetuid, is_directdatauid").eq("projectid", projectid).execute().data or []
    pd_uids = {r["datasetuid"] for r in pd_rows if r.get("is_directdatauid")}
    group_ids = [r["datasetuid"] for r in pd_rows if not r.get("is_directdatauid")]
    if group_ids:
        member_rows = sb_svc.schema(SUPABASE_SCHEMA).table("datasetmembers") \
            .select("datauid").in_("datasetuid", group_ids).execute().data or []
        pd_uids |= {r["datauid"] for r in member_rows}
    pd_datas = []
    if pd_uids:
        pd_datas = sb_svc.schema(SUPABASE_SCHEMA).table("dataunits") \
            .select("datauid, datanm, datasourcecd").in_("datauid", list(pd_uids)) \
            .order("datanm").execute().data or []

    datas_by_uid = {d["datauid"]: d for d in base_datas + df_datas + pd_datas}
    datas = sorted(datas_by_uid.values(), key=lambda d: d["datanm"])

    # 해당 데이터들의 datacols (orderno 순)
    data_uids = [d["datauid"] for d in datas]
    col_map: dict = {}
    if data_uids:
        all_datacols = sb_svc.schema(SUPABASE_SCHEMA).table("datacols") \
            .select("datauid, querycolnm, dispcolnm, orderno") \
            .in_("datauid", data_uids).order("orderno").execute().data or []
        for col in all_datacols:
            col_map.setdefault(col["datauid"], []).append(col)

    # 문서 매개변수
    docparams = sb_svc.schema(SUPABASE_SCHEMA).table("docparams").select("*") \
        .eq("docid", docid).order("orderno").execute().data or []

    # 선택된 데이터 목록 (doc_datas)
    doc_datas = sb_svc.schema(SUPABASE_SCHEMA).table("doc_datas") \
        .select("datauid").eq("docid", docid).eq("useyn", True).execute().data or []
    selected_datauids = [d["datauid"] for d in doc_datas]

    # 기존 매핑: { datauid: { paramuid: querycolnm } }
    docparamdtls = sb_svc.schema(SUPABASE_SCHEMA).table("docparamdtls").select("*") \
        .eq("docid", docid).execute().data or []
    dataparam_map: dict = {}
    for d in docparamdtls:
        if not d.get("paramnm"):
            dataparam_map.setdefault(d["datauid"], {})[d["paramuid"]] = d["querycolnm"]

    # API non-fixed params: { datauid: [paramnm, ...] }
    api_datauids = [d["datauid"] for d in datas if d["datasourcecd"] == "api"]
    api_params_map: dict = {}
    if api_datauids:
        api_param_rows_all = sb_svc.schema(SUPABASE_SCHEMA).table("data_api_params") \
            .select("datauid, paramnm, is_fixed, orderno") \
            .in_("datauid", api_datauids) \
            .order("orderno").execute().data or []
        for p in api_param_rows_all:
            if not p.get("is_fixed"):
                api_params_map.setdefault(p["datauid"], []).append(p["paramnm"])

    # API param 기존 매핑: { datauid: { paramnm: paramuid } }
    apiparam_map: dict = {}
    for d in docparamdtls:
        if d.get("paramnm"):
            apiparam_map.setdefault(d["datauid"], {})[d["paramnm"]] = d["paramuid"]

    return {
        "datas": datas,
        "col_map": col_map,
        "dataparams": docparams,
        "selected_datauids": selected_datauids,
        "dataparam_map": dataparam_map,
        "api_params_map": api_params_map,
        "apiparam_map": apiparam_map,
    }


class DocParamSaveRequest(BaseModel):
    selected_datauids: list[str]
    records: list[dict]   # [{ datauid, paramuid, querycolnm }]


@router.post("/{docid}/doc-params", dependencies=[Depends(require_doc_write)])
def save_doc_params(docid: int, body: DocParamSaveRequest, request: Request, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """doc_datas 선택 및 docparamdtls 매핑 저장"""
    sb = _sb(token)
    user_id = str(_get_user(token).id)

    before = {
        "doc_datas": sb.schema(SUPABASE_SCHEMA).table("doc_datas").select("*").eq("docid", docid).execute().data or [],
        "docparamdtls": sb.schema(SUPABASE_SCHEMA).table("docparamdtls").select("*").eq("docid", docid).execute().data or [],
    }

    # doc_datas: 전체 교체
    sb.schema(SUPABASE_SCHEMA).table("doc_datas").delete().eq("docid", docid).execute()
    if body.selected_datauids:
        sb.schema(SUPABASE_SCHEMA).table("doc_datas").insert([
            {"docid": docid, "datauid": uid, "useyn": True, "creator": user_id}
            for uid in body.selected_datauids
        ]).execute()

    # docparamdtls: 전체 교체
    sb.schema(SUPABASE_SCHEMA).table("docparamdtls").delete().eq("docid", docid).execute()
    if body.records:
        sb.schema(SUPABASE_SCHEMA).table("docparamdtls").insert([
            {
                "paramuid": r["paramuid"],
                "datauid": r["datauid"],
                "querycolnm": r.get("querycolnm"),
                "paramnm": r.get("paramnm"),
                "docid": docid,
                "creator": user_id,
            }
            for r in body.records
        ]).execute()

    after = {
        "doc_datas": sb.schema(SUPABASE_SCHEMA).table("doc_datas").select("*").eq("docid", docid).execute().data or [],
        "docparamdtls": sb.schema(SUPABASE_SCHEMA).table("docparamdtls").select("*").eq("docid", docid).execute().data or [],
    }
    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Do",
        actioncd="update", targettype="docs/doc-params", targetid=docid, before=before, after=after,
        ip=get_client_ip(request),
    )
    return {"ok": True}


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _delete_storage_file(sb, url: str, expected_accountuid: Optional[str] = None):
    if is_private_path(url):
        delete_private_file(get_service_client(), url, expected_accountuid=expected_accountuid)
        return
    try:
        parsed = urlparse(url)
        prefix = "/storage/v1/object/public/d2doc/"
        if prefix in parsed.path:
            path = parsed.path.split(prefix)[-1]
            sb.storage.from_("d2doc").remove([path])
    except Exception:
        pass
