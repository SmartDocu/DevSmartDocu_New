"""Supabase 클라이언트 싱글턴 + Storage 유틸리티."""
from __future__ import annotations

from pathlib import Path

from supabase import create_client, Client

from backend.app.config import settings

_client: Client | None = None

_BUCKET = "sdoc"
_REPORT_PREFIX = "insight_report"


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


def upload_report(folder_en: str, file_path: str | Path) -> str:
    """보고서 파일을 Supabase Storage에 업로드하고 Public URL을 반환한다.

    경로: sdoc/insight_report/{folder_en}/{filename}
    """
    file_path = Path(file_path)
    storage_key = f"{_REPORT_PREFIX}/{folder_en}/{file_path.name}"
    content_type = "text/markdown; charset=utf-8" if file_path.suffix == ".md" else "application/pdf"

    get_client().storage.from_(_BUCKET).upload(
        path=storage_key,
        file=file_path.read_bytes(),
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return get_client().storage.from_(_BUCKET).get_public_url(storage_key)


def build_qas_path(
    user_id: str | None,
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
    """insight/qas/{tenant}/{project}/{user}/{filename} 경로를 반환한다."""
    t = str(tenant_id) if tenant_id is not None else "0"
    p = str(project_id) if project_id is not None else "0"
    u = user_id or "unknown"
    return f"insight/qas/{t}/{p}/{u}/{filename}"


def build_shares_path(
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
    """insight/shares/{tenant}/{project}/{filename} 경로를 반환한다."""
    t = str(tenant_id) if tenant_id is not None else "0"
    p = str(project_id) if project_id is not None else "0"
    return f"insight/shares/{t}/{p}/{filename}"


def delete_from_storage(storage_path: str) -> None:
    """Supabase Storage에서 파일을 삭제한다."""
    try:
        get_client().storage.from_(_BUCKET).remove([storage_path])
    except Exception as e:
        print(f"[supabase_client] 스토리지 삭제 실패 ({storage_path}): {e}")


def copy_to_shares(
    src_url: str,
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
    """qas 경로의 파일을 shares 경로로 복사하고 public URL을 반환한다."""
    import urllib.request
    with urllib.request.urlopen(src_url) as resp:
        content = resp.read()

    ct = "application/pdf" if filename.endswith(".pdf") else "text/markdown; charset=utf-8"
    shares_path = build_shares_path(tenant_id, project_id, filename)
    return upload_report_bytes(shares_path, content, ct)


def upload_report_bytes(
    storage_path: str,
    content: bytes,
    content_type: str = "text/markdown; charset=utf-8",
) -> str:
    """보고서 내용(bytes)을 Supabase Storage에 직접 저장하고 Public URL을 반환한다."""
    get_client().storage.from_(_BUCKET).upload(
        path=storage_path,
        file=content,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return get_client().storage.from_(_BUCKET).get_public_url(storage_path)
