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
    SUPABASE_DB_URL: str = ""   # postgresql://postgres:pw@db.xxx.supabase.co:5432/postgres

    # LLM API Keys
    CLAUDE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    # 암호화
    ENCRYPTION_KEY: str = ""

    # AWS
    AWS_REGION: str = "ap-northeast-2"
    SECRETS_TTL_SECONDS: int = 86400
    SQS_QUEUE_URL: str = ""
    SQS_CHAPTER_QUEUE_URL: str = ""

    # 이메일
    EMAIL_HOST_USER: str = ""
    EMAIL_HOST_PASSWORD: str = ""

    # PortOne (결제)
    PORTONE_STORE_ID: str = ""
    PORTONE_CHANNEL_KEY: str = ""
    PORTONE_API_SECRET: str = ""
    PORTONE_WEBHOOK_SECRET: str = ""
    BILLING_CRON_SECRET: str = ""

    # SMS (Naver Cloud)
    NAVER_ACCESS_KEY_ID: str = ""
    NAVER_SECRET_KEY: str = ""
    NAVER_SMS_SERVICE_ID: str = ""
    NAVER_SMS_FROM_NUMBER: str = ""

    # MSSQL (d2chat 전용)
    DB_DRIVER: str = ""
    DB_SERVER: str = ""
    DB_DATABASE: str = ""
    DB_USERNAME: str = ""
    DB_PASSWORD: str = ""

    # 앱 설정
    DJANGO_DEBUG: bool = True
    BASE_URL: str = "http://localhost:5174"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://d2doc-alb-2141263733.ap-northeast-2.elb.amazonaws.com",
    ]

    class Config:
        env_file = str(_ROOT_ENV)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
