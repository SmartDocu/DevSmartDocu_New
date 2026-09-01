"""조립 매트릭스 — 스텝×모듈, 모듈×툴 (2026-09-01).

행이 스텝, 열이 모듈이고, 그 스텝에 어울리는 모듈이면 O, 아니면 빈칸이다.

    ┌────────────────┬───────────┬──────────┬─────────────┐
    │                │ new_party │ pnl_cogs │ composition │
    ├────────────────┼───────────┼──────────┼─────────────┤
    │ 고객 매출 기여도│     O     │          │      O      │
    │ 매출원가(COGS) │           │    O     │      O      │
    └────────────────┴───────────┴──────────┴─────────────┘

판정 근거는 **주제(topic)** 하나뿐이다. 스텝과 모듈이 각자 자기 주제를 달고(steps.py의
"topics", modules.py의 _MODULE_TOPICS), 겹치면 O다. 어느 쪽이든 "any"면 항상 O.

서로를 나열하지 않는 것이 요점이다 — 스텝이 늘어도 모듈 쪽을 안 고치고, 모듈이 늘어도
스텝 쪽을 안 고친다. 새 항목에 자기 주제 한 줄만 적으면 나머지 칸이 저절로 채워진다.

**이 매트릭스는 "의미가 맞는가"만 본다.** 실제로 실행할 수 있는지는 다른 문제이고, 계획
단계에서 따로 검사한다 — 선행 데이터(requires)가 있는지는 planner.resolve_dependencies가,
필요한 역할이 데이터소스에 있는지는 planner.validate_plan과 options_to_plan이 본다.
그 조건들은 계획 전체와 데이터소스에 따라 달라져서 스텝·모듈 고유 속성이 아니다.
둘을 한 표에 섞으면 "데이터소스마다 달라지는 매트릭스"가 되어 카탈로그 문서로 못 쓴다.
"""
from __future__ import annotations

from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.catalog.steps import get_step_registry

ANY = "any"

# 등록된 주제. 새 주제를 늘리려면 여기에 더하고 스텝·모듈 양쪽에 달면 된다.
TOPICS: tuple[str, ...] = ("sales", "customer", "item", "pnl", "inventory", "closing", ANY)

TOPIC_LABELS: dict[str, str] = {
    "sales":     "매출",
    "customer":  "고객",
    "item":      "제품",
    "pnl":       "손익",
    "inventory": "재고",
    "closing":   "마무리",
    ANY:         "공통",
}

# 전용 주제 — "any" 와일드카드가 뚫지 못한다. 한쪽이 이 주제를 가지면 다른 쪽도 같은
# 주제를 가져야 O다.
#
# 왜 필요한가: 결론(conclusion)은 도메인 주제가 아니라 **보고서에서의 자리**다. "어디에나
# 어울리는 모듈"과는 성격이 다른데, 보통 규칙으로는 any 모듈이 결론 스텝에 다 들어가고
# 결론 모듈이 모든 스텝에 들어가 버린다. 둘 다 실제로는 없는 일이다.
EXCLUSIVE: frozenset[str] = frozenset({"closing"})


def applies(step_topics, module_topics) -> bool:
    """스텝 주제와 모듈 주제가 어울리면 True."""
    s, m = set(step_topics or [ANY]), set(module_topics or [ANY])
    if EXCLUSIVE & (s | m):
        return bool(EXCLUSIVE & s & m)
    return ANY in s or ANY in m or bool(s & m)


def modules_for_step(step_id: str) -> list[str]:
    """그 스텝에 어울리는 module_name 목록."""
    preset = get_step_registry().get(step_id)
    if preset is None:
        raise KeyError(f"등록되지 않은 스텝: '{step_id}'")
    topics = preset.get("topics") or [ANY]
    return [
        name for name, spec in get_module_registry().items()
        if applies(topics, spec.topics)
    ]


def steps_for_module(module_name: str) -> list[str]:
    """그 모듈이 어울리는 step_id 목록 — 매트릭스를 열 방향으로 읽은 것."""
    spec = get_module_registry().get(module_name)
    if spec is None:
        raise KeyError(f"등록되지 않은 모듈: '{module_name}'")
    return [
        sid for sid, preset in get_step_registry().items()
        if applies(preset.get("topics"), spec.topics)
    ]


def tools_for_module(module_name: str) -> list[str]:
    """그 모듈이 쓸 수 있는 tool_id 목록. 대체 툴이 없는 모듈은 빈 목록이다."""
    spec = get_module_registry().get(module_name)
    if spec is None:
        raise KeyError(f"등록되지 않은 모듈: '{module_name}'")
    return list(spec.tools.get("available") or [])


def step_module_matrix() -> dict:
    """스텝×모듈 매트릭스.

    반환: {"steps": [...], "modules": [...], "cells": {step_id: [module_name, ...]}}
      cells는 O가 찍히는 칸만 담는다 — 빈칸까지 다 실으면 응답이 1,500칸으로 불어난다.
    """
    steps, modules = get_step_registry(), get_module_registry()
    return {
        "topics": list(TOPICS),
        "topic_labels": dict(TOPIC_LABELS),
        "steps": [
            {"step_id": sid, "title": p["title"], "topics": list(p.get("topics") or [ANY])}
            for sid, p in steps.items()
        ],
        "modules": [
            {"module_name": name, "purpose": spec.purpose, "topics": list(spec.topics)}
            for name, spec in modules.items()
        ],
        "cells": {
            sid: [
                name for name, spec in modules.items()
                if applies(p.get("topics"), spec.topics)
            ]
            for sid, p in steps.items()
        },
    }


def module_tool_matrix() -> dict:
    """모듈×툴 매트릭스. 스텝×모듈과 달리 새 선언이 없다 — 이미 스펙에 있는 값을 편 것이다.

    반환: {"modules": [...], "tools": [...], "cells": {module_name: [tool_id, ...]},
           "defaults": {module_name: tool_id}}
    """
    from d2insight.engine.catalog.tools import get_tool_registry

    modules = get_module_registry()
    tools = get_tool_registry()
    return {
        "tools": [{"tool_id": tid, "purpose": meta.get("purpose", "")}
                  for tid, meta in tools.items()],
        "modules": [{"module_name": name, "purpose": spec.purpose}
                    for name, spec in modules.items()],
        "cells": {name: list(spec.tools.get("available") or [])
                  for name, spec in modules.items()},
        "defaults": {name: spec.tools.get("default")
                     for name, spec in modules.items() if spec.tools.get("default")},
    }


def render_step_module_text() -> str:
    """터미널·문서용 텍스트 표. 열이 37개라 스텝별 목록 형태로 편다 — 격자로 그리면
    가로가 넘쳐 오히려 안 읽힌다.
    """
    steps, modules = get_step_registry(), get_module_registry()
    lines = [f"스텝 {len(steps)} × 모듈 {len(modules)}  (O = 주제가 맞음)", ""]
    for sid, preset in steps.items():
        topics = preset.get("topics") or [ANY]
        hits = [n for n, s in modules.items() if applies(topics, s.topics)]
        lines.append(f"[{'/'.join(topics)}] {sid} \"{preset['title']}\"  — {len(hits)}개")
        lines.append(f"    {', '.join(hits)}")
    return "\n".join(lines)
