"""Execute analysis pipeline tools and return formatted chat results."""
from __future__ import annotations

import json
import traceback

from backend.app.config import settings
from utilsPrj.ai_chain import get_llm_clients, get_llm_info
from d2insight import token_tracker


def _get_llm(grade: str = "fast", project_id=None, tenant_id=None, user_uid=None, account_uid=None):
    # ai_chain.get_llm_clients()가 (project/tenant/user/account) 조합당 한 번만 인증·생성해
    # 캐싱한다 — 중앙 캐시 하나를 공유(2026-08-31, 파일별 로컬 캐시 통일).
    clients = get_llm_clients(
        project_id=project_id, tenant_id=tenant_id,
        user_uid=user_uid, account_uid=account_uid, service_code="In",
    )
    return clients[grade]


def _quick_chat(
    prompt: str,
    *,
    grade: str = "fast",
    system: str | None = None,
    max_tokens: int = 500,
    project_id=None,
    tenant_id=None,
    user_uid=None,
    account_uid=None,
) -> str:
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    resp = _get_llm(grade, project_id=project_id, tenant_id=tenant_id,
                    user_uid=user_uid, account_uid=account_uid).invoke(messages)
    content = resp.content
    return content if isinstance(content, str) else content[0].text


def _answer_from_data(question: str, data: list, llm) -> str:
    """조회된 실제 데이터에만 근거해 답변 문장을 생성한다 (환각 방지 grounding)."""
    from langchain_core.messages import HumanMessage
    prompt = (
        f"사용자 질문: {question}\n\n"
        f"실제 조회된 데이터(JSON, 최대 30건): {json.dumps(data[:30], ensure_ascii=False, default=str)}\n\n"
        "위 데이터에 근거해서만 답변하세요. 데이터에 없는 내용은 절대 지어내지 마세요. "
        "간결하게 한국어로 답변하세요."
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    content = resp.content
    return content if isinstance(content, str) else str(content)


def _answer_data_question(
    user_message: str,
    session_id: str | None,
    project_id=None,
    tenant_id=None,
    user_uid=None,
    account_uid=None,
) -> str | None:
    """chat 메시지가 데이터 내용을 묻는 질문이면 실제 데이터로 그라운딩한 답을 반환하고,
    개념/방법론 질문 등 데이터와 무관하면 None을 반환해 지식 기반 답변으로 폴백하게 한다.

    업로드 데이터셋(있으면)과 DB 메타데이터 양쪽 모두에 대칭적으로 적용한다.
    """
    from d2insight.report.classifier import classify_question_and_table
    from d2insight.report.excel_registry import get_excel_server

    excel_server = get_excel_server()
    has_upload = bool(session_id and excel_server.has_datasets(session_id))
    llm = _get_llm("fast", project_id=project_id, tenant_id=tenant_id, user_uid=user_uid, account_uid=account_uid)

    if has_upload:
        probe = excel_server.execute_natural_language_query(
            question=user_message,
            session_id=session_id,
            llm=llm,
            classifier_fn=classify_question_and_table,
            log_ctx=token_tracker.get_log_ctx(),
        )
        status = probe.get("status")
        if status == "not_answerable":
            return None  # 데이터 질문이 아님 — 지식 기반 답변으로 폴백
        if status in ("no_data", "error", "no_dataset"):
            return probe.get("message") or "등록된 데이터에서 해당 내용을 찾지 못했습니다."
        data = probe.get("data")
        if status == "success" and data:
            return _answer_from_data(user_message, data, llm)
        return "등록된 데이터에서 해당 내용을 찾지 못했습니다."

    # DB 모드
    from d2insight.data_source.meta_loader import all_metadata
    from d2insight.report.sql_generator import SqlGenerator

    tables_metadata = all_metadata()
    if not tables_metadata:
        return None

    classification = classify_question_and_table(user_message, llm, tables_metadata)
    if not classification.get("is_answerable"):
        return None  # 데이터 질문이 아님 — 지식 기반 답변으로 폴백

    gen = SqlGenerator()
    result = gen.execute_natural_language_query(
        question=user_message,
        table_name=classification.get("table"),
        table_metadata=tables_metadata,
    )
    if result.get("error"):
        return f"조회 중 문제가 발생했습니다: {result['error']}"

    rows = result.get("data") or []
    if not rows or (len(rows) == 1 and str(rows[0].get("result", "")).upper() == "CANNOT_ANSWER"):
        return "등록된 데이터에서 해당 내용을 찾지 못했습니다."
    return _answer_from_data(user_message, rows, llm)


def _upload_engine_target(session_id: str | None) -> str | None:
    """이 세션에서 엔진이 쓸 업로드 데이터셋 키 목록을 "+"로 이어 돌려준다.

    DB의 source_id와 같은 형식이다. 스텝마다 이 목록에서 필요한 파일만 골라 쓴다 — 여러 개를
    올렸으면 스텝이 서로 다른 파일을 볼 수 있고, 한 스텝이 둘을 함께 봐야 하면 병합한다.
    """
    if not session_id:
        return None
    from d2insight.report.excel_registry import get_excel_server

    datasets = get_excel_server().session_datasets.get(session_id) or {}
    keys = [key for key, entry in datasets.items() if entry.get("engine_meta")]
    return "+".join(keys) if keys else None


def run_report_from_spec(spec: dict, user_id: str | None = None,
                         project_id=None, tenant_id=None, account_uid=None,
                         session_id: str | None = None) -> dict:
    """대화형 보고서 명세(ReportSpec)로부터 보고서를 생성한다."""
    target_month = spec.get("target_month")
    months_back = spec.get("months_back") or 3
    report_type = spec.get("report_type") or "판매분석"
    top_n = spec.get("top_n", 5)
    threshold = spec.get("threshold", "±3σ")
    intent = {
        "tool": "report",
        "target_month": target_month,
        "months_back": months_back,
        "report_type": report_type,
        "threshold": threshold,
        "mode": "auto",
        "original_message": (
            f"{target_month} {report_type} 보고서. "
            f"기준 데이터 {months_back}개월, 주요 품목 상위 {top_n}개, 이상치 기준 {threshold}."
        ),
        # "이대로 작성" 확정 후 기준월을 나중에 물어본 경우, create_spec()에 실어뒀던 스텝
        # 확정 옵션을 여기서 꺼내 넘긴다 — 없으면(자유 대화형) None 그대로.
        "scenario_options": spec.get("scenario_options"),
    }
    return run_tool("report", target_month, months_back, intent=intent, user_id=user_id,
                    project_id=project_id, tenant_id=tenant_id, user_uid=user_id, account_uid=account_uid,
                    session_id=session_id)


def run_tool(
    tool: str,
    target_month: str | None,
    months_back: int = 3,
    history: list[dict] | None = None,
    intent: dict | None = None,
    user_id: str | None = None,
    project_id=None,
    tenant_id=None,
    user_uid: str | None = None,
    account_uid: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Execute pipeline tool and return {answer, visualization_type, table_html, chart_image, report_path}."""
    intent = intent or {}
    result: dict = {"visualization_type": "none", "table_html": None, "chart_image": None, "report_path": None}

    # ── health ──────────────────────────────────────────────────────────────
    if tool == "health":
        from d2insight.data_source.meta_loader import all_metadata
        meta_keys = list(all_metadata().keys())
        try:
            _hm, _, _hv, _, _ = get_llm_info()
            llm_info_str = f"LLM: {_hm} ({_hv})"
        except Exception:
            llm_info_str = "LLM: 조회 실패"
        result["answer"] = (
            f"서버 상태: 정상 ✓\n"
            f"{llm_info_str}\n"
            f"DB 연결: {'설정됨' if all([settings.DB_SERVER, settings.DB_DATABASE, settings.DB_USERNAME]) else '미설정'}\n"
            f"메타 뷰/테이블: {', '.join(meta_keys) if meta_keys else '로드되지 않음'}"
        )
        return result

    # ── general chat ─────────────────────────────────────────────────────────
    if tool == "chat":
        hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in (history or [])[-6:])
        user_message = intent.get("original_message") or "도움이 필요합니다."

        try:
            data_answer = _answer_data_question(
                user_message, session_id,
                project_id=project_id, tenant_id=tenant_id, user_uid=user_uid, account_uid=account_uid,
            )
        except Exception as e:
            # print(f"[chat] 데이터 질문 응답 시도 실패 (지식 기반으로 폴백): {e}")
            pass
            data_answer = None

        if data_answer:
            result["answer"] = data_answer
            return result

        system = (
            "당신은 기업 데이터 분석 보고서 에이전트입니다.\n\n"
            "## 응답 방침\n"
            "1. 보고서 작성·데이터 분석 방법·통계 기법·분석 도구에 관한 질문은 "
            "보유한 지식으로 충분히 답변하세요.\n"
            "2. 보고서 작성 요청을 받으면 유형과 기간을 확인하여 작성을 안내하세요.\n"
            "3. 보고서·데이터 분석과 전혀 무관한 질문은 "
            "한두 문장으로 이 챗봇의 역할을 설명하고 정중히 거절하세요.\n\n"
            "## 지원 보고서 유형\n"
            "경영분석, 판매분석, 생산분석, 원가분석, 품질분석, 구매조달분석,\n"
            "재고물류분석, 고객분석, 마케팅분석, 인사분석, 재무분석, 기술분석, 리스크분석\n\n"
            "## 보고서 요청 예시\n"
            "• '2026-04 판매분석 보고서 작성해줘'\n"
            "• '2026-03 기술분석 보고서 (서버 로그)'\n"
            "• '2026-04 경영분석 보고서 작성하려 합니다'\n\n"
            + (f"이전 대화:\n{hist_text}\n\n" if hist_text else "")
        )
        result["answer"] = _quick_chat(user_message, system=system, grade="fast", max_tokens=600,
                                       project_id=project_id, tenant_id=tenant_id,
                                       user_uid=user_uid, account_uid=account_uid)
        return result

    # ── 이하 report 도구: target_month 필수 ─────────────────────────────────
    if not target_month:
        result["answer"] = "분석 기준월을 알려주세요. 예: '2024-01 보고서 작성해줘'"
        return result

    try:
        if tool == "report":
            from d2insight.db.insight_storage import get_project_info

            report_type = intent.get("report_type") or "보고서"
            user_request = intent.get("original_message")

            _tenant_id = tenant_id
            _project_id = project_id
            if user_id and (_project_id is None or _tenant_id is None):
                _tenant_id, _project_id = get_project_info(user_id)

            # 보고서를 만드는 곳은 engine 하나다. 시나리오가 매칭되면 그 프리셋으로, 매칭되지
            # 않으면 resolve_report_plan 안에서 compose_scenario(LLM이 카탈로그의 스텝·모듈·툴을
            # 조합)로 넘어간다 — 시나리오를 어디서 얻느냐만 다르고 실행은 같은 흐름이다.
            from d2insight.engine.entry import (
                extract_inline_options, match_scenario, run_engine_report, skipped_steps_note,
            )
            from d2insight.engine.runner import DataLoadError

            scenario_options = intent.get("scenario_options") or {}
            inline_options = None
            if scenario_options.get("applied_steps"):
                # 확정된 스텝 그대로 실행 — 재매칭 없이 미리보기와 정확히 같은 구성으로 돈다.
                inline_options = {
                    "steps": scenario_options["applied_steps"],
                    "scenario": scenario_options.get("scenario"),
                }
                matched_scenario = scenario_options.get("scenario")
            else:
                # 대화·JSON 두 경로가 같은 형태로 수렴한다는 원칙(engine/entry.py) — 메시지에
                # "적용된 옵션" JSON을 직접 붙여넣은 경우도 여기서 잡는다.
                inline_options = extract_inline_options(user_request or "")
                matched_scenario = match_scenario(user_request)

            # 데이터 출처(DB/업로드)로 실행이 갈리지 않는다 — 가져오는 방법만 다르고 그 뒤는
            # 같다. 업로드 파일이 있으면 그 목록을, 없으면 등록된 DB 소스 목록을 넘긴다.
            # 어느 쪽이든 "+"로 이은 목록이고, 스텝마다 그중 필요한 것만 골라 쓴다.
            from d2insight.report.excel_registry import get_excel_server
            has_upload = bool(session_id and get_excel_server().has_datasets(session_id))
            upload_dataset_key = _upload_engine_target(session_id) if has_upload else None
            if has_upload and not upload_dataset_key:
                # 파일을 올렸는데 쓸 수 있는 것이 하나도 없다. DB로 대신 만들면 사용자는 자기가
                # 올린 파일로 만들어진 줄 안다.
                result["answer"] = (
                    "업로드한 파일에서 컬럼의 뜻(역할)을 읽지 못했습니다. 다시 올려보시거나 "
                    "다른 파일로 시도해주세요."
                )
                return result

            source_id = None
            if not upload_dataset_key:
                from d2insight.engine.pipeline.db_meta import DbMetaError, resolve_source_cluster
                try:
                    source_id = "+".join(
                        c["datauid"] for c in resolve_source_cluster(_project_id, message=user_request)
                    )
                except DbMetaError as _dbe:
                    # 어느 데이터로 만들지 정하지 못하면 여기서 멈춘다 — 다른 경로로 몰래 만들면
                    # 무엇으로 만들어진 보고서인지 알 수 없다.
                    result["answer"] = str(_dbe)
                    return result

            try:
                eng = run_engine_report(
                    message=user_request or report_type,
                    target_month=target_month,
                    report_type=matched_scenario or report_type,
                    source_id=source_id,
                    user_id=user_id,
                    session_id=session_id,
                    upload_session_id=session_id if upload_dataset_key else None,
                    upload_dataset_key=upload_dataset_key,
                    matched_scenario=matched_scenario,
                    inline_options=inline_options,
                )
            except DataLoadError as _de:
                # 사유가 이미 사용자에게 할 말이다 — 앞말을 덧붙이지 않는다.
                print(f"[engine] {_de}")
                result["answer"] = str(_de)
                return result
            except Exception as _ee:
                traceback.print_exc()
                result["answer"] = f"보고서를 만들지 못했습니다: {_ee}"
                return result

            md_text = eng.get("md_text", "")
            md_filename = eng.get("md_filename", "")
            raw_applied_steps = eng.get("applied_steps")
            result["execution_cache"] = eng.get("execution_cache")
            report_type = eng.get("scenario") or report_type

            brief = ""
            if md_text:
                try:
                    brief = _quick_chat(
                        f"다음 보고서 내용에서 핵심 내용을 3~4문장으로 요약하세요. 수치 중심으로 간결하게.\n\n{md_text[:4000]}",
                        grade="fast",
                        max_tokens=400,
                        project_id=project_id,
                        tenant_id=tenant_id,
                        user_uid=user_uid,
                        account_uid=account_uid,
                    )
                except Exception:
                    pass

            answer = f"{target_month} {report_type} 보고서 생성 완료.\n\n"
            if brief:
                answer += brief
            # 일부 스텝이 빠졌으면 알린다 — 문서만 보면 처음부터 안 넣은 것인지 실패해서 빠진
            # 것인지 알 수 없다.
            skipped = skipped_steps_note(eng.get("notes") or [])
            if skipped:
                answer += f"\n\n{skipped}"
            result["answer"] = answer
            result["report_path"] = md_filename
            # 실제로 실행된 스텝·모듈 구성 그 자체다. _session.append_qa로 그대로 저장되므로
            # 이력·즐겨찾기·공유에서 다시 볼 때도 같은 값이 보인다.
            result["applied_steps"] = raw_applied_steps or scenario_options.get("applied_steps")

            try:
                from d2insight.db.insight_storage import record_analytics
                result["analytic_uid"] = record_analytics(
                    _tenant_id, _project_id, report_type,
                    raw_applied_steps, creator=user_id,
                )
            except Exception as _e:
                # print(f"[analytics] 실행 로그 기록 실패(무시하고 진행): {_e}")
                pass

            if md_text and md_filename:
                try:
                    from d2insight.db.supabase_client import upload_report_bytes, build_qas_path
                    from d2insight.db.insight_storage import get_project_info
                    from d2insight.report.pdf import md_to_pdf_bytes

                    tenant_id, project_id = get_project_info(user_id) if user_id else (None, None)

                    md_path = build_qas_path(user_id, tenant_id, project_id, md_filename)
                    upload_report_bytes(md_path, md_text.encode("utf-8"), "text/markdown; charset=utf-8")
                    # print(f"[Storage] MD 저장 성공: {md_path}")

                    pdf_filename = md_filename.replace(".md", ".pdf")
                    pdf_path = build_qas_path(user_id, tenant_id, project_id, pdf_filename)
                    pdf_bytes = md_to_pdf_bytes(md_text)
                    result["fileurl"] = upload_report_bytes(pdf_path, pdf_bytes, "application/pdf")
                    # print(f"[Storage] PDF 저장 성공: {result['fileurl']}")
                except Exception as _e:
                    # print(f"[Storage] {report_type} 저장 실패: {_e}")
                    pass
                    traceback.print_exc()

        else:
            result["answer"] = f"알 수 없는 도구입니다: {tool}"

    except Exception as exc:
        result["answer"] = f"분석 중 오류가 발생했습니다.\n{type(exc).__name__}: {str(exc)[:400]}"

    return result
