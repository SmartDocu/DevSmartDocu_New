# app/api/i18n.py
from fastapi import APIRouter
from app.core.supabase_client import get_admin_client
from app.core.config import config

router = APIRouter(prefix="/i18n")


@router.get("/terms")
async def get_translations(lang: str = None):
    """
    로그인 여부와 상관없이 접근 가능
    """
    lang = lang or config.DEFAULT_LANG

    client = get_admin_client()  # 서비스 키 사용, RLS 무시

    # 원본 용어 가져오기
    terms_resp = (
        client.schema(config.DB_SCHEMA)
        .table("ui_terms")
        .select("term_key, term_group, default_text")
        .eq("is_active", True)
        .execute()
    )
    terms = terms_resp.data

    # 번역 가져오기
    trans_resp = (
        client.schema(config.DB_SCHEMA)
        .table("ui_term_translations")
        .select("term_key, translated_text")
        .eq("language_cd", lang)
        .execute()
    )
    translations = {t["term_key"]: t["translated_text"] for t in trans_resp.data}

    # 최종 매핑
    result = {t["term_key"]: translations.get(t["term_key"], t["default_text"]) for t in terms}

    return result