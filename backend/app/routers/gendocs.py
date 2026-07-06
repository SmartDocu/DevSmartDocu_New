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
from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()


def _get_docid(sb, user_id: str) -> Optional[int]:
    row = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("mydocid").eq("useruid", user_id).execute().data
    docid = row[0].get("mydocid") if row else None
    return int(docid) if docid else None


def _get_user_context(sb, user_id: str) -> dict:
    """docid → projectid → tenantid 순으로 조회하여 LLM 모델 선택에 필요한 컨텍스트 반환"""
    docid = tenantid = projectid = None
    try:
        row = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select("mydocid").eq("useruid", user_id).execute().data
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
                tenantid = proj_row[0]["tenantid"]
    except Exception:
        pass

    return {"docid": docid, "tenantid": tenantid, "projectid": projectid}


def _get_offsetminutes(sb, user_id: str) -> Optional[int]:
    try:
        tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id).maybe_single().execute()
        if not tu.data:
            return None
        tz = tu.data.get("timezone")
        if not tz and tu.data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu.data["tenantid"]).maybe_single().execute()
            if t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row.data else None
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

@router.get("")
def list_gendocs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    docid: Optional[int] = None,
    search_by: Optional[str] = "Doc",
    docgroupid: Optional[int] = None,
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    if not docid:
        docid = _get_docid(sb, str(user.id))
    if not docid:
        return {"gendocs": [], "docnm": None, "dataparams": []}

    today = datetime.now().date()
    sd = start_date or (today - timedelta(days=10)).strftime("%Y-%m-%d")
    ed = end_date or today.strftime("%Y-%m-%d")
    offsetminutes = _get_offsetminutes(sb, str(user.id))

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

    for item in rows:
        item["createfiledts"] = _fmt(item.get("createfiledts"), offsetminutes)
        item["closedts"] = _fmt(item.get("closedts"), offsetminutes)
        item["createdts"] = _fmt(item.get("createdts"), offsetminutes)
        # params
        params = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs_params__r", {"p_gendocuid": item["gendocuid"]}).execute().data or []
        item["params"] = params
        item["finalnm_joined"] = " / ".join(p.get("finalnm") or p.get("paramvalue") or "" for p in params if p.get("paramvalue"))

    docparams = sb.schema(SUPABASE_SCHEMA).table("docparams").select("*").eq("docid", docid).order("orderno").execute().data or []

    return {"gendocs": rows, "docnm": docnm, "dataparams": docparams, "docid": docid}


# ── Gendoc Detail ───────────────────────────────────────────────────────────────

@router.get("/dataparams")
def get_dataparams(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    ctx = _get_user_context(sb, str(user.id))
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


@router.get("/{gendocuid}/status")
def get_gendoc_status(gendocuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    status_rows = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendoc_status__r", {"p_gendocuid": gendocuid}).execute().data or []
    gendoc = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs__r", {"p_gendocuid": gendocuid}).execute().data or []
    offsetminutes = _get_offsetminutes(sb, str(user.id))

    for i in status_rows:
        i["createfiledts"] = _fmt(i.get("createfiledts"), offsetminutes)
        i["updatefiledts"] = _fmt(i.get("updatefiledts"), offsetminutes)

    gendocnm = gendoc[0]["gendocnm"] if gendoc else ""
    createfiledts = _fmt(gendoc[0].get("createfiledts"), offsetminutes) if gendoc else ""
    return {"status": status_rows, "gendocnm": gendocnm, "createfiledts": createfiledts}


@router.get("/{gendocuid}/chapters")
def get_genchapters(gendocuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id))
    chapters = sb.schema(SUPABASE_SCHEMA).rpc("fn_genchapters__r_gendocuid", {"p_gendocuid": gendocuid}).execute().data or []
    for c in chapters:
        c["createfiledts"] = _fmt(c.get("createfiledts"), offsetminutes)
        c["updatefiledts"] = _fmt(c.get("updatefiledts"), offsetminutes)
    gendoc = sb.schema(SUPABASE_SCHEMA).rpc("fn_gendocs__r", {"p_gendocuid": gendocuid}).execute().data or []
    gendoc_info = gendoc[0] if gendoc else {}
    gendoc_info["createfiledts"] = _fmt(gendoc_info.get("createfiledts"), offsetminutes)
    gendoc_info["updatefiledts"] = _fmt(gendoc_info.get("updatefiledts"), offsetminutes)
    finaldts_raw = gendoc_info.get("finaldts")
    formatted_finaldts = _fmt(finaldts_raw, offsetminutes)
    gendoc_info["finaldts"] = "" if formatted_finaldts == "00-01-01 00:00" else formatted_finaldts
    return {"chapters": chapters, "gendoc": gendoc_info}


# ── Gendoc Create ───────────────────────────────────────────────────────────────

class GendocCreateRequest(BaseModel):
    docid: int
    docnm: str
    params: list[dict]
    projectid: Optional[int] = None
    tenantid: Optional[int] = None
    accountuid: Optional[str] = None


@router.post("")
def create_gendoc(body: GendocCreateRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now().isoformat()

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

@router.delete("/{gendocuid}")
def delete_gendoc(gendocuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    # Remove storage file
    row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("createfileurl").eq("gendocuid", gendocuid).execute().data
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

@router.post("/{gendocuid}/close")
def close_gendoc(gendocuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now(timezone.utc).isoformat()

    row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("docid").eq("gendocuid", gendocuid).execute().data
    if not row:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
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


@router.post("/{gendocuid}/open")
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


@router.post("/params/update")
def update_gendoc_params(body: GendocUpdateRequest, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({"gendocnm": body.gendocnm}).eq("gendocuid", body.gendocuid).execute()
    for p in body.params:
        sb.schema(SUPABASE_SCHEMA).table("gendoc_params").update({"paramvalue": p.get("paramvalue")}).eq("gendocuid", body.gendocuid).eq("paramuid", p.get("paramuid")).execute()
    return {"message": "파라미터가 변경되었습니다."}


# ── Params Check ─────────────────────────────────────────────────────────────────

class ParamsCheckRequest(BaseModel):
    docid: int
    params: list[dict]


@router.post("/params/check")
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

@router.post("/check-objects")
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

@router.get("/genchapters/{genchapteruid}/objects")
def get_chapter_objects(genchapteruid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id))

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid,chapteruid,docid,createfiledts").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]
    chapteruid = genchap[0]["chapteruid"]
    docid = genchap[0].get("docid")
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
        obj_rows = sb.schema(SUPABASE_SCHEMA).table("objects").select("objectnm,objectdesc,objecttypecd,orderno,createdts").eq("objectuid", go["objectuid"]).execute().data
        if not obj_rows:
            continue
        obj = obj_rows[0]
        typecd = go.get("objecttypecd") or obj.get("objecttypecd")
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
            "new_objectyn": False,
            "new_genobjectyn": not bool(go.get("resulttext")),
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


@router.post("/genchapters/{genchapteruid}/objects/{objectuid}/rewrite")
def rewrite_object(genchapteruid: str, objectuid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id)
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
    """단일 항목 재작성(gencontenttypecd='O') 1회당 genobjectcounts에 시간당(1시간 버킷) 사용량 1건 집계"""
    try:
        row = sb.schema(SUPABASE_SCHEMA).table("genobjects").select("accountuid,tenantid") \
            .eq("genchapteruid", genchapteruid).eq("objectuid", objectuid).execute().data
        if not row or not row[0].get("accountuid") or row[0].get("tenantid") is None:
            return
        accountuid = row[0]["accountuid"]
        tenantid = row[0]["tenantid"]

        now = datetime.now(timezone.utc)
        usedts = now.replace(minute=0, second=0, microsecond=0).isoformat()
        now_iso = now.isoformat()

        sb_svc = get_service_client()
        existing = sb_svc.schema(SUPABASE_SCHEMA).table("genobjectcounts").select("countuid,count") \
            .eq("accountuid", accountuid).eq("tenantid", tenantid).eq("usedts", usedts).execute().data
        if existing:
            sb_svc.schema(SUPABASE_SCHEMA).table("genobjectcounts").update({
                "count": existing[0]["count"] + 1,
                "updatedts": now_iso,
            }).eq("countuid", existing[0]["countuid"]).execute()
        else:
            sb_svc.schema(SUPABASE_SCHEMA).table("genobjectcounts").insert({
                "countuid": str(uuid.uuid4()),
                "usedts": usedts,
                "accountuid": accountuid,
                "tenantid": tenantid,
                "count": 1,
                "updatedts": now_iso,
            }).execute()
    except Exception:
        pass


# ── Apply Objects to Chapter ─────────────────────────────────────────────────────

@router.post("/genchapters/{genchapteruid}/apply")
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

    now = datetime.now().isoformat()

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

@router.get("/{gendocuid}/doc-content")
def get_doc_content(
    gendocuid: str,
    type: str = "auto",
    token: str = Depends(get_token),
):
    """전체 문서 HTML 내용 반환 (sep='doc') — Django chapter_read?sep=doc 에 해당"""
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id)
    docid = ctx["docid"]
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
                    try:
                        u = sb.schema("public").table("users").select("full_name").eq("useruid", uid).maybe_single().execute()
                        doc_info[nm_field] = u.data.get("full_name", "") if u.data else ""
                    except Exception:
                        doc_info[nm_field] = ""
                    ts = d.get(ts_field)
                    if ts:
                        try:
                            from dateutil import parser as dp
                            doc_info[ts_field] = dp.parse(ts).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            doc_info[ts_field] = ts
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

@router.get("/genchapters/{genchapteruid}/content")
def get_chapter_content(
    genchapteruid: str,
    type: str = "auto",
    token: str = Depends(get_token),
):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id)
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


@router.post("/genchapters/{genchapteruid}/rewrite")
def rewrite_chapter(genchapteruid: str, body: RewriteChapterRequest = RewriteChapterRequest(), token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id)

    genchap = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("gendocuid,chapteruid").eq("genchapteruid", genchapteruid).execute().data
    if not genchap:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    gendocuid = genchap[0]["gendocuid"]
    chapteruid = genchap[0]["chapteruid"]

    docid_row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("docid,gendocjobuid").eq("gendocuid", gendocuid).execute().data
    docid = docid_row[0]["docid"] if docid_row else ctx.get("docid")
    doc_gendocjobuid = docid_row[0]["gendocjobuid"] if docid_row else None

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

    # 잠금 중복 확인
    remaining = sb.schema(SUPABASE_SCHEMA).table("genlocks").select("doclocked,chapterlocked").eq("gendocuid", gendocuid).execute().data or []
    if any(r.get("doclocked") or r.get("chapterlocked") for r in remaining):
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
    sb_svc = get_service_client()
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
            "gendocjobuid": doc_gendocjobuid,
            "chapteruid": chapteruid,
            "docid": docid,
            "tenantid": body.tenantid,
            "projectid": body.projectid,
            "accountuid": body.accountuid,
            "user_id": user_id,
            "access_token": token,
            "is_start_doc": False,
        }, ensure_ascii=False),
    )

    return {"genchapteruid": genchapteruid}


@router.get("/genchapters/{genchapteruid}/rewrite/status")
def rewrite_chapter_status(genchapteruid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb_svc = get_service_client()
    row = sb_svc.schema(SUPABASE_SCHEMA).table("genchapters_realtimes").select(
        "genchapterjobuid,jobstatuscd,errorcd,errormessage,startdts,chapteruid"
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
                return {"JobStatusCD": "E", "ErrorCD": "CRASH", "ErrorMessage": "Worker process terminated unexpectedly"}
        except Exception:
            pass

    return {
        "JobStatusCD": row[0]["jobstatuscd"],
        "ErrorCD": row[0]["errorcd"],
        "ErrorMessage": row[0]["errormessage"],
    }


# ── Chapter File Upload ───────────────────────────────────────────────────────────

@router.post("/genchapters/{genchapteruid}/upload")
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
    now = datetime.now().isoformat()

    sb.schema(SUPABASE_SCHEMA).table("genchapters").update({
        "updatefileurl": public_url,
        "updatefilenm": file.filename,
        "updatefiledts": now,
        "updateuserid": user_id,
    }).eq("genchapteruid", genchapteruid).execute()

    docid_row = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("docid").eq("gendocuid", gendocuid).execute().data
    if docid_row:
        sb.schema(SUPABASE_SCHEMA).table("loguploads").insert({
            "objecttypenm": "C",
            "docid": docid_row[0]["docid"],
            "gendocuid": gendocuid,
            "genchapteruid": genchapteruid,
            "updatefileurl": public_url,
            "updatefilenm": file.filename,
            "updatefiledts": now,
            "updateuserid": user_id,
        }).execute()

    return {"success": True, "message": "업로드되었습니다.", "url": public_url}


# ── File Upload ──────────────────────────────────────────────────────────────────

@router.post("/{gendocuid}/upload")
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
    now = datetime.now().isoformat()

    sb.schema(SUPABASE_SCHEMA).table("gendocs").update({
        "updatefileurl": public_url,
        "updatefilenm": file.filename,
        "updatefiledts": now,
        "updateuserid": user_id,
    }).eq("gendocuid", gendocuid).execute()

    docid = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("docid").eq("gendocuid", gendocuid).execute().data
    if docid:
        sb.schema(SUPABASE_SCHEMA).table("loguploads").insert({
            "objecttypenm": "D",
            "docid": docid[0]["docid"],
            "gendocuid": gendocuid,
            "updatefileurl": public_url,
            "updatefilenm": file.filename,
            "updatefiledts": now,
            "updateuserid": user_id,
        }).execute()

    return {"message": "업로드되었습니다.", "url": public_url}


# ── Generate (SQS) ───────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    results: list[dict]
    projectid: Optional[int] = None
    tenantid: Optional[int] = None
    accountuid: Optional[str] = None


@router.post("/{gendocuid}/generate")
def generate_doc(gendocuid: str, body: GenerateRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    ctx = _get_user_context(sb, user_id)
    docid = ctx["docid"]
    results = body.results

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

    # gendocs_realtimes insert (처리 시작 상태) → gendocjobuid 획득
    sb_svc = get_service_client()
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


@router.get("/{gendocuid}/generate/status")
def generate_status(gendocuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb_svc = get_service_client()
    row = sb_svc.schema(SUPABASE_SCHEMA).table("gendocs_realtimes").select(
        "gendocjobuid,jobstatuscd,errorcd,errormessage,startdts"
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
                return {"JobStatusCD": "E", "ErrorCD": "CRASH", "ErrorMessage": "Worker process terminated unexpectedly"}
        except Exception:
            pass

    return {
        "JobStatusCD": status,
        "ErrorCD": row[0].get("errorcd"),
        "ErrorMessage": row[0].get("errormessage"),
    }


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
            print(f"[_build_context] @{v} 데이터 비어있음 (sourcedatauid={sourcedatauid})", file=sys.stderr)
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

    # gencontenttypecd: 챕터 단위 처리(C) > 문서 전체 생성(D) > 단일 항목 재작성(O)
    # 문서 전체 작성 시에도 챕터별로 genchapterjobuid가 함께 부여되므로 genchapterjobuid를 먼저 판별한다
    if genchapterjobuid:
        gencontenttypecd = "C"
    elif gendocjobuid:
        gencontenttypecd = "D"
    else:
        gencontenttypecd = "O"

    rows = []
    for item in extracted:
        object_data = sb.schema(SUPABASE_SCHEMA).table("objects").select("*").eq("objectnm", item["objectNm"]).execute().data
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