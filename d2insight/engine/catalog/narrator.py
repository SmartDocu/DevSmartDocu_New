"""스텝 해설자 — 스텝의 표·수치를 근거로 본문 해설을 쓴다 (§7.1, 결정 2026-07-14).

호출 단위는 **스텝 1회**다. 같은 스텝의 모듈들은 하나의 이야기를 이루므로, 해설자가 그 스텝의
표를 전부 보고 써야 문단들이 서로 이어진다(모듈별 호출은 서로를 모른 채 따로 논다). 대신 결과는
모듈별로 나눠 받는다 — 그래야 각 표 옆에 해설을 붙이고 layout(설명 먼저/그림 먼저)을 지킬 수 있다.

숫자 규율(핵심): 해설자는 **주어진 표·수치에 있는 값만 인용**하고 새 수치·비율을 만들지 않는다.
계산은 모듈이 이미 끝냈고, 공용 분모(total_variance)로 숫자 일관성을 확보해 두었다. 해설이 없는
비율을 지어내면 그 일관성이 텍스트에서 무너진다.

LLM에 넘기는 표는 **렌더용 표의 상위 N행**이다. 전 구간 통계는 모듈이 이미 계산해 key_value·summary로
넘기므로, 원본 수천 행을 넣을 이유가 없다.
"""
from __future__ import annotations

import json
import re

from d2insight.engine.format import table_to_markdown
from d2insight.engine._llm import chat

MAX_TABLE_ROWS = 30          # 해설자에게 보여줄 표 최대 행수
_TIER_RANK = {"none": 0, "fast": 1, "balanced": 2, "quality": 3}

_SYSTEM = """당신은 데이터 분석 보고서의 본문을 쓰는 애널리스트다.
스텝 하나에 속한 모듈들의 표와 수치를 받아, 모듈마다 해설 문단을 쓴다.

규칙
1. 주어진 표·수치에 있는 숫자만 인용한다. 없는 수치·비율·증감률을 새로 계산하거나 추정하지 않는다.
2. 숫자는 표에 적힌 값을 **그대로** 옮긴다. '만/억' 단위로 환산하지 않고, 통화 기호나 화폐 단위
   ('원', '달러' 등)를 임의로 붙이지 않는다. 예: 4,289,818 은 "4,289,818"로 쓴다.
3. 표를 그대로 읽어 나열하지 말고, 무엇이 두드러지는지·무엇을 뜻하는지 해석한다.
4. 모듈당 3~6문장. 한국어 평문. 소제목·불릿·마크다운 표를 쓰지 않는다.
5. 같은 스텝의 다른 모듈 결과와 이어지게 쓴다(앞 모듈이 짚은 것을 뒤 모듈이 받아 설명).
6. '§' 기호나 스펙 번호를 쓰지 않는다. 모듈 이름(module_id)을 문장에 노출하지 않는다.
7. 데이터가 뒷받침하지 않는 원인 단정은 피하고, 추정이면 추정임을 밝힌다.

출력은 JSON 객체 하나. 키는 module_id, 값은 해설 문단 문자열. 그 외 텍스트는 쓰지 않는다."""


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
        if it.get("narrative_hint"):
            lines.append(f"서술 지침: {it['narrative_hint']}")
        if it.get("key_value"):
            lines.append("핵심 수치: " + ", ".join(f"{k}={v}" for k, v in it["key_value"].items()))
        if it.get("summary"):
            lines.append(f"계산 결과 요약: {it['summary']}")
        lines.append("표:")
        lines.append(_table_text(it.get("table")))
        lines.append("")
    lines.append(
        "위 각 항목에 대해 해설 문단을 쓰고, **key**를 키로 하는 JSON 객체로만 답하라. "
        f"키: {[it['key'] for it in items]}"
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
