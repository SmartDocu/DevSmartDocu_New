from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
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


@router.get("", response_model=DocGroupsListResponse)
def list_docgroups(projectid: int, token: str = Depends(get_token)):
    sb = _sb(token)
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


@router.post("")
def create_docgroup(body: DocGroupSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
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


@router.delete("/{docgroupid}")
def delete_docgroup(docgroupid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    linked = (
        sb.schema(SUPABASE_SCHEMA)
        .table("docs")
        .select("docid")
        .eq("docgroupid", docgroupid)
        .execute()
        .data or []
    )
    if linked:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="msg.docgroup.has.docs")
    sb.schema(SUPABASE_SCHEMA).table("docgroups").delete().eq("docgroupid", docgroupid).execute()
    return {"ok": True}
