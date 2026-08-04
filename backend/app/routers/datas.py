import math
import os
import re
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user, require_doc_read, require_doc_write
from backend.app.schemas.datas import (
    AiDataSaveRequest, AiPreviewRequest, DataColItem, DataColsResponse,
    DbConnectorsResponse, DbDataSaveRequest, DatasListResponse,
    DfDataSaveRequest, DfvDataSaveRequest,
    ApiConnectorsResponse, ApiDataSaveRequest,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()

_DDL_TYPE_MAP = {
    # string
    'varchar': 'string', 'nvarchar': 'string', 'char': 'string', 'nchar': 'string',
    'varchar2': 'string', 'nvarchar2': 'string',
    # text
    'text': 'text', 'ntext': 'text', 'clob': 'text', 'nclob': 'text',
    'longtext': 'text', 'mediumtext': 'text', 'tinytext': 'text',
    # number
    'int': 'number', 'integer': 'number', 'bigint': 'number', 'smallint': 'number', 'tinyint': 'number',
    'float': 'number', 'real': 'number', 'double': 'number',
    'numeric': 'number', 'decimal': 'number', 'number': 'number',
    # currency
    'money': 'currency', 'smallmoney': 'currency',
    # date
    'date': 'date',
    # datetime
    'datetime': 'datetime', 'datetime2': 'datetime', 'timestamp': 'datetime',
    'smalldatetime': 'datetime', 'datetimeoffset': 'datetime', 'time': 'datetime',
    # boolean
    'bit': 'boolean', 'boolean': 'boolean', 'bool': 'boolean',
    # identifier
    'uniqueidentifier': 'identifier', 'serial': 'identifier', 'bigserial': 'identifier',
}
_DDL_SKIP = {'constraint', 'primary', 'foreign', 'unique', 'index', 'check', 'key'}


def parse_ddl_columns(ddl: str) -> list[dict]:
    """CREATE TABLE DDL에서 컬럼 목록을 추출한다."""
    # ON [filegroup] 등 CREATE TABLE 끝 절 허용
    match = re.search(r'\((.+)\)\s*(?:ON\s+\S+)?\s*;?\s*$', ddl.strip(), re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    inner = match.group(1)
    segments, depth, buf = [], 0, []
    for ch in inner:
        if ch == '(':
            depth += 1; buf.append(ch)
        elif ch == ')':
            depth -= 1; buf.append(ch)
        elif ch == ',' and depth == 0:
            segments.append(''.join(buf).strip()); buf = []
        else:
            buf.append(ch)
    if buf:
        segments.append(''.join(buf).strip())
    result = []
    for i, seg in enumerate(segments, 1):
        tokens = seg.strip().split()
        if not tokens or tokens[0].lower().strip('[]"`\'') in _DDL_SKIP:
            continue
        col_name = tokens[0].strip('[]"`\' ')
        # 대괄호·따옴표 제거 후 타입 추출 ([int] → int, [nvarchar](25) → nvarchar)
        raw_type = tokens[1].strip('[]"`\'').lower().split('(')[0] if len(tokens) > 1 else 'varchar'
        result.append({
            'querycolnm': col_name,
            'dispcolnm':  col_name,
            'datatypecd': _DDL_TYPE_MAP.get(raw_type, 'string'),
            'measureyn':  False,
            'orderno':    i,
        })
    return result


def _active_projects(sb, user_id: str, servicecd: Optional[str] = None, tenantid: Optional[str] = None):
    proj_list = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_project_filtered__r_user_manager_viewer", {"p_useruid": user_id})
        .execute().data or []
    )
    ids = [p["projectid"] for p in proj_list]
    if not ids:
        return [], {}, {}
    q = (
        sb.schema(SUPABASE_SCHEMA).table("projects")
        .select("projectid, projectnm, servicecd")
        .in_("projectid", ids).eq("useyn", True)
    )
    if servicecd:
        q = q.eq("servicecd", servicecd)
    if tenantid:
        q = q.eq("tenantid", int(tenantid))
    active = q.execute().data or []
    pmap = {p["projectid"]: p["projectnm"] for p in active}
    svc_map = {p["projectid"]: p.get("servicecd") for p in active}
    return [p["projectid"] for p in active], pmap, svc_map


def _delete_storage(sb, url: str):
    if not url:
        return
    parsed = urlparse(url)
    prefix = "/storage/v1/object/public/sdoc/"
    if prefix in parsed.path:
        path = parsed.path.split(prefix)[-1]
        try:
            sb.storage.from_("sdoc").remove([path])
        except Exception:
            pass


# ── Projects ───────────────────────────────────────────────────────────────────

@router.get("/projects", dependencies=[Depends(require_doc_read)])
def list_datas_projects(servicecd: Optional[str] = None, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    active_ids, pmap, svc_map = _active_projects(sb, str(user.id), servicecd, tenantid)

    myprojectid = None
    if servicecd:
        # serviceusers는 (useruid, servicecd) 조합이 테넌트별로 행이 나뉘므로
        # tenantid 없이 조회하면 다중 테넌트 계정에서 .maybe_single()이 406(복수 행)으로 실패한다.
        try:
            su_q = sb.schema(SUPABASE_SCHEMA).table("serviceusers") \
                .select("myprojectid").eq("useruid", str(user.id)).eq("servicecd", servicecd)
            if tenantid:
                su_q = su_q.eq("tenantid", int(tenantid))
            su_row = su_q.maybe_single().execute()
            if su_row and su_row.data:
                myprojectid = su_row.data.get("myprojectid")
        except Exception:
            pass

    return {
        "projects": [
            {"projectid": pid, "projectnm": pmap[pid], "servicecd": svc_map.get(pid)}
            for pid in active_ids
        ],
        "myprojectid": myprojectid,
    }


class MyProjectRequest(BaseModel):
    myprojectid: str
    servicecd: str

@router.post("/myproject", dependencies=[Depends(require_doc_write)])
def update_my_project(body: MyProjectRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    # serviceusers는 (useruid, servicecd) 조합이 테넌트별로 행이 나뉘므로 tenantid로 반드시 제한
    # (안 그러면 다른 테넌트의 myprojectid 행까지 덮어써버림)
    query = sb.schema(SUPABASE_SCHEMA).table("serviceusers").update({"myprojectid": body.myprojectid}) \
        .eq("useruid", str(user.id)).eq("servicecd", body.servicecd)
    if tenantid:
        query = query.eq("tenantid", int(tenantid))
    query.execute()
    return {"status": "ok"}


# ── Datas by Project (read-only) ───────────────────────────────────────────────

_DATASOURCE_LABEL = {
    "db": "DB",
    "ex": "Excel",
    "api": "API",
    "df": "AI DataSet - Dataset",
    "dfv": "AI DataSet - Variable",
}


@router.get("/by-project", dependencies=[Depends(require_doc_read)])
def list_datas_by_project(
    projectid: Optional[str] = None,
    docid: Optional[str] = None,
    token: str = Depends(get_token),
):
    _get_user(token)
    sb = _sb(token)

    if not projectid:
        return {"items": []}

    # db/ex/api: projectid 기준
    base_datas = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("*")
        .eq("projectid", int(projectid))
        .in_("datasourcecd", ["db", "ex", "api"])
        .execute().data or []
    )

    # df: doc_datas where docid=? and useyn=true 기준
    df_datas = []
    if docid:
        doc_data_uids = [
            r["datauid"] for r in (
                sb.schema(SUPABASE_SCHEMA).table("doc_datas")
                .select("datauid").eq("docid", int(docid)).eq("useyn", True)
                .execute().data or []
            )
        ]
        if doc_data_uids:
            df_datas = (
                sb.schema(SUPABASE_SCHEMA).table("datas")
                .select("*")
                .eq("datasourcecd", "df")
                .in_("datauid", doc_data_uids)
                .execute().data or []
            )

    # dfv: dfv_docid 기준
    dfv_datas = []
    if docid:
        dfv_datas = (
            sb.schema(SUPABASE_SCHEMA).table("datas")
            .select("*")
            .eq("dfv_docid", int(docid))
            .eq("datasourcecd", "dfv")
            .execute().data or []
        )

    # 데이터 그룹(project_datasets) 매핑: is_directdatauid=true면 datauid 직접, false면 datasetmembers 경유
    pd_rows = (
        sb.schema(SUPABASE_SCHEMA).table("project_datasets")
        .select("datasetuid, is_directdatauid").eq("projectid", int(projectid)).execute().data or []
    )
    pd_uids = {r["datasetuid"] for r in pd_rows if r.get("is_directdatauid")}
    group_ids = [r["datasetuid"] for r in pd_rows if not r.get("is_directdatauid")]
    if group_ids:
        member_rows = (
            sb.schema(SUPABASE_SCHEMA).table("datasetmembers")
            .select("datauid").in_("datasetuid", group_ids).execute().data or []
        )
        pd_uids |= {r["datauid"] for r in member_rows}

    pd_datas = []
    if pd_uids:
        pd_datas = (
            sb.schema(SUPABASE_SCHEMA).table("dataunits")
            .select("*").in_("datauid", list(pd_uids)).execute().data or []
        )

    datas_by_uid = {d["datauid"]: d for d in base_datas + df_datas + dfv_datas + pd_datas}
    datas = list(datas_by_uid.values())

    # 사용 중 목록: doc_datas.docid 기준
    doc_use_set: set = set()
    if docid:
        doc_data_rows = (
            sb.schema(SUPABASE_SCHEMA).table("doc_datas")
            .select("datauid")
            .eq("docid", int(docid))
            .execute().data or []
        )
        doc_use_set = {r["datauid"] for r in doc_data_rows if r.get("datauid")}

    # df/dfv는 sourcedatauid의 connector를 사용
    src_uids = list({d["sourcedatauid"] for d in datas if d.get("datasourcecd") in ("df", "dfv") and d.get("sourcedatauid")})
    src_conn_lookup: dict = {}
    if src_uids:
        src_rows = (
            sb.schema(SUPABASE_SCHEMA).table("datas")
            .select("datauid, connuid")
            .in_("datauid", src_uids)
            .execute().data or []
        )
        src_conn_lookup = {r["datauid"]: r.get("connuid") for r in src_rows}

    all_conn_ids = list({
        cid for cid in
        [d.get("connuid") for d in datas] +
        list(src_conn_lookup.values())
        if cid
    })
    conn_map: dict = {}
    if all_conn_ids:
        connectors = (
            sb.schema(SUPABASE_SCHEMA).table("connectors")
            .select("connuid, connnm")
            .in_("connuid", all_conn_ids)
            .execute().data or []
        )
        conn_map = {c["connuid"]: c["connnm"] for c in connectors}

    def _connnm(d: dict) -> str:
        src = d.get("datasourcecd") or ""
        if src in ("df", "dfv"):
            src_connuid = src_conn_lookup.get(d.get("sourcedatauid") or "")
            return conn_map.get(src_connuid or "", "")
        return conn_map.get(d.get("connuid") or "", "")

    _SORT_ORDER = {"db": 0, "ex": 1, "api": 2, "df": 3, "dfv": 4}

    items = sorted(
        [
            {
                "datauid": d.get("datauid"),
                "datanm": d.get("datanm") or "",
                "datasourcecd": d.get("datasourcecd") or "",
                "datasource_label": _DATASOURCE_LABEL.get(d.get("datasourcecd") or "", d.get("datasourcecd") or ""),
                "connnm": _connnm(d),
                "desc": d.get("desc"),
                "useyn": d.get("useyn"),
                "doc_use_yn": d.get("datasourcecd") == "dfv" or d.get("datauid") in doc_use_set,
            }
            for d in datas
        ],
        key=lambda x: (_SORT_ORDER.get(x["datasourcecd"], 99), x["connnm"].lower(), x["datanm"].lower()),
    )

    return {"items": items}


@router.get("/{datauid}/detail", dependencies=[Depends(require_doc_read)])
def get_data_detail(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    rows = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("datauid", datauid).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    d = rows[0]
    src = d.get("datasourcecd") or ""

    # 커넥터 dbtype 조회
    dbtype = None
    if d.get("connuid"):
        conn_row = (
            sb.schema(SUPABASE_SCHEMA).table("connectors")
            .select("dbtype")
            .eq("connuid", d["connuid"])
            .execute().data
        )
        dbtype = conn_row[0].get("dbtype") if conn_row else None

    result: dict = {
        "datasourcecd": src,
        "dbtype": dbtype,
        "query": d.get("query"),
        "endpoint": d.get("endpoint"),
        "excelnm": d.get("excelnm"),
        "gensentence": d.get("gensentence"),
        "conn_api": None,
        "source_data": None,
    }

    if src == "api" and d.get("connuid"):
        ca = (
            sb.schema(SUPABASE_SCHEMA).table("conn_apis")
            .select("baseurl, authtype")
            .eq("connuid", d["connuid"])
            .execute().data
        )
        result["conn_api"] = ca[0] if ca else None

    if src in ("df", "dfv") and d.get("sourcedatauid"):
        sr = (
            sb.schema(SUPABASE_SCHEMA).table("datas")
            .select("*")
            .eq("datauid", d["sourcedatauid"])
            .execute().data
        )
        if sr:
            s = sr[0]
            s_src = s.get("datasourcecd") or ""
            source_data: dict = {
                "datanm": s.get("datanm"),
                "datasourcecd": s_src,
                "datasource_label": _DATASOURCE_LABEL.get(s_src, s_src),
                "connnm": "",
                "dbtype": None,
                "query": s.get("query"),
                "endpoint": s.get("endpoint"),
                "excelnm": s.get("excelnm"),
                "conn_api": None,
            }
            if s.get("connuid"):
                conn = (
                    sb.schema(SUPABASE_SCHEMA).table("connectors")
                    .select("connnm, dbtype")
                    .eq("connuid", s["connuid"])
                    .execute().data
                )
                if conn:
                    source_data["connnm"] = conn[0].get("connnm", "")
                    source_data["dbtype"] = conn[0].get("dbtype")
                if s_src == "api":
                    ca2 = (
                        sb.schema(SUPABASE_SCHEMA).table("conn_apis")
                        .select("baseurl, authtype")
                        .eq("connuid", s["connuid"])
                        .execute().data
                    )
                    source_data["conn_api"] = ca2[0] if ca2 else None
            result["source_data"] = source_data

    datacols = (
        sb.schema(SUPABASE_SCHEMA).table("datacols")
        .select("querycolnm, dispcolnm, datatypecd, measureyn, orderno")
        .eq("datauid", datauid)
        .order("orderno")
        .execute().data or []
    )
    result["datacols"] = datacols

    return result


# ── DB Connectors ──────────────────────────────────────────────────────────────

@router.get("/dbconnectors", response_model=DbConnectorsResponse, dependencies=[Depends(require_doc_read)])
def list_dbconnectors(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("connuid, connnm")
        .eq("useyn", True).eq("conntype", "db").eq("tenantid", tenantid)
        .execute().data or []
    )
    return {"connectors": rows}


# ── API Connectors ─────────────────────────────────────────────────────────────

@router.get("/api-connectors", response_model=ApiConnectorsResponse, dependencies=[Depends(require_doc_read)])
def list_apiconnectors(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("connuid, connnm")
        .eq("tenantid", tenantid).eq("conntype", "api").eq("useyn", True)
        .order("connnm")
        .execute().data or []
    )
    return {"connectors": rows}


# ── Datas List ──────────────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(require_doc_read)])
def list_datas(
    datasourcecd: Optional[str] = None,
    chapteruid: Optional[str] = None,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    import sys
    user = _get_user(token)
    sb = _sb(token)

    # ex 타입은 dataunits가 projectid 없이 tenantid로만 스코핑되므로 datas/project 경유 없이 직접 조회
    if datasourcecd == "ex" and not chapteruid:
        query = sb.schema(SUPABASE_SCHEMA).table("dataunits") \
            .select("*").eq("tenantid", tenantid).eq("datasourcecd", "ex")

        issystemtenant = True
        if tenantid:
            t_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
            issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True
        if issystemtenant:
            query = query.eq("creator", str(user.id))

        rows = query.execute().data or []
        rows.sort(key=lambda r: (r.get("datanm") or "").lower())
        return {"datas": rows}

    # db/api 타입은 프로젝트 연결과 무관하게 테넌트 소속이면 바로 노출
    # (단, 시스템 테넌트는 여러 개인 계정이 tenantid를 공유하므로 creator로 추가 제한)
    if datasourcecd in ("db", "api") and not chapteruid:
        issystemtenant = True
        if tenantid:
            t_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
            issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True

        query = (
            sb.schema(SUPABASE_SCHEMA).table("dataunits")
            .select("*").eq("tenantid", tenantid).eq("datasourcecd", datasourcecd)
        )
        if issystemtenant:
            query = query.eq("creator", str(user.id))
        rows = query.execute().data or []
        if rows:
            cids = list({r["connuid"] for r in rows if r.get("connuid")})
            if cids:
                connectors = (
                    sb.schema(SUPABASE_SCHEMA).table("connectors")
                    .select("connuid, connnm").in_("connuid", cids)
                    .execute().data or []
                )
                cmap = {c["connuid"]: c["connnm"] for c in connectors}
                key = "connectnm" if datasourcecd == "db" else "connnm"
                for r in rows:
                    r[key] = cmap.get(r.get("connuid"), "")
        rows.sort(key=lambda r: ((r.get("connectnm") or r.get("connnm") or "").lower(), (r.get("datanm") or "").lower()))
        return {"datas": rows}

    # chapteruid가 있으면 해당 챕터의 projectid로 직접 필터 (llm/init 방식과 동일)
    single_pid = None
    chapter_docid = None
    project_ids: list = []
    pmap: dict = {}
    if chapteruid:
        try:
            ch = sb.schema(SUPABASE_SCHEMA).table("chapters").select("docid").eq("chapteruid", chapteruid).execute().data or []
            if ch:
                chapter_docid = ch[0]["docid"]
                docs = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid, docnm").eq("docid", chapter_docid).execute().data or []
                if docs:
                    single_pid = docs[0]["projectid"]
                    pmap = {single_pid: docs[0].get("docnm", "")}
        except Exception as e:
            print(f"[list_datas] chapteruid 조회 오류: {e}", file=sys.stderr)

    if single_pid is None:
        project_ids, pmap, _ = _active_projects(sb, str(user.id), tenantid=tenantid)

    try:
        rows = []
        if single_pid is not None:
            # chapteruid 경로: .eq() 사용 (llm/init과 동일한 방식)
            query = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("projectid", single_pid)
            if datasourcecd:
                query = query.eq("datasourcecd", datasourcecd)
            rows = query.execute().data or []
        elif project_ids:
            query = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").in_("projectid", project_ids)
            if datasourcecd:
                query = query.eq("datasourcecd", datasourcecd)
            rows = query.execute().data or []

        # db/api는 프로젝트 연결과 무관하게 테넌트 소속이면 항상 포함
        if not datasourcecd or datasourcecd in ("db", "api"):
            dbapi_types = [datasourcecd] if datasourcecd else ["db", "api"]
            dbapi_rows = (
                sb.schema(SUPABASE_SCHEMA).table("datas").select("*")
                .eq("tenantid", tenantid).in_("datasourcecd", dbapi_types)
                .execute().data or []
            )
            rows += dbapi_rows
    except Exception as e:
        print(f"[list_datas] datas 조회 오류: {e}", file=sys.stderr)
        return {"datas": []}

    # doc_datas 필터: chapteruid 경로에서 doc_datas에 등록된 datauid만 노출 (db/ex/df 모두)
    if chapter_docid:
        doc_datas_rows = sb.schema(SUPABASE_SCHEMA).table("doc_datas") \
            .select("datauid").eq("docid", chapter_docid) \
            .execute().data or []
        allowed_uids = {d["datauid"] for d in doc_datas_rows}
        rows = [r for r in rows if r["datauid"] in allowed_uids]

    # AI로 만든 데이터(df/dfv)는 시스템 테넌트에서 본인이 등록한 것이면
    # doc_datas 등록 여부와 무관하게 노출 (master/datas/ai에서 아직 doc_datas에 매핑할 방법이 없음)
    if chapter_docid and (not datasourcecd or datasourcecd in ("df", "dfv")):
        issystemtenant = True
        if tenantid:
            t_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
            issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True

        if issystemtenant:
            ai_rows = []
            if single_pid is not None and (not datasourcecd or datasourcecd == "df"):
                ai_rows += (
                    sb.schema(SUPABASE_SCHEMA).table("datas").select("*")
                    .eq("projectid", single_pid).eq("datasourcecd", "df").eq("creator", str(user.id))
                    .execute().data or []
                )
            if not datasourcecd or datasourcecd == "dfv":
                ai_rows += (
                    sb.schema(SUPABASE_SCHEMA).table("datas").select("*")
                    .eq("dfv_docid", chapter_docid).eq("datasourcecd", "dfv").eq("creator", str(user.id))
                    .execute().data or []
                )
            existing_uids = {r["datauid"] for r in rows}
            rows += [r for r in ai_rows if r["datauid"] not in existing_uids]

    for r in rows:
        pid = r.get("projectid")
        r["projectnm"] = pmap.get(pid)

    db_rows = [r for r in rows if r.get("datasourcecd") == "db"]
    if db_rows:
        cids = list({r["connuid"] for r in db_rows if r.get("connuid")})
        if cids:
            connectors = (
                sb.schema(SUPABASE_SCHEMA).table("connectors")
                .select("connuid, connnm").in_("connuid", cids)
                .execute().data or []
            )
            cmap = {c["connuid"]: c["connnm"] for c in connectors}
            for r in db_rows:
                r["connectnm"] = cmap.get(r.get("connuid"), "")

    api_rows = [r for r in rows if r.get("datasourcecd") == "api"]
    if api_rows:
        conn_uids = list({r["connuid"] for r in api_rows if r.get("connuid")})
        if conn_uids:
            api_conns = (
                sb.schema(SUPABASE_SCHEMA).table("connectors")
                .select("connuid, connnm").in_("connuid", conn_uids)
                .execute().data or []
            )
            cmap = {c["connuid"]: c["connnm"] for c in api_conns}
            for r in api_rows:
                r["connnm"] = cmap.get(r.get("connuid"), "")

    rows.sort(key=lambda r: (
        (r.get("projectnm") or "").lower(),
        (r.get("connectnm") or "").lower(),
        (r.get("datanm") or "").lower(),
    ))

    return {"datas": rows}


# ── Source datas list (for AI page) ────────────────────────────────────────────

@router.get("/source", dependencies=[Depends(require_doc_read)])
def list_source_datas(projectid: int = None, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """DB / API / Excel 데이터소스 목록 (AI 데이터 연결용)"""
    user = _get_user(token)
    sb = _sb(token)

    issystemtenant = True
    if tenantid:
        t_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
        issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True

    # db/api (+ 기업 테넌트의 ex): 프로젝트 연결과 무관하게 테넌트 소속이면 전부 후보
    # (단, 시스템 테넌트는 여러 개인 계정이 tenantid를 공유하므로 creator로 추가 제한)
    tenant_wide_types = ["db", "api"] if issystemtenant else ["db", "api", "ex"]
    tenant_wide_query = (
        sb.schema(SUPABASE_SCHEMA).table("datas")
        .select("datauid, datanm, datasourcecd, projectid")
        .eq("tenantid", tenantid).in_("datasourcecd", tenant_wide_types)
    )
    if issystemtenant:
        tenant_wide_query = tenant_wide_query.eq("creator", str(user.id))
    rows = tenant_wide_query.execute().data or []

    # 개인/시스템 테넌트의 ex: 기존처럼 프로젝트(=creator가 매니저인 프로젝트) 기준
    if issystemtenant:
        ex_query = (
            sb.schema(SUPABASE_SCHEMA).table("datas")
            .select("datauid, datanm, datasourcecd, projectid")
            .eq("datasourcecd", "ex")
        )
        if projectid:
            rows += ex_query.eq("projectid", projectid).execute().data or []
        else:
            active_ids, _, _ = _active_projects(sb, str(user.id), tenantid=tenantid)
            if active_ids:
                rows += ex_query.in_("projectid", active_ids).execute().data or []

    rows.sort(key=lambda r: (r.get("datanm") or "").lower())
    return {"datas": rows}


# ── DB Data Save ────────────────────────────────────────────────────────────────

@router.post("/db", dependencies=[Depends(require_doc_write)])
def save_db_data(body: DbDataSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    if body.databasiscd == "dbq":
        query_val = body.querybasis
    elif body.databasiscd == "dbt":
        query_val = f"SELECT * FROM {body.querybasis}" if body.querybasis else None
    else:  # dbs — createCols 시점에 DDL 파싱 후 채워짐
        query_val = None

    record = {
        "tenantid":    tenantid,
        "datanm":      body.datanm,
        "desc":        body.desc,
        "connuid":     body.connuid,
        "databasiscd": body.databasiscd,
        "querybasis":  body.querybasis,
        "query":       query_val,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("dataunits").update(record).eq("datauid", body.datauid).execute()
        return {"datauid": body.datauid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    record["datasourcecd"] = "db"
    resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").insert(record).execute()
    datauid = resp.data[0]["datauid"]
    return {"datauid": datauid, "message": "저장되었습니다."}


# ── Excel Data Save ─────────────────────────────────────────────────────────────

@router.post("/ex", dependencies=[Depends(require_doc_write)])
async def save_ex_data(
    datanm: str = Form(...),
    datauid: Optional[str] = Form(None),
    accountuid: Optional[str] = Form(None),
    excelfile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    record: dict = {"tenantid": tenantid, "datanm": datanm}

    existing_url = None
    if datauid:
        res = sb.schema(SUPABASE_SCHEMA).table("datas").select("excelurl").eq("datauid", datauid).execute()
        if res.data:
            existing_url = res.data[0].get("excelurl")

    if excelfile:
        content = await excelfile.read()

        plancd = None
        if accountuid:
            svc = sb.schema(SUPABASE_SCHEMA).table("accountservices") \
                .select("plancd").eq("accountuid", accountuid).eq("servicecd", "Do") \
                .maybe_single().execute()
            plancd = svc.data.get("plancd") if svc and svc.data else None

        limit_mb = None
        if plancd:
            cfg = sb.schema(SUPABASE_SCHEMA).table("config_plans") \
                .select("value").eq("configcd", "Excel_Size_Limit").eq("plancd", plancd).eq("servicecd", "Do") \
                .execute()
            values = [float(r["value"]) for r in (cfg.data or []) if r.get("value") is not None]
            if values:
                limit_mb = max(values)

        if limit_mb is None:
            raise HTTPException(status_code=400, detail="업로드 용량 제한 정보를 확인할 수 없어 업로드할 수 없습니다.")
        if len(content) > limit_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"엑셀 파일 크기는 최대 {limit_mb:g}MB까지 업로드할 수 있습니다.")

        _delete_storage(sb, existing_url)
        ext = os.path.splitext(excelfile.filename)[1]
        fname = f"{uuid.uuid4()}{ext}"
        path = f"source/ex/{tenantid or 'common'}/{fname}"
        sb.storage.from_("sdoc").upload(path, content, {"content-type": excelfile.content_type})
        public_url = sb.storage.from_("sdoc").get_public_url(path).split("?")[0]
        record["excelurl"] = public_url
        record["excelnm"] = excelfile.filename

    if datauid:
        sb.schema(SUPABASE_SCHEMA).table("dataunits").update(record).eq("datauid", datauid).execute()
        return {"datauid": datauid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    record["datasourcecd"] = "ex"
    resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").insert(record).execute()
    new_datauid = resp.data[0]["datauid"]
    return {"datauid": new_datauid, "message": "저장되었습니다."}


# ── AI Data Save ────────────────────────────────────────────────────────────────

@router.post("/ai", dependencies=[Depends(require_doc_write)])
def save_ai_data(body: AiDataSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "tenantid": tenantid,
        "datanm": body.datanm,
        "sourcedatauid": body.sourcedatauid,
        "gensentence": body.sentence,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("dataunits").update(record).eq("datauid", body.datauid).execute()
        return {"datauid": body.datauid, "message": "저장되었습니다."}
    record["creator"] = str(user.id)
    record["datasourcecd"] = "df"
    resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").insert(record).execute()
    return {"datauid": resp.data[0]["datauid"], "message": "저장되었습니다."}


# ── API Data Save ───────────────────────────────────────────────────────────────

@router.post("/api", dependencies=[Depends(require_doc_write)])
def save_api_data(body: ApiDataSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "datanm":    body.datanm,
        "desc":      body.desc,
        "connuid":   body.connuid,
        "endpoint":  body.endpoint,
        "useyn":     body.useyn,
        "tenantid":  tenantid,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("dataunits").update(record).eq("datauid", body.datauid).execute()
        datauid = body.datauid
    else:
        record["creator"]      = str(user.id)
        record["datasourcecd"] = "api"
        resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").insert(record).execute()
        datauid = resp.data[0]["datauid"]

    # params: 기존 전체 삭제 후 재삽입
    sb.schema(SUPABASE_SCHEMA).table("data_api_params").delete().eq("datauid", datauid).execute()
    if body.params:
        sb.schema(SUPABASE_SCHEMA).table("data_api_params").insert([
            {
                "datauid":          datauid,
                "paramnm":          p.paramnm,
                "param_locationcd": p.param_locationcd,
                "datatypecd":       p.datatypecd,
                "is_required":      p.is_required,
                "testvalue":        p.testvalue,
                "is_fixed":         p.is_fixed,
                "fixed_value":      p.fixed_value,
                "desc":             p.desc,
                "orderno":          p.orderno if p.orderno is not None else i,
                "creator":          str(user.id),
            }
            for i, p in enumerate(body.params, 1)
        ]).execute()

    return {"datauid": datauid, "message": "저장되었습니다."}


# ── API Params Get ──────────────────────────────────────────────────────────────

@router.get("/apiparams", dependencies=[Depends(require_doc_read)])
def get_apiparams(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("data_api_params")
        .select("*").eq("datauid", datauid).order("orderno")
        .execute().data or []
    )
    return {"params": rows}


# ── DF/DFV List ────────────────────────────────────────────────────────────────

@router.get("/df-list", dependencies=[Depends(require_doc_read)])
def list_df_datas(projectid: int, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    # df: project_datasets(is_directdatauid=true)로 이 프로젝트에 직접 연결된 datauid만
    pd_resp = (
        sb.schema(SUPABASE_SCHEMA).table("project_datasets")
        .select("datasetuid").eq("projectid", projectid).eq("is_directdatauid", True).execute()
    )
    df_uids = [r["datasetuid"] for r in (pd_resp.data or [])]
    df_rows = []
    if df_uids:
        # datas 뷰는 doc_datas 매핑이 없는 df 행을 노출하지 않으므로(문서 미연결 df 존재 가능),
        # 실제 저장 테이블인 dataunits에서 직접 조회한다.
        df_resp = (
            sb.schema(SUPABASE_SCHEMA).table("dataunits")
            .select("datauid, datanm, datasourcecd, sourcedatauid, gensentence, is_multirow")
            .eq("datasourcecd", "df").in_("datauid", df_uids).execute()
        )
        df_rows = df_resp.data or []

    # dfv: 이 프로젝트 소속 문서에 연결된(dfv_docid) 것만
    doc_resp = sb.schema(SUPABASE_SCHEMA).table("docs").select("docid").eq("projectid", projectid).execute()
    project_docids = [d["docid"] for d in (doc_resp.data or [])]
    dfv_rows = []
    if project_docids:
        dfv_resp = (
            sb.schema(SUPABASE_SCHEMA).table("dataunits")
            .select("datauid, datanm, datasourcecd, sourcedatauid, gensentence, is_multirow, dfv_docid")
            .eq("datasourcecd", "dfv").in_("dfv_docid", project_docids).execute()
        )
        dfv_rows = dfv_resp.data or []

    return {"datas": df_rows + dfv_rows}


# ── AI Preview ─────────────────────────────────────────────────────────────────

@router.post("/ai-preview", dependencies=[Depends(require_doc_write)])
def preview_ai_data(body: AiPreviewRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    class _FakeRequest:
        def __init__(self, t, projectid):
            self.session = {"access_token": t, "refresh_token": None}
            self.method = "GET"
            if projectid:
                self.projectid = projectid

    from utilsPrj.process_data_ai import process_data_ai_preview
    result = process_data_ai_preview(sb, _FakeRequest(token, body.projectid), body.sourcedatauid, body.gensentence, docid=body.docid)
    df = result.get("result")
    
    raw = df.head(15).to_dict(orient="records") if df is not None and not df.empty else []
    rows = [{k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in r.items()} for r in raw]
    return {
        "rows": rows,
        "cols_info": result.get("cols_info"),
    }


# ── DF Save ────────────────────────────────────────────────────────────────────

@router.post("/df", dependencies=[Depends(require_doc_write)])
def save_df_data(body: DfDataSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    record = {
        "tenantid": tenantid,
        "datanm": body.datanm,
        "sourcedatauid": body.sourcedatauid,
        "gensentence": body.gensentence,
        "is_multirow": body.is_multirow,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("dataunits").update(record).eq("datauid", body.datauid).execute()
        datauid = body.datauid
    else:
        record.update({"creator": str(user.id), "datasourcecd": "df"})
        resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").insert(record).execute()
        datauid = resp.data[0]["datauid"]

    # project_datasets: datasetuid 자리에 datauid를 직접 넣어 프로젝트-데이터 연결(is_directdatauid=true)
    sb.schema(SUPABASE_SCHEMA).table("project_datasets").delete() \
        .eq("datasetuid", datauid).eq("is_directdatauid", True).execute()
    sb.schema(SUPABASE_SCHEMA).table("project_datasets").insert({
        "projectid": body.projectid,
        "datasetuid": datauid,
        "tenantid": tenantid,
        "useyn": True,
        "creator": str(user.id),
        "is_directdatauid": True,
    }).execute()

    if body.cols:
        sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert(
            [{**c.model_dump(), "datauid": datauid, "useyn": True, "creator": str(user.id)} for c in body.cols]
        ).execute()
    return {"datauid": datauid, "message": "저장되었습니다."}


# ── DFV Save ───────────────────────────────────────────────────────────────────

@router.post("/dfv", dependencies=[Depends(require_doc_write)])
def save_dfv_data(body: DfvDataSaveRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)

    doc_row = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid").eq("docid", body.dfv_docid).maybe_single().execute()
    if not doc_row.data or doc_row.data.get("projectid") != body.projectid:
        raise HTTPException(status_code=400, detail="msg.dfv.doc.project.mismatch")

    record = {
        "tenantid": tenantid,
        "datanm": body.datanm,
        "sourcedatauid": body.sourcedatauid,
        "gensentence": body.gensentence,
        "is_multirow": body.is_multirow,
        "dfv_docid": body.dfv_docid,
    }
    if body.datauid:
        sb.schema(SUPABASE_SCHEMA).table("dataunits").update(record).eq("datauid", body.datauid).execute()
        datauid = body.datauid
    else:
        record.update({"creator": str(user.id), "datasourcecd": "dfv"})
        resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").insert(record).execute()
        datauid = resp.data[0]["datauid"]

    # dfv는 문서 1개에만 귀속 — 기존 매핑(문서가 바뀐 경우 포함) 정리 후 재삽입
    sb.schema(SUPABASE_SCHEMA).table("doc_datas").delete().eq("datauid", datauid).execute()
    sb.schema(SUPABASE_SCHEMA).table("doc_datas").insert(
        {"docid": body.dfv_docid, "datauid": datauid, "useyn": True, "creator": str(user.id)}
    ).execute()

    if body.cols:
        sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert(
            [{**c.model_dump(), "datauid": datauid, "useyn": True, "creator": str(user.id)} for c in body.cols]
        ).execute()
    return {"datauid": datauid, "message": "저장되었습니다."}


# ── Delete ──────────────────────────────────────────────────────────────────────

@router.delete("/{datauid}", dependencies=[Depends(require_doc_write)])
def delete_data(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    res = sb.schema(SUPABASE_SCHEMA).table("datas").select("excelurl, datasourcecd").eq("datauid", datauid).execute()
    if res.data:
        _delete_storage(sb, res.data[0].get("excelurl"))
    sb.schema(SUPABASE_SCHEMA).table("doc_datas").delete().eq("datauid", datauid).execute()
    sb.schema(SUPABASE_SCHEMA).table("project_datasets").delete() \
        .eq("datasetuid", datauid).eq("is_directdatauid", True).execute()
    sb.schema(SUPABASE_SCHEMA).table("data_api_params").delete().eq("datauid", datauid).execute()
    sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
    resp = sb.schema(SUPABASE_SCHEMA).table("dataunits").delete().eq("datauid", datauid).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="삭제할 데이터가 없습니다.")
    return {"message": "삭제되었습니다."}


# ── DataCols ────────────────────────────────────────────────────────────────────

@router.get("/datacols", response_model=DataColsResponse, dependencies=[Depends(require_doc_read)])
def get_datacols(datauid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("datacols")
        .select("*").eq("datauid", datauid).eq("useyn", True).order("orderno")
        .execute().data or []
    )
    return {"columns": rows}


def _infer_col_type(v) -> tuple:
    if isinstance(v, bool):
        return "boolean", False
    if isinstance(v, (int, float)):
        return "number", True
    return "string", False


def _extract_json_columns(data) -> list:
    """JSON 응답에서 컬럼 목록 추출. list[dict] 또는 dict 처리."""
    target = None
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            target = data[0]
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                target = v[0]
                break
        if target is None:
            target = data
    if not target:
        return []
    result = []
    for i, (k, v) in enumerate(target.items(), 1):
        dtype, measure = _infer_col_type(v)
        result.append({"querycolnm": str(k), "dispcolnm": str(k),
                        "datatypecd": dtype, "measureyn": measure, "orderno": i})
    return result


@router.post("/datacols/create", dependencies=[Depends(require_doc_write)])
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

    data_row = data_resp.data[0]
    databasiscd = data_row.get("databasiscd")

    # ── dbs 모드: DDL 파싱 → 컬럼 생성 + query 컬럼 업데이트 ───────────
    if databasiscd == "dbs":
        querybasis = data_row.get("querybasis") or ""
        parsed = parse_ddl_columns(querybasis)
        if not parsed:
            raise HTTPException(status_code=400, detail="DDL에서 컬럼을 추출할 수 없습니다.")

        tbl_match = re.search(r'CREATE\s+TABLE\s+(\S+)\s*\(', querybasis, re.IGNORECASE)
        table_name = tbl_match.group(1).rstrip('(') if tbl_match else "unknown"
        col_list = ", ".join(c["querycolnm"] for c in parsed)
        select_query = f"SELECT {col_list} FROM {table_name}"

        sb.schema(SUPABASE_SCHEMA).table("dataunits").update({"query": select_query}).eq("datauid", datauid).execute()
        sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
        records = [
            {
                "datauid":    datauid,
                "querycolnm": c["querycolnm"],
                "dispcolnm":  c["dispcolnm"],
                "datatypecd": c["datatypecd"],
                "measureyn":  c["measureyn"],
                "orderno":    c["orderno"],
                "useyn":      True,
                "creator":    str(user.id),
            }
            for c in parsed
        ]
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert(records).execute()
        return {"message": "컬럼이 생성되었습니다.", "columns": [c["querycolnm"] for c in parsed]}

    # ── api 모드: 실제 API 호출 → 응답 파싱 → 컬럼 생성 ────────────────
    if data_row.get("datasourcecd") == "api":
        import json as _json
        connuid  = data_row.get("connuid")
        endpoint = data_row.get("endpoint") or ""
        if not connuid:
            raise HTTPException(status_code=400, detail="API 커넥터가 설정되지 않았습니다.")

        api_row = (
            sb.schema(SUPABASE_SCHEMA).table("conn_apis")
            .select("baseurl, authtype, health_method").eq("connuid", connuid).execute().data
        )
        if not api_row:
            raise HTTPException(status_code=400, detail="커넥터 API 설정이 없습니다.")
        conn_api = api_row[0]
        baseurl  = conn_api.get("baseurl") or ""
        authtype = conn_api.get("authtype") or "NONE"
        method   = conn_api.get("health_method") or "GET"

        if not baseurl:
            raise HTTPException(status_code=400, detail="커넥터 Base URL이 설정되지 않았습니다.")

        cred_rows = (
            sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials")
            .select("*").eq("connuid", connuid).execute().data
        )
        cred = cred_rows[0] if cred_rows else {}
        secret_path = cred.get("secret_path") or ""
        secrets: dict = {}
        if secret_path == "aws-sm":
            from utilsPrj.secrets_cache import get_connector_secret
            conn_row = (
                sb.schema(SUPABASE_SCHEMA).table("connectors")
                .select("tenantid").eq("connuid", connuid).execute().data
            )
            _tenantid = conn_row[0]["tenantid"] if conn_row else None
            try:
                secrets = get_connector_secret(_tenantid, connuid)
            except Exception:
                secrets = {}
        elif secret_path:
            try:
                secrets = _json.loads(secret_path)
            except Exception:
                secrets = {}

        param_rows = (
            sb.schema(SUPABASE_SCHEMA).table("data_api_params")
            .select("*").eq("datauid", datauid).order("orderno").execute().data or []
        )

        full_url = baseurl.rstrip("/") + ("" if endpoint.startswith("/") else "/") + endpoint

        if authtype == "OAUTH2":
            if not cred.get("token_endpoint"):
                raise HTTPException(status_code=400, detail="OAuth2 Token Endpoint가 설정되지 않았습니다. 커넥터 설정을 확인하세요.")
            if not cred.get("oauth_client_id"):
                raise HTTPException(status_code=400, detail="OAuth2 Client ID가 설정되지 않았습니다.")
            if not secrets.get("oauth_client_secret"):
                raise HTTPException(status_code=400, detail="OAuth2 Client Secret이 설정되지 않았습니다. 커넥터 저장 시 Secret을 다시 입력하세요.")

        from utilsPrj.api_helper import call_api_for_data
        result = call_api_for_data(
            url=full_url,
            method=method,
            authtype=authtype,
            api_params=param_rows,
            auth_cred=cred,
            secrets=secrets,
        )

        if not result.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=f"API 호출 실패 ({result.get('status_code', 0)}): {result.get('detail', '')}",
            )

        parsed = _extract_json_columns(result.get("data"))
        if not parsed:
            raise HTTPException(status_code=400, detail="API 응답에서 컬럼을 추출할 수 없습니다.")

        sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).execute()
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert([
            {
                "datauid":    datauid,
                "querycolnm": c["querycolnm"],
                "dispcolnm":  c["dispcolnm"],
                "datatypecd": c["datatypecd"],
                "measureyn":  c["measureyn"],
                "orderno":    c["orderno"],
                "useyn":      True,
                "creator":    str(user.id),
            }
            for c in parsed
        ]).execute()
        return {"message": "컬럼이 생성되었습니다.", "columns": [c["querycolnm"] for c in parsed]}
    # ────────────────────────────────────────────────────────────────────

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
        {
            "datauid":    datauid,
            "querycolnm": c,
            "dispcolnm":  c,
            "datatypecd": "string",
            "useyn":      True,
            "measureyn":  False,
            "creator":    str(user.id),
            "orderno":    i,
        }
        for i, c in enumerate(cols, 1)
    ]
    if records:
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert(records).execute()

    return {"message": "컬럼이 생성되었습니다.", "columns": cols}


@router.get("/rows", dependencies=[Depends(require_doc_read)])
def get_data_rows(datauid: str, token: str = Depends(get_token), docid: Optional[str] = None):
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
        df = process_data(req, datauid=datauid, docid=docid)
        raw_columns = df.columns.tolist()
        raw_rows = df.head(15).values.tolist()
        _, dict_rows = apply_column_display_mapping(datauid, raw_columns, raw_rows, sb)
        return {"data": dict_rows}
    except Exception as e:
        import traceback, sys
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"데이터 조회 오류: {e}")


@router.post("/datacols", dependencies=[Depends(require_doc_write)])
def save_datacols(cols: list[DataColItem], token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    if not cols:
        raise HTTPException(status_code=400, detail="컬럼 데이터가 필요합니다.")
    datauids = {c.datauid for c in cols}
    if len(datauids) != 1:
        raise HTTPException(status_code=400, detail="모든 컬럼의 datauid가 동일해야 합니다.")
    datauid = datauids.pop()

    existing = sb.schema(SUPABASE_SCHEMA).table("datacols").select("querycolnm").eq("datauid", datauid).execute().data or []
    existing_names = {r["querycolnm"] for r in existing}
    incoming_map = {c.querycolnm: c for c in cols}
    incoming_names = set(incoming_map.keys())

    # 삭제: DB에 있지만 incoming에 없는 컬럼
    to_delete = existing_names - incoming_names
    if to_delete:
        sb.schema(SUPABASE_SCHEMA).table("datacols").delete().eq("datauid", datauid).in_("querycolnm", list(to_delete)).execute()

    # 추가: incoming에 있지만 DB에 없는 컬럼
    to_insert = incoming_names - existing_names
    if to_insert:
        insert_records = [
            {
                "datauid":    datauid,
                "querycolnm": c.querycolnm,
                "dispcolnm":  c.dispcolnm or c.querycolnm,
                "datatypecd": c.datatypecd,
                "measureyn":  c.measureyn or False,
                "useyn":      c.useyn if c.useyn is not None else True,
                "creator":    str(user.id),
                "orderno":    i,
                "field_path": c.field_path,
            }
            for i, c in enumerate(cols, 1)
            if c.querycolnm in to_insert
        ]
        sb.schema(SUPABASE_SCHEMA).table("datacols").insert(insert_records).execute()

    # 수정: 양쪽에 모두 있는 컬럼은 편집 가능한 모든 필드 업데이트
    to_update = existing_names & incoming_names
    for i, c in enumerate(cols, 1):
        if c.querycolnm not in to_update:
            continue
        sb.schema(SUPABASE_SCHEMA).table("datacols").update({
            "dispcolnm":  c.dispcolnm or c.querycolnm,
            "datatypecd": c.datatypecd,
            "measureyn":  c.measureyn or False,
            "useyn":      c.useyn if c.useyn is not None else True,
            "orderno":    i,
            "field_path": c.field_path,
        }).eq("datauid", datauid).eq("querycolnm", c.querycolnm).execute()

    return {"message": "저장되었습니다."}
