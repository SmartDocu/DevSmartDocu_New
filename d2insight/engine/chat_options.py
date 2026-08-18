"""채팅 메시지 → 편집 연산 추출 (2026-07-22 채팅 연결 작업, 2026-07-24 2단계에서 연산 형태로 전환).

사용자는 시나리오 지목과 옵션 지정을 한 문장 안에서 동시에 한다
("매출증감원인분석 보고서 작성해줘, Price는 빼고 Customer를 Volume 앞으로, Region 추가해줘").

여기서 하는 일은 그 문장을 operations.apply_operations가 받는 **편집 연산 목록**
(add/remove/move/reorder/set_param/set_tool)으로 번역하는 것뿐이다 — 실제 적용 로직은
operations.py 하나뿐이라, UI(드래그·체크·슬라이더)가 연산을 직접 만드는 경우와 결과가
같음을 보장한다. 언급 안 한 스텝·파라미터는 절대 건드리지 않는다.
"""
from __future__ import annotations

import json

from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.catalog.steps import get_step_registry
from d2insight.engine.catalog.scenarios import get_scenario
from d2insight.engine._llm import chat


def default_steps_for_scenario(scenario: str) -> list[dict]:
    """등록된 시나리오의 프리셋을 옵션 JSON의 "steps" 형태로 편다.

    각 모듈의 파라미터는 스펙 기본값 위에 프리셋이 지정한 값을 얹은 **실제 적용값**이다
    (§ plan_composition과 같은 원칙 — 빈 채로 두지 않는다).
    """
    base = get_scenario(scenario)
    if base is None:
        raise ValueError(f"등록되지 않은 시나리오: '{scenario}'")

    step_registry = get_step_registry()
    modules = get_module_registry()
    steps: list[dict] = []

    for ref in base["steps"]:
        sid = ref["step_id"]
        preset = step_registry[sid]
        modules_out = []
        for m in preset["default_modules"]:
            module_id = m["module_id"]
            spec = modules[module_id]
            params = {name: field.get("default") for name, field in spec.params.items()}
            params.update(m.get("params") or {})
            entry: dict = {"module_id": module_id, "params": params}
            tool = m.get("tools", [None])[0] if m.get("tools") else spec.tools.get("default")
            if tool:
                entry["tool"] = tool
            modules_out.append(entry)
        steps.append({"step_id": sid, "title": preset["title"], "modules": modules_out})

    return steps


def _catalog_digest(default_steps: list[dict]) -> str:
    """LLM에게 줄, 현재 스텝별 모듈·툴·파라미터 설명 + 추가 가능한 다른 카탈로그 스텝 목록."""
    modules = get_module_registry()
    steps = get_step_registry()
    present_ids = {s["step_id"] for s in default_steps}
    lines = ["[현재 포함된 스텝]"]
    for step in default_steps:
        lines.append(f"- step_id \"{step['step_id']}\" (\"{step['title']}\")")
        for m in step["modules"]:
            spec = modules[m["module_id"]]
            tools_avail = spec.tools.get("available")
            tool_txt = f" | 선택 가능 툴: {tools_avail}" if tools_avail else ""
            params_txt = ", ".join(
                f"{k}({field.get('type', 'str')}"
                + (f", 가능한 값: {'/'.join(field['enum'])}" if field.get("enum") else "")
                + ")"
                for k, field in spec.params.items()
            ) or "(없음)"
            lines.append(
                f"    module_id \"{m['module_id']}\" — 지정 가능한 파라미터: {params_txt}{tool_txt}"
            )

    others = [(sid, preset["title"]) for sid, preset in steps.items() if sid not in present_ids]
    if others:
        lines.append("\n[추가로 넣을 수 있는 다른 카탈로그 스텝 — add 연산의 step_id 후보]")
        for sid, title in others:
            lines.append(f"- step_id \"{sid}\" (\"{title}\")")

    return "\n".join(lines)


_SYSTEM = """당신은 분석 보고서 요청 문장에서, 사용자가 프리셋 기본값과 다르게 하고 싶어하는
부분을 "편집 연산" 목록으로 뽑아내는 추출기입니다. 반드시 JSON 배열만 출력하세요.

지원하는 연산(다른 연산을 지어내지 마세요):
- {"op": "remove", "step_id": "..."}
    스텝 전체 제외. "OO는 빼줘/제외해줘".
- {"op": "move", "step_id": "...", "before": "..."}  (또는 "after": "...", 또는 "at": "start"|"end")
    스텝 순서 이동. "OO를 XX 앞/뒤로", "OO를 맨 앞/뒤로".
- {"op": "add", "step_id": "...", "after": "..."}  (before/at도 가능, 생략 시 맨 뒤)
    "[추가로 넣을 수 있는 다른 카탈로그 스텝]" 목록에 있는 step_id만 쓸 수 있습니다.
- {"op": "reorder", "order": ["step_id", "step_id", ...]}
    순서를 통째로 다시 말한 경우("A, B, C 순으로"). order는 현재 스텝 전체를 담아야 합니다.
- {"op": "set_param", "step_id": "...", "module_id": "...", "params": {"top_n": 5}}
    "상위 N개", "N개까지" 같은 개수·조건 지정. "가능한 값"이 명시된 파라미터는 반드시 그
    목록 중 하나를 그대로 씁니다 — 비슷한 뜻이라도 다른 문자열을 지어내지 마세요
    (예: compare_type은 "MoM"/"QoQ"/"YoY"만 유효, "month_over_month" 같은 값은 안 됩니다).
- {"op": "set_tool", "step_id": "...", "module_id": "...", "tool": "..."}
    분석 방법(툴) 변경 요청("IQR로 바꿔줘", "샤플리로 해줘"). 그 모듈의 "선택 가능 툴" 중에서만.

규칙
1. 문장에 명시적으로(또는 아주 명확하게 함의되어) 언급된 것만 담습니다. 언급되지 않은
   스텝·모듈·파라미터는 절대 건드리지 마세요.
2. dimension/measure 값은 역할 이름(item/party/item_group/amount/quantity/discount 중 하나)으로 씁니다.
3. move·add의 위치를 알 수 없으면(그냥 "추가해줘"만 있으면) 위치 지정 없이(맨 뒤) 담습니다.
4. 여러 스텝의 순서를 한 번에 재배치하라는 요청이면 move를 여러 개 쓰지 말고 reorder 하나로 담습니다.
5. 아무 것도 언급되지 않았으면 빈 배열 []을 그대로 출력합니다.

출력 형식(다른 설명 없이 JSON 배열만): [ {"op": "...", ...}, ... ]
"""


def extract_operations(
    message: str, scenario: str, default_steps: list[dict], provider: str | None = None,
) -> list[dict]:
    """사용자 메시지를 편집 연산 목록으로 번역한다.

    실패(파싱 불가 등)하면 빈 목록을 돌려준다 — 호출부가 안전하게 프리셋 기본값으로 진행할
    수 있게 한다(조용한 실패 아님 — 호출부가 이 상황을 notes에 남긴다).
    """
    digest = _catalog_digest(default_steps)
    prompt = f"[시나리오]\n{scenario}\n\n{digest}\n\n[사용자 요청]\n{message}"
    try:
        raw = chat(
            [{"role": "user", "content": prompt}],
            grade="balanced", system=_SYSTEM, max_tokens=600,
            label="편집 연산 추출", stepnm="options_operations", steptitle="편집 연산 추출",
            provider=provider,
        )
        m = raw.strip()
        if m.startswith("```"):
            m = m.strip("`").split("\n", 1)[-1]
        operations = json.loads(m)
        if not isinstance(operations, list):
            raise ValueError(f"연산 목록이 배열이 아닙니다: {type(operations).__name__}")
        return operations
    except Exception as e:
        print(f"[chat_options] 편집 연산 추출 실패, 프리셋 기본값 사용: {e}")
        return []
