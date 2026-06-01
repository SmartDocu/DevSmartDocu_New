"""
migrate_secrets.py — 기존 커넥터 자격증명을 AWS Secrets Manager로 일괄 이전.
실행 후 삭제할 것.

사용법:
  python migrate_secrets.py            # 실제 실행
  python migrate_secrets.py --dry-run  # 확인만 (AWS/DB 변경 없음)
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
from utilsPrj.secrets_cache import _fetch_from_aws, _put_tenant_secret


def _parse_json(sp):
    """평문 JSON이면 dict 반환, 아니면 None."""
    if not sp or sp == "aws-sm":
        return None
    try:
        d = json.loads(sp)
        return d if isinstance(d, dict) and d else None
    except Exception:
        return None


def main(dry_run: bool):
    sb = get_service_client()
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}마이그레이션 시작\n")

    # ── 1. DB 커넥터 조회 ───────────────────────────────────────
    all_db = (
        sb.schema(SUPABASE_SCHEMA).table("connectors")
        .select("connuid, tenantid, secret_path")
        .eq("conntype", "db")
        .execute().data or []
    )
    db_rows = [r for r in all_db if _parse_json(r.get("secret_path"))]

    # ── 2. API 커넥터 자격증명 조회 ─────────────────────────────
    all_api = (
        sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials")
        .select("connuid, secret_path")
        .execute().data or []
    )
    api_rows = [r for r in all_api if _parse_json(r.get("secret_path"))]

    # API 커넥터의 tenantid 매핑
    api_connuids = [r["connuid"] for r in api_rows]
    conn_tenant_map: dict = {}
    if api_connuids:
        conn_rows = (
            sb.schema(SUPABASE_SCHEMA).table("connectors")
            .select("connuid, tenantid")
            .in_("connuid", api_connuids)
            .execute().data or []
        )
        conn_tenant_map = {r["connuid"]: r["tenantid"] for r in conn_rows}

    # ── 3. tenantid 기준으로 그룹핑 ────────────────────────────
    # {tenantid: {connuid: {creds}}}
    tenant_data: dict = {}

    for row in db_rows:
        creds = _parse_json(row["secret_path"])
        tid, cid = row["tenantid"], row["connuid"]
        tenant_data.setdefault(tid, {})[cid] = creds
        print(f"  DB  커넥터 | tenant={tid} | connuid={cid} | keys={list(creds.keys())}")

    for row in api_rows:
        creds = _parse_json(row["secret_path"])
        cid = row["connuid"]
        tid = conn_tenant_map.get(cid)
        if not tid:
            print(f"  [SKIP] API 커넥터 {cid}: tenantid 없음")
            continue
        tenant_data.setdefault(tid, {})[cid] = creds
        print(f"  API 커넥터 | tenant={tid} | connuid={cid} | keys={list(creds.keys())}")

    if not tenant_data:
        print("\n이전할 데이터 없음. 종료.")
        return

    total_conns = sum(len(v) for v in tenant_data.values())
    print(f"\n→ {len(tenant_data)}개 테넌트, {total_conns}개 커넥터 이전 예정\n")

    # ── 4. AWS SM 저장 ──────────────────────────────────────────
    for tenantid, connectors in tenant_data.items():
        print(f"  AWS SM 저장: tenant={tenantid} ({len(connectors)}개) ...", end=" ", flush=True)
        if not dry_run:
            existing = _fetch_from_aws(tenantid)
            existing.update(connectors)
            _put_tenant_secret(tenantid, existing)
        print("OK" if not dry_run else "SKIP")

    # ── 5. DB secret_path → "aws-sm" 업데이트 ──────────────────
    print()
    for row in db_rows:
        cid = row["connuid"]
        print(f"  DB 업데이트 (connectors)           connuid={cid} ...", end=" ", flush=True)
        if not dry_run:
            sb.schema(SUPABASE_SCHEMA).table("connectors").update(
                {"secret_path": "aws-sm"}
            ).eq("connuid", cid).execute()
        print("OK" if not dry_run else "SKIP")

    for row in api_rows:
        cid = row["connuid"]
        print(f"  DB 업데이트 (conn_api_credentials) connuid={cid} ...", end=" ", flush=True)
        if not dry_run:
            sb.schema(SUPABASE_SCHEMA).table("conn_api_credentials").update(
                {"secret_path": "aws-sm"}
            ).eq("connuid", cid).execute()
        print("OK" if not dry_run else "SKIP")

    print(f"\n{prefix}완료!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="커넥터 자격증명 → AWS Secrets Manager 이전")
    parser.add_argument("--dry-run", action="store_true", help="변경 없이 확인만")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
