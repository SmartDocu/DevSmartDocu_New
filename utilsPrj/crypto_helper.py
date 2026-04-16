# utils/crypto_helper.py
import base64
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def _get_fernet() -> Fernet:
    """Django 컨텍스트에서는 settings.FERNET, FastAPI 컨텍스트에서는 env var 직접 사용."""
    try:
        from django.conf import settings
        return settings.FERNET
    except Exception:
        pass
    key = os.environ.get('ENCRYPTION_KEY') or os.getenv('ENCRYPTION_KEY')
    if not key:
        raise ValueError("ENCRYPTION_KEY 환경변수가 설정되지 않았습니다.")
    return Fernet(key.encode())


def encrypt_value(value: str) -> str:
    """문자열 → Fernet 암호화 → Base64 문자열"""
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(value.encode())
    return base64.b64encode(encrypted_bytes).decode()


def decrypt_value(encrypted_base64: str) -> str:
    """Base64 문자열 → Fernet 복호화 → 평문"""
    fernet = _get_fernet()
    encrypted_bytes = base64.b64decode(encrypted_base64.encode())
    return fernet.decrypt(encrypted_bytes).decode()
