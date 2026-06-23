"""
meta_loader.py — Supabase data_chatmetas 공통 메타데이터 로더 (d2chat · d2insight 공유)

앱 시작 시 한 번 로드 후 모듈 수준에서 캐싱한다.
data_chatmetas → datas → connectors 경로로 DB 연결 URL도 함께 로드한다.
"""
from __future__ import annotations

import json

_tables_metadata: dict[str, dict] = {}
_db_connection_url: str | None = None
_loaded = False


def load() -> dict[str, dict]:
    """Supabase {schema}.data_chatmetas 에서 테이블/뷰 메타정보와 DB 연결 URL을 로드한다."""
    global _tables_metadata, _db_connection_url, _loaded
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
            .table("data_chatmetas")
            .select("datauid,json")
            .execute()
            .data
        )

        datauid_list = []
        for row in rows:
            if row.get("datauid"):
                datauid_list.append(row["datauid"])
            if row.get("json"):
                meta = json.loads(row["json"])
                key = meta.get("physical_name") or meta.get("logical_name")
                if key:
                    _tables_metadata[key] = meta

        print(f"[meta_loader] 메타 로드 완료: {list(_tables_metadata.keys())}")

        if datauid_list:
            _db_connection_url = _resolve_connection_url(client, datauid_list, settings.SUPABASE_SCHEMA)
            if _db_connection_url:
                print("[meta_loader] DB 연결 URL 로드 완료")
            else:
                print("[meta_loader] DB 연결 URL 로드 실패 — connuid 또는 connector 정보 없음")

    except Exception as exc:
        print(f"[meta_loader] 메타 로드 실패: {exc}")

    _loaded = True
    return _tables_metadata


def _resolve_connection_url(client, datauid_list: list, schema: str) -> str | None:
    """data_chatmetas.datauid → datas.connuid → connectors → SQLAlchemy URL."""
    from urllib.parse import quote_plus

    # 1. datas 테이블에서 connuid 조회
    try:
        datas = (
            client.schema(schema).table("datas")
            .select("connuid")
            .in_("datauid", datauid_list)
            .execute().data or []
        )
    except Exception as exc:
        print(f"[meta_loader] datas 조회 실패: {exc}")
        return None

    connuids = list({r["connuid"] for r in datas if r.get("connuid")})
    if not connuids:
        print("[meta_loader] datas에서 connuid를 찾을 수 없습니다.")
        return None

    connuid = connuids[0]

    # 2. connectors 테이블에서 접속 정보 조회
    try:
        conn_resp = (
            client.schema(schema).table("connectors")
            .select("*").eq("connuid", connuid).execute()
        )
    except Exception as exc:
        print(f"[meta_loader] connectors 조회 실패: {exc}")
        return None

    if not conn_resp.data:
        print(f"[meta_loader] connuid={connuid} 에 해당하는 커넥터가 없습니다.")
        return None

    connector = conn_resp.data[0]

    # 3. secret에서 username/password 획득
    secret_path = connector.get("secret_path") or ""
    secret: dict = {}

    if secret_path == "aws-sm":
        try:
            from utilsPrj.secrets_cache import get_connector_secret
            secret = get_connector_secret(connector.get("tenantid"), connuid)
        except Exception as exc:
            print(f"[meta_loader] AWS Secrets Manager 조회 실패: {exc}")
    elif secret_path:
        try:
            secret = json.loads(secret_path)
        except Exception:
            pass

    username = secret.get("username", "")
    password = secret.get("password", "")
    server = connector.get("server") or ""
    db = connector.get("db") or ""
    dbtype = (connector.get("dbtype") or "mssql").lower()

    # 4. dbtype별 SQLAlchemy URL 생성
    if "mssql" in dbtype:
        odbc = (
            "Driver={ODBC Driver 17 for SQL Server};"
            f"Server={server},1433;"
            f"Database={db};"
            f"UID={username};"
            f"PWD={password};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"

    if dbtype == "postgres":
        return f"postgresql+psycopg2://{quote_plus(username)}:{quote_plus(password)}@{server}/{db}"

    if dbtype == "mysql":
        return f"mysql+pymysql://{quote_plus(username)}:{quote_plus(password)}@{server}/{db}"

    print(f"[meta_loader] 지원하지 않는 dbtype: {dbtype}")
    return None


def get_connection_url() -> str | None:
    """캐시된 DB 연결 URL을 반환한다. 미로드 상태면 load()를 먼저 호출한다."""
    if not _loaded:
        load()
    return _db_connection_url


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
    global _tables_metadata, _db_connection_url, _loaded
    _tables_metadata = {}
    _db_connection_url = None
    _loaded = False
