from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_token
from backend.app.schemas.messages import (
    MessageItem, MessagesListResponse, MessageSaveRequest, MessageSaveResponse,
    MessageTranslationItem, MessageTranslationsListResponse, MessageTranslationSaveRequest,
)
from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


def _get_user(token: str):
    from backend.app.dependencies import verify_user
    sb = _sb(token)
    return verify_user(sb, token)


# ─── 전체 목록 ───────────────────────────────────────────────────────────────

@router.get("", response_model=MessagesListResponse)
def list_messages(token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("messages")
        .select("*")
        .order("messagekey")
        .execute()
        .data or []
    )
    return MessagesListResponse(messages=[MessageItem(**r) for r in rows])


# ─── 생성 ────────────────────────────────────────────────────────────────────

@router.post("", response_model=MessageSaveResponse)
def create_message(body: MessageSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("messages")
        .select("messagekey").eq("messagekey", body.messagekey).execute().data
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 메시지 키입니다: {body.messagekey}")

    record = {
        "messagekey": body.messagekey,
        "messagetypecd": body.messagetypecd,
        "default_message": body.default_message,
        "description": body.description,
        "useyn": body.useyn,
        "creator": user_id,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("messages").insert(record).execute()
        return MessageSaveResponse(result="success", messagekey=body.messagekey)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 수정 ────────────────────────────────────────────────────────────────────

@router.put("/{messagekey}", response_model=MessageSaveResponse)
def update_message(messagekey: str, body: MessageSaveRequest, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("messages")
        .select("messagekey").eq("messagekey", messagekey).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")

    record = {
        "messagetypecd": body.messagetypecd,
        "default_message": body.default_message,
        "description": body.description,
        "useyn": body.useyn,
    }
    try:
        sb.schema(SUPABASE_SCHEMA).table("messages").update(record).eq("messagekey", messagekey).execute()
        return MessageSaveResponse(result="success", messagekey=messagekey)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 삭제 ────────────────────────────────────────────────────────────────────

@router.delete("/{messagekey}")
def delete_message(messagekey: str, token: str = Depends(get_token)):
    sb = _sb(token)

    existing = (
        sb.schema(SUPABASE_SCHEMA).table("messages")
        .select("messagekey").eq("messagekey", messagekey).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")

    sb.schema(SUPABASE_SCHEMA).table("message_translations").delete().eq("messagekey", messagekey).execute()
    sb.schema(SUPABASE_SCHEMA).table("messages").delete().eq("messagekey", messagekey).execute()
    return {"ok": True, "message": "메시지가 삭제되었습니다."}


# ─── 번역 목록 ───────────────────────────────────────────────────────────────

@router.get("/{messagekey}/translations", response_model=MessageTranslationsListResponse)
def list_translations(messagekey: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("message_translations")
        .select("messagekey, languagecd, translated_text")
        .eq("messagekey", messagekey)
        .order("languagecd")
        .execute()
        .data or []
    )
    return MessageTranslationsListResponse(translations=[MessageTranslationItem(**r) for r in rows])


# ─── 번역 저장 ───────────────────────────────────────────────────────────────

@router.post("/{messagekey}/translations")
def save_translation(messagekey: str, body: MessageTranslationSaveRequest, token: str = Depends(get_token)):
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
        sb.schema(SUPABASE_SCHEMA).table("message_translations")
        .select("messagekey")
        .eq("messagekey", messagekey)
        .eq("languagecd", body.languagecd)
        .execute()
        .data
    )

    try:
        if existing:
            sb.schema(SUPABASE_SCHEMA).table("message_translations").update({
                "translated_text": body.translated_text,
            }).eq("messagekey", messagekey).eq("languagecd", body.languagecd).execute()
        else:
            sb.schema(SUPABASE_SCHEMA).table("message_translations").insert({
                "messagekey": messagekey,
                "languagecd": body.languagecd,
                "translated_text": body.translated_text,
                "creator": user_id,
            }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")


# ─── 번역 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/{messagekey}/translations/{languagecd}")
def delete_translation(messagekey: str, languagecd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("message_translations").delete().eq("messagekey", messagekey).eq("languagecd", languagecd).execute()
    return {"ok": True}
