from typing import Optional

from utilsPrj.supabase_client import SUPABASE_SCHEMA


def notification_tenant_tag(issystemtenant: bool, disptenantnm: Optional[str]) -> str:
    """알림 메시지 접두어 — 개인(시스템) 테넌트는 회사 개념이 없어 굳이 표시할 필요가 없으므로 생략하고,
    기업 테넌트일 때만 "[테넌트명] "을 붙인다. 어느 테넌트의 결제/구독/작업 알림인지 구분하기 위한 용도.
    백엔드 라우터와 워커(worker/main.py) 양쪽에서 공유해서 쓴다."""
    if issystemtenant:
        return ""
    return f"[{disptenantnm or '-'}] "


def notification_tenant_tag_by_id(sd, tenantid) -> str:
    """tenantid로 tenants를 조회해 notification_tenant_tag()를 계산하는 편의 함수.
    sd는 이미 sdoc 스키마로 스코핑된 클라이언트여야 한다(예: get_service_client().schema(SUPABASE_SCHEMA)).
    조회 실패/tenantid 없음이면 개인 테넌트로 간주해 빈 문자열을 반환한다."""
    if not tenantid:
        return ""
    try:
        row = sd.table("tenants").select("disptenantnm,issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
        data = (row.data if row else None) or {}
    except Exception:
        return ""
    return notification_tenant_tag(data.get("issystemtenant", True), data.get("disptenantnm"))


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
