# app/core/supabase_client.py
from supabase import create_client
from app.core.config import config
from fastapi import Header, HTTPException

SUPABASE_URL = config.SUPABASE_URL
SUPABASE_ANON_KEY = config.SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY = config.SUPABASE_SERVICE_KEY  # 관리자/공용용

def get_supabase_client(authorization: str | None = Header(None)):
    """
    JWT 기반 Supabase client (RLS 적용용)
    - 로그인 사용자 전용 API용
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.split(" ")[1]

    # anon key + JWT 조합으로 RLS 활성화
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.postgrest.auth(token)
    return client


def get_admin_client():
    """
    로그인 여부 상관 없는 관리자/공용용 client
    - 공용 읽기, i18n 등
    """
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)