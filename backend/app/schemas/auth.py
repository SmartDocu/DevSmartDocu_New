from typing import Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserContext(BaseModel):
    id: str
    email: str
    roleid: Optional[int] = None
    docid: Optional[str] = None
    docnm: Optional[str] = None
    tenantid: Optional[str] = None
    tenantnm: Optional[str] = None
    disptenantnm: Optional[str] = None
    tenantmanager: Optional[str] = "N"
    tenanticonurl: Optional[str] = None
    projectid: Optional[str] = None
    projectmanager: Optional[str] = "N"
    editbuttonyn: Optional[str] = "N"
    languagecd: Optional[str] = None
    offsetminutes: Optional[int] = None
    tenants: Optional[list] = []
    accountuid: Optional[str] = None
    accountmanager: Optional[str] = "N"


# ── 기존 LoginResponse → MFA 필드 추가 ──────────────────────────────────────
# access_token / refresh_token / user 를 Optional 로 변경한 이유:
#   MFA 등록된 사용자는 1단계 로그인 시 임시 토큰만 내려주고
#   실제 토큰은 /mfa-verify 완료 후 발급하기 때문
class LoginResponse(BaseModel):
    # ── 정상 로그인 완료 시 (MFA 없거나 MFA 검증 완료 후) ──
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserContext] = None

    # ── MFA 필요 시 (1단계 로그인 후 추가 검증 필요) ──
    mfa_required: bool = False
    factor_id: Optional[str] = None          # /mfa-verify 에 전달할 factor ID
    access_token_temp: Optional[str] = None  # aal1 임시 토큰 (MFA 검증 전용)
    refresh_token_temp: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    password_confirm: Optional[str] = None
    usernm: str
    termsofuseyn: str = "Y"
    userinfoyn: str = "Y"
    marketingyn: str = "N"
    accounttype: str = "U"
    single: Optional[str] = None
    tenantid: Optional[str] = None
    products: Optional[list[str]] = None


class RegisterInviteRequest(BaseModel):
    req: str
    usernm: str
    password: str
    password_confirm: Optional[str] = None
    termsofuseyn: str = "Y"
    userinfoyn: str = "Y"
    marketingyn: str = "N"


class SendResetEmailRequest(BaseModel):
    email: EmailStr


class SendSmsRequest(BaseModel):
    phone_number: str


class VerifySmsRequest(BaseModel):
    phone_number: str
    code: str


class UpdatePasswordRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    new_password: str


class MessageResponse(BaseModel):
    ok: bool
    message: str = ""


class TenantItem(BaseModel):
    id: str
    tenantname: str


class TenantsResponse(BaseModel):
    tenants: list[TenantItem]
    multitenantyn: str = "N"


# ── MFA 관련 스키마 ──────────────────────────────────────────────────────────

class MfaVerifyRequest(BaseModel):
    """2단계 로그인: TOTP 코드 + 1단계에서 받은 임시 토큰"""
    factor_id: str
    code: str
    access_token: str
    refresh_token: str


class MfaEnrollRequest(BaseModel):
    """MFA 등록 시작 요청"""
    refresh_token: str


class MfaEnrollResponse(BaseModel):
    """MFA 등록 시작 응답: QR 코드 렌더링에 필요한 정보"""
    factor_id: str
    totp_uri: str
    secret: str


class MfaEnrollVerifyRequest(BaseModel):
    """MFA 등록 확인: 앱 코드로 verified 상태 전환"""
    factor_id: str
    code: str
    refresh_token: Optional[str] = None


class MfaUnenrollRequest(BaseModel):
    """MFA 해제 요청"""
    factor_id: str
    refresh_token: Optional[str] = None


class MfaFactorItem(BaseModel):
    """factor 목록 조회 시 개별 항목"""
    factor_id: str
    status: str
    friendly_name: Optional[str] = None
    created_at: Optional[str] = None


class MfaFactorsResponse(BaseModel):
    """GET /mfa-factors 응답"""
    factors: list[MfaFactorItem]
    mfa_enabled: bool