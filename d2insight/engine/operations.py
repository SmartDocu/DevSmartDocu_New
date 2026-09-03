"""편집 연산 — 대화·UI 어느 통로로 온 요청이든 이 형태로 수렴해 스텝 목록에 적용한다
(2단계, 2026-07-24).

연산 10종.

  스텝 단위 (방을 넣고 뺀다)   : add / remove / move / reorder
  모듈 단위 (방 안의 가구를 바꾼다): add_module / remove_module / set_sub_name /
                                    set_measure / set_param / set_tool

UI(드래그·체크·슬라이더)는 이 연산을 직접 만들고, 채팅 문장은 LLM이 이 연산으로 번역한다
(chat_options.extract_operations). 적용 로직은 이 파일 하나뿐이라 어느 통로로 와도 결과가
같다는 것을 보장한다 — 대화로 고치다 UI로 넘어가도, 혹은 그 반대도 이어진다.

모듈 단위 4종은 스텝 카드 팝업을 위해 늘렸다(2026-09-01). 팝업에서 자연어로 지시하는 것이
대부분 이쪽이다 — "제품별 말고 브랜드별로"(set_sub_name), "수량 기준으로"(set_measure),
"추이도 같이"(add_module), "구성비는 빼줘"(remove_module).

조용히 무시하지 않는다 — 적용할 수 없는 연산(잠긴 스텝 이동, 이름표 충돌 등)은 즉시
OperationError를 올린다. 호출부(entry.py)가 이를 잡아 사용자에게 알린다.
"""
from __future__ import annotations

from d2insight.engine.catalog.module_key import ModuleKeyError, normalize, to_key
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


def _module_name(m: dict) -> str:
    """모듈 항목에서 module_name을 꺼낸다. 조립 표현·실행 표현·옛 문자열 형태를 모두 받는다."""
    try:
        return normalize(m)["module_name"]
    except Exception:
        return ""


def is_locked_step(step: dict) -> bool:
    """뿌리 스텝(맨 앞)이거나 결론(맨 뒤)이면 True — 이동·삭제 불가 표시.

    공개 함수다 — entry.py가 applied_steps에 "locked" 플래그를 붙일 때도 이 판정을 그대로
    쓴다(2026-07-24, 5단계). 잠금 규칙이 Python(백엔드 검증)과 JS(프론트 표시) 두 곳에
    따로 구현되면 언젠가 서로 어긋난다 — 여기 하나만 있어야 한다.
    """
    return any(
        _module_name(m) in _ROOT_MODULE_IDS | _TAIL_MODULE_IDS and not m.get("_auto")
        for m in step.get("modules", [])
    )


def _is_tail_locked(step: dict) -> bool:
    """결론처럼 "맨 뒤에" 고정인 스텝인지 — reorder/add의 삽입 위치 계산에만 쓴다."""
    return any(_module_name(m) in _TAIL_MODULE_IDS for m in step.get("modules", []))


def _find_index(steps: list[dict], step_id: str) -> int:
    for i, s in enumerate(steps):
        if s.get("step_id") == step_id:
            return i
    raise OperationError(
        f"스텝 '{step_id}'을 찾을 수 없습니다. 현재 스텝: "
        f"{[s.get('step_id') for s in steps]}"
    )


def _producer_labels(steps: list[dict], registry: dict) -> set[str]:
    """이미 생산되는 이름표. 조합 단위로 본다 — runner.ModuleInstance.label과 같은 규칙이다.

    같은 분석이라도 대상이 다르면 다른 이름표다(오류코드별 이상탐지 ≠ 앱별 이상탐지).
    """
    labels: set[str] = set()
    for s in steps:
        for m in s.get("modules", []):
            spec = registry.get(_module_name(m))
            if not spec:
                continue
            sub = normalize(m).get("sub_name")
            labels.update(f"{lbl}@{sub}" if sub else lbl for lbl in spec.produces)
    return labels


def _default_step_entry(step_id: str, step_registry: dict, modules: dict) -> dict:
    """카탈로그 프리셋 → steps[] 항목(스펙 기본값 위에 프리셋 값을 얹은 실제 적용값).

    chat_options.module_entry_from_preset과 **같은 함수**를 쓴다 — 두 경로가 프리셋을 서로
    다르게 펼치면 대화로 만든 구성과 UI로 만든 구성이 어긋난다.
    """
    from d2insight.engine.chat_options import module_entry_from_preset

    preset = step_registry.get(step_id)
    if preset is None:
        raise OperationError(
            f"'{step_id}'은 카탈로그에 없는 스텝입니다. 등록된 스텝: {sorted(step_registry)}"
        )
    modules_out = [module_entry_from_preset(m, modules) for m in preset["default_modules"]]
    return {"step_id": step_id, "title": preset["title"], "modules": modules_out}


def _find_module(step: dict, ref: str) -> dict:
    """스텝 안에서 모듈 하나를 지목한다.

    ref는 조합 키("actual_aggregate@region")가 원칙이다. 한 스텝에 같은 module_name이
    sub_name만 다르게 여러 개 있을 수 있어, 이름만으로는 어느 것인지 정해지지 않는다
    (예전에는 첫 번째가 조용히 잡혔다 — 2026-09-01 재구조화로 고친 자리).

    이름만 준 경우에도 그 이름이 스텝 안에서 유일하면 받아준다. 여럿이면 어느 것인지
    되묻는 대신 후보를 보여주고 실패시킨다 — 엉뚱한 모듈을 고치는 것보다 낫다.
    """
    modules = step.get("modules", [])
    keys = [to_key(normalize(m)) for m in modules]
    if ref in keys:
        return modules[keys.index(ref)]

    hits = [m for m in modules if _module_name(m) == ref]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise OperationError(
            f"스텝 '{step.get('title')}'에 '{ref}' 모듈이 여러 개 있습니다. "
            f"어느 것인지 정확히 지정하세요: {[k for k in keys if k.startswith(ref)]}"
        )
    raise OperationError(
        f"스텝 '{step.get('title')}'에 모듈 '{ref}'이 없습니다. 현재 모듈: {keys}"
    )


def _module_ref(op: dict) -> str:
    """연산이 가리키는 모듈. 새 키("module")를 우선하고 옛 키("module_id")도 받는다."""
    ref = op.get("module") or op.get("module_id")
    if not ref:
        raise OperationError(f"연산에 대상 모듈이 없습니다: {op}")
    return ref


def _combo_keys(step: dict) -> list[str]:
    return [to_key(normalize(m)) for m in step.get("modules", [])]


def _assert_no_duplicate(step: dict, key: str, exclude: dict | None = None) -> None:
    """한 스텝 안에서 같은 조합이 두 번 생기지 않게 막는다.

    조합이 겹치면 그 스텝에서 모듈을 지목할 수 없게 되고(어느 쪽인지 알 수 없다), 같은
    분석이 두 번 실려 보고서에도 중복으로 나온다 — 재구조화로 없앤 상태를 되돌리는 셈이다.
    """
    for m in step.get("modules", []):
        if m is exclude:
            continue
        if to_key(normalize(m)) == key:
            raise OperationError(
                f"스텝 '{step.get('title')}'에 '{key}'이(가) 이미 있습니다. "
                "같은 분석을 두 번 넣을 수는 없습니다."
            )


def _assert_in_schema(schema, kind: str, value) -> None:
    """바꾸려는 분석 대상·기준 값이 이 데이터에 실제로 있는지 확인한다.

    역할 이름(item/region 등)과 컬럼명 둘 다 받는다 — 프롬프트가 두 형태를 모두 허용한다.
    확인 없이 통과시키면 나중에 "작성 불가"로만 나타나 사유를 알 수 없다.
    """
    if schema is None or not value:
        return
    available = schema.dimensions if kind == "sub_name" else schema.measures
    if value in available or schema.columns(value):
        return
    what = "분석 대상" if kind == "sub_name" else "기준 값"
    raise OperationError(
        f"이 데이터에 '{value}'이(가) 없습니다. 쓸 수 있는 {what}: {', '.join(available)}"
    )


def _module_entry_for(module_name: str, sub_name, measure, registry: dict) -> dict:
    """카탈로그에서 모듈 하나를 꺼내 steps[] 항목으로 만든다(조립 표현 + params 기본값)."""
    from d2insight.engine.chat_options import module_entry_from_preset

    spec = registry.get(module_name)
    if spec is None:
        raise OperationError(f"'{module_name}'은 이 앱에 없는 분석입니다.")
    if sub_name and not spec.sub_name_pool:
        raise OperationError(
            f"모듈 '{module_name}'은 분석 대상을 따로 고르지 않습니다(sub_name 지정 불가)."
        )
    if spec.sub_name_required and not sub_name:
        raise OperationError(f"모듈 '{module_name}'은 분석 대상(sub_name)을 지정해야 합니다.")
    if measure and not spec.accepts_measure:
        raise OperationError(
            f"모듈 '{module_name}'은 기준 값(measure)을 따로 고르지 않습니다."
        )
    ref = {"module_name": module_name, "sub_name": sub_name or None, "measure": measure or None}
    return module_entry_from_preset(ref, registry)


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


def apply_operations(
    steps: list[dict], operations: list[dict], schema=None,
) -> tuple[list[dict], list[str]]:
    """편집 연산 목록을 스텝 목록에 순서대로 적용한다.

    steps: 옵션 JSON의 steps 형태(각 항목 {"step_id","title","modules":[...]}).
    schema: 주면 분석 대상·기준 값이 그 데이터에 실제로 있는지 확인한다.
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
            new_labels = _producer_labels([entry], registry)
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
            # step_id가 없는 옛 저장분도 있으므로 .get으로 읽는다 — 직접 꺼내면 KeyError다.
            non_locked_ids = {s.get("step_id") for s in steps if not is_locked_step(s)}
            if set(order) != non_locked_ids:
                raise OperationError(
                    "reorder의 step_id 목록은 잠기지 않은 스텝 전체와 정확히 일치해야 합니다"
                    f"(자료확인/총평 등 뿌리 스텝, 결론은 제외). 대상: {sorted(filter(None, non_locked_ids))}"
                )
            by_id = {s.get("step_id"): s for s in steps}
            # 뿌리 스텝(맨 앞)과 결론(맨 뒤)은 방향이 반대라 한데 묶어 앞으로 몰면 안 된다
            # (2026-07-28, 결론 스텝화 — 예전엔 모든 잠긴 스텝을 맨 앞으로 몰았다).
            head_locked = [s for s in steps if is_locked_step(s) and not _is_tail_locked(s)]
            tail_locked = [s for s in steps if _is_tail_locked(s)]
            steps = head_locked + [by_id[sid] for sid in order] + tail_locked

        elif kind == "set_title":
            idx = _find_index(steps, op["step_id"])
            title = (op.get("title") or "").strip()
            if not title:
                raise OperationError("바꿀 스텝 이름이 비어 있습니다.")
            steps[idx]["title"] = title

        elif kind == "set_param":
            idx = _find_index(steps, op["step_id"])
            ref = _module_ref(op)
            module_entry = _find_module(steps[idx], ref)
            mid = _module_name(module_entry)
            spec = registry.get(mid)
            new_params = op.get("params") or {}
            # sub_name/measure는 조립 필드라 params로 바꾸지 않는다 — 여기로 오면 같은 것이
            # 두 자리에 생겨 어느 쪽이 진짜인지 알 수 없게 된다(2026-09-01).
            misplaced = set(new_params) & {"dimension", "dimensions", "measure"}
            if misplaced:
                raise OperationError(
                    f"모듈 '{mid}': {sorted(misplaced)}은(는) 파라미터가 아니라 모듈 자체를 "
                    "바꾸는 값입니다. 분석 대상을 바꾸려면 그 대상의 모듈을 쓰세요."
                )
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
            module_entry = _find_module(steps[idx], _module_ref(op))
            mid = _module_name(module_entry)
            spec = registry.get(mid)
            available = (spec.tools.get("available") if spec else None) or []
            tool = op.get("tool")
            if tool not in available:
                raise OperationError(
                    f"모듈 '{mid}': 툴 '{tool}'을 쓸 수 없습니다. 사용 가능: {available or '(없음)'}"
                )
            module_entry["tool"] = tool

        # ── 모듈 단위 연산 (2026-09-01, 스텝 카드 팝업) ───────────────────────
        # 스텝 단위 연산(add/remove/move)이 "방을 넣고 뺀다"면, 이 넷은 "방 안의 가구를
        # 바꾼다". 팝업에서 자연어로 지시하는 것이 대부분 이쪽이다.

        elif kind == "set_sub_name":
            idx = _find_index(steps, op["step_id"])
            entry = _find_module(steps[idx], _module_ref(op))
            mid = _module_name(entry)
            spec = registry.get(mid)
            sub_name = op.get("sub_name") or None
            if spec is not None and not spec.sub_name_pool:
                raise OperationError(
                    f"모듈 '{mid}'은 분석 대상을 따로 고르지 않습니다."
                )
            if spec is not None and spec.sub_name_required and not sub_name:
                raise OperationError(f"모듈 '{mid}'은 분석 대상을 비울 수 없습니다.")
            _assert_in_schema(schema, "sub_name", sub_name)
            new_key = to_key({**normalize(entry), "sub_name": sub_name})
            _assert_no_duplicate(steps[idx], new_key, exclude=entry)
            entry["sub_name"] = sub_name

        elif kind == "set_measure":
            idx = _find_index(steps, op["step_id"])
            entry = _find_module(steps[idx], _module_ref(op))
            mid = _module_name(entry)
            spec = registry.get(mid)
            measure = op.get("measure") or None
            if spec is not None and not spec.accepts_measure:
                raise OperationError(f"모듈 '{mid}'은 기준 값을 따로 고르지 않습니다.")
            _assert_in_schema(schema, "measure", measure)
            new_key = to_key({**normalize(entry), "measure": measure})
            _assert_no_duplicate(steps[idx], new_key, exclude=entry)
            entry["measure"] = measure

        elif kind == "add_module":
            idx = _find_index(steps, op["step_id"])
            # 이름만 오기도 하고 조합 키("amount:actual_aggregate@Brand")로 오기도 한다.
            ref = op.get("module_name") or op.get("module")
            try:
                parts = normalize(ref)
            except ModuleKeyError:
                raise OperationError(f"추가할 분석을 읽지 못했습니다: {ref!r}")
            sub_name = op.get("sub_name") or parts["sub_name"]
            measure = op.get("measure") or parts["measure"]
            _assert_in_schema(schema, "sub_name", sub_name)
            _assert_in_schema(schema, "measure", measure)
            entry = _module_entry_for(parts["module_name"], sub_name, measure, registry)
            _assert_no_duplicate(steps[idx], to_key(normalize(entry)))

            # 싱글턴 이름표 사전 검사 — add(스텝)와 같은 규칙이다. 실행 도중 PlanError로
            # 죽기 전에 여기서 막는다.
            clash = (_producer_labels([{"modules": [entry]}], registry)
                     & _producer_labels(steps, registry))
            if clash:
                raise OperationError(
                    f"'{_module_name(entry)}'을 추가할 수 없습니다 — 이미 있는 분석과 같은 "
                    f"결과({sorted(clash)})를 만듭니다."
                )
            steps[idx]["modules"].append(entry)

        elif kind == "remove_module":
            idx = _find_index(steps, op["step_id"])
            entry = _find_module(steps[idx], _module_ref(op))
            mid = _module_name(entry)
            if mid in _ROOT_MODULE_IDS | _TAIL_MODULE_IDS:
                raise OperationError(
                    f"'{mid}'은 다른 모든 분석의 기반(자료확인/총평)이거나 결론이라 뺄 수 "
                    "없습니다."
                )
            steps[idx]["modules"] = [m for m in steps[idx]["modules"] if m is not entry]
            # 모듈이 하나도 안 남으면 그 스텝 자체가 사라진다 — 빈 스텝은 두지 않는다.
            if not steps[idx]["modules"]:
                removed = steps.pop(idx)
                notes.append(f"'{removed.get('title')}' 스텝은 모듈이 모두 빠져 함께 제외했습니다.")

        else:
            raise OperationError(f"알 수 없는 연산: '{kind}'")

    return steps, notes
