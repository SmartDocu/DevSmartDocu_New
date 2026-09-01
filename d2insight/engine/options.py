"""옵션 JSON ↔ 엔진 plan 변환 — 대화·UI 어느 경로로 온 옵션이든 이 통로 하나로 수렴한다.

알 수 없는 module_id·param명·tool은 카탈로그와 어긋난 것이라 즉시 OptionsError를 올린다.
dimension/measure만 예외다 — 데이터셋에 없을 수 있는 정상적인 경우라, 그 모듈만 건너뛴다
(planner.finalize의 근사 매칭과 같은 원칙).
"""
from __future__ import annotations

import json

from d2insight.engine.catalog.module_key import (
    ModuleKeyError, check_required, to_execution_entry,
)
from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.planner import finalize
from d2insight.engine.schema import ROLE_ITEM, Schema


class OptionsError(Exception):
    """옵션 JSON이 카탈로그와 맞지 않을 때 — 조용히 보정하지 않고 여기서 즉시 실패한다."""


def _build_disabled_step(title: str, raw_modules: list[dict], reasons: list[str], schema: Schema) -> dict:
    """스텝의 모듈이 전부 실행 불가일 때 버리지 않고 비활성 스텝(enabled=False)으로 남긴다."""
    reason_text = " / ".join(dict.fromkeys(reasons)) or "필요한 조건을 이 데이터셋에서 찾지 못했습니다."
    if any((m.get("params") or {}).get("dimension") == ROLE_ITEM for m in raw_modules):
        alts = schema.item_fallback_columns()
        if alts:
            reason_text += f" (가능한 대안: {', '.join(alts)})"
    return {"title": title, "modules": raw_modules, "enabled": False, "disabled_reason": reason_text}


def load_options(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def global_to_meta(options: dict) -> dict:
    """옵션 JSON의 "global" 절 → run_engine_report/ctx.meta에 넘길 인자.

    명시되지 않은 키는 None으로 둔다 — 호출부가 "명시된 값만 기존 값을 덮어쓴다"는 원칙을
    지킬 수 있게 한다(조용히 기본값으로 되돌리지 않는다, 2026-07-24 G2).
    """
    g = options.get("global", {})
    return {
        "source_id": g.get("datasource"),
        "target_month": g.get("target_period"),
        "compare_type": g.get("compare_type"),
        "months_back": g.get("months_back"),
        "measure": g.get("measure"),
        "grain": g.get("grain"),          # month(기본)/quarter/year/week — 2026-07-24 3단계
    }


def _resolve_dimension_value(module_id: str, role: str, schema: Schema) -> str:
    """차원 값 하나가 역할 이름(item/party/item_group 등, schema.py의 ROLE_*)으로 오면 실제
    물리 컬럼명으로 바꾼다. 이미 실제 차원명이면 그대로 둔다(호환).
    """
    col = schema.column(role)
    if col:
        return col
    if role in schema.dimensions:
        return role
    raise OptionsError(
        f"모듈 '{module_id}': dimension '{role}'을 역할로도 실제 차원으로도 찾을 수 없습니다. "
        f"사용 가능한 차원: {schema.dimensions}"
    )


def _resolve_dimension(module_id: str, params: dict, schema: Schema) -> dict:
    """params.dimension(단수)·dimensions(복수, 리스트)이 역할 이름으로 오면 실제 물리 컬럼명
    으로 바꾼다. 둘 다 처리한다 — 리스트 파라미터를 쓰는 모듈(new_lost_detection의
    dimensions 등)도 있어 단수만 다루면 역할화 자체가 반쪽으로 남는다(2026-07-24, G9).

    값이 없으면(키 자체가 없거나 None/빈 리스트) 건드리지 않는다 — default_steps_for_scenario가
    미지정 파라미터도 기본값(None 포함)까지 채워 넘기므로, "키 존재"만으로는 "값이 지정됨"을
    판별할 수 없다(2026-07-24, 시나리오1 8스텝 복원 중 trend의 dimension=None에서 발견해 수정).
    """
    resolved = dict(params)
    if params.get("dimension"):
        resolved["dimension"] = _resolve_dimension_value(module_id, params["dimension"], schema)
    if params.get("dimensions"):
        resolved["dimensions"] = [
            _resolve_dimension_value(module_id, d, schema) for d in params["dimensions"]
        ]
    return resolved


def _resolve_measure_value(module_id: str, value: str, schema: Schema) -> str:
    """measure 값이 역할 이름(amount/quantity/discount)으로 오면 실제 물리 컬럼명으로 바꾼다.
    이미 실제 measure명이면 그대로 둔다(호환).
    """
    col = schema.column(value)
    if col:
        return col
    if value in schema.measures:
        return value
    raise OptionsError(
        f"모듈 '{module_id}': measure '{value}'를 역할로도 실제 측정값으로도 찾을 수 없습니다. "
        f"사용 가능한 measure: {schema.measures}"
    )


def _resolve_measure(module_id: str, params: dict, spec, schema: Schema,
                     global_measure: str | None) -> dict:
    """params.measure를 역할→물리명으로 바꾼다. 사용자가 지정하지 않았고 global.measure가
    있으며 이 모듈이 measure 파라미터를 지원하면, global 값을 기본값으로 채운다(2026-07-24 G2).

    "measures"(복수, measure_summary 전용)는 다루지 않는다 — 전체 측정값을 나열하는 다른
    성격의 파라미터라 단일 measure 주입과 의미가 다르다(4단계 measure 확대 과제로 남긴다).
    """
    if params.get("measure"):
        return dict(params, measure=_resolve_measure_value(module_id, params["measure"], schema))
    if global_measure and "measure" in spec.params:
        return dict(params, measure=_resolve_measure_value(module_id, global_measure, schema))
    return params


def _build_entry(module_id: str, params: dict, tool: str | None, spec, title: str,
                 auto: bool = False, assembly: dict | None = None) -> dict:
    """resolved params + tool 검증 → plan에 들어갈 module entry 하나. 툴 오류는 그대로 올린다
    (dimension/measure와 달리 카탈로그와 어긋난 것이라 즉시 실패 대상, 기존 규칙과 동일).

    auto: 입력 모듈에 이미 "_auto"(자동 삽입 표시)가 있으면 그대로 이어받는다 — 안 그러면
    미리보기→"이대로 작성" 왕복에서 이 표시가 사라진다(2026-08-26 확인).

    assembly: {measure, module_name, sub_name}. 실행에는 안 쓰이지만 그대로 실어 보낸다 —
    이 entry가 곧 applied_steps가 되어 오른쪽 패널에 뜨고, 거기서 모듈을 이름으로 지목해
    편집한다(2026-09-01 카탈로그 재구조화).
    """
    entry = {"module_id": module_id, "params": params}
    if assembly:
        entry.update(assembly)
    if auto:
        entry["_auto"] = True
    if tool:
        available = spec.tools.get("available") or []
        if tool not in available:
            raise OptionsError(
                f"스텝 '{title}' 모듈 '{module_id}': 툴 '{tool}'을 쓸 수 없습니다. "
                f"사용 가능: {available or '(없음)'}"
            )
        entry["tools"] = [tool]
    return entry


def options_to_plan(options: dict, schema: Schema,
                    global_measure: str | None = None) -> tuple[dict, list[str]]:
    """옵션 JSON → 엔진 plan dict.

    - steps[].modules[]를 steps[].modules[]로 그대로 옮긴다(제목·순서 보존).
    - "tool"(단수)은 엔진이 쓰는 "tools"(리스트)로 감싼다.
    - 결론(module_id "conclusion")도 다른 스텝과 똑같이 plan에 그대로 옮긴다(2026-07-28,
      7단계 — 예전엔 runner가 결론을 특수 처리해 여기서 빼야 했지만, 이제 결론도 평범한
      실행 스텝이라 빼면 오히려 보고서에서 결론이 통째로 사라진다).
    - 알 수 없는 module_id·param·tool은 조용히 고치지 않고 즉시 OptionsError를 올린다.
    - finalize()를 내부에서 호출해 누락된 선행 모듈(period_dataset 등)을 자동 삽입한다
      (scenario_plan/auto_plan과 동일한 마지막 단계).

    global_measure: 옵션 JSON의 global.measure(역할 또는 물리명). 모듈이 measure를 직접
      지정하지 않았고 이 모듈이 measure 파라미터를 지원하면 기본값으로 채운다(2026-07-24 G2).

    반환: (finalize를 거친 최종 plan, notes) — notes는 finalize의 보정 내역.
    """
    registry = get_module_registry()
    notes: list[str] = []
    steps = []

    for step in options.get("steps", []):
        step_id = step.get("step_id", "?")
        title = step.get("title") or step_id
        raw_modules = step.get("modules", [])
        modules_out = []
        skip_reasons: list[str] = []

        for raw_m in raw_modules:
            # 조립 표현({measure, module_name, sub_name}) → 실행 표현(module_id + params).
            # 옛 형태(module_id 문자열 + params.dimension)도 여기서 흡수한다.
            try:
                reason = check_required(raw_m)
            except ModuleKeyError as e:
                raise OptionsError(f"스텝 '{title}': 모듈을 읽지 못했습니다 — {e}")
            if reason:
                notes.append(f"스텝 '{title}': {reason} 이 모듈을 건너뛰었습니다.")
                skip_reasons.append(reason)
                continue
            m = to_execution_entry(raw_m)
            module_id = m["module_id"]
            assembly = {k: m.get(k) for k in ("measure", "module_name", "sub_name")}

            spec = registry.get(module_id)
            if spec is None:
                raise OptionsError(
                    f"스텝 '{title}': 알 수 없는 모듈 '{module_id}'. "
                    f"등록된 모듈: {sorted(registry)}"
                )

            raw_params = dict(m.get("params") or {})
            unknown = set(raw_params) - set(spec.params)
            if unknown:
                raise OptionsError(
                    f"스텝 '{title}' 모듈 '{module_id}': 알 수 없는 param {sorted(unknown)}. "
                    f"사용 가능: {sorted(spec.params)}"
                )
            missing = [p for p, s in spec.params.items() if s.get("required") and p not in raw_params]
            if missing:
                raise OptionsError(f"스텝 '{title}' 모듈 '{module_id}': 필수 param 누락 {missing}")

            # dimension/measure는 module_id·param명과 달리 "이 데이터셋에 그 항목이 있는지"
            # 문제다 — 같은 스텝 구성이라도 데이터셋이 바뀌면(예: 미리보기 이후 다른 데이터셋으로
            # 실행) 얼마든지 없을 수 있는 정상적인 상황이라, 이 경우만 모듈을 건너뛴다(스텝
            # 전체를 죽이지 않음). module_id·param명·툴 오류는 카탈로그와 어긋난 것이라 여전히
            # 즉시 실패한다.
            missing_roles = [r for r in spec.required_roles if not schema.has(r)]
            if missing_roles:
                reason = f"필요한 역할 {missing_roles}이(가) 데이터셋에 없습니다."
                notes.append(f"스텝 '{title}' 모듈 '{module_id}'을 건너뛰었습니다: {reason}")
                skip_reasons.append(reason)
                continue

            tool = m.get("tool")
            auto = bool(m.get("_auto"))

            try:
                params = _resolve_dimension(module_id, raw_params, schema)
                params = _resolve_measure(module_id, params, spec, schema, global_measure)
            except OptionsError as e:
                notes.append(f"스텝 '{title}' 모듈 '{module_id}'을 건너뛰었습니다: {e}")
                skip_reasons.append(str(e))
                continue

            modules_out.append(
                _build_entry(module_id, params, tool, spec, title, auto=auto, assembly=assembly)
            )

        # step_id를 그대로 실어 보낸다 — applied_steps가 곧 오른쪽 패널의 스텝 카드이고,
        # 팝업이 "어느 스텝을 고칠지"를 이 값으로 지목한다(2026-09-01). 없으면 카드를 눌러도
        # 서버가 스텝을 찾지 못한다.
        sid = step.get("step_id")
        if not modules_out:
            if raw_modules:
                out = _build_disabled_step(title, raw_modules, skip_reasons, schema)
                if sid:
                    out["step_id"] = sid
                steps.append(out)
            continue
        out = {"title": title, "modules": modules_out}
        if sid:
            out["step_id"] = sid
        steps.append(out)

    plan = {
        "report_title": options.get("report_title") or options.get("scenario") or "보고서",
        "steps": steps,
    }
    plan, finalize_notes = finalize(plan, schema)
    return plan, notes + finalize_notes
