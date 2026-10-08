"""회원 탈퇴 — /withdraw 페이지 전용 API.

- GET  /withdraw/overview            탈퇴 화면에 필요한 모든 정보(시나리오, 구독, 소속 조직, 미납 여부 등)
- POST /withdraw/transfer-admin      유일 관리자가 다른 구성원에게 조직 관리자 권한을 넘김
- POST /withdraw/end-org-subscription 구성원이 본인뿐인 조직의 구독을 종료(조직 해지 신청)
- POST /withdraw/submit              실제 탈퇴 처리

시나리오: 소속 조직(시스템 테넌트가 아닌 활성 테넌트)이 없으면 "personal", 있으면 "tenant".
개인 영역(시스템 테넌트의 내 계정) 자료는 탈퇴 당일 야간에 삭제된다(ImmediateDelete = Archived +
purge_immediate=True, 실제 물리삭제는 content_purge.py 배치).
"""
import math
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid, get_user as _get_user
from backend.app.routers.settings import _reserve_service_cancellation, _get_offsetminutes, _fmt_dt
from utilsPrj.audit_log import log_work_action, get_client_ip
from utilsPrj.notifications import create_notification
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client, get_supabase_client
from utilsPrj.user_lookup import get_usernm_email_map, mask_email, mask_name

router = APIRouter()

_MAX_FAILS = 5
_LOCK_SECONDS = 30
# 본인 확인 실패 횟수/잠금 — 프로세스 메모리에 둔다(여러 태스크로 늘어나면 태스크별로 따로 센다).
_auth_state: dict[str, dict] = {}


# ─── 본인 확인 ────────────────────────────────────────────────────────────────

def _auth_method(user) -> str:
    """'password'(이메일 가입) 또는 'email'(소셜 등 비밀번호가 없는 가입 — 가입 이메일 직접 입력)."""
    provider = (getattr(user, "app_metadata", None) or {}).get("provider")
    return "password" if provider in (None, "email") else "email"


def _verify_identity(user, auth_value: str) -> None:
    """비밀번호(또는 가입 이메일)가 맞는지 확인한다. 연속 5회 실패 시 30초 잠금.
    실패는 400(401로 하면 프론트 인터셉터가 토큰 갱신을 시도해 시도가 이중 집계된다)."""
    uid = str(user.id)
    now = time.time()
    st = _auth_state.setdefault(uid, {"count": 0, "lock_until": 0.0})
    if st["lock_until"] > now:
        raise HTTPException(
            status_code=429, detail="msg.withdraw.auth.locked",
            headers={"Retry-After": str(math.ceil(st["lock_until"] - now))},
        )

    method = _auth_method(user)
    ok = False
    if auth_value:
        if method == "password":
            try:
                get_supabase_client().auth.sign_in_with_password({"email": user.email, "password": auth_value})
                ok = True
            except Exception:
                ok = False
        else:
            ok = auth_value.strip().lower() == (user.email or "").strip().lower()

    if ok:
        _auth_state.pop(uid, None)
        return

    st["count"] += 1
    if st["count"] >= _MAX_FAILS:
        st["count"] = 0
        st["lock_until"] = now + _LOCK_SECONDS
        raise HTTPException(
            status_code=429, detail="msg.withdraw.auth.locked",
            headers={"Retry-After": str(_LOCK_SECONDS)},
        )
    raise HTTPException(
        status_code=400,
        detail="msg.withdraw.auth.password_invalid" if method == "password" else "msg.withdraw.auth.email_mismatch",
    )


# ─── 현황 조회 ────────────────────────────────────────────────────────────────

def _personal_account(svc, user_id: str) -> Optional[str]:
    rows = svc.table("accounts").select("accountuid").eq("useruid", user_id).limit(1).execute().data or []
    return rows[0]["accountuid"] if rows else None


def _load_orgs(svc, user_id: str) -> list[dict]:
    """내가 속한 활성 조직(시스템 테넌트 제외)의 현황. kind:
    member(일반 구성원) / admin(다른 관리자가 있는 관리자) / sole(유일 관리자, 다른 구성원 있음 → 권한 이전 필요)
    / soloOrg(유일 관리자이자 유일 구성원 → 조직 구독 종료 필요)."""
    my_rows = svc.table("tenantusers").select("tenantid,rolecd").eq("useruid", user_id).eq("useyn", True).execute().data or []
    if not my_rows:
        return []
    my_role = {r["tenantid"]: r.get("rolecd") for r in my_rows}
    tenants = svc.table("tenants").select(
        "tenantid,tenantnm,disptenantnm,issystemtenant,useyn,cancel_requested_dt"
    ).in_("tenantid", list(my_role)).execute().data or []
    orgs = [t for t in tenants if not t.get("issystemtenant") and t.get("useyn", True)]
    if not orgs:
        return []
    org_ids = [t["tenantid"] for t in orgs]

    members = svc.table("tenantusers").select("tenantid,useruid,rolecd").in_(
        "tenantid", org_ids).eq("useyn", True).execute().data or []
    accounts = svc.table("accounts").select("accountuid,tenantid").in_("tenantid", org_ids).execute().data or []
    acc_by_tenant = {a["tenantid"]: a["accountuid"] for a in accounts}
    acc_ids = list(acc_by_tenant.values())
    accsvcs = svc.table("accountservices").select("accountuid,servicecd,subscriptionuid").in_(
        "accountuid", acc_ids).eq("servicestatus", "Active").execute().data if acc_ids else []
    sub_ids = [a["subscriptionuid"] for a in (accsvcs or []) if a.get("subscriptionuid")]
    subs = svc.table("subscriptions").select("subscriptionuid,canceldts,cancel_typecd").in_(
        "subscriptionuid", sub_ids).execute().data if sub_ids else []
    sub_map = {s["subscriptionuid"]: s for s in (subs or [])}

    other_member_ids = [m["useruid"] for m in members if m["useruid"] != user_id]
    user_map = get_usernm_email_map(svc, other_member_ids)

    result = []
    for t in orgs:
        tid = t["tenantid"]
        t_members = [m for m in members if m["tenantid"] == tid]
        managers = [m for m in t_members if m.get("rolecd") == "M"]
        role = my_role.get(tid)
        acc_id = acc_by_tenant.get(tid)
        t_svcs = [a for a in (accsvcs or []) if a["accountuid"] == acc_id]

        if role == "M":
            if len(managers) > 1:
                kind = "admin"
            elif len(t_members) > 1:
                kind = "sole"
            else:
                kind = "soloOrg"
        else:
            kind = "member"

        end_mode = None
        cancel_types = [sub_map.get(a.get("subscriptionuid"), {}).get("cancel_typecd") for a in t_svcs
                        if sub_map.get(a.get("subscriptionuid"), {}).get("canceldts")]
        if cancel_types:
            end_mode = "delete" if "ImmediateDelete" in cancel_types else "keep"

        item = {
            "tenantid": str(tid),
            "tenantnm": t.get("disptenantnm") or t.get("tenantnm") or "",
            "rolecd": role,
            "kind": kind,
            "resolved": bool(t.get("cancel_requested_dt")) if kind == "soloOrg" else False,
            "end_mode": end_mode,
            "servicecds": sorted({a["servicecd"] for a in t_svcs}),
        }
        if kind == "sole":
            item["candidates"] = [
                {
                    "useruid": m["useruid"],
                    "usernm": user_map.get(m["useruid"], ("", ""))[0],
                    "email": user_map.get(m["useruid"], ("", ""))[1],
                }
                for m in t_members if m["useruid"] != user_id
            ]
        result.append(item)
    return result


def _load_overview(svc, user, header_tenantid: Optional[str]) -> dict:
    user_id = str(user.id)
    accountuid = _personal_account(svc, user_id)

    # 개인 영역 서비스 (Free/Pro)
    personal_services = []
    unpaid = False
    if accountuid:
        accsvcs = svc.table("accountservices").select(
            "servicecd,productcd,plancd,subscriptionuid,billingday"
        ).eq("accountuid", accountuid).eq("servicestatus", "Active").execute().data or []
        prod_ids = [a["productcd"] for a in accsvcs if a.get("productcd")]
        prods = svc.table("products").select("productcd,productnm").in_("productcd", prod_ids).execute().data if prod_ids else []
        name_map = {p["productcd"]: p.get("productnm") or p["productcd"] for p in (prods or [])}
        sub_ids = [a["subscriptionuid"] for a in accsvcs if a.get("subscriptionuid")]
        buckets = svc.table("creditbuckets").select("subscriptionuid,expiredts").in_(
            "subscriptionuid", sub_ids).eq("creditchargecd", "Ba").execute().data if sub_ids else []
        bucket_map = {b["subscriptionuid"]: b.get("expiredts") for b in (buckets or [])}
        offsetminutes = _get_offsetminutes(get_service_client(), user_id, header_tenantid)
        order = {r["codevalue"]: r.get("orderno") or 999 for r in (
            svc.table("codes").select("codevalue,orderno").eq("codegroupcd", "servicecd").execute().data or [])}
        for a in sorted(accsvcs, key=lambda x: order.get(x["servicecd"], 999)):
            is_pro = a.get("plancd") != "Fr"
            personal_services.append({
                "servicecd": a["servicecd"],
                "productnm": name_map.get(a.get("productcd"), a.get("productcd") or ""),
                "is_pro": is_pro,
                "billingday": a.get("billingday") if is_pro else None,
                "expire_date": _fmt_dt(bucket_map.get(a.get("subscriptionuid")), offsetminutes)[:10].replace("-", ".") if is_pro else None,
            })
        billing = svc.table("account_billing").select("billing_status").eq("accountuid", accountuid).execute().data or []
        unpaid = any(b.get("billing_status") in ("PastDue", "Suspended") for b in billing)

    orgs = _load_orgs(svc, user_id)

    u_row = svc.table("users").select("usernm,email").eq("useruid", user_id).maybe_single().execute()
    usernm = (u_row.data.get("usernm") if u_row and u_row.data else "") or ""

    return {
        "scenario": "tenant" if orgs else "personal",
        "email": user.email,
        "usernm": usernm,
        "masked_usernm": mask_name(usernm),
        "masked_email": mask_email(user.email or ""),
        "auth_method": _auth_method(user),
        "unpaid": unpaid,
        "personal_services": personal_services,
        "has_pro": any(s["is_pro"] for s in personal_services),
        "orgs": orgs,
    }


@router.get("/overview")
def get_overview(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    user = _get_user(token)
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    return _load_overview(svc, user, tenantid)


# ─── 관리자 권한 넘기기 ───────────────────────────────────────────────────────

class TransferAdminRequest(BaseModel):
    tenantid: str
    new_admin_useruid: str
    auth_value: str = ""


@router.post("/transfer-admin")
def transfer_admin(body: TransferAdminRequest, request: Request, token: str = Depends(get_token)):
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    _verify_identity(user, body.auth_value)

    org = next((o for o in _load_orgs(svc, user_id) if o["tenantid"] == body.tenantid), None)
    if not org or org["kind"] != "sole":
        raise HTTPException(status_code=400, detail="msg.withdraw.transfer.not_allowed")
    if body.new_admin_useruid not in {c["useruid"] for c in org.get("candidates", [])}:
        raise HTTPException(status_code=400, detail="msg.withdraw.transfer.invalid_user")

    tid = int(body.tenantid)
    svc.table("tenantusers").update({"rolecd": "M"}).eq("tenantid", tid).eq("useruid", body.new_admin_useruid).execute()
    svc.table("tenantusers").update({"rolecd": "U"}).eq("tenantid", tid).eq("useruid", user_id).execute()

    try:
        create_notification(
            svc, category="plan", status="info",
            title="조직 관리자 지정",
            message=f"'{org['tenantnm']}' 조직의 관리자로 지정되었습니다.",
            title_key="msg.notification.admin_transferred.title", message_key="msg.notification.admin_transferred.body",
            params={"tenantnm": org["tenantnm"]},
            target_object="tenant", target_uid=body.tenantid, target_url="myinfo", target_useruid=body.new_admin_useruid,
        )
    except Exception:
        pass

    log_work_action(
        useruid=user_id, tenantid=tid, servicecd="Tenant",
        actioncd="update", targettype="withdraw/transfer-admin", targetid=body.new_admin_useruid,
        before={"admin": user_id}, after={"admin": body.new_admin_useruid},
        ip=get_client_ip(request),
    )
    new_nm = next((c["usernm"] or c["email"] for c in org["candidates"] if c["useruid"] == body.new_admin_useruid), "")
    return {"result": "success", "new_admin_name": new_nm}


# ─── 조직 구독 종료 ───────────────────────────────────────────────────────────

class EndOrgSubscriptionRequest(BaseModel):
    tenantid: str
    mode: str  # keep(90일 열람 후 삭제) | delete(오늘 야간 삭제)


@router.post("/end-org-subscription")
def end_org_subscription(body: EndOrgSubscriptionRequest, request: Request, token: str = Depends(get_token)):
    if body.mode not in ("keep", "delete"):
        raise HTTPException(status_code=400, detail="msg.cancel_typecd.invalid")
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    org = next((o for o in _load_orgs(svc, user_id) if o["tenantid"] == body.tenantid), None)
    if not org or org["kind"] != "soloOrg":
        raise HTTPException(status_code=400, detail="msg.withdraw.end.not_allowed")
    if org["resolved"]:
        raise HTTPException(status_code=400, detail="msg.withdraw.end.already")

    tid = int(body.tenantid)
    acc = svc.table("accounts").select("accountuid").eq("tenantid", tid).limit(1).execute().data or []
    accountuid = acc[0]["accountuid"] if acc else None
    cancel_typecd = "ImmediateDelete" if body.mode == "delete" else "ArchiveDelete"

    if accountuid:
        rows = svc.table("accountservices").select("servicecd,subscriptionuid").eq(
            "accountuid", accountuid).eq("servicestatus", "Active").execute().data or []
        for r in rows:
            sub_uid = r.get("subscriptionuid")
            if not sub_uid:
                continue
            sub = svc.table("subscriptions").select("canceldts").eq("subscriptionuid", sub_uid).maybe_single().execute()
            if sub and sub.data and sub.data.get("canceldts"):
                continue  # 이미 별도로 해지가 예약된 서비스는 건드리지 않는다
            _reserve_service_cancellation(
                svc, accountuid, r["servicecd"], sub_uid, user_id, cancel_typecd,
                extra_fields={"cancel_reasondesc": "account withdrawal"},
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    svc.table("tenants").update({
        "cancel_requested_dt": now_iso,
        "cancel_useruid": user_id,
        "cancel_reasondesc": "account withdrawal",
    }).eq("tenantid", tid).execute()

    log_work_action(
        useruid=user_id, tenantid=tid, servicecd="Tenant",
        actioncd="update", targettype="withdraw/end-org-subscription", targetid=body.tenantid,
        before={"cancel_requested_dt": None}, after={"cancel_requested_dt": now_iso},
        detail={"cancel_typecd": cancel_typecd},
        ip=get_client_ip(request),
    )
    return {"result": "success", "mode": body.mode}


# ─── 탈퇴 ────────────────────────────────────────────────────────────────────

class WithdrawSubmitRequest(BaseModel):
    reasoncd: Optional[str] = None
    reasondesc: Optional[str] = None
    auth_value: str = ""
    agree_all: bool = False
    agree_personal: bool = False
    agree_pro: bool = False


def _send_withdraw_mail(email: str, lang: str, lines: list[str]) -> None:
    import smtplib
    from email.mime.text import MIMEText

    if not email or not settings.EMAIL_HOST_USER:
        return
    ko = lang == "ko"
    subject = "[D2Doc] 회원 탈퇴가 완료되었습니다." if ko else "[D2Doc] Your account has been deleted."
    intro = "회원 탈퇴가 완료되었습니다." if ko else "Your account deletion is complete."
    outro = "그동안 D2Doc을 이용해 주셔서 감사합니다." if ko else "Thank you for using D2Doc."
    body = intro + "\n\n" + "\n".join(f"- {ln}" for ln in lines) + "\n\n" + outro + "\n\nD2Doc"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_HOST_USER
    msg["To"] = email
    smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    try:
        smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        smtp.sendmail(settings.EMAIL_HOST_USER, [email], msg.as_string())
    finally:
        smtp.quit()


@router.post("/submit")
def submit_withdraw(
    body: WithdrawSubmitRequest, request: Request,
    token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client().schema(SUPABASE_SCHEMA)

    # 마스킹 보존 컬럼이 없으면(users_masked_columns.sql 미적용) 아무것도 바꾸기 전에 중단한다
    try:
        svc.table("users").select("masked_usernm,masked_email,out_reasoncd,out_etcreason,out_agree,out_datadel,out_norefund,out_dts").limit(1).execute()
        # 타입 검증 — out_reasoncd는 문자열 코드, out_dts는 timestamptz여야 한다(users_withdraw_column_types.sql)
        svc.table("users").select("useruid").eq("out_reasoncd", "__probe__").gt("out_dts", "2000-01-01T00:00:00+00:00").limit(1).execute()
    except Exception:
        raise HTTPException(status_code=500, detail="withdraw schema not ready: check sdoc.users out_*/masked_* columns (users_withdraw_column_types.sql)")

    ov = _load_overview(svc, user, tenantid)
    if not body.agree_all or not body.agree_personal or (ov["has_pro"] and not body.agree_pro):
        raise HTTPException(status_code=400, detail="msg.withdraw.agree_required")
    if ov["unpaid"]:
        raise HTTPException(status_code=400, detail="msg.withdraw.unpaid_blocked")
    pending = [o for o in ov["orgs"] if o["kind"] == "sole" or (o["kind"] == "soloOrg" and not o["resolved"])]
    if pending:
        raise HTTPException(status_code=400, detail="msg.withdraw.org_action_required")

    _verify_identity(user, body.auth_value)

    now_iso = datetime.now(timezone.utc).isoformat()
    email = user.email or ""
    lang_row = svc.table("tenantusers").select("languagecd").eq("useruid", user_id).limit(1).execute().data or []
    lang = (lang_row[0].get("languagecd") if lang_row else None) or "ko"

    # 0) 탈퇴 사유/동의/마스킹 값을 sdoc.users에 먼저 기록한다 — 컬럼 타입이 안 맞으면 파괴적 작업 전에 여기서 실패한다.
    #    (email/usernm 비우기는 모든 처리가 끝난 3단계에서 한다)
    svc.table("users").update({
        "out_reasoncd": body.reasoncd,
        "out_etcreason": body.reasondesc,
        "out_agree": bool(body.agree_all),
        "out_datadel": bool(body.agree_personal),
        "out_norefund": bool(body.agree_pro),
        "out_dts": now_iso,
        "masked_usernm": ov["masked_usernm"],
        "masked_email": ov["masked_email"],
        "updatedts": now_iso,
    }).eq("useruid", user_id).execute()

    # 1) 개인 영역: 모든 서비스를 오늘 야간 삭제 대상으로 전환(Archived + purge_immediate). 이미 보관(Archived) 중인 것도 당겨서 삭제.
    accountuid = _personal_account(svc, user_id)
    reserved: list[str] = []
    if accountuid:
        rows = svc.table("accountservices").select("servicecd,subscriptionuid,servicestatus,archived_dt").eq(
            "accountuid", accountuid).in_("servicestatus", ["Active", "Archived"]).execute().data or []
        for r in rows:
            sub_uid = r.get("subscriptionuid")
            if r["servicestatus"] == "Active" and sub_uid:
                _reserve_service_cancellation(
                    svc, accountuid, r["servicecd"], sub_uid, user_id, "ImmediateDelete",
                    extra_fields={"cancel_reasoncd": body.reasoncd, "cancel_reasondesc": body.reasondesc},
                )
            else:
                svc.table("accountservices").update({
                    "servicestatus": "Archived",
                    "archived_dt": r.get("archived_dt") or now_iso,
                    "purge_immediate": True,
                    "updater": user_id,
                }).eq("accountuid", accountuid).eq("servicecd", r["servicecd"]).execute()
            reserved.append(r["servicecd"])

    # 2) 소속 조직에서 모두 나가기(구성원/다른 관리자가 있는 관리자/구독 종료를 마친 1인 조직)
    left_orgs = []
    for o in ov["orgs"]:
        tid = int(o["tenantid"])
        svc.table("tenantusers").delete().eq("tenantid", tid).eq("useruid", user_id).execute()
        projects = svc.table("projects").select("projectid").eq("tenantid", tid).execute().data or []
        for p in projects:
            svc.table("projectusers").delete().eq("projectid", p["projectid"]).eq("useruid", user_id).execute()
        svc.table("serviceusers").delete().eq("tenantid", tid).eq("useruid", user_id).execute()
        left_orgs.append(o)

    # 3) users 행: 개인정보 초기화 + 기업에 남는 작성자 표시용 마스킹 값 보존
    before_user = svc.table("users").select("*").eq("useruid", user_id).maybe_single().execute()
    svc.table("users").update({
        "email": "",
        "usernm": "",
        "isemailconfirm": None,
        "default_tenantid": None,
        "electronicfinancialtermsyn": None,
        "useyn": False,
        "updatedts": now_iso,
    }).eq("useruid", user_id).execute()

    log_work_action(
        useruid=user_id, tenantid=int(tenantid) if tenantid else None, servicecd="Tenant",
        actioncd="update", targettype="withdraw/submit", targetid=user_id,
        before=before_user.data if before_user else None,
        after={"useyn": False, "reserved_services": reserved, "left_tenantids": [o["tenantid"] for o in left_orgs]},
        detail={"reasoncd": body.reasoncd, "reasondesc": body.reasondesc},
        ip=get_client_ip(request),
    )

    # 4) Supabase Auth 사용자 하드 삭제 — 마지막에 둔다(이후 이 토큰으로는 어떤 API도 호출할 수 없다)
    get_service_client().auth.admin.delete_user(user_id)

    # 5) 확인 메일(실패해도 탈퇴 결과에는 영향 없음)
    mail_lines = []
    if ov["personal_services"] or reserved:
        mail_lines.append("개인 영역의 모든 자료는 오늘 야간에 삭제됩니다." if lang == "ko"
                          else "All data in your personal area will be deleted tonight.")
    for o in left_orgs:
        mail_lines.append(
            f"{o['tenantnm']}: " + ("조직에서 나갔으며 개인정보가 삭제되었습니다." if lang == "ko"
                                   else "You left the organization and your personal information was removed.")
        )
    try:
        _send_withdraw_mail(email, lang, mail_lines)
    except Exception:
        pass

    return {
        "result": "success",
        "email": email,
        "personal_services": ov["personal_services"],
        "has_pro": ov["has_pro"],
        "orgs": [{"tenantnm": o["tenantnm"], "kind": o["kind"], "end_mode": o["end_mode"]} for o in left_orgs],
    }
