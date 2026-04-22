from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from backend.app.schemas.menus import CodeItem, CodesListResponse
from backend.app.schemas.codes import (
    CodeAdminItem, CodesAdminListResponse,
    CodeSaveRequest, CodeSaveResponse,
    CodeTranslationItem, CodeTranslationsListResponse, CodeTranslationSaveRequest,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()




# ─── 공용 유틸: 코드그룹별 목록 ──────────────────────────────────────────────

@router.get("", response_model=CodesListResponse)
def list_codes(codegroupcd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("codes")
        .select("codegroupcd, codevalue, default_name, orderno")
        .eq("codegroupcd", codegroupcd)
        .eq("useyn", True)
        .order("orderno")
        .execute()
        .data or []
    )
    codes = [
        CodeItem(
            codevalue=r["codevalue"],
            term_key=f"cod.{r['codegroupcd']}_{r['codevalue']}",
            default_name=r.get("default_name"),
        )
        for r in rows
    ]
    return CodesListResponse(codes=codes)


# ─── 관리자 전체 목록 ─────────────────────────────────────────────────────────

@router.get("/admin", response_model=CodesAdminListResponse)
def list_codes_admin(token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("codes")
        .select("*")
        .order("codegroupcd")
        .order("orderno")
        .execute()
        .data or []
    )
    return CodesAdminListResponse(codes=[CodeAdminItem(**r) for r in rows])


# ─── 코드 생성 ───────────────────────────────────────────────────────────────

@router.post("", response_model=CodeSaveResponse)
def create_code(body: CodeSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("codes")
        .select("codegroupcd")
        .eq("codegroupcd", body.codegroupcd)
        .eq("codevalue", body.codevalue)
        .execute().data
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 코드입니다: {body.codegroupcd} / {body.codevalue}")

    record = {
        "codegroupcd": body.codegroupcd,
        "codevalue": body.codevalue,
        "default_name": body.default_name,
        "orderno": body.orderno,
        "useyn": body.useyn,
        "creator": user_id,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("codes").insert(record).execute()
        return CodeSaveResponse(result="success", codegroupcd=body.codegroupcd, codevalue=body.codevalue)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 코드 수정 ───────────────────────────────────────────────────────────────

@router.put("/{codegroupcd}/{codevalue}", response_model=CodeSaveResponse)
def update_code(codegroupcd: str, codevalue: str, body: CodeSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("codes")
        .select("codegroupcd")
        .eq("codegroupcd", codegroupcd)
        .eq("codevalue", codevalue)
        .execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="코드를 찾을 수 없습니다.")

    record = {
        "default_name": body.default_name,
        "orderno": body.orderno,
        "useyn": body.useyn,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("codes").update(record).eq("codegroupcd", codegroupcd).eq("codevalue", codevalue).execute()
        return CodeSaveResponse(result="success", codegroupcd=codegroupcd, codevalue=codevalue)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 코드 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{codegroupcd}/{codevalue}")
def delete_code(codegroupcd: str, codevalue: str, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("codes")
        .select("codegroupcd")
        .eq("codegroupcd", codegroupcd)
        .eq("codevalue", codevalue)
        .execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="코드를 찾을 수 없습니다.")

    sb.schema(SUPABASE_SCHEMA).table("code_translations").delete().eq("codegroupcd", codegroupcd).eq("codevalue", codevalue).execute()
    sb.schema(SUPABASE_SCHEMA).table("codes").delete().eq("codegroupcd", codegroupcd).eq("codevalue", codevalue).execute()
    return {"ok": True, "message": "코드가 삭제되었습니다."}


# ─── 번역 목록 ───────────────────────────────────────────────────────────────

@router.get("/{codegroupcd}/{codevalue}/translations", response_model=CodeTranslationsListResponse)
def list_code_translations(codegroupcd: str, codevalue: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("code_translations")
        .select("codegroupcd, codevalue, languagecd, translated_text, translated_desc")
        .eq("codegroupcd", codegroupcd)
        .eq("codevalue", codevalue)
        .order("languagecd")
        .execute()
        .data or []
    )
    return CodeTranslationsListResponse(translations=[CodeTranslationItem(**r) for r in rows])


# ─── 번역 저장 (upsert) ──────────────────────────────────────────────────────

@router.post("/{codegroupcd}/{codevalue}/translations")
def save_code_translation(codegroupcd: str, codevalue: str, body: CodeTranslationSaveRequest, token: str = Depends(get_token)):
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
        sb.schema(SUPABASE_SCHEMA).table("code_translations")
        .select("codegroupcd")
        .eq("codegroupcd", codegroupcd)
        .eq("codevalue", codevalue)
        .eq("languagecd", body.languagecd)
        .execute().data
    )

    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("code_translations").update({
                "translated_text": body.translated_text,
                "translated_desc": body.translated_desc,
            }).eq("codegroupcd", codegroupcd).eq("codevalue", codevalue).eq("languagecd", body.languagecd).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("code_translations").insert({
                "codegroupcd": codegroupcd,
                "codevalue": codevalue,
                "languagecd": body.languagecd,
                "translated_text": body.translated_text,
                "translated_desc": body.translated_desc,
                "creator": user_id,
            }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 번역 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{codegroupcd}/{codevalue}/translations/{languagecd}")
def delete_code_translation(codegroupcd: str, codevalue: str, languagecd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("code_translations").delete().eq("codegroupcd", codegroupcd).eq("codevalue", codevalue).eq("languagecd", languagecd).execute()
    return {"ok": True}
