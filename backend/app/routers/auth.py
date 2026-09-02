import hashlib
import ipaddress
import random
import re
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_token, get_tenantid
from utilsPrj.supabase_client import get_thread_supabase, get_service_client, SUPABASE_SCHEMA
from utilsPrj.credit_helper import upsert_ba_creditbucket
from utilsPrj.private_storage import resolve_display_url
from backend.app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    MfaVerifyRequest,
    MfaEnrollRequest,
    MfaEnrollResponse,
    MfaEnrollVerifyRequest,
    MfaEnrollVerifyResponse,
    MfaUnenrollRequest,
    RefreshRequest,
    RegisterInviteRequest,
    RegisterRequest,
    SelectTenantRequest,
    SendResetEmailRequest,
    SendSmsRequest,
    TenantsResponse,
    TokenResponse,
    UpdatePasswordRequest,
    UserContext,
    VerifySmsRequest,
)

router = APIRouter()


# ─── 로그인 로그 헬퍼 ────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _get_tenant_config(tenantid: int, configcd: str) -> bool:
    """config_tenants.value == 'true' 여부를 반환한다."""
    svc = get_service_client().schema(SUPABASE_SCHEMA)
    cfg = svc.table("config_tenants").select("value").eq("tenantid", tenantid).eq("configcd", configcd).maybe_single().execute()
    val = (cfg.data or {}).get("value") if cfg else None
    return val is True or (isinstance(val, str) and val.lower() == "true")


def _check_ip_whitelist(tenantid: int, ip: str, is_manager: bool) -> bool:
    """tenant의 IP allow-list 설정을 확인한다. 미설정/비활성 시 통과(True)."""
    configcd = "Is_Manager_IP_Allow" if is_manager else "Is_User_IP_Allow"
    if not _get_tenant_config(tenantid, configcd):
        return True

    try:
        ip_num = int(ipaddress.IPv4Address(ip))
    except ValueError:
        return False

    svc = get_service_client().schema(SUPABASE_SCHEMA)
    rows = svc.table("whitelists").select("start_ip_num,end_ip_num").eq("tenantid", tenantid).eq("useyn", True).execute().data or []
    return any(r["start_ip_num"] <= ip_num <= r["end_ip_num"] for r in rows)


def _get_mfa_session_state(user_client) -> dict:
    """계정의 MFA 등록 여부와 현재 세션의 aal 상태를 반환한다.
    aal은 세션 전역 값이라 테넌트를 넘나들어도 한 번 aal2가 되면 유지된다.
    """
    try:
        assurance = user_client.auth.mfa.get_authenticator_assurance_level()
        is_aal2 = assurance.current_level == "aal2"
        has_verified = False
        factor_id = None
        if assurance.next_level == "aal2":
            factors_resp = user_client.auth.mfa.list_factors()
            verified_factors = [f for f in (factors_resp.totp or []) if f.status == "verified"]
            if verified_factors:
                has_verified = True
                factor_id = verified_factors[0].id
        return {"has_verified": has_verified, "is_aal2": is_aal2, "factor_id": factor_id}
    except Exception:
        return {"has_verified": False, "is_aal2": False, "factor_id": None}


def _evaluate_tenant_access(user_client, tenantid: int, is_manager: bool, ip: str) -> dict:
    """대상 테넌트의 IP 화이트리스트 / MFA 정책을 평가한다.

    반환:
      {"status": "ok"}
      {"status": "blocked", "reason": "ip"}
      {"status": "blocked", "reason": "mfa_setup"}                       — MFA 미등록, 강제 설정 필요
      {"status": "blocked", "reason": "mfa_challenge", "factor_id": ...} — 등록됨, 이번 세션 TOTP 미인증
    """
    if not _check_ip_whitelist(tenantid, ip, is_manager):
        return {"status": "blocked", "reason": "ip"}

    if _get_tenant_config(tenantid, "Is_MFA"):
        mfa_state = _get_mfa_session_state(user_client)
        if not mfa_state["has_verified"]:
            return {"status": "blocked", "reason": "mfa_setup"}
        if not mfa_state["is_aal2"]:
            return {"status": "blocked", "reason": "mfa_challenge", "factor_id": mfa_state["factor_id"]}

    return {"status": "ok"}


def _parse_user_agent(ua: str) -> dict:
    browser, browser_version, os_nm = "Unknown", "", "Unknown"

    if "Windows NT 10.0" in ua:
        os_nm = "Windows 10/11"
    elif "Windows NT" in ua:
        os_nm = "Windows"
    elif "Mac OS X" in ua:
        os_nm = "macOS"
    elif "Android" in ua:
        os_nm = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_nm = "iOS"
    elif "Linux" in ua:
        os_nm = "Linux"

    if "Edg/" in ua:
        browser = "Edge"
        m = re.search(r"Edg/([\d.]+)", ua)
        browser_version = m.group(1) if m else ""
    elif "Chrome/" in ua:
        browser = "Chrome"
        m = re.search(r"Chrome/([\d.]+)", ua)
        browser_version = m.group(1) if m else ""
    elif "Firefox/" in ua:
        browser = "Firefox"
        m = re.search(r"Firefox/([\d.]+)", ua)
        browser_version = m.group(1) if m else ""
    elif "Safari/" in ua:
        browser = "Safari"
        m = re.search(r"Version/([\d.]+)", ua)
        browser_version = m.group(1) if m else ""

    return {"browser": browser, "browser_version": browser_version, "os_nm": os_nm}


def _device_fingerprint(ip: str, ua: str) -> str:
    return hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:64]


def _get_user_info_by_email(email: str) -> tuple[int, Optional[str]]:
    """로그인 실패 시 이메일로 tenantid·useruid 조회."""
    try:
        svc = get_service_client()
        sd = svc.schema(SUPABASE_SCHEMA)
        user_row = sd.table("users").select("useruid").eq("email", email).maybe_single().execute()
        if not user_row or not user_row.data:
            return 0, None
        useruid = user_row.data["useruid"]
        tu_row = sd.table("tenantusers").select("tenantid").eq("useruid", useruid).maybe_single().execute()
        tenantid = int(tu_row.data["tenantid"]) if tu_row and tu_row.data else 0
        return tenantid, str(useruid)
    except Exception:
        return 0, None


def _get_country_code(ip: str) -> Optional[str]:
    """ip-api.com으로 국가코드 조회 (2자리, 예: KR). 실패 시 None."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return None
    try:
        import httpx
        resp = httpx.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "countryCode"},
            timeout=3.0,
        )
        data = resp.json()
        return data.get("countryCode") or None
    except Exception:
        return None


def _insert_login_log(
    tenantid: int,
    useruid: Optional[str],
    logintypecd: str,
    is_success: bool,
    errorcd: Optional[str],
    errormessage: Optional[str],
    ip: str,
    is_mfaused: bool,
    sessionid: Optional[str],
    browser: str,
    browser_version: str,
    os_nm: str,
    device_fingerprint: str,
    eventtypecd: str = "login",
    roleid: Optional[int] = None,
):
    countrycd = _get_country_code(ip)
    try:
        svc = get_service_client()
        if roleid is None and useruid:
            urow = svc.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", useruid).maybe_single().execute()
            roleid = urow.data.get("roleid") if urow and urow.data else None
        svc.schema(SUPABASE_SCHEMA).table("login_logs").insert({
            "tenantid": tenantid,
            "useruid": useruid,
            "logintypecd": logintypecd,
            "eventtypecd": eventtypecd,
            "roleid": roleid,
            "is_success": is_success,
            "errorcd": errorcd,
            "errormessage": errormessage,
            "ip": ip or None,
            "countrycd": countrycd,
            "is_mfaused": is_mfaused,
            "sessionid": sessionid,
            "browser": browser,
            "browser_version": browser_version,
            "os": os_nm,
            "device_fingerprint": device_fingerprint,
        }).execute()
    except Exception as e:
        # print(f"[login_log] INSERT 실패: {e}")
        pass


# ─── 개인정보 동의 로그 헬퍼 ──────────────────────────────────────────────────

# 회원가입 필수 동의 항목 → terms.json 키 매핑
_CONSENT_TERMS_KEY = {
    "userinfo": "collection",
    "termsofuse": "service",
    "electronicfinancialterms": "finance",
}


def _get_terms_versions() -> dict:
    """frontend/public/terms/terms.json에서 약관별 version을 읽어온다. 실패 시 빈 dict."""
    try:
        import json
        from pathlib import Path
        path = Path("frontend/public/terms/terms.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v.get("version") for k, v in data.items()}
    except Exception:
        return {}


def _insert_privacy_consent_logs(
    useruid: str,
    consents: dict,  # {"userinfo": "Y", "termsofuse": "Y", "electronicfinancialterms": "Y"}
    ip: str,
    useragent: str,
):
    """회원가입 필수 동의 3개 항목을 항목별 1 row로 기록한다 (append-only, 5년 고정 보존)."""
    try:
        versions = _get_terms_versions()
        svc = get_service_client()
        rows = [
            {
                "useruid": useruid,
                "consenttypecd": consenttypecd,
                "consentyn": (consents.get(consenttypecd) == "Y"),
                "termsversion": versions.get(_CONSENT_TERMS_KEY[consenttypecd]),
                "ip": ip or None,
                "useragent": useragent,
            }
            for consenttypecd in _CONSENT_TERMS_KEY
        ]
        svc.schema(SUPABASE_SCHEMA).table("privacy_consent_logs").insert(rows).execute()
    except Exception as e:
        # print(f"[privacy_consent_log] INSERT 실패: {e}")
        pass


# SMS 인증번호 임시 저장소 (프로세스 내 메모리)
# 운영 환경에서는 Redis 또는 Supabase로 교체 권장
_sms_storage: dict[str, dict] = {}


# ─── 공통 헬퍼 ──────────────────────────────────────────────────────────────

def _get_service_client():
    """서비스 역할 Supabase 클라이언트 (관리 작업용)."""
    return get_service_client()


def _get_user_client(access_token: str, refresh_token: Optional[str] = None):
    """사용자 토큰 기반 Supabase 클라이언트."""
    return get_thread_supabase(access_token=access_token, refresh_token=refresh_token)


def _get_offsetminutes(sb, user_id: str, tenantid: Optional[str] = None) -> Optional[int]:
    """tenantid를 주면 그 테넌트 기준으로, 없으면(다중 테넌트일 때 모호해질 수 있어) 아무 소속 행이나 사용."""
    try:
        q = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id)
        if tenantid:
            q = q.eq("tenantid", int(tenantid))
        rows = q.limit(1).execute().data or []
        if not rows:
            return None
        tu_data = rows[0]
        tz = tu_data.get("timezone")
        if not tz and tu_data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu_data["tenantid"]).maybe_single().execute()
            if t and t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None
    except Exception:
        return None


def _fmt_dt(raw, offsetminutes: Optional[int] = None) -> str:
    if not raw:
        return ""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


def _load_user_context(supabase, user_id: str, email: str) -> UserContext:
    ctx = UserContext(id=user_id, email=email)
    sd = supabase.schema(SUPABASE_SCHEMA)

    # 1. 사용자 기본 정보
    try:
        user_row = (
            sd.table("users")
            .select("roleid,default_tenantid")
            .eq("useruid", user_id)
            .maybe_single()
            .execute()
        )
        if user_row.data:
            ctx.roleid = user_row.data.get("roleid")
    except Exception:
        pass

    # 2. tenantid + tenanticonurl + tenants 목록
    try:
        tu_rows = (
            sd.table("tenantusers")
            .select("tenantid")
            .eq("useruid", user_id)
            .eq("useyn", True)
            .execute()
        )
        if tu_rows.data:
            tenantids = [r["tenantid"] for r in tu_rows.data]

            tenants_info = (
                sd.table("tenants")
                .select("tenantid,tenantnm,disptenantnm,iconfileurl")
                .in_("tenantid", tenantids)
                .execute()
            )
            tenants_map = {t["tenantid"]: t for t in (tenants_info.data or [])}
            ctx.tenants = [
                {"tenantid": str(t["tenantid"]), "tenantnm": t.get("tenantnm", "")}
                for t in (tenants_info.data or [])
            ]

            # 기본 tenantid: users.default_tenantid 직접 사용
            active_tenantid = None
            if user_row.data and user_row.data.get("default_tenantid"):
                active_tenantid = user_row.data["default_tenantid"]

            if not active_tenantid and tenantids:
                active_tenantid = tenantids[0]

            if active_tenantid:
                ctx.tenantid = str(active_tenantid)
                t_info = tenants_map.get(active_tenantid)
                if t_info:
                    ctx.tenantnm = t_info.get("tenantnm")
                    ctx.disptenantnm = t_info.get("disptenantnm") or t_info.get("tenantnm")
                    ctx.tenanticonurl = resolve_display_url(supabase, t_info.get("iconfileurl"))

    except Exception:
        pass

    # 2-1. mydocid(마지막 선택 문서) 조회
    # serviceusers는 (useruid, servicecd) 조합이 테넌트별로 행이 나뉘어 있으므로
    # tenantid 없이 조회하면 다중 테넌트 계정에서 .maybe_single()이 406(복수 행)으로 실패한다.
    mydocid = None
    try:
        svc_q = sd.table("serviceusers").select("mydocid").eq("useruid", user_id).eq("servicecd", "Do")
        if ctx.tenantid:
            svc_q = svc_q.eq("tenantid", int(ctx.tenantid))
        svc_row = svc_q.maybe_single().execute()
        if svc_row and svc_row.data:
            mydocid = svc_row.data.get("mydocid")
    except Exception:
        pass

    # 3. 문서 목록 (활성 테넌트 소속 문서만 후보로 필터링 — 다른 테넌트 문서가 잡히는 것 방지)
    docid = None
    try:
        docs_row = sd.rpc("fn_docs_filtered__r_user_viewer", {"p_useruid": user_id}).execute()
        candidates = docs_row.data or []

        if candidates and ctx.tenantid:
            candidate_docids = [d["docid"] for d in candidates if d.get("docid")]
            docs_detail = (
                sd.table("docs").select("docid, projectid").in_("docid", candidate_docids).execute().data or []
            )
            project_ids = list({d["projectid"] for d in docs_detail if d.get("projectid")})
            tenant_project_ids = set()
            if project_ids:
                tenant_project_ids = {
                    p["projectid"]
                    for p in sd.table("projects").select("projectid").in_("projectid", project_ids)
                    .eq("tenantid", int(ctx.tenantid)).execute().data or []
                }
            doc_project_map = {d["docid"]: d.get("projectid") for d in docs_detail}
            candidates = [d for d in candidates if doc_project_map.get(d.get("docid")) in tenant_project_ids]

        if candidates:
            target_doc = None

            if mydocid:
                target_doc = next(
                    (d for d in candidates if str(d.get("docid")) == str(mydocid)),
                    None,
                )

            if not target_doc:
                target_doc = candidates[0]

            docid = target_doc.get("docid")
            ctx.docid = str(docid)
            ctx.docnm = target_doc.get("docnm", "")

            # mydocid가 실제 선택 docid와 다를 때 DB 동기화 (현재 활성 테넌트 행만 갱신)
            if str(docid) != str(mydocid or ""):
                try:
                    sync_q = sd.table("serviceusers").update({"mydocid": docid}).eq("useruid", user_id).eq("servicecd", "Do")
                    if ctx.tenantid:
                        sync_q = sync_q.eq("tenantid", int(ctx.tenantid))
                    sync_q.execute()
                except Exception:
                    pass

    except Exception:
        pass

    # 4. doc detail
    projectid = None
    try:
        if docid:
            doc_detail = (
                sd.table("docs")
                .select("projectid")
                .eq("docid", docid)
                .maybe_single()
                .execute()
            )

            if doc_detail.data:
                projectid = str(doc_detail.data.get("projectid", ""))

    except Exception:
        pass

    # 5. projectid fallback (문서에 projectid 없을 경우)
    if not projectid:
        try:
            proj_rows = (
                sd.table("projectusers")
                .select("projectid")
                .eq("useruid", user_id)
                .eq("useyn", True)
                .eq("rolecd", "M")
                .execute()
            )
            if proj_rows.data:
                projectid = str(proj_rows.data[0].get("projectid", ""))
            else:
                proj_rows2 = (
                    sd.table("projectusers")
                    .select("projectid")
                    .eq("useruid", user_id)
                    .eq("useyn", True)
                    .execute()
                )
                if proj_rows2.data:
                    projectid = str(proj_rows2.data[0].get("projectid", ""))
        except Exception:
            pass

    if projectid:
        ctx.projectid = projectid

    # 6. projectmanager
    try:
        if projectid:
            user_proj = (
                sd.table("projectusers")
                .select("rolecd")
                .eq("projectid", projectid)
                .eq("useruid", user_id)
                .eq("useyn", True)
                .execute()
            )

            ctx.projectmanager = (
                "Y"
                if user_proj.data and any(p.get("rolecd") == "M" for p in user_proj.data)
                else "N"
            )

    except Exception:
        pass

    # 7. tenantmanager
    try:
        if ctx.tenantid:
            user_tenant = (
                sd.table("tenantusers")
                .select("rolecd, useyn")
                .eq("useruid", user_id)
                .eq("tenantid", int(ctx.tenantid))
                .maybe_single()
                .execute()
            )
            ctx.tenantmanager = (
                "Y"
                if user_tenant.data
                and user_tenant.data.get("rolecd") == "M"
                and user_tenant.data.get("useyn") is True
                else "N"
            )

    except Exception:
        pass

    # 8. accountuid + accountstatus + accountmanager (issystemtenant 여부에 따라 조회 기준 다름)
    #    system tenant는 여러 개인 계정이 같은 tenantid를 공유하므로 useruid로 조회해야
    #    accounts 행이 유일하게 특정된다. 기업 tenant는 tenantid당 accounts 행이 유일하다.
    try:
        if ctx.tenantid:
            t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", int(ctx.tenantid)).maybe_single().execute()
            issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True
            ctx.issystemtenant = issystemtenant

            if issystemtenant:
                acc = sd.table("accounts").select("accountuid, accountstatus").eq("useruid", user_id).maybe_single().execute()
                ctx.accountmanager = "Y"  # 개인 계정 = 본인이 account 소유자
            else:
                acc = sd.table("accounts").select("accountuid, accountstatus").eq("tenantid", int(ctx.tenantid)).maybe_single().execute()
                # 기업 테넌트: tenantusers.rolecd = "M" 이면 accountmanager
                tu_row = sd.table("tenantusers").select("rolecd").eq("tenantid", int(ctx.tenantid)).eq("useruid", user_id).maybe_single().execute()
                ctx.accountmanager = "Y" if tu_row and tu_row.data and tu_row.data.get("rolecd") == "M" else "N"

            if acc and acc.data:
                ctx.accountuid = str(acc.data["accountuid"])
                ctx.accountstatus = acc.data.get("accountstatus")
    except Exception:
        pass

    # 9. editbuttonyn (accountmanager 세팅 이후 판단) — servicestatus(Do 서비스) write 권한도 함께 확인
    is_manager = ctx.projectmanager == "Y" or ctx.tenantmanager == "Y" or ctx.accountmanager == "Y"
    can_write_service = True
    if is_manager and ctx.tenantid:
        try:
            from utilsPrj.service_status import get_service_permission
            can_write_service = get_service_permission(supabase, ctx.tenantid, user_id, "Do")["can_write"]
        except Exception:
            can_write_service = True  # 조회 실패 시 매니저 권한 판단만으로 폴백(백엔드 write 엔드포인트에서 별도로 최종 차단됨)
    ctx.editbuttonyn = "Y" if (is_manager and can_write_service) else "N"

    # 10. languagecd: TenantUsers.languagecd → Tenants.languagecd
    try:
        if ctx.tenantid:
            lang_row = (
                sd.table("tenantusers")
                .select("languagecd")
                .eq("useruid", user_id)
                .eq("tenantid", int(ctx.tenantid))
                .maybe_single()
                .execute()
            )
            if lang_row.data and lang_row.data.get("languagecd"):
                ctx.languagecd = lang_row.data["languagecd"]
            else:
                t_lang = (
                    sd.table("tenants")
                    .select("languagecd")
                    .eq("tenantid", int(ctx.tenantid))
                    .maybe_single()
                    .execute()
                )
                if t_lang.data:
                    ctx.languagecd = t_lang.data.get("languagecd")
    except Exception:
        pass

    return ctx


# ─── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, background_tasks: BackgroundTasks):
    """
    1단계 로그인: 이메일/비밀번호 검증
    - MFA 미등록 → 즉시 토큰 + 사용자 컨텍스트 반환
    - MFA 등록됨 → mfa_required=True + 임시 토큰 반환 (2단계 필요)
    """
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    ua_info = _parse_user_agent(ua)
    fingerprint = _device_fingerprint(ip, ua)

    def _log(**kwargs):
        background_tasks.add_task(_insert_login_log, **kwargs)

    try:
        from utilsPrj.supabase_client import get_supabase_client
        anon_client = get_supabase_client()
        auth_resp = anon_client.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as exc:
        err_msg = str(exc)
        errorcd = "email_not_confirmed" if "Email not confirmed" in err_msg else "wrong_password"
        tenantid, useruid = _get_user_info_by_email(body.email)
        _log(
            tenantid=tenantid, useruid=useruid, logintypecd="Em",
            is_success=False, errorcd=errorcd, errormessage=err_msg[:500],
            ip=ip, is_mfaused=False, sessionid=None,
            device_fingerprint=fingerprint, **ua_info,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    session = auth_resp.session
    if not session:
        tenantid, useruid = _get_user_info_by_email(body.email)
        _log(
            tenantid=tenantid, useruid=useruid, logintypecd="Em",
            is_success=False, errorcd="no_session", errormessage="session is None",
            ip=ip, is_mfaused=False, sessionid=None,
            device_fingerprint=fingerprint, **ua_info,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인에 실패했습니다.",
        )

    user_client = _get_user_client(session.access_token, session.refresh_token)
    user = auth_resp.user
    ctx = _load_user_context(user_client, str(user.id), user.email)

    # ── 다중 테넌트: 정책 평가 없이 먼저 테넌트를 선택하게 한다 ────────────────
    if len(ctx.tenants or []) > 1:
        _log(
            tenantid=0, useruid=str(user.id), logintypecd="Em",
            is_success=True, errorcd=None, errormessage=None,
            ip=ip, is_mfaused=False,
            sessionid=(session.access_token[:100] if session.access_token else None),
            device_fingerprint=fingerprint, **ua_info,
        )
        return LoginResponse(
            tenant_selection_required=True,
            tenants=ctx.tenants,
            access_token_temp=session.access_token,
            refresh_token_temp=session.refresh_token,
        )

    # ── 단일 테넌트(또는 무소속): 해당 테넌트의 IP/MFA 정책 평가 ───────────────
    eval_result = {"status": "ok"}
    if ctx.tenantid:
        eval_result = _evaluate_tenant_access(user_client, int(ctx.tenantid), ctx.tenantmanager == "Y", ip)

    if eval_result["status"] == "blocked":
        reason = eval_result["reason"]
        _log(
            tenantid=int(ctx.tenantid) if ctx.tenantid else 0,
            useruid=str(user.id), logintypecd="Em",
            is_success=False, errorcd=f"policy_{reason}", errormessage=f"접근 차단: {reason}",
            ip=ip, is_mfaused=False, sessionid=None,
            device_fingerprint=fingerprint, **ua_info,
        )
        if reason == "ip":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="msg.login.ip.not.allowed")
        if reason == "mfa_setup":
            return LoginResponse(
                mfa_setup_required=True,
                tenantid=ctx.tenantid,
                access_token_temp=session.access_token,
                refresh_token_temp=session.refresh_token,
            )
        # reason == "mfa_challenge" — aal1 임시 토큰만 반환, 완전한 인증 아님
        return LoginResponse(
            mfa_required=True,
            factor_id=eval_result["factor_id"],
            tenantid=ctx.tenantid,
            access_token_temp=session.access_token,
            refresh_token_temp=session.refresh_token,
        )

    _log(
        tenantid=int(ctx.tenantid) if ctx.tenantid else 0,
        useruid=str(user.id), logintypecd="Em",
        is_success=True, errorcd=None, errormessage=None,
        ip=ip, is_mfaused=False,
        sessionid=(session.access_token[:100] if session.access_token else None),
        device_fingerprint=fingerprint, **ua_info,
    )
    # ────────────────────────────────────────────────────────────────────────

    return LoginResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user=ctx,
    )


@router.post("/mfa-verify", response_model=LoginResponse)
def mfa_verify(body: MfaVerifyRequest):
    """
    2단계 로그인: TOTP 코드 검증 → aal2 세션 발급
    프론트는 /login에서 받은 임시 토큰 + factor_id + 6자리 코드를 전송한다.
    """
    user_client = _get_user_client(body.access_token, body.refresh_token)

    try:
        # Step 1: challenge 발급
        challenge_resp = user_client.auth.mfa.challenge(
            {"factor_id": body.factor_id}
        )
        challenge_id = challenge_resp.id
        # print(f"[MFA-VERIFY] challenge 발급 성공: challenge_id={challenge_id}")
    except Exception as e:
        # print(f"[MFA-VERIFY] challenge 실패: {type(e).__name__}: {e}")
        pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"MFA challenge 실패: {str(e)}",
        )

    try:
        # Step 2: TOTP 코드 검증 → aal2 세션 반환
        verify_resp = user_client.auth.mfa.verify({
            "factor_id": body.factor_id,
            "challenge_id": challenge_id,
            "code": body.code,
        })
        # print(f"[MFA-VERIFY] verify 성공")
    except Exception as e:
        # print(f"[MFA-VERIFY] verify 실패: {type(e).__name__}: {e}")
        pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 코드가 올바르지 않습니다.",
        )

    access_token = getattr(verify_resp, "access_token", None)
    refresh_token = getattr(verify_resp, "refresh_token", None)
    # print(f"[MFA-VERIFY] verify_resp attrs: {vars(verify_resp)}")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA 검증에 실패했습니다.",
        )

    final_client = _get_user_client(access_token, refresh_token)
    user = verify_resp.user

    if body.tenantid:
        get_service_client().schema(SUPABASE_SCHEMA).table("users").update(
            {"default_tenantid": body.tenantid}
        ).eq("useruid", str(user.id)).execute()

    ctx = _load_user_context(final_client, str(user.id), user.email)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=ctx,
    )


@router.post("/select-tenant", response_model=LoginResponse)
def select_tenant(body: SelectTenantRequest, request: Request):
    """
    다중 테넌트 계정의 로그인 직후 테넌트 확정, 또는 강제 MFA 설정 완료 후 재개.
    임시 토큰(access_token_temp/refresh_token_temp) 기준으로 동작한다.
    """
    ip = _get_client_ip(request)
    user_client = _get_user_client(body.access_token_temp, body.refresh_token_temp)

    try:
        user_resp = user_client.auth.get_user(body.access_token_temp)
        user = user_resp.user
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")

    sd = get_service_client().schema(SUPABASE_SCHEMA)
    tu_check = (
        sd.table("tenantusers").select("tenantid")
        .eq("useruid", str(user.id)).eq("tenantid", int(body.tenantid)).eq("useyn", True)
        .maybe_single().execute()
    )
    if not tu_check or not tu_check.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="소속되지 않은 테넌트입니다.")

    sd.table("users").update({"default_tenantid": body.tenantid}).eq("useruid", str(user.id)).execute()

    ctx = _load_user_context(user_client, str(user.id), user.email)

    eval_result = _evaluate_tenant_access(user_client, int(body.tenantid), ctx.tenantmanager == "Y", ip)
    if eval_result["status"] == "blocked":
        reason = eval_result["reason"]
        if reason == "ip":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="msg.login.ip.not.allowed")
        if reason == "mfa_setup":
            return LoginResponse(
                mfa_setup_required=True,
                tenantid=body.tenantid,
                access_token_temp=body.access_token_temp,
                refresh_token_temp=body.refresh_token_temp,
            )
        return LoginResponse(
            mfa_required=True,
            factor_id=eval_result["factor_id"],
            tenantid=body.tenantid,
            access_token_temp=body.access_token_temp,
            refresh_token_temp=body.refresh_token_temp,
        )

    return LoginResponse(
        access_token=body.access_token_temp,
        refresh_token=body.refresh_token_temp,
        user=ctx,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, background_tasks: BackgroundTasks, token: str = Depends(get_token)):
    """로그아웃: Supabase 세션을 무효화한다."""
    from utilsPrj.audit_log import decode_jwt_sub

    useruid = decode_jwt_sub(token)
    if useruid:
        try:
            svc = get_service_client()
            tu_row = svc.schema(SUPABASE_SCHEMA).table("tenantusers").select("tenantid").eq("useruid", useruid).maybe_single().execute()
            tenantid = int(tu_row.data["tenantid"]) if tu_row and tu_row.data else 0
        except Exception:
            tenantid = 0
        ip = _get_client_ip(request)
        ua_info = _parse_user_agent(request.headers.get("user-agent", ""))
        background_tasks.add_task(
            _insert_login_log,
            tenantid=tenantid, useruid=useruid, logintypecd="Em", eventtypecd="logout",
            is_success=True, errorcd=None, errormessage=None,
            ip=ip, is_mfaused=False, sessionid=None,
            device_fingerprint=_device_fingerprint(ip, request.headers.get("user-agent", "")),
            **ua_info,
        )

    try:
        supabase = _get_user_client(token)
        supabase.auth.sign_out()
    except Exception:
        pass
    return MessageResponse(ok=True, message="로그아웃 되었습니다.")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest):
    """refresh_token으로 새 access_token을 발급한다."""
    try:
        from utilsPrj.supabase_client import get_supabase_client
        client = get_supabase_client()
        resp = client.auth.refresh_session(body.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰 갱신에 실패했습니다. 다시 로그인해주세요.",
        )

    session = resp.session
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인해주세요.",
        )

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )


@router.get("/me", response_model=UserContext)
def get_me(token: str = Depends(get_token)):
    """현재 로그인한 사용자의 컨텍스트 정보를 반환한다."""
    try:
        supabase = _get_user_client(token)
        user_resp = supabase.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise ValueError("user not found")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )

    return _load_user_context(supabase, str(user.id), user.email)


@router.post("/send-reset-email", response_model=MessageResponse)
def send_reset_email(body: SendResetEmailRequest):
    """비밀번호 재설정 이메일을 발송한다."""
    try:
        from utilsPrj.supabase_client import get_supabase_client
        client = get_supabase_client()
        redirect_to = f"{settings.BASE_URL.rstrip('/')}/password-reset"
        client.auth.reset_password_email(
            body.email,
            options={"redirect_to": redirect_to},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return MessageResponse(ok=True, message="비밀번호 재설정 이메일을 발송했습니다.")


@router.post("/update-password", response_model=MessageResponse)
def update_password(body: UpdatePasswordRequest):
    """비밀번호 재설정 링크의 token_hash를 검증해 세션을 얻은 후 새 비밀번호로 변경한다.

    이메일 보안 스캐너(수신 메일사/백신 등)가 복구 링크를 자동으로 미리 방문해
    1회용 토큰을 소진시키는 문제를 피하기 위해, token_hash 검증은 페이지 진입 시가 아니라
    사용자가 "비밀번호 변경" 버튼을 눌러 이 API를 호출하는 시점에만 수행한다.
    """
    try:
        from utilsPrj.supabase_client import get_supabase_client, get_thread_supabase
        client = get_supabase_client()
        verify_resp = client.auth.verify_otp({"token_hash": body.token_hash, "type": "recovery"})
        session = verify_resp.session
        if not session:
            raise ValueError("session not found")

        sb = get_thread_supabase(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
        )
        sb.auth.update_user({"password": body.new_password})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return MessageResponse(ok=True, message="비밀번호가 변경되었습니다.")


@router.get("/products")
def get_products():
    """회원가입 시 선택 가능한 서비스 상품 목록."""
    service = _get_service_client()
    result = (
        service.schema(SUPABASE_SCHEMA)
        .table("products")
        .select("productcd,productnm,servicecd,plancd,billingtermcd,users,credit,is_customeraikey")
        .eq("producttype", "Service")
        .eq("useyn", True)
        .eq("is_sales", True)
        .eq("plancd", "Fr")
        .order("orderno")
        .execute()
    )
    return {"products": result.data or []}


@router.get("/tenants", response_model=TenantsResponse)
def get_tenants():
    """회원가입 시 선택 가능한 테넌트 목록을 반환한다."""
    try:
        service = _get_service_client()
        result = service.table("tenants").select("id,tenantname").execute()
        tenants = result.data or []
    except Exception:
        tenants = []

    from backend.app.schemas.auth import TenantItem
    return TenantsResponse(
        tenants=[TenantItem(id=str(t["id"]), tenantname=t["tenantname"]) for t in tenants],
        multitenantyn="N",
    )


@router.post("/register", response_model=MessageResponse)
def register(body: RegisterRequest, request: Request, _invite_tenantid: Optional[int] = None):
    """회원가입: Supabase auth + users 테이블 + 기본 권한 할당.

    _invite_tenantid: register_invite()에서 호출 시에만 전달 — 해당 테넌트의
    초대 건만 가입완료 처리하기 위한 내부 파라미터 (공개 API에는 노출하지 않음).
    """
    from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA
    from dateutil.relativedelta import relativedelta

    SCHEMA = SUPABASE_SCHEMA

    # 비밀번호 검증
    if body.password_confirm and body.password != body.password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호가 일치하지 않습니다.",
        )
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호는 최소 8자 이상이어야 합니다.",
        )

    service = _get_service_client()

    # 중복 이메일 확인
    try:
        existing = (
            service.schema(SCHEMA)
            .table("users")
            .select("useruid")
            .eq("email", body.email)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 가입된 회원입니다.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"중복 확인 중 오류: {str(e)}",
        )

    # Supabase auth.sign_up (이메일 인증 발송)
    try:
        anon_client = get_supabase_client()
        signup_result = anon_client.auth.sign_up({
            "email": body.email,
            "password": body.password,
        })
        user_id = str(signup_result.user.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"회원가입 실패: {str(e)}",
        )

    # users 테이블에 사용자 정보 저장
    try:
        service.schema(SCHEMA).table("users").insert({
            "useruid": user_id,
            "email": body.email,
            "roleid": 1,
            "termsofuseyn": body.termsofuseyn,
            "userinfoyn": body.userinfoyn,
            "electronicfinancialtermsyn": body.electronicfinancialtermsyn,
            "marketingyn": body.marketingyn,
            "usernm": body.usernm,
            "useyn": True,
        }).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DB 저장 실패: {str(e)}",
        )

    # 개인정보 필수 동의 3개 항목 로그 기록 (실패해도 가입은 계속 진행)
    _insert_privacy_consent_logs(
        useruid=user_id,
        consents={
            "userinfo": body.userinfoyn,
            "termsofuse": body.termsofuseyn,
            "electronicfinancialterms": body.electronicfinancialtermsyn,
        },
        ip=_get_client_ip(request),
        useragent=request.headers.get("user-agent", ""),
    )

    # SmartDoc 기본 tenantid 조회
    smartdoc_row = (
        service.schema(SCHEMA)
        .table("tenants")
        .select("tenantid")
        .eq("issystemtenant", True)
        .execute()
    )
    if not smartdoc_row.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DB 저장 실패: 테넌트를 찾을 수 없습니다.",
        )
    smartdoc_tenantid = smartdoc_row.data[0]["tenantid"]

    effective_tenantid = body.tenantid if body.tenantid else smartdoc_tenantid

    # accounts 테이블에 User 타입 계정 생성 (개인 가입자만)
    accountuid = None
    if body.accounttype == "U":
        try:
            account_result = service.schema(SCHEMA).table("accounts").insert({
                "accounttype": "U",
                "useruid": user_id,
                "tenantid": smartdoc_tenantid,
                "accountstatus": "Active",
                "creator": user_id,
            }).execute()
            accountuid = account_result.data[0]["accountuid"]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"DB 저장 실패 (accounts): {str(e)}",
            )

    # 공통 권한 부여 + 추가 처리
    try:
        service.schema(SCHEMA).table("tenantusers").insert({
            "tenantid": smartdoc_tenantid,
            "useruid": user_id,
            "rolecd": "U",
            "useyn": True,
            "creator": user_id,
        }).execute()

        if body.accounttype == "U" and accountuid and body.products:
            prod_rows = (
                service.schema(SCHEMA)
                .table("products")
                .select("productcd,plancd,servicecd,billingtermcd,users,credit,is_customeraikey")
                .in_("productcd", body.products)
                .eq("plancd", "Fr")
                .execute()
            )
            prod_map = {p["productcd"]: p for p in (prod_rows.data or [])}

            created_service_projects: set[str] = set()

            for productcd in body.products:
                product = prod_map.get(productcd)
                if not product:
                    continue

                servicecd = product["servicecd"]
                if servicecd not in created_service_projects:
                    proj_result = service.schema(SCHEMA).table("projects").insert({
                        "tenantid": smartdoc_tenantid,
                        "accountuid": accountuid,
                        "projectnm": f"{body.email}_{servicecd}",
                        "projectdesc": "계정에 따른 자동 생성된 프로젝트 입니다.",
                        "servicecd": servicecd,
                        "useyn": True,
                        "creator": user_id,
                    }).execute()
                    respon_projectid = proj_result.data[0]["projectid"]
                    service.schema(SCHEMA).table("projectusers").insert({
                        "projectid": respon_projectid,
                        "useruid": user_id,
                        "rolecd": "M",
                        "useyn": True,
                        "creator": user_id,
                    }).execute()
                    created_service_projects.add(servicecd)

                sub_result = service.schema(SCHEMA).table("subscriptions").insert({
                    "tenantid": smartdoc_tenantid,
                    "accountuid": accountuid,
                    "productcd": product["productcd"],
                    "plancd": product.get("plancd"),
                    "servicecd": product.get("servicecd"),
                    "billingtermcd": product.get("billingtermcd"),
                    "subscription_status": "Paid",
                    "creator": user_id,
                }).execute()
                subscriptionuid = sub_result.data[0]["subscriptionuid"]

                service.schema(SCHEMA).table("accountservices").insert({
                    "accountuid": accountuid,
                    "servicecd": product["servicecd"],
                    "tenantid": smartdoc_tenantid,
                    "subscriptionuid": subscriptionuid,
                    "servicestatus": "Active",
                    "productcd": product["productcd"],
                    "plancd": product.get("plancd"),
                    "is_customerAIKey": product.get("is_customeraikey", False),
                    "is_postpaid": False,
                    "included_users": product.get("users", 1),
                    "total_users": product.get("users", 1),
                    "is_autotopup": False,
                    "creator": user_id,
                }).execute()

                service.schema(SCHEMA).table("serviceusers").insert({
                    "accountuid": accountuid,
                    "servicecd": product["servicecd"],
                    "useruid": user_id,
                    "tenantid": smartdoc_tenantid,
                    "useyn": True,
                    "creator": user_id,
                }).execute()

                now_utc = datetime.now(timezone.utc)
                upsert_ba_creditbucket(
                    service.schema(SCHEMA),
                    subscriptionuid=subscriptionuid,
                    tenantid=smartdoc_tenantid,
                    accountuid=accountuid,
                    servicecd=product["servicecd"],
                    chargecredit=product.get("credit", 0),
                    granteddts=now_utc.isoformat(),
                    expiredts=(now_utc + relativedelta(months=1)).isoformat(),
                    startdt=now_utc.date().isoformat(),
                )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DB 저장 실패: {str(e)}",
        )

    # 해당 이메일로 대기 중인 초대(userregreqs)가 있으면 가입 완료 처리
    # (초대 가입인 경우 _invite_tenantid로 실제 처리된 테넌트 건만 범위 제한)
    try:
        q = service.schema(SCHEMA).table("userregreqs").update({
            "is_signup": True,
            "signupdts": datetime.now(timezone.utc).isoformat(),
        }).eq("email", body.email)
        if _invite_tenantid is not None:
            q = q.eq("tenantid", _invite_tenantid)
        q.execute()
    except Exception:
        pass

    return MessageResponse(ok=True, message="회원가입이 완료되었습니다.\n이메일 인증 후 로그인 가능합니다.")


# ─── MFA 관리 ────────────────────────────────────────────────────────────────

@router.get("/mfa-factors", response_model=dict)
def get_mfa_factors(token: str = Depends(get_token), tenantid: Optional[str] = Depends(get_tenantid)):
    """
    현재 사용자의 MFA factor 목록 조회.
    설정 화면에서 MFA 등록 여부 확인 및 factor_id 획득에 사용한다.
    """
    import httpx

    # access_token으로 user_id 조회
    try:
        user_client = _get_user_client(token)
        user_resp = user_client.auth.get_user(token)
        user_id = str(user_resp.user.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )

    offsetminutes = _get_offsetminutes(user_client, user_id, tenantid)

    # Admin REST API로 factor 목록 조회 (set_session 없이도 동작)
    try:
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }
        list_url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}/factors"
        res = httpx.get(list_url, headers=headers)
        factors = res.json() or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    totp_list = [
        {
            "factor_id": f.get("id"),
            "status": f.get("status"),
            "friendly_name": f.get("friendly_name", ""),
            "created_at": _fmt_dt(f.get("created_at"), offsetminutes),
        }
        for f in factors
        if f.get("factor_type") == "totp"
    ]
    return {
        "factors": totp_list,
        "mfa_enabled": any(f["status"] == "verified" for f in totp_list),
    }

@router.post("/mfa-enroll", response_model=MfaEnrollResponse)
def mfa_enroll(body: MfaEnrollRequest, token: str = Depends(get_token)):
    user_client = _get_user_client(token, body.refresh_token)

    # ── Supabase Admin REST API로 unverified factor 직접 삭제 ─────────────
    try:
        import httpx
        from backend.app.config import settings  # SUPABASE_URL, SUPABASE_SERVICE_KEY

        user_resp = user_client.auth.get_user(token)
        user_id = str(user_resp.user.id)

        # 1) factor 목록 조회 (Admin API)
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }
        list_url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}/factors"
        res = httpx.get(list_url, headers=headers)
        factors = res.json()
        # print(f"[MFA] admin factors: {factors}")

        # 2) unverified factor 삭제
        for f in (factors or []):
            if f.get("status") == "unverified":
                factor_id = f.get("id")
                del_url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}/factors/{factor_id}"
                del_res = httpx.delete(del_url, headers=headers)
                # print(f"[MFA] 삭제 결과: {factor_id} → {del_res.status_code}")

    except Exception as e:
        # print(f"[MFA] factor 정리 실패: {e}")
        pass

    try:
        resp = user_client.auth.mfa.enroll({
            "factor_type": "totp",
            "issuer": "D2Doc",
        })
    except Exception as e:
        # print(f"[MFA] enroll 실패: {e}")
        pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MFA 등록 실패: {str(e)}",
        )

    return MfaEnrollResponse(
        factor_id=resp.id,
        totp_uri=resp.totp.uri,
        secret=resp.totp.secret,
    )


@router.post("/mfa-enroll-verify", response_model=MfaEnrollVerifyResponse)
def mfa_enroll_verify(body: MfaEnrollVerifyRequest, request: Request, token: str = Depends(get_token)):
    """
    등록한 TOTP 코드를 검증하여 verified 상태로 전환한다.
    이 단계 완료 후부터 로그인 시 MFA 코드 입력이 요구된다.
    성공 시 세션이 aal2로 격상되면 그 새 토큰을 함께 반환한다(강제 설정 흐름 재개용).
    """
    user_client = _get_user_client(token, body.refresh_token or None)  # ← refresh_token 추가
    try:
        challenge_resp = user_client.auth.mfa.challenge(
            {"factor_id": body.factor_id}
        )
        # print(f"[MFA] challenge_id: {challenge_resp.id}")  # ← 추가
        verify_resp = user_client.auth.mfa.verify({
            "factor_id": body.factor_id,
            "challenge_id": challenge_resp.id,
            "code": body.code,
        })
    except Exception as e:
        # print(f"[MFA] enroll_verify 실패: {e}")  # ← 추가
        pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 코드가 올바르지 않습니다. QR 코드를 다시 스캔해주세요.",
        )

    try:
        user_id = str(user_client.auth.get_user(token).user.id)
    except Exception:
        user_id = None
    if user_id:
        from utilsPrj.audit_log import log_work_action, get_client_ip
        log_work_action(
            useruid=user_id, servicecd="Tenant",
            actioncd="update", targettype="auth/mfa", targetid=body.factor_id,
            after={"mfa_enabled": True},
            detail={"action": "enroll_verify"},
            ip=get_client_ip(request),
        )
    return MfaEnrollVerifyResponse(
        ok=True,
        message="MFA가 활성화되었습니다.",
        access_token=getattr(verify_resp, "access_token", None),
        refresh_token=getattr(verify_resp, "refresh_token", None),
    )


@router.delete("/mfa-unenroll", response_model=MessageResponse)
def mfa_unenroll(body: MfaUnenrollRequest, request: Request, token: str = Depends(get_token)):
    user_client = _get_user_client(token, body.refresh_token or None)  # ← refresh_token 추가
    try:
        user_client.auth.mfa.unenroll({"factor_id": body.factor_id})  # ← body.factor_id로
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MFA 해제 실패: {str(e)}",
        )

    try:
        user_id = str(user_client.auth.get_user(token).user.id)
    except Exception:
        user_id = None
    if user_id:
        from utilsPrj.audit_log import log_work_action, get_client_ip
        log_work_action(
            useruid=user_id, servicecd="Tenant",
            actioncd="update", targettype="auth/mfa", targetid=body.factor_id,
            before={"mfa_enabled": True}, after={"mfa_enabled": False},
            detail={"action": "unenroll"},
            ip=get_client_ip(request),
        )
    return MessageResponse(ok=True, message="MFA가 비활성화되었습니다.")


# ─── SMS 인증 ────────────────────────────────────────────────────────────────

_PHONE_REGEX = re.compile(r"^01[016789]-?\d{3,4}-?\d{4}$")
_SMS_EXPIRE_MINUTES = 5
_SMS_MAX_ATTEMPTS = 5


@router.post("/send-sms", response_model=MessageResponse)
def send_sms(body: SendSmsRequest):
    """SMS 인증번호를 발송한다."""
    phone = re.sub(r"-", "", body.phone_number)
    if not _PHONE_REGEX.match(phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바른 휴대폰 번호 형식이 아닙니다.",
        )

    code = "".join(random.choices(string.digits, k=6))
    _sms_storage[phone] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=_SMS_EXPIRE_MINUTES),
        "attempts": 0,
    }

    try:
        from utilsPrj.sms_sender import NaverSMSSender
        sender = NaverSMSSender()
        sender.send_sms(
            to_number=phone,
            content=f"[D2Doc] 인증번호: {code} (5분 이내 입력)",
        )
    except Exception as e:
        import logging
        logging.warning(f"SMS send failed: {e} | code={code}")

    return MessageResponse(ok=True, message="인증번호를 발송했습니다.")


class SwitchTenantRequest(BaseModel):
    tenantid: int
    refresh_token: Optional[str] = None


@router.post("/switch-tenant")
def switch_tenant(body: SwitchTenantRequest, request: Request, token: str = Depends(get_token)):
    """테넌트 전환: 대상 테넌트의 IP/MFA 정책을 먼저 평가하고, 통과했을 때만 users.default_tenantid를 갱신한다."""
    # refresh_token까지 넘겨야 client.auth.set_session()이 호출되어 mfa.* SDK 호출(assurance level/factor 목록)이 정상 동작한다.
    supabase = _get_user_client(token, body.refresh_token)
    user_resp = supabase.auth.get_user(token)
    if not user_resp or not user_resp.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    user_id = str(user_resp.user.id)
    sd = get_service_client().schema(SUPABASE_SCHEMA)

    ip = _get_client_ip(request)
    tu_row = (
        sd.table("tenantusers").select("rolecd, useyn")
        .eq("tenantid", body.tenantid).eq("useruid", user_id)
        .maybe_single().execute()
    )
    # 대상 테넌트의 활성 멤버가 아니면 전환 자체를 막는다 — 로그인 시 tenantids 목록이
    # tenantusers 멤버십에서만 파생되는 것과 동일 기준(_load_user_context). 여기서 막지
    # 않으면 tenantid 헤더만으로 다른 테넌트 컨텍스트를 얻어 다른 엔드포인트들을 공격할 수 있다.
    if not tu_row or not tu_row.data or tu_row.data.get("useyn") is not True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="msg.tenant.no.permission")
    is_manager = tu_row.data.get("rolecd") == "M"

    eval_result = _evaluate_tenant_access(supabase, body.tenantid, is_manager, ip)
    if eval_result["status"] == "blocked":
        reason = eval_result["reason"]
        if reason == "ip":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="msg.login.ip.not.allowed")
        if reason == "mfa_setup":
            return {"mfa_setup_required": True, "tenantid": str(body.tenantid)}
        return {"mfa_required": True, "factor_id": eval_result["factor_id"], "tenantid": str(body.tenantid)}

    sd.table("users").update({"default_tenantid": body.tenantid}).eq("useruid", user_id).execute()

    tenant_info = sd.table("tenants").select("tenantnm,disptenantnm,iconfileurl,issystemtenant").eq("tenantid", body.tenantid).maybe_single().execute()
    tenant_data = tenant_info.data if tenant_info else None

    accountuid = None
    accountstatus = None
    issystemtenant = tenant_data.get("issystemtenant", True) if tenant_data else True
    try:
        if issystemtenant:
            acc = sd.table("accounts").select("accountuid, accountstatus").eq("useruid", user_id).maybe_single().execute()
        else:
            acc = sd.table("accounts").select("accountuid, accountstatus").eq("tenantid", body.tenantid).maybe_single().execute()
        if acc and acc.data:
            accountuid = str(acc.data["accountuid"])
            accountstatus = acc.data.get("accountstatus")
    except Exception:
        pass

    # 사이드바 메뉴 노출(canSee의 TM/AM 판정)에 쓰이는 값 — 전환 시마다 갱신해야 함
    tenantmanager = "Y" if is_manager else "N"
    accountmanager = "Y" if (issystemtenant or is_manager) else "N"

    tenantnm = tenant_data.get("tenantnm", "") if tenant_data else ""
    return {
        "tenantid": str(body.tenantid),
        "tenantnm": tenantnm,
        "disptenantnm": (tenant_data.get("disptenantnm") or tenantnm) if tenant_data else "",
        "tenanticonurl": resolve_display_url(sd, tenant_data.get("iconfileurl")) if tenant_data else None,
        "accountuid": accountuid,
        "accountstatus": accountstatus,
        "tenantmanager": tenantmanager,
        "accountmanager": accountmanager,
        "issystemtenant": issystemtenant,
    }


@router.patch("/language", response_model=MessageResponse)
def update_language(body: dict, token: str = Depends(get_token)):
    """로그인 사용자의 TenantUsers.languagecd를 업데이트한다."""
    languagecd = body.get("languagecd")
    if not languagecd:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="languagecd가 필요합니다.")
    try:
        supabase = _get_user_client(token)
        user_resp = supabase.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise ValueError("user not found")
        user_id = str(user.id)
        sd = supabase.schema(SUPABASE_SCHEMA)
        sd.table("tenantusers").update({"languagecd": languagecd}).eq("useruid", user_id).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return MessageResponse(ok=True, message="언어가 변경되었습니다.")


@router.post("/verify-sms", response_model=MessageResponse)
def verify_sms(body: VerifySmsRequest):
    """SMS 인증번호를 검증한다."""
    phone = re.sub(r"-", "", body.phone_number)
    record = _sms_storage.get(phone)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증번호를 먼저 요청해주세요.",
        )

    if datetime.now(timezone.utc) > record["expires_at"]:
        _sms_storage.pop(phone, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증번호가 만료되었습니다. 다시 요청해주세요.",
        )

    record["attempts"] += 1
    if record["attempts"] > _SMS_MAX_ATTEMPTS:
        _sms_storage.pop(phone, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="시도 횟수를 초과했습니다. 다시 요청해주세요.",
        )

    if record["code"] != body.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증번호가 올바르지 않습니다.",
        )

    _sms_storage.pop(phone, None)
    return MessageResponse(ok=True, message="인증이 완료되었습니다.")


# ─── 초대 회원가입 ────────────────────────────────────────────────────────────

def _resolve_invite(req_uuid: str) -> dict:
    """userregreqs에서 초대 정보를 조회하고 servicecd → productcd 변환."""
    svc = _get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    row = sd.table("userregreqs").select("*").eq("userregrequid", req_uuid).maybe_single().execute()
    if not row or not row.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="유효하지 않은 초대 링크입니다.")

    invite = row.data
    email = invite.get("email", "")
    tenantid = invite.get("tenantid")
    servicecd = invite.get("servicecd")

    # servicecd → productcd (Free 플랜 기준)
    productcds = []
    if servicecd:
        prod_rows = (
            sd.table("products")
            .select("productcd")
            .eq("servicecd", servicecd)
            .eq("plancd", "Fr")
            .eq("useyn", True)
            .eq("is_sales", True)
            .execute()
            .data
        )
        if prod_rows:
            productcds.append(prod_rows[0]["productcd"])

    t_row = sd.table("tenants").select("tenantnm").eq("tenantid", tenantid).maybe_single().execute()
    tenantnm = t_row.data.get("tenantnm", "") if t_row and t_row.data else ""

    return {
        "email": email,
        "tenantid": str(tenantid) if tenantid else None,
        "tenantid_int": int(tenantid) if tenantid else None,
        "tenantnm": tenantnm,
        "servicecd": servicecd,
        "productcds": productcds,
    }


@router.get("/invite-info")
def get_invite_info(req: str = Query(...)):
    """초대 링크 정보 조회 (이메일·서비스 자동 채움용)."""
    invite = _resolve_invite(req)

    svc = _get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)
    existing_user = sd.table("users").select("useruid").eq("email", invite["email"]).execute().data
    already_registered = bool(existing_user)

    return {
        "email": invite["email"],
        "tenantid": invite["tenantid"],
        "tenantnm": invite["tenantnm"],
        "servicecd": invite["servicecd"],
        "productcds": invite["productcds"],
        "already_registered": already_registered,
    }


@router.post("/register-invite", response_model=MessageResponse)
def register_invite(body: RegisterInviteRequest, request: Request):
    """초대 링크를 통한 회원가입: 기존 register 로직 + 초대 테넌트에 자동 추가.

    동일 이메일로 같은 테넌트에서 여러 서비스(예: Doc, Chat) 초대가 동시에 대기 중이면,
    그중 하나의 초대 링크로 가입해도 같은 테넌트의 대기 중인 초대를 모두 함께 처리한다.
    """
    invite = _resolve_invite(body.req)
    tenantid_invite = invite["tenantid_int"]

    svc = _get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    # 같은 테넌트 + 같은 이메일로 대기 중인 초대의 servicecd 전체 취합
    pending_servicecds: list[str] = []
    if tenantid_invite:
        pending_rows = (
            sd.table("userregreqs")
            .select("servicecd")
            .eq("email", invite["email"])
            .eq("tenantid", tenantid_invite)
            .execute()
            .data or []
        )
        pending_servicecds = sorted({r["servicecd"] for r in pending_rows if r.get("servicecd")})
    if not pending_servicecds and invite["servicecd"]:
        pending_servicecds = [invite["servicecd"]]

    # servicecd → productcd (Free 플랜 기준) 전체 취합
    productcds: list[str] = []
    for servicecd in pending_servicecds:
        prod_rows = (
            sd.table("products")
            .select("productcd")
            .eq("servicecd", servicecd)
            .eq("plancd", "Fr")
            .eq("useyn", True)
            .eq("is_sales", True)
            .execute()
            .data
        )
        if prod_rows:
            productcds.append(prod_rows[0]["productcd"])

    # 기존 register 함수에 위임 (코드 재사용)
    register_body = RegisterRequest(
        email=invite["email"],
        password=body.password,
        password_confirm=body.password_confirm,
        usernm=body.usernm,
        termsofuseyn=body.termsofuseyn,
        userinfoyn=body.userinfoyn,
        electronicfinancialtermsyn=body.electronicfinancialtermsyn,
        marketingyn=body.marketingyn,
        accounttype="U",
        products=productcds,
    )
    register(register_body, request, _invite_tenantid=tenantid_invite)

    # 초대한 테넌트에 사용자 추가
    if tenantid_invite:
        smartdoc_row = sd.table("tenants").select("tenantid").eq("issystemtenant", True).execute().data
        smartdoc_tenantid = smartdoc_row[0]["tenantid"] if smartdoc_row else None

        if smartdoc_tenantid and tenantid_invite != smartdoc_tenantid:
            user_row = sd.table("users").select("useruid").eq("email", invite["email"]).execute().data
            if user_row:
                user_id = user_row[0]["useruid"]
                existing = sd.table("tenantusers").select("useruid").eq("tenantid", tenantid_invite).eq("useruid", user_id).execute().data
                if not existing:
                    sd.table("tenantusers").insert({
                        "tenantid": tenantid_invite,
                        "useruid": user_id,
                        "rolecd": "U",
                        "useyn": True,
                        "creator": user_id,
                    }).execute()

                # 초대한 테넌트의 계정으로, 대기 중이던 초대 서비스 전체에 가입 처리
                # (프로젝트는 서비스별로 구분되므로 servicecd마다 해당 프로젝트를 찾아 등록)
                if pending_servicecds:
                    acc = sd.table("accounts").select("accountuid").eq("tenantid", tenantid_invite).maybe_single().execute()
                    invite_accountuid = acc.data["accountuid"] if acc and acc.data else None
                    if invite_accountuid:
                        for servicecd in pending_servicecds:
                            pub_proj = (
                                sd.table("projects")
                                .select("projectid")
                                .eq("tenantid", tenantid_invite)
                                .eq("servicecd", servicecd)
                                .eq("projectnm", "public")
                                .execute()
                                .data
                            )
                            if pub_proj:
                                pu_existing = (
                                    sd.table("projectusers")
                                    .select("useruid")
                                    .eq("projectid", pub_proj[0]["projectid"])
                                    .eq("useruid", user_id)
                                    .execute()
                                    .data
                                )
                                if not pu_existing:
                                    sd.table("projectusers").insert({
                                        "projectid": pub_proj[0]["projectid"],
                                        "useruid": user_id,
                                        "rolecd": "U",
                                        "useyn": True,
                                        "creator": user_id,
                                    }).execute()

                            su_row = (
                                sd.table("serviceusers")
                                .select("useruid,useyn")
                                .eq("accountuid", invite_accountuid)
                                .eq("servicecd", servicecd)
                                .eq("useruid", user_id)
                                .maybe_single()
                                .execute()
                            )
                            if su_row and su_row.data:
                                if not su_row.data.get("useyn"):
                                    sd.table("serviceusers").update({"useyn": True}).eq("accountuid", invite_accountuid).eq("servicecd", servicecd).eq("useruid", user_id).execute()
                            else:
                                sd.table("serviceusers").insert({
                                    "accountuid": invite_accountuid,
                                    "servicecd": servicecd,
                                    "useruid": user_id,
                                    "tenantid": tenantid_invite,
                                    "useyn": True,
                                    "creator": user_id,
                                }).execute()

    return MessageResponse(ok=True, message="회원가입이 완료되었습니다.\n이메일 인증 후 로그인 가능합니다.")