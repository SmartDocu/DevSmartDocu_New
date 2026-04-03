# app/routers/settings.py
from fastapi import APIRouter
# DB 관련 주석 처리
# from app.core.supabase_client import get_admin_client
from app.core.config import config
import app.core.settings as settings

router = APIRouter(prefix="/settings")

@router.get("/max-tabs")
async def get_max_tabs():
    """
    DB 없을 때 기본값 반환
    """
    # DB 호출 주석 처리
    # client = get_admin_client()
    # resp = (
    #     client.schema(config.DB_SCHEMA)
    #     .table("configs")
    #     .select("maxtabs")
    #     .single()
    #     .execute()
    # )
    # max_tabs = int(resp.data["maxtabs"]) if resp.data else settings.DEFAULT_MAX_TABS

    max_tabs = settings.DEFAULT_MAX_TABS
    return {"maxTabs": max_tabs}


@router.get("/default-lang")
async def get_default_lang(user_id: str = None):
    """
    사용자별 기본 언어 반환
    user_id 없으면 시스템 기본값 반환
    """
    if not user_id:
        return {"defaultLang": settings.DEFAULT_LANG}

    # DB 호출 주석 처리
    # client = get_admin_client()
    # user_resp = (
    #     client.schema(config.DB_SCHEMA)
    #     .table("users")
    #     .select("lang")
    #     .eq("id", user_id)
    #     .single()
    #     .execute()
    # )
    # return {"defaultLang": settings.get_user_default_lang(user_resp.data)}

    return {"defaultLang": settings.DEFAULT_LANG}


@router.get("/menu")
async def get_menu(user_id: str = None):
    """
    로그인 상태, 권한에 따라 메뉴 반환
    - user_id 없으면 guest
    """
    print("user_id:", user_id)  # 🔥 확인용

    is_logged_in = bool(user_id)
    user_role = None

    # DB 호출 주석 처리
    # if user_id:
    #     client = get_admin_client()
    #     user_resp = (
    #         client.schema(config.DB_SCHEMA)
    #         .table("users")
    #         .select("role")
    #         .eq("id", user_id)
    #         .single()
    #         .execute()
    #     )
    #     user_role = user_resp.data.get("role") if user_resp.data else None

    menu = settings.filter_menu_for_role(settings.MENU_STRUCTURE, user_role, is_logged_in)
    return {"menu": menu}