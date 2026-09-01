"""Supabase 클라이언트 싱글턴 + Storage 유틸리티.

Storage는 d2doc-private(비공개) 버킷을 쓴다. qas/shares/report 전부 tenant/project 소속
사용자 개인 또는 팀 내부 자료라 공개 버킷에 둘 이유가 없다 — 다른 서비스(Doc 등)와 동일하게
Users/{accountuid}/Insight/... 구조를 따른다(utilsPrj/private_storage.py 공용 컨벤션).
"""
from __future__ import annotations

from pathlib import Path

from supabase import create_client, Client

from backend.app.config import settings
from utilsPrj.private_storage import (
    resolve_accountuid_best_effort, build_private_path,
    upload_private_file, delete_private_file, resolve_template_bytes,
)

_client: Client | None = None

_REPORT_PREFIX = "Report"


def get_client() -> Client:
    global _client
    if _client is None:
        key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        _client = create_client(settings.SUPABASE_URL, key)
    return _client


def table(name: str):
    """스키마의 테이블 접근 헬퍼."""
    schema = settings.SUPABASE_SCHEMA or "public"
    return get_client().schema(schema).table(name)


def upload_report(accountuid: str, folder_en: str, file_path: str | Path) -> str:
    """보고서 파일을 Supabase Storage에 업로드하고 저장 경로를 반환한다.

    경로: Users/{accountuid}/Insight/Report/{folder_en}/{filename}
    """
    file_path = Path(file_path)
    storage_path = build_private_path(accountuid, "Insight", _REPORT_PREFIX, folder_en, file_path.name)
    content_type = "text/markdown; charset=utf-8" if file_path.suffix == ".md" else "application/pdf"
    upload_private_file(get_client(), storage_path, file_path.read_bytes(), content_type, upsert=True)
    return storage_path


def build_qas_path(
    user_id: str | None,
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
    """Users/{accountuid}/Insight/Qas/{project}/{user}/{filename} 경로를 반환한다."""
    accountuid = resolve_accountuid_best_effort(get_client(), user_id, tenant_id) if user_id else None
    p = str(project_id) if project_id is not None else "0"
    u = user_id or "unknown"
    if not accountuid:
        # accountuid를 못 구하면(orphan 데이터 등) 기존처럼 tenant/project/user로만 구분해
        # 최소한 저장은 되게 한다 — Users/ 하위가 아니라 별도 미해결(unresolved) 영역에 둔다.
        t = str(tenant_id) if tenant_id is not None else "0"
        return f"Unresolved/Insight/Qas/{t}/{p}/{u}/{filename}"
    return build_private_path(accountuid, "Insight", "Qas", p, u, filename)


def build_shares_path(
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
    accountuid: str | None = None,
) -> str:
    """Users/{accountuid}/Insight/Shares/{project}/{filename} 경로를 반환한다."""
    p = str(project_id) if project_id is not None else "0"
    if not accountuid:
        t = str(tenant_id) if tenant_id is not None else "0"
        return f"Unresolved/Insight/Shares/{t}/{p}/{filename}"
    return build_private_path(accountuid, "Insight", "Shares", p, filename)


def delete_from_storage(storage_path: str) -> None:
    """Supabase Storage에서 파일을 삭제한다."""
    delete_private_file(get_client(), storage_path)


def copy_to_shares(
    src_path: str,
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
    accountuid: str | None = None,
) -> str:
    """qas 경로의 파일을 shares 경로로 복사하고 저장 경로를 반환한다."""
    content = resolve_template_bytes(get_client(), src_path)
    ct = "application/pdf" if filename.endswith(".pdf") else "text/markdown; charset=utf-8"
    shares_path = build_shares_path(tenant_id, project_id, filename, accountuid=accountuid)
    return upload_report_bytes(shares_path, content, ct)


def upload_report_bytes(
    storage_path: str,
    content: bytes,
    content_type: str = "text/markdown; charset=utf-8",
) -> str:
    """보고서 내용(bytes)을 Supabase Storage(private)에 직접 저장하고 저장 경로를 반환한다."""
    upload_private_file(get_client(), storage_path, content, content_type, upsert=True)
    return storage_path
