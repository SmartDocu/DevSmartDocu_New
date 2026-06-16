"""Supabase 서비스 롤 클라이언트 래퍼 + Storage 유틸리티."""
from __future__ import annotations

from pathlib import Path

_BUCKET = "sdoc"
_REPORT_PREFIX = "insight_report"


def _sc():
    from utilsPrj.supabase_client import get_service_client
    from backend.app.config import settings
    return get_service_client().schema(settings.SUPABASE_SCHEMA)


def table(name: str):
    return _sc().table(name)


def upload_report(folder_en: str, file_path: str | Path) -> str:
    from utilsPrj.supabase_client import get_service_client
    client = get_service_client()
    file_path = Path(file_path)
    storage_key = f"{_REPORT_PREFIX}/{folder_en}/{file_path.name}"
    content_type = "text/markdown; charset=utf-8" if file_path.suffix == ".md" else "application/pdf"
    client.storage.from_(_BUCKET).upload(
        path=storage_key,
        file=file_path.read_bytes(),
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return client.storage.from_(_BUCKET).get_public_url(storage_key)


def build_qas_path(
    user_id: str | None,
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
    t = str(tenant_id) if tenant_id is not None else "0"
    p = str(project_id) if project_id is not None else "0"
    u = user_id or "unknown"
    return f"insight/qas/{t}/{p}/{u}/{filename}"


def build_shares_path(
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
    t = str(tenant_id) if tenant_id is not None else "0"
    p = str(project_id) if project_id is not None else "0"
    return f"insight/shares/{t}/{p}/{filename}"


def delete_from_storage(storage_path: str) -> None:
    try:
        from utilsPrj.supabase_client import get_service_client
        get_service_client().storage.from_(_BUCKET).remove([storage_path])
    except Exception as e:
        print(f"[supabase_client] 스토리지 삭제 실패 ({storage_path}): {e}")


def copy_to_shares(
    src_url: str,
    tenant_id: int | None,
    project_id: int | None,
    filename: str,
) -> str:
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
    from utilsPrj.supabase_client import get_service_client
    client = get_service_client()
    client.storage.from_(_BUCKET).upload(
        path=storage_path,
        file=content,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return client.storage.from_(_BUCKET).get_public_url(storage_path)
