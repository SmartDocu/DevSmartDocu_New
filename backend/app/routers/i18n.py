from fastapi import APIRouter, HTTPException

from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

router = APIRouter()


@router.get("/languages")
def list_languages():
    """sdoc.languages 목록 반환 (useyn=true, orderno 정렬). 인증 불요."""
    try:
        sb = get_service_client()
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("languages")
            .select("languagecd,languagenm,orderno")
            .eq("useyn", True)
            .order("orderno")
            .execute()
            .data
        )
        return {"languages": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translations/{lang_cd}")
def get_translations(lang_cd: str):
    """번역 정보 반환. 인증 불요.

    응답:
    - translations: ui_term_translations[lang_cd] 만 (언어 전용)
    - defaults:     ui_terms.default_text (언어 무관 기본값)

    프론트 우선순위: translations[key] → defaults[key] → key 그대로
    """
    try:
        sb = get_service_client()
        sd = sb.schema(SUPABASE_SCHEMA)

        # ui_terms → defaults dict (언어 무관)
        terms_rows = sd.table("ui_terms").select("term_key,default_text").execute().data or []
        defaults = {
            row["term_key"]: row["default_text"]
            for row in terms_rows
            if row.get("term_key")
        }

        # ui_term_translations[lang_cd] → translations dict (언어 전용만)
        trans_rows = (
            sd.table("ui_term_translations")
            .select("term_key,translated_text")
            .eq("language_cd", lang_cd)
            .execute()
            .data
        ) or []
        translations = {
            row["term_key"]: row["translated_text"]
            for row in trans_rows
            if row.get("term_key") and row.get("translated_text")
        }

        return {"translations": translations, "defaults": defaults}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
