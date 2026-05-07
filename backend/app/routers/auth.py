import random
import re
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import settings
from backend.app.dependencies import get_token
from utilsPrj.supabase_client import get_thread_supabase, get_service_client, SUPABASE_SCHEMA
from backend.app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    SendResetEmailRequest,
    SendSmsRequest,
    TenantsResponse,
    TokenResponse,
    UpdatePasswordRequest,
    UserContext,
    VerifySmsRequest,
)

router = APIRouter()

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

def _load_user_context(supabase, user_id: str, email: str) -> UserContext:
    ctx = UserContext(id=user_id, email=email)
    sd = supabase.schema(SUPABASE_SCHEMA)

    # 1. 사용자 기본 정보
    mydocid = None
    try:
        user_row = (
            sd.table("users")
            .select("roleid,billingmodelcd,mydocid")
            .eq("useruid", user_id)
            .maybe_single()
            .execute()
        )
        if user_row.data:
            ctx.roleid = user_row.data.get("roleid")
            ctx.billingmodelcd = user_row.data.get("billingmodelcd")
            mydocid = user_row.data.get("mydocid")
    except Exception:
        pass

    # 2. tenantid + tenanticonurl
    try:
        tenant_rows = (
            sd.table("tenantusers")
            .select("tenantid,rolecd")
            .eq("useruid", user_id)
            .execute()
        )
        if tenant_rows.data:
            first_tenant = tenant_rows.data[0]
            tenantid_val = first_tenant.get("tenantid")
            ctx.tenantid = str(tenantid_val)

            tenant_info = (
                sd.table("tenants")
                .select("iconfileurl")
                .eq("tenantid", tenantid_val)
                .maybe_single()
                .execute()
            )

            if tenant_info.data:
                ctx.tenanticonurl = tenant_info.data.get("iconfileurl")

    except Exception:
        pass

    # 3. 문서 목록
    docid = None
    try:
        docs_row = sd.rpc("fn_docs_filtered__r_user_viewer", {"p_useruid": user_id}).execute()

        if docs_row.data:
            target_doc = None

            if mydocid:
                target_doc = next(
                    (d for d in docs_row.data if str(d.get("docid")) == str(mydocid)),
                    None,
                )

            if not target_doc:
                target_doc = docs_row.data[0]

            docid = target_doc.get("docid")
            ctx.docid = str(docid)
            ctx.docnm = target_doc.get("docnm", "")

            # mydocid가 실제 선택 docid와 다를 때 DB 동기화
            if str(docid) != str(mydocid or ""):
                try:
                    sd.table("users").update({"mydocid": docid}).eq("useruid", user_id).execute()
                except Exception:
                    pass

    except Exception:
        pass

    # 4. doc detail
    projectid = None
    sampleyn = False
    try:
        if docid:
            doc_detail = (
                sd.table("docs")
                .select("projectid,sampleyn")
                .eq("docid", docid)
                .maybe_single()
                .execute()
            )

            if doc_detail.data:
                projectid = str(doc_detail.data.get("projectid", ""))
                sampleyn = doc_detail.data.get("sampleyn", False)

                ctx.sampledocyn = "Y" if sampleyn else "N"

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
        user_tenant = (
            sd.table("tenantusers")
            .select("rolecd, useyn")
            .eq("useruid", user_id)
            .execute()
        )

        ctx.tenantmanager = (
            "Y"
            if user_tenant.data
            and any(t.get("rolecd") == "M" and t.get("useyn") is True for t in user_tenant.data)
            else "N"
        )

    except Exception:
        pass

    # 8. editbuttonyn
    if not sampleyn and (ctx.projectmanager == "Y" or ctx.tenantmanager == "Y"):
        ctx.editbuttonyn = "Y"
    elif sampleyn and ctx.roleid == 7:
        ctx.editbuttonyn = "Y"
    else:
        ctx.editbuttonyn = "N"

    # 9. languagecd: TenantUsers.languagecd → Tenants.languagecd
    try:
        lang_row = (
            sd.table("tenantusers")
            .select("languagecd, tenantid")
            .eq("useruid", user_id)
            .maybe_single()
            .execute()
        )
        if lang_row.data and lang_row.data.get("languagecd"):
            ctx.languagecd = lang_row.data["languagecd"]
        elif lang_row.data and lang_row.data.get("tenantid"):
            t_lang = (
                sd.table("tenants")
                .select("languagecd")
                .eq("tenantid", lang_row.data["tenantid"])
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
def login(body: LoginRequest):
    """이메일/비밀번호로 로그인하고 토큰과 사용자 컨텍스트를 반환한다."""
    try:
        from utilsPrj.supabase_client import get_supabase_client
        anon_client = get_supabase_client()
        auth_resp = anon_client.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    session = auth_resp.session
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인에 실패했습니다.",
        )

    user = auth_resp.user
    supabase = _get_user_client(session.access_token, session.refresh_token)
    ctx = _load_user_context(supabase, str(user.id), user.email)

    return LoginResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user=ctx,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(token: str = Depends(get_token)):
    """로그아웃: Supabase 세션을 무효화한다."""
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
    except Exception as e:
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
        client.auth.reset_password_email(
            body.email,
            options={"redirect_to": "https://dev-smart-doc.azurewebsites.net/password-reset/"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return MessageResponse(ok=True, message="비밀번호 재설정 이메일을 발송했습니다.")


@router.post("/update-password", response_model=MessageResponse)
def update_password(body: UpdatePasswordRequest):
    """복구 토큰으로 세션을 설정한 후 새 비밀번호로 변경한다."""
    try:
        from utilsPrj.supabase_client import get_thread_supabase
        sb = get_thread_supabase(
            access_token=body.access_token,
            refresh_token=body.refresh_token,
        )
        sb.auth.update_user({"password": body.new_password})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return MessageResponse(ok=True, message="비밀번호가 변경되었습니다.")


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
def register(body: RegisterRequest):
    """회원가입: Supabase auth + users 테이블 + 기본 권한 할당."""
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

    # billingmodelcd 값 결정
    # tenant 있으면 테넌트 테이블에서 조회, 없으면 single 파라미터 사용
    try:
        if body.tenantid:
            tenant_row = (
                service.schema(SCHEMA)
                .table("tenants")
                .select("billingmodelcd")
                .eq("tenantid", body.tenantid)
                .execute()
            )
            billcd = tenant_row.data[0]["billingmodelcd"]
        else:
            billcd = body.single or body.billingmodelcd
    except Exception:
        billcd = body.billingmodelcd

    # users 테이블에 사용자 정보 저장
    try:
        service.schema(SCHEMA).table("users").insert({
            "useruid": user_id,
            "email": body.email,
            "roleid": 1,
            "billingmodelcd": billcd,
            "termsofuseyn": body.termsofuseyn,
            "userinfoyn": body.userinfoyn,
            "marketingyn": body.marketingyn,
            "usernm": body.usernm,
            "useyn": True,
        }).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DB 저장 실패: {str(e)}",
        )

    # SmartDoc 기본 tenantid 조회
    smartdoc_row = (
        service.schema(SCHEMA)
        .table("tenants")
        .select("tenantid")
        .eq("issytemtenant", True)
        .execute()
    )
    if not smartdoc_row.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DB 저장 실패: SmartDoc 테넌트를 찾을 수 없습니다.",
        )
    smartdoc_tenantid = smartdoc_row.data[0]["tenantid"]

    # tenant 미선택 시 SmartDoc으로 설정
    effective_tenantid = body.tenantid if body.tenantid else smartdoc_tenantid

    # SmartDoc public 프로젝트 조회
    public_proj_row = (
        service.schema(SCHEMA)
        .table("projects")
        .select("projectid")
        .eq("projectnm", "public")
        .eq("tenantid", smartdoc_tenantid)
        .execute()
    )
    if not public_proj_row.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DB 저장 실패: SmartDoc public 프로젝트를 찾을 수 없습니다.",
        )
    public_projectid = public_proj_row.data[0]["projectid"]

    # 공통 권한 부여 + 추가 처리
    try:
        # 공통 tenantusers 삽입
        service.schema(SCHEMA).table("tenantusers").insert({
            "tenantid": smartdoc_tenantid,
            "useruid": user_id,
            "rolecd": "U",
            "useyn": True,
            "creator": user_id,
        }).execute()

        # 공통 projectusers 삽입
        service.schema(SCHEMA).table("projectusers").insert({
            "projectid": public_projectid,
            "useruid": user_id,
            "rolecd": "U",
            "useyn": True,
            "creator": user_id,
        }).execute()

        # billingmodelcd == 'single': 개인 프로젝트 생성
        if body.billingmodelcd == "single":
            proj_result = service.schema(SCHEMA).table("projects").insert({
                "tenantid": smartdoc_tenantid,
                "projectnm": body.email,
                "projectdesc": "계정에 따른 자동 생성된 프로젝트 입니다.",
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

        # 별도 테넌트 선택 시 tenantnewusers 삽입
        if body.tenantid and str(body.tenantid) != str(smartdoc_tenantid):
            service.schema(SCHEMA).table("tenantnewusers").insert({
                "tenantid": body.tenantid,
                "useruid": user_id,
                "creator": user_id,
                "approvecd": "A",
            }).execute()

        # Pro(Pr) 결제 처리
        if body.single == "Pr":
            billing_start = datetime.now().date()
            billing_end = billing_start + relativedelta(months=1) - timedelta(days=1)
            config = service.schema(SCHEMA).table("configs").select("*").execute().data[0]
            service.schema(SCHEMA).table("billmasters").insert({
                "billtargetcd": "U",
                "tenantid": effective_tenantid,
                "useruid": user_id,
                "billingmodelcd": "Pr",
                "billingfirstdt": billing_start.isoformat(),
                "useyn": True,
                "creator": user_id,
            }).execute()
            service.schema(SCHEMA).table("billdts").insert({
                "billtargetcd": "U",
                "tenantid": effective_tenantid,
                "useruid": user_id,
                "billstartdt": billing_start.isoformat(),
                "billenddt": billing_end.isoformat(),
                "billingmodelcd": "Pr",
                "inputtokencapa": config["inputtokencapa"],
                "serviceamt": config["pricepro"],
                "creator": user_id,
            }).execute()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DB 저장 실패: {str(e)}",
        )

    return MessageResponse(ok=True, message="회원가입이 완료되었습니다.\n이메일 인증 후 로그인 가능합니다.")


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
        "expires_at": datetime.now() + timedelta(minutes=_SMS_EXPIRE_MINUTES),
        "attempts": 0,
    }

    try:
        from utilsPrj.sms_sender import NaverSMSSender
        sender = NaverSMSSender()
        sender.send_sms(
            to=phone,
            content=f"[SmartDoc] 인증번호: {code} (5분 이내 입력)",
        )
    except Exception as e:
        # SMS 발송 실패 시에도 개발 환경에서는 코드를 반환 (로그로 확인)
        import logging
        logging.warning(f"SMS send failed: {e} | code={code}")

    return MessageResponse(ok=True, message="인증번호를 발송했습니다.")


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

    if datetime.now() > record["expires_at"]:
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
