import json
from datetime import datetime
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.dependencies import get_token
from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


def _get_user(token: str):
    from backend.app.dependencies import verify_user
    sb = _sb(token)
    return verify_user(sb, token)


class TableSaveRequest(BaseModel):
    objectuid: str
    chapteruid: str
    objectnm: str
    datauid: str
    tablejson: Optional[dict] = None
    coljson: Optional[dict] = None


class TablePreviewRequest(BaseModel):
    selected_datauid: str
    tablejson: Optional[dict] = None
    coljson: Optional[dict] = None


@router.get("")
def get_table(chapteruid: str, objectnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("tables")
        .select("datauid, tablejson, coljson")
        .eq("chapteruid", chapteruid).eq("objectnm", objectnm)
        .execute().data or []
    )
    if not rows:
        return {"table": None}
    row = rows[0]
    try:
        row["tablejson"] = json.loads(row["tablejson"]) if isinstance(row["tablejson"], str) else row["tablejson"] or {}
    except Exception:
        row["tablejson"] = {}
    try:
        row["coljson"] = json.loads(row["coljson"]) if isinstance(row["coljson"], str) else row["coljson"] or {}
    except Exception:
        row["coljson"] = {}
    return {"table": row}


@router.post("")
def save_table(body: TableSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now().isoformat()

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("tables")
        .select("datauid")
        .eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm)
        .execute().data
    )

    tablejson = json.dumps(body.tablejson or {})
    coljson = json.dumps(body.coljson or {})

    if existing:
        sb.schema(SUPABASE_SCHEMA).table("tables").update({
            "objectuid": body.objectuid,
            "datauid": body.datauid,
            "tablejson": tablejson,
            "coljson": coljson,
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
        sb.schema(SUPABASE_SCHEMA).table("objects").update({
            "modifier": user_id, "modifydts": now
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
    else:
        sb.schema(SUPABASE_SCHEMA).table("tables").insert({
            "objectuid": body.objectuid,
            "chapteruid": body.chapteruid,
            "objectnm": body.objectnm,
            "datauid": body.datauid,
            "tablejson": tablejson,
            "coljson": coljson,
            "creator": user_id,
            "gentypecd": "UI",
        }).execute()
        sb.schema(SUPABASE_SCHEMA).table("objects").update({
            "objectsettingyn": True,
            "modifydts": now,
            "modifier": user_id,
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()

    return {"message": "저장되었습니다."}


@router.post("/preview")
def preview_table(body: TablePreviewRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    from utilsPrj.process_data import process_data, apply_column_display_mapping

    class _FakeRequest:
        def __init__(self, access_token):
            self.session = {"access_token": access_token, "refresh_token": None}
            self.method = "GET"

    try:
        req = _FakeRequest(token)
        df = process_data(req, datauid=body.selected_datauid)
        raw_columns = df.columns.tolist()
        raw_rows = df.head(15).values.tolist()
        _, dict_rows = apply_column_display_mapping(body.selected_datauid, raw_columns, raw_rows, sb)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 오류: {e}")

    if not dict_rows:
        return {"preview_html": "<p>데이터가 없습니다.</p>"}

    tablejson = body.tablejson or {}
    coljson = body.coljson or {}
    columns = list(dict_rows[0].keys())

    # 컬럼 순서 + 사용 여부 적용
    ordered = sorted(
        [c for c in columns if coljson.get(c, {}).get("enabled", "y") != "n"],
        key=lambda c: coljson.get(c, {}).get("order", 999),
    ) or columns

    hdr_bg    = tablejson.get("row_bgcolor",    "#ffffff")
    hdr_color = tablejson.get("row_color",      "#000000")
    hdr_align = tablejson.get("row_align",      "center")
    hdr_bold  = tablejson.get("row_fontweight", "bold")
    hdr_size  = tablejson.get("row_fontsize",   14)
    hdr_border= tablejson.get("row_bordercolor","#000000")

    html = (
        '<table border="1" cellpadding="4" cellspacing="0" '
        'style="border-collapse:collapse;width:100%;font-size:12px;">'
        "<thead><tr>"
    )
    for col in ordered:
        s = (f"background:{hdr_bg};color:{hdr_color};text-align:{hdr_align};"
             f"font-weight:{hdr_bold};font-size:{hdr_size}px;"
             f"border-color:{hdr_border};white-space:nowrap;")
        html += f'<th style="{s}">{col}</th>'
    html += "</tr></thead><tbody>"

    for row in dict_rows:
        html += "<tr>"
        for col in ordered:
            cf  = coljson.get(col, {})
            bg  = cf.get("bgcolor",    "#ffffff")
            clr = cf.get("color",      "#000000")
            aln = cf.get("align",      "left")
            fw  = cf.get("fontweight", "normal")
            fs  = cf.get("fontsize",   14)
            val = row.get(col, "")
            if cf.get("unityn") == "y" and val is not None:
                try:
                    val = f"{float(val):,.{int(cf.get('decimal', 0))}f}"
                except Exception:
                    pass
            s = f"background:{bg};color:{clr};text-align:{aln};font-weight:{fw};font-size:{fs}px;"
            html += f'<td style="{s}">{val}</td>'
        html += "</tr>"
    html += "</tbody></table>"
    return {"preview_html": html}


@router.delete("")
def delete_table(chapteruid: str, objectnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    resp = (
        sb.schema(SUPABASE_SCHEMA).table("tables")
        .delete()
        .eq("chapteruid", chapteruid).eq("objectnm", objectnm)
        .execute()
    )
    sb.schema(SUPABASE_SCHEMA).table("objects").update({"objectsettingyn": False}).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
    return {"message": "삭제되었습니다."}
