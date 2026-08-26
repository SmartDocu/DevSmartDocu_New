"""Payments router — PortOne 기반 결제수단(빌링키) 관리 뼈대"""
import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid, get_user as _get_user
from utilsPrj.notifications import create_notification
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

router = APIRouter()

PORTONE_API_BASE = "https://api.portone.io"
WEBHOOK_TOLERANCE_SECONDS = 300  # 리플레이 공격 방지용 타임스탬프 허용 오차 (Standard Webhooks 권장)


def _resolve_tenant_accountuid(sd, tenantid: int, user_id: str) -> Optional[str]:
    """tenantid → accountuid 해석. issystemtenant면 useruid 기준, 아니면 tenantid 기준."""
    t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True
    if issystemtenant:
        acc = sd.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = sd.table("accounts").select("accountuid").eq("tenantid", tenantid).maybe_single().execute()
    return acc.data["accountuid"] if acc and acc.data else None


def _payment_manage_url(issystemtenant: bool) -> str:
    """알림 target_url — 개인(시스템) 테넌트는 개인 결제 관리, 기업 테넌트는 기업 결제 관리 화면으로 안내."""
    return "upgrade/payment-manage" if issystemtenant else "org/payment-manage"


def _require_tenant_manager_tenantid(user_id: str, header_tenantid: Optional[str]) -> int:
    """
    현재 선택된 테넌트(X-Tenant-ID)에 대한 결제 관리 권한을 검증 후 tenantid 반환. 아니면 403.
    개인(시스템) 테넌트는 1인 소유라 "매니저" 개념이 없으므로 소속 여부만 확인하고,
    기업 테넌트는 기존대로 매니저(rolecd=M)만 허용한다.
    """
    if not header_tenantid:
        raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
    tenantid = int(header_tenantid)
    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True

    tu_row = (
        sd.table("tenantusers")
        .select("rolecd")
        .eq("useruid", user_id)
        .eq("tenantid", tenantid)
        .eq("useyn", True)
        .maybe_single()
        .execute()
    )
    if not tu_row.data:
        raise HTTPException(status_code=403, detail="테넌트 소속이 아닙니다.")
    if not issystemtenant and tu_row.data.get("rolecd") != "M":
        raise HTTPException(status_code=403, detail="테넌트 매니저 권한이 필요합니다.")
    return tenantid


def _portone_get_billing_key(billing_key_id: str) -> dict:
    """포트원 서버에 빌링키 상태를 직접 재확인한다 (프론트에서 넘어온 값을 그대로 신뢰하지 않음)."""
    if not settings.PORTONE_API_SECRET:
        raise HTTPException(status_code=503, detail="PORTONE_API_SECRET이 설정되지 않았습니다. 포트원 콘솔에서 V2 API Secret을 발급 후 .env에 등록하세요.")
    resp = requests.get(
        f"{PORTONE_API_BASE}/billing-keys/{billing_key_id}",
        headers={"Authorization": f"PortOne {settings.PORTONE_API_SECRET}"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"포트원 빌링키 조회 실패: {resp.text[:300]}")
    return resp.json()


def _portone_charge_billing_key(payment_id: str, billing_key: str, order_name: str, amount: int, customer: dict) -> tuple[int, dict]:
    """
    빌링키로 실제 결제를 청구한다.
    실제 응답 구조는 2026-08-19 테스트 채널(KG이니시스)로 직접 호출해 확정함:
    - customer.name은 문자열이 아니라 {"full": "..."} 객체여야 한다.
    - customer.email/phoneNumber는 이 PG 채널 기준 필수값이다.
    - 성공 시 {"payment": {"pgTxId": ..., "paidAt": ...}} 형태로 응답한다.
    """
    if not settings.PORTONE_API_SECRET:
        raise HTTPException(status_code=503, detail="PORTONE_API_SECRET이 설정되지 않았습니다. 포트원 콘솔에서 V2 API Secret을 발급 후 .env에 등록하세요.")
    resp = requests.post(
        f"{PORTONE_API_BASE}/payments/{payment_id}/billing-key",
        headers={"Authorization": f"PortOne {settings.PORTONE_API_SECRET}", "Content-Type": "application/json"},
        json={
            "billingKey": billing_key,
            "orderName": order_name,
            "customer": customer,
            "amount": {"total": amount},
            "currency": "KRW",
        },
        timeout=15,
    )
    try:
        result = resp.json()
    except Exception:
        result = {"message": resp.text[:300]}
    return resp.status_code, result


def _portone_cancel_payment(portone_payment_id: str, reason: str) -> tuple[int, dict]:
    """
    포트원 결제를 취소(환불)한다. 2026-08-19 실제 호출로 확인:
    POST /payments/{paymentId}/cancel, body {"reason": "..."},
    성공 시 {"cancellation": {"status": "SUCCEEDED", "id": ..., "totalAmount": ...}} 형태.
    """
    if not settings.PORTONE_API_SECRET:
        raise HTTPException(status_code=503, detail="PORTONE_API_SECRET이 설정되지 않았습니다.")
    resp = requests.post(
        f"{PORTONE_API_BASE}/payments/{portone_payment_id}/cancel",
        headers={"Authorization": f"PortOne {settings.PORTONE_API_SECRET}", "Content-Type": "application/json"},
        json={"reason": reason},
        timeout=15,
    )
    try:
        result = resp.json()
    except Exception:
        result = {"message": resp.text[:300]}
    return resp.status_code, result


def refund_charge(sd, user_id: str, paymentuid: str, reason: str) -> dict:
    """
    성공한 결제를 자동 취소(환불)하고 payments/payment_refunds에 기록하는 보정(compensation) 로직.
    "결제는 성공했는데 후속 처리(예: 크레딧 지급)가 실패한" 상황에서 결제를 되돌리기 위해 쓴다.
    반환: {"success": True} 또는 {"success": False, "message": ...}
    """
    from datetime import datetime as _dt, timezone as _tz

    payment_row = sd.table("payments").select("*").eq("paymentuid", paymentuid).maybe_single().execute()
    if not payment_row or not payment_row.data:
        return {"success": False, "message": "환불 대상 결제를 찾을 수 없습니다."}
    payment = payment_row.data

    now_iso = _dt.now(_tz.utc).isoformat()
    status_code, pg_result = _portone_cancel_payment(f"charge-{paymentuid}", reason)
    success = status_code == 200

    sd.table("payments").update({
        "payment_status": "Refunded" if success else payment.get("payment_status"),
    }).eq("paymentuid", paymentuid).execute()

    sd.table("payment_refunds").insert({
        "tenantid": payment.get("tenantid"),
        "accountuid": payment.get("accountuid"),
        "paymentuid": paymentuid,
        "refund_amount": payment.get("payment_amount"),
        "currencycd": payment.get("currencycd"),
        "refund_reasondesc": reason,
        "refund_status": "Success" if success else "Failed",
        "provider_refund_id": (pg_result.get("cancellation") or {}).get("id") if success else None,
        "requesteduid": user_id,
        "requesteddts": now_iso,
        "processeduid": user_id,
        "processeddts": now_iso,
        "creator": user_id,
    }).execute()

    t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", payment.get("tenantid")).maybe_single().execute()
    issystemtenant = (t_row.data or {}).get("issystemtenant", True) if t_row else True
    payment_url = _payment_manage_url(issystemtenant)
    amount_txt = f"{int(payment.get('payment_amount') or 0):,}원"

    refund_params = {"amount": int(payment.get("payment_amount") or 0)}
    if success:
        create_notification(
            get_service_client(), category="payment", status="info",
            title="결제 환불 완료", message=f"결제({amount_txt})가 환불되었습니다.",
            title_key="msg.notification.payment.refund.completed.title",
            message_key="msg.notification.payment.refund.completed.body", params=refund_params,
            target_object="payment", target_uid=paymentuid, target_url=payment_url, target_useruid=user_id,
        )
    else:
        create_notification(
            get_service_client(), category="payment", status="error",
            title="결제 환불 실패", message=f"결제({amount_txt}) 환불 처리 중 오류가 발생했습니다. 고객센터에 문의해주세요.",
            title_key="msg.notification.payment.refund.failed.title",
            message_key="msg.notification.payment.refund.failed.body", params=refund_params,
            target_object="payment", target_uid=paymentuid, target_url=payment_url, target_useruid=user_id,
        )

    if not success:
        return {"success": False, "message": pg_result.get("message") or str(pg_result)}
    return {"success": True}


# ══════════════════════════════════════════════════════
#  CONFIG (프론트 SDK 초기화용 — 공개 가능한 값만)
# ══════════════════════════════════════════════════════

@router.get("/config")
def get_payment_config(token: str = Depends(get_token)):
    return {
        "storeId": settings.PORTONE_STORE_ID,
        "channelKey": settings.PORTONE_CHANNEL_KEY,
    }


# ══════════════════════════════════════════════════════
#  PAYMENT METHODS (빌링키)
# ══════════════════════════════════════════════════════

@router.get("/methods")
def list_payment_methods(token: str = Depends(get_token), header_tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _require_tenant_manager_tenantid(user_id, header_tenantid)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    accountuid = _resolve_tenant_accountuid(sd, tenantid, user_id)
    if not accountuid:
        return {"methods": []}

    rows = (
        sd.table("payment_methods")
        .select("*")
        .eq("accountuid", accountuid)
        .neq("payment_method_status", "Deleted")
        .order("is_default", desc=True)
        .execute()
        .data or []
    )
    return {"methods": rows}


def _get_offsetminutes(sb, user_id: str, tenantid: Optional[str] = None) -> Optional[int]:
    """tenantid를 주면 그 테넌트 기준으로, 없으면(다중 테넌트일 때 모호해질 수 있어) 활성(useyn=True) 소속 행을 사용."""
    try:
        q = sb.table("tenantusers").select("timezone,tenantid").eq("useruid", user_id)
        if tenantid:
            q = q.eq("tenantid", int(tenantid))
        else:
            q = q.eq("useyn", True)
        rows = q.limit(1).execute().data or []
        if not rows:
            return None
        tu_data = rows[0]
        tz = tu_data.get("timezone")
        if not tz and tu_data.get("tenantid"):
            t = sb.table("tenants").select("timezone").eq("tenantid", tu_data["tenantid"]).maybe_single().execute()
            if t and t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None
    except Exception:
        return None


def _fmt_dt(raw, offsetminutes: Optional[int] = None) -> str:
    if not raw:
        return ""
    try:
        from datetime import timedelta
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


@router.get("/history")
def list_payment_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    """결제 이력 조회 화면: 계정의 결제(payments) 내역을 최신순으로 반환한다.
    start_date/end_date: "YYYY-MM-DD"(사용자 로컬 날짜) — 미지정 시 최근 1개월."""
    from datetime import date, timedelta as td

    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _require_tenant_manager_tenantid(user_id, header_tenantid)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    accountuid = _resolve_tenant_accountuid(sd, tenantid, user_id)
    if not accountuid:
        return {"payments": []}

    offsetminutes = _get_offsetminutes(sd, user_id, str(tenantid))

    today = date.today()
    sd_str = start_date or (today - td(days=30)).strftime("%Y-%m-%d")
    ed_str = end_date or today.strftime("%Y-%m-%d")

    query = (
        sd.table("payments").select(
            "paymentuid,productcd,quantity,currencycd,payment_amount,payment_status,createdts"
        )
        .eq("accountuid", accountuid)
    )
    if offsetminutes is not None:
        sd_utc = datetime.strptime(sd_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) - td(minutes=offsetminutes)
        ed_utc = datetime.strptime(ed_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + td(days=1) - td(minutes=offsetminutes)
        query = query.gte("createdts", sd_utc.isoformat()).lt("createdts", ed_utc.isoformat())
    else:
        end_plus = (datetime.strptime(ed_str, "%Y-%m-%d") + td(days=1)).strftime("%Y-%m-%d")
        query = query.gte("createdts", sd_str).lt("createdts", end_plus)

    rows = query.order("createdts", desc=True).execute().data or []
    productcds = [r["productcd"] for r in rows if r.get("productcd")]
    prod_map = {}
    if productcds:
        prod_rows = sd.table("products").select("productcd,productnm").in_("productcd", productcds).execute().data or []
        prod_map = {p["productcd"]: p["productnm"] for p in prod_rows}

    for r in rows:
        r["productnm"] = prod_map.get(r.get("productcd"))
        r["createdts"] = _fmt_dt(r.get("createdts"), offsetminutes)

    return {"payments": rows}


class BillingKeySaveRequest(BaseModel):
    billing_key_id: str
    is_default: bool = False
    display_nm: Optional[str] = None


@router.post("/methods/billing-key")
def save_billing_key(
    body: BillingKeySaveRequest,
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    """결제창(결제창 방식)에서 발급된 billingKeyId를 포트원 서버에 재확인 후 payment_methods에 저장한다."""
    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _require_tenant_manager_tenantid(user_id, header_tenantid)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    accountuid = _resolve_tenant_accountuid(sd, tenantid, user_id)
    if not accountuid:
        raise HTTPException(status_code=400, detail="계정(accountuid)을 확인할 수 없습니다.")

    pg_data = _portone_get_billing_key(body.billing_key_id)
    if pg_data.get("status") != "ISSUED":
        raise HTTPException(status_code=400, detail=f"빌링키 상태가 유효하지 않습니다: {pg_data.get('status')}")

    # 2026-08-19 테스트 채널(KG이니시스) 실제 응답으로 필드 경로 확정:
    # channels는 배열이고, card.number는 "536148*********4"처럼 끝 1자리만 노출되며
    # expiryYear/expiryMonth는 이 API 자체에서 내려주지 않는다(PG 정책 — 코드로 해결 불가).
    method_info = (pg_data.get("methods") or [{}])[0]
    card = method_info.get("card", {})
    channel = (pg_data.get("channels") or [{}])[0]

    card_number = card.get("number") or ""
    trailing_digits = re.search(r"(\d+)$", card_number)
    card_last4 = trailing_digits.group(1)[-4:] if trailing_digits else ""

    data = {
        "tenantid": tenantid,
        "accountuid": accountuid,
        "payment_providercd": "portone",
        "gateway_providercd": channel.get("pgProvider", ""),
        "provider_customerid": (pg_data.get("customer") or {}).get("id", ""),
        "billing_key": body.billing_key_id,
        "payment_method_type": method_info.get("type", "Card"),
        "payment_method_status": "Active",
        "is_default": body.is_default,
        "display_nm": body.display_nm or card.get("name", ""),
        "card_brand": card.get("brand", ""),
        "card_last4": card_last4,
        "expiry_year": card.get("expiryYear"),
        "expiry_month": card.get("expiryMonth"),
    }

    if body.is_default:
        sd.table("payment_methods").update({"is_default": False}).eq("accountuid", accountuid).execute()

    existing = sd.table("payment_methods").select("payment_methoduid").eq("billing_key", body.billing_key_id).execute().data
    if existing:
        sd.table("payment_methods").update(data).eq("payment_methoduid", existing[0]["payment_methoduid"]).execute()
    else:
        sd.table("payment_methods").insert(data).execute()

    return {"result": "success", "message": "결제수단이 등록되었습니다."}


@router.delete("/methods/{payment_methoduid}")
def delete_payment_method(
    payment_methoduid: str,
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _require_tenant_manager_tenantid(user_id, header_tenantid)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    sd.table("payment_methods").update({
        "payment_method_status": "Deleted",
        "is_default": False,
    }).eq("payment_methoduid", payment_methoduid).eq("tenantid", tenantid).execute()

    return {"result": "success", "message": "결제수단이 삭제되었습니다."}


@router.post("/methods/{payment_methoduid}/set-default")
def set_default_payment_method(
    payment_methoduid: str,
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    """지정한 결제수단을 기본(구매 시 자동 청구되는 카드)으로 설정한다."""
    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _require_tenant_manager_tenantid(user_id, header_tenantid)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    method_row = sd.table("payment_methods").select("accountuid,payment_method_status").eq(
        "payment_methoduid", payment_methoduid
    ).eq("tenantid", tenantid).maybe_single().execute()
    if not method_row.data:
        raise HTTPException(status_code=404, detail="결제수단을 찾을 수 없습니다.")
    if method_row.data.get("payment_method_status") != "Active":
        raise HTTPException(status_code=400, detail="사용할 수 없는 결제수단입니다.")

    accountuid = method_row.data.get("accountuid")
    sd.table("payment_methods").update({"is_default": False}).eq("accountuid", accountuid).execute()
    sd.table("payment_methods").update({"is_default": True}).eq("payment_methoduid", payment_methoduid).execute()

    return {"result": "success", "message": "기본 결제수단으로 설정되었습니다."}


class ChargeRequest(BaseModel):
    amount: int
    order_name: Optional[str] = None


def execute_charge(sd, user_id: str, tenantid: int, method: dict, amount: float, order_name: str, productcd: Optional[str] = None, quantity: Optional[int] = None) -> dict:
    """
    등록된 빌링키로 즉시 결제를 청구하는 공용 로직 (payments/payment_attempts 기록 포함).
    payments.py의 /methods/{id}/charge 엔드포인트와 settings.py의 크레딧 구매 등 다른 도메인에서
    "이미 등록된 카드로 상품 금액만큼 청구"가 필요할 때 공용으로 재사용한다.
    productcd/quantity: 결제 이력에서 "무엇을 몇 개 샀는지" 확인용(테스트 결제 등 상품 연결이
    없는 경우 None으로 둔다).
    반환: {"success": True, "pgTxId": ...} 또는 {"success": False, "message": ...}
    """
    from utilsPrj.crypto_helper import decrypt_value

    payment_methoduid = method["payment_methoduid"]
    accountuid = method.get("accountuid")

    t_row = sd.table("tenants").select("disptenantnm,issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    disptenantnm = (t_row.data or {}).get("disptenantnm") or "고객"
    payment_url = _payment_manage_url((t_row.data or {}).get("issystemtenant", True))

    email, telno = "", ""
    if accountuid:
        acc_row = sd.table("accounts").select("encemail,enctelno").eq("accountuid", accountuid).maybe_single().execute()
        acc = acc_row.data or {}
        if acc.get("encemail"):
            email = decrypt_value(acc["encemail"])
        if acc.get("enctelno"):
            telno = decrypt_value(acc["enctelno"])

    payment_row = {
        "tenantid": tenantid,
        "accountuid": accountuid,
        "payment_methoduid": payment_methoduid,
        "currencycd": "KRW",
        "payment_amount": amount,
        "payment_status": "Pending",
        "productcd": productcd,
        "quantity": quantity,
        "creator": user_id,
    }
    paymentuid = sd.table("payments").insert(payment_row).execute().data[0]["paymentuid"]

    attempt_row = {
        "tenantid": tenantid,
        "accountuid": accountuid,
        "paymentuid": paymentuid,
        "attemptno": 1,
        "payment_methoduid": payment_methoduid,
        "attempt_status": "Pending",
    }
    attemptuid = sd.table("payment_attempts").insert(attempt_row).execute().data[0]["attemptuid"]

    customer = {
        "name": {"full": disptenantnm},
        "email": email or "noemail@example.com",
        "phoneNumber": telno or "01000000000",
    }
    status_code, pg_result = _portone_charge_billing_key(
        f"charge-{paymentuid}", method["billing_key"], order_name, amount, customer,
    )

    amount_txt = f"{int(amount):,}원"

    if status_code == 200:
        sd.table("payments").update({
            "payment_status": "Success",
            "succesful_payment_methoduid": payment_methoduid,
            "succesful_attemptuid": attemptuid,
            "succesful_attemptdts": datetime.now(timezone.utc).isoformat(),
        }).eq("paymentuid", paymentuid).execute()
        sd.table("payment_attempts").update({"attempt_status": "Success"}).eq("attemptuid", attemptuid).execute()
        create_notification(
            get_service_client(), category="payment", status="info",
            title="결제 완료", message=f"'{order_name}' 결제가 완료되었습니다. ({amount_txt})",
            title_key="msg.notification.payment.completed.title", message_key="msg.notification.payment.completed.body",
            params={"order_name": order_name, "amount": int(amount)},
            target_object="payment", target_uid=paymentuid, target_url=payment_url, target_useruid=user_id,
        )
        return {"success": True, "pgTxId": (pg_result.get("payment") or {}).get("pgTxId"), "paymentuid": paymentuid}

    failure_message = pg_result.get("message") or str(pg_result)
    sd.table("payments").update({"payment_status": "Failed"}).eq("paymentuid", paymentuid).execute()
    sd.table("payment_attempts").update({
        "attempt_status": "Failed",
        "failure_code": pg_result.get("type", ""),
        "failure_message": failure_message[:250],
    }).eq("attemptuid", attemptuid).execute()
    create_notification(
        get_service_client(), category="payment", status="error",
        title="결제 실패", message=f"'{order_name}' 결제가 실패했습니다. ({amount_txt})",
        title_key="msg.notification.payment.failed.title", message_key="msg.notification.payment.failed.body",
        params={"order_name": order_name, "amount": int(amount)},
        target_object="payment", target_uid=paymentuid, target_url=payment_url, target_useruid=user_id,
    )
    return {"success": False, "message": failure_message, "paymentuid": paymentuid}


@router.post("/methods/{payment_methoduid}/charge")
def charge_payment_method(
    payment_methoduid: str,
    body: ChargeRequest,
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    """등록된 빌링키로 즉시 결제를 청구한다 (연동 검증용 테스트 결제 포함)."""
    user = _get_user(token)
    user_id = str(user.id)
    tenantid = _require_tenant_manager_tenantid(user_id, header_tenantid)

    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="결제 금액은 0보다 커야 합니다.")

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    method_row = sd.table("payment_methods").select("*").eq("payment_methoduid", payment_methoduid).eq("tenantid", tenantid).maybe_single().execute()
    if not method_row.data:
        raise HTTPException(status_code=404, detail="결제수단을 찾을 수 없습니다.")

    order_name = body.order_name or "결제 테스트"
    result = execute_charge(sd, user_id, tenantid, method_row.data, body.amount, order_name, productcd=None, quantity=None)

    if result["success"]:
        return {"result": "success", "message": "결제가 완료되었습니다.", "pgTxId": result["pgTxId"]}
    raise HTTPException(status_code=400, detail=result["message"])


# ══════════════════════════════════════════════════════
#  WEBHOOK (포트원 → 서버 콜백. get_token 인증 예외 — 서명으로 검증)
# ══════════════════════════════════════════════════════

def _verify_portone_webhook(request: Request, raw_body: bytes) -> bool:
    """
    포트원 웹훅 서명 검증 (Standard Webhooks 스펙, https://www.standardwebhooks.com/).
    webhook-id/webhook-timestamp/webhook-signature 헤더 + HMAC-SHA256으로 검증한다.
    PORTONE_WEBHOOK_SECRET 미설정이거나 헤더/서명이 없거나 형식이 안 맞으면 False.
    """
    secret = settings.PORTONE_WEBHOOK_SECRET
    if not secret:
        return False

    webhook_id = request.headers.get("webhook-id")
    webhook_timestamp = request.headers.get("webhook-timestamp")
    webhook_signature = request.headers.get("webhook-signature")
    if not webhook_id or not webhook_timestamp or not webhook_signature:
        return False

    try:
        timestamp = int(webhook_timestamp)
    except ValueError:
        return False
    if abs(time.time() - timestamp) > WEBHOOK_TOLERANCE_SECONDS:
        return False

    try:
        secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
        signed_content = f"{webhook_id}.{webhook_timestamp}.{raw_body.decode('utf-8')}"
        expected_sig = base64.b64encode(
            hmac.new(secret_bytes, signed_content.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
    except Exception:
        return False

    for part in webhook_signature.split():
        _, _, sig = part.partition(",")
        if sig and hmac.compare_digest(sig, expected_sig):
            return True
    return False


@router.post("/webhook")
async def receive_webhook(request: Request):
    """포트원 웹훅 수신 엔드포인트. 서명 검증 후 원본 payload를 payment_webhook_logs에 저장한다."""
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except Exception:
        payload = {"raw": raw_body.decode("utf-8", errors="ignore")}

    verified = _verify_portone_webhook(request, raw_body)
    secret_configured = bool(settings.PORTONE_WEBHOOK_SECRET)

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    sd.table("payment_webhook_logs").insert({
        "providercd": "portone",
        "event_type": payload.get("type", ""),
        "provider_transaction_id": (payload.get("data") or {}).get("paymentId", ""),
        "signature_verified": verified,
        "payload": payload,
        "process_status": "Received" if (verified or not secret_configured) else "Failed",
    }).execute()

    # 시크릿이 설정된 상태에서 검증이 실패하면 위조/변조 가능성이 있으므로 거부한다.
    # 시크릿 미설정 시(이전 단계)는 검증 자체가 불가능하므로 기록만 하고 통과시킨다.
    if secret_configured and not verified:
        raise HTTPException(status_code=400, detail="웹훅 서명 검증에 실패했습니다.")

    return {"result": "ok"}
