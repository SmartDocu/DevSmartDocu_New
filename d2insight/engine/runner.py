"""실행 엔진 (Step 3) — 조합 JSON → 위상정렬 → 모듈 실행 → 결론 → 보고서 조립.

지시서 §6(실행 순서·조립), §11 Step 3, 그리고 실패 처리 정책(Step 2)을 구현한다.
자동/수동/디폴트-제시가 모두 이 하나의 실행 엔진을 공유한다(계획 단계만 다름, §4.2).

이 엔진은 카탈로그(Step/Module Registry)의 "내용물"을 모른다. resolver(카탈로그)로부터
모듈 명세(ModuleSpec)와 섹션 프리셋만 받아 그릇 역할만 한다 → 카탈로그에 무엇이 추가되든 불변.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from d2insight.engine.chart import render_chart_markdown
from d2insight.engine.context import SharedContext
from d2insight.engine.format import table_to_markdown
from d2insight.engine.types import DEFAULT_LAYOUT, ModuleResult, ModuleSpec, Render

# 섹션 제목에 실수로 새어든 스펙 번호(§11, §12-A 등)를 출력 직전에 제거하는 방어 패턴.
# 스펙 번호는 코드 주석·설계 문서에만 존재해야 하며 보고서 본문에 노출되면 안 된다.
_SPEC_MARK = re.compile(r"^\s*§\s*\d+[\-A-Za-z]*\.?\s*")


def clean_title(title: str) -> str:
    """섹션 제목에서 선두의 '§NN.' 류 스펙 마커를 제거한다(중복 적용 안전)."""
    prev = None
    out = title or ""
    while out != prev:
        prev = out
        out = _SPEC_MARK.sub("", out)
    return out.strip()


class PlanError(Exception):
    """조합(plan) 자체가 잘못됨 (빈 섹션, 미등록 모듈, 이름표 충돌, 순환 의존 등)."""


class Catalog(Protocol):
    """실행 엔진이 카탈로그에 요구하는 최소 인터페이스 (실제 레지스트리는 이 형태를 만족)."""
    def get_module(self, module_id: str) -> ModuleSpec: ...
    def get_step(self, step_id: str) -> dict: ...        # {"title","default_modules"}
    def narrate_step(self, step_label: str, items: list[dict], ctx: SharedContext) -> dict: ...


@dataclass
class ModuleInstance:
    """plan을 펼쳐 만든 실행 단위 하나."""
    step_label: str
    module_id: str
    spec: ModuleSpec
    params: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    layout: list[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        return f"{self.step_label} / {self.module_id}"


# ── 1. plan 펼치기 ──────────────────────────────────────────────────────────
def expand_plan(plan: dict, catalog: Catalog) -> tuple[list[ModuleInstance], list[str]]:
    """조합 JSON(§8)을 ModuleInstance 목록 + 섹션 표시 순서로 펼친다.

    - step_id: 프리셋 섹션 참조. modules 생략 시 디폴트 모듈로 채움.
    - title + custom: 사용자 정의 섹션.
    - 빈 섹션 금지.
    """
    instances: list[ModuleInstance] = []
    step_order: list[str] = []

    for sec in plan.get("steps", []):
        if sec.get("step_id"):
            preset = catalog.get_step(sec["step_id"])
            label = clean_title(sec.get("title") or preset.get("title") or sec["step_id"])
            modules = sec.get("modules") or preset.get("default_modules") or []
        else:
            label = clean_title(sec.get("title") or "무제 섹션")
            modules = sec.get("modules") or []

        if not modules:
            raise PlanError(f"빈 섹션은 허용되지 않습니다: '{label}'")

        step_order.append(label)
        for m in modules:
            spec = catalog.get_module(m["module_id"])
            tools = m.get("tools") or ([spec.tools["default"]] if spec.tools.get("default") else [])
            instances.append(ModuleInstance(
                step_label=label,
                module_id=m["module_id"],
                spec=spec,
                params=m.get("params") or {},
                tools=tools,
                layout=m.get("layout") or list(spec.layout),   # 계획 > 모듈 명세 > 기본값
            ))
    return instances, step_order


def plan_composition(plan: dict, catalog: Catalog) -> list[dict]:
    """plan을 섹션→모듈→툴 구조의 직렬화 가능한 목록으로 펼친다(실행 전 조합 확인용).

    expand_plan을 재사용해 **기본 툴까지 채워진** 실제 실행 조합을 만든다. 순수 함수라
    부작용이 없고, 터미널/로그에 JSON으로 찍기 좋다.
    """
    instances, step_order = expand_plan(plan, catalog)
    by_step: dict[str, list[dict]] = {label: [] for label in step_order}
    for inst in instances:
        by_step.setdefault(inst.step_label, []).append({
            "module": inst.module_id,
            "tools": inst.tools,
            "params": inst.params,
        })
    return [{"step": label, "modules": by_step[label]} for label in step_order]


# ── 2. 위상 정렬 (requires 기반) ─────────────────────────────────────────────
def topo_order(instances: list[ModuleInstance]) -> list[ModuleInstance]:
    """requires/produces 이름표로 실행 순서를 계산한다. 의존 없는 것끼리는 plan 순서 유지.

    같은 이름표를 두 인스턴스가 produces 하면(같은 모듈 다중 실행, §3.4-2) 네임스페이스가 필요하며
    이는 후속 과제다. 지금은 명확한 오류로 surface 한다(조용한 오작동 방지).
    """
    producer: dict[str, int] = {}
    for i, inst in enumerate(instances):
        for lbl in inst.spec.produces:
            if lbl in producer:
                raise PlanError(
                    f"이름표 '{lbl}'를 두 모듈이 생산합니다 "
                    f"({instances[producer[lbl]].module_id}, {inst.module_id}). "
                    f"같은 모듈 다중 실행 시 이름표 네임스페이스는 후속 과제입니다(§3.4-2)."
                )
            producer[lbl] = i

    deps: dict[int, set[int]] = {i: set() for i in range(len(instances))}
    for i, inst in enumerate(instances):
        for lbl in inst.spec.requires:
            if lbl in producer and producer[lbl] != i:
                deps[i].add(producer[lbl])

    order: list[int] = []
    resolved: set[int] = set()
    remaining = list(range(len(instances)))
    while remaining:
        progressed = False
        for i in list(remaining):          # plan 순서대로 훑어 안정 정렬
            if deps[i] <= resolved:
                order.append(i)
                resolved.add(i)
                remaining.remove(i)
                progressed = True
        if not progressed:
            stuck = [instances[i].module_id for i in remaining]
            raise PlanError(f"순환 의존 또는 해소 불가한 선행관계: {stuck}")
    return [instances[i] for i in order]


# ── 3. 실행 ─────────────────────────────────────────────────────────────────
def execute(order: list[ModuleInstance], ctx: SharedContext) -> dict[str, list[tuple[ModuleInstance, Render]]]:
    """위상 순서대로 모듈을 실행한다.

    실패 처리(Step 2):
      - 선행 이름표 부재 → 생략 기록(선행 모듈이 실패/생략됐다는 뜻). 후속으로 전파됨.
      - 실행 예외/실패 → 실패 기록. produces 이름표는 저장되지 않아 의존 모듈이 자동 생략됨.
    반환: 섹션 표시명 → [(ModuleInstance, Render), ...]  (렌더 순서 보존)

    모듈은 계산만 한다. 본문 해설(narrative)은 이 단계 뒤 섹션 단위로 LLM이 채운다(narrate).
    """
    step_renders: dict[str, list[tuple[ModuleInstance, Render]]] = {}

    for inst in order:
        missing = ctx.missing_requires(inst.spec.requires)
        if missing:
            ctx.mark_skipped(inst.ref, f"선행 데이터 {missing} 없음(선행 모듈 실패·생략 추정)")
            continue

        try:
            result: ModuleResult = inst.spec.run(ctx, inst.params, inst.tools)
        except Exception as e:                 # 조용히 생략하지 않고 기록
            ctx.mark_failed(inst.ref, f"{type(e).__name__}: {e}")
            continue

        if result.status != "ok":
            ctx.mark_failed(inst.ref, result.error or "알 수 없는 실패")
            continue

        for lbl, val in result.outputs.items():
            ctx.put(lbl, val)
        if result.render is not None:
            ctx.add_summary(inst.ref, result.render.summary)   # 결론 전용(본문에는 안 나감)
            step_renders.setdefault(inst.step_label, []).append((inst, result.render))

    return step_renders


# ── 4. 해설 (섹션 단위 LLM 1회, 결정 2026-07-14) ─────────────────────────────
def narrate(step_order: list[str],
            step_renders: dict[str, list[tuple[ModuleInstance, Render]]],
            catalog: Catalog, ctx: SharedContext) -> None:
    """섹션마다 해설자를 1회 호출해 각 모듈의 narrative를 채운다(제자리 수정).

    모듈별로 따로 호출하지 않는 이유: 같은 섹션의 모듈들은 하나의 이야기를 이루므로, 해설자가
    그 섹션의 표를 **전부 보고** 써야 앞뒤가 이어진다. 호출 1회로 문맥과 비용을 함께 잡는다.

    해설 실패는 본문을 죽이지 않는다. 실패를 기록하고 summary로 대체한다(조용히 감추지 않음).

    모듈이 narrative를 이미 스스로 채워왔으면(결론처럼, 2026-07-28 7단계) 이 단계를 건너뛴다 —
    일반 해설자가 이미 완성된 본문 위에 다시 써서 덮어쓰지 않도록. 지금은 conclusion만 해당.
    """
    for label in step_order:
        entries = step_renders.get(label)
        if not entries:
            continue
        if all(render.narrative for _, render in entries):
            continue

        # 같은 모듈이 파라미터만 달리해 여러 번 실행될 수 있다(§3.4-2). module_id를 키로 쓰면
        # 해설이 서로 덮어써져 엉뚱한 표에 붙는다 → 인스턴스마다 고유 키를 준다.
        seen: dict[str, int] = {}
        keys: list[str] = []
        for inst, _ in entries:
            n = seen.get(inst.module_id, 0) + 1
            seen[inst.module_id] = n
            keys.append(inst.module_id if n == 1 else f"{inst.module_id}#{n}")

        items = [{
            "key": key,
            "module_id": inst.module_id,
            "purpose": inst.spec.purpose,
            "narrative_hint": inst.spec.narrative_hint,
            "model_tier": inst.spec.model_tier,
            "params": inst.params,          # 어느 차원의 표인지 구분하려면 파라미터가 필요하다
            "summary": render.summary,
            "key_value": render.key_value,
            "table": render.table,
        } for key, (inst, render) in zip(keys, entries)]

        try:
            written = catalog.narrate_step(label, items, ctx) or {}
        except Exception as e:
            ctx.mark_failed(f"{label} / 해설", f"{type(e).__name__}: {e} (요약문으로 대체)")
            written = {}

        for key, (_, render) in zip(keys, entries):
            render.narrative = written.get(key) or render.summary


# ── 5. 보고서 조립 ───────────────────────────────────────────────────────────
def _render_block(render: Render, layout: list[str] | None = None) -> list[str]:
    """layout 순서대로 블록을 찍는다. summary는 본문에 넣지 않는다(결론 전용).

    layout 어휘: narrative | key_value | table | chart. 순서는 모듈·계획이 정한다
    (설명 먼저도, 그림 먼저도 가능 — 엔진은 순서를 강제하지 않는다).
    """
    order = layout or DEFAULT_LAYOUT
    lines: list[str] = []

    for block in order:
        if block == "narrative" and render.narrative:
            lines.append(render.narrative)
        elif block == "key_value" and render.key_value:
            lines.append(" · ".join(f"{k}: {v}" for k, v in render.key_value.items()))
        elif block == "table" and render.table is not None:
            lines.append(table_to_markdown(render.table))   # 서식은 format.py가 통일(해설자와 동일)
        elif block == "chart" and render.chart is not None:
            img = render_chart_markdown(render.chart)        # 스펙 → base64 이미지 마크다운
            if img:
                lines.append(img)

    return [ln for ln in lines if ln]


def assemble(plan: dict, step_order: list[str],
             step_renders: dict[str, list[tuple[ModuleInstance, Render]]],
             ctx: SharedContext) -> str:
    """섹션을 순서대로 조립한다(§6.2). 결론도 이제 평범한 스텝 하나라 이 루프가 그대로
    처리한다(2026-07-28, 7단계 — 예전엔 conclusion을 별도 인자로 받아 특수 처리했다).
    """
    md: list[str] = [f"# {clean_title(plan.get('report_title') or '보고서')}"]

    for label in step_order:
        entries = step_renders.get(label)
        if not entries:
            continue                            # 섹션 내 모듈이 전부 실패·생략된 경우
        md.append(f"## {label}")
        for inst, render in entries:
            md.extend(_render_block(render, render.layout or inst.layout))

    # 실패·생략 안내 (조용히 감추지 않는다)
    notes = ctx.notes()
    if notes:
        md.append("### 분석 생략 안내")
        for n in notes:
            verb = "실패" if n["kind"] == "failed" else "생략"
            md.append(f"- {n['ref']}: {n['reason']} → {verb}")

    return "\n\n".join(md)


# ── 6. 최상위 진입 ───────────────────────────────────────────────────────────
def run_plan(plan: dict, catalog: Catalog, ctx: SharedContext | None = None) -> dict:
    """조합(plan JSON) 하나를 실행해 보고서를 만든다. 자동/수동 공통 진입점.

    계산(execute) → 해설(narrate) → 조립 순서다. 결론도 execute 단계의 스텝 하나로 실행된다
    (requires가 없어 plan에서 맨 뒤에 있는 한 항상 마지막에 돈다, 2026-07-28 7단계). 해설이
    계산을 되돌리지 않으므로 공용 수치는 한 번만 계산된다(재계산 금지 §6.2).

    반환: {"markdown", "step_renders", "notes", "context"}
    """
    ctx = ctx or SharedContext()
    instances, step_order = expand_plan(plan, catalog)
    ordered = topo_order(instances)
    step_renders = execute(ordered, ctx)
    narrate(step_order, step_renders, catalog, ctx)
    markdown = assemble(plan, step_order, step_renders, ctx)
    return {
        "markdown": markdown,
        "step_renders": step_renders,
        "notes": ctx.notes(),
        "context": ctx,
    }
