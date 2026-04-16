import re
import json
from bs4 import BeautifulSoup
from collections import defaultdict


def extract_from_processed_html(html: str) -> list[dict]:
    """
    HTML 문서 순서 그대로 {{항목명}} 과 {{항목명}}(params) 추출
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n')

    # ✅ 함수형 + 일반형을 하나의 패턴으로 동시에 탐색
    # 함수형이 먼저 매칭되도록 | 앞에 배치 (순서 중요)
    combined_pattern = re.compile(
        r'\{\{([^}]+)\}\}\(([^)]*)\)'  # 함수형: {{이름}}(params)
        r'|\{\{([^}]+)\}\}'            # 일반형: {{이름}}
    )

    results = []

    for m in combined_pattern.finditer(text):

        # ── 함수형 매칭 ──────────────────────────────────────
        if m.group(1) is not None:
            obj_nm     = m.group(1).strip()
            raw_params = [p.strip() for p in m.group(2).split(',') if p.strip()]

            # key-value 쌍으로 묶기
            # ex) ["deviation_id", "DV-2024-001"] → {"deviation_id": "DV-2024-001"}
            param_dict = {}
            it = iter(raw_params)
            for key in it:
                try:
                    val = next(it)
                    # 숫자 변환 시도
                    try:    val = int(val)
                    except ValueError:
                        try:    val = float(val)
                        except ValueError:  pass
                    param_dict[key] = val
                except StopIteration:
                    param_dict[key] = None

            results.append({
                "objectNm": obj_nm,
                "params"  : [param_dict] if param_dict else [],
                "pos"     : m.start()   # ✅ 문서 내 위치 기록
            })

        # ── 일반형 매칭 ──────────────────────────────────────
        elif m.group(3) is not None:
            nm = m.group(3).strip()

            # FOR/IF 구문 키워드 제외
            if nm.startswith('#') or nm.startswith('@') or nm.startswith('##'):
                continue

            results.append({
                "objectNm": nm,
                "params"  : [],
                "pos"     : m.start()   # ✅ 문서 내 위치 기록
            })

    # ✅ 문서 순서 보장 (combined_pattern.finditer 는 이미 순서대로지만 명시적으로 정렬)
    results.sort(key=lambda x: x["pos"])

    # pos 키는 내부용이므로 제거
    for r in results:
        r.pop("pos")

    return results


def group_by_object(extracted: list[dict]) -> list[dict]:
    """
    같은 objectNm 끼리 params 를 합치되 첫 등장 순서 유지
    """
    grouped = defaultdict(list)
    order   = []  # 첫 등장 순서

    for item in extracted:
        nm = item["objectNm"]
        if nm not in grouped:
            order.append(nm)
        if item["params"]:
            grouped[nm].extend(item["params"])

    return [
        {"objectNm": nm, "json": grouped[nm]}
        for nm in order
    ]


def to_db_rows(grouped: list[dict]) -> list[dict]:
    """DB 저장용: objectNm / json(str)"""
    return [
        {
            "objectNm": item["objectNm"],
            "json"    : json.dumps(item["json"], ensure_ascii=False)
        }
        for item in grouped
    ]


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":

    processed_html = """
    <p><strong>111. 개요 (Executive Summary)</strong></p>
    <p>본 보고서는 제품 {{개요_제품명}}의 2024년도 검토합니다.</p>
    <ul>
        <li><strong>전체 배치 수 :</strong> {{전체배치수}}</li>
        <li><strong>생산수량 :</strong> {{생산수량}}</li>
        <li><strong>일탈건수 :</strong> {{일탈건수}}</li>
    </ul>
    <p>{{OOS표}}(deviation_id, DV-2024-001)</p>
    <p>{{OOS표}}(deviation_id, DV-2024-002)</p>
    <p>{{OOS표}}(deviation_id, DV-2024-003)</p>
    <p>{{OOS표}}(deviation_id, DV-2024-004)</p>
    <p>{{OOS표}}(deviation_id, DV-2024-005)</p>
    <p>아우</p>
    """

    extracted = extract_from_processed_html(processed_html)

    print("=== 문서 순서대로 추출 ===")
    for i, item in enumerate(extracted, 1):
        print(f"  {i:2}. {item['objectNm']:15} | {item['params']}")

    print()

    grouped = group_by_object(extracted)
    print("=== 그룹화 (첫 등장 순서 유지) ===")
    for item in grouped:
        print(f"  {item['objectNm']:15} | {item['json']}")

    print()

    db_rows = to_db_rows(grouped)
    print("=== DB 저장 형태 ===")
    for row in db_rows:
        print(f"  objectNm : {row['objectNm']}")
        print(f"  json     : {row['json']}")
        print()