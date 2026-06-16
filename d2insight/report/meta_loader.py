"""data_metas 테이블에서 메타데이터를 로드한다."""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_cache: dict | None = None


def _load_from_supabase() -> dict:
    from utilsPrj.supabase_client import get_service_client
    from backend.app.config import settings
    try:
        sb = get_service_client().schema(settings.SUPABASE_SCHEMA)
        res = sb.table("data_metas").select("*").execute()
        meta: dict[str, Any] = {}
        for row in (res.data or []):
            name = row.get("physical_name") or row.get("viewnm") or row.get("name")
            if not name:
                continue
            cols_raw = row.get("columns") or []
            if isinstance(cols_raw, str):
                import json
                try:
                    cols_raw = json.loads(cols_raw)
                except Exception:
                    cols_raw = []
            meta[name] = {
                "description": row.get("description") or row.get("viewdesc") or "",
                "columns": cols_raw,
                "query": row.get("query") or "",
            }
        return meta
    except Exception as e:
        print(f"[meta_loader] 메타 로드 실패: {e}")
        return {}


def all_metadata() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load_from_supabase()
        return dict(_cache)


def refresh() -> None:
    global _cache
    with _lock:
        _cache = None
