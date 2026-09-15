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

# 비율 열은 이름 끝이 항상 이 규칙을 따른다(불량률·성장률·전환율·기여율... / Rate·Ratio·
# Share·Pct...) — 특정 보고서 단어를 나열한 목록이 아니라 비율을 가리키는 이름의 공통
# 어미다. 여기 하나로 판정하면 어떤 모듈이 어떤 이름의 비율 열을 새로 만들어도 자동으로
# %로 표시된다(2026-09-15 — 모듈마다 환산을 따로 챙기다 빠뜨린 사례가 있었다).
_RATIO_SUFFIXES_EN = ("rate", "ratio", "share", "pct", "percentage")
_RATIO_SUFFIXES_KO = ("율", "률", "비율", "비중")


def _is_ratio_column(name) -> bool:
    text = str(name).strip()
    # "Z_" 접두는 표준편차 배수(Z-score)를 가리키는 별도의 고정 통계 표기다(anomaly.py의
    # Z_rate·Z_amount 등) — 이름 끝이 "rate"와 겹쳐도 0~1 비율이 아니므로 %로 바꾸면 안 된다
    # ("6.90표준편차"가 "690%"로 둔갑하는 사례가 있었다, 2026-09-15).
    if text.startswith("Z_") or text == "Z":
        return False
    if any(text.endswith(suf) for suf in _RATIO_SUFFIXES_KO):
        return True
    lower = text.lower().replace(" ", "").replace("_", "")
    return any(lower.endswith(suf) for suf in _RATIO_SUFFIXES_EN)


def _format_column(s: pd.Series, name=None) -> pd.Series:
    """float뿐 아니라 int(예: groupby.sum() 결과)도 콤마 서식을 적용한다.
    정수는 이미 소수점이 없으므로 큰 값이든 작은 값이든 콤마만 붙이면 된다.

    name이 비율 열 이름 규칙(_is_ratio_column)에 맞으면 0~1 소수를 %로 바꿔 찍는다
    (예: -1.1826 -> "-118.26%") — 이후 LLM이 ×100을 직접 계산할 필요가 없어진다."""
    if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
        return s
    valid = s.dropna()
    if valid.empty:
        return s
    if name is not None and _is_ratio_column(name) and not pd.api.types.is_integer_dtype(s):
        return s.map(lambda v: f"{v * 100:+.2f}%" if pd.notna(v) else "")
    if pd.api.types.is_integer_dtype(s):
        fmt = "{:,.0f}"
    else:
        big = valid.abs().max() >= BIG_VALUE_THRESHOLD
        fmt = "{:,.0f}" if big else f"{{:,.{SMALL_DECIMALS}f}}"
    return s.map(lambda v: fmt.format(v) if pd.notna(v) else "")


def format_table(df: pd.DataFrame) -> pd.DataFrame:
    """표시용 사본 — 실수 열을 사람이 읽는 문자열로 바꾼다(원본 불변)."""
    out = df.copy()
    for col in out.columns:
        out[col] = _format_column(out[col], name=col)
    return out


def table_to_markdown(table) -> str:
    """DataFrame이면 서식을 적용해 마크다운으로, 아니면 문자열로.

    disable_numparse=True 필수: to_markdown()이 내부적으로 쓰는 tabulate가 기본값으로는
    이미 format_table()이 "0.0030"처럼 자릿수를 맞춰둔 문자열을 다시 숫자로 파싱해
    끝자리 0을 지워버린다(예: "0.0030"→"0.003", "0.1710"→"0.171") — 같은 표 안에서
    소수 자릿수가 3~4자리로 뒤섞이는 원인이었다.
    """
    if isinstance(table, pd.DataFrame):
        return format_table(table).to_markdown(index=False, disable_numparse=True)
    return str(table)


MONEY_UNIT_THRESHOLD = 100_000_000     # 이 이상이면 백만원, 아니면 천원 단위로 표시


def money_unit(values) -> tuple[int, str]:
    """금액 값들의 규모를 보고 나눌 배수와 단위 라벨을 고른다. 표 캡션("단위: OO")에 쓴다."""
    max_abs = max((abs(v) for v in values if pd.notna(v)), default=0.0)
    if max_abs >= MONEY_UNIT_THRESHOLD:
        return 1_000_000, "백만원"
    return 1_000, "천원"


def fmt_money(v, divisor: int, signed: bool = False) -> str:
    """금액 값 하나를 money_unit()이 고른 단위로 나눠 3자리 콤마로 표시."""
    if pd.isna(v):
        return ""
    spec = "+,.0f" if signed else ",.0f"
    return format(v / divisor, spec)


def to_korean_money(v) -> str:
    """금액을 억/만 단위 한글 표기로 변환한다(예: 3,842,356,350 -> "38억 4,236만원").

    LLM이 이 환산을 직접 하면 자릿수를 틀리는 사례가 있었다(예: 1.34억을 "134억"으로
    100배 부풀림). 계산은 파이썬이 하고, LLM은 이 문자열을 그대로 옮겨 쓰기만 한다.
    """
    if pd.isna(v):
        return ""
    sign = "-" if v < 0 else ""
    n = int(round(abs(v)))
    eok, rem = divmod(n, 100_000_000)
    man, won = divmod(rem, 10_000)
    parts = []
    if eok:
        parts.append(f"{eok:,}억")
    if man:
        parts.append(f"{man:,}만")
    if not parts:
        return f"{sign}{won:,}원"
    return f"{sign}{' '.join(parts)}원"


def korean_money_reference(df: pd.DataFrame, extra: dict | None = None) -> str:
    """금액성 열(BIG_VALUE_THRESHOLD 이상)의 억/만 표기를 미리 계산해 표로 만든다.

    LLM(모듈 해설·해설자·결론)이 억/만 단위로 쓸 때 직접 환산하면 자릿수를 틀린
    사례가 있다(예: 1.34억을 "134억"으로 100배 부풀림). 파이썬이 계산한 값을
    프롬프트에 같이 주고 LLM은 그대로 옮기게 한다. 금액성 열이 없으면 빈 문자열.

    extra: {표시 이름: 금액값} — 표에 행으로 없는 집계값(예: 전체 증감액)도 같은 참고표에
    싣는다. 서술 지침이 "전체 대비"를 요구하는데 그 전체값이 표의 행이 아닐 때, 모듈이
    이미 갖고 있는 그 값을 넘기지 않으면 LLM이 보이는 행들만으로 전체 규모를 암산하게 되고,
    그 추정이 크게 틀어진 사례가 있었다(2026-09-15).
    """
    lines: list[str] = []
    if isinstance(df, pd.DataFrame) and not df.empty:
        money_cols = [
            c for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c]) and not df[c].dropna().empty
            and df[c].dropna().abs().max() >= BIG_VALUE_THRESHOLD
        ]
        if money_cols:
            label_col = df.columns[0]
            ref = pd.DataFrame({label_col: df[label_col]})
            for c in money_cols:
                ref[c] = df[c].map(to_korean_money)
            lines.append(ref.to_markdown(index=False))
    if extra:
        lines += [f"- {k}: {to_korean_money(v)}" for k, v in extra.items() if pd.notna(v)]
    if not lines:
        return ""
    return (
        "\n[한글 단위 참고표 — 억/만으로 쓸 때는 반드시 이 값을 그대로 옮긴다. 직접 계산 금지]\n"
        + "\n".join(lines)
    )
