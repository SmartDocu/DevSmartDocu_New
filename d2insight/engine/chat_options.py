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

from d2insight.engine.catalog.module_key import normalize, to_key
from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.catalog.steps import get_step_registry
from d2insight.engine.catalog.scenarios import get_scenario
from d2insight.engine._llm import chat


def module_entry_from_preset(m: dict, modules: dict) -> dict:
    """프리셋의 모듈 참조 → 옵션 JSON의 모듈 항목.

    조립 필드({measure, module_name, sub_name})는 프리셋이 고른 그대로 두고, params는 스펙
    기본값으로 채운다 — 사용자가 JSON을 열었을 때 **실제 적용값**이 보여야 하기 때문이다
    (§ plan_composition과 같은 원칙 — 빈 채로 두지 않는다).

    dimension/dimensions/measure는 params에 넣지 않는다. 조립 필드로 올라갔으므로 여기 두면
    같은 것이 두 자리에 적힌다(2026-09-01 카탈로그 재구조화).
    """
    parts = normalize(m)
    spec = modules[parts["module_name"]]
    params = {
        name: field.get("default")
        for name, field in spec.params.items()
        if name not in ("dimension", "dimensions", "measure")
    }
    params.update({
        k: v for k, v in (m.get("params") or {}).items()
        if k not in ("dimension", "dimensions", "measure")
    })
    entry: dict = {**parts, "params": params}
    tool = m.get("tools", [None])[0] if m.get("tools") else spec.tools.get("default")
    if tool:
        entry["tool"] = tool
    return entry


def default_steps_for_scenario(scenario: str) -> list[dict]:
    """등록된 시나리오의 프리셋을 옵션 JSON의 "steps" 형태로 편다."""
    base = get_scenario(scenario)
    if base is None:
        raise ValueError(f"등록되지 않은 시나리오: '{scenario}'")

    step_registry = get_step_registry()
    modules = get_module_registry()
    steps: list[dict] = []

    for ref in base["steps"]:
        sid = ref["step_id"]
        preset = step_registry[sid]
        modules_out = [module_entry_from_preset(m, modules) for m in preset["default_modules"]]
        steps.append({"step_id": sid, "title": preset["title"], "modules": modules_out})

    return steps


def _catalog_digest(default_steps: list[dict]) -> str:
    """LLM에게 줄, 현재 스텝별 모듈·툴·파라미터 설명 + 추가 가능한 다른 카탈로그 스텝 목록.

    모듈은 조합 키(`amount:ranking@item`)로 보여준다 — 한 스텝에 같은 module_name이 여러
    번 있어도(sub_name만 다른 경우) LLM이 어느 것을 가리키는지 정확히 말할 수 있어야 한다.
    """
    modules = get_module_registry()
    steps = get_step_registry()
    present_ids = {s["step_id"] for s in default_steps}
    lines = ["[현재 포함된 스텝]"]
    for step in default_steps:
        lines.append(f"- step_id \"{step['step_id']}\" (\"{step['title']}\")")
        for m in step["modules"]:
            parts = normalize(m)
            spec = modules[parts["module_name"]]
            tools_avail = spec.tools.get("available")
            tool_txt = f" | 선택 가능 툴: {tools_avail}" if tools_avail else ""
            params_txt = ", ".join(
                f"{k}({field.get('type', 'str')}"
                + (f", 가능한 값: {'/'.join(field['enum'])}" if field.get("enum") else "")
                + ")"
                for k, field in spec.params.items()
                if k not in ("dimension", "dimensions", "measure")
            ) or "(없음)"
            fields = []
            if spec.sub_name_pool:
                fields.append("sub_name" + ("(필수)" if spec.sub_name_required else ""))
            if spec.accepts_measure:
                fields.append("measure")
            field_txt = f" | 바꿀 수 있는 조립 필드: {', '.join(fields)}" if fields else ""
            lines.append(
                f"    module \"{to_key(parts)}\" — 지정 가능한 파라미터: "
                f"{params_txt}{tool_txt}{field_txt}"
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
- {"op": "set_param", "step_id": "...", "module": "...", "params": {"top_n": 5}}
    "상위 N개", "N개까지" 같은 개수·조건 지정. "가능한 값"이 명시된 파라미터는 반드시 그
    목록 중 하나를 그대로 씁니다 — 비슷한 뜻이라도 다른 문자열을 지어내지 마세요
    (예: compare_type은 "MoM"/"QoQ"/"YoY"만 유효, "month_over_month" 같은 값은 안 됩니다).
- {"op": "set_tool", "step_id": "...", "module": "...", "tool": "..."}
    분석 방법(툴) 변경 요청("IQR로 바꿔줘", "샤플리로 해줘"). 그 모듈의 "선택 가능 툴" 중에서만.

규칙
1. 문장에 명시적으로(또는 아주 명확하게 함의되어) 언급된 것만 담습니다. 언급되지 않은
   스텝·모듈·파라미터는 절대 건드리지 마세요.
2. "module"은 위 목록에 적힌 조합 키를 **그대로** 씁니다(예: "actual_aggregate@region").
   한 스텝에 같은 이름의 모듈이 sub_name만 다르게 여러 개 있을 수 있으니, 이름만 쓰면
   어느 것인지 알 수 없습니다.
3. sub_name/measure 값은 역할 이름(item/party/item_group/region/amount/quantity/discount 중
   하나)으로 씁니다.
4. move·add의 위치를 알 수 없으면(그냥 "추가해줘"만 있으면) 위치 지정 없이(맨 뒤) 담습니다.
5. 여러 스텝의 순서를 한 번에 재배치하라는 요청이면 move를 여러 개 쓰지 말고 reorder 하나로 담습니다.
6. 아무 것도 언급되지 않았으면 빈 배열 []을 그대로 출력합니다.

출력 형식(다른 설명 없이 JSON 배열만): [ {"op": "...", ...}, ... ]
"""


# ── 스텝 카드 팝업 (2026-09-01) ───────────────────────────────────────────────
# 아래 둘은 스텝 **하나**를 문맥으로 삼는다. 위의 extract_operations가 보고서 전체를 놓고
# 스텝을 넣고 빼는 것이라면, 이쪽은 그 스텝 안의 모듈·툴·값을 바꾼다.

def _step_digest(step: dict, schema=None, *, include_candidates: bool = True) -> str:
    """스텝 하나를 LLM에게 보여줄 텍스트로 편다. 모듈마다 조합 키·기능·현재 값.

    include_candidates=False면 add_module 후보 목록을 뺀다 — 설명에는 쓰이지 않는다.
    """
    modules = get_module_registry()
    lines = [f'스텝 "{step.get("title")}" (step_id: {step.get("step_id")})', "", "[포함된 모듈]"]
    for m in step.get("modules", []):
        parts = normalize(m)
        spec = modules.get(parts["module_name"])
        lines.append(f'- module "{to_key(parts)}"')
        if spec is not None:
            lines.append(f"    기능: {spec.purpose}")
            if spec.sub_name_pool:
                req = " (필수)" if spec.sub_name_required else ""
                lines.append(f'    분석 대상(sub_name){req}: {parts["sub_name"] or "지정 안 함(자동)"}')
            if spec.accepts_measure:
                lines.append(f'    기준 값(measure): {parts["measure"] or "지정 안 함(기본)"}')
            # 툴은 **고를 수 있을 때만** 보여준다. 하나뿐이면 사용자가 바꿀 수 없어 설명에
            # 넣어봐야 군더더기다.
            # 그리고 반드시 tool_id와 함께 그 뜻(TOOL_REGISTRY의 purpose)을 준다 — id만 주면
            # LLM이 이름을 글자 그대로 옮긴다("bridge_decompose" → "다리 분해", 2026-09-01).
            avail = spec.tools.get("available") or []
            if len(avail) > 1:
                from d2insight.engine.catalog.tools import get_tool_registry
                treg = get_tool_registry()
                cur = m.get("tool") or spec.tools.get("default")
                lines.append(f'    방법(tool): {cur} — {treg.get(cur, {}).get("purpose", "")}')
                others = [f'{t}({treg.get(t, {}).get("purpose", "")})' for t in avail if t != cur]
                if others:
                    lines.append(f'    바꿀 수 있는 방법: {"; ".join(others)}')
        shown = {
            k: v for k, v in (m.get("params") or {}).items()
            if k not in ("dimension", "dimensions", "measure", "query_sql")
            and not k.startswith("_") and v is not None
        }
        if shown:
            lines.append(f"    값: {shown}")
    if schema is not None:
        lines.append("")
        lines.append(f"[이 데이터에서 쓸 수 있는 분석 대상] {', '.join(schema.dimensions)}")
        lines.append(f"[이 데이터에서 쓸 수 있는 기준 값] {', '.join(schema.measures)}")
    if include_candidates:
        lines.append("")
        lines.append("[이 스텝에 넣을 수 있는 다른 모듈 — add_module 후보]")
        present = {normalize(m)["module_name"] for m in step.get("modules", [])}
        try:
            from d2insight.engine.catalog.matrix import modules_for_step
            candidates = [n for n in modules_for_step(step.get("step_id")) if n not in present]
        except Exception:
            candidates = [n for n in modules if n not in present]
        for name in candidates:
            lines.append(f'- "{name}": {modules[name].purpose}')
    return "\n".join(lines)


_DESCRIBE_SYSTEM = """당신은 데이터 분석 보고서의 설정을 일반 사용자에게 설명하는 사람입니다.
사용자는 JSON이나 기술 용어를 모릅니다.

주어진 스텝의 모듈 하나하나를 아래 JSON 배열로 설명하세요.

[
  {"module": "조합 키를 그대로", "title": "이 분석을 한 줄로 부르는 이름",
   "what": "무엇을 하는지 한 문장", "values": ["주어진 값을 사람 말로 푼 것", ...]}
]

규칙
1. "module"은 주어진 조합 키를 **글자 그대로** 옮깁니다. 바꾸거나 지어내지 마세요.
2. "title"은 8자 안팎의 짧은 이름입니다(예: "제품별 순위", "고객 구성비").
3. "what"은 한 문장입니다. 모듈의 기능 설명을 사용자 말로 다시 씁니다.
4. "values"는 **주어진 값들만** 사람이 읽는 문장으로 바꾼 짧은 항목들입니다.
   예: sub_name=item → "제품별로 봅니다" / top_n=10 → "상위 10개만 봅니다"
       measure=quantity → "판매 수량 기준입니다"
   값이 "지정 안 함(자동)"이면 "시스템이 알아서 고릅니다"처럼 씁니다.
5. **적혀 있지 않은 값을 지어내지 마세요.** 주어진 줄에 없는 내용은 넣지 않습니다.
   같은 모듈은 몇 번을 설명하든 같은 항목이 나와야 합니다.
6. **내부 이름을 글자 그대로 옮기지 마세요.** tool 이름 옆에는 그 뜻이 "—" 뒤에 적혀
   있습니다. 그 뜻을 풀어 쓰고, 영어 이름을 직역하지 마세요.
   (예: "bridge_decompose — 수량/ASP/할인/신규/이탈 효과 분해"가 주어지면
    "다리 분해"가 아니라 "수량·단가·할인 효과로 나눠 봅니다"라고 씁니다.)
7. 내부 용어(module_id, params, dimension 등)를 그대로 노출하지 마세요.
8. JSON 배열만 출력합니다. 다른 텍스트를 붙이지 마세요."""


def describe_step(step: dict, provider: str | None = None) -> list[dict]:
    """스텝 하나 → 사람이 읽는 모듈 설명 목록. 실패하면 카탈로그 값으로 만든 기본 설명.

    사전(용어 매핑 표)을 두지 않고 LLM에 맡긴다 — 역할·파라미터·툴을 모두 담으려면 사전이
    너무 넓어지고, 카탈로그가 늘 때마다 같이 늘려야 한다(2026-09-01 결정).
    """
    modules = get_module_registry()
    try:
        raw = chat(
            [{"role": "user", "content": _step_digest(step, include_candidates=False)}],
            grade="fast", system=_DESCRIBE_SYSTEM, max_tokens=1200,
            label="스텝 설명", stepnm="step_describe", steptitle="스텝 설명",
            provider=provider,
        )
        m = raw.strip()
        if m.startswith("```"):
            m = m.strip("`").split("\n", 1)[-1]
        out = json.loads(m)
        if isinstance(out, list) and out:
            return out
    except Exception as e:
        print(f"[chat_options] 스텝 설명 생성 실패, 카탈로그 값으로 대체: {e}")

    # 폴백 — LLM 없이도 팝업이 비어 보이지 않게 한다.
    fallback = []
    for mod in step.get("modules", []):
        parts = normalize(mod)
        spec = modules.get(parts["module_name"])
        values = []
        if parts["sub_name"]:
            values.append(f"{parts['sub_name']}별로 봅니다")
        if parts["measure"]:
            values.append(f"{parts['measure']} 기준입니다")
        fallback.append({
            "module": to_key(parts),
            "title": parts["module_name"],
            "what": spec.purpose if spec else "",
            "values": values,
        })
    return fallback


_EDIT_SYSTEM = """당신은 보고서의 한 스텝을 고쳐달라는 요청을, 아래 편집 연산 목록으로
번역하는 추출기입니다. 반드시 JSON 배열만 출력하세요.

지원하는 연산(다른 연산을 지어내지 마세요):
- {"op": "set_sub_name", "module": "...", "sub_name": "..."}
    분석 대상 변경. "제품별 말고 브랜드별로", "고객 기준으로 봐줘".
    sub_name을 비우려면(자동 선택) null을 넣습니다.
- {"op": "set_measure", "module": "...", "measure": "..."}
    기준 값 변경. "수량 기준으로", "금액 말고 판매량으로".
- {"op": "set_param", "module": "...", "params": {"top_n": 5}}
    개수·조건 변경. "5개만", "상위 20개까지".
- {"op": "set_tool", "module": "...", "tool": "..."}
    분석 방법 변경. "IQR로 바꿔줘", "샤플리로 해줘". "선택 가능" 목록 중에서만.
- {"op": "add_module", "module_name": "...", "sub_name": "...", "measure": "..."}
    분석 추가. "추이도 같이 보여줘". "[이 스텝에 넣을 수 있는 다른 모듈]" 목록에서만 고릅니다.
    module_name에는 그 목록에 적힌 **이름만** 씁니다(조합 키를 넣지 마세요). 분석 대상과
    기준 값은 sub_name/measure에 따로 넣습니다.
- {"op": "remove_module", "module": "..."}
    분석 제외. "구성비는 빼줘". 모듈이 하나도 안 남으면 이 스텝이 통째로 사라집니다.
- {"op": "remove"}
    이 스텝 전체를 뺍니다. "이 스텝 통째로 빼줘", "이 스텝의 분석을 전부 빼줘".
- {"op": "set_title", "title": "..."}
    이 스텝의 이름을 바꿉니다. "스텝명도 브랜드로 바꿔줘".

규칙
1. "module"은 위 목록에 적힌 조합 키를 **글자 그대로** 씁니다(예: "actual_aggregate@region").
   이름만 쓰면 같은 이름의 다른 모듈과 구분되지 않습니다.
2. 요청에 명시된 것만 담습니다. 언급되지 않은 모듈·값은 절대 건드리지 마세요.
3. sub_name/measure 값은 "[이 데이터에서 쓸 수 있는 …]" 목록에 있는 이름을 씁니다.
   목록이 주어지지 않았으면 역할 이름(item/party/item_group/region/amount/quantity)을 씁니다.
4. **사용자가 말한 대상이 그 목록에 없으면 비슷한 것으로 바꾸지 마세요.** 뜻이 통할 것
   같아도 다른 이름을 대신 넣지 말고, 아무 연산도 만들지 말고 빈 배열 []을 출력합니다
   (예: "쇼핑몰"이 목록에 없는데 region으로 바꿔 넣으면 안 됩니다).
5. 분석 대상이나 기준 값을 바꾸는 것은 set_param이 아니라 set_sub_name/set_measure입니다.
6. 요청이 이 스텝에서 할 수 없는 일이거나, 고쳐달라는 지시가 아니라 질문이면 빈 배열 []을
   출력합니다("뭘 더 넣을 수 있나요?" 같은 물음에 억지로 연산을 만들지 마세요).

출력 형식(다른 설명 없이 JSON 배열만): [ {"op": "...", ...}, ... ]"""


def extract_module_operations(
    instruction: str, step: dict, schema=None, provider: str | None = None,
) -> list[dict]:
    """스텝 하나에 대한 자연어 수정 지시 → 편집 연산 목록.

    step_id는 여기서 넣어 준다 — LLM이 스텝을 옮겨 적다 틀릴 이유가 없다.
    실패하면 빈 목록(호출부가 "고칠 내용을 못 알아들었다"고 알린다).
    """
    prompt = f"{_step_digest(step, schema)}\n\n[사용자 요청]\n{instruction}"
    try:
        raw = chat(
            [{"role": "user", "content": prompt}],
            grade="fast", system=_EDIT_SYSTEM, max_tokens=800,
            label="스텝 편집 연산 추출", stepnm="step_edit_ops", steptitle="스텝 편집",
            provider=provider,
        )
        m = raw.strip()
        if m.startswith("```"):
            m = m.strip("`").split("\n", 1)[-1]
        operations = json.loads(m)
        if not isinstance(operations, list):
            raise ValueError(f"연산 목록이 배열이 아닙니다: {type(operations).__name__}")
    except Exception as e:
        print(f"[chat_options] 스텝 편집 연산 추출 실패: {e}")
        return []
    return [dict(op, step_id=step.get("step_id")) for op in operations if isinstance(op, dict)]


_SUGGEST_SYSTEM = """당신은 데이터 분석 보고서 화면에서 사용자를 돕는 사람입니다.
사용자는 기술 용어를 모릅니다. "모듈", "툴", "파라미터", "스텝", "sub_name" 같은 말을 쓰지 마세요.

주어진 것은 지금 열려 있는 분석 묶음 하나의 구성과, 사용자가 적은 문장입니다. 그 문장은 고칠
내용을 알아듣지 못한 것이거나, 무엇을 더 할 수 있는지 묻는 질문입니다.

2~4문장으로 답하세요.
1. 사용자가 콕 집어 요청한 것이 "[이 스텝에 넣을 수 있는 다른 모듈]" 목록에 없으면, 여기서는
   할 수 없다고 한 줄로 알립니다.
2. 추천은 **"[이 스텝에 넣을 수 있는 다른 모듈]" 목록 안에서만** 3~5개 고릅니다. 사람이 쓰는
   말로 바꿔 부릅니다.
3. **"[포함된 모듈]"에 이미 있는 것은 절대 추천하지 마세요** — 이미 들어 있는 분석입니다.
4. 지금 있는 분석 중 "바꿀 수 있는 방법"이 적힌 것이 있으면 한 줄로 덧붙입니다.
5. 어떻게 말하면 되는지 예를 하나 듭니다(예: "추이도 같이 보여주세요").

목록에 없는 것을 지어내지 마세요. 짧게 씁니다."""


def suggest_for_step(step: dict, instruction: str, schema=None, provider: str | None = None) -> str:
    """고칠 내용을 못 찾았을 때 — 넣을 수 있는 분석·바꿀 수 있는 방법을 사람 말로 추천한다."""
    prompt = f"{_step_digest(step, schema)}\n\n[사용자가 적은 문장]\n{instruction}"
    try:
        text = chat(
            [{"role": "user", "content": prompt}],
            grade="fast", system=_SUGGEST_SYSTEM, max_tokens=600,
            label="스텝 추천", stepnm="step_suggest", steptitle="스텝 추천",
            provider=provider,
        ).strip()
        if text:
            return text
    except Exception as e:
        print(f"[chat_options] 스텝 추천 생성 실패: {e}")
    return "고칠 내용을 알아듣지 못했습니다. 다르게 말씀해 주세요."


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
