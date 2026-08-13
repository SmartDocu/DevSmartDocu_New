"""
tools/amount_format_tool.py — d2chat · d2insight 공통 (2026-08 pr_d2chat에서 이식)
숫자를 한글 화폐 단위(조/억/천만/백만/만/천/원)로 정확하게 변환하는 Tool.

LLM이 큰 숫자를 "OO억원", "OO조원"처럼 한글 단위로 옮기며 암산하다가 자릿수를 놓치는
오류(예: 384억원을 3,842억원 또는 3.8조원으로 잘못 읽는 것)를 막기 위함. 10억 이상에서
특히 빈발하므로, 나눗셈/반올림은 이 도구(코드)가 계산하고 LLM은 결과 문자열만 그대로 쓴다.
어느 단위까지 보여줄지(스타일)는 LLM이 정하고, 그 단위로 정확히 얼마인지(산수)는 도구가 정한다.
"""
import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from d2shared.amount_format import format_krw_amount as _format_krw_amount


class FormatAmountInput(BaseModel):
    value: float = Field(description="한글 단위로 변환할 원 단위 숫자 (예: 38412312312). 조회 결과에 이미 나와 있는 숫자를 그대로 옮겨 적으세요 - 직접 암산해서 줄이지 마세요.")
    unit: str = Field(
        default="자동",
        description=(
            "표현할 단위. '조'|'억'|'천만'|'백만'|'만'|'천'|'원' 중 하나, 또는 '자동'(가장 정밀하게 "
            "두 단위를 조합해 표기, 예: '3조 8,412억원'). 예: unit='억' → '384억원', "
            "unit='조'+decimals=1 → '3.8조원', unit='천만' → '38,412천만원'"
        ),
    )
    decimals: int = Field(
        default=0,
        description="unit을 지정했을 때 소수점 자리수 (예: unit='조', decimals=1 → '3.8조원'). '자동' 모드에서는 무시됩니다.",
    )


def format_krw_amount_tool(value: float, unit: str = "자동", decimals: int = 0) -> str:
    try:
        formatted = _format_krw_amount(value, unit=unit, decimals=decimals)
        print(f"[format_krw_amount] value={value!r} unit={unit!r} decimals={decimals!r} -> {formatted!r}")
        return json.dumps({"formatted": formatted}, ensure_ascii=False)
    except Exception as e:
        print(f"[format_krw_amount] 오류: value={value!r} unit={unit!r} decimals={decimals!r} -> {e}")
        return json.dumps({"error": f"변환 오류: {str(e)}"}, ensure_ascii=False)


def create_amount_format_tool() -> StructuredTool:
    """format_krw_amount tool 인스턴스 생성"""
    return StructuredTool(
        name="format_krw_amount",
        description=(
            "숫자를 한글 화폐 단위(조/억/천만/백만/만/천원)로 정확하게 변환. "
            "10억 이상인 숫자를 답변 문장에서 'OO억원', 'OO조원'처럼 한글 단위로 표현해야 할 때는 "
            "절대 암산하지 말고 반드시 이 도구를 호출해서 나온 문자열을 그대로 사용하세요. "
            "value에는 조회 결과에 이미 나와 있는 숫자를 그대로 넣으세요. "
            "10억 미만 숫자에는 사용하지 않아도 됩니다."
        ),
        func=format_krw_amount_tool,
        args_schema=FormatAmountInput,
    )
