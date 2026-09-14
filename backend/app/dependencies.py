from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthApiError

from backend.app.config import settings

security = HTTPBearer(auto_error=False)


def get_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Authorization 헤더에서 Bearer 토큰을 추출한다."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_optional_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """토큰이 없어도 허용하는 옵셔널 버전."""
    if credentials is None:
        return None
    return credentials.credentials


def get_sb(token: str):
    """토큰 기반 Supabase 클라이언트 반환 (라우터 공용)."""
    from utilsPrj.supabase_client import get_thread_supabase
    return get_thread_supabase(access_token=token)


def get_user(token: str):
    """토큰으로 인증된 Supabase 유저 반환 (라우터 공용)."""
    sb = get_sb(token)
    try:
        resp = sb.auth.get_user(token)
    except AuthApiError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었습니다.",
        )
    if not resp or not resp.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
        )
    return resp.user


def get_tenantid(x_tenant_id: Optional[str] = Header(None)) -> Optional[str]:
    """X-Tenant-ID 헤더에서 현재 선택된 tenantid를 추출한다."""
    return x_tenant_id


def _require_service_permission(servicecd: str, need: str):
    """accountservices.servicestatus(servicecd) 기준 읽기/쓰기 권한 확인 dependency를 생성한다.

    청구 실패로 PastDue/Suspended가 되면 utilsPrj/service_status.py의 get_service_permission()이
    can_read/can_write를 False로 판정 — 불허 시 403(msg.service.{need}.forbidden, 서비스 공통 키).
    """
    def _dep(
        token: str = Depends(get_token),
        tenantid: Optional[str] = Depends(get_tenantid),
    ) -> None:
        from utilsPrj.service_status import get_service_permission

        sb = get_sb(token)
        user = get_user(token)
        perm = get_service_permission(sb, tenantid, str(user.id), servicecd)
        if not perm[f"can_{need}"]:
            raise HTTPException(status_code=403, detail=f"msg.service.{need}.forbidden")

    return _dep


require_doc_read = _require_service_permission("Do", "read")
require_doc_write = _require_service_permission("Do", "write")
require_chat_read = _require_service_permission("Ch", "read")
require_chat_write = _require_service_permission("Ch", "write")
require_insight_read = _require_service_permission("In", "read")
require_insight_write = _require_service_permission("In", "write")


def require_login(token: str = Depends(get_token)) -> None:
    """로그인 여부만 확인 — 서비스(Do/Ch/In) 구독·결제 상태와 무관하게 통과시킨다.

    마스터(MGR) 앱은 apps.servicecd가 null이라 특정 서비스 구독 여부와 무관하게 접근 가능하도록
    설계되어 있는데(canSeeApp()의 !rolecd 분기 참고), 정작 마스터 화면들이 쓰는 datas/docs/chapters/
    objects/tables/sentences/charts 라우터가 require_doc_read/write(= Do 서비스 구독 확인)에 걸려
    있어서 Do 서비스를 구독하지 않은 테넌트는 마스터 앱에 들어와도 데이터를 못 읽는 문제가 있었다
    (2026-09-09). 이 라우터들은 실제 문서 생성(req/* → gendocs.py, docgroups.py)과는 분리된 마스터
    데이터 관리 기능이므로, 여기서는 로그인 여부만 확인한다.
    """
    get_user(token)


def get_supabase(token: str = Depends(get_token)):
    """
    요청별 Supabase 클라이언트를 반환한다.
    utilsPrj.supabase_client는 프로젝트 루트에서 실행 시 임포트 가능하다.
    Stage 2에서 인증 미들웨어와 함께 완성된다.
    """
    try:
        from utilsPrj.supabase_client import get_thread_supabase
        return get_thread_supabase(access_token=token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"데이터베이스 연결 실패: {str(e)}",
        )
