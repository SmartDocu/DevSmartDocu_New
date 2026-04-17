import re
import json
from bs4 import BeautifulSoup
from collections import defaultdict


def _normalize_template_text(text: str) -> str:
    """
    get_text() 결과에서 템플릿 파싱 전 정규화:
    1. {{ }} 와 [{ 사이에 끼어든 \n 제거
    2. 스마트 따옴표 → 일반 따옴표 변환
    """
    # 스마트 따옴표 → 일반 따옴표
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")

    # {{이름}} 과 [{ 사이의 공백/줄바꿈 제거
    text = re.sub(r'(\{\{[^}]+\}\})\s+(\[)', r'\1\2', text)

    # {{이름 내부의 줄바꿈 제거 (태그가 끼어든 경우)
    text = re.sub(r'\{\{([^}]*)\n([^}]*)\}\}', r'{{\1\2}}', text)

    return text


def extract_from_processed_html(html: str) -> list[dict]:
    """
    HTML 문서 순서 그대로 {{항목명}}, {{항목명}}(params), {{항목명}}[{...}] 추출
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n')
    text = _normalize_template_text(text)   # ← 정규화

    # JSON 브라켓형이 먼저 매칭되도록 앞에 배치 (순서 중요)
    # JSON형은 {{ }} 뒤에 [{ 가 오는 위치만 정규식으로 찾고,
    # 실제 JSON 범위는 json.JSONDecoder.raw_decode() 로 정확히 파싱
    combined_pattern = re.compile(
        r'\{\{([^}]+)\}\}(\[)'             # JSON형 시작:  {{이름}}[
        r'|\{\{([^}]+)\}\}\(([^)]*)\)'     # 구형:         {{이름}}(params)
        r'|\{\{([^}]+)\}\}'                # 일반형:       {{이름}}
    )

    decoder = json.JSONDecoder()
    results = []

    for m in combined_pattern.finditer(text):

        # ── JSON 브라켓형 매칭: {{이름}}[{...}] ──────────────
        if m.group(1) is not None:
            obj_nm     = m.group(1).strip()
            bracket_pos = m.end() - 1   # '[' 의 위치

            # '[' 부터 json.raw_decode 로 실제 배열/객체 범위를 정확히 읽음
            try:
                parsed_val, end_offset = decoder.raw_decode(text, bracket_pos)
                raw_bracket = text[bracket_pos: end_offset]   # end_offset 은 절대 위치
                replacestring  = f"{{{{{obj_nm}}}}}{raw_bracket}"

                # [{...}] → 첫 번째 dict 사용 / {...} → 그대로
                if isinstance(parsed_val, list):
                    param_dict = parsed_val[0] if parsed_val and isinstance(parsed_val[0], dict) else {}
                elif isinstance(parsed_val, dict):
                    param_dict = parsed_val
                else:
                    param_dict = {}
            except (json.JSONDecodeError, ValueError):
                param_dict = {}
                replacestring = f"{{{{{obj_nm}}}}}[...]"

            results.append({
                "objectNm"      : obj_nm,
                "params"        : param_dict,
                "replacestring" : replacestring,
                "pos"           : m.start()
            })

        # ── 구형 함수형 매칭: {{이름}}(k, v, ...) ────────────
        elif m.group(3) is not None:
            obj_nm     = m.group(3).strip()
            raw_params = [p.strip() for p in m.group(4).split(',') if p.strip()]

            param_dict = {}
            it = iter(raw_params)
            for key in it:
                try:
                    val = next(it)
                    try:    val = int(val)
                    except ValueError:
                        try:    val = float(val)
                        except ValueError:  pass
                    param_dict[key] = val
                except StopIteration:
                    param_dict[key] = None

            replacestring = f"{{{{{obj_nm}}}}}[{json.dumps(param_dict, ensure_ascii=False)}]"

            results.append({
                "objectNm"      : obj_nm,
                "params"        : param_dict if param_dict else {},
                "replacestring" : replacestring,
                "pos"           : m.start()
            })

        # ── 일반형 매칭 ──────────────────────────────────────
        elif m.group(5) is not None:
            nm = m.group(5).strip()

            # FOR/IF 구문 키워드 제외
            if nm.startswith('#') or nm.startswith('@') or nm.startswith('##'):
                continue

            results.append({
                "objectNm"      : nm,
                "params"        : {},
                "replacestring" : f"{{{{{nm}}}}}",
                "pos"           : m.start()
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