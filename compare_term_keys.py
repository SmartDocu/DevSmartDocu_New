"""
docs/term_keys.md 와 Supabase DB(ui_terms, ui_term_translations) 비교 스크립트
실행: python compare_term_keys.py
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

# 비교 제외 prefix: 별도 관리 대상 (cod/faq/prm/mnu 는 term_keys.md 에서 관리하지 않음)
EXCLUDED_PREFIXES = ("cod.", "faq.", "prm.", "mnu.")


def parse_md_keys(filepath: str) -> set[str]:
    keys = set()
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # | key | 형식, 헤더/구분선 제외
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[-\s|]+\|$", line):
                continue
            cell = line.strip("|").strip()
            if cell and cell != "term_key" and "." in cell and " " not in cell:
                keys.add(cell)
    return keys


def fetch_all(sb, schema: str, table: str, select: str, filters: dict = None) -> list:
    rows, offset, batch = [], 0, 1000
    while True:
        q = sb.schema(schema).table(table).select(select).range(offset, offset + batch - 1)
        for k, v in (filters or {}).items():
            q = q.eq(k, v)
        r = q.execute()
        rows.extend(r.data)
        if len(r.data) < batch:
            break
        offset += batch
    return rows


def fetch_db_data():
    sb = get_service_client()
    schema = SUPABASE_SCHEMA or "sdoc"

    db_keys = {row["term_key"] for row in fetch_all(sb, schema, "ui_terms", "term_key")}
    en_keys = {row["term_key"] for row in fetch_all(sb, schema, "ui_term_translations", "term_key", {"language_cd": "en"})}
    ko_keys = {row["term_key"] for row in fetch_all(sb, schema, "ui_term_translations", "term_key", {"language_cd": "ko"})}

    return db_keys, en_keys, ko_keys


def print_section(title: str, items: set[str]):
    print(f"\n{'='*60}")
    print(f"  {title}  ({len(items)}개)")
    print("="*60)
    for k in sorted(items):
        print(f"  {k}")


def main():
    md_path = os.path.join(os.path.dirname(__file__), "docs", "term_keys.md")
    print(f"MD 파일: {md_path}")

    md_keys = parse_md_keys(md_path)
    print(f"MD 키 수: {len(md_keys)}")

    print("DB 조회 중...")
    db_keys, en_keys, ko_keys = fetch_db_data()
    print(f"DB ui_terms 키 수: {len(db_keys)}")
    print(f"DB en 번역 수: {len(en_keys)}")
    print(f"DB ko 번역 수: {len(ko_keys)}")

    # 제외 prefix 필터링
    def exclude(keys: set[str]) -> set[str]:
        return {k for k in keys if not k.startswith(EXCLUDED_PREFIXES)}

    md_keys = exclude(md_keys)
    db_keys = exclude(db_keys)
    en_keys = exclude(en_keys)
    ko_keys = exclude(ko_keys)

    only_md = md_keys - db_keys
    only_db = db_keys - md_keys
    no_en = db_keys - en_keys
    no_ko = db_keys - ko_keys

    if only_md:
        print_section("MD에만 있음 (DB INSERT 필요)", only_md)
    else:
        print("\n[OK] MD에만 있는 키 없음")

    if only_db:
        print_section("DB에만 있음 (MD 업데이트 필요)", only_db)
    else:
        print("[OK] DB에만 있는 키 없음")

    if no_en:
        print_section("en 번역 없음", no_en)
    else:
        print("[OK] en 번역 누락 없음")

    if no_ko:
        print_section("ko 번역 없음", no_ko)
    else:
        print("[OK] ko 번역 누락 없음")

    print(f"\n{'='*60}")
    print(f"  요약")
    print(f"{'='*60}")
    print(f"  MD 키 수      : {len(md_keys)}")
    print(f"  DB 키 수      : {len(db_keys)}")
    print(f"  MD에만 있음   : {len(only_md)}")
    print(f"  DB에만 있음   : {len(only_db)}")
    print(f"  en 번역 누락  : {len(no_en)}")
    print(f"  ko 번역 누락  : {len(no_ko)}")


if __name__ == "__main__":
    main()
