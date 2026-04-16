import random
import re
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import settings
from backend.app.dependencies import get_token
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
    from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
    return get_service_client()


def _get_user_client(access_token: str, refresh_token: Optional[str] = None):
    """사용자 토큰 기반 Supabase 클라이언트."""
    from utilsPrj.supabase_client import get_thread_supabase
    return get_thread_supabase(access_token=access_token, refresh_token=refresh_token)


def _load_user_context(supabase, user_id: str, email: str) -> UserContext:
    """
    로그인 후 사용자 컨텍스트를 로드한다.
    mydocid 기준으로 문서를 복원하고, 해당 문서의 project/tenant/manager 권한을 설정.
    """
    ctx = UserContext(id=user_id, email=email)
    sd = supabase.schema(SUPABASE_SCHEMA)

    # 1. 사용자 기본 정보 + 마지막 선택 문서 ID(mydocid)
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

    # 2. 테넌트 아이콘 로드 (문서 선택과 무관)
    try:
        tenant_rows = (
            sd.table("tenantusers")
            .select("tenantid,rolecd")
            .eq("useruid", user_id)
            .execute()
        )
        if tenant_rows.data:
            first_tenant = tenant_rows.data[0]
            try:
                tenant_info = sd.table("tenants").select("iconfileurl").eq(
                    "tenantid", first_tenant.get("tenantid")
                ).maybe_single().execute()
                if tenant_info.data:
                    ctx.tenanticonurl = tenant_info.data.get("iconfileurl")
            except Exception:
                pass
    except Exception:
        pass

    # 3. 열람 가능한 문서 목록 조회
    try:
        docs_row = sd.rpc("fn_docs_filtered__r_user_viewer", {"p_useruid": user_id}).execute()
        if not docs_row.data:
            return ctx

        # mydocid가 있으면 해당 문서, 없으면 첫 번째 문서
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
    except Exception:
        return ctx

    # 4. 선택 문서의 projectid · sampleyn 조회
    try:
        doc_detail = (
            sd.table("docs")
            .select("projectid,sampleyn")
            .eq("docid", docid)
            .maybe_single()
            .execute()
        )
        if not doc_detail.data:
            return ctx

        projectid = str(doc_detail.data.get("projectid", ""))
        sampleyn = doc_detail.data.get("sampleyn", False)
        ctx.sampledocyn = "Y" if sampleyn else "N"
        if not sampleyn:
            ctx.editbuttonyn = "Y"
        elif sampleyn and ctx.roleid == 7:
            ctx.editbuttonyn = "Y"
        else:
            ctx.editbuttonyn = "N"
    except Exception:
        return ctx

    # 5. 프로젝트 → tenantid
    try:
        proj_detail = (
            sd.table("projects")
            .select("tenantid")
            .eq("projectid", projectid)
            .maybe_single()
            .execute()
        )
        tenantid = str(proj_detail.data.get("tenantid", "")) if proj_detail.data else ""
        ctx.projectid = projectid
        ctx.tenantid = tenantid
    except Exception:
        return ctx

    # 6. projectmanager 여부 (선택 문서의 프로젝트 기준)
    try:
        user_proj = (
            sd.table("projectusers")
            .select("rolecd")
            .eq("projectid", projectid)
            .eq("useruid", user_id)
            .execute()
        )
        ctx.projectmanager = "Y" if user_proj.data and any(p.get("rolecd") == "M" for p in user_proj.data) else "N"
    except Exception:
        pass

    # 7. tenantmanager 여부 (선택 문서의 테넌트 기준)
    try:
        if tenantid:
            user_tenant = (
                sd.table("tenantusers")
                .select("rolecd")
                .eq("tenantid", tenantid)
                .eq("useruid", user_id)
                .execute()
            )
            ctx.tenantmanager = "Y" if user_tenant.data and any(t.get("rolecd") == "M" for t in user_tenant.data) else "N"
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
    service = _get_service_client()

    # 중복 이메일 확인
    try:
        existing = (
            service.table("users")
            .select("id")
            .eq("email", body.email)
            .maybe_single()
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 사용 중인 이메일입니다.",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Supabase auth.sign_up
    try:
        auth_resp = service.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                "email_confirm": True,
            }
        )
        user_id = str(auth_resp.user.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"회원가입 실패: {str(e)}",
        )

    # users 테이블에 사용자 정보 저장
    try:
        service.table("users").insert(
            {
                "id": user_id,
                "email": body.email,
                "usernm": body.usernm,
                "phone": body.phone or "",
                "roleid": 1,
                "billingmodelcd": body.billingmodelcd,
                "termsofuseyn": body.termsofuseyn,
                "userinfoyn": body.userinfoyn,
                "marketingyn": body.marketingyn,
            }
        ).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"사용자 정보 저장 실패: {str(e)}",
        )

    # 테넌트/프로젝트 기본 권한 할당
    try:
        if body.tenantid:
            service.table("tenantusers").insert(
                {"userid": user_id, "tenantid": body.tenantid, "tenantmanager": "N"}
            ).execute()
        if body.billingmodelcd == "single":
            # 개인 프로젝트 생성
            proj_result = service.table("projects").insert(
                {"projectnm": f"{body.usernm}의 프로젝트", "tenantid": body.tenantid}
            ).execute()
            if proj_result.data:
                project_id = str(proj_result.data[0]["id"])
                service.table("projectusers").insert(
                    {"userid": user_id, "projectid": project_id, "projectmanager": "Y"}
                ).execute()
    except Exception:
        # 권한 할당 실패는 치명적이지 않으므로 로그만 남기고 계속
        pass

    return MessageResponse(ok=True, message="회원가입이 완료되었습니다.")


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
