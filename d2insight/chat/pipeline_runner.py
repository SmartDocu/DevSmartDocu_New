"""Execute analysis pipeline tools and return formatted chat results."""
from __future__ import annotations

import traceback

from backend.app.config import settings
from utilsPrj.ai_chain import build_langchain_llm, get_llm_info
from d2insight.config import LLM_MODELS

_llm_cache: dict = {}


def _get_llm(grade: str = "fast", project_id=None, tenant_id=None):
    key = (grade, project_id, tenant_id)
    if key not in _llm_cache:
        _, _api_key, _vendor = get_llm_info(project_id=project_id, tenant_id=tenant_id)
        _llm_cache[key] = build_langchain_llm(_vendor, _api_key, LLM_MODELS[_vendor][grade])
    return _llm_cache[key]


def _quick_chat(
    prompt: str,
    *,
    grade: str = "fast",
    system: str | None = None,
    max_tokens: int = 500,
    project_id=None,
    tenant_id=None,
) -> str:
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    resp = _get_llm(grade, project_id=project_id, tenant_id=tenant_id).invoke(messages)
    content = resp.content
    return content if isinstance(content, str) else content[0].text


def run_report_from_spec(spec: dict, user_id: str | None = None,
                         project_id=None, tenant_id=None) -> dict:
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
    }
    return run_tool("report", target_month, months_back, intent=intent, user_id=user_id,
                    project_id=project_id, tenant_id=tenant_id)


def run_tool(
    tool: str,
    target_month: str | None,
    months_back: int = 3,
    history: list[dict] | None = None,
    intent: dict | None = None,
    user_id: str | None = None,
    project_id=None,
    tenant_id=None,
) -> dict:
    """Execute pipeline tool and return {answer, visualization_type, table_html, chart_image, report_path}."""
    intent = intent or {}
    result: dict = {"visualization_type": "none", "table_html": None, "chart_image": None, "report_path": None}

    # ── health ──────────────────────────────────────────────────────────────
    if tool == "health":
        from d2insight.data_source.meta_loader import all_metadata
        meta_keys = list(all_metadata().keys())
        try:
            _hm, _, _hv = get_llm_info()
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
                                       project_id=project_id, tenant_id=tenant_id)
        return result

    # ── 이하 report 도구: target_month 필수 ─────────────────────────────────
    if not target_month:
        result["answer"] = "분석 기준월을 알려주세요. 예: '2024-01 보고서 작성해줘'"
        return result

    try:
        if tool == "report":
            from d2insight.report.agent import ReportAgent
            from d2insight.db.insight_storage import get_project_info

            report_type = intent.get("report_type") or "판매분석"
            user_request = intent.get("original_message")

            _tenant_id = tenant_id
            _project_id = project_id
            if user_id and (_project_id is None or _tenant_id is None):
                _tenant_id, _project_id = get_project_info(user_id)
            agent = ReportAgent(project_id=_project_id, tenant_id=_tenant_id)
            report_result = agent.generate(
                report_type, target_month, months_back,
                user_request=user_request,
            )
            md_text = report_result.get("md_text", "")
            md_filename = report_result.get("md_filename", "")

            brief = ""
            if md_text:
                try:
                    brief = _quick_chat(
                        f"다음 보고서 내용에서 핵심 내용을 3~4문장으로 요약하세요. 수치 중심으로 간결하게.\n\n{md_text[:4000]}",
                        grade="fast",
                        max_tokens=400,
                        project_id=project_id,
                        tenant_id=tenant_id,
                    )
                except Exception:
                    pass

            answer = f"{target_month} {report_type} 보고서 생성 완료.\n\n"
            if brief:
                answer += brief
            result["answer"] = answer
            result["report_path"] = md_filename

            if md_text and md_filename:
                try:
                    from d2insight.db.supabase_client import upload_report_bytes, build_qas_path
                    from d2insight.db.insight_storage import get_project_info
                    from d2insight.report.pdf import md_to_pdf_bytes

                    tenant_id, project_id = get_project_info(user_id) if user_id else (None, None)

                    md_path = build_qas_path(user_id, tenant_id, project_id, md_filename)
                    upload_report_bytes(md_path, md_text.encode("utf-8"), "text/markdown; charset=utf-8")
                    print(f"[Storage] MD 저장 성공: {md_path}")

                    pdf_filename = md_filename.replace(".md", ".pdf")
                    pdf_path = build_qas_path(user_id, tenant_id, project_id, pdf_filename)
                    pdf_bytes = md_to_pdf_bytes(md_text)
                    result["fileurl"] = upload_report_bytes(pdf_path, pdf_bytes, "application/pdf")
                    print(f"[Storage] PDF 저장 성공: {result['fileurl']}")
                except Exception as _e:
                    print(f"[Storage] {report_type} 저장 실패: {_e}")
                    traceback.print_exc()

        else:
            result["answer"] = f"알 수 없는 도구입니다: {tool}"

    except Exception as exc:
        result["answer"] = f"분석 중 오류가 발생했습니다.\n{type(exc).__name__}: {str(exc)[:400]}"

    return result
