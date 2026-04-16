from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
