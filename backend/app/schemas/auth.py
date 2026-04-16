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
    billingmodelcd: Optional[str] = None
    docid: Optional[str] = None
    docnm: Optional[str] = None
    tenantid: Optional[str] = None
    tenantmanager: Optional[str] = "N"
    tenanticonurl: Optional[str] = None
    projectid: Optional[str] = None
    projectmanager: Optional[str] = "N"
    editbuttonyn: Optional[str] = "N"
    sampledocyn: Optional[str] = "N"


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserContext


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    usernm: str
    phone: Optional[str] = None
    termsofuseyn: str = "Y"
    userinfoyn: str = "Y"
    marketingyn: str = "N"
    billingmodelcd: str = "single"
    tenantid: Optional[str] = None


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
