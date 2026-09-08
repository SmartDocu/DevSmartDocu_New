from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user, require_doc_read, require_doc_write
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()


class DocGroupItem(BaseModel):
    docgroupid: int
    docgroupnm: Optional[str] = None
    docgroupdesc: Optional[str] = None
    projectid: Optional[int] = None


class DocGroupsListResponse(BaseModel):
    docgroups: list[DocGroupItem]


class DocGroupSaveRequest(BaseModel):
    docgroupnm: str
    docgroupdesc: Optional[str] = None
    projectid: int


def _require_project_in_tenant(sb, projectid: int, tenantid: Optional[str]) -> None:
    """projectid가 정말 호출자의 현재 테넌트(tenantid) 소속인지 검증한다.

    과거엔 이 검증이 전혀 없어서(require_doc_read/write는 테넌트 단위 Do 서비스 구독
    여부만 확인하고 projectid 소유권은 안 봄), Do 서비스를 구독 중인 사용자라면 누구나
    다른 조직의 projectid를 넣어 문서 그룹을 조회·생성·삭제할 수 있었다(2026-09-08 발견·수정)."""
    if not tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
    row = sb.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq("projectid", projectid).maybe_single().execute()
    if not row or not row.data or str(row.data.get("tenantid")) != str(tenantid):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")


@router.get("", response_model=DocGroupsListResponse, dependencies=[Depends(require_doc_read)])
def list_docgroups(projectid: int, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    sb = _sb(token)
    _require_project_in_tenant(sb, projectid, tenantid)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("docgroups")
        .select("docgroupid, docgroupnm, docgroupdesc, projectid")
        .eq("projectid", projectid)
        .order("docgroupid")
        .execute()
        .data or []
    )
    return DocGroupsListResponse(docgroups=[DocGroupItem(**r) for r in rows])


@router.post("", dependencies=[Depends(require_doc_write)])
def create_docgroup(body: DocGroupSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    _require_project_in_tenant(sb, body.projectid, tenantid)
    res = (
        sb.schema(SUPABASE_SCHEMA)
        .table("docgroups")
        .insert({
            "docgroupnm": body.docgroupnm,
            "docgroupdesc": body.docgroupdesc,
            "projectid": body.projectid,
            "creator": str(user.id),
        })
        .execute()
    )
    row = res.data[0] if res.data else {}
    return {"ok": True, "docgroup": row}


@router.delete("/{docgroupid}", dependencies=[Depends(require_doc_write)])
def delete_docgroup(docgroupid: int, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    sb = _sb(token)
    dg = sb.schema(SUPABASE_SCHEMA).table("docgroups").select("projectid").eq("docgroupid", docgroupid).maybe_single().execute()
    if not dg or not dg.data:
        raise HTTPException(status_code=404, detail="문서 그룹을 찾을 수 없습니다.")
    _require_project_in_tenant(sb, dg.data["projectid"], tenantid)

    linked = (
        sb.schema(SUPABASE_SCHEMA)
        .table("docs")
        .select("docid")
        .eq("docgroupid", docgroupid)
        .execute()
        .data or []
    )
    if linked:
        raise HTTPException(status_code=400, detail="msg.docgroup.has.docs")
    sb.schema(SUPABASE_SCHEMA).table("docgroups").delete().eq("docgroupid", docgroupid).execute()
    return {"ok": True}
