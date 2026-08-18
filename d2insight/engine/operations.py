"""편집 연산 — 대화·UI 어느 통로로 온 요청이든 이 형태로 수렴해 스텝 목록에 적용한다
(2단계, 2026-07-24).

연산 6종: add / remove / move / reorder / set_param / set_tool.
UI(드래그·체크·슬라이더)는 이 연산을 직접 만들고, 채팅 문장은 LLM이 이 연산으로 번역한다
(chat_options.extract_operations). 적용 로직은 이 파일 하나뿐이라 어느 통로로 와도 결과가
같다는 것을 보장한다 — 대화로 고치다 UI로 넘어가도, 혹은 그 반대도 이어진다.

조용히 무시하지 않는다 — 적용할 수 없는 연산(잠긴 스텝 이동, 이름표 충돌 등)은 즉시
OperationError를 올린다. 호출부(entry.py)가 이를 잡아 사용자에게 알린다.
"""
from __future__ import annotations

from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.catalog.steps import get_step_registry

# 거의 모든 모듈이 이 둘에 의존한다 — 이 모듈을 담은 스텝은 뿌리 스텝으로 보고 맨 앞에
# 고정한다(이동·삭제 불가, 2026-07-24 §4-1). 도메인이 바뀌어도 이 두 module_id는 그대로다.
_ROOT_MODULE_IDS = {"period_dataset", "measure_summary"}

# 결론은 모든 본문을 근거로 삼으므로 항상 맨 뒤여야 한다 — 뿌리 스텝과 같은 "잠김"이지만
# 방향이 반대다(2026-07-28, 7단계 — 결론 스텝화). reorder/add처럼 위치를 다루는 연산은
# 이 둘을 구분해야 하므로 _is_tail_locked를 따로 둔다.
_TAIL_MODULE_IDS = {"conclusion"}


class OperationError(Exception):
    """편집 연산을 스텝 목록에 적용할 수 없을 때."""


def is_locked_step(step: dict) -> bool:
    """뿌리 스텝(맨 앞)이거나 결론(맨 뒤)이면 True — 이동·삭제 불가 표시.

    공개 함수다 — entry.py가 applied_steps에 "locked" 플래그를 붙일 때도 이 판정을 그대로
    쓴다(2026-07-24, 5단계). 잠금 규칙이 Python(백엔드 검증)과 JS(프론트 표시) 두 곳에
    따로 구현되면 언젠가 서로 어긋난다 — 여기 하나만 있어야 한다.
    """
    return any(
        m.get("module_id") in _ROOT_MODULE_IDS | _TAIL_MODULE_IDS
        for m in step.get("modules", [])
    )


def _is_tail_locked(step: dict) -> bool:
    """결론처럼 "맨 뒤에" 고정인 스텝인지 — reorder/add의 삽입 위치 계산에만 쓴다."""
    return any(m.get("module_id") in _TAIL_MODULE_IDS for m in step.get("modules", []))


def _find_index(steps: list[dict], step_id: str) -> int:
    for i, s in enumerate(steps):
        if s.get("step_id") == step_id:
            return i
    raise OperationError(
        f"스텝 '{step_id}'을 찾을 수 없습니다. 현재 스텝: "
        f"{[s.get('step_id') for s in steps]}"
    )


def _producer_labels(steps: list[dict], registry: dict) -> set[str]:
    labels: set[str] = set()
    for s in steps:
        for m in s.get("modules", []):
            spec = registry.get(m.get("module_id"))
            if spec:
                labels.update(spec.produces)
    return labels


def _default_step_entry(step_id: str, step_registry: dict, modules: dict) -> dict:
    """카탈로그 프리셋 → steps[] 항목(스펙 기본값 위에 프리셋 값을 얹은 실제 적용값).

    chat_options.default_steps_for_scenario와 같은 원칙 — 빈 채로 두지 않는다.
    """
    preset = step_registry.get(step_id)
    if preset is None:
        raise OperationError(
            f"'{step_id}'은 카탈로그에 없는 스텝입니다. 등록된 스텝: {sorted(step_registry)}"
        )
    modules_out = []
    for m in preset["default_modules"]:
        mid = m["module_id"]
        spec = modules[mid]
        params = {name: field.get("default") for name, field in spec.params.items()}
        params.update(m.get("params") or {})
        entry: dict = {"module_id": mid, "params": params}
        tool = m.get("tools", [None])[0] if m.get("tools") else spec.tools.get("default")
        if tool:
            entry["tool"] = tool
        modules_out.append(entry)
    return {"step_id": step_id, "title": preset["title"], "modules": modules_out}


def _insert_at(steps: list[dict], entry: dict, position: dict) -> tuple[list[dict], str | None]:
    """position: {"before": step_id} | {"after": step_id} | {"at": "start"|"end"}. 기본은 end.

    잠긴(뿌리) 스텝보다 앞에는, 결론보다 뒤에는 어떤 것도 끼워 넣지 않는다 — 자료확인·
    총평은 항상 맨 앞, 결론은 항상 맨 뒤다.

    위치 기준 스텝(before/after)을 못 찾으면(같은 연산 배치의 앞선 연산이 그 스텝을 이미
    지웠거나 옮긴 경우 등) 실패시키지 않고 맨 뒤에 넣은 뒤 note로만 알린다 — "무엇을 할지는
    알았는데 정확히 어디인지만 못 찾은" 경우까지 통째로 실패 처리하면, 사용자가 명확히
    지정한 다른 연산(제외·이동 등)까지 함께 기본값으로 롤백돼 버린다(2026-07-24, 실사용
    중 발견 — LLM이 "Mix를 Price 뒤에" 위치를 추론했는데 같은 요청에서 Price가 먼저
    제거되어 기준점이 사라진 사례).
    """
    steps = list(steps)
    note = None
    idx = None
    if "before" in position:
        try:
            idx = _find_index(steps, position["before"])
        except OperationError:
            note = f"'{position['before']}' 위치를 찾지 못해 맨 뒤에 넣었습니다."
    elif "after" in position:
        try:
            idx = _find_index(steps, position["after"]) + 1
        except OperationError:
            note = f"'{position['after']}' 위치를 찾지 못해 맨 뒤에 넣었습니다."
    elif position.get("at") == "start":
        idx = 0
    if idx is None:
        idx = len(steps)
    first_unlocked = next((i for i, s in enumerate(steps) if not is_locked_step(s)), len(steps))
    tail_start = next((i for i, s in enumerate(steps) if _is_tail_locked(s)), len(steps))
    idx = min(max(idx, first_unlocked), tail_start)
    steps.insert(idx, entry)
    return steps, note


def _position_of(op: dict) -> dict:
    return {k: v for k, v in op.items() if k in ("before", "after", "at")}


def apply_operations(steps: list[dict], operations: list[dict]) -> tuple[list[dict], list[str]]:
    """편집 연산 목록을 스텝 목록에 순서대로 적용한다.

    steps: 옵션 JSON의 steps 형태(각 항목 {"step_id","title","modules":[...]}).
    실패하면 즉시 OperationError — 일부만 적용된 애매한 상태로 두지 않는다(호출부가
    통째로 롤백해 기본 구성으로 대체하도록).
    반환: (적용된 steps, notes). notes에는 요청한 그대로 처리된 경우의 "확인" 문구는 담지
    않는다 — 결과가 이미 화면의 스텝 목록에 그대로 보이므로 중복이다(2026-07-28, 오른쪽
    패널이 이런 확인 문구까지 ⚠로 표시해 진짜 경고처럼 보인다는 피드백으로 제거). 요청한
    위치를 못 찾아 다르게 처리된 경우처럼, 사용자가 몰랐다면 놓칠 수 있는 차이만 담는다.
    """
    registry = get_module_registry()
    step_registry = get_step_registry()
    steps = [dict(s, modules=[dict(m) for m in s.get("modules", [])]) for s in steps]
    notes: list[str] = []

    for op in operations:
        kind = op.get("op")

        if kind == "remove":
            idx = _find_index(steps, op["step_id"])
            if is_locked_step(steps[idx]):
                raise OperationError(
                    f"스텝 '{op['step_id']}'은 다른 모든 분석의 기반(자료확인/총평)이라 "
                    "제외할 수 없습니다."
                )
            steps.pop(idx)

        elif kind == "move":
            idx = _find_index(steps, op["step_id"])
            if is_locked_step(steps[idx]):
                raise OperationError(
                    f"스텝 '{op['step_id']}'은 항상 맨 앞에 있어야 해서 순서를 바꿀 수 없습니다."
                )
            entry = steps.pop(idx)
            steps, pos_note = _insert_at(steps, entry, _position_of(op))
            if pos_note:
                notes.append(f"스텝 '{entry['title']}'의 순서 이동: {pos_note}")

        elif kind == "add":
            step_id = op["step_id"]
            if any(s.get("step_id") == step_id for s in steps):
                raise OperationError(f"스텝 '{step_id}'은 이미 있습니다.")
            entry = _default_step_entry(step_id, step_registry, registry)

            # 싱글턴 이름표 사전 검사(G5) — 실행 도중 PlanError로 죽기 전에 여기서 막는다.
            new_labels: set[str] = set()
            for m in entry["modules"]:
                spec = registry.get(m["module_id"])
                if spec:
                    new_labels.update(spec.produces)
            clash = new_labels & _producer_labels(steps, registry)
            if clash:
                raise OperationError(
                    f"스텝 '{step_id}'을 추가할 수 없습니다 — 이미 있는 스텝과 같은 결과"
                    f"({sorted(clash)})를 만듭니다. 같은 분석이 이미 포함돼 있습니다."
                )
            steps, pos_note = _insert_at(steps, entry, _position_of(op))
            if pos_note:
                notes.append(f"스텝 '{entry['title']}' 추가 위치: {pos_note}")

        elif kind == "reorder":
            order = op.get("order") or []
            non_locked_ids = {s["step_id"] for s in steps if not is_locked_step(s)}
            if set(order) != non_locked_ids:
                raise OperationError(
                    "reorder의 step_id 목록은 잠기지 않은 스텝 전체와 정확히 일치해야 합니다"
                    f"(자료확인/총평 등 뿌리 스텝, 결론은 제외). 대상: {sorted(non_locked_ids)}"
                )
            by_id = {s["step_id"]: s for s in steps}
            # 뿌리 스텝(맨 앞)과 결론(맨 뒤)은 방향이 반대라 한데 묶어 앞으로 몰면 안 된다
            # (2026-07-28, 결론 스텝화 — 예전엔 모든 잠긴 스텝을 맨 앞으로 몰았다).
            head_locked = [s for s in steps if is_locked_step(s) and not _is_tail_locked(s)]
            tail_locked = [s for s in steps if _is_tail_locked(s)]
            steps = head_locked + [by_id[sid] for sid in order] + tail_locked

        elif kind == "set_param":
            idx = _find_index(steps, op["step_id"])
            mid = op["module_id"]
            module_entry = next((m for m in steps[idx]["modules"] if m["module_id"] == mid), None)
            if module_entry is None:
                raise OperationError(f"스텝 '{op['step_id']}'에 모듈 '{mid}'이 없습니다.")
            spec = registry.get(mid)
            new_params = op.get("params") or {}
            unknown = set(new_params) - set(spec.params if spec else {})
            if unknown:
                raise OperationError(f"모듈 '{mid}': 알 수 없는 파라미터 {sorted(unknown)}.")
            # enum이 선언된 파라미터는 LLM이 지어낸 값을 여기서 한 번 더 막는다 — 프롬프트에
            # 허용값을 알려줘도 LLM이 어길 수 있어, 조용히 통과시키지 않는다(2026-07-28,
            # compare_type에 "month_over_month" 같은 값이 넘어온 사례에서 발견).
            for name, value in new_params.items():
                enum = (spec.params.get(name) or {}).get("enum") if spec else None
                if enum and value not in enum:
                    raise OperationError(
                        f"모듈 '{mid}': 파라미터 '{name}' 값 '{value}'은 유효하지 않습니다. "
                        f"가능한 값: {enum}."
                    )
            module_entry["params"] = {**module_entry.get("params", {}), **new_params}

        elif kind == "set_tool":
            idx = _find_index(steps, op["step_id"])
            mid = op["module_id"]
            module_entry = next((m for m in steps[idx]["modules"] if m["module_id"] == mid), None)
            if module_entry is None:
                raise OperationError(f"스텝 '{op['step_id']}'에 모듈 '{mid}'이 없습니다.")
            spec = registry.get(mid)
            available = (spec.tools.get("available") if spec else None) or []
            tool = op.get("tool")
            if tool not in available:
                raise OperationError(
                    f"모듈 '{mid}': 툴 '{tool}'을 쓸 수 없습니다. 사용 가능: {available or '(없음)'}"
                )
            module_entry["tool"] = tool

        else:
            raise OperationError(f"알 수 없는 연산: '{kind}'")

    return steps, notes
