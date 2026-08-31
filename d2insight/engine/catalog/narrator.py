"""스텝 해설자 — 같은 스텝 여러 모듈의 해설을 서로 이어지게 다듬는다 (2026-08-27 재설계).

각 모듈이 이제 자기 표·차트·해설을 스스로 LLM으로 만든다(모듈 단위 호출). 이 해설자는 그
초안을 새로 쓰는 게 아니라 **편집**한다 — 스텝 안 모듈이 2개 이상일 때만 호출되어, 앞
모듈이 짚은 것을 뒤 모듈이 받아 설명하도록 문단을 자연스럽게 이어 붙인다.

숫자 규율(핵심): 주어진 표·수치에 있는 값만 인용하고 새 수치·비율을 만들지 않는다 — 초안에
이미 없는 숫자를 추가하지 않는다.
"""
from __future__ import annotations

import json
import re

from d2insight.engine.format import korean_money_reference, table_to_markdown
from d2insight.engine._llm import chat

MAX_TABLE_ROWS = 30          # 해설자에게 보여줄 표 최대 행수
_TIER_RANK = {"none": 0, "fast": 1, "balanced": 2, "quality": 3}

_SYSTEM = """당신은 데이터 분석 보고서를 편집하는 애널리스트다.
스텝 하나에 속한 모듈마다 이미 초안 해설(narrative)이 있다. 이 초안들을 하나의 이야기로
읽히도록 다듬어 다시 쓴다 — 처음부터 새로 쓰는 게 아니다.

규칙
1. 초안과 표에 있는 숫자만 쓴다. 없는 수치·비율을 새로 계산하거나 추가하지 않는다.
2. 숫자는 원본 그대로 옮기는 게 기본이다. 억/만 등 한글 단위는 초안에 이미 쓰여 있으면 그대로
   두고, 새로 쓰려면 반드시 [한글 단위 참고표]의 값을 그대로 옮긴다 — 직접 환산하지 않는다
   (직접 계산하면 자릿수를 틀린 사례가 있다). 통화기호는 임의로 붙이지 않는다.
3. 앞 모듈이 짚은 것을 뒤 모듈이 받아 설명하듯 문단을 이어 붙인다 — 각 초안의 핵심 내용은
   보존하되, 중복되는 도입부·비슷한 표현은 정리한다.
4. 모듈당 3~6문장. 한국어 평문. 소제목·불릿·마크다운 표를 쓰지 않는다.
5. '§' 기호나 스펙 번호, 모듈 이름(module_id)을 문장에 노출하지 않는다.

출력은 JSON 객체 하나. 키는 key, 값은 다듬은 해설 문단 문자열. 그 외 텍스트는 쓰지 않는다."""


def _pick_grade(items: list[dict]) -> str:
    """스텝에 섞인 모듈 등급 중 가장 높은 등급으로 1회 호출한다."""
    grades = [(it.get("model_tier") or "balanced") for it in items]
    best = max(grades, key=lambda g: _TIER_RANK.get(g, 2))
    return best if best in ("fast", "balanced", "quality") else "balanced"


def _table_text(table) -> str:
    """해설자에게 보여줄 표. 보고서에 실리는 것과 **같은 서식**이어야 해설문의 숫자가 표와 일치한다."""
    if table is None:
        return "(표 없음)"
    try:
        head = table.head(MAX_TABLE_ROWS)
        omitted = len(table) - len(head)
    except AttributeError:
        return str(table)

    text = table_to_markdown(head)
    if omitted > 0:
        text += f"\n(이하 {omitted:,}행 생략 — 전체 통계는 위 수치 참조)"
    text += korean_money_reference(head)
    return text


def _build_prompt(step_label: str, items: list[dict], ctx) -> str:
    meta = ctx.meta or {}
    lines = [
        f"[보고서 공통] 기준월={meta.get('target_month', '미지정')}, "
        f"비교유형={meta.get('compare_type', '미지정')}",
        f"[스텝] {step_label}",
        "",
    ]
    for it in items:
        # key는 인스턴스 식별자다. 같은 모듈이 파라미터만 달리해 두 번 나올 수 있으므로
        # module_id가 아니라 key로 구분해 답해야 해설이 엉뚱한 표에 붙지 않는다.
        lines.append(f"### key: {it['key']}")
        lines.append(f"목적: {it.get('purpose') or '-'}")
        if it.get("params"):
            lines.append("파라미터: " + ", ".join(f"{k}={v}" for k, v in it["params"].items()))
        if it.get("key_value"):
            lines.append("핵심 수치: " + ", ".join(f"{k}={v}" for k, v in it["key_value"].items()))
        lines.append("초안 해설:")
        lines.append(it.get("narrative") or it.get("summary") or "(초안 없음)")
        lines.append("근거 표:")
        lines.append(_table_text(it.get("table")))
        lines.append("")
    lines.append(
        "위 각 항목의 초안 해설을 하나의 이야기로 이어지게 다듬어, **key**를 키로 하는 "
        f"JSON 객체로만 답하라. 키: {[it['key'] for it in items]}"
    )
    return "\n".join(lines)


def _parse(text: str, items: list[dict]) -> dict[str, str]:
    """LLM 응답에서 {key: 해설} 을 뽑는다. 코드펜스·잡텍스트에 관대하게."""
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]

    data = json.loads(raw)          # 실패 시 예외 → runner가 실패 기록 후 summary로 대체
    if not isinstance(data, dict):
        raise ValueError("해설자 응답이 JSON 객체가 아닙니다.")

    keys = {it["key"] for it in items}
    return {k: str(v) for k, v in data.items() if k in keys and v}


def narrate_step(step_label: str, items: list[dict], ctx) -> dict[str, str]:
    """스텝 해설 1회 호출 → {module_id: 해설 문단}."""
    if not items:
        return {}

    grade = _pick_grade(items)
    text = chat(
        [{"role": "user", "content": _build_prompt(step_label, items, ctx)}],
        grade=grade,
        system=_SYSTEM,
        label=f"narrate:{step_label}",
        is_report=True,
        call_type="narrative",
        stepnm=step_label,
        provider=(ctx.meta or {}).get("provider"),   # 채팅 요청이 고른 provider를 존중
    )
    return _parse(text, items)
