"""엔진 진입점 (Step 0 플랫폼 접점).

채팅 라우터(app/chat/pipeline_runner.run_tool의 report 분기)가 부르는 단일 함수.
인텐트 파서가 뽑은 message/target_month/compare_type를 받아
계획기(scenario_plan 또는 auto_plan) → 실행 엔진(run_plan)을 돌리고 결과 마크다운·파일명·notes를 돌려준다.

**출력 계약 변환과 Supabase 저장은 호출부가 기존 흐름 그대로 처리한다.** 이 함수는
md_text/md_filename/notes 까지만 만든다 — 저장 로직을 여기서 중복하지 않는다(플랫폼 층은
기존 코드를 따른다, 지시서 §0.6).

기준월·비교유형은 여기서 계산하지 않는다(인텐트 파서의 몫, LLM 사용 경계 §7.1.2). 이 함수는
ctx.meta에 실어 모듈이 읽게 할 뿐이다.
"""
from __future__ import annotations

import json
from datetime import datetime

import d2insight.config as config
from d2insight.engine.catalog import EngineCatalog
from d2insight.engine.chat_options import default_steps_for_scenario, extract_operations
from d2insight.engine.context import SharedContext
from d2insight.engine.datasource import DEFAULT_SOURCE_ID
from d2insight.engine.operations import apply_operations, is_locked_step
from d2insight.engine.options import global_to_meta, options_to_plan
from d2insight.engine.planner import auto_plan, data_digest, finalize, scenario_plan
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

    없으면(추론 실패·미생성) None — 호출부가 데이터소스 정의 파일 경로로 폴백하지 않고
    그대로 진행하게 둔다. finalize()가 이후 스키마 없이 실행되면 명시적으로 실패한다(§11 Step 2).
    """
    if not upload_session_id or not upload_dataset_key:
        return None
    from d2insight.report.excel_registry import get_excel_server

    entry = (get_excel_server().session_datasets.get(upload_session_id) or {}).get(upload_dataset_key)
    engine_meta = (entry or {}).get("engine_meta")
    if not engine_meta:
        return None
    return Schema(engine_meta["meta_columns"])


_SCENARIO_MATCH_SYSTEM = """당신은 보고서 요청 문장을 읽고, 아래 등록된 시나리오 중 어느 것을
요청하는 것인지 의미로 판단한다. 표현이 등록된 이름과 글자 그대로 같지 않아도(예: "판매증감분석"은
"매출 증감 원인 분석"을 뜻함) 뜻이 같으면 매칭한 것으로 본다.

요청이 등록된 시나리오 중 하나에 해당하면 그 이름을 정확히 그대로(다른 글자·설명 추가 없이) 한 줄로
출력하라. 어느 것에도 해당하지 않으면 "없음"이라고만 출력하라."""


def match_scenario(message: str, provider: str | None = None) -> str | None:
    """메시지가 등록된 시나리오(기본세트) 중 하나를 요청하는 것인지 LLM으로 판단한다.

    문자열 부분일치가 아니라 의미 판단이다 — intent_parser의 report_type 분류와 같은 방식
    (§7.1.2, 2026-07-21 수정: 부분일치가 "판매증감분석" 같은 표현을 못 잡아 auto_plan으로
    빠지고, 그 경로에서 싱글턴 이름표 중복으로 PlanError가 난 사고의 근본 수정).
    어느 것도 아니면 None → 호출부는 auto_plan(자유 계획, 예외 경로)으로 진행한다.
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
    """채팅 메시지 안에 붙여넣은 옵션 JSON(steps + global)을 찾아 파싱한다.

    사용자가 이전 응답의 "적용된 옵션" JSON을 복사해 값만 고쳐 다시 던지는 흐름을 지원한다
    (2026-07-22). 대화·JSON 두 경로가 같은 형태로 수렴한다는 원칙 그대로 — 여기서 찾은 것은
    LLM 추출을 거치지 않고 그대로 options_to_plan에 들어간다.

    받는 형태는 둘 다 허용한다:
      - steps 배열 그대로:  [{"step_id": ..., "modules": [...]}, ...]
      - 감싼 객체:          {"steps": [...], "global": {...}}
    JSON이 없거나 형태가 다르면 None — 호출부는 기존 자연어 경로로 진행한다.

    반환: {"steps": [...], "global": {...}, "scenario": str|None, "analytic_uid": str|None,
    "origin_report": dict|None} — steps 배열 그대로 붙여넣은 경우 나머지는 빈 값(2026-07-24,
    G2 — global 절을 조용히 버리지 않도록 함께 반환한다. scenario는 2026-07-27, 정기 보고서
    이름 표시용으로 추가. analytic_uid는 2026-07-28, "정기 보고서로 저장" 시 이 실행의 출처를
    AnalyticTemplates.AnalyticUID/Analytics.Is_Template에 남기기 위해 추가. origin_report는
    같은 날, 정기 보고서 등록 시점에 방금 만든 보고서를 전용 세션의 첫 QA로 그대로 남기기
    위해 추가 — {"answer", "report_path", "fileurl"}. 오른쪽 패널이 보고서 응답에서 이미 받은
    값을 그대로 실어 보낼 뿐, 서버가 DB를 뒤져 찾지 않는다).
    """
    if not message or "{" not in message:
        return None

    # 객체 형태({"steps":[...], "global":{...}})를 배열 형태보다 먼저 시도한다. 반대 순서면
    # "[" 탐색이 steps 배열 안쪽만 잘라내 바깥 객체(및 global 절)를 통째로 놓친다 — global을
    # 버리기만 하던 때는 안 보이던 결함이었다(2026-07-24, G2에서 발견해 함께 수정).
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
    report_type: str = "판매분석",
    source_id: str | None = None,
    provider: str | None = None,
    upload_session_id: str | None = None,
    upload_dataset_key: str | None = None,
    matched_scenario=_UNRESOLVED,
    inline_options=_UNRESOLVED_INLINE,
) -> dict:
    """요청 하나를 실행 가능한 plan으로 해석한다(**실행은 하지 않는다**).

    확인 카드(preview_report_plan)와 실제 실행(run_engine_report)이 공유하는 단 하나의
    해석 로직이다 — 둘이 서로 다른 결과를 낼 수 없도록(2026-07-24, 5단계).

    반환: {"plan", "plan_notes", "applied_steps", "scenario",
           "target_month", "compare_type", "months_back", "grain", "source_id"}
      뒤 5개는 인자로 받은 값 위에 global 절(있으면)을 반영한 **최종 값**이다.
    """
    src_id = source_id or DEFAULT_SOURCE_ID
    upload_schema = _upload_schema(upload_session_id, upload_dataset_key)

    # 요청 문장이 등록된 시나리오를 지목하면, 프리셋 기본값 위에 그 문장이 명시적으로 요청한
    # 옵션(스텝 제외, top_n, 툴 등)만 얹는다(2026-07-22, 채팅 연결 작업). 시나리오를 못 찾으면
    # 순수 purpose 기반 auto_plan(LLM, 예외 경로). 업로드 데이터면 데이터소스 정의 파일 대신
    # 업로드 세션의 역할 메타(upload_schema)로 차원·측정 목록을 만든다.
    # applied_steps: 실제로 options_to_plan에 넘긴 "steps" 그대로 — 사용자에게 그대로 되돌려
    # 보여줄 수 있는 유일한 JSON이다(§ 표시용·입력용을 다른 형태로 만들지 않는다, 2026-07-22).
    # 사용자가 요청하지 않은 것(자동 삽입된 선행 모듈 등)은 여기 나타나지 않는다 — 의도된 것이다.
    applied_steps: list[dict] | None = None

    # 메시지에 옵션 JSON을 직접 붙여넣었으면 그것이 곧 사용자의 지정이다 — LLM 추출을 건너뛰고
    # 그대로 쓴다(대화·JSON 두 경로가 같은 형태로 수렴, 2026-07-22).
    if inline_options is _UNRESOLVED_INLINE:
        inline_options = extract_inline_options(message)

    scenario = match_scenario(message, provider=provider) if matched_scenario is _UNRESOLVED else matched_scenario

    if inline_options:
        inline_steps = inline_options["steps"]
        inline_global = inline_options.get("global") or {}

        # global 절이 명시한 값은 자연어보다 우선한다(2026-07-24, G2) — JSON에 적은 기간·
        # 비교유형·데이터소스·이력개월·measure를 조용히 버리지 않는다. 명시 안 된 키는 None이라
        # 기존 값(자연어에서 파싱된 값 또는 기본값)을 그대로 둔다.
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
            applied_steps = merged_steps
            print(f"[engine] 시나리오 프리셋 + 편집 연산 사용: '{scenario}' (operations={operations})")
        except Exception as e:
            # 조용히 삼키지 않는다(2026-07-24, G10) — 서버 로그뿐 아니라 plan_notes에도 남겨
            # 사용자가 "왜 내 요청이 기본값으로 나왔는지" 말풍선/패널에서 확인할 수 있게 한다.
            print(f"[engine] 편집 연산 추출/적용 실패, 프리셋 기본값으로 대체: {e}")
            plan, plan_notes = scenario_plan(scenario, source_id=src_id, schema=upload_schema)
            plan_notes = [
                f"요청하신 옵션을 반영하지 못해 기본 구성으로 작성했습니다 "
                f"({type(e).__name__}: {e})."
            ] + plan_notes
    else:
        plan, plan_notes = auto_plan(message, source_id=src_id, provider=provider, schema=upload_schema)
        # auto_plan은 steps 형태를 쓰지 않는 별도 경로(예외 경로)라 applied_steps를 만들지 않는다.

    if applied_steps:
        # period_dataset 파라미터에 실제 해석된 값을 채운다 — measure는 _resolve_measure가
        # 이미 이렇게 하고 있는데(options.py), compare_type/months_back/grain은 이 파라미터가
        # period_dataset 스펙에 선언만 돼 있을 뿐 채워주는 코드가 없어 늘 빈 값(카탈로그 기본값)
        # 으로 남아 있었다. applied_steps가 곧 실행 로그(AnalyticModules)로 남으므로, 여기서
        # 채워두지 않으면 "이 실행이 어느 기간·비교방식으로 돌았는지"가 로그 어디에도 남지
        # 않는다(2026-07-27, 6-2단계 — AnalyticTemplates 저장을 준비하며 발견).
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

        # 뿌리 스텝(자료확인·총평)에 locked 플래그를 붙인다 — 오른편 패널이 이동·삭제 불가
        # 표시를 별도 규칙 없이 그대로 읽게 한다(2026-07-24, 5단계). 잠금 판정은 operations.py
        # 하나뿐이다.
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
    report_type: str = "판매분석",
    source_id: str | None = None,
    provider: str | None = None,
    matched_scenario=_UNRESOLVED,
    inline_options=_UNRESOLVED_INLINE,
) -> dict:
    """확인 카드(오른편 패널)용 — 계획만 만들고 **실행하지 않는다**(2026-07-24, 5단계).

    run_plan(DB 조회·스텝별 LLM 서술·결론 LLM)을 타지 않아 run_engine_report보다 훨씬 가볍고
    빠르다. resolve_report_plan과 같은 해석 로직을 쓰므로, 사용자가 이 미리보기를 보고
    "이대로 작성"을 누르면 그때 실행되는 것과 **똑같은 구성**이 나온다는 것이 보장된다.

    반환의 "applied_steps"/"global"은 그대로 다시 붙여넣을 수 있는 옵션 JSON 형태다
    (§ 표시용=입력용 원칙). 업로드 데이터셋 미리보기는 이번 범위 밖(DB 모드만 지원).
    """
    resolved = resolve_report_plan(
        message, target_month, compare_type, months_back, grain, report_type, source_id, provider,
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
    report_type: str = "판매분석",
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

    matched_scenario: 호출부(pipeline_runner)가 라우팅 게이트에서 이미 match_scenario를 한 번
      돌렸다면 그 결과("시나리오명" 또는 None)를 그대로 넘긴다 — 같은 메시지로 LLM을 두 번
      부르지 않기 위함. 기본값(_UNRESOLVED)이면 여기서 직접 판단한다(스크립트 등 직접 호출용).

    반환: {"md_text", "md_filename", "notes", "plan_notes", "applied_steps", "scenario"}
      - notes: 실행 중 실패·생략된 분석(조용히 감추지 않는다)
      - plan_notes: 계획기가 요청을 카탈로그에 맞추며 보정한 내역(없는 차원 교정 등)
      - scenario: 매칭된 시나리오 이름(없으면 None) — 호출부가 Analytics 실행 로그에 그대로 싣는다
        (2026-07-27, 6-1단계). scenariouid는 아직 못 채운다 — 카탈로그(Scenarios 테이블) DB
        동기화가 안 돼 있어 이름 문자열만 대응할 UUID가 없다(추후 과제, 이번 6단계 범위 밖).
    """
    resolved = resolve_report_plan(
        message, target_month, compare_type, months_back, grain, report_type, source_id, provider,
        upload_session_id, upload_dataset_key, matched_scenario, inline_options,
    )
    plan = resolved["plan"]
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
        "grain": grain or "month",           # 2026-07-24 3단계 — month(기본)/quarter/year/week
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
        print(json.dumps(plan_composition(plan, catalog), ensure_ascii=False, indent=2, default=str))
    except Exception as _pe:                    # 조합 출력 실패가 보고서 생성을 막지 않게 한다
        print(f"[engine] 조합 출력 생략: {_pe}")

    out = run_plan(plan, catalog, ctx)

    # 파일명 — 옛 보고서와 같은 규칙(안전유형_기준월_타임스탬프.md)이라 저장 경로가 일관된다.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_filename = f"{_safe_type(report_type)}_{target_month}_{ts}.md"

    return {
        "md_text": out["markdown"],
        "md_filename": md_filename,
        "notes": out["notes"],
        "plan_notes": plan_notes,
        "applied_steps": applied_steps,
        "scenario": resolved["scenario"],
    }


def resolve_scheduled_period(period_json: dict, run_date=None) -> dict:
    """PeriodJson(규칙) + 기준일 → 이번 실행에 쓸 실제 target_month/compare_type/grain/
    months_back. 정의는 규칙만 갖고 값은 실행 시점에 계산한다(계획 §3 원칙) — 6-3단계, 세션
    없는 실행 진입점이 정기 보고서를 돌릴 때 쓴다. 기준일 기본값은 오늘(실행일) — 백필·재실행은
    run_date만 과거로 주면 특별한 코드 없이 같은 함수로 처리된다.
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
    report_type: str = "판매분석",
    session_id: str | None = None,
    provider: str | None = None,
) -> dict:
    """세션 없는 실행 진입점(6-3단계) — 저장된 정기 보고서 정의를 실제로 실행한다.

    사람이 없는 실행이라 확인 카드가 없다(§5 원칙) — 저장된 정의는 6-2에서 이미 빈 값 없이
    저장됐으므로, steps_json을 곧바로 inline_options로 넘긴다(시나리오 재매칭·LLM 편집 연산
    추출 모두 건너뜀 — matched_scenario=None으로 스킵해 불필요한 LLM 호출도 없다). 이 함수는
    Supabase 접근을 하지 않는다(entry.py는 엔진 계층, DB/Storage는 호출부의 몫이라는 원칙
    그대로, 파일 맨 위 docstring 참조) — template 조회·결과 저장·실행 로그 기록은
    app/chat/scheduled_runner.py가 담당한다.
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
