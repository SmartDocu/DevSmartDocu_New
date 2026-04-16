import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings

# 프로젝트 루트에서 실행하므로 .env는 현재 디렉터리(루트)에서 찾는다
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_SCHEMA: str = ""

    # LLM API Keys
    CLAUDE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    # 암호화
    ENCRYPTION_KEY: str = ""

    # 이메일
    EMAIL_HOST_PASSWORD: str = ""

    # SMS (Naver Cloud)
    NAVER_ACCESS_KEY_ID: str = ""
    NAVER_SECRET_KEY: str = ""
    NAVER_SMS_SERVICE_ID: str = ""
    NAVER_SMS_FROM_NUMBER: str = ""

    # 앱 설정
    PROJECT_DEBUG: bool = True
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "https://dev-smart-doc.azurewebsites.net",
    ]

    class Config:
        env_file = str(_ROOT_ENV)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
