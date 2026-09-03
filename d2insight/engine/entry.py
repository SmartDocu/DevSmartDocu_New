"""엔진 진입점 (Step 0 플랫폼 접점).

채팅 라우터(app/chat/pipeline_runner.run_tool의 report 분기)가 부르는 단일 함수.
인텐트 파서가 뽑은 message/target_month/compare_type를 받아
계획기(scenario_plan 또는 compose_scenario) → 실행 엔진(run_plan)을 돌리고 결과 마크다운·파일명·notes를 돌려준다.

**출력 계약 변환과 Supabase 저장은 호출부가 기존 흐름 그대로 처리한다.** 이 함수는
md_text/md_filename/notes 까지만 만든다 — 저장 로직을 여기서 중복하지 않는다(플랫폼 층은
기존 코드를 따른다, 지시서 §0.6).

기준월·비교유형은 여기서 계산하지 않는다(인텐트 파서의 몫, LLM 사용 경계 §7.1.2). 이 함수는
ctx.meta에 실어 모듈이 읽게 할 뿐이다.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime

import d2insight.config as config
from d2insight.engine.catalog import EngineCatalog
from d2insight.engine.chat_options import default_steps_for_scenario, extract_operations
from d2insight.engine.context import SharedContext
from d2insight.engine.datasource import DEFAULT_SOURCE_ID
from d2insight.engine.operations import apply_operations, is_locked_step
from d2insight.engine.options import global_to_meta, options_to_plan
from d2insight.engine.planner import compose_scenario, data_digest, finalize, scenario_plan
from d2insight.engine.runner import execute, expand_plan, plan_composition, run_plan, topo_order
from d2insight.engine.schema import Schema
from d2insight.engine.types import Render
from d2insight.engine._llm import chat

# match_scenario()가 "어느 시나리오와도 매칭 확인을 아직 안 했음"을 표시하는 내부 전용 값.
# None은 "확인했고 없다"는 뜻이라 구분해야 한다 — 안 그러면 run_engine_report가 매번 다시
# match_scenario를 불러 같은 메시지에 LLM을 두 번 쓰게 된다(호출부가 이미 판단해 넘겨준 경우 제외).
_UNRESOLVED = object()

# inline_options도 같은 이유로 "아직 안 봤음"과 "보았고 없음(None)"을 구분해야 한다.
_UNRESOLVED_INLINE = object()


def _upload_schema(upload_session_id: str | None, upload_dataset_key: str | None) -> Schema | None:
    """업로드 데이터셋에 저장된 역할 메타(engine_meta)로 Schema를 만든다.

    upload_dataset_key는 "key1+key2" 형태로 여러 파일을 담을 수 있다(DB의 source_id와 같은
    형식). 여러 개면 컬럼 메타를 합쳐 하나의 Schema로 만든다 — 계획 단계가 어느 파일에 있든
    쓸 수 있는 축·값을 모두 보게 하기 위해서다. 실제로 어느 파일을 읽을지는 스텝이 정한다.

    없으면(추론 실패·미생성) None — 호출부가 데이터소스 정의 파일 경로로 폴백하지 않고
    그대로 진행하게 둔다. finalize()가 이후 스키마 없이 실행되면 명시적으로 실패한다(§11 Step 2).
    """
    if not upload_session_id or not upload_dataset_key:
        return None
    import pandas as pd
    from d2insight.report.excel_registry import get_excel_server

    datasets = get_excel_server().session_datasets.get(upload_session_id) or {}
    metas = [
        (datasets.get(key) or {}).get("engine_meta", {}).get("meta_columns")
        for key in upload_dataset_key.split("+")
    ]
    metas = [m for m in metas if m is not None and len(m)]
    if not metas:
        return None
    if len(metas) == 1:
        return Schema(metas[0])
    return Schema(pd.concat(metas, ignore_index=True).drop_duplicates(subset=["Physical_Name"]))


_SCENARIO_MATCH_SYSTEM = """당신은 보고서 요청 문장을 읽고, 아래 등록된 시나리오 중 어느 것을
요청하는 것인지 의미로 판단한다. 표현이 등록된 이름과 글자 그대로 같지 않아도(예: "판매증감분석"은
"매출 증감 원인 분석"을 뜻함) 뜻이 같으면 매칭한 것으로 본다.

요청이 등록된 시나리오 중 하나에 해당하면 그 이름을 정확히 그대로(다른 글자·설명 추가 없이) 한 줄로
출력하라. 어느 것에도 해당하지 않으면 "없음"이라고만 출력하라."""


def match_scenario(message: str, provider: str | None = None) -> str | None:
    """메시지가 등록된 시나리오(기본세트) 중 하나를 요청하는 것인지 LLM으로 판단한다.

    문자열 부분일치가 아니라 의미 판단이다 — intent_parser의 report_type 분류와 같은 방식.
    어느 것도 아니면 None → 호출부는 compose_scenario(LLM이 시나리오를 조합)로 진행한다.
    """
    if not message:
        return None
    from d2insight.engine.catalog.scenarios import SCENARIO_REGISTRY
    names = list(SCENARIO_REGISTRY)
    prompt = f"[등록된 시나리오 목록]\n{json.dumps(names, ensure_ascii=False)}\n\n[요청 문장]\n{message}"
    try:
        raw = chat(
            [{"role": "user", "content": prompt}],
            grade="fast", system=_SCENARIO_MATCH_SYSTEM, max_tokens=30,
            label="시나리오 매칭", stepnm="scenario_match", steptitle="시나리오 판단",
            provider=provider,
        )
        name = raw.strip().strip('"')
        return name if name in names else None
    except Exception as e:
        print(f"[match_scenario] error: {e}")
        return None


def extract_inline_options(message: str) -> dict | None:
    """채팅 메시지에 붙여넣은 옵션 JSON(steps + global)을 찾아 파싱한다. 있으면 LLM 추출 없이
    그대로 options_to_plan에 쓴다.

    받는 형태: steps 배열 그대로, 또는 {"steps":[...], "global":{...}}로 감싼 객체.
    JSON이 없거나 형태가 다르면 None.

    반환: {"steps", "global", "scenario", "analytic_uid", "origin_report"}. scenario는 정기
    보고서 이름 표시용, analytic_uid는 정기 보고서 출처 기록용, origin_report는
    {"answer","report_path","fileurl"}로 정기 보고서 등록 시 첫 QA로 남긴다.
    """
    if not message or "{" not in message:
        return None

    # 객체 형태({"steps":[...], "global":{...}})를 배열 형태보다 먼저 시도한다. 반대 순서면
    # "[" 탐색이 steps 배열 안쪽만 잘라내 바깥 객체(및 global 절)를 통째로 놓친다.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = message.find(opener)
        end = message.rfind(closer)
        if start < 0 or end <= start:
            continue
        try:
            parsed = json.loads(message[start:end + 1])
        except Exception:
            continue
        steps = parsed.get("steps") if isinstance(parsed, dict) else parsed
        if isinstance(steps, list) and steps and all(
            isinstance(s, dict) and "modules" in s for s in steps
        ):
            global_section = parsed.get("global") if isinstance(parsed, dict) else None
            scenario = parsed.get("scenario") if isinstance(parsed, dict) else None
            analytic_uid = parsed.get("analytic_uid") if isinstance(parsed, dict) else None
            origin_report = parsed.get("origin_report") if isinstance(parsed, dict) else None
            return {
                "steps": steps, "global": global_section or {}, "scenario": scenario,
                "analytic_uid": analytic_uid,
                "origin_report": origin_report if isinstance(origin_report, dict) else None,
            }
    return None


def _safe_type(report_type: str) -> str:
    """옛 보고서와 같은 파일명 규칙을 쓰려고 folder_en(영문 유형)을 재사용한다."""
    try:
        from d2insight.report.registry import get_config
        folder_en = get_config(report_type).get("folder_en")
        if folder_en:
            return folder_en
    except Exception:
        pass
    return (report_type or "report").replace("/", "_").replace("\\", "_")


def resolve_report_plan(
    message: str,
    target_month: str,
    compare_type: str | None = None,
    months_back: int | None = None,
    grain: str | None = None,
    report_type: str = "보고서",
    source_id: str | None = None,
    provider: str | None = None,
    upload_session_id: str | None = None,
    upload_dataset_key: str | None = None,
    matched_scenario=_UNRESOLVED,
    inline_options=_UNRESOLVED_INLINE,
) -> dict:
    """요청 하나를 실행 가능한 plan으로 해석한다(**실행은 하지 않는다**).

    확인 카드(preview_report_plan)와 실제 실행(run_engine_report)이 공유하는 단 하나의
    해석 로직이다 — 둘이 서로 다른 결과를 낼 수 없도록.

    반환: {"plan", "plan_notes", "applied_steps", "scenario",
           "target_month", "compare_type", "months_back", "grain", "source_id"}
      뒤 5개는 인자로 받은 값 위에 global 절(있으면)을 반영한 **최종 값**이다.
    """
    src_id = source_id or DEFAULT_SOURCE_ID
    upload_schema = _upload_schema(upload_session_id, upload_dataset_key)

    # 시나리오가 매칭되면 프리셋 위에 요청한 옵션만 얹고, 못 찾으면 LLM이 시나리오를 조합한다.
    # applied_steps는 사용자에게 그대로 보여줄 JSON — 자동 삽입된 모듈은 포함하지 않는다.
    applied_steps: list[dict] | None = None

    # 메시지에 옵션 JSON을 직접 붙여넣었으면 그것이 곧 사용자의 지정이다 — LLM 추출을 건너뛰고
    # 그대로 쓴다(대화·JSON 두 경로가 같은 형태로 수렴, 2026-07-22).
    if inline_options is _UNRESOLVED_INLINE:
        inline_options = extract_inline_options(message)

    scenario = match_scenario(message, provider=provider) if matched_scenario is _UNRESOLVED else matched_scenario

    if inline_options:
        inline_steps = inline_options["steps"]
        inline_global = inline_options.get("global") or {}

        # global 절이 명시한 값은 자연어보다 우선한다. 명시 안 된 키는 None이라 기존 값을
        # 그대로 둔다.
        meta_override = global_to_meta({"global": inline_global})
        target_month = meta_override.get("target_month") or target_month
        compare_type = meta_override.get("compare_type") or compare_type
        src_id = meta_override.get("source_id") or src_id
        months_back = meta_override.get("months_back") or months_back
        grain = meta_override.get("grain") or grain

        schema_for_options, _ = data_digest(src_id, schema=upload_schema)
        plan, plan_notes = options_to_plan(
            {"scenario": scenario or report_type, "steps": inline_steps}, schema_for_options,
            global_measure=meta_override.get("measure"),
        )
        applied_steps = inline_steps
        print(f"[engine] 메시지에 포함된 옵션 JSON 사용 (스텝 {len(inline_steps)}개, global={inline_global})")
    elif scenario:
        try:
            schema_for_options, _ = data_digest(src_id, schema=upload_schema)
            default_steps = default_steps_for_scenario(scenario)
            operations = extract_operations(message, scenario, default_steps, provider=provider)
            merged_steps, op_notes = apply_operations(default_steps, operations)
            options = {"scenario": scenario, "steps": merged_steps}
            plan, plan_notes = options_to_plan(options, schema_for_options)
            plan_notes = op_notes + plan_notes
            # 미리보기 = 실제 실행 구성(다른 두 경로와 동일 원칙) — 검증 끝난 plan["steps"] 사용.
            applied_steps = plan.get("steps")
            print(f"[engine] 시나리오 프리셋 + 편집 연산 사용: '{scenario}' (operations={operations})")
        except Exception as e:
            # 실패 사유를 plan_notes에도 남겨 패널에서 확인할 수 있게 한다.
            print(f"[engine] 편집 연산 추출/적용 실패, 프리셋 기본값으로 대체: {e}")
            plan, plan_notes = scenario_plan(scenario, source_id=src_id, schema=upload_schema)
            plan_notes = [
                f"요청하신 옵션을 반영하지 못해 기본 구성으로 작성했습니다 "
                f"({type(e).__name__}: {e})."
            ] + plan_notes
            # 미리보기가 실제 실행과 같은 구성이어야 하므로, 검증까지 마친 plan["steps"]를
            # applied_steps에도 반영한다.
            applied_steps = plan.get("steps")
    else:
        plan, plan_notes = compose_scenario(message, source_id=src_id, provider=provider,
                                            schema=upload_schema)
        # 미리보기·이대로 작성이 실제 실행과 같은 구성을 보게 하려면, 검증까지 마친
        # plan["steps"]를 applied_steps에도 반영해야 한다(시나리오 경로와 동일한 원칙).
        applied_steps = plan.get("steps")

    if applied_steps:
        # period_dataset 파라미터에 실제 값을 채운다 — applied_steps가 실행 로그로 남으므로
        # 안 채우면 어느 기간·비교방식으로 돌았는지 로그에 안 남는다.
        resolved_compare_type = compare_type or config.COMPARE_TYPE
        resolved_grain = grain or "month"
        for step in applied_steps:
            for m in step.get("modules", []):
                if m.get("module_id") == "period_dataset":
                    m["params"] = {
                        **m.get("params", {}),
                        "compare_type": resolved_compare_type,
                        "months_back": months_back or m.get("params", {}).get("months_back") or 3,
                        "grain": resolved_grain,
                    }

        # 뿌리 스텝(자료확인·총평)에 locked 플래그를 붙인다 — 오른편 패널의 이동·삭제 불가
        # 표시에 쓴다. 잠금 판정 로직은 operations.py 하나뿐이다.
        applied_steps = [dict(s, locked=is_locked_step(s)) for s in applied_steps]

    return {
        "plan": plan, "plan_notes": plan_notes, "applied_steps": applied_steps, "scenario": scenario,
        "target_month": target_month, "compare_type": compare_type, "months_back": months_back,
        "grain": grain, "source_id": src_id,
    }


def preview_report_plan(
    message: str,
    target_month: str,
    compare_type: str | None = None,
    months_back: int | None = None,
    grain: str | None = None,
    report_type: str = "보고서",
    source_id: str | None = None,
    provider: str | None = None,
    upload_session_id: str | None = None,
    upload_dataset_key: str | None = None,
    matched_scenario=_UNRESOLVED,
    inline_options=_UNRESOLVED_INLINE,
) -> dict:
    """확인 카드(오른편 패널)용 — 계획만 만들고 **실행하지 않는다**.

    resolve_report_plan과 같은 해석 로직을 써서, "이대로 작성"을 누르면 실제 실행과
    **똑같은 구성**이 나온다는 것을 보장한다. 반환의 "applied_steps"/"global"은 그대로
    다시 붙여넣을 수 있는 옵션 JSON 형태다. upload_session_id/upload_dataset_key를 주면
    업로드 데이터셋 기준으로 미리보기를 만든다(run_engine_report와 동일한 스키마 사용).
    """
    resolved = resolve_report_plan(
        message, target_month, compare_type, months_back, grain, report_type, source_id, provider,
        upload_session_id, upload_dataset_key,
        matched_scenario=matched_scenario, inline_options=inline_options,
    )
    return {
        "report_type": report_type,
        "scenario": resolved["scenario"],
        "applied_steps": resolved["applied_steps"],
        "plan_notes": resolved["plan_notes"],
        "global": {
            "target_period": resolved["target_month"],
            "compare_type": resolved["compare_type"] or config.COMPARE_TYPE,
            "months_back": resolved["months_back"],
            "grain": resolved["grain"] or "month",
            "datasource": resolved["source_id"],
        },
    }


def run_engine_report(
    message: str,
    target_month: str,
    compare_type: str | None = None,
    months_back: int | None = None,
    grain: str | None = None,
    report_type: str = "보고서",
    source_id: str | None = None,
    provider: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    upload_session_id: str | None = None,
    upload_dataset_key: str | None = None,
    matched_scenario=_UNRESOLVED,
    inline_options=_UNRESOLVED_INLINE,
) -> dict:
    """채팅 요청 하나를 모듈화 엔진으로 실행해 보고서 마크다운을 만든다.

    matched_scenario: 호출부가 미리 match_scenario를 돌렸다면 그 결과를 그대로 넘겨 LLM을
      두 번 안 부르게 한다. 기본값(_UNRESOLVED)이면 여기서 직접 판단한다.

    반환: {"md_text", "md_filename", "notes", "plan_notes", "applied_steps", "scenario"}
      - notes: 실행 중 실패·생략된 분석
      - plan_notes: 계획기가 요청을 카탈로그에 맞추며 보정한 내역
      - scenario: 매칭된 시나리오 이름(없으면 None)
    """
    resolved = resolve_report_plan(
        message, target_month, compare_type, months_back, grain, report_type, source_id, provider,
        upload_session_id, upload_dataset_key, matched_scenario, inline_options,
    )
    # 비활성 스텝(enabled=False)은 실행 대상에서 뺀다 — applied_steps에는 그대로 남겨 표시한다.
    plan = dict(resolved["plan"], steps=[s for s in resolved["plan"]["steps"] if s.get("enabled", True)])
    plan_notes = resolved["plan_notes"]
    applied_steps = resolved["applied_steps"]
    target_month = resolved["target_month"]
    compare_type = resolved["compare_type"]
    months_back = resolved["months_back"]
    grain = resolved["grain"]
    src_id = resolved["source_id"]

    # 실행 컨텍스트 — 모듈들이 ctx.meta에서 기준월·비교유형·provider를 읽는다.
    meta: dict = {
        "target_month": target_month,
        "compare_type": compare_type or config.COMPARE_TYPE,
        "source_id": src_id,
        "provider": provider,
        "grain": grain or "month",           # month(기본)/quarter/year/week
    }
    if months_back:
        meta["months_back"] = months_back
    if upload_session_id and upload_dataset_key:
        # period_dataset이 이걸 보고 DB 대신 업로드 세션의 DataFrame으로 뿌리를 만든다.
        meta["upload_session_id"] = upload_session_id
        meta["upload_dataset_key"] = upload_dataset_key
    ctx = SharedContext(session_id=session_id or "", meta=meta)

    catalog = EngineCatalog()

    # 어떤 스텝-모듈-툴 조합으로 보고서를 만드는지 백엔드 터미널에 JSON으로 남긴다(개발자 확인용
    # 로그일 뿐, 사용자에게 보여주는 것과는 별개다 — 그건 위의 applied_steps가 담당한다).
    try:
        print(f"[engine] 보고서 조합 (target_month={target_month}, compare_type={meta['compare_type']}):")
        # print(json.dumps(plan_composition(plan, catalog), ensure_ascii=False, indent=2, default=str))     # jeff 20260825
    except Exception as _pe:                    # 조합 출력 실패가 보고서 생성을 막지 않게 한다
        print(f"[engine] 조합 출력 생략: {_pe}")

    out = run_plan(plan, catalog, ctx)

    # 실행 흔적(생성 SQL·렌더 형식)은 applied_steps에 덧붙이지 않는다 — 작성 후 JSON이 작성 전
    # JSON과 같아야 그대로 복사해 붙여넣어 같은 보고서를 다시 만들 수 있다.
    if applied_steps:
        _sync_failure_status(applied_steps, out["notes"])

    # 파일명 — 옛 보고서와 같은 규칙(안전유형_기준월_타임스탬프.md)이라 저장 경로가 일관된다.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_filename = f"{_safe_type(report_type)}_{target_month}_{ts}.md"

    return {
        "md_text": out["markdown"],
        "md_filename": md_filename,
        "notes": out["notes"],
        "plan_notes": plan_notes,
        "applied_steps": applied_steps,
        "execution_cache": collect_execution_cache(out["step_renders"]),
        "scenario": resolved["scenario"],
    }


def collect_execution_cache(step_renders: dict) -> dict:
    """실행 중 만들어진 SQL과 표·차트 형식을 스텝별로 모은다.

    applied_steps에는 넣지 않는다 — 사용자가 보는 JSON은 작성 전 지시 그대로여야 한다.
    정기 보고서로 등록할 때만 merge_execution_cache()로 스냅샷에 합쳐, 회차마다 같은 SQL·형식으로
    돌게 한다.
    """
    cache: dict = {}
    for step_label, entries in step_renders.items():
        query_sql = None
        renders: dict = {}
        seen: dict[str, int] = {}
        for inst, render in entries:
            n = seen.get(inst.module_id, 0) + 1
            seen[inst.module_id] = n
            key = inst.module_id if n == 1 else f"{inst.module_id}#{n}"
            if inst.module_id == "period_dataset" and inst.params.get("query_sql"):
                query_sql = inst.params["query_sql"]
            if render.llm_spec:
                renders[key] = render.llm_spec
        if query_sql or renders:
            cache[step_label] = {"query_sql": query_sql, "renders": renders}
    return cache


def merge_execution_cache(steps: list[dict] | None, cache: dict | None) -> list[dict]:
    """지시 JSON + 실행 캐시 → 정기 보고서 스냅샷. 원본 steps는 건드리지 않는다."""
    if not steps:
        return []
    if not cache:
        return copy.deepcopy(steps)

    merged = copy.deepcopy(steps)
    for step in merged:
        entry = cache.get(step.get("title"))
        if not entry:
            continue
        seen: dict[str, int] = {}
        for m in step.get("modules", []):
            mid = m.get("module_id")
            n = seen.get(mid, 0) + 1
            seen[mid] = n
            key = mid if n == 1 else f"{mid}#{n}"
            params = dict(m.get("params") or {})
            if mid == "period_dataset" and entry.get("query_sql"):
                params["query_sql"] = entry["query_sql"]
            spec = (entry.get("renders") or {}).get(key)
            if spec:
                params["_llm_render_cache"] = spec
            m["params"] = params
    return merged


def _sync_failure_status(applied_steps: list[dict], notes: list[dict]) -> None:
    """실행 중 실패·생략된 모듈(ctx.notes())을 applied_steps에 되돌려 쓴다.

    보고서 본문에는 실패를 나열하지 않는다(완성된 문서를 지저분하게 만들지 않기 위해 —
    결론이 문장으로 언급할 수는 있지만 보장되지 않는다). 대신 이 JSON에 실패 사유를 남겨,
    사용자가 JSON을 열어보면 어느 스텝의 어느 모듈이 왜 빠졌는지 확인할 수 있게 한다.
    """
    by_step: dict[str, list[dict]] = {}
    for note in notes:
        step_label, _, module_id = note["ref"].partition(" / ")
        by_step.setdefault(step_label, []).append(
            {"module_id": module_id, "kind": note["kind"], "reason": note["reason"]}
        )

    for step in applied_steps:
        failures = by_step.get(step.get("title"))
        if failures:
            step["execution_notes"] = failures


def skipped_steps_note(notes: list[dict]) -> str:
    """실행 중 빠진 스텝을 사용자에게 알릴 한 줄로 만든다. 빠진 것이 없으면 빈 문자열.

    보고서는 끝까지 만들되, 무엇이 빠졌는지는 답변에서 알려준다 — 문서만 보면 그 분석을
    처음부터 안 넣은 것인지 실패해서 빠진 것인지 알 수 없다.
    """
    steps: list[str] = []
    reason = ""
    for note in notes:
        step_label = note["ref"].partition(" / ")[0]
        if step_label not in steps:
            steps.append(step_label)
        if not reason and note["kind"] == "failed":
            reason = note["reason"].splitlines()[0][:120]
    if not steps:
        return ""
    return (f"다음 내용은 빠졌습니다 — {', '.join(steps)}."
            + (f" ({reason})" if reason else ""))


def resolve_scheduled_period(period_json: dict, run_date=None) -> dict:
    """PeriodJson(규칙) + 기준일 → 실제 target_month/compare_type/grain/months_back.
    기준일 기본값은 오늘 — 백필·재실행은 run_date만 과거로 주면 된다.
    """
    from datetime import date as _date
    from d2insight.engine.pipeline.dataset_builder import shift_period

    run_date = run_date or _date.today()
    grain = period_json.get("grain") or "month"
    offset = period_json.get("offset", -1)

    if grain == "week":
        iso = run_date.isocalendar()
        current_period = f"{iso[0]:04d}-W{iso[1]:02d}"
    elif grain == "quarter":
        q = (run_date.month - 1) // 3 + 1
        current_period = f"{run_date.year:04d}-Q{q}"
    elif grain == "year":
        current_period = f"{run_date.year:04d}"
    else:
        current_period = f"{run_date.year:04d}-{run_date.month:02d}"

    target_month = shift_period(grain, current_period, offset)

    compare_base = (period_json.get("compare") or {}).get("base", "prev_period")
    compare_type = "YoY" if compare_base == "prev_year" else "MoM"

    return {
        "target_month": target_month,
        "compare_type": compare_type,
        "grain": grain,
        "months_back": period_json.get("history") or 3,
    }


def run_scheduled_report(
    steps_json: list,
    global_json: dict,
    period_json: dict,
    run_date=None,
    report_type: str = "보고서",
    session_id: str | None = None,
    provider: str | None = None,
) -> dict:
    """세션 없는 실행 진입점 — 저장된 정기 보고서 정의를 실제로 실행한다.

    확인 카드 없이 steps_json을 곧바로 inline_options로 넘긴다(재매칭·LLM 편집 연산 추출
    생략). Supabase 접근은 하지 않는다 — template 조회·결과 저장은 scheduled_runner.py가 한다.
    """
    period = resolve_scheduled_period(period_json, run_date)
    inline_options = {"steps": steps_json, "global": global_json or {}}
    return run_engine_report(
        message=f"[정기 보고서] {period['target_month']} {report_type}",
        target_month=period["target_month"],
        compare_type=period["compare_type"],
        months_back=period["months_back"],
        grain=period["grain"],
        report_type=report_type,
        provider=provider,
        session_id=session_id,
        matched_scenario=None,
        inline_options=inline_options,
    )


def run_module_quick(
    module_id: str,
    target_month: str,
    params: dict | None = None,
    compare_type: str | None = None,
    months_back: int | None = None,
    source_id: str | None = None,
    provider: str | None = None,
) -> dict:
    """단일 모듈 하나를 빠르게 실행한다(해설·결론 없음) — 채팅의 단일 분석 툴을 엔진으로 잇는 진입점.

    period_dataset 등 선행 모듈은 finalize의 의존성 보정이 자동으로 끼워 넣는다. 요청 모듈의
    Render만 골라 돌려주므로, 호출부(채팅)가 표/차트/요약을 자기 결과 계약으로 변환한다.

    반환: {"render": Render|None, "notes": [...], "plan_notes": [...]}
      - render None = 모듈이 실패·생략됨(사유는 notes). 조용히 감추지 않는다(§11 Step 2).
    """
    src_id = source_id or DEFAULT_SOURCE_ID
    plan = {"report_title": module_id, "steps": [
        {"title": module_id, "modules": [{"module_id": module_id, "params": params or {}}]},
    ]}
    schema, _ = data_digest(src_id)
    plan, plan_notes = finalize(plan, schema)      # 선행 모듈(period_dataset 등) 자동 보정

    meta: dict = {
        "target_month": target_month,
        "compare_type": compare_type or config.COMPARE_TYPE,
        "source_id": src_id,
        "provider": provider,
    }
    if months_back:
        meta["months_back"] = months_back
    ctx = SharedContext(meta=meta)

    instances, _ = expand_plan(plan, EngineCatalog())
    step_renders = execute(topo_order(instances), ctx)

    target_render: Render | None = None
    for entries in step_renders.values():
        for inst, render in entries:
            if inst.module_id == module_id:       # 의존으로 딸려온 선행 모듈이 아니라 요청 모듈만
                target_render = render
    return {"render": target_render, "notes": ctx.notes(), "plan_notes": plan_notes}
