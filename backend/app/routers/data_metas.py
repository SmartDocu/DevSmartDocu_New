from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA
from utilsPrj.data_json_utils import master_data_json_create

router = APIRouter()


class DataMetaSaveRequest(BaseModel):
    datauid: str
    aliases: Optional[str] = None
    primary_key: Optional[str] = None
    default_time_column: Optional[str] = None
    grain: Optional[str] = None
    purpose: Optional[str] = None
    query_examples: Optional[str] = None
    parent_schema: Optional[str] = None
    parent_table: Optional[str] = None
    parent_column: Optional[str] = None
    child_column: Optional[str] = None


def _user_project_ids(sb, user_id: str) -> list:
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("projectusers")
        .select("projectid")
        .eq("useruid", user_id)
        .eq("useyn", True)
        .execute().data or []
    )
    return list({r["projectid"] for r in rows})


# ── 선택 가능한 datas 목록 (dfv 제외) ─────────────────────────────────────────

@router.get("/datas")
def list_meta_datas(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    project_ids = _user_project_ids(sb, str(user.id))
    if not project_ids:
        return {"datas": []}
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("datauid, datanm, datasourcecd, projectid")
        .in_("projectid", project_ids)
        .neq("datasourcecd", "dfv")
        .order("datanm")
        .execute().data or []
    )
    # projectnm 조회
    proj_rows = (
        sb.schema(SUPABASE_SCHEMA).table("projects")
        .select("projectid, projectnm")
        .in_("projectid", project_ids)
        .execute().data or []
    )
    pmap = {p["projectid"]: p["projectnm"] for p in proj_rows}
    for r in rows:
        r["projectnm"] = pmap.get(r.get("projectid"), "")

    # data_metas 존재 여부
    if rows:
        data_uids = [r["datauid"] for r in rows]
        meta_rows = (
            sb.schema(SUPABASE_SCHEMA).table("data_metas")
            .select("datauid")
            .in_("datauid", data_uids)
            .execute().data or []
        )
        meta_uids = {m["datauid"] for m in meta_rows}
        for r in rows:
            r["settingyn"] = r["datauid"] in meta_uids

    return {"datas": rows}


# ── 단건 조회 ──────────────────────────────────────────────────────────────────

@router.get("/{datauid}")
def get_data_meta(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("data_metas")
        .select("*")
        .eq("datauid", datauid)
        .execute().data or []
    )
    return {"meta": rows[0] if rows else None}


# ── Upsert ─────────────────────────────────────────────────────────────────────

@router.post("")
def save_data_meta(body: DataMetaSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "datauid":             body.datauid,
        "aliases":             body.aliases,
        "primary_key":         body.primary_key,
        "default_time_column": body.default_time_column,
        "grain":               body.grain,
        "purpose":             body.purpose,
        "query_examples":      body.query_examples,
        "parent_schema":       body.parent_schema,
        "parent_table":        body.parent_table,
        "parent_column":       body.parent_column,
        "child_column":        body.child_column,
        "creator":             str(user.id),
    }
    sb.schema(SUPABASE_SCHEMA).table("data_metas").upsert(record, on_conflict="datauid").execute()
    try:
        master_data_json_create(sb, body.datauid)
    except Exception:
        pass
    return {"message": "저장되었습니다."}


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/{datauid}")
def delete_data_meta(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    resp = (
        sb.schema(SUPABASE_SCHEMA).table("data_metas")
        .delete()
        .eq("datauid", datauid)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="삭제할 데이터가 없습니다.")
    return {"message": "삭제되었습니다."}
