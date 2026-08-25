from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_optional_token, get_token, get_sb as _sb, get_user as _get_user
from backend.app.schemas.popups import (
    PopupAdminItem, PopupsAdminListResponse, PopupSaveRequest, PopupSaveResponse,
    PopupTranslationItem, PopupTranslationsListResponse, PopupTranslationSaveRequest,
)
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

router = APIRouter()


def _svc():
    return get_service_client()


# ─── 공개: 노출 대상 팝업 목록 ─────────────────────────────────────────────────

@router.get("")
def list_popups(
    mainlogin: Optional[str] = None,
    token: Optional[str] = Depends(get_optional_token),
):
    """활성 팝업 목록. 로그인 사용자는 비활성화된 팝업 자동 제외."""
    sb = _svc()
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()

    q = (
        sb.schema(SUPABASE_SCHEMA).table("popups")
        .select(
            "popupid, title, content_type, pageurl, body, button_text, button_url, "
            "width, height, lefts, top, deactivateday, mainlogin"
        )
        .eq("useyn", True)
        .lte("startdts", now)
        .gte("enddts", now)
    )
    if mainlogin:
        q = q.eq("mainlogin", mainlogin)

    rows = q.execute().data or []
    if not rows:
        return {"popups": []}

    deactivated_ids: set[int] = set()
    if token:
        try:
            user = _get_user(token)
            popup_ids = [r["popupid"] for r in rows]
            deact = (
                sb.schema(SUPABASE_SCHEMA).table("popupdeactivates")
                .select("popupid")
                .in_("popupid", popup_ids)
                .eq("useruid", str(user.id))
                .gte("enddt", today)
                .execute().data or []
            )
            deactivated_ids = {r["popupid"] for r in deact}
        except Exception:
            pass

    visible = [r for r in rows if r["popupid"] not in deactivated_ids]

    # 언어별 번역 오버라이드 — 프론트에서 langCd로 골라 쓰고, 없으면 base(title/body/button_text) 사용
    trans_map: dict[int, dict] = {}
    if visible:
        trans_rows = (
            sb.schema(SUPABASE_SCHEMA).table("popup_translations")
            .select("popupid, languagecd, title, body, button_text")
            .in_("popupid", [r["popupid"] for r in visible])
            .execute().data or []
        )
        for t in trans_rows:
            trans_map.setdefault(t["popupid"], {})[t["languagecd"]] = {
                "title": t.get("title"), "body": t.get("body"), "button_text": t.get("button_text"),
            }
    for r in visible:
        r["translations"] = trans_map.get(r["popupid"], {})

    return {"popups": visible}


@router.post("/{popupid}/deactivate")
def deactivate_popup(
    popupid: int,
    token: str = Depends(get_token),
):
    """n일간 보지 않기 — popupdeactivates 기록."""
    sb_user = _sb(token)
    user = _get_user(token)
    uid = str(user.id)

    popup = (
        sb_user.schema(SUPABASE_SCHEMA).table("popups")
        .select("popupid, deactivateday")
        .eq("popupid", popupid)
        .maybe_single()
        .execute().data
    )
    if not popup:
        raise HTTPException(status_code=404, detail="팝업을 찾을 수 없습니다.")

    enddt = (datetime.now(timezone.utc).date() + timedelta(days=popup.get("deactivateday") or 7)).isoformat()

    existing = (
        sb_user.schema(SUPABASE_SCHEMA).table("popupdeactivates")
        .select("popupdeactivateuid")
        .eq("popupid", popupid)
        .eq("useruid", uid)
        .execute().data or []
    )

    if existing:
        (
            sb_user.schema(SUPABASE_SCHEMA).table("popupdeactivates")
            .update({"enddt": enddt})
            .eq("popupdeactivateuid", existing[0]["popupdeactivateuid"])
            .execute()
        )
    else:
        (
            sb_user.schema(SUPABASE_SCHEMA).table("popupdeactivates")
            .insert({"popupid": popupid, "useruid": uid, "enddt": enddt, "creator": uid})
            .execute()
        )

    return {"ok": True}


# ─── 관리자: 전체 목록 ─────────────────────────────────────────────────────────

@router.get("/admin", response_model=PopupsAdminListResponse)
def list_popups_admin(token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("popups")
        .select("*")
        .order("createdts", desc=True)
        .execute().data or []
    )
    return PopupsAdminListResponse(popups=[PopupAdminItem(**r) for r in rows])


# ─── 관리자: 생성 ──────────────────────────────────────────────────────────────

@router.post("", response_model=PopupSaveResponse)
def create_popup(body: PopupSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)

    record = {**body.model_dump(), "creator": str(user.id)}
    try:
        resp = sb.schema(SUPABASE_SCHEMA).table("popups").insert(record).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")
    if not resp.data:
        raise HTTPException(status_code=500, detail="팝업 저장에 실패했습니다.")
    return PopupSaveResponse(result="success", popupid=resp.data[0]["popupid"])


# ─── 관리자: 수정 ──────────────────────────────────────────────────────────────

@router.put("/{popupid}", response_model=PopupSaveResponse)
def update_popup(popupid: int, body: PopupSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("popups").select("popupid").eq("popupid", popupid).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="팝업을 찾을 수 없습니다.")

    try:
        sb.schema(SUPABASE_SCHEMA).table("popups").update(body.model_dump()).eq("popupid", popupid).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")
    return PopupSaveResponse(result="success", popupid=popupid)


# ─── 관리자: 삭제 ──────────────────────────────────────────────────────────────

@router.delete("/{popupid}")
def delete_popup(popupid: int, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("popups").select("popupid").eq("popupid", popupid).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="팝업을 찾을 수 없습니다.")

    sb.schema(SUPABASE_SCHEMA).table("popup_translations").delete().eq("popupid", popupid).execute()
    sb.schema(SUPABASE_SCHEMA).table("popupdeactivates").delete().eq("popupid", popupid).execute()
    sb.schema(SUPABASE_SCHEMA).table("popups").delete().eq("popupid", popupid).execute()
    return {"ok": True, "message": "팝업이 삭제되었습니다."}


# ─── 관리자: 번역 목록 ─────────────────────────────────────────────────────────

@router.get("/{popupid}/translations", response_model=PopupTranslationsListResponse)
def list_popup_translations(popupid: int, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("popup_translations")
        .select("popupid, languagecd, title, body, button_text")
        .eq("popupid", popupid)
        .order("languagecd")
        .execute().data or []
    )
    return PopupTranslationsListResponse(translations=[PopupTranslationItem(**r) for r in rows])


# ─── 관리자: 번역 저장 ─────────────────────────────────────────────────────────

@router.post("/{popupid}/translations")
def save_popup_translation(popupid: int, body: PopupTranslationSaveRequest, token: str = Depends(get_token)):
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
        sb.schema(SUPABASE_SCHEMA).table("popup_translations")
        .select("popupid")
        .eq("popupid", popupid).eq("languagecd", body.languagecd)
        .execute().data
    )

    payload = {"title": body.title, "body": body.body, "button_text": body.button_text}
    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("popup_translations").update(payload).eq(
                "popupid", popupid
            ).eq("languagecd", body.languagecd).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("popup_translations").insert({
                "popupid": popupid, "languagecd": body.languagecd, **payload, "creator": user_id,
            }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 관리자: 번역 삭제 ─────────────────────────────────────────────────────────

@router.delete("/{popupid}/translations/{languagecd}")
def delete_popup_translation(popupid: int, languagecd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("popup_translations").delete().eq(
        "popupid", popupid
    ).eq("languagecd", languagecd).execute()
    return {"ok": True}
