from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_optional_token, get_token, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

router = APIRouter()


def _svc():
    return get_service_client()


@router.get("")
def list_popups(
    mainlogin: Optional[str] = None,
    token: Optional[str] = Depends(get_optional_token),
):
    """활성 팝업 목록. 로그인 사용자는 비활성화된 팝업 자동 제외."""
    sb = _svc()
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    q = (
        sb.schema(SUPABASE_SCHEMA).table("popups")
        .select("popupid, title, pageurl, width, height, lefts, top, deactivateday, mainlogin")
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

    return {"popups": [r for r in rows if r["popupid"] not in deactivated_ids]}


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

    enddt = (date.today() + timedelta(days=popup.get("deactivateday") or 7)).isoformat()

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
