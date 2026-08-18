"""표 표시 서식 — 보고서와 해설자가 **같은 숫자 표기**를 보게 한다.

두 곳에서 따로 서식을 정하면 해설문의 숫자와 표의 숫자가 달라 보인다. 하나로 모은다.

열 단위로 판단한다.
  - 금액처럼 큰 값(최대 절대값 ≥ 1000): 천단위 구분, 소수점 없음  → 373,646
  - 비율·지수처럼 작은 값: 소수 4자리                              → 0.0526
  - 정수 열: 그대로                                                 → 28

지수 표기(4.07e+06)는 절대 내보내지 않는다. LLM이 이를 오독해 단위를 잘못 환산한 사례가 있다.
"""
from __future__ import annotations

import pandas as pd

BIG_VALUE_THRESHOLD = 1000.0     # 이 이상이면 금액성 열로 보고 소수점을 버린다
SMALL_DECIMALS = 4


def _format_column(s: pd.Series) -> pd.Series:
    if not pd.api.types.is_float_dtype(s):
        return s
    valid = s.dropna()
    if valid.empty:
        return s
    big = valid.abs().max() >= BIG_VALUE_THRESHOLD
    fmt = "{:,.0f}" if big else f"{{:,.{SMALL_DECIMALS}f}}"
    return s.map(lambda v: fmt.format(v) if pd.notna(v) else "")


def format_table(df: pd.DataFrame) -> pd.DataFrame:
    """표시용 사본 — 실수 열을 사람이 읽는 문자열로 바꾼다(원본 불변)."""
    out = df.copy()
    for col in out.columns:
        out[col] = _format_column(out[col])
    return out


def table_to_markdown(table) -> str:
    """DataFrame이면 서식을 적용해 마크다운으로, 아니면 문자열로."""
    if isinstance(table, pd.DataFrame):
        return format_table(table).to_markdown(index=False)
    return str(table)
