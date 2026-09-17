from fastapi import APIRouter, HTTPException, Request

from backend.app.utils import get_client_ip, get_country_code
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

router = APIRouter()

# 활성 언어(ko/en/ja) 기준 국가코드 → 언어코드 매핑. 매핑에 없는 국가는 en.
_COUNTRY_LANG_MAP = {"KR": "ko", "JP": "ja"}


@router.get("/geo-language")
def get_geo_language(request: Request):
    """접속 IP의 국가코드로 추정 언어를 반환한다 (비로그인 최초 방문자 기본 언어 추정용). 인증 불요."""
    ip = get_client_ip(request)
    countrycd = get_country_code(ip)
    languagecd = _COUNTRY_LANG_MAP.get(countrycd, "en")
    return {"languagecd": languagecd, "countrycd": countrycd}


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
    def _fetch_all(query_fn):
        rows, offset, batch = [], 0, 1000
        while True:
            r = query_fn(offset, offset + batch - 1).execute()
            rows.extend(r.data or [])
            if len(r.data or []) < batch:
                break
            offset += batch
        return rows

    try:
        sb = get_service_client()
        sd = sb.schema(SUPABASE_SCHEMA)

        # ui_terms → defaults dict (언어 무관)
        terms_rows = _fetch_all(
            lambda s, e: sd.table("ui_terms").select("term_key,default_text").range(s, e)
        )
        defaults = {
            row["term_key"]: row["default_text"]
            for row in terms_rows
            if row.get("term_key")
        }

        # ui_term_translations[lang_cd] → translations dict (언어 전용만)
        trans_rows = _fetch_all(
            lambda s, e: sd.table("ui_term_translations")
            .select("term_key,translated_text")
            .eq("language_cd", lang_cd)
            .range(s, e)
        )
        translations = {
            row["term_key"]: row["translated_text"]
            for row in trans_rows
            if row.get("term_key") and row.get("translated_text")
        }

        return {"translations": translations, "defaults": defaults}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
