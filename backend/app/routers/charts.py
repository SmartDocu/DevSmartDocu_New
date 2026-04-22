import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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


class ChartSaveRequest(BaseModel):
    objectuid: str
    chapteruid: str
    objectnm: str
    datauid: str
    displaytype: Optional[str] = None
    chartjson: Optional[dict] = None
    chart_width: Optional[int] = 500
    chart_height: Optional[int] = 250


class ChartPreviewRequest(BaseModel):
    chapteruid: str
    objectnm: str
    selected_datauid: str
    selected_chart_type: str
    docid: Optional[int] = None
    properties: Optional[dict] = None
    chart_width: Optional[int] = 500
    chart_height: Optional[int] = 250


@router.get("/types")
def list_chart_types(token: str = Depends(get_token)):
    _get_user(token)
    from utilsPrj.chart_definitions import get_chart_types_detail
    types_detail = get_chart_types_detail()
    return {"chart_types": [{"code": c["code"], "name": c["name"]} for c in types_detail]}


@router.get("/types/detail")
def list_chart_types_detail(token: str = Depends(get_token)):
    """차트 타입별 설정 필드 목록 (select options 제외)"""
    _get_user(token)
    from utilsPrj.chart_definitions import get_chart_types_detail
    return {"chart_types": get_chart_types_detail()}


@router.get("")
def get_chart(chapteruid: str, objectnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("charts")
        .select("datauid, displaytype, chartjson, chart_width, chart_height")
        .eq("chapteruid", chapteruid).eq("objectnm", objectnm)
        .execute().data or []
    )
    if not rows:
        return {"chart": None}
    row = rows[0]
    try:
        row["chartjson"] = json.loads(row["chartjson"]) if isinstance(row["chartjson"], str) else row["chartjson"] or {}
    except Exception:
        row["chartjson"] = {}
    return {"chart": row}


@router.post("")
def save_chart(body: ChartSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now().isoformat()
    chartjson = json.dumps(body.chartjson or {})

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("charts")
        .select("datauid")
        .eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm)
        .execute().data
    )

    payload = {
        "objectuid": body.objectuid,
        "chapteruid": body.chapteruid,
        "objectnm": body.objectnm,
        "datauid": body.datauid,
        "displaytype": body.displaytype,
        "chartjson": chartjson,
        "creator": user_id,
        "chart_width": body.chart_width,
        "chart_height": body.chart_height,
    }

    if existing:
        sb.schema(SUPABASE_SCHEMA).table("charts").update(payload).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
        sb.schema(SUPABASE_SCHEMA).table("objects").update({"modifier": user_id, "modifydts": now}).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
    else:
        payload["gentypecd"] = "UI"
        sb.schema(SUPABASE_SCHEMA).table("charts").insert(payload).execute()
        sb.schema(SUPABASE_SCHEMA).table("objects").update({
            "objectsettingyn": True, "modifydts": now, "modifier": user_id,
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()

    return {"message": "저장되었습니다."}


@router.delete("")
def delete_chart(chapteruid: str, objectnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("charts").delete().eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
    sb.schema(SUPABASE_SCHEMA).table("objects").update({"objectsettingyn": False}).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
    return {"message": "삭제되었습니다."}


@router.post("/preview")
def preview_chart(body: ChartPreviewRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)

    if not body.selected_datauid or not body.selected_chart_type:
        raise HTTPException(status_code=400, detail="필수 값 누락")

    from utilsPrj.process_data import process_data
    from utilsPrj.process_data import apply_column_display_mapping
    from utilsPrj.chart_utils import draw_chart
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    class _FakeRequest:
        def __init__(self, access_token: str, docid):
            self.session = {"access_token": access_token, "refresh_token": None}
            self.method = "GET"

    try:
        req = _FakeRequest(token, body.docid)
        df = process_data(req, datauid=body.selected_datauid, docid=body.docid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 처리 오류: {e}")

    raw_columns = df.columns.tolist()
    raw_rows = df.values.tolist()
    columns, dict_rows = apply_column_display_mapping(body.selected_datauid, raw_columns, raw_rows, sb)

    props = body.properties or {}
    try:
        fig = draw_chart(req, sb, body.selected_chart_type, dict_rows, props, body.selected_datauid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"차트 생성 오류: {e}")

    dpi = 96
    w = float(body.chart_width or 500)
    h = float(body.chart_height or 250)
    try:
        fig.set_size_inches(w / dpi, h / dpi)
    except Exception:
        fig.set_size_inches(5, 2.5)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
