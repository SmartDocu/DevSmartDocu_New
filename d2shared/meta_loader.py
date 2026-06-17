"""
meta_loader.py — Supabase data_metas 공통 메타데이터 로더 (d2chat · d2insight 공유)

앱 시작 시 한 번 로드 후 모듈 수준에서 캐싱한다.
"""
from __future__ import annotations

import json

_tables_metadata: dict[str, dict] = {}
_loaded = False


def load() -> dict[str, dict]:
    """Supabase {schema}.data_metas 에서 테이블/뷰 메타정보를 로드한다."""
    global _tables_metadata, _loaded
    if _loaded:
        return _tables_metadata

    from backend.app.config import settings
    from utilsPrj.supabase_client import get_service_client

    if not settings.SUPABASE_URL or not (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY):
        print("[meta_loader] SUPABASE_URL / SUPABASE_KEY 미설정 — 메타 로드 건너뜀")
        _loaded = True
        return _tables_metadata

    try:
        client = get_service_client()
        rows = (
            client.schema(settings.SUPABASE_SCHEMA)
            .table("data_metas")
            .select("json")
            .execute()
            .data
        )
        for row in rows:
            meta = json.loads(row["json"])
            key = meta.get("physical_name") or meta.get("logical_name")
            if key:
                _tables_metadata[key] = meta

        print(f"[meta_loader] 메타 로드 완료: {list(_tables_metadata.keys())}")

    except Exception as exc:
        print(f"[meta_loader] 메타 로드 실패: {exc}")

    _loaded = True
    return _tables_metadata


def get(view_name: str) -> dict | None:
    """특정 뷰/테이블의 메타정보를 반환한다. 미로드 상태면 load()를 먼저 호출한다."""
    if not _loaded:
        load()
    return _tables_metadata.get(view_name)


def all_metadata() -> dict[str, dict]:
    """전체 메타정보 딕셔너리를 반환한다. 미로드 상태면 load()를 먼저 호출한다."""
    if not _loaded:
        load()
    return _tables_metadata


def reset() -> None:
    """테스트 등에서 캐시를 초기화할 때 사용."""
    global _tables_metadata, _loaded
    _tables_metadata = {}
    _loaded = False
