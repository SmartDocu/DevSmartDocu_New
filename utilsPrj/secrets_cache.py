"""
AWS Secrets Manager + in-memory TTL cache (테넌트 단위).

- 테넌트당 시크릿 1개: smartdocu/{tenantid}/connectors
- 시크릿 내용: {connuid: {creds}, connuid2: {creds2}, ...}
- 캐시 키: tenantid (1개 엔트리로 해당 테넌트 전체 커버)
- 저장/수정/삭제는 read-modify-write로 AWS SM 업데이트 후 캐시 무효화
"""
import json
import logging
import threading
import time
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from backend.app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict = {}  # {tenantid: {data: {connuid: {...}}, expires_at: float}}

AWS_SM_MARKER = "aws-sm"  # secret_path 컬럼에 저장하는 마커값


def _ttl() -> float:
    return float(getattr(settings, "SECRETS_TTL_SECONDS", 86400))


def _client():
    return boto3.client(
        "secretsmanager",
        region_name=getattr(settings, "AWS_REGION", "ap-northeast-2"),
    )


def _secret_name(tenantid: str) -> str:
    return f"smartdocu/{tenantid}/connectors"


def _fetch_from_aws(tenantid: str) -> dict:
    """AWS SM에서 테넌트 전체 시크릿 조회. 없으면 빈 dict 반환."""
    client = _client()
    try:
        resp = client.get_secret_value(SecretId=_secret_name(tenantid))
        return json.loads(resp["SecretString"])
    except client.exceptions.ResourceNotFoundException:
        return {}


def get_connector_secret(tenantid: str, connuid: str) -> dict:
    """
    tenantid 캐시 → AWS SM → stale 캐시 순으로 조회.
    connuid에 해당하는 자격증명 dict 반환.
    """
    now = time.monotonic()

    with _lock:
        e = _cache.get(tenantid)
        if e and e["expires_at"] > now:
            return e["data"].get(connuid, {})

    try:
        data = _fetch_from_aws(tenantid)
        with _lock:
            _cache[tenantid] = {"data": data, "expires_at": now + _ttl()}
        return data.get(connuid, {})
    except (BotoCoreError, ClientError, Exception) as exc:
        logger.warning("AWS SM get 실패 tenant=%s: %s", tenantid, exc)

    with _lock:
        e = _cache.get(tenantid)
        if e:
            logger.warning("stale 캐시 사용 tenant=%s", tenantid)
            return e["data"].get(connuid, {})

    return {}


def _put_tenant_secret(tenantid: str, data: dict) -> None:
    """테넌트 시크릿 전체를 AWS SM에 upsert."""
    client = _client()
    name = _secret_name(tenantid)
    secret_str = json.dumps(data, ensure_ascii=False)
    try:
        client.put_secret_value(SecretId=name, SecretString=secret_str)
    except client.exceptions.ResourceNotFoundException:
        client.create_secret(Name=name, SecretString=secret_str)


def save_connector_secret(tenantid: str, connuid: str, creds: dict) -> None:
    """
    커넥터 자격증명 저장 (read-modify-write).
    저장 후 테넌트 캐시 무효화.
    """
    existing = _fetch_from_aws(tenantid)
    existing[connuid] = {k: v for k, v in creds.items() if v is not None}
    _put_tenant_secret(tenantid, existing)
    invalidate_tenant(tenantid)


def delete_connector_secret(tenantid: str, connuid: str) -> None:
    """
    커넥터 자격증명 삭제 (read-modify-write).
    마지막 커넥터 삭제 시 시크릿 자체도 삭제.
    """
    try:
        existing = _fetch_from_aws(tenantid)
        existing.pop(connuid, None)
        if existing:
            _put_tenant_secret(tenantid, existing)
        else:
            try:
                _client().delete_secret(
                    SecretId=_secret_name(tenantid),
                    ForceDeleteWithoutRecovery=False,
                )
            except Exception:
                pass
    except Exception as exc:
        logger.warning("delete_connector_secret 실패 tenant=%s connuid=%s: %s", tenantid, connuid, exc)
    invalidate_tenant(tenantid)


def invalidate_tenant(tenantid: str) -> None:
    """테넌트 캐시 무효화."""
    with _lock:
        _cache.pop(tenantid, None)
