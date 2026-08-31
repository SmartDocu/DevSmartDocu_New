from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_user as _get_user, get_sb as _sb
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()


class AppItem(BaseModel):
    appcd: str
    appnm: Optional[str] = None
    iconurl: Optional[str] = None
    desc: Optional[str] = None
    useyn: Optional[bool] = True
    orderno: Optional[int] = None
    rolecd: Optional[str] = None
    routepath: Optional[str] = None
    servicecd: Optional[str] = None


class AppsListResponse(BaseModel):
    apps: list[AppItem]
    subscribed_servicecds: list[str] = []


class AppTranslationItem(BaseModel):
    appcd: str
    languagecd: str
    translated_text: Optional[str] = None


class AppTranslationsListResponse(BaseModel):
    translations: list[AppTranslationItem]


class AppTranslationSaveRequest(BaseModel):
    languagecd: str
    translated_text: Optional[str] = None


class WarmLlmRequest(BaseModel):
    tenantid: Optional[str] = None
    account_uid: Optional[str] = None


@router.get("", response_model=AppsListResponse)
def list_apps(token: str = Depends(get_token), tenantid: Optional[str] = None, languagecd: Optional[str] = None):
    try:
        sb = _sb(token)
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("apps")
            .select("appcd, appnm, iconurl, desc, useyn, orderno, rolecd, routepath, servicecd")
            .eq("useyn", True)
            .order("orderno")
            .execute()
            .data or []
        )

        # languagecd가 주어지면 app_translations에서 번역명으로 appnm을 대체 (없으면 원본 appnm 유지)
        if languagecd:
            trans_rows = (
                sb.schema(SUPABASE_SCHEMA)
                .table("app_translations")
                .select("appcd, translated_text")
                .eq("languagecd", languagecd)
                .execute()
                .data or []
            )
            trans_map = {r["appcd"]: r["translated_text"] for r in trans_rows if r.get("translated_text")}
            for r in rows:
                if r["appcd"] in trans_map:
                    r["appnm"] = trans_map[r["appcd"]]

        subscribed_servicecds = []
        if tenantid:
            user_resp = sb.auth.get_user(token)
            if user_resp and user_resp.user:
                user_id = str(user_resp.user.id)
                subs = (
                    sb.schema(SUPABASE_SCHEMA)
                    .table("serviceusers")
                    .select("servicecd")
                    .eq("useruid", user_id)
                    .eq("tenantid", tenantid)
                    .eq("useyn", True)
                    .execute()
                    .data or []
                )
                subscribed_servicecds = list({s["servicecd"] for s in subs if s.get("servicecd")})

        return AppsListResponse(
            apps=[AppItem(**r) for r in rows],
            subscribed_servicecds=subscribed_servicecds,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 앱 이름 번역 (system.i18n.apps 관리 화면) ────────────────────────────────

@router.get("/{appcd}/translations", response_model=AppTranslationsListResponse)
def list_app_translations(appcd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("app_translations")
        .select("appcd, languagecd, translated_text")
        .eq("appcd", appcd)
        .order("languagecd")
        .execute()
        .data or []
    )
    return AppTranslationsListResponse(translations=[AppTranslationItem(**r) for r in rows])


@router.post("/{appcd}/translations")
def save_app_translation(appcd: str, body: AppTranslationSaveRequest, token: str = Depends(get_token)):
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
        sb.schema(SUPABASE_SCHEMA).table("app_translations")
        .select("appcd")
        .eq("appcd", appcd)
        .eq("languagecd", body.languagecd)
        .execute()
        .data
    )

    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("app_translations").update({
                "translated_text": body.translated_text,
            }).eq("appcd", appcd).eq("languagecd", body.languagecd).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("app_translations").insert({
                "appcd": appcd,
                "languagecd": body.languagecd,
                "translated_text": body.translated_text,
                "creator": user_id,
            }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


@router.delete("/{appcd}/translations/{languagecd}")
def delete_app_translation(appcd: str, languagecd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("app_translations").delete().eq("appcd", appcd).eq("languagecd", languagecd).execute()
    return {"ok": True}


# ─── LLM 미리 인증(warm-up) — 메뉴에서 앱을 고른 시점에 한 번만 인증받아 캐싱해두고,
# 실제 문서 작성/보고서 생성 시에는 그 결과를 재사용한다(2026-08-31, d2doc/d2insight가
# 항목·모듈마다 매번 재인증하던 문제 확인 후 도입). ────────────────────────────────

@router.post("/{appcd}/warm-llm")
def warm_llm(appcd: str, body: WarmLlmRequest, token: str = Depends(get_token)):
    """appcd에 대응하는 servicecd로 LLM을 미리 인증·캐싱한다(utilsPrj.ai_chain.get_llm_clients).
    실패해도 화면 흐름을 막지 않는다 — 실제 사용 시점에 다시 시도되므로 여기선 조용히 넘어간다."""
    user = _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("apps").select("servicecd")
        .eq("appcd", appcd).execute().data or []
    )
    service_code = rows[0].get("servicecd") if rows else None
    if not service_code:
        return {"ok": False, "reason": "servicecd 없음"}

    from utilsPrj.ai_chain import get_llm_clients
    try:
        get_llm_clients(
            project_id=None, tenant_id=body.tenantid, user_uid=str(user.id),
            account_uid=body.account_uid, service_code=service_code,
        )
        return {"ok": True, "service_code": service_code}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
