"""표 표시 서식 — 보고서와 해설자가 **같은 숫자 표기**를 보게 한다.

두 곳에서 따로 서식을 정하면 해설문의 숫자와 표의 숫자가 달라 보인다. 하나로 모은다.

열 단위로 판단한다.
  - 금액처럼 큰 값(최대 절대값 ≥ 1000): 천단위 구분, 소수점 없음  → 373,646
  - 비율·지수처럼 작은 값: 소수 4자리                              → 0.0526
  - 정수 열: 그대로                                                 → 28

지수 표기(4.07e+06)는 절대 내보내지 않는다. LLM이 이를 오독해 단위를 잘못 환산한 사례가 있다.
"""
from __future__ import annotations

import json

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


def facts_json(facts: dict) -> str:
    """키: 값 묶음을 LLM에 줄 JSON 문자열로. 문장은 만들지 않는다."""
    return json.dumps(facts, ensure_ascii=False, indent=1, default=str)


def df_facts(df: pd.DataFrame) -> str:
    """표에서 pandas가 계산한 값을 키: 값(JSON)으로 만든다 — 행 수, 열별 양수·음수 행 수, 합계, 절댓값 상위 3행.

    이 표에 보이는 행 기준이다. 표 밖 항목에 대한 값은 모듈이 따로 넘긴다(extra_facts).
    열 이름을 가리지 않는다. 항목 이름은 첫 문자열 열에서 가져온다.
    """
    if not isinstance(df, pd.DataFrame) or df.empty or len(df) < 4:
        return ""
    df = df.reset_index(drop=True)
    label_col = next((c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])), None)
    stats: dict = {"행 수": len(df)}
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        col = df[c].dropna()
        if col.empty:
            continue
        item = {"양수 행 수": int((col > 0).sum()), "음수 행 수": int((col < 0).sum())}
        if col.abs().max() >= BIG_VALUE_THRESHOLD:
            top = col.loc[col.abs().nlargest(3).index]
            total, total_abs = float(col.sum()), float(col.abs().sum())
            item["합계"] = round(total, 2)
            item["절댓값 총합"] = round(total_abs, 2)
            item["절댓값 상위 3행"] = [
                {"항목": (df.at[i, label_col] if label_col else int(i)), "값": round(float(v), 2)}
                for i, v in top.items()
            ]
            item["상위 3행 값의 합"] = round(float(top.sum()), 2)
            if total:
                item["상위 3행 값의 합 ÷ 합계(%)"] = round(float(top.sum()) / total * 100, 1)
            if total_abs:
                item["상위 3행 절댓값의 합 ÷ 절댓값 총합(%)"] = round(float(top.abs().sum()) / total_abs * 100, 1)
        stats[c] = item
    return "\n[표 통계 — 이 표에 보이는 행 기준(JSON)]\n" + facts_json(stats)


# compare_type("MoM" 등)은 grain에 따라 뜻이 달라지는 내부 코드값이라, 그대로 LLM에 보여주면
# 이름 그대로("MoM"→"전월") 잘못 서술한다(dataset_builder.compare_shift 참고).
_PERIOD_COMPARE_LABEL = {"month": "전월", "quarter": "전분기", "half": "전반기", "year": "전년", "week": "전주"}
_YOY_COMPARE_LABEL = {"month": "전년 동월", "quarter": "전년 동분기", "half": "전년 동반기", "year": "전년", "week": "전년 동주"}


def compare_period_label(grain: str, compare_type: str | None) -> str:
    normalized = (compare_type or "").strip().lower()
    if normalized == "qoq":
        return "전분기(3개월 전)"
    if normalized == "yoy":
        return _YOY_COMPARE_LABEL.get(grain, "전년 동기")
    return _PERIOD_COMPARE_LABEL.get(grain, "전월")
