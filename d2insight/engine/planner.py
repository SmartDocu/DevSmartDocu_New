"""계획기 (Step 5) — 사용자 요청 → 조합(plan JSON).

지시서 §4.2 결정: **프리셋/자유 계획은 방식이 다르다. 실행 엔진만 공유한다.**

  프리셋(scenario_plan): 등록된 시나리오 요청이면 LLM을 돌리지 않고 유형별 기본 세트(SCENARIO)를
    그대로 쓴다. 이것이 기본 동작이다 — 사람이 미리 검증해둔 고정 스텝 구성.
  자유 계획(auto_plan): 등록된 4개 시나리오 어디에도 해당하지 않는 요청에 한해, 카탈로그의
    purpose를 근거로 LLM이 그 자리에서 조합을 짠다. 매번 다른 조합이 나올 수 있는 예외 경로다.

계획기는 **DB를 건드리지 않는다.** 차원·측정 목록은 데이터소스 정의(JSON)에서 오므로, 실행 전에
"그런 차원 없다"를 잡아낼 수 있다. 실행 도중 터지는 것보다 계획 단계에서 고치는 편이 싸다.

이 파일은 실행 엔진(runner) 바깥이다. runner는 report_type도 SCENARIO도 모른다(§7.3).
"""
from __future__ import annotations

import difflib
import json
import re

from d2insight.engine.catalog import get_scenario, get_module_registry, get_step_registry
from d2insight.engine.datasource import DEFAULT_SOURCE_ID, build_meta_columns
from d2insight.engine.schema import Schema
from d2insight.engine._llm import chat


class PlannerError(Exception):
    """계획을 세울 수 없음 (카탈로그에 없는 요청, 응답 파싱 실패 등)."""


# ── 카탈로그 → LLM에 보여줄 명세 ────────────────────────────────────────────
def catalog_digest() -> str:
    """LLM 계획기가 보는 카탈로그. purpose가 선택 근거다(§4.1)."""
    lines = ["[모듈]"]
    for mid, spec in get_module_registry().items():
        params = ", ".join(
            f"{k}{'*' if v.get('required') else ''}" for k, v in (spec.params or {}).items()
        ) or "-"
        tools = "/".join(spec.tools.get("available", [])) or "-"
        lines.append(
            f"- {mid} ({spec.kind}): {spec.purpose}\n"
            f"    params: {params}   tools: {tools}   requires: {spec.requires or '없음'}"
        )
    lines.append("")
    lines.append("[스텝 프리셋] — 그대로 써도 되고, 직접 제목을 지어 모듈을 담아도 된다")
    for sid, sec in get_step_registry().items():
        mods = ", ".join(m["module_id"] for m in sec["default_modules"])
        lines.append(f"- {sid}: \"{sec['title']}\" ({mods})")
    return "\n".join(lines)


def data_digest(source_id: str = DEFAULT_SOURCE_ID, schema: Schema | None = None) -> tuple[Schema, str]:
    """분석 가능한 차원·측정. DB 없이 데이터소스 정의만으로 만든다.

    schema를 직접 주면(업로드 데이터처럼 파일 기반 정의가 아닌 경우) 그것을 그대로 쓰고,
    없으면 source_id로 datasources/<source_id>.json을 읽는다.
    """
    if schema is None:
        schema = Schema(build_meta_columns(source_id))
    text = (
        f"[분석 가능한 차원] {', '.join(schema.dimensions)}\n"
        f"[분석 가능한 측정] {', '.join(schema.measures)} (핵심: {schema.key_measure})"
    )
    return schema, text


_SYSTEM = """당신은 데이터 분석 보고서의 구성을 짜는 설계자다.
사용자 요청을 읽고, 카탈로그의 모듈을 조합해 보고서 계획(JSON)을 만든다.

규칙
1. 모듈은 **purpose를 근거로** 고른다. 요청과 무관한 모듈을 습관적으로 넣지 마라.
2. 카탈로그에 없는 module_id·step_id·tool을 지어내지 마라.
3. params의 dimension/measure는 반드시 [분석 가능한 차원/측정] 목록에 있는 이름을 쓴다.
4. 스텝은 하나의 이야기를 이루도록 묶는다. 빈 스텝은 만들지 않는다.
5. 선행 데이터(requires)는 시스템이 자동으로 채워 넣으니, 뿌리 모듈까지 일일이 넣지 않아도 된다.
6. 같은 모듈을 파라미터만 바꿔 여러 번 넣어도 된다(예: 차원별 실적집계).
7. 보고서는 보통 3~6개 스텝이면 충분하다. 요청이 좁으면 더 적게 짜라.

출력은 JSON 객체 하나뿐이다. 다른 텍스트를 덧붙이지 마라.

{
  "report_title": "보고서 제목",
  "steps": [
    {"step_id": "프리셋 id"},
    {"title": "직접 지은 제목", "modules": [
      {"module_id": "...", "params": {"dimension": "..."}, "tools": ["..."]}
    ]}
  ]
}"""


def _parse_plan(text: str) -> dict:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PlannerError(f"계획기 응답을 JSON으로 읽지 못했습니다: {e}") from e
    if not isinstance(plan, dict) or not plan.get("steps"):
        raise PlannerError("계획기 응답에 steps가 없습니다.")
    return plan


# ── 자동 모드 ────────────────────────────────────────────────────────────────
def auto_plan(message: str, source_id: str = DEFAULT_SOURCE_ID,
              provider: str | None = None, schema: Schema | None = None) -> tuple[dict, list[str]]:
    """순수 purpose 기반 LLM 계획 (§4.1). 보고서 유형 고정 세트를 쓰지 않는다."""
    schema, data_text = data_digest(source_id, schema=schema)
    prompt = (
        f"[사용자 요청]\n{message}\n\n{data_text}\n\n{catalog_digest()}\n\n"
        "위 요청에 맞는 보고서 계획을 JSON으로 만들어라."
    )
    text = chat(
        [{"role": "user", "content": prompt}],
        grade="balanced", system=_SYSTEM, label="planner:auto",
        call_type="planning", provider=provider,
    )
    plan = _parse_plan(text)
    plan, notes = finalize(plan, schema)
    return plan, notes


# ── 프리셋 모드 ──────────────────────────────────────────────────────────────
def scenario_plan(report_type: str, source_id: str = DEFAULT_SOURCE_ID,
                schema: Schema | None = None) -> tuple[dict, list[str]]:
    """유형별 기본 세트를 편집용으로 꺼낸다 (§4.2). LLM을 돌리지 않는다."""
    base = get_scenario(report_type)
    if base is None:
        raise PlannerError(
            f"'{report_type}' 유형의 기본 세트가 없습니다. "
            f"사용 가능: {list_report_types()}. 자동 모드로 진행하거나 유형을 선택하세요."
        )
    schema, _ = data_digest(source_id, schema=schema)
    plan = json.loads(json.dumps(base))          # 원본 템플릿 보호(편집은 사본에서)
    return finalize(plan, schema)


def list_report_types() -> list[str]:
    from d2insight.engine.catalog.scenarios import SCENARIO_REGISTRY
    return list(SCENARIO_REGISTRY)


# ── 카탈로그에 없는 요청 → 최근접 추천 (§8 결정 2026-07-10) ──────────────────
def suggest(name: str, candidates: list[str]) -> str | None:
    """가장 비슷한 항목 하나. 없으면 None."""
    hit = difflib.get_close_matches(str(name), candidates, n=1, cutoff=0.4)
    return hit[0] if hit else None


# ── 의존성 자동 보정 + 검증 ──────────────────────────────────────────────────
def _producer_of(label: str) -> str | None:
    for mid, spec in get_module_registry().items():
        if label in spec.produces:
            return mid
    return None


def expand_steps(plan: dict) -> tuple[dict, list[str]]:
    """프리셋 스텝(step_id)을 실제 모듈 목록으로 펼친다.

    검증·의존성 계산은 모듈을 봐야 하므로, 무엇보다 먼저 펼쳐야 한다.
    존재하지 않는 step_id는 최근접 프리셋으로 추천 대체한다(§8).
    """
    steps = get_step_registry()
    notes: list[str] = []
    expanded: list[dict] = []

    for sec in plan.get("steps", []):
        sid = sec.get("step_id")
        if sid:
            preset = steps.get(sid)
            if preset is None:
                near = suggest(sid, list(steps))
                if not near:
                    notes.append(f"'{sid}' 스텝은 카탈로그에 없어 제외했습니다.")
                    continue
                notes.append(f"'{sid}' 스텝이 없어 가장 비슷한 '{near}'로 대체했습니다.")
                preset = steps[near]
            expanded.append({
                "title": sec.get("title") or preset["title"],
                "modules": [dict(m) for m in (sec.get("modules") or preset["default_modules"])],
            })
        else:
            expanded.append({"title": sec.get("title") or "무제 스텝",
                             "modules": [dict(m) for m in (sec.get("modules") or [])]})

    plan = dict(plan)
    plan["steps"] = expanded
    return plan, notes


def resolve_dependencies(plan: dict) -> tuple[dict, list[str]]:
    """requires를 역추적해 빠진 선행 모듈을 끼워 넣는다 (§6.1 자동 보정).

    LLM이 within_contribution만 골라도 total_variance가 없으면 실행되지 않는다. 계획 단계에서
    생산자(measure_summary → period_dataset)를 찾아 **필요한 스텝의 앞쪽**에 넣는다.
    실행 순서는 runner가 위상정렬로 다시 잡으므로, 여기서는 어느 스텝에 실릴지만 정한다.
    """
    registry = get_module_registry()
    notes: list[str] = []
    expanded = [dict(s, modules=[dict(m) for m in s["modules"]]) for s in plan.get("steps", [])]

    produced: set[str] = set()
    for sec in expanded:
        for m in sec["modules"]:
            spec = registry.get(m.get("module_id"))
            if spec:
                produced.update(spec.produces)

    # 각 스텝을 훑으며 아직 없는 선행 이름표의 생산자를 그 스텝 앞에 삽입한다.
    for sec in expanded:
        inserted: list[dict] = []
        for m in list(sec["modules"]):
            spec = registry.get(m.get("module_id"))
            if not spec:
                continue
            for label in spec.requires:
                if label in produced:
                    continue
                producer = _producer_of(label)
                if not producer:
                    notes.append(f"'{label}'을 생산하는 모듈이 카탈로그에 없습니다 "
                                 f"({m['module_id']}는 실행되지 못합니다).")
                    continue
                inserted.append({"module_id": producer})
                produced.update(registry[producer].produces)
                notes.append(f"{m['module_id']}에 필요한 '{label}'을 위해 {producer}를 자동 추가했습니다.")
        if inserted:
            sec["modules"] = inserted + sec["modules"]

    # 삽입된 생산자가 또 다른 선행을 요구할 수 있다(measure_summary → period_dataset).
    # 더 이상 추가할 것이 없을 때까지 반복한다.
    for _ in range(len(registry)):
        missing_found = False
        for sec in expanded:
            for m in list(sec["modules"]):
                spec = registry.get(m.get("module_id"))
                if not spec:
                    continue
                for label in spec.requires:
                    if label in produced:
                        continue
                    producer = _producer_of(label)
                    if not producer:
                        continue
                    sec["modules"].insert(0, {"module_id": producer})
                    produced.update(registry[producer].produces)
                    notes.append(f"{m['module_id']}에 필요한 '{label}'을 위해 "
                                 f"{producer}를 자동 추가했습니다.")
                    missing_found = True
        if not missing_found:
            break

    plan = dict(plan)
    plan["steps"] = [s for s in expanded if s["modules"]]
    return plan, notes


def validate_plan(plan: dict, schema: Schema) -> tuple[dict, list[str]]:
    """모듈·툴·파라미터가 실재하는지 확인하고, 없으면 최근접 추천으로 고친다 (§8).

    조용히 넘기지 않는다 — 고친 것은 전부 notes로 남겨 사용자에게 알린다.
    """
    registry = get_module_registry()
    module_ids = list(registry)
    dims, measures = schema.dimensions, schema.measures
    notes: list[str] = []

    out_steps = []
    for sec in plan.get("steps", []):
        modules = []
        for m in sec.get("modules", []):
            mid = m.get("module_id")
            if mid not in registry:
                near = suggest(mid, module_ids)
                if not near:
                    notes.append(f"'{mid}' 모듈은 카탈로그에 없어 제외했습니다.")
                    continue
                notes.append(f"'{mid}' 모듈이 없어 가장 비슷한 '{near}'로 대체했습니다.")
                mid = near
            spec = registry[mid]
            m = dict(m, module_id=mid)

            params = dict(m.get("params") or {})
            for key, pool in (("dimension", dims), ("measure", measures)):
                val = params.get(key)
                if not val or val in pool:
                    continue
                # 역할 이름(item/party/amount 등, schema.py ROLE_*)이면 조용히 물리명으로
                # 바꾼다 — 오타 교정이 아니라 설계된 경로이므로 근사매칭 note를 남기지 않는다.
                # options.py의 options_to_plan과 같은 우선순위(2026-07-24, G9 — steps.py를
                # 역할명으로 옮기면서, 이 경로(scenario_plan/auto_plan)도 역할을 몰라 조용히
                # 깨지지 않게 맞췄다).
                role_col = schema.column(val)
                if role_col:
                    params[key] = role_col
                    continue
                near = suggest(val, pool)
                if near:
                    notes.append(f"{mid}: {key} '{val}'이 없어 '{near}'로 바꿨습니다.")
                    params[key] = near
                else:
                    notes.append(f"{mid}: {key} '{val}'이 없어 제거했습니다 "
                                 f"(사용 가능: {', '.join(pool)}).")
                    params.pop(key)
            # 필수 파라미터 누락 — 실행하면 실패하므로 계획 단계에서 알린다.
            for key, meta in (spec.params or {}).items():
                if meta.get("required") and key not in params:
                    notes.append(f"{mid}: 필수 파라미터 '{key}'가 없어 이 모듈을 제외했습니다.")
                    params = None
                    break
            if params is None:
                continue
            m["params"] = params

            available = spec.tools.get("available", [])
            tools = [t for t in (m.get("tools") or []) if t]
            if tools and available:
                fixed = []
                for t in tools:
                    if t in available:
                        fixed.append(t)
                    else:
                        near = suggest(t, available)
                        notes.append(
                            f"{mid}: 툴 '{t}'을 쓸 수 없어 "
                            + (f"'{near}'로 바꿨습니다." if near else "기본 툴로 되돌렸습니다.")
                        )
                        if near:
                            fixed.append(near)
                m["tools"] = fixed
            modules.append(m)

        if modules:
            out_steps.append(dict(sec, modules=modules))
        else:
            notes.append(f"스텝 '{sec.get('title')}'은 실행할 모듈이 없어 제외했습니다.")

    if not out_steps:
        raise PlannerError("실행할 수 있는 모듈이 없습니다. 요청을 다시 말씀해 주세요.")

    plan = dict(plan)
    plan["steps"] = out_steps
    return plan, notes


def finalize(plan: dict, schema: Schema) -> tuple[dict, list[str]]:
    """펼치기 → 검증 → 의존성 보정.

    순서가 중요하다. 프리셋을 펼쳐야 모듈이 보이고, 없는 모듈을 걷어내야 의존성 계산이 어긋나지 않는다.
    """
    plan, notes1 = expand_steps(plan)
    plan, notes2 = validate_plan(plan, schema)
    plan, notes3 = resolve_dependencies(plan)
    return plan, notes1 + notes2 + notes3
