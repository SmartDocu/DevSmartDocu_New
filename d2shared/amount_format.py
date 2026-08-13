"""
amount_format.py — 금액을 한글 화폐 단위(조/억/천만/백만/만/천/원)로 정확하게 변환하는 공용 유틸.
d2chat · d2insight 공통 (2026-08 pr_d2chat에서 이식).

LLM이 큰 숫자를 "OO억원", "OO조원"처럼 한글 단위로 옮기며 암산하다가 자릿수를 놓치는 오류
(예: 68,146,317원을 "68억 1천만원"으로 잘못 읽는 것 — 100배 부풀림)를 막기 위한 것.
나눗셈/반올림은 이 모듈(코드)이 계산하고, LLM은 결과 문자열만 그대로 옮겨 쓴다.

두 곳에서 공유해서 쓴다:
- tools/amount_format_tool.py: LLM이 필요하면 직접 호출하는 도구
- annotate_amounts(): mcp_server.py/excel_server.py의 SQL/pandas 조회 결과에 애초에 한글
  표기를 미리 계산해 끼워넣는 후처리 — LLM이 숫자를 아예 옮겨 적을 필요조차 없게 만드는,
  더 근본적인 방어선
"""
from typing import Any, Dict, List

_UNIT_DIVISORS = {
    "조": 10**12,
    "억": 10**8,
    "천만": 10**7,
    "백만": 10**6,
    "만": 10**4,
    "천": 10**3,
    "원": 1,
}

# 조회 결과 후처리(annotate_amounts) 전용 설정
AMOUNT_ANNOTATE_THRESHOLD = 1_000_000  # 100만원 이상이면 한글 표기를 같이 붙여준다
_RATIO_KEYWORDS = ('율', '률', '비율', '%', 'rate', 'ratio', 'pct', 'percent')


def format_auto(v: int) -> str:
    """단위 미지정 시: 가장 정밀한 두 단위 조합(조+억, 억+만, 만+천 등)으로 표기"""
    if v >= 10**12:
        jo, rem = divmod(v, 10**12)
        eok = rem // 10**8
        return f"{jo:,}조 {eok:,}억원" if eok else f"{jo:,}조원"
    if v >= 10**8:
        eok, rem = divmod(v, 10**8)
        man = rem // 10**4
        return f"{eok:,}억 {man:,}만원" if man else f"{eok:,}억원"
    if v >= 10**4:
        man, rem = divmod(v, 10**4)
        cheon = rem // 10**3
        return f"{man:,}만 {cheon:,}천원" if cheon else f"{man:,}만원"
    if v >= 10**3:
        return f"{v // 10**3:,}천원"
    return f"{v:,}원"


def format_krw_amount(value: float, unit: str = "자동", decimals: int = 0) -> str:
    is_negative = value < 0
    v = round(abs(value))
    sign = "-" if is_negative else ""

    if unit == "자동" or unit not in _UNIT_DIVISORS:
        return sign + format_auto(v)

    if unit == "원":
        return f"{sign}{v:,}원"

    divisor = _UNIT_DIVISORS[unit]
    scaled = v / divisor
    num_str = f"{scaled:,.{decimals}f}" if decimals > 0 else f"{round(scaled):,}"
    return f"{sign}{num_str}{unit}원"


def _is_ratio_like(key: str) -> bool:
    return any(kw in str(key).lower() for kw in _RATIO_KEYWORDS)


def annotate_amounts(data: List[Dict[str, Any]], threshold: int = AMOUNT_ANNOTATE_THRESHOLD) -> List[Dict[str, Any]]:
    """조회 결과(list[dict])의 각 행을 돌면서, 금액으로 보이는 숫자 컬럼 옆에
    "{컬럼명}_한글" 필드로 억/만 단위 한글 표기 문자열을 추가한 새 리스트를 반환한다.

    비율/퍼센트류 컬럼(이름에 '율'/'%' 등이 있는 경우)은 금액이 아니므로 제외한다.
    threshold 미만인 작은 숫자는 굳이 억/만 단위로 안 써도 되므로 건드리지 않는다.
    원본 data는 변경하지 않고 새 리스트/딕셔너리를 반환한다.
    """
    if not data:
        return data

    annotated = []
    for row in data:
        if not isinstance(row, dict):
            annotated.append(row)
            continue
        new_row = dict(row)
        for key, value in row.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if abs(value) < threshold:
                continue
            if _is_ratio_like(key):
                continue
            new_row[f"{key}_한글"] = format_krw_amount(value)
        annotated.append(new_row)
    return annotated
