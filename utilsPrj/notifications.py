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
) -> None:
    """sdoc.notifications에 알림 1건을 insert한다. sb는 service-role 클라이언트."""
    try:
        sb.schema(SUPABASE_SCHEMA).table("notifications").insert({
            "notificationcategory": category,
            "notificationstatus": status,
            "title": title,
            "message": message,
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
