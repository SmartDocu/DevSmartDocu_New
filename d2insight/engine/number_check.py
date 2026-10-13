"""LLM이 쓴 문장 속 숫자가 LLM에게 준 자료에 있는지 확인한다.

프롬프트에 "새 수치를 만들지 마라"고 적는 것만으로는 막히지 않는다 — LLM이 표의 숫자 셋을 머릿속으로
더해 나눈 비율("상위 3개가 약 40%")을 써도 어길 방법을 감지하는 곳이 없었다. 이 모듈은 쓴 문장에서
숫자를 뽑아, LLM에게 준 프롬프트 전체(표·계산된 사실·한글 단위 참고표)에 같은 숫자가 있는지 코드로
대조한다. 없는 숫자는 다시 쓰게 하고(한 번), 그래도 남으면 그 숫자가 든 문장을 뺀다.

- 도메인 단어나 컬럼명을 쓰지 않는다 — 숫자 모양만 본다.
- 작은 정수(100 미만, % 없는 것)는 "3개 항목" 같은 세는 말이라 대상에서 뺀다.
- 날짜·기간 표기(2013-09, 2013년, 9월)는 대상에서 뺀다.
- 반올림은 허용한다: 자료의 1,214,629를 "1,214,629"로 쓰든, 자료의 36.04를 "36%"로 쓰든 통과.
"""
from __future__ import annotations

import logging
import re

import numpy as np

log = logging.getLogger("d2insight.number_check")

_DATE = re.compile(
    r"\d{4}\s*[-./]\s*\d{1,2}(?:\s*[-./]\s*\d{1,2})?|\d{4}\s*년|\d{1,2}\s*(?:월|일|개월|분기|주차)"
)
_NUM = re.compile(r"(?<![\w.])[+\-−±]?\d[\d,]*(?:\.\d+)?%?")
_ALWAYS_OK = {0.0, 100.0}          # "0건", "100%"는 근거 없이도 자연스럽게 쓰인다
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _to_float(raw: str) -> float | None:
    cleaned = raw.replace(",", "").replace("%", "").lstrip("+-−±")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _decimals(raw: str) -> int:
    body = raw.replace(",", "").replace("%", "")
    return len(body.split(".")[1]) if "." in body else 0


def _tokens(text: str) -> list[tuple[str, float, bool]]:
    """(원문 토큰, 절댓값, 검사 대상 여부). 날짜·기간 표기는 지우고 센다."""
    stripped = _DATE.sub(" ", text or "")
    out: list[tuple[str, float, bool]] = []
    for m in _NUM.finditer(stripped):
        raw = m.group(0)
        value = _to_float(raw)
        if value is None:
            continue
        needs = raw.endswith("%") or "." in raw or abs(value) >= 100
        out.append((raw, abs(value), needs))
    return out


def build_allowed(source_text: str) -> np.ndarray:
    """LLM에게 준 자료 전체에서 숫자를 모은다(날짜 표기 제외, 검사 대상 여부와 무관하게 전부)."""
    values = [v for _, v, _ in _tokens(source_text)]
    return np.array(values, dtype=float) if values else np.array([], dtype=float)


def _is_supported(raw: str, value: float, allowed: np.ndarray) -> bool:
    if value in _ALWAYS_OK:
        return True
    d = _decimals(raw)
    if np.any(np.isclose(np.round(allowed, d), value, atol=1e-9)):
        return True
    # 비율을 퍼센트로 옮긴 경우(자료 0.3988 → 문장 39.88%)
    if raw.endswith("%") and np.any(np.isclose(np.round(allowed * 100.0, d), value, atol=1e-9)):
        return True
    return False


def find_unverified(text: str, allowed: np.ndarray) -> list[str]:
    """문장에서 자료에 없는 숫자의 원문 토큰 목록(중복 제거, 등장 순서 유지)."""
    bad: list[str] = []
    for raw, value, needs in _tokens(text):
        if needs and not _is_supported(raw, value, allowed) and raw not in bad:
            bad.append(raw)
    return bad


def drop_sentences(text: str, bad: list[str]) -> str:
    """근거 없는 숫자가 든 문장을 뺀다. 제목 줄(#)과 숫자 없는 문장은 그대로 둔다."""
    if not bad:
        return text
    kept_lines: list[str] = []
    for line in (text or "").split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            kept_lines.append(line)
            continue
        sentences = _SENTENCE_END.split(line)
        kept = [s for s in sentences if not any(b in s for b in bad)]
        if kept:
            kept_lines.append(" ".join(kept))
    return "\n".join(kept_lines).strip()


def enforce(text: str, allowed: np.ndarray, *, rewrite=None, label: str = "") -> tuple[str, list[str]]:
    """text 속 근거 없는 숫자를 처리한다. 반환: (고친 문장, 처음 감지된 근거 없는 숫자 목록).

    rewrite: 근거 없는 숫자 목록을 받아 다시 쓴 문장(실패 시 None)을 돌려주는 함수. 한 번만 부른다.
    다시 쓴 문장이 오히려 더 나쁘면 쓰지 않는다. 그래도 남은 숫자는 그 문장째 뺀다.
    """
    if not text:
        return text, []
    bad = find_unverified(text, allowed)
    if not bad:
        return text, []
    first = list(bad)
    if rewrite is not None:
        try:
            redone = rewrite(bad)
        except Exception as e:
            log.warning("[number_check:%s] 다시 쓰기 실패: %s", label, e)
            redone = None
        if redone:
            redone_bad = find_unverified(redone, allowed)
            if len(redone_bad) <= len(bad):
                text, bad = redone, redone_bad
    if bad:
        text = drop_sentences(text, bad)
    log.warning("[number_check:%s] 근거 없는 숫자 %d개 감지 %s → %s", label, len(first), first,
                "문장 제거" if bad else "다시 쓰기로 해결")
    return text, first
