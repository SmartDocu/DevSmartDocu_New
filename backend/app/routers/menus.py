from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_optional_token, get_token
from backend.app.config import settings
from utilsPrj.supabase_client import get_thread_supabase, get_service_client, SUPABASE_SCHEMA

router = APIRouter()


@router.get("")
def list_menus():
    """sdoc.menus 전체 목록 (useyn=true, orderno 정렬). 인증 불요."""
    try:
        sb = get_service_client()
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("menus")
            .select("*")
            .eq("useyn", True)
            .order("orderno")
            .execute()
            .data
        )
        return {"menus": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/favorites")
def list_favorites(token: str = Depends(get_token)):
    """로그인 유저의 즐겨찾기 목록."""
    try:
        sb = get_thread_supabase(access_token=token)
        user = sb.auth.get_user(token)
        useruid = user.user.id

        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("favorites")
            .select("menucd, orderno")
            .eq("useruid", useruid)
            .order("orderno")
            .execute()
            .data
        )
        return {"favorites": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/favorites/{menucd}")
def toggle_favorite(menucd: str, token: str = Depends(get_token)):
    """즐겨찾기 토글 — 없으면 추가, 있으면 삭제."""
    try:
        sb = get_thread_supabase(access_token=token)
        user = sb.auth.get_user(token)
        useruid = user.user.id

        existing = (
            sb.schema(SUPABASE_SCHEMA)
            .table("favorites")
            .select("menucd")
            .eq("useruid", useruid)
            .eq("menucd", menucd)
            .execute()
            .data
        )

        if existing:
            sb.schema(SUPABASE_SCHEMA).table("favorites").delete().eq("useruid", useruid).eq("menucd", menucd).execute()
            return {"action": "removed", "menucd": menucd}
        else:
            # orderno: 기존 즐겨찾기 수 + 1
            count_rows = (
                sb.schema(SUPABASE_SCHEMA)
                .table("favorites")
                .select("menucd", count="exact")
                .eq("useruid", useruid)
                .execute()
            )
            orderno = (count_rows.count or 0) + 1
            sb.schema(SUPABASE_SCHEMA).table("favorites").insert({
                "useruid": useruid,
                "menucd": menucd,
                "orderno": orderno,
                "creator": useruid,
            }).execute()
            return {"action": "added", "menucd": menucd}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
