from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from backend.app.schemas.terms import (
    TermItem, TermsListResponse, TermSaveRequest, TermSaveResponse,
    TranslationItem, TranslationsListResponse, TranslationSaveRequest,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()




# ─── 관리자 전체 목록 ─────────────────────────────────────────────────────────

@router.get("/admin", response_model=TermsListResponse)
def list_terms_admin(token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("terms")
        .select("*")
        .order("termkey")
        .execute()
        .data or []
    )
    return TermsListResponse(terms=[TermItem(**r) for r in rows])


# ─── 용어 생성 ───────────────────────────────────────────────────────────────

@router.post("", response_model=TermSaveResponse)
def create_term(body: TermSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("terms")
        .select("termkey").eq("termkey", body.termkey).execute().data
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 용어 키입니다: {body.termkey}")

    record = {
        "termkey": body.termkey,
        "termgroupcd": body.termgroupcd,
        "default_text": body.default_text,
        "description": body.description,
        "useyn": body.useyn,
        "creator": user_id,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("terms").insert(record).execute()
        return TermSaveResponse(result="success", termkey=body.termkey)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 용어 수정 ───────────────────────────────────────────────────────────────

@router.put("/{termkey}", response_model=TermSaveResponse)
def update_term(termkey: str, body: TermSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("terms")
        .select("termkey").eq("termkey", termkey).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="용어를 찾을 수 없습니다.")

    record = {
        "termgroupcd": body.termgroupcd,
        "default_text": body.default_text,
        "description": body.description,
        "useyn": body.useyn,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("terms").update(record).eq("termkey", termkey).execute()
        return TermSaveResponse(result="success", termkey=termkey)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 용어 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{termkey}")
def delete_term(termkey: str, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("terms")
        .select("termkey").eq("termkey", termkey).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="용어를 찾을 수 없습니다.")

    sb.schema(SUPABASE_SCHEMA).table("term_translations").delete().eq("termkey", termkey).execute()
    sb.schema(SUPABASE_SCHEMA).table("terms").delete().eq("termkey", termkey).execute()
    return {"ok": True, "message": "용어가 삭제되었습니다."}


# ─── 번역 목록 ───────────────────────────────────────────────────────────────

@router.get("/{termkey}/translations", response_model=TranslationsListResponse)
def list_translations(termkey: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("term_translations")
        .select("termkey, languagecd, translated_text")
        .eq("termkey", termkey)
        .order("languagecd")
        .execute()
        .data or []
    )
    return TranslationsListResponse(translations=[TranslationItem(**r) for r in rows])


# ─── 번역 저장 (upsert) ──────────────────────────────────────────────────────

@router.post("/{termkey}/translations")
def save_translation(termkey: str, body: TranslationSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    if not body.languagecd:
        raise HTTPException(status_code=400, detail="languagecd가 필요합니다.")

    lang_check = (
        sb.schema(SUPABASE_SCHEMA).table("languages")
        .select("languagecd").eq("languagecd", body.languagecd).execute().data
    )
    if not lang_check:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 언어 코드입니다: {body.languagecd}")

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("term_translations")
        .select("termkey")
        .eq("termkey", termkey)
        .eq("languagecd", body.languagecd)
        .execute()
        .data
    )

    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("term_translations").update({
                "translated_text": body.translated_text,
            }).eq("termkey", termkey).eq("languagecd", body.languagecd).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("term_translations").insert({
                "termkey": termkey,
                "languagecd": body.languagecd,
                "translated_text": body.translated_text,
                "creator": user_id,
            }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 번역 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{termkey}/translations/{languagecd}")
def delete_translation(termkey: str, languagecd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("term_translations").delete().eq("termkey", termkey).eq("languagecd", languagecd).execute()
    return {"ok": True}
