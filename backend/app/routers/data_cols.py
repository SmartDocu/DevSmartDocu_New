from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA
from utilsPrj.data_json_utils import master_data_json_create

router = APIRouter()


class ColAliasItem(BaseModel):
    datauid: str
    querycolnm: str
    aliases: Optional[str] = None


class ColValueSaveRequest(BaseModel):
    datauid: str
    querycolnm: str
    value: str
    logical_name: Optional[str] = None
    aliases: Optional[str] = None
    orderno: Optional[int] = None


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
def list_col_datas(token: str = Depends(get_token)):
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
    proj_rows = (
        sb.schema(SUPABASE_SCHEMA).table("projects")
        .select("projectid, projectnm")
        .in_("projectid", project_ids)
        .execute().data or []
    )
    pmap = {p["projectid"]: p["projectnm"] for p in proj_rows}
    for r in rows:
        r["projectnm"] = pmap.get(r.get("projectid"), "")

    if rows:
        data_uids = [r["datauid"] for r in rows]
        meta_rows = (
            sb.schema(SUPABASE_SCHEMA).table("data_metas")
            .select("datauid")
            .in_("datauid", data_uids)
            .execute().data or []
        )
        meta_uids = {m["datauid"] for m in meta_rows}
        rows = [r for r in rows if r["datauid"] in meta_uids]

    return {"datas": rows}


# ── datacols 목록 ──────────────────────────────────────────────────────────────

@router.get("/datacols")
def list_datacols(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datacols")
        .select("datauid, querycolnm, dispcolnm, aliases, orderno, useyn")
        .eq("datauid", datauid)
        .eq("useyn", True)
        .order("orderno")
        .execute().data or []
    )
    if rows:
        val_rows = (
            sb.schema(SUPABASE_SCHEMA).table("datacolvalues")
            .select("querycolnm")
            .eq("datauid", datauid)
            .execute().data or []
        )
        val_count: dict = {}
        for v in val_rows:
            col = v["querycolnm"]
            val_count[col] = val_count.get(col, 0) + 1
        for r in rows:
            r["value_count"] = val_count.get(r["querycolnm"], 0)
    return {"cols": rows}


# ── datacols aliases 일괄 저장 ─────────────────────────────────────────────────

@router.post("/datacols/aliases")
def save_col_aliases(cols: list[ColAliasItem], token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    for col in cols:
        sb.schema(SUPABASE_SCHEMA).table("datacols").update(
            {"aliases": col.aliases}
        ).eq("datauid", col.datauid).eq("querycolnm", col.querycolnm).execute()
    if cols:
        try:
            master_data_json_create(sb, cols[0].datauid)
        except Exception:
            pass
    return {"message": "저장되었습니다."}


# ── datacolvalues 목록 ─────────────────────────────────────────────────────────

@router.get("/values")
def list_col_values(datauid: str, querycolnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datacolvalues")
        .select("*")
        .eq("datauid", datauid)
        .eq("querycolnm", querycolnm)
        .order("orderno")
        .execute().data or []
    )
    return {"values": rows}


# ── datacolvalues upsert ───────────────────────────────────────────────────────

@router.post("/values")
def save_col_value(body: ColValueSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "datauid":      body.datauid,
        "querycolnm":   body.querycolnm,
        "value":        body.value,
        "logical_name": body.logical_name,
        "aliases":      body.aliases,
        "orderno":      body.orderno,
        "creator":      str(user.id),
    }
    sb.schema(SUPABASE_SCHEMA).table("datacolvalues").upsert(
        record, on_conflict="datauid,querycolnm,value"
    ).execute()
    try:
        master_data_json_create(sb, body.datauid)
    except Exception:
        pass
    return {"message": "저장되었습니다."}


# ── datacolvalues 삭제 ─────────────────────────────────────────────────────────

@router.delete("/values")
def delete_col_value(
    datauid: str,
    querycolnm: str,
    value: str,
    token: str = Depends(get_token),
):
    _get_user(token)
    sb = _sb(token)
    resp = (
        sb.schema(SUPABASE_SCHEMA).table("datacolvalues")
        .delete()
        .eq("datauid", datauid)
        .eq("querycolnm", querycolnm)
        .eq("value", value)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="삭제할 데이터가 없습니다.")
    try:
        master_data_json_create(sb, datauid)
    except Exception:
        pass
    return {"message": "삭제되었습니다."}
