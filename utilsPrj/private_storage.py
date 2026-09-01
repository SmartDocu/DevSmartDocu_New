"""Private Storage(d2doc-private 버킷) 공용 헬퍼.

Storage RLS(Postgres 정책 기반)는 이 프로젝트에서 신뢰할 수 없다 — Storage API가
신형 JWT 서명 키(ES256)를 검증하지 못하고 모든 요청을 anon으로 취급하는 문제를
2026-09-01 실측으로 확인함(Supabase 플랫폼 쪽 이슈로 추정, storage 로그의
"role": "anon"으로 확인됨 — 로그인 사용자 JWT를 보내도 anon 취급됨).

그래서 접근 통제는 Storage 정책이 아니라 전부 이 헬퍼를 호출하는 라우터 코드에서
처리한다: 업로드/다운로드 전에 반드시 resolve_user_accountuid()로 대상 accountuid를
구하고, 실제 Storage I/O는 항상 service-role 클라이언트로 수행한다(어차피 유저 JWT로
호출해도 anon 취급되니 RLS로 막을 수 없다 — service-role로 통일하고 권한 판단은
코드가 대신한다).

경로 규칙: Users/{accountuid}/{servicecd}/...
"""
from typing import Optional

from utilsPrj.supabase_client import SUPABASE_SCHEMA

PRIVATE_BUCKET = "d2doc-private"


def resolve_user_accountuid(sb_service, tenantid: int, user_id: str) -> Optional[str]:
    """tenantid + user_id → accountuid 해석.

    시스템(개인) 테넌트면 useruid 기준, 기업 테넌트면 tenantid 기준(계정을 테넌트
    전체가 공유)으로 조회한다. org.py/payments.py의 _resolve_tenant_accountuid와
    동일한 판단 로직 — private storage 쪽에서 재사용하기 위해 공용 헬퍼로 뺐다.
    """
    sd = sb_service.schema(SUPABASE_SCHEMA)
    t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True
    if issystemtenant:
        acc = sd.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = sd.table("accounts").select("accountuid").eq("tenantid", tenantid).maybe_single().execute()
    return acc.data["accountuid"] if acc and acc.data else None


def build_private_path(accountuid: str, servicecd: str, *parts: str) -> str:
    """Users/{accountuid}/{servicecd}/{parts...} 형태로 경로를 조립."""
    segments = [p.strip("/") for p in parts if p]
    return "/".join(["Users", accountuid, servicecd, *segments])


def upload_private_file(sb_service, path: str, content: bytes, content_type: str, upsert: bool = False) -> None:
    sb_service.storage.from_(PRIVATE_BUCKET).upload(
        path, content, {"content-type": content_type, "upsert": "true" if upsert else "false"}
    )


def get_private_signed_url(sb_service, path: str, expires_in: int = 3600) -> Optional[str]:
    """만료시간(초)이 있는 서명 URL 발급. 실패하면 None."""
    try:
        res = sb_service.storage.from_(PRIVATE_BUCKET).create_signed_url(path, expires_in)
    except Exception:
        return None
    if isinstance(res, dict):
        return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    return res


def delete_private_file(sb_service, path: str) -> None:
    try:
        sb_service.storage.from_(PRIVATE_BUCKET).remove([path])
    except Exception:
        pass


def is_private_path(value: Optional[str]) -> bool:
    """DB에 저장된 값이 (구형) 공개 URL이 아니라 (신형) private 버킷 경로인지 판별.
    구형 값은 항상 http(s):// 로 시작하는 완전한 URL이었다."""
    return bool(value) and not value.startswith("http://") and not value.startswith("https://")


def resolve_display_url(sb_service, value: Optional[str]) -> Optional[str]:
    """저장된 값이 private 경로면 서명 URL로 변환, 구형 공개 URL이면 그대로 반환.
    프론트에 URL을 그대로 내려주는 모든 read 지점에서 공용으로 사용."""
    if not value:
        return value
    if is_private_path(value):
        return get_private_signed_url(sb_service, value) or value
    return value


def resolve_template_bytes(sb_service, url_or_path: Optional[str]) -> Optional[bytes]:
    """docs.basetemplateurl / chapters.chaptertemplateurl 값을 실제 바이트로 변환.
    구형(공개 URL)이면 그대로 HTTP GET, 신형(private 버킷 경로)이면 스토리지에서 직접 다운로드."""
    if not url_or_path:
        return None
    if is_private_path(url_or_path):
        return sb_service.storage.from_(PRIVATE_BUCKET).download(url_or_path)
    import requests
    resp = requests.get(url_or_path)
    resp.raise_for_status()
    return resp.content
