"""감사 로그 공용 헬퍼 — sdoc.admin_action_logs INSERT.

admin_action_logs는 append-only(DB 트리거로 UPDATE/DELETE 차단)이므로,
로그 기록 자체가 실패해도 원본 관리자 작업은 막지 않는다(예외를 삼킨다).
"""
import base64
import json
from typing import Optional

from fastapi import Request

from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def decode_jwt_sub(token_or_auth_header: Optional[str]) -> Optional[str]:
    """JWT의 sub(useruid) claim을 서명 검증 없이 읽는다.
    로그 기록 전용 — 실제 인가는 각 엔드포인트가 이미 처리했다는 전제.
    "Bearer xxx" 헤더값과 순수 토큰 문자열 둘 다 받는다."""
    if not token_or_auth_header:
        return None
    token = token_or_auth_header
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return payload.get("sub")
    except Exception:
        return None


def snapshot_row(sb, table: str, pk_col: str, pk_val) -> Optional[dict]:
    """감사로그 before/after용 — 대상 row 전체 컬럼을 조회한다. 실패/미존재 시 None."""
    if not pk_val:
        return None
    try:
        row = sb.schema(SUPABASE_SCHEMA).table(table).select("*").eq(pk_col, pk_val).maybe_single().execute()
        return row.data if row else None
    except Exception:
        return None


def log_admin_action(
    useruid: str,
    roleid: int,
    actioncd: str,
    tenantid: Optional[int] = None,
    targettype: Optional[str] = None,
    targetid: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    detail: Optional[dict] = None,
    ip: Optional[str] = None,
    sessionid: Optional[str] = None,
):
    """
    actioncd: view_user | view_data | download | update | delete
              | permission_change | config_change
              | apikey_issue | apikey_delete | log_access_attempt
    """
    try:
        svc = get_service_client()
        svc.schema(SUPABASE_SCHEMA).table("admin_action_logs").insert({
            "useruid": useruid,
            "roleid": roleid,
            "tenantid": tenantid,
            "actioncd": actioncd,
            "targettype": targettype,
            "targetid": str(targetid) if targetid is not None else None,
            "before_json": before,
            "after_json": after,
            "detail": detail,
            "ip": ip or None,
            "sessionid": sessionid,
        }).execute()
    except Exception:
        pass


def log_work_action(
    useruid: str,
    actioncd: str,
    tenantid: Optional[int] = None,
    servicecd: Optional[str] = None,
    targettype: Optional[str] = None,
    targetid: Optional[str] = None,
    before=None,
    after=None,
    detail: Optional[dict] = None,
    ip: Optional[str] = None,
    sessionid: Optional[str] = None,
):
    """
    일반 사용자/테넌트매니저의 쓰기성 작업 로그(work_logs). append-only.
    actioncd: create | update | delete (HTTP 메서드 기준 자동 판별값)
    servicecd: Do | Ch | In | Tenant
    before/after: 대부분의 엔드포인트는 미들웨어가 자동으로 남기며 이 값이 없다(None).
                   datas.py 등 일부 핵심 엔드포인트만 직접 snapshot_row()로 채운다.
                   단건 dict뿐 아니라 list(예: datacols 여러 행 일괄저장)도 그대로 저장 가능.
    """
    try:
        svc = get_service_client()
        svc.schema(SUPABASE_SCHEMA).table("work_logs").insert({
            "useruid": useruid,
            "tenantid": tenantid,
            "servicecd": servicecd,
            "actioncd": actioncd,
            "targettype": targettype,
            "targetid": str(targetid) if targetid is not None else None,
            "before_json": before,
            "after_json": after,
            "detail": detail,
            "ip": ip or None,
            "sessionid": sessionid,
        }).execute()
    except Exception:
        pass
