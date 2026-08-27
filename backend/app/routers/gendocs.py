import boto3
import io
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from dateutil import parser as dp
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user, require_doc_read, require_doc_write
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client
from utilsPrj.notifications import create_notification
from utilsPrj.user_lookup import get_usernm_email

router = APIRouter()


def _get_docid(sb, user_id: str, tenantid: Optional[str] = None) -> Optional[int]:
    # serviceusers는 (useruid, servicecd) 조합이 활성 테넌트별로 행이 나뉘므로
    # tenantid로 제한하지 않으면 다중 테넌트 계정에서 임의의(엉뚱한) 행이 잡힐 수 있다.
    query = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("mydocid").eq("useruid", user_id).eq("servicecd", "Do")
    if tenantid:
        query = query.eq("tenantid", int(tenantid))
    row = query.execute().data
    docid = row[0].get("mydocid") if row else None
    return int(docid) if docid else None


def _tenant_of_doc(sb, docid: int) -> Optional[str]:
    doc_row = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid").eq("docid", docid).maybe_single().execute()
    if not doc_row or not doc_row.data or not doc_row.data.get("projectid"):
        return None
    proj_row = sb.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq("projectid", doc_row.data["projectid"]).maybe_single().execute()
    return str(proj_row.data["tenantid"]) if proj_row and proj_row.data and proj_row.data.get("tenantid") is not None else None


def _resolve_docid(sb, user_id: str, tenantid: Optional[str], requested_docid: Optional[int]) -> Optional[int]:
    """docid를 현재 테넌트 기준으로 검증/해석한다.

    serviceusers.mydocid(마지막 선택 문서)는 테넌트 구분 없이 전역으로 저장되므로,
    다른 테넌트로 전환한 상태에서 그대로 쓰면 이전 테넌트의 문서가 노출될 수 있다.
    """
    candidate = requested_docid or _get_docid(sb, user_id, tenantid)
    if candidate and (not tenantid or _tenant_of_doc(sb, candidate) == str(tenantid)):
        return candidate

    if not tenantid:
        return None

    # 현재 테넌트에서 열람 가능한 문서 중 하나로 대체
    docs_data = sb.schema(SUPABASE_SCHEMA).rpc("fn_docs_filtered__r_user_viewer", {"p_useruid": user_id}).execute().data or []
    docids = [d["docid"] for d in docs_data if d.get("docid")]
    if not docids:
        return None
    docs_details = sb.schema(SUPABASE_SCHEMA).table("docs").select("docid, projectid").in_("docid", docids).execute().data or []
    project_ids = list({d["projectid"] for d in docs_details if d.get("projectid")})
    if not project_ids:
        return None
    proj_rows = (
        sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid")
        .in_("projectid", project_ids).eq("tenantid", tenantid).eq("useyn", True)
        .execute().data or []
    )
    valid_pids = {p["projectid"] for p in proj_rows}
    for d in docs_details:
        if d.get("projectid") in valid_pids:
            return d["docid"]
    return None


def _get_user_context(sb, user_id: str, tenantid: Optional[str] = None) -> dict:
    """docid → projectid → tenantid 순으로 조회하여 LLM 모델 선택에 필요한 컨텍스트 반환.

    serviceusers는 (useruid, servicecd) 조합이 활성 테넌트별로 행이 나뉘므로,
    호출부에서 현재 활성 테넌트(tenantid, X-Tenant-ID)를 넘겨 그 행만 조회한다
    (안 넘기면 다중 테넌트 계정에서 임의의 테넌트 행이 잡힐 수 있음).
    """
    docid = doc_tenantid = projectid = None
    try:
        query = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("mydocid").eq("useruid", user_id).eq("servicecd", "Do")
        if tenantid:
            query = query.eq("tenantid", int(tenantid))
        row = query.execute().data
        if row and row[0].get("mydocid"):
            docid = int(row[0]["mydocid"])
    except Exception:
        pass

    try:
        if docid:
            doc_row = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid").eq("docid", docid).execute().data
            if doc_row and doc_row[0].get("projectid"):
                projectid = doc_row[0]["projectid"]
    except Exception:
        pass

    try:
        if projectid:
            proj_row = sb.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq("projectid", projectid).execute().data
            if proj_row and proj_row[0].get("tenantid"):
                doc_tenantid = proj_row[0]["tenantid"]
    except Exception:
        pass

    return {"docid": docid, "tenantid": doc_tenantid, "projectid": projectid}


def _get_chapteruids_for_gendoc(sb, gendocuid: str) -> list:
    rows = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("chapteruid").eq("gendocuid", gendocuid).execute().data or []
    return list({r["chapteruid"] for r in rows if r.get("chapteruid")})


def _count_active_objects(sb, chapteruids: list) -> int:
    """대상 챕터들의 활성/설정완료 objects 건수 (useyn=True AND objectsettingyn=True)
    주의: 이 값은 사전 차단용 1차 필터(대략치)일 뿐 실제 사용 크레딧과 다를 수 있다.
    챕터 생성 시 for문으로 항목 1개가 조건별로 여러 건(예: 5건)으로 확장될 수 있어,
    실제 차감(genchapterlogs.count, genobjectlogs 기준 실제 생성 건수)이 이 값을 초과해
    creditbuckets가 마이너스가 되는 것은 정상적인 사후 정산 케이스다."""
    if not chapteruids:
        return 0
    res = sb.schema(SUPABASE_SCHEMA).table("objects").select("objectuid", count="exact") \
        .in_("chapteruid", chapteruids).eq("useyn", True).eq("objectsettingyn", True).execute()
    return res.count or 0


def _get_remain_credit(sb_svc, accountuid: str) -> int:
    rows = sb_svc.schema(SUPABASE_SCHEMA).table("vw_creditbucketsums").select("remaincredit") \
        .eq("accountuid", accountuid).eq("servicecd", "Do").execute().data or []
    return sum(r.get("remaincredit") or 0 for r in rows)


def _check_credit_gate(sb, sb_svc, accountuid: Optional[str], chapteruids: list) -> Optional[dict]:
    """예정크레딧(대상 objects 건수)이 잔여크레딧을 초과하면 안내 dict 반환, 충분하면 None.
    accountuid가 없으면(문서 조합 작성 화면 등 아직 미전달) 체크를 생략한다.
    BYOK(고객 자체 AI 키) 계정은 크레딧을 쓰지 않으므로 항상 통과시킨다(2026-08-13 추가)."""
    if not accountuid:
        return None
    from utilsPrj.credit_helper import is_byok_account
    if is_byok_account(sb_svc, accountuid, "Do"):
        return None
    planned_credit = _count_active_objects(sb, chapteruids)
    remain_credit = _get_remain_credit(sb_svc, accountuid)
    if remain_credit < planned_credit:
        return {
            "insufficient_credit": True,
            "message": f"잔여 크레딧이 부족하여 작성할 수 없습니다. (필요 크레딧: {planned_credit}, 잔여 크레딧: {remain_credit})",
        }
    return None


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


def _fmt(val: Optional[str], offsetminutes: Optional[int] = None) -> str:
    if not val:
        return ""
    try:
        dt = dp.parse(val) if isinstance(val, str) else val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _parse_ts(val):
    """비교용 — raw timestamp 문자열/값을 tz-aware datetime으로. 실패/빈값이면 None."""
    if not val:
        return None
    try:
        dt = dp.parse(val) if isinstance(val, str) else val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class FakeRequest:
    """Minimal Django-like request stub for utilsPrj compatibility."""
    def __init__(self, access_token: str, user_id: str, docid: Optional[int] = None,
                 tenantid=None, projectid=None):
        self.session = {
            "access_token": access_token,
            "refresh_token": None,
            "user": {
                "id": user_id,
                "docid": str(docid) if docid else None,
                "tenantid": tenantid,
                "projectid": projectid,
            },
        }
        self.method = "POST"


# ── Gendoc List ─────────────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(require_doc_read)])
def list_gendocs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    docid: Optional[int] = None,
    search_by: Optional[str] = "Doc",
    docgroupid: Optional[int] = None,
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    docid = _resolve_docid(sb, str(user.id), tenantid, docid)
    if not docid:
        return {"gendocs": [], "docnm": None, "dataparams": []}

    today = datetime.now(timezone.utc).date()
    sd = start_date or (today - timedelta(days=10)).strftime("%Y-%m-%d")
    ed = end_date or today.strftime("%Y-%m-%d")
    offsetminutes = _get_offsetminutes(sb, str(user.id), tenantid)

    # 사용자 로컬 날짜 → UTC 변환 후 RPC 전달
    # utc = local_midnight(UTC 기준) - offsetminutes분
    if offsetminutes is not None:
        sd_utc = datetime.strptime(sd, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(minutes=offsetminutes)
        ed_utc = datetime.strptime(ed, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1) - timedelta(minutes=offsetminutes)
        rpc_params = {"p_docid": docid, "p_start_date": sd_utc.isoformat(), "p_end_date": ed_utc.isoformat(), "p_search_by": search_by, "p_docgroupid": docgroupid}
    else:
        end_plus = (datetime.strptime(ed, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        rpc_params = {"p_docid": docid, "p_start_date": sd, "p_end_date": end_plus, "p_search_by": search_by, "p_docgroupid": docgroupid}

    rows = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs__r_docid", rpc_params).execute().data or []
    docnm_resp = sb.schema(SUPABASE_SCHEMA).table("docs").select("docnm").eq("docid", docid).execute().data
    docnm = docnm_resp[0]["docnm"] if docnm_resp else None

    # fn_gendocs__r_docid RPC가 paramchangedyn을 내려주지 않아 별도 조회 후 병합
    gendocuids = [r["gendocuid"] for r in rows if r.get("gendocuid")]
    paramchanged_map = {}
    if gendocuids:
        pc_rows = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocuid,paramchangedyn").in_("gendocuid", gendocuids).execute().data or []
        paramchanged_map = {r["gendocuid"]: r.get("paramchangedyn", False) for r in pc_rows}

    for item in rows:
        item["paramchangedyn"] = paramchanged_map.get(item.get("gendocuid"), False)
        item["createfiledts"] = _fmt(item.get("createfiledts"), offsetminutes)
        item["updatefiledts"] = _fmt(item.get("updatefiledts"), offsetminutes)
        item["closedts"] = _fmt(item.get("closedts"), offsetminutes)
        item["createdts"] = _fmt(item.get("createdts"), offsetminutes)
        # params
        params = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs_params__r", {"p_gendocuid": item["gendocuid"]}).execute().data or []
        item["params"] = params
        item["finalnm_joined"] = " / ".join(p.get("finalnm") or p.get("paramvalue") or "" for p in params if p.get("paramvalue"))

    docparams = sb.schema(SUPABASE_SCHEMA).table("docparams").select("*").eq("docid", docid).order("orderno").execute().data or []

    return {"gendocs": rows, "docnm": docnm, "dataparams": docparams, "docid": docid}


# ── Gendoc Detail ───────────────────────────────────────────────────────────────

@router.get("/dataparams", dependencies=[Depends(require_doc_read)])
def get_dataparams(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    ctx = _get_user_context(sb, str(user.id), tenantid)
    docid = ctx["docid"]
    if not docid:
        return {"dataparams": [], "params_value": []}

    docparams = sb.schema(SUPABASE_SCHEMA).table("docparams").select("*").eq("docid", docid).order("orderno").execute().data or []
    data_ids = [d["datauid"] for d in docparams if d.get("datauid")]
    datas = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").in_("datauid", data_ids).execute().data or [] if data_ids else []

    # Run each data source to get options
    from utilsPrj.process_data import process_data
    import pandas as pd, numpy as np
    from datetime import date

    def _convert(v):
        if isinstance(v, bytes):
            return v.decode("utf-8")
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        if isinstance(v, (float,)) and (v != v):
            return None
        try:
            if isinstance(v, (np.integer, np.floating)):
                return v.item()
        except Exception:
            pass
        return v

    req = FakeRequest(token, str(user.id), docid, tenantid=ctx["tenantid"], projectid=ctx["projectid"])
    params_value = []
    for data_item in datas:
        try:
            df = process_data(req, datauid=data_item["datauid"], all=True)
            rows = df.to_dict("records") if not df.empty else []
            rows = [{k: _convert(v) for k, v in r.items()} for r in rows]
            rows = sorted(rows, key=lambda x: str(list(x.values())[0]) if x else "")
        except Exception:
            rows = []
        params_value.append({"datauid": data_item["datauid"], "value": rows})

    return {"dataparams": docparams, "params_value": params_value}


@router.get("/{gendocuid}/status", dependencies=[Depends(require_doc_read)])
def get_gendoc_status(gendocuid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    status_rows = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendoc_status__r", {"p_gendocuid": gendocuid}).execute().data or []
    gendoc = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs__r", {"p_gendocuid": gendocuid}).execute().data or []
    offsetminutes = _get_offsetminutes(sb, str(user.id), tenantid)

    for i in status_rows:
        i["createfiledts"] = _fmt(i.get("createfiledts"), offsetminutes)
        i["updatefiledts"] = _fmt(i.get("updatefiledts"), offsetminutes)

    gendocnm = gendoc[0]["gendocnm"] if gendoc else ""
    createfiledts = _fmt(gendoc[0].get("createfiledts"), offsetminutes) if gendoc else ""
    return {"status": status_rows, "gendocnm": gendocnm, "createfiledts": createfiledts}


@router.get("/{gendocuid}/chapters", dependencies=[Depends(require_doc_read)])
def get_genchapters(gendocuid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id), tenantid)

    gendoc = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs__r", {"p_gendocuid": gendocuid}).execute().data or []
    gendoc_info = gendoc[0] if gendoc else {}
    doc_createfiledts_dt = _parse_ts(gendoc_info.get("createfiledts"))

    chapters = sb.schema(SUPABASE_SCHEMA).rpc("fn_genchapters__r_gendocuid", {"p_gendocuid": gendocuid}).execute().data or []
    for c in chapters:
        # 신규작성/신규업로드 — 챕터가 문서 최종 병합(gendocs.createfiledts)보다 나중에
        # (재)작성/업로드됐으면 체크 → 지금 문서 파일엔 이 챕터의 최신 내용이 반영 안 된 상태.
        # RPC(fn_genchapters__r_gendocuid)가 반환하는 chaptercreate/uploadchapter는 이 비교와
        # 무관한(작성방식 출처) 값이라 여기서 직접 계산해 덮어쓴다.
        chap_created_dt = _parse_ts(c.get("createfiledts"))
        chap_updated_dt = _parse_ts(c.get("updatefiledts"))
        c["new_chapteryn"] = bool(chap_created_dt and doc_createfiledts_dt and chap_created_dt > doc_createfiledts_dt)
        c["new_uploadyn"] = bool(chap_updated_dt and doc_createfiledts_dt and chap_updated_dt > doc_createfiledts_dt)
        c["createfiledts"] = _fmt(c.get("createfiledts"), offsetminutes)
        c["updatefiledts"] = _fmt(c.get("updatefiledts"), offsetminutes)

    gendoc_info["createfiledts"] = _fmt(gendoc_info.get("createfiledts"), offsetminutes)
    gendoc_info["updatefiledts"] = _fmt(gendoc_info.get("updatefiledts"), offsetminutes)
    # fn_gendocs__r는 finaldts 미확정 시 NULL 대신 1900-01-01(UTC) 센티널을 반환한다.
    # 타임존 오프셋 적용 후 문자열로 비교하면(예: KST) "1900-01-01 09:00"처럼 오프셋만큼
    # 시각이 밀려 표시되므로, 오프셋 적용 전 원본(UTC) 날짜를 기준으로 판정해야 한다.
    finaldts_raw = gendoc_info.get("finaldts")
    finaldts_dt = _parse_ts(finaldts_raw)
    finaldts_unset = bool(finaldts_dt and (finaldts_dt.year, finaldts_dt.month, finaldts_dt.day) == (1900, 1, 1))
    gendoc_info["finaldts"] = "" if finaldts_unset else _fmt(finaldts_raw, offsetminutes)
    return {"chapters": chapters, "gendoc": gendoc_info}


# ── Gendoc Create ───────────────────────────────────────────────────────────────

class GendocCreateRequest(BaseModel):
    docid: int
    docnm: str
    params: list[dict]
    projectid: Optional[int] = None
    tenantid: Optional[int] = None
    accountuid: Optional[str] = None


@router.post("", dependencies=[Depends(require_doc_write)])
def create_gendoc(body: GendocCreateRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now(timezone.utc).isoformat()

    # 1. Create gendocs
    result = sb.schema(SUPABASE_SCHEMA).table("gendocs").insert({
        "docid": body.docid,
        "gendocnm": body.docnm,
        "creator": user_id,
        "projectid": body.projectid,
        "tenantid": body.tenantid,
        "accountuid": body.accountuid,
    }).execute()
    gendocuid = result.data[0]["gendocuid"]

    # 2. Create gendoc_params
    if body.params:
        param_records = [
            {
                "gendocuid": gendocuid,
                "paramnm": p.get("paramnm"),
                "paramuid": p.get("paramuid"),
                "orderno": p.get("orderno"),
                "paramvalue": p.get("paramvalue"),
                "creator": user_id,
            }
            for p in body.params
        ]
        sb.schema(SUPABASE_SCHEMA).table("gendoc_params").insert(param_records).execute()

    # 3. Create genchapters (one per active chapter)
    chapters = (
        sb.schema(SUPABASE_SCHEMA).table("chapters")
        .select("*").eq("docid", body.docid).eq("useyn", True).execute().data or []
    )
    if chapters:
        genchapter_records = [
            {
                "docid": c["docid"],
                "chapteruid": c["chapteruid"],
                "gendocuid": gendocuid,
                "texttemplate": c.get("texttemplate"),
                "createfilestartdts": now,
                "creator": user_id,
                "createdts": now,
                "projectid": body.projectid,
                "tenantid": body.tenantid,
                "accountuid": body.accountuid,
            }
            for c in chapters
        ]
        sb.schema(SUPABASE_SCHEMA).table("genchapters").insert(genchapter_records).execute()

    return {"gendocuid": gendocuid, "message": "생성되었습니다."}


# ── Gendoc Delete ───────────────────────────────────────────────────────────────

@router.delete("/{gendocuid}", dependencies=[Depends(require_doc_write)])
def delete_gendoc(gendocuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    # Remove storage file
    row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("createfileurl,closeyn").eq("gendocuid", gendocuid).execute().data
    if row and row[0].get("closeyn"):
        raise HTTPException(status_code=400, detail="msg.gendoc.closed.readonly")
    if row and row[0].get("createfileurl"):
        url = row[0]["createfileurl"]
        parsed = urlparse(url)
        prefix = "/storage/v1/object/public/sdoc/"
        if prefix in parsed.path:
            try:
                sb.storage.from_("sdoc").remove([parsed.path.split(prefix)[-1]])
            except Exception:
                pass
    sb.schema(SUPABASE_SCHEMA).table("gendoc_params").delete().eq("gendocuid", gendocuid).execute()
    sb.schema(SUPABASE_SCHEMA).table("genchapters").delete().eq("gendocuid", gendocuid).execute()
    sb.schema(SUPABASE_SCHEMA).table("gendocs").delete().eq("gendocuid", gendocuid).execute()
    return {"message": "삭제되었습니다."}


# ── Gendoc Close / Open ─────────────────────────────────────────────────────────

@router.post("/{gendocuid}/close", dependencies=[Depends(require_doc_write)])
def close_gendoc(gendocuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now(timezone.utc).isoformat()

    row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("docid,createfiledts").eq("gendocuid", gendocuid).execute().data
    if not row:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if not row[0].get("createfiledts"):
        raise HTTPException(status_code=400, detail="msg.gendoc.close.needs.file")
    docid = row[0]["docid"]

    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({
        "closeyn": True,
        "closeuseruid": user_id,
        "closedts": now,
    }).eq("gendocuid", gendocuid).execute()

    sb.schema(SUPABASE_SCHEMA).table("loggendoccloses").upsert({
        "gendocuid": gendocuid,
        "docid": docid,
        "closeyn": True,
        "closeuseruid": user_id,
        "closedts": now,
    }).execute()

    return {"message": "마감 처리되었습니다."}


@router.post("/{gendocuid}/open", dependencies=[Depends(require_doc_write)])
def open_gendoc(gendocuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({
        "closeyn": False,
        "closeuseruid": None,
        "closedts": None,
    }).eq("gendocuid", gendocuid).execute()

    return {"message": "마감 해제되었습니다."}


# ── Params Update ────────────────────────────────────────────────────────────────

class GendocUpdateRequest(BaseModel):
    gendocuid: str
    gendocnm: str
    params: list[dict]


@router.post("/params/update", dependencies=[Depends(require_doc_write)])
def update_gendoc_params(body: GendocUpdateRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)

    gendoc_rows = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("closeyn,createfiledts").eq("gendocuid", body.gendocuid).execute().data
    if gendoc_rows and gendoc_rows[0].get("closeyn"):
        raise HTTPException(status_code=400, detail="msg.gendoc.closed.readonly")
    if gendoc_rows and gendoc_rows[0].get("createfiledts"):
        raise HTTPException(status_code=400, detail="msg.gendoc.file.readonly")

    # 저장 전 값과 비교해 실제로 매개변수가 바뀌었는지 판단 — 하위 챕터 재작업 필요 여부 표시에 사용
    existing_params = sb.schema(SUPABASE_SCHEMA).table("gendoc_params").select("paramuid,paramvalue").eq("gendocuid", body.gendocuid).execute().data or []
    existing_map = {p["paramuid"]: p.get("paramvalue") for p in existing_params}
    params_changed = any(existing_map.get(p.get("paramuid")) != p.get("paramvalue") for p in body.params)

    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({"gendocnm": body.gendocnm}).eq("gendocuid", body.gendocuid).execute()
    for p in body.params:
        sb.schema(SUPABASE_SCHEMA).table("gendoc_params").update({"paramvalue": p.get("paramvalue")}).eq("gendocuid", body.gendocuid).eq("paramuid", p.get("paramuid")).execute()

    if params_changed:
        genchap_exists = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("genchapteruid").eq("gendocuid", body.gendocuid).limit(1).execute().data
        if genchap_exists:
            sb.schema(SUPABASE_SCHEMA).table("gendocs").update({"paramchangedyn": True}).eq("gendocuid", body.gendocuid).execute()

    return {"message": "파라미터가 변경되었습니다."}


# ── Params Check ─────────────────────────────────────────────────────────────────

class ParamsCheckRequest(BaseModel):
    docid: int
    params: list[dict]


@router.post("/params/check", dependencies=[Depends(require_doc_write)])
def check_params(body: ParamsCheckRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    if not body.params:
        return {"exists": False}

    paramuids = [p["paramuid"] for p in body.params if p.get("paramuid")]
    rows = sb.schema(SUPABASE_SCHEMA).table("gendoc_params").select("*").in_("paramuid", paramuids).execute().data or []

    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["gendocuid"]].append(r)

    for gendocuid, items in grouped.items():
        if all(
            any(
                i["paramuid"] == p["paramuid"] and str(i["paramvalue"]).strip() == str(p["paramvalue"]).strip()
                for i in items
            )
            for p in body.params if p.get("paramuid")
        ):
            return {"exists": True, "gendocuid": gendocuid}

    return {"exists": False}


# ── Check Objects ────────────────────────────────────────────────────────────────

@router.post("/check-objects", dependencies=[Depends(require_doc_write)])
def check_objects(body: dict, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    docid = body.get("docid")
    chapters = sb.schema(SUPABASE_SCHEMA).table("chapters").select("*").eq("docid", docid).eq("useyn", True).execute().data or []
    unset = []
    for chap in chapters:
        objs = sb.schema(SUPABASE_SCHEMA).rpc("fn_objects__r", {"p_chapteruid": chap["chapteruid"]}).execute().data or []
        for obj in objs:
            if obj.get("useyn") and not obj.get("objectsettingyn"):
                unset.append({"text": f'챕터: {chap["chapternm"]} - 항목: {obj.get("objectnm", "")}'})
    return {"unset_objects": unset}


# ── Chapter Objects Read ──────────────────────────────────────────────────────────

@router.get("/genchapters/{genchapteruid}/objects", dependencies=[Depends(require_doc_read)])
def get_chapter_objects(genchapteruid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id), tenantid)

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid,chapteruid,docid,createfiledts").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]
    chapteruid = genchap[0]["chapteruid"]
    docid = genchap[0].get("docid")
    createfiledts_dt = _parse_ts(genchap[0].get("createfiledts"))
    createfiledts = _fmt(genchap[0].get("createfiledts"), offsetminutes)

    chapter = sb.schema(SUPABASE_SCHEMA).table("chapters").select("chapternm").eq("chapteruid", chapteruid).execute().data
    chapternm = chapter[0]["chapternm"] if chapter else ""

    gendoc = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocnm,closeyn").eq("gendocuid", gendocuid).execute().data
    closeyn = bool(gendoc[0]["closeyn"]) if gendoc else False
    gendocnm = gendoc[0]["gendocnm"] if gendoc else ""

    # RPC 대신 genobjects 직접 조회 (FOR 루프 확장으로 동일 objectuid에 genobject 여러 개)
    _type_nm_map = {
        "CA": "AI차트", "TA": "AI표", "SA": "AI문장",
        "CU": "차트", "TU": "표", "SU": "문장",
    }
    go_rows = sb.schema(SUPABASE_SCHEMA).table("genobjects").select("*").eq("genchapteruid", genchapteruid).order("createdts").execute().data or []
    objects = []
    for go in go_rows:
        obj_rows = sb.schema(SUPABASE_SCHEMA).table("objects").select("objectnm,objectdesc,objecttypecd,orderno,createdts,modifydts").eq("objectuid", go["objectuid"]).execute().data
        if not obj_rows:
            continue
        obj = obj_rows[0]
        typecd = go.get("objecttypecd") or obj.get("objecttypecd")

        go_created_dt = _parse_ts(go.get("createdts"))
        obj_modified_dt = _parse_ts(obj.get("modifydts")) or _parse_ts(obj.get("createdts"))

        # 설정 미반영 — 항목(objects) 설정이 이 genobject 콘텐츠가 생성된 시점보다 나중에 바뀌었으면 True
        new_objectyn = bool(obj_modified_dt and go_created_dt and obj_modified_dt > go_created_dt)
        # 항목 미반영 — 아직 한 번도 생성 안 됐거나(resulttext 없음), genobject 콘텐츠가 챕터 파일
        # 확정(createfiledts)보다 나중에 생성/재작성됐으면 True (예: 항목만 단독 재작성한 경우)
        new_genobjectyn = (not bool(go.get("resulttext"))) or bool(
            go_created_dt and createfiledts_dt and go_created_dt > createfiledts_dt
        )

        objects.append({
            "genobjectuid": go["genobjectuid"],
            "objectuid": go["objectuid"],
            "objectnm": obj.get("objectnm", ""),
            "objectdesc": obj.get("objectdesc", ""),
            "objecttypecd": typecd,
            "objecttypenm": _type_nm_map.get(typecd, typecd or ""),
            "filterjson": go.get("filterjson"),
            "orderno": obj.get("orderno", 0),
            "resulttext": go.get("resulttext"),
            "replacestring": go.get("replacestring"),
            "objcreatedts": _fmt(obj.get("createdts"), offsetminutes),
            "genobjcreatedts": _fmt(go.get("createdts"), offsetminutes),
            "new_objectyn": new_objectyn,
            "new_genobjectyn": new_genobjectyn,
            "chapteruid": chapteruid,
        })
    objects = sorted(objects, key=lambda x: (x.get("orderno", 0), str(x.get("filterjson") or "")))

    return {
        "objects": objects,
        "chapternm": chapternm,
        "gendocnm": gendocnm,
        "gendocuid": gendocuid,
        "docid": docid,
        "chapteruid": chapteruid,
        "closeyn": closeyn,
        "createfiledts": createfiledts,
    }


# ── Object Rewrite ───────────────────────────────────────────────────────────────

class ObjectRewriteRequest(BaseModel):
    objectuid: str


@router.post("/genchapters/{genchapteruid}/objects/{objectuid}/rewrite", dependencies=[Depends(require_doc_write)])
def rewrite_object(genchapteruid: str, objectuid: str, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id, tenantid)
    docid = ctx["docid"]

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]

    # Check locks
    genlocks_c = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).eq("genchapteruid", genchapteruid).execute().data or []
    genlocks_d = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).eq("genchapteruid", "").execute().data or []
    is_locked = any(r.get("doclocked") or r.get("chapterlocked") for r in genlocks_c + genlocks_d)
    if is_locked:
        raise HTTPException(status_code=409, detail="이 문서의 해당 챕터가 이미 작성 중입니다.")

    req = FakeRequest(token, user_id, docid, tenantid=ctx["tenantid"], projectid=ctx["projectid"])

    try:
        from utilsPrj.chapter_making import replace_doc

        for progress_data in replace_doc(req, sb, user_id, genchapteruid, "create", "rewrite", objectuid, genObjectDirectYn=True):
            if progress_data.get("type") == "error":
                raise HTTPException(status_code=500, detail=progress_data.get("message", "오류가 발생했습니다."))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    _increment_genobjectcount(sb, genchapteruid, objectuid)

    return {"success": True}


def _increment_genobjectcount(sb, genchapteruid: str, objectuid: str):
    """단일 항목 재작성(gencontenttypecd='O') 1회당 genobjectcounts에 시간당(1시간 버킷)+인원별 사용량 1건 집계"""
    try:
        row = sb.schema(SUPABASE_SCHEMA).table("genobjects").select("accountuid,tenantid,creator") \
            .eq("genchapteruid", genchapteruid).eq("objectuid", objectuid).execute().data
        if not row or not row[0].get("accountuid") or row[0].get("tenantid") is None:
            return

        from utilsPrj.credit_helper import increment_genobjectcount
        increment_genobjectcount(get_service_client(), row[0]["accountuid"], row[0]["tenantid"], row[0].get("creator"))
    except Exception:
        pass


# ── Apply Objects to Chapter ─────────────────────────────────────────────────────

@router.post("/genchapters/{genchapteruid}/apply", dependencies=[Depends(require_doc_write)])
def apply_chapter_objects(genchapteruid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid,chapteruid").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]
    chapteruid = genchap[0]["chapteruid"]

    # Check locks
    genlocks_c = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).eq("genchapteruid", genchapteruid).execute().data or []
    genlocks_d = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).eq("genchapteruid", "").execute().data or []
    is_locked = any(r.get("doclocked") or r.get("chapterlocked") for r in genlocks_c + genlocks_d)
    if is_locked:
        raise HTTPException(status_code=409, detail="이 문서의 해당 챕터가 이미 작성 중입니다.")

    # flattexttemplate 우선 사용 (FOR 루프 확장 플레이스홀더 포함), 없으면 texttemplate
    flat_row = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("flattexttemplate").eq("genchapteruid", genchapteruid).execute().data
    flat_template = flat_row[0].get("flattexttemplate") if flat_row else None
    chapter_row = sb.schema(SUPABASE_SCHEMA).table("chapters").select("texttemplate").eq("chapteruid", chapteruid).execute().data
    texttemplate = flat_template or (chapter_row[0]["texttemplate"] if chapter_row else "")

    # replacestring 기반 교체 (FOR 루프 확장 genobject 각각의 플레이스홀더 정확히 매칭)
    go_rows = sb.schema(SUPABASE_SCHEMA).table("genobjects").select("genobjectuid,replacestring,resulttext").eq("genchapteruid", genchapteruid).execute().data or []
    for go in go_rows:
        replace_key = go.get("replacestring")
        html = go.get("resulttext") or ""
        if replace_key:
            texttemplate = texttemplate.replace(replace_key, html)

    now = datetime.now(timezone.utc).isoformat()

    # Update genchapters
    sb.schema(SUPABASE_SCHEMA).table("genchapters").update({
        "gentexttemplate": texttemplate,
        "genchapteruid": genchapteruid,
        "createuserid": user_id,
        "createfiledts": now,
    }).eq("genchapteruid", genchapteruid).execute()

    # Insert log
    try:
        sb.schema(SUPABASE_SCHEMA).table("gendoc_genchapters").insert({
            "gendocuid": gendocuid,
            "genchapteruid": genchapteruid,
            "creator": user_id,
            "createdts": now,
        }).execute()
    except Exception:
        pass

    return {"success": True, "message": "항목 반영이 완료되었습니다."}


# ── Full-Document Content Read (req_chapter_read 해당) ──────────────────────────

@router.get("/{gendocuid}/doc-content", dependencies=[Depends(require_doc_read)])
def get_doc_content(
    gendocuid: str,
    type: str = "auto",
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    """전체 문서 HTML 내용 반환 (sep='doc') — Django chapter_read?sep=doc 에 해당"""
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id, tenantid)
    docid = ctx["docid"]
    offsetminutes = _get_offsetminutes(sb, user_id, tenantid)
    req = FakeRequest(token, user_id, docid, tenantid=ctx["tenantid"], projectid=ctx["projectid"])

    try:
        from utilsPrj.chapter_read import chapter_contents_read
        resp = chapter_contents_read(req, gendocuid, None, "doc", type)
        contents = resp.get("contents") or "작업된 항목이 없습니다."
        file_path = resp.get("file_path")
        file_name = resp.get("file_name")
        inmemoryyn = resp.get("inmemoryyn", False)
    except Exception as e:
        contents = f"오류: {e}"
        file_path = None
        file_name = None
        inmemoryyn = False

    # 문서 정보 (작성자, 작성일시, 업로더, 업로드일시)
    doc_info = {}
    try:
        gd = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("*").eq("gendocuid", gendocuid).execute().data
        if gd:
            d = gd[0]
            doc_info["gendocnm"] = d.get("gendocnm", "")
            doc_info["createfileurl"] = d.get("createfileurl")
            doc_info["updatefileurl"] = d.get("updatefileurl")
            doc_info["closeyn"] = bool(d.get("closeyn", False))
            # 작성자/업로더 이름
            for uid_field, nm_field, ts_field in [
                ("createuserid", "createuser", "createfiledts"),
                ("updateuserid", "updateuser", "updatefiledts"),
            ]:
                uid = d.get(uid_field)
                if uid:
                    nm, _ = get_usernm_email(sb, uid)
                    doc_info[nm_field] = nm
                    doc_info[ts_field] = _fmt(d.get(ts_field), offsetminutes)
    except Exception:
        pass

    return {
        "contents": contents,
        "file_path": file_path,
        "file_name": file_name,
        "inmemoryyn": inmemoryyn,
        "doc_info": doc_info,
        "type": type,
    }


# ── Chapter Content Read ─────────────────────────────────────────────────────────

@router.get("/genchapters/{genchapteruid}/content", dependencies=[Depends(require_doc_read)])
def get_chapter_content(
    genchapteruid: str,
    type: str = "auto",
    token: str = Depends(get_token),
    tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id, tenantid)
    docid = ctx["docid"]

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid").eq("genchapteruid", genchapteruid).execute().data
    gendocuid = genchap[0]["gendocuid"] if genchap else None

    req = FakeRequest(token, user_id, docid, tenantid=ctx["tenantid"], projectid=ctx["projectid"])

    try:
        from utilsPrj.chapter_read import chapter_contents_read
        resp = chapter_contents_read(req, gendocuid, genchapteruid, "chapter", type)
        contents = resp.get("contents") or "작업된 항목이 없습니다."
        file_path = resp.get("file_path")
        file_name = resp.get("file_name")
        inmemoryyn = resp.get("inmemoryyn", False)
    except Exception as e:
        contents = f"오류: {e}"
        file_path = None
        file_name = None
        inmemoryyn = False

    closeyn = False
    if gendocuid:
        gd = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("closeyn").eq("gendocuid", gendocuid).execute().data
        closeyn = bool(gd[0]["closeyn"]) if gd else False

    return {
        "contents": contents,
        "file_path": file_path,
        "file_name": file_name,
        "inmemoryyn": inmemoryyn,
        "closeyn": closeyn,
        "gendocuid": gendocuid,
        "genchapteruid": genchapteruid,
    }


# ── Chapter Rewrite (SQS 비동기) ─────────────────────────────────────────────────

class RewriteChapterRequest(BaseModel):
    projectid: Optional[int] = None
    tenantid: Optional[int] = None
    accountuid: Optional[str] = None


@router.post("/genchapters/{genchapteruid}/rewrite", dependencies=[Depends(require_doc_write)])
def rewrite_chapter(genchapteruid: str, body: RewriteChapterRequest = RewriteChapterRequest(), token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id, tenantid)

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid,chapteruid").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]
    chapteruid = genchap[0]["chapteruid"]

    docid_row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("docid,gendocnm").eq("gendocuid", gendocuid).execute().data
    docid = docid_row[0]["docid"] if docid_row else ctx.get("docid")
    gendocnm = docid_row[0].get("gendocnm", "") if docid_row else ""

    sb_svc = get_service_client()

    # 크레딧 체크 — 대상 챕터의 objects 건수 + 정산 대기 건수가 잔여 크레딧을 초과하면 차단
    credit_block = _check_credit_gate(sb, sb_svc, body.accountuid, [chapteruid])
    if credit_block:
        return credit_block

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    timeout = timedelta(hours=2)

    # Stale 잠금 해제
    genlocks = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("*").eq("gendocuid", gendocuid).execute().data or []
    for lock in genlocks:
        upd = {}
        if lock.get("doclocked") and lock.get("docstartdts"):
            start = datetime.fromisoformat(lock["docstartdts"].replace("Z", "+00:00"))
            if now_dt - start > timeout:
                upd["doclocked"] = False
                upd["docenddts"] = now_iso
        if lock.get("chapterlocked") and lock.get("chapterstartdts"):
            start = datetime.fromisoformat(lock["chapterstartdts"].replace("Z", "+00:00"))
            if now_dt - start > timeout:
                upd["chapterlocked"] = False
                upd["chapterenddts"] = now_iso
        if upd:
            sb.schema(SUPABASE_SCHEMA).table("genlocks").update(upd).eq("gendocuid", gendocuid).eq("genchapteruid", lock["genchapteruid"]).execute()

    # 잠금 중복 확인 — 문서 전체 잠금(genchapteruid="") 또는 이 챕터 자신의 잠금만 확인 (다른 챕터의 잠금은 무관)
    remaining_c = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).eq("genchapteruid", genchapteruid).execute().data or []
    remaining_d = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).eq("genchapteruid", "").execute().data or []
    if any(r.get("doclocked") or r.get("chapterlocked") for r in remaining_c + remaining_d):
        return {"locked": True, "message": "이 문서 혹은 해당 챕터가 이미 작성 중입니다."}

    # 챕터 잠금 선점
    sb.schema(SUPABASE_SCHEMA).table("genlocks").upsert({
        "gendocuid": gendocuid,
        "genchapteruid": genchapteruid,
        "doclocked": False,
        "chapterlocked": True,
        "docstartdts": None,
        "docenddts": None,
        "chapterstartdts": now_iso,
        "chapterenddts": None,
        "useruid": user_id,
    }, on_conflict="gendocuid,genchapteruid").execute()

    # genchapters_realtimes insert (처리 시작 상태) → genchapterjobuid 획득
    res = sb_svc.schema(SUPABASE_SCHEMA).table("genchapters_realtimes").insert({
        "genchapteruid": genchapteruid,
        "docid": docid,
        "chapteruid": chapteruid,
        "jobstatuscd": "S",
        "startdts": now_iso,
        "errorcd": None,
        "errormessage": None,
        "creator": user_id,
        "is_start_doc": False,
        "gendocjobuid": None,
    }).execute()
    genchapterjobuid = res.data[0]["genchapterjobuid"]
    sb_svc.schema(SUPABASE_SCHEMA).table("genchapters").update({
        "genchapterjobuid": genchapterjobuid,
    }).eq("genchapteruid", genchapteruid).execute()

    # SQS 메시지 전송
    sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
    sqs.send_message(
        QueueUrl=settings.SQS_CHAPTER_QUEUE_URL,
        MessageBody=json.dumps({
            "genchapteruid": genchapteruid,
            "genchapterjobuid": genchapterjobuid,
            "gendocuid": gendocuid,
            "gendocjobuid": None,  # 챕터 단독 작성 — gendocjobuid는 공백으로 둔다 (genobjects gencontenttypecd='C' 판정 근거)
            "chapteruid": chapteruid,
            "docid": docid,
            "tenantid": body.tenantid,
            "projectid": body.projectid,
            "accountuid": body.accountuid,
            "user_id": user_id,
            "access_token": token,
            "is_start_doc": False,
            "gendocnm": gendocnm,
        }, ensure_ascii=False),
    )

    return {"genchapteruid": genchapteruid}


@router.get("/genchapters/{genchapteruid}/rewrite/status", dependencies=[Depends(require_doc_read)])
def rewrite_chapter_status(genchapteruid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    genchap_check = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("genchapteruid,gendocuid").eq("genchapteruid", genchapteruid).execute().data
    if not genchap_check:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap_check[0]["gendocuid"]
    sb_svc = get_service_client()
    row = sb_svc.schema(SUPABASE_SCHEMA).table("genchapters_realtimes").select(
        "genchapterjobuid,jobstatuscd,errorcd,errormessage,startdts,chapteruid,creator,is_start_doc"
    ).eq("genchapteruid", genchapteruid).order("startdts", desc=True).limit(1).execute().data
    if not row:
        return {"JobStatusCD": None, "ErrorCD": None, "ErrorMessage": None}

    job_status = row[0]["jobstatuscd"]

    # S 상태 30분 초과 시 CRASH 자동 처리
    if job_status == "S" and row[0].get("startdts"):
        try:
            start = datetime.fromisoformat(row[0]["startdts"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - start > timedelta(minutes=30):
                now_iso = datetime.now(timezone.utc).isoformat()
                sb_svc.schema(SUPABASE_SCHEMA).table("genchapters_realtimes").update({
                    "jobstatuscd": "E",
                    "errorcd": "CRASH",
                    "errormessage": "Worker process terminated unexpectedly",
                    "enddts": now_iso,
                }).eq("genchapterjobuid", row[0]["genchapterjobuid"]).execute()
                sb_svc.schema(SUPABASE_SCHEMA).table("genlocks").update({
                    "chapterlocked": False,
                    "chapterenddts": now_iso,
                }).eq("genchapteruid", genchapteruid).execute()
                if not row[0].get("is_start_doc") and row[0].get("creator"):
                    _chap_nm_row = sb_svc.schema(SUPABASE_SCHEMA).table("chapters").select("chapternm").eq("chapteruid", row[0].get("chapteruid")).execute().data
                    _chapternm = _chap_nm_row[0]["chapternm"] if _chap_nm_row else ""
                    _gendoc_nm_row = sb_svc.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocnm").eq("gendocuid", gendocuid).execute().data
                    _gendocnm = _gendoc_nm_row[0]["gendocnm"] if _gendoc_nm_row else ""
                    create_notification(
                        sb_svc, category="chapter", status="error",
                        title="챕터 작성 실패", message=f"'{_gendocnm}' 문서의 '{_chapternm}' 챕터 작성 중 오류가 발생했습니다.",
                        title_key="msg.notification.chapter.failed.title", message_key="msg.notification.chapter.failed.body",
                        params={"gendocnm": _gendocnm, "chapternm": _chapternm},
                        target_object="gendoc", target_uid=gendocuid,
                        target_url=f"req/chapters-read?genchapteruid={genchapteruid}", target_useruid=row[0]["creator"],
                    )
                return {"JobStatusCD": "E", "ErrorCD": "CRASH", "ErrorMessage": "Worker process terminated unexpectedly"}
        except Exception:
            pass

    return {
        "JobStatusCD": row[0]["jobstatuscd"],
        "ErrorCD": row[0]["errorcd"],
        "ErrorMessage": row[0]["errormessage"],
    }


# ── Chapter File Upload ───────────────────────────────────────────────────────────

@router.post("/genchapters/{genchapteruid}/upload", dependencies=[Depends(require_doc_write)])
async def upload_chapter_file(
    genchapteruid: str,
    file: UploadFile = File(...),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid,updatefileurl").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]

    if genchap[0].get("updatefileurl"):
        old_url = genchap[0]["updatefileurl"]
        parsed = urlparse(old_url)
        prefix = "/storage/v1/object/public/sdoc/"
        if prefix in parsed.path:
            try:
                sb.storage.from_("sdoc").remove([parsed.path.split(prefix)[-1]])
            except Exception:
                pass

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "docx"
    path = f"result/{gendocuid}/chapters/{uuid.uuid4()}.{ext}"
    content = await file.read()
    sb.storage.from_("sdoc").upload(path, content, {"cacheControl": "3600", "upsert": "true"})
    public_url = sb.storage.from_("sdoc").get_public_url(path)
    now = datetime.now(timezone.utc).isoformat()

    sb.schema(SUPABASE_SCHEMA).table("genchapters").update({
        "updatefileurl": public_url,
        "updatefilenm": file.filename,
        "updatefiledts": now,
        "updateuserid": user_id,
    }).eq("genchapteruid", genchapteruid).execute()

    return {"success": True, "message": "업로드되었습니다.", "url": public_url}


# ── File Upload ──────────────────────────────────────────────────────────────────

@router.post("/{gendocuid}/upload", dependencies=[Depends(require_doc_write)])
async def upload_file(
    gendocuid: str,
    file: UploadFile = File(...),
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    old = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("updatefileurl,updatefilenm").eq("gendocuid", gendocuid).execute().data
    if old and old[0].get("updatefileurl"):
        parsed = urlparse(old[0]["updatefileurl"])
        prefix = "/storage/v1/object/public/sdoc/"
        if prefix in parsed.path:
            try:
                sb.storage.from_("sdoc").remove([parsed.path.split(prefix)[-1]])
            except Exception:
                pass

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "docx"
    path = f"result/{gendocuid}/{uuid.uuid4()}.{ext}"
    content = await file.read()
    sb.storage.from_("sdoc").upload(path, content, {"cacheControl": "3600", "upsert": "true"})
    public_url = sb.storage.from_("sdoc").get_public_url(path)
    now = datetime.now(timezone.utc).isoformat()

    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({
        "updatefileurl": public_url,
        "updatefilenm": file.filename,
        "updatefiledts": now,
        "updateuserid": user_id,
    }).eq("gendocuid", gendocuid).execute()

    return {"message": "업로드되었습니다.", "url": public_url}


# ── Generate (SQS) ───────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    results: list[dict]
    projectid: Optional[int] = None
    tenantid: Optional[int] = None
    accountuid: Optional[str] = None


@router.post("/{gendocuid}/generate", dependencies=[Depends(require_doc_write)])
def generate_doc(gendocuid: str, body: GenerateRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id, tenantid)
    docid = ctx["docid"]
    results = body.results

    gendoc_check = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocuid").eq("gendocuid", gendocuid).execute().data
    if not gendoc_check:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    sb_svc = get_service_client()

    # 크레딧 체크 — 대상 챕터들의 objects 건수 + 정산 대기 건수가 잔여 크레딧을 초과하면 차단
    credit_block = _check_credit_gate(sb, sb_svc, body.accountuid, _get_chapteruids_for_gendoc(sb, gendocuid))
    if credit_block:
        return credit_block

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    timeout = timedelta(hours=2)

    # 스테일 락 해제
    genlocks = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("*").eq("gendocuid", gendocuid).execute().data or []
    for lock in genlocks:
        upd = {}
        if lock.get("doclocked") and lock.get("docstartdts"):
            start = datetime.fromisoformat(lock["docstartdts"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if now_dt - start > timeout:
                upd["doclocked"] = False
                upd["docenddts"] = now_iso
        if lock.get("chapterlocked") and lock.get("chapterstartdts"):
            start = datetime.fromisoformat(lock["chapterstartdts"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if now_dt - start > timeout:
                upd["chapterlocked"] = False
                upd["chapterenddts"] = now_iso
        if upd:
            sb.schema(SUPABASE_SCHEMA).table("genlocks").update(upd).eq("gendocuid", gendocuid).eq("genchapteruid", lock["genchapteruid"]).execute()

    # 남은 락 확인
    genlocks = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).execute().data or []
    if any(r.get("doclocked") or r.get("chapterlocked") for r in genlocks):
        return {"locked": True, "message": "이 문서가 이미 작성 중입니다."}

    # 문서 락 설정
    sb.schema(SUPABASE_SCHEMA).table("genlocks").upsert({
        "gendocuid": gendocuid,
        "genchapteruid": "",
        "doclocked": True,
        "chapterlocked": False,
        "docstartdts": now_iso,
        "docenddts": None,
        "chapterstartdts": None,
        "chapterenddts": None,
        "useruid": user_id,
    }, on_conflict="gendocuid,genchapteruid").execute()

    # gendocnm 조회
    gendocnm_row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocnm").eq("gendocuid", gendocuid).execute().data
    gendocnm = gendocnm_row[0]["gendocnm"] if gendocnm_row else ""

    # 전체 문서 작성을 요청하는 시점에 "매개변수 변경으로 인한 재작업 필요" 표시를 해제한다
    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({"paramchangedyn": False}).eq("gendocuid", gendocuid).execute()

    # gendocs_realtimes insert (처리 시작 상태) → gendocjobuid 획득
    res = sb_svc.schema(SUPABASE_SCHEMA).table("gendocs_realtimes").insert({
        "gendocuid": gendocuid,
        "docid": docid,
        "gendocnm": gendocnm,
        "jobstatuscd": "S",
        "startdts": now_iso,
        "errorcd": None,
        "errormessage": None,
        "creator": user_id,
    }).execute()
    gendocjobuid = res.data[0]["gendocjobuid"]
    sb_svc.schema(SUPABASE_SCHEMA).table("gendocs").update({
        "gendocjobuid": gendocjobuid,
    }).eq("gendocuid", gendocuid).execute()

    # SQS 메시지 전송
    sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
    sqs.send_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MessageBody=json.dumps({
            "gendocuid": gendocuid,
            "gendocjobuid": gendocjobuid,
            "user_id": user_id,
            "access_token": token,
            "results": results,
            "docid": docid,
            "tenantid": body.tenantid,
            "projectid": body.projectid,
            "accountuid": body.accountuid,
            "gendocnm": gendocnm,
        }, ensure_ascii=False),
    )

    return {"gendocuid": gendocuid}


@router.get("/{gendocuid}/generate/status", dependencies=[Depends(require_doc_read)])
def generate_status(gendocuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    gendoc_check = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocuid").eq("gendocuid", gendocuid).execute().data
    if not gendoc_check:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    sb_svc = get_service_client()
    row = sb_svc.schema(SUPABASE_SCHEMA).table("gendocs_realtimes").select(
        "gendocjobuid,jobstatuscd,errorcd,errormessage,startdts,creator,gendocnm"
    ).eq("gendocuid", gendocuid).order("startdts", desc=True).limit(1).execute().data
    if not row:
        return {"JobStatusCD": None, "ErrorCD": None, "ErrorMessage": None}

    status = row[0]["jobstatuscd"]

    # S 상태가 30분 이상 지속되면 워커 비정상 종료로 판단 → E 자동 리셋 + 잠금 해제
    if status == "S" and row[0].get("startdts"):
        try:
            start = datetime.fromisoformat(row[0]["startdts"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - start > timedelta(minutes=30):
                now_iso = datetime.now(timezone.utc).isoformat()
                sb_svc.schema(SUPABASE_SCHEMA).table("gendocs_realtimes").update({
                    "jobstatuscd": "E",
                    "errorcd": "CRASH",
                    "errormessage": "Worker process terminated unexpectedly",
                    "enddts": now_iso,
                }).eq("gendocjobuid", row[0]["gendocjobuid"]).execute()
                sb_svc.schema(SUPABASE_SCHEMA).table("genlocks").update({
                    "doclocked": False,
                    "docenddts": now_iso,
                }).eq("gendocuid", gendocuid).eq("genchapteruid", "").execute()
                if row[0].get("creator"):
                    create_notification(
                        sb_svc, category="doc", status="error",
                        title="문서 작성 실패",
                        message=f"'{row[0].get('gendocnm') or ''}' 문서 작성 중 오류가 발생했습니다.",
                        title_key="msg.notification.doc.failed.title", message_key="msg.notification.doc.failed.body",
                        params={"gendocnm": row[0].get("gendocnm") or ""},
                        target_object="gendoc", target_uid=gendocuid, target_url="req/doc-read", target_useruid=row[0]["creator"],
                    )
                return {"JobStatusCD": "E", "ErrorCD": "CRASH", "ErrorMessage": "Worker process terminated unexpectedly"}
        except Exception:
            pass

    return {
        "JobStatusCD": status,
        "ErrorCD": row[0].get("errorcd"),
        "ErrorMessage": row[0].get("errormessage"),
    }


# ── Combine (SQS, 신규 생성 없이 이미 작성된 챕터만 병합) ─────────────────────────
# 문서 조합 작성 — 각 챕터의 작성본(create) 또는 업로드본(update) 중 선택된 그대로
# 순서대로 병합만 한다. LLM 재생성이 없으므로 크레딧 차감도 발생하지 않는다
# (worker의 _run_merge_and_upload가 신규 gendocjobuid에 연결된 genobjectlogs가 없으면
# apply_doc_credit_deduction에서 자연히 0건 차감으로 종료됨).

class CombineChapterItem(BaseModel):
    genchapteruid: str
    mode: str  # 'create'(작성본) | 'update'(업로드본)


class CombineRequest(BaseModel):
    chapters: list[CombineChapterItem]
    projectid: Optional[int] = None
    tenantid: Optional[int] = None
    accountuid: Optional[str] = None


@router.post("/{gendocuid}/combine", dependencies=[Depends(require_doc_write)])
def combine_doc(gendocuid: str, body: CombineRequest, token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id, tenantid)
    docid = ctx["docid"]

    gendoc_check = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocuid").eq("gendocuid", gendocuid).execute().data
    if not gendoc_check:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    if not body.chapters:
        return {"no_written_chapters": True, "message": "조합할 작성된 챕터가 없습니다."}

    sb_svc = get_service_client()

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    timeout = timedelta(hours=2)

    # 스테일 락 해제
    genlocks = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("*").eq("gendocuid", gendocuid).execute().data or []
    for lock in genlocks:
        upd = {}
        if lock.get("doclocked") and lock.get("docstartdts"):
            start = datetime.fromisoformat(lock["docstartdts"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if now_dt - start > timeout:
                upd["doclocked"] = False
                upd["docenddts"] = now_iso
        if lock.get("chapterlocked") and lock.get("chapterstartdts"):
            start = datetime.fromisoformat(lock["chapterstartdts"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if now_dt - start > timeout:
                upd["chapterlocked"] = False
                upd["chapterenddts"] = now_iso
        if upd:
            sb.schema(SUPABASE_SCHEMA).table("genlocks").update(upd).eq("gendocuid", gendocuid).eq("genchapteruid", lock["genchapteruid"]).execute()

    # 남은 락 확인
    genlocks = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).execute().data or []
    if any(r.get("doclocked") or r.get("chapterlocked") for r in genlocks):
        return {"locked": True, "message": "이 문서가 이미 작성 중입니다."}

    # 문서 락 설정
    sb.schema(SUPABASE_SCHEMA).table("genlocks").upsert({
        "gendocuid": gendocuid,
        "genchapteruid": "",
        "doclocked": True,
        "chapterlocked": False,
        "docstartdts": now_iso,
        "docenddts": None,
        "chapterstartdts": None,
        "chapterenddts": None,
        "useruid": user_id,
    }, on_conflict="gendocuid,genchapteruid").execute()

    gendocnm_row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("gendocnm").eq("gendocuid", gendocuid).execute().data
    gendocnm = gendocnm_row[0]["gendocnm"] if gendocnm_row else ""

    # gendocs_realtimes insert (처리 시작 상태) → gendocjobuid 획득
    res = sb_svc.schema(SUPABASE_SCHEMA).table("gendocs_realtimes").insert({
        "gendocuid": gendocuid,
        "docid": docid,
        "gendocnm": gendocnm,
        "jobstatuscd": "S",
        "startdts": now_iso,
        "errorcd": None,
        "errormessage": None,
        "creator": user_id,
    }).execute()
    gendocjobuid = res.data[0]["gendocjobuid"]
    sb_svc.schema(SUPABASE_SCHEMA).table("gendocs").update({
        "gendocjobuid": gendocjobuid,
    }).eq("gendocuid", gendocuid).execute()

    # SQS 메시지 전송 — combine_only=True: 워커가 Phase 1(fan-out/LLM 생성) 없이 Phase 2+3(병합/업로드)만 수행
    sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
    sqs.send_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MessageBody=json.dumps({
            "combine_only": True,
            "gendocuid": gendocuid,
            "gendocjobuid": gendocjobuid,
            "user_id": user_id,
            "access_token": token,
            "chapters": [c.model_dump() for c in body.chapters],
            "docid": docid,
            "tenantid": body.tenantid,
            "projectid": body.projectid,
            "accountuid": body.accountuid,
            "gendocnm": gendocnm,
        }, ensure_ascii=False),
    )

    return {"gendocuid": gendocuid}


# 2026-05-06 Min 헬퍼 함수 수정 >> 실제 데이터를 동작시켜서 내용 작성
def _build_context(sb, variables: list, req, docid) -> dict:
    """req_chapters_read.py의 _build_context와 동일"""
    from utilsPrj.process_data_ai import process_data_ai_preview
    context = {}
    for v in variables:
        find = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("datanm", v).eq("dfv_docid", docid).eq("datasourcecd", "dfv").execute().data
        if not find:
            continue
        sourcedatauid = find[0]['sourcedatauid']
        datas = process_data_ai_preview(sb, req, sourcedatauid, find[0]['gensentence'], docid=docid)
        df = datas.get("result")
        if df is not None and not df.empty:
            datacols = sb.schema(SUPABASE_SCHEMA).table("datacols").select("querycolnm,dispcolnm").eq("datauid", sourcedatauid).execute().data
            disp_to_query = {item["dispcolnm"]: item["querycolnm"] for item in datacols}
            enriched = []
            for rec in df.to_dict("records"):
                row = dict(rec)
                for disp, query in disp_to_query.items():
                    if disp in rec:
                        row[query] = rec[disp]
                enriched.append(row)
            context[f"@{v}"] = enriched
        else:
            import sys
            # print(f"[_build_context] @{v} 데이터 비어있음 (sourcedatauid={sourcedatauid})", file=sys.stderr)
    return context


def _convert_filterjson_to_querycolnm(sb, dfv_datauids: list, raw_params: dict) -> dict:
    if not raw_params or not dfv_datauids:
        return raw_params
    ofm_resp = sb.schema(SUPABASE_SCHEMA).table("objectfiltermaps") \
        .select("dfvcolnm, objectdatauid, objectdatacolnm") \
        .in_("dfvdatauid", dfv_datauids).execute()
    if not ofm_resp.data:
        return raw_params
    dfvcolnm_to_ofm = {}
    for r in ofm_resp.data:
        if r["dfvcolnm"] not in dfvcolnm_to_ofm:
            dfvcolnm_to_ofm[r["dfvcolnm"]] = r
    obj_datauids = list({r["objectdatauid"] for r in ofm_resp.data if r.get("objectdatauid")})
    src_uid_map = {}
    if obj_datauids:
        datas_resp = sb.schema(SUPABASE_SCHEMA).table("datas") \
            .select("datauid, sourcedatauid").in_("datauid", obj_datauids).execute()
        src_uid_map = {r["datauid"]: r.get("sourcedatauid") for r in (datas_resp.data or [])}
    source_uids = [v for v in src_uid_map.values() if v]
    dc_map = {}
    if source_uids:
        dc_resp = sb.schema(SUPABASE_SCHEMA).table("datacols") \
            .select("datauid, querycolnm, dispcolnm").in_("datauid", source_uids).execute()
        for c in (dc_resp.data or []):
            dc_map.setdefault(c["datauid"], {})[c["dispcolnm"]] = c["querycolnm"]
    converted = {}
    for k, v in raw_params.items():
        ofm = dfvcolnm_to_ofm.get(k)
        if not ofm:
            converted[k] = v
            continue
        obj_disp = ofm["objectdatacolnm"]
        src_uid = src_uid_map.get(ofm.get("objectdatauid"))
        disp_col_map = dc_map.get(src_uid, {}) if src_uid else {}
        query_col = disp_col_map.get(obj_disp, obj_disp)
        converted[query_col] = v
    return converted


_DOMAIN_TBL_MAP = {"CU": "charts", "TU": "tables", "SU": "sentences",
                   "CA": "charts", "TA": "tables", "SA": "sentences"}


def _upsert_genobjects(sb, extracted: list, genchapteruid: str, chapteruid: str, user_id: str, docid=None,
                        projectid=None, tenantid=None, accountuid=None,
                        gendocjobuid=None, genchapterjobuid=None):
    """req_chapters_read.py의 _upsert_genobjects와 동일"""
    now_iso = datetime.now(timezone.utc).isoformat()
    dfv_datauids = []
    if docid:
        dfv_rows = sb.schema(SUPABASE_SCHEMA).table("datas") \
            .select("datauid").eq("datasourcecd", "dfv").eq("dfv_docid", docid).execute().data
        dfv_datauids = [r["datauid"] for r in dfv_rows]

    # gencontenttypecd: 문서 전체 생성(D) > 챕터 단위 처리(C) > 단일 항목 재작성(O)
    # 문서 전체 작성 시에는 gendocjobuid+genchapterjobuid 둘 다 들어오므로 gendocjobuid를 먼저 판별해야
    # 문서/챕터 단독 생성이 구분된다(gendocjobuid 없이 genchapterjobuid만 있으면 챕터 단독 생성).
    if gendocjobuid:
        gencontenttypecd = "D"
    elif genchapterjobuid:
        gencontenttypecd = "C"
    else:
        gencontenttypecd = "O"

    rows = []
    for item in extracted:
        object_data = sb.schema(SUPABASE_SCHEMA).table("objects").select("*").eq("chapteruid", chapteruid).eq("objectnm", item["objectNm"]).execute().data
        if not object_data:
            continue
        objecttypecd = object_data[0].get("objecttypecd")
        objectuid = object_data[0]["objectuid"]
        filterjson = _convert_filterjson_to_querycolnm(sb, dfv_datauids, item["params"] or {})
        rows.append({
            "genobjectuid": str(uuid.uuid4()),
            "genchapteruid": genchapteruid,
            "chapteruid": chapteruid,
            "objectuid": object_data[0]["objectuid"],
            "objecttypecd": object_data[0].get("objecttypecd"),
            "filterjson": filterjson,
            "replacestring": item["replacestring"],
            "creator": user_id,
            "createdts": now_iso,
            "projectid": projectid,
            "tenantid": tenantid,
            "accountuid": accountuid,
            "gendocjobuid": gendocjobuid,
            "genchapterjobuid": genchapterjobuid,
            "gencontenttypecd": gencontenttypecd,
        })

    sb.schema(SUPABASE_SCHEMA).table("genobjects").delete().eq("genchapteruid", genchapteruid).execute()
    if rows:
        sb.schema(SUPABASE_SCHEMA).table("genobjects").insert(rows).execute()