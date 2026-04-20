from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_token
from backend.app.schemas.menus import (
    MenuItem, MenusListResponse, MenuSaveRequest, MenuSaveResponse,
    TranslationItem, TranslationsListResponse, TranslationSaveRequest,
    LanguageItem, LanguagesListResponse,
)
from utilsPrj.supabase_client import get_thread_supabase, get_service_client, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


def _get_user(token: str):
    sb = _sb(token)
    resp = sb.auth.get_user(token)
    if not resp or not resp.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    return resp.user


# ─── 공개 목록 (useyn=true, 사이드바용) ──────────────────────────────────────

@router.get("", response_model=MenusListResponse)
def list_menus():
    try:
        sb = get_service_client()
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("menus")
            .select("*")
            .eq("useyn", True)
            .order("orderno")
            .execute()
            .data or []
        )
        return MenusListResponse(menus=[MenuItem(**r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 관리자 전체 목록 (useyn 무관) ───────────────────────────────────────────

@router.get("/admin", response_model=MenusListResponse)
def list_menus_admin(token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("menus")
        .select("*")
        .order("orderno")
        .execute()
        .data or []
    )
    return MenusListResponse(menus=[MenuItem(**r) for r in rows])


# ─── 언어 목록 ───────────────────────────────────────────────────────────────

@router.get("/languages", response_model=LanguagesListResponse)
def list_languages(token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("languages")
        .select("languagecd, languagenm, useyn, orderno")
        .eq("useyn", True)
        .order("orderno")
        .execute()
        .data or []
    )
    return LanguagesListResponse(languages=[LanguageItem(**r) for r in rows])


# ─── 즐겨찾기 ────────────────────────────────────────────────────────────────

@router.get("/favorites")
def list_favorites(token: str = Depends(get_token)):
    sb = _sb(token)
    user = _get_user(token)
    useruid = str(user.id)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("favorites")
        .select("menucd, orderno")
        .eq("useruid", useruid)
        .order("orderno")
        .execute()
        .data or []
    )
    return {"favorites": rows}


@router.post("/favorites/{menucd}")
def toggle_favorite(menucd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    user = _get_user(token)
    useruid = str(user.id)

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


# ─── 메뉴 생성 ───────────────────────────────────────────────────────────────

@router.post("", response_model=MenuSaveResponse)
def create_menu(body: MenuSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("menus")
        .select("menucd").eq("menucd", body.menucd).execute().data
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 메뉴 코드입니다: {body.menucd}")

    record = {
        "menucd": body.menucd,
        "default_text": body.default_text,
        "description": body.description,
        "iconnm": body.iconnm,
        "orderno": body.orderno,
        "useyn": body.useyn,
        "rolecd": body.rolecd,
        "route_path": body.route_path,
        "creator": user_id,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("menus").insert(record).execute()
        return MenuSaveResponse(result="success", menucd=body.menucd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 메뉴 수정 ───────────────────────────────────────────────────────────────

@router.put("/{menucd}", response_model=MenuSaveResponse)
def update_menu(menucd: str, body: MenuSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("menus")
        .select("menucd").eq("menucd", menucd).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")

    record = {
        "default_text": body.default_text,
        "description": body.description,
        "iconnm": body.iconnm,
        "orderno": body.orderno,
        "useyn": body.useyn,
        "rolecd": body.rolecd,
        "route_path": body.route_path,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("menus").update(record).eq("menucd", menucd).execute()
        return MenuSaveResponse(result="success", menucd=menucd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 메뉴 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{menucd}")
def delete_menu(menucd: str, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("menus")
        .select("menucd").eq("menucd", menucd).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")

    sb.schema(SUPABASE_SCHEMA).table("menu_translations").delete().eq("menucd", menucd).execute()
    sb.schema(SUPABASE_SCHEMA).table("menus").delete().eq("menucd", menucd).execute()
    return {"ok": True, "message": "메뉴가 삭제되었습니다."}


# ─── 번역 목록 ───────────────────────────────────────────────────────────────

@router.get("/{menucd}/translations", response_model=TranslationsListResponse)
def list_translations(menucd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("menu_translations")
        .select("menucd, languagecd, translated_text")
        .eq("menucd", menucd)
        .order("languagecd")
        .execute()
        .data or []
    )
    return TranslationsListResponse(translations=[TranslationItem(**r) for r in rows])


# ─── 번역 저장 (upsert) ──────────────────────────────────────────────────────

@router.post("/{menucd}/translations")
def save_translation(menucd: str, body: TranslationSaveRequest, token: str = Depends(get_token)):
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
        sb.schema(SUPABASE_SCHEMA).table("menu_translations")
        .select("menucd")
        .eq("menucd", menucd)
        .eq("languagecd", body.languagecd)
        .execute()
        .data
    )

    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("menu_translations").update({
                "translated_text": body.translated_text,
            }).eq("menucd", menucd).eq("languagecd", body.languagecd).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("menu_translations").insert({
                "menucd": menucd,
                "languagecd": body.languagecd,
                "translated_text": body.translated_text,
                "creator": user_id,
            }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 번역 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{menucd}/translations/{languagecd}")
def delete_translation(menucd: str, languagecd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("menu_translations").delete().eq("menucd", menucd).eq("languagecd", languagecd).execute()
    return {"ok": True}
