import os
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from backend.app.schemas.datas import (
    AiDataSaveRequest, DataColItem, DataColsResponse,
    DbConnectorsResponse, DbDataSaveRequest, DatasListResponse,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()


def _active_projects(sb, user_id: str):
    proj_list = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager_viewer", {"p_useruid": user_id})
        .execute().data or []
    )
    ids = [p["projectid"] for p in proj_list]
    if not ids:
        return [], {}
    active = (
        sb.schema(SUPABASE_SCHEMA).table("projects")
        .select("projectid, projectnm")
        .in_("projectid", ids).eq("useyn", True)
        .execute().data or []
    )
    pmap = {p["projectid"]: p["projectnm"] for p in active}
    return [p["projectid"] for p in active], pmap


def _delete_storage(sb, url: str):
    if not url:
        return
    parsed = urlparse(url)
    prefix = "/storage/v1/object/public/smartdoc/"
    if prefix in parsed.path:
        path = parsed.path.split(prefix)[-1]
        try:
            sb.storage.from_("smartdoc").remove([path])
        except Exception:
            pass


# ── DB Connectors ──────────────────────────────────────────────────────────────

@router.get("/dbconnectors", response_model=DbConnectorsResponse)
def list_dbconnectors(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    row = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("tenantid").eq("useruid", str(user.id)).execute().data
    tenantid = row[0]["tenantid"] if row else None
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("dbconnectors")
        .select("connectid, connectnm")
        .eq("useyn", True).eq("tenantid", tenantid)
        .execute().data or []
    )
    return {"connectors": rows}


# ── Datas List ──────────────────────────────────────────────────────────────────

@router.get("")
def list_datas(
    datasourcecd: Optional[str] = None,
    chapteruid: Optional[str] = None,
    token: str = Depends(get_token),
):
    import sys
    user = _get_user(token)
    sb = _sb(token)

    # chapteruid가 있으면 해당 챕터의 projectid로 직접 필터 (llm/init 방식과 동일)
    single_pid = None
    project_ids: list = []
    pmap: dict = {}
    if chapteruid:
        try:
            ch = sb.schema(SUPABASE_SCHEMA).table("chapters").select("docid").eq("chapteruid", chapteruid).execute().data or []
            if ch:
                docs = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid, docnm").eq("docid", ch[0]["docid"]).execute().data or []
                if docs:
                    single_pid = docs[0]["projectid"]
                    pmap = {single_pid: docs[0].get("docnm", "")}
        except Exception as e:
            print(f"[list_datas] chapteruid 조회 오류: {e}", file=sys.stderr)

    if single_pid is None:
        project_ids, pmap = _active_projects(sb, str(user.id))
        if not project_ids:
            return {"datas": []}

    try:
        if single_pid is not None:
            # chapteruid 경로: .eq() 사용 (llm/init과 동일한 방식)
            query = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("projectid", single_pid)
        else:
            query = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").in_("projectid", project_ids)

        if datasourcecd:
            query = query.eq("datasourcecd", datasourcecd)
        rows = query.order("datanm").execute().data or []
    except Exception as e:
        print(f"[list_datas] datas 조회 오류: {e}", file=sys.stderr)
        return {"datas": []}

    for r in rows:
        pid = r.get("projectid")
        r["projectnm"] = pmap.get(pid)

    if datasourcecd == "db" and rows:
        cids = list({r["connectid"] for r in rows if r.get("connectid")})
        if cids:
            connectors = (
                sb.schema(SUPABASE_SCHEMA).table("dbconnectors")
                .select("connectid, connectnm").in_("connectid", cids)
                .execute().data or []
            )
            cmap = {c["connectid"]: c["connectnm"] for c in connectors}
            for r in rows:
                r["connectnm"] = cmap.get(r.get("connectid"), "")

    return {"datas": rows}


# ── Source datas list (for AI page) ────────────────────────────────────────────

@router.get("/source")
def list_source_datas(token: str = Depends(get_token)):
    """DB / Excel 데이터소스 목록 (AI 데이터 연결용)"""
    user = _get_user(token)
    sb = _sb(token)
    active_ids, _ = _active_projects(sb, str(user.id))
    if not active_ids:
        return {"datas": []}
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("datauid, datanm, datasourcecd, projectid")
        .in_("projectid", active_ids)
        .neq("datasourcecd", "df")
        .order("datanm")
        .execute().data or []
    )
    return {"datas": rows}


# ── DB Data Save ────────────────────────────────────────────────────────────────

@router.post("/db")
def save_db_data(body: DbDataSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "projectid": body.projectid,
        "datanm": body.datanm,
        "connectid": body.connectid,
        "query": body.query,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("datas").update(record).eq("datauid", body.datauid).execute()
        return {"datauid": body.datauid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    record["datasourcecd"] = "db"
    resp = sb.schema(SUPABASE_SCHEMA).table("datas").insert(record).execute()
    return {"datauid": resp.data[0]["datauid"], "message": "저장되었습니다."}


# ── Excel Data Save ─────────────────────────────────────────────────────────────

@router.post("/ex")
async def save_ex_data(
    projectid: int = Form(...),
    datanm: str = Form(...),
    datauid: Optional[str] = Form(None),
    excelfile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    record: dict = {"projectid": projectid, "datanm": datanm}

    existing_url = None
    if datauid:
        res = sb.schema(SUPABASE_SCHEMA).table("datas").select("excelurl").eq("datauid", datauid).execute()
        if res.data:
            existing_url = res.data[0].get("excelurl")

    if excelfile:
        _delete_storage(sb, existing_url)
        content = await excelfile.read()
        ext = os.path.splitext(excelfile.filename)[1]
        fname = f"{uuid.uuid4()}{ext}"
        path = f"source/{projectid}/{fname}"
        sb.storage.from_("smartdoc").upload(path, content, {"content-type": excelfile.content_type})
        public_url = sb.storage.from_("smartdoc").get_public_url(path).split("?")[0]
        record["excelurl"] = public_url
        record["excelnm"] = excelfile.filename

    if datauid:
        sb.schema(SUPABASE_SCHEMA).table("datas").update(record).eq("datauid", datauid).execute()
        return {"datauid": datauid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    record["datasourcecd"] = "ex"
    resp = sb.schema(SUPABASE_SCHEMA).table("datas").insert(record).execute()
    return {"datauid": resp.data[0]["datauid"], "message": "저장되었습니다."}


# ── AI Data Save ────────────────────────────────────────────────────────────────

@router.post("/ai")
def save_ai_data(body: AiDataSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "projectid": body.projectid,
        "datanm": body.datanm,
        "sourcedatauid": body.sourcedatauid,
        "gensentence": body.sentence,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("datas").update(record).eq("datauid", body.datauid).execute()
        return {"datauid": body.datauid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    record["datasourcecd"] = "df"
    resp = sb.schema(SUPABASE_SCHEMA).table("datas").insert(record).execute()
    return {"datauid": resp.data[0]["datauid"], "message": "저장되었습니다."}


# ── Delete ──────────────────────────────────────────────────────────────────────

@router.delete("/{datauid}")
def delete_data(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    # Delete storage file if excel
    res = sb.schema(SUPABASE_SCHEMA).table("datas").select("excelurl").eq("datauid", datauid).execute()
    if res.data:
        _delete_storage(sb, res.data[0].get("excelurl"))
    sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
    resp = sb.schema(SUPABASE_SCHEMA).table("datas").delete().eq("datauid", datauid).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="삭제할 데이터가 없습니다.")
    return {"message": "삭제되었습니다."}


# ── DataCols ────────────────────────────────────────────────────────────────────

@router.get("/datacols", response_model=DataColsResponse)
def get_datacols(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datacols")
        .select("*").eq("datauid", datauid).order("orderno")
        .execute().data or []
    )
    return {"columns": rows}


@router.post("/datacols/create")
def create_datacols(body: dict, token: str = Depends(get_token)):
    """쿼리를 실행해 컬럼을 자동 생성한다."""
    user = _get_user(token)
    sb = _sb(token)
    datauid = body.get("datauid")
    projectid = body.get("projectid")
    if not datauid:
        raise HTTPException(status_code=400, detail="datauid가 필요합니다.")

    data_resp = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("datauid", datauid).execute()
    if not data_resp.data:
        raise HTTPException(status_code=404, detail="해당 데이터가 없습니다.")

    import string
    from utilsPrj.process_data import process_data

    class _FakeRequest:
        def __init__(self, access_token: str):
            self.session = {"access_token": access_token, "refresh_token": None}
            self.method = "GET"
            if projectid:
                self.projectid = projectid

    try:
        df = process_data(_FakeRequest(token), datauid=datauid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실행 오류: {e}")

    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="쿼리 실행 결과가 없습니다.")

    cols = df.columns.tolist()

    # Fill empty names
    alphabet = list(string.ascii_uppercase)
    filled = []
    empty_idx = 0
    for c in cols:
        if str(c).strip() == "":
            filled.append(alphabet[empty_idx % 26])
            empty_idx += 1
        else:
            filled.append(c)
    cols = filled

    # Deduplicate
    seen: dict = {}
    deduped = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            deduped.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            deduped.append(c)
    cols = deduped

    sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
    records = [
        {"datauid": datauid, "querycolnm": c, "dispcolnm": c, "creator": str(user.id), "orderno": i}
        for i, c in enumerate(cols, 1)
    ]
    if records:
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert(records).execute()

    return {"message": "컬럼이 생성되었습니다.", "columns": cols}


@router.get("/rows")
def get_data_rows(datauid: str, token: str = Depends(get_token)):
    """데이터 미리보기 — 최대 15행 반환"""
    _get_user(token)
    sb = _sb(token)

    from utilsPrj.process_data import process_data, apply_column_display_mapping

    class _FakeRequest:
        def __init__(self, access_token):
            self.session = {"access_token": access_token, "refresh_token": None}
            self.method = "GET"

    try:
        req = _FakeRequest(token)
        df = process_data(req, datauid=datauid)
        raw_columns = df.columns.tolist()
        raw_rows = df.head(15).values.tolist()
        _, dict_rows = apply_column_display_mapping(datauid, raw_columns, raw_rows, sb)
        return {"data": dict_rows}
    except Exception as e:
        import traceback, sys
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"데이터 조회 오류: {e}")


@router.post("/datacols")
def save_datacols(cols: list[DataColItem], token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    if not cols:
        raise HTTPException(status_code=400, detail="컬럼 데이터가 필요합니다.")
    datauids = {c.datauid for c in cols}
    if len(datauids) != 1:
        raise HTTPException(status_code=400, detail="모든 컬럼의 datauid가 동일해야 합니다.")
    datauid = datauids.pop()
    sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
    records = [
        {
            "datauid": c.datauid,
            "querycolnm": c.querycolnm,
            "dispcolnm": c.dispcolnm or c.querycolnm,
            "datatypecd": c.datatypecd,
            "measureyn": c.measureyn or False,
            "creator": str(user.id),
            "orderno": i,
        }
        for i, c in enumerate(cols, 1)
    ]
    sb.schema(SUPABASE_SCHEMA).table("datacols").insert(records).execute()
    return {"message": "저장되었습니다."}
