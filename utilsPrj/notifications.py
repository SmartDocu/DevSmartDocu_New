from typing import Optional

from utilsPrj.supabase_client import SUPABASE_SCHEMA


def create_notification(
    sb,
    *,
    category: str,
    status: str,
    title: str,
    message: str,
    target_useruid: str,
    target_object: Optional[str] = None,
    target_uid: Optional[str] = None,
    target_url: Optional[str] = None,
    is_onetarget: bool = True,
    creator: Optional[str] = None,
    title_key: Optional[str] = None,
    message_key: Optional[str] = None,
    params: Optional[dict] = None,
) -> None:
    """sdoc.notifications에 알림 1건을 insert한다. sb는 service-role 클라이언트.

    title/message는 한글 고정 문구로, 검색(search) 및 titlekey/messagekey 미등록 시
    폴백으로 계속 쓰인다. title_key/message_key(ui_terms의 msg.* term_key)와 params를
    함께 넘기면 프론트가 로그인 사용자 언어에 맞춰 번역 렌더링한다.
    """
    try:
        sb.schema(SUPABASE_SCHEMA).table("notifications").insert({
            "notificationcategory": category,
            "notificationstatus": status,
            "title": title,
            "message": message,
            "titlekey": title_key,
            "messagekey": message_key,
            "params": params,
            "target_object": target_object,
            "target_uid": target_uid,
            "target_url": target_url,
            "is_onetarget": is_onetarget,
            "target_useruid": target_useruid,
            "is_read": False,
            "deleted_yn": False,
            "creator": creator or target_useruid,
        }).execute()
    except Exception:
        pass
