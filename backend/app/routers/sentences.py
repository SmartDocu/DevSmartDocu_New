from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()


class SentenceSaveRequest(BaseModel):
    objectuid: str
    chapteruid: str
    objectnm: str
    datauid: str
    sentencestext: Optional[str] = None


class SentencePreviewRequest(BaseModel):
    chapteruid: str
    objectnm: str
    selected_datauid: str
    docid: Optional[int] = None
    template_text: str


@router.get("")
def get_sentence(chapteruid: str, objectnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("sentences")
        .select("datauid, sentencestext")
        .eq("chapteruid", chapteruid).eq("objectnm", objectnm)
        .execute().data or []
    )
    if not rows:
        return {"sentence": None}
    return {"sentence": rows[0]}


@router.post("")
def save_sentence(body: SentenceSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)
    now = datetime.now().isoformat()

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("sentences")
        .select("datauid")
        .eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm)
        .execute().data
    )

    if existing:
        sb.schema(SUPABASE_SCHEMA).table("sentences").update({
            "objectuid": body.objectuid,
            "datauid": body.datauid,
            "sentencestext": body.sentencestext,
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
        sb.schema(SUPABASE_SCHEMA).table("objects").update({
            "modifier": user_id, "modifydts": now
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
    else:
        sb.schema(SUPABASE_SCHEMA).table("sentences").insert({
            "objectuid": body.objectuid,
            "chapteruid": body.chapteruid,
            "objectnm": body.objectnm,
            "datauid": body.datauid,
            "sentencestext": body.sentencestext,
            "creator": user_id,
            "gentypecd": "UI",
        }).execute()
        sb.schema(SUPABASE_SCHEMA).table("objects").update({
            "objectsettingyn": True, "modifydts": now, "modifier": user_id,
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()

    return {"message": "저장되었습니다."}


@router.delete("")
def delete_sentence(chapteruid: str, objectnm: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("sentences").delete().eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
    sb.schema(SUPABASE_SCHEMA).table("objects").update({"objectsettingyn": False}).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
    return {"message": "삭제되었습니다."}


@router.post("/preview")
def preview_sentence(body: SentencePreviewRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)

    from utilsPrj.process_data import process_data, apply_column_display_mapping
    from utilsPrj.sentences_utils import draw_sentences

    class _FakeRequest:
        def __init__(self, access_token: str):
            self.session = {"access_token": access_token, "refresh_token": None}
            self.method = "GET"

    try:
        req = _FakeRequest(token)
        df = process_data(req, datauid=body.selected_datauid, docid=body.docid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 처리 오류: {e}")

    raw_columns = df.columns.tolist()
    raw_rows = df.head(15).values.tolist()
    _, dict_rows = apply_column_display_mapping(body.selected_datauid, raw_columns, raw_rows, sb)

    try:
        result = draw_sentences(req, sb, dict_rows, body.template_text, body.selected_datauid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문장 변환 오류: {e}")

    return {"result": result}
