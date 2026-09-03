"""계획기 (Step 5) — 사용자 요청 → 조합(plan JSON).

시나리오를 **어디서 얻느냐만** 다르다. 그 뒤 실행은 같은 엔진이다.

  scenario_plan     : 등록된 시나리오면 LLM을 돌리지 않고 그 프리셋을 그대로 쓴다.
  compose_scenario  : 등록된 시나리오가 없으면 LLM이 카탈로그(스텝·모듈·툴)에서 골라
                      시나리오를 그 자리에서 조합한다.

계획기는 **DB를 건드리지 않는다.** 차원·측정 목록은 데이터소스 정의(JSON)에서 오므로, 실행 전에
"그런 차원 없다"를 잡아낼 수 있다. 실행 도중 터지는 것보다 계획 단계에서 고치는 편이 싸다.

이 파일은 실행 엔진(runner) 바깥이다. runner는 report_type도 SCENARIO도 모른다(§7.3).
"""
from __future__ import annotations

import difflib
import json
import re

from d2insight.engine.catalog import get_scenario, get_module_registry, get_step_registry
from d2insight.engine.catalog.steps import TMP_STEP_PREFIX, is_catalog_step
from d2insight.engine.catalog.module_key import (
    ModuleKeyError, check_required, label as module_label, to_execution_entry,
)
from d2insight.engine.datasource import DEFAULT_SOURCE_ID, build_meta_columns
from d2insight.engine.runner import STEP_SCOPED_LABELS
from d2insight.engine.schema import Schema
from d2insight.engine._llm import chat


class PlannerError(Exception):
    """계획을 세울 수 없음 (카탈로그에 없는 요청, 응답 파싱 실패 등)."""


# 맺음 — 어느 보고서든 마지막은 결론이다(operations._TAIL_MODULE_IDS와 같은 대상).
_CLOSING_STEP = "conclusion"
_CLOSING_MODULE = "conclusion"


# ── 카탈로그 → LLM에 보여줄 명세 ────────────────────────────────────────────
def catalog_digest() -> str:
    """LLM 계획기가 보는 카탈로그. purpose가 선택 근거다(§4.1).

    모듈 항목은 조립 표현({measure, module_name, sub_name})으로 보여준다 — sub_name·measure를
    받는 모듈인지, sub_name이 필수인지까지 알려줘야 LLM이 올바른 조합을 만든다.
    """
    lines = ["[모듈] — module_name과, 그 모듈이 받는 조립 필드"]
    for mid, spec in get_module_registry().items():
        # sub_name/measure는 조립 필드로 올라갔으므로 params 목록에서 뺀다 — LLM에게 같은
        # 것을 두 자리에 넣으라고 보여주면 안 된다.
        params = ", ".join(
            f"{k}{'*' if v.get('required') else ''}"
            for k, v in (spec.params or {}).items()
            if k not in ("dimension", "dimensions", "measure")
        ) or "-"
        tools = "/".join(spec.tools.get("available", [])) or "-"
        fields = []
        if spec.sub_name_pool:
            fields.append("sub_name*" if spec.sub_name_required else "sub_name")
        if spec.accepts_measure:
            fields.append("measure")
        lines.append(
            f"- {mid} ({spec.kind}): {spec.purpose}\n"
            f"    조립 필드: {', '.join(fields) or '없음'}   params: {params}   "
            f"tools: {tools}   requires: {spec.requires or '없음'}"
        )
    lines.append("")
    lines.append("[스텝 프리셋] — 그대로 써도 되고, 직접 제목을 지어 모듈을 담아도 된다")
    for sid, sec in get_step_registry().items():
        mods = ", ".join(module_label(m) for m in sec["default_modules"])
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

모듈 하나는 **세 필드의 조합**이다.

  module_name  어떻게 분석하는가 (카탈로그의 모듈 이름)
  sub_name     무엇별로 보는가 (제품·고객·지역·브랜드 등) — 받는 모듈만
  measure      무엇을 분석하는가 (금액·수량 등) — 받는 모듈만

규칙
1. 모듈은 **purpose를 근거로** 고른다. 요청과 무관한 모듈을 습관적으로 넣지 마라.
2. 카탈로그에 없는 module_name·step_id·tool을 지어내지 마라.
3. sub_name은 [분석 가능한 차원], measure는 [분석 가능한 측정] 목록에 있는 이름만 쓴다.
4. "조립 필드"에 없는 필드는 그 모듈에 넣지 마라. sub_name*는 반드시 지정해야 한다.
   sub_name을 안 쓰는 모듈(별표 없고 목록에도 없음)은 알아서 대상을 고른다.
5. 스텝은 하나의 이야기를 이루도록 묶는다. 빈 스텝은 만들지 않는다.
6. 선행 데이터(requires)는 시스템이 자동으로 채워 넣으니, 뿌리 모듈까지 일일이 넣지 않아도 된다.
7. **한 스텝 안에서 같은 조합을 두 번 쓰지 마라.** 차원별로 여러 개를 보고 싶으면 sub_name을
   다르게 해서 넣는다(예: sub_name="item_group" 하나와 sub_name="region" 하나).
8. 보고서는 보통 3~6개 스텝이면 충분하다. 요청이 좁으면 더 적게 짜라.

출력은 JSON 객체 하나뿐이다. 다른 텍스트를 덧붙이지 마라.

{
  "report_title": "보고서 제목",
  "steps": [
    {"step_id": "프리셋 id"},
    {"title": "직접 지은 제목", "modules": [
      {"module_name": "...", "sub_name": "...", "measure": "...", "tools": ["..."]}
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
def compose_scenario(message: str, source_id: str = DEFAULT_SOURCE_ID,
                     provider: str | None = None, schema: Schema | None = None) -> tuple[dict, list[str]]:
    """등록된 시나리오가 없을 때 — LLM이 카탈로그의 스텝·모듈·툴을 조합해 시나리오를 만든다.

    만들어진 조합은 등록된 시나리오와 같은 plan 형태이고, 이후 finalize·실행 흐름도 같다.
    """
    schema, data_text = data_digest(source_id, schema=schema)
    prompt = (
        f"[사용자 요청]\n{message}\n\n{data_text}\n\n{catalog_digest()}\n\n"
        "위 요청에 맞는 보고서 계획을 JSON으로 만들어라."
    )
    text = chat(
        [{"role": "user", "content": prompt}],
        grade="balanced", system=_SYSTEM, label="planner:compose",
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


def _step_query_params(modules: list[dict], registry: dict) -> dict:
    """스텝의 모듈들이 선언한 dimension/measure를 모아, 그 스텝에 자동 삽입되는 쿼리
    모듈(period_dataset)이 "이 스텝은 무엇이 필요한지" 알 수 있게 파라미터로 만든다
    (스텝 단위 쿼리, 2026-08-24) — 보고서 전체가 아니라 이 스텝에 필요한 것만 쿼리한다.
    """
    dims: list[str] = []
    measures: list[str] = []
    needs_history = False
    for m in modules:
        params = m.get("params") or {}
        val = params.get("dimension")
        if val and val not in dims:
            dims.append(val)
        for val in params.get("dimensions") or []:
            if val not in dims:
                dims.append(val)
        val = params.get("measure")
        if val and val not in measures:
            measures.append(val)
        spec = registry.get(m.get("module_id"))
        if spec and "history_dataset" in spec.requires:
            needs_history = True
    out: dict = {}
    if dims:
        out["dimensions"] = dims
    if measures:
        out["measures"] = measures
    if needs_history:
        out["needs_history"] = True
    return out


def _tmp_step_id(title: str, used: set[str]) -> str:
    """카탈로그에 없는 스텝의 id. 보고서 한 건 안에서만 유일하면 된다."""
    base = TMP_STEP_PREFIX + re.sub(r"\s+", "_", (title or "step").strip())
    sid, n = base, 2
    while sid in used:
        sid, n = f"{base}_{n}", n + 1
    return sid


def expand_steps(plan: dict) -> tuple[dict, list[str]]:
    """프리셋 스텝(step_id)을 실제 모듈 목록으로 펼친다.

    검증·의존성 계산은 모듈을 봐야 하므로, 무엇보다 먼저 펼쳐야 한다.
    존재하지 않는 step_id는 최근접 프리셋으로 추천 대체한다(§8).

    여기서 조립 표현({measure, module_name, sub_name})을 실행 표현(module_id + params)으로
    펼친다(2026-09-01 카탈로그 재구조화). 조립 필드는 지우지 않고 함께 남기므로, 이 뒤의
    검증·의존성 보정·실행은 예전과 똑같이 module_id/params만 보면 된다.
    """
    steps = get_step_registry()
    notes: list[str] = []
    expanded: list[dict] = []

    used_ids: set[str] = set()
    for sec in plan.get("steps", []):
        sid = sec.get("step_id")
        if is_catalog_step(sid):
            preset = steps.get(sid)
            if preset is None:
                near = suggest(sid, list(steps))
                if not near:
                    notes.append(f"'{sid}' 스텝은 카탈로그에 없어 제외했습니다.")
                    continue
                notes.append(f"'{sid}' 스텝이 없어 가장 비슷한 '{near}'로 대체했습니다.")
                preset = steps[near]
            raw_modules = sec.get("modules") or preset["default_modules"]
            entry = {"title": sec.get("title") or preset["title"], "step_id": sid,
                     "modules": _expand_modules(raw_modules, notes)}
        else:
            # 카탈로그에 없는 스텝(LLM이 새로 지은 것)에도 지목할 값이 있어야 한다 —
            # 없으면 오른쪽 카드를 눌러도 서버가 어느 스텝인지 모른다. 이미 tmp_ id가
            # 있으면 그대로 둔다(붙여넣기·정기 보고서에서 같은 스텝을 가리켜야 한다).
            title = sec.get("title") or "무제 스텝"
            entry = {"title": title, "step_id": sid or _tmp_step_id(title, used_ids),
                     "modules": _expand_modules(sec.get("modules") or [], notes)}
        used_ids.add(entry["step_id"])
        if sec.get("enabled") is False:
            entry["enabled"] = False
            entry["disabled_reason"] = sec.get("disabled_reason")
        expanded.append(entry)

    # 보고서는 결론으로 끝난다. 등록된 시나리오는 결론 스텝을 명시하지만, LLM이 조합한
    # 시나리오는 빠뜨릴 수 있다 — 그러면 본문만 있고 맺음이 없는 보고서가 나온다.
    if not any(m.get("module_id") == _CLOSING_MODULE
               for s in expanded for m in s.get("modules", [])):
        preset = steps.get(_CLOSING_STEP)
        if preset:
            expanded.append({
                "title": preset["title"], "step_id": _CLOSING_STEP,
                "modules": _expand_modules(preset["default_modules"], notes),
            })

    plan = dict(plan)
    plan["steps"] = expanded
    return plan, notes


def _expand_modules(raw_modules: list[dict], notes: list[str]) -> list[dict]:
    """모듈 항목을 조립 표현 → 실행 표현으로 펼친다. 옛 형태(module_id 문자열)도 흡수한다.

    필수 sub_name이 빠진 모듈은 조용히 넘기지 않고 여기서 제외하고 note를 남긴다 — 그대로
    두면 실행 도중 필수 파라미터 누락으로 터진다.
    """
    out: list[dict] = []
    for m in raw_modules:
        try:
            reason = check_required(m)
        except ModuleKeyError as e:
            notes.append(f"모듈을 읽지 못해 제외했습니다: {e}")
            continue
        if reason:
            notes.append(f"{reason} 이 모듈을 제외했습니다.")
            continue
        out.append(to_execution_entry(m))
    return out


def resolve_dependencies(plan: dict) -> tuple[dict, list[str]]:
    """requires를 역추적해 빠진 선행 모듈을 끼워 넣는다 (§6.1 자동 보정).

    LLM이 within_contribution만 골라도 total_variance가 없으면 실행되지 않는다. 계획 단계에서
    생산자(measure_summary → period_dataset)를 찾아 **필요한 스텝의 앞쪽**에 넣는다.
    실행 순서는 runner가 위상정렬로 다시 잡으므로, 여기서는 어느 스텝에 실릴지만 정한다.

    STEP_SCOPED_LABELS(actual_dataset 등, 스텝 단위 쿼리 — runner.py 참고)는 "이미 생산됨"
    판정을 스텝별로 따로 한다 — 스텝마다 자기만의 쿼리 모듈이 자동 삽입되게 하기 위함이다.
    그 외 이름표(total_variance 등 공용 수치)는 계획 전체에서 한 번만 생산되면 재사용한다
    (기존 동작 그대로).
    """
    registry = get_module_registry()
    notes: list[str] = []
    expanded = [dict(s, modules=[dict(m) for m in s["modules"]]) for s in plan.get("steps", [])]

    produced: set[str] = set()
    produced_by_step: dict[str, set[str]] = {}

    def _mark_produced(labels, step_key: str) -> None:
        for lbl in labels:
            if lbl in STEP_SCOPED_LABELS:
                produced_by_step.setdefault(step_key, set()).add(lbl)
            else:
                produced.add(lbl)

    def _is_produced(label: str, step_key: str) -> bool:
        if label in STEP_SCOPED_LABELS:
            return label in produced_by_step.get(step_key, set())
        return label in produced

    for sec in expanded:
        if sec.get("enabled") is False:
            continue
        step_key = sec.get("title") or ""
        for m in sec["modules"]:
            spec = registry.get(m.get("module_id"))
            if spec:
                _mark_produced(spec.produces, step_key)

    # 각 스텝을 훑으며 아직 없는 선행 이름표의 생산자를 그 스텝 앞에 삽입한다.
    for sec in expanded:
        if sec.get("enabled") is False:
            continue
        step_key = sec.get("title") or ""
        inserted: list[dict] = []
        for m in list(sec["modules"]):
            spec = registry.get(m.get("module_id"))
            if not spec:
                continue
            for label in spec.requires:
                if _is_produced(label, step_key):
                    continue
                producer = _producer_of(label)
                if not producer:
                    notes.append(f"'{label}'을 생산하는 모듈이 카탈로그에 없습니다 "
                                 f"({m['module_id']}는 실행되지 못합니다).")
                    continue
                entry = {"module_id": producer, "module_name": producer,
                         "measure": None, "sub_name": None, "_auto": True}
                if any(p in STEP_SCOPED_LABELS for p in registry[producer].produces):
                    entry["params"] = _step_query_params(sec["modules"], registry)
                inserted.append(entry)
                _mark_produced(registry[producer].produces, step_key)
                notes.append(f"{m['module_id']}에 필요한 '{label}'을 위해 {producer}를 자동 추가했습니다.")
        if inserted:
            sec["modules"] = inserted + sec["modules"]

    # 삽입된 생산자가 또 다른 선행을 요구할 수 있다(measure_summary → period_dataset).
    # 더 이상 추가할 것이 없을 때까지 반복한다.
    for _ in range(len(registry)):
        missing_found = False
        for sec in expanded:
            if sec.get("enabled") is False:
                continue
            step_key = sec.get("title") or ""
            for m in list(sec["modules"]):
                spec = registry.get(m.get("module_id"))
                if not spec:
                    continue
                for label in spec.requires:
                    if _is_produced(label, step_key):
                        continue
                    producer = _producer_of(label)
                    if not producer:
                        continue
                    entry = {"module_id": producer, "module_name": producer,
                         "measure": None, "sub_name": None, "_auto": True}
                    if any(p in STEP_SCOPED_LABELS for p in registry[producer].produces):
                        entry["params"] = _step_query_params(sec["modules"], registry)
                    sec["modules"].insert(0, entry)
                    _mark_produced(registry[producer].produces, step_key)
                    notes.append(f"{m['module_id']}에 필요한 '{label}'을 위해 "
                                 f"{producer}를 자동 추가했습니다.")
                    missing_found = True
        if not missing_found:
            break

    plan = dict(plan)
    plan["steps"] = [s for s in expanded if s["modules"]]
    for s in plan["steps"]:
        for m in s["modules"]:
            if m.get("module_id") == "period_dataset":
                print(f"[DEBUG-resolve_dependencies] step={s.get('title')!r} period_dataset _auto={m.get('_auto')!r}")
    return plan, notes


def _resolve_module_params(mid: str, m: dict, spec, schema: Schema,
                           dims: list[str], measures: list[str], notes: list[str]) -> dict | None:
    """모듈 하나의 dimension/measure/필수파라미터/툴을 해석한다. 못 살리면 None(제외)."""
    m = dict(m, module_id=mid)
    params = dict(m.get("params") or {})
    for key, pool in (("dimension", dims), ("measure", measures)):
        val = params.get(key)
        if not val or val in pool:
            continue
        # 역할 이름(item/party/amount 등, schema.py ROLE_*)이면 조용히 물리명으로
        # 바꾼다 — 오타 교정이 아니라 설계된 경로이므로 근사매칭 note를 남기지 않는다.
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
            return None
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
    return m


def _build_disabled_step(title: str, raw_modules: list[dict], reasons: list[str]) -> dict:
    """스텝의 모듈이 전부 실행 불가일 때 버리지 않고 비활성 스텝(enabled=False)으로 남긴다."""
    reason_text = " / ".join(dict.fromkeys(reasons)) or "필요한 조건을 이 데이터셋에서 찾지 못했습니다."
    return {"title": title, "modules": raw_modules, "enabled": False, "disabled_reason": reason_text}


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
        if sec.get("enabled") is False:
            out_steps.append(sec)
            continue
        modules = []
        skip_reasons: list[str] = []
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

            missing_roles = [r for r in spec.required_roles if not schema.has(r)]
            if missing_roles:
                reason = f"필요한 역할 {missing_roles}이(가) 없습니다."
                notes.append(f"{mid}: {reason} 제외했습니다.")
                skip_reasons.append(reason)
                continue

            resolved = _resolve_module_params(mid, m, spec, schema, dims, measures, notes)
            if resolved is not None:
                modules.append(resolved)
            else:
                skip_reasons.append(f"{mid}에 필요한 값을 이 데이터셋에서 찾지 못했습니다.")

        if modules:
            out_steps.append(dict(sec, modules=modules))
        elif sec.get("modules"):
            out_steps.append(_build_disabled_step(
                sec.get("title") or "무제 스텝", sec.get("modules"), skip_reasons,
            ))
        else:
            notes.append(f"스텝 '{sec.get('title')}'은 실행할 모듈이 없어 제외했습니다.")

    if not out_steps:
        raise PlannerError("실행할 수 있는 모듈이 없습니다. 요청을 다시 말씀해 주세요.")

    plan = dict(plan)
    plan["steps"] = out_steps
    return plan, notes


def finalize(plan: dict, schema: Schema) -> tuple[dict, list[str]]:
    """펼치기 → 검증 → 의존성 보정."""
    plan, notes1 = expand_steps(plan)
    plan, notes2 = validate_plan(plan, schema)
    plan, notes3 = resolve_dependencies(plan)
    return plan, notes1 + notes2 + notes3
