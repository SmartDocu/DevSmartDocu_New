import os
import re
import uuid
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from backend.app.dependencies import get_token
from backend.app.schemas.auth import MessageResponse
from backend.app.schemas.docs import ChapterItem, ChapterSaveResponse, ChaptersListResponse
from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


def _get_user_id(token: str) -> str:
    sb = _sb(token)
    resp = sb.auth.get_user(token)
    if not resp or not resp.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    return str(resp.user.id)


# ─── 챕터 목록 ───────────────────────────────────────────────────────────────

@router.get("", response_model=ChaptersListResponse)
def list_chapters(docid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("chapters")
        .select("*")
        .eq("docid", docid)
        .order("chapterno")
        .execute()
        .data or []
    )
    return ChaptersListResponse(
        chapters=[
            ChapterItem(
                chapteruid=str(r["chapteruid"]),
                docid=r["docid"],
                chapternm=r.get("chapternm", ""),
                chapterno=r.get("chapterno", 0),
                useyn=r.get("useyn", True),
                chaptertemplatenm=r.get("chaptertemplatenm"),
                chaptertemplateurl=r.get("chaptertemplateurl"),
            )
            for r in rows
        ]
    )


# ─── 챕터 저장 (신규/수정) ────────────────────────────────────────────────────

@router.post("", response_model=ChapterSaveResponse)
async def save_chapter(
    docid: int = Form(...),
    chapternm: str = Form(...),
    chapterno: int = Form(...),
    useyn: bool = Form(True),
    chapteruid: Optional[str] = Form(None),
    templatefile: Optional[UploadFile] = File(None),
    token: str = Depends(get_token),
):
    user_id = _get_user_id(token)
    sb = _sb(token)

    existing = None
    if chapteruid:
        rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select("*").eq("chapteruid", chapteruid).execute().data
        existing = rows[0] if rows else None

    # useyn 활성화 시 항목 수 제한 확인
    if existing and useyn and not existing.get("useyn", False):
        configs = sb.schema(SUPABASE_SCHEMA).table("configs").select("freeobjectcnt").execute().data or []
        freeobjectcnt = configs[0]["freeobjectcnt"] if configs else 999

        doc_data = (
            sb.schema(SUPABASE_SCHEMA)
            .rpc("fn_doc_count__r", {"p_docid": docid, "p_chapteruid": chapteruid})
            .execute()
            .data or []
        )
        object_cnt = doc_data[0].get("object_cnt", 0) if doc_data else 0
        chapter_objs = (
            sb.schema(SUPABASE_SCHEMA)
            .table("objects")
            .select("objectuid")
            .eq("useyn", True)
            .eq("chapteruid", chapteruid)
            .execute()
            .data or []
        )
        if object_cnt + len(chapter_objs) > freeobjectcnt:
            raise HTTPException(
                status_code=405,
                detail=f"항목 설정 최대 사용량 {freeobjectcnt}을 초과하였습니다.",
            )

    record: dict = {
        "docid": docid,
        "chapternm": chapternm,
        "chapterno": chapterno,
        "useyn": useyn,
    }

    if templatefile and templatefile.filename:
        if existing and existing.get("chaptertemplateurl"):
            _delete_storage_file(sb, existing["chaptertemplateurl"])

        ext = os.path.splitext(templatefile.filename)[1]
        path = f"template/chaptertemplate/{uuid.uuid4()}{ext}"
        content = await templatefile.read()
        sb.storage.from_("smartdoc").upload(path, content, {"content-type": templatefile.content_type})
        record["chaptertemplatenm"] = templatefile.filename
        record["chaptertemplateurl"] = sb.storage.from_("smartdoc").get_public_url(path).split("?")[0]

    try:
        if existing:
            res = sb.schema(SUPABASE_SCHEMA).table("chapters").update(record).eq("chapteruid", chapteruid).execute()
            return ChapterSaveResponse(result="success", chapteruid=str(res.data[0]["chapteruid"]))
        else:
            record["creator"] = user_id
            res = sb.schema(SUPABASE_SCHEMA).table("chapters").insert(record).execute()
            return ChapterSaveResponse(result="success", chapteruid=str(res.data[0]["chapteruid"]))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 챕터 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{chapteruid}", response_model=MessageResponse)
def delete_chapter(chapteruid: str, token: str = Depends(get_token)):
    sb = _sb(token)

    rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select("*").eq("chapteruid", chapteruid).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    chapter = rows[0]

    if chapter.get("chaptertemplateurl"):
        _delete_storage_file(sb, chapter["chaptertemplateurl"])

    res = sb.schema(SUPABASE_SCHEMA).table("chapters").delete().eq("chapteruid", chapteruid).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="챕터 삭제 실패.")

    return MessageResponse(ok=True, message="챕터가 삭제되었습니다.")


# ══════════════════════════════════════════════════════
#  챕터 템플릿 에디터
# ══════════════════════════════════════════════════════

class TemplateSaveRequest(BaseModel):
    texttemplate: str
    formats: List[Dict[str, Any]]  # [{objectUID, objectNm, orderno, filters: {docvariableuid, params}}]


@router.get("/{chapteruid}/template")
def get_chapter_template(chapteruid: str, token: str = Depends(get_token)):
    import json as _json
    sb = _sb(token)
    ch_rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select("*").eq("chapteruid", chapteruid).execute().data
    if not ch_rows:
        raise HTTPException(status_code=404, detail="챕터를 찾을 수 없습니다.")
    chapter = ch_rows[0]
    docid = chapter.get("docid")

    obj_rows = sb.schema(SUPABASE_SCHEMA).table("objects").select("*").eq("chapteruid", chapteruid).order("orderno").execute().data or []

    # tbl_params / sca_params (docvariables 테이블)
    tbl_rows = []
    sca_rows = []
    if docid:
        raw_tbl = sb.schema(SUPABASE_SCHEMA).table("docvariables").select("*").eq("docid", docid).eq("variabletypecd", "DataSet").execute().data or []
        raw_sca = sb.schema(SUPABASE_SCHEMA).table("docvariables").select("*").eq("docid", docid).eq("variabletypecd", "Value").execute().data or []

        seen = set()
        for item in raw_tbl:
            nm = item.get("variablenm", "")
            if nm and nm not in seen:
                seen.add(nm)
                cols = item.get("dispcolnmjson")
                if isinstance(cols, str):
                    try:
                        cols = _json.loads(cols)
                    except Exception:
                        cols = [c.strip() for c in cols.replace("[", "").replace("]", "").replace('"', "").split(",") if c.strip()]
                tbl_rows.append({"docvariableuid": item.get("docvariableuid"), "paramnm": nm, "columns": cols or []})

        seen2 = set()
        for item in raw_sca:
            nm = item.get("variablenm", "")
            if nm and nm not in seen2:
                seen2.add(nm)
                sca_rows.append({"docvariableuid": item.get("docvariableuid"), "paramnm": nm, "columns": item.get("dispcolnmjson")})

    return {
        "chapter": {
            "chapteruid": chapter["chapteruid"],
            "chapternm": chapter.get("chapternm", ""),
            "texttemplate": chapter.get("texttemplate") or "",
            "docid": docid,
            "editbuttonyn": chapter.get("editbuttonyn", "Y"),
        },
        "objects": obj_rows,
        "tbl_params": tbl_rows,
        "sca_params": sca_rows,
    }


@router.post("/{chapteruid}/template")
def save_chapter_template(chapteruid: str, body: TemplateSaveRequest, token: str = Depends(get_token)):
    sb_user = _sb(token)
    user_id = _get_user_id(token)
    from utilsPrj.supabase_client import get_service_client
    sb_svc = get_service_client()

    # 사용자 billingmodelcd (무료 플랜 제한)
    user_info = sb_svc.schema(SUPABASE_SCHEMA).table("users").select("billingmodelcd").eq("useruid", user_id).execute().data
    billingmodelcd = user_info[0]["billingmodelcd"] if user_info else ""

    # page-break 정규화
    pagebreak = '<p>&nbsp;</p><div class="page-break" style="page-break-after:always;"><span style="display:none;">&nbsp;</span></div>'
    html = body.texttemplate
    if pagebreak not in html:
        html = html.replace(
            '<div class="page-break" style="page-break-after:always;"><span style="display:none;">&nbsp;</span></div>',
            pagebreak,
        )

    # 1. texttemplate 저장
    sb_user.schema(SUPABASE_SCHEMA).table("chapters").update({"texttemplate": html}).eq("chapteruid", chapteruid).execute()

    # 2. 무료 플랜 항목 수 제한 체크
    if billingmodelcd == "Fr":
        cfg = sb_svc.schema(SUPABASE_SCHEMA).table("configs").select("freeobjectcnt").execute().data
        freeobjectcnt = cfg[0]["freeobjectcnt"] if cfg else 0
        ch_row = sb_svc.schema(SUPABASE_SCHEMA).table("chapters").select("docid").eq("chapteruid", chapteruid).execute().data
        docid = ch_row[0]["docid"] if ch_row else None
        if docid:
            cnt_data = sb_svc.schema(SUPABASE_SCHEMA).rpc("fn_doc_count__r", {"p_docid": docid, "p_chapteruid": chapteruid}).execute().data
            object_cnt = cnt_data[0].get("object_cnt", 0) if cnt_data else 0
            if object_cnt + len(body.formats) > freeobjectcnt:
                return {
                    "ok": False,
                    "message": f"항목 설정 최대 사용량 {freeobjectcnt}을 초과하였습니다.",
                    "add": "템플릿은 정상 저장되었습니다.",
                }

    # 3. objects 동기화
    existing = sb_svc.schema(SUPABASE_SCHEMA).table("objects").select("objectuid,objectnm").eq("chapteruid", chapteruid).execute().data or []
    new_nms = {f["objectNm"] for f in body.formats if f.get("objectNm")}
    to_del = [o["objectuid"] for o in existing if o["objectnm"] not in new_nms]
    if to_del:
        sb_svc.schema(SUPABASE_SCHEMA).table("objects").delete().in_("objectuid", to_del).execute()

    import json as _json
    for idx, f in enumerate(body.formats):
        objectuid = f.get("objectUID") or str(uuid.uuid4())
        filters_raw = f.get("filters") or {}
        docvariableuid = filters_raw.get("docvariableuid") if filters_raw else None
        params = filters_raw.get("params", []) if filters_raw else []
        filters_json = _json.dumps(params, ensure_ascii=False) if params else None
        sb_svc.schema(SUPABASE_SCHEMA).table("objects").upsert({
            "chapteruid": chapteruid,
            "objectuid": objectuid,
            "objectnm": f["objectNm"],
            "useyn": True,
            "orderno": f.get("orderno", idx + 1),
            "creator": user_id,
            "filters": filters_json,
            "docvariableuid": docvariableuid,
        }).execute()

    return {"ok": True}


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _delete_storage_file(sb, url: str):
    try:
        parsed = urlparse(url)
        prefix = "/storage/v1/object/public/smartdoc/"
        if prefix in parsed.path:
            path = parsed.path.split(prefix)[-1]
            sb.storage.from_("smartdoc").remove([path])
    except Exception:
        pass
