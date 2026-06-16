"""분석 파이프라인 도구를 실행하고 채팅 결과를 반환한다."""
from __future__ import annotations

import json
import traceback

import pandas as pd

from sqlalchemy.exc import OperationalError as SaOperationalError

from d2insight.llm.client import chat, ANTHROPIC_MODELS, OPENAI_MODELS
from d2insight.pipeline.data_loader import load_monthly_sales
from d2insight.pipeline.abc_xyz import run_phase2
from d2insight.pipeline.shapley import run_phase3
from d2insight.pipeline.drilldown import run_phase4_drilldown
from d2insight.pipeline.supplementary import run_phase4_supplementary
from d2insight.pipeline.validator import run_data_validation
from d2insight.pipeline.anomaly import run_anomaly_detection
from d2insight.pipeline.factor_selector import (
    detect_changes, select_factors, rank_combinations, build_factor_context,
)
from d2shared.visualization import dataframe_to_html_table, dataframe_to_chart_image
from d2insight import config


def _llm(
    context: str,
    data_str: str,
    grade: str = "fast",
    stepnm: str = "",
    call_type: str = "",
    provider: str | None = None,
) -> str:
    prompt = f"{context}\n\n분석 결과:\n{data_str[:2500]}"
    return chat(
        [{"role": "user", "content": prompt}],
        grade=grade,
        max_tokens=500,
        label="분석 요약",
        provider=provider,
    )


def _load_and_check(target_month: str, months_back: int) -> tuple[pd.DataFrame | None, str | None]:
    df = load_monthly_sales(target_month, months_back)
    if df.empty:
        return None, (
            f"'{target_month}' 기간에 해당하는 데이터가 없습니다.\n\n"
            "데이터가 존재하는 기간으로 다시 요청해주세요."
        )
    months_in_data: list[str] = sorted(df["월"].unique().tolist()) if "월" in df.columns else []
    if target_month not in months_in_data:
        recent = months_in_data[-3:] if months_in_data else []
        recent_str = ", ".join(recent) if recent else "없음"
        return None, (
            f"'{target_month}' 월의 데이터가 없습니다.\n\n"
            f"데이터에서 확인된 최근 기간: {recent_str}\n"
            "해당 기간으로 다시 요청해주세요."
        )
    return df, None


def run_report_from_spec(spec: dict, user_id: str | None = None, provider: str | None = None) -> dict:
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
    return run_tool("report", target_month, months_back, intent=intent, user_id=user_id, provider=provider)


def run_tool(
    tool: str,
    target_month: str | None,
    months_back: int = 5,
    history: list[dict] | None = None,
    intent: dict | None = None,
    user_id: str | None = None,
    provider: str | None = None,
) -> dict:
    """파이프라인 도구를 실행하고 {answer, visualization_type, table_html, chart_image, report_path}를 반환한다."""
    intent = intent or {}
    result: dict = {"visualization_type": "none", "table_html": None, "chart_image": None, "report_path": None}

    # ── health ──────────────────────────────────────────────────────────────
    if tool == "health":
        from d2insight.report.meta_loader import all_metadata
        from backend.app.config import settings
        meta_keys = list(all_metadata().keys())
        _prov = provider or "anthropic"
        if _prov == "anthropic":
            model_fast     = ANTHROPIC_MODELS["fast"]
            model_balanced = ANTHROPIC_MODELS["balanced"]
            model_quality  = ANTHROPIC_MODELS["quality"]
        elif _prov == "openai":
            model_fast     = OPENAI_MODELS["fast"]
            model_balanced = OPENAI_MODELS["balanced"]
            model_quality  = OPENAI_MODELS["quality"]
        else:
            model_fast = model_balanced = model_quality = f"unknown({_prov})"
        result["answer"] = (
            f"서버 상태: 정상 ✓\n"
            f"데이터 소스: postgresql\n"
            f"LLM provider: {_prov}\n"
            f"모델 fast: {model_fast}\n"
            f"모델 balanced: {model_balanced}\n"
            f"모델 quality: {model_quality}\n"
            f"Anthropic API: {'설정됨' if settings.CLAUDE_API_KEY else '미설정'}\n"
            f"DB 연결: {'설정됨' if settings.SUPABASE_DB_URL else '미설정'}\n"
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
            "1. 보고서 작성·데이터 분석 방법·통계 기법·분석 도구(ABC-XYZ, Shapley, 드릴다운, 이상치 감지 등)에 관한 질문은 "
            "보유한 지식으로 충분히 답변하세요.\n"
            "2. 보고서 작성 요청을 받으면 유형과 기간을 확인하여 작성을 안내하세요.\n"
            "3. 보고서·데이터 분석와 전혀 무관한 질문(날씨, 요리, 스포츠 등)은 "
            "한두 문장으로 이 챗봇의 역할을 설명하고 정중히 거절하세요.\n\n"
            "## 지원 보고서 유형\n"
            "경영분석, 판매분석, 생산분석, 원가분석, 품질분석, 구매조달분석,\n"
            "재고물류분석, 고객분석, 마케팅분석, 인사분석, 재무분석, 기술분석, 리스크분석\n\n"
            "## 판매분석 전용 고급 기능\n"
            "• ABC-XYZ 분류: 매출 기여도(A/B/C)와 수요 변동성(X/Y/Z)으로 제품을 분류\n"
            "• Shapley 기여도 분석: 차원별(채널·제품·지역 등) 매출 변화 원인 기여도 산출\n"
            "• 드릴다운: Primary Driver 기준 2단계 세부 원인 탐색\n"
            "• 이상치 감지·데이터 검증\n\n"
            "## 보고서 요청 예시\n"
            "• '2026-04 판매분석 보고서 작성해줘'\n"
            "• '2026-03 기술분석 보고서 (서버 로그)'\n"
            "• '2026-04 경영분석 보고서 작성하려 합니다'\n\n"
            + (f"이전 대화:\n{hist_text}\n\n" if hist_text else "")
        )
        try:
            result["answer"] = chat(
                [{"role": "user", "content": user_message}],
                grade="fast",
                system=system,
                max_tokens=600,
                label="채팅 응답",
                stepnm="agent",
                steptitle="에이전트 응답",
                provider=provider,
            )
        except Exception as _e:
            result["answer"] = f"LLM 응답 중 오류가 발생했습니다.\n{type(_e).__name__}: {str(_e)[:400]}"
        return result

    # ── 이하 모든 분석 도구: target_month 필수 ──────────────────────────────
    if not target_month:
        result["answer"] = "분석 기준월을 알려주세요. 예: '2014-01 분석해주세요'"
        return result

    try:
        if tool == "extract":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            df_summary = df.groupby("월")["매출"].sum().reset_index()
            df_summary.columns = ["월", "총매출"]
            table_html, _ = dataframe_to_html_table(df_summary)
            answer = _llm(
                f"{target_month} 기준 최근 {months_back}개월 월별 매출입니다. 추세와 핵심 내용을 3줄로 요약하세요.",
                df_summary.to_json(orient="records", force_ascii=False),
                provider=provider,
            )
            result.update({"answer": answer, "visualization_type": "table", "table_html": table_html})

        elif tool == "abc_xyz":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            p2 = run_phase2(df, target_month)
            targets = pd.DataFrame(p2["analysis_targets"])
            if not targets.empty:
                table_html, _ = dataframe_to_html_table(targets)
                result.update({"visualization_type": "table", "table_html": table_html})
            summary = p2["filter_window"]["summary"]
            n_changes = len(p2["grade_changes"])
            answer = _llm(
                f"{target_month} ABC-XYZ 분류 완료. 분석 대상 {len(targets)}건, 등급 변동 {n_changes}건. 핵심 내용을 3줄로 요약하세요.",
                json.dumps(summary, ensure_ascii=False, default=str),
                provider=provider,
            )
            result["answer"] = answer

        elif tool == "shapley":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            p2 = run_phase2(df, target_month)
            p3 = run_phase3(df, target_month, p2["analysis_targets"])
            shares: dict = p3.get("shapley_share", {})
            if shares:
                df_sh = pd.DataFrame([
                    {"차원": k, "기여도(%)": round(v * 100, 1)}
                    for k, v in sorted(shares.items(), key=lambda x: -abs(x[1]))
                ])
                chart_image, _ = dataframe_to_chart_image(df_sh, "차원별 기여도 막대그래프", chart_type="bar")
                if chart_image:
                    result.update({"visualization_type": "chart", "chart_image": chart_image})
            driver = p3.get("primary_driver", {}).get("primary", "알 수 없음")
            answer = _llm(
                f"{target_month} Shapley 분석 완료. Primary Driver: '{driver}'. 기여도와 시사점을 3줄로 요약하세요.",
                json.dumps(shares, ensure_ascii=False, default=str),
                grade="balanced",
                provider=provider,
            )
            result["answer"] = answer

        elif tool == "drilldown":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            p2 = run_phase2(df, target_month)
            p3 = run_phase3(df, target_month, p2["analysis_targets"])
            p4 = run_phase4_drilldown(
                df, target_month,
                p2["analysis_targets"],
                p3["primary_driver"]["primary"],
                p3["noise_dims"],
                p3["shapley_share"],
            )
            nodes = p4.get("nodes", [])
            if nodes:
                rows = []
                for n in nodes[:20]:
                    rows.append({
                        "차원": n.get("dim", ""),
                        "항목": n.get("item", ""),
                        "당월매출": n.get("current", 0),
                        "전월매출": n.get("prev", 0),
                        "Δ매출": round(n.get("current", 0) - n.get("prev", 0), 0),
                    })
                df_dd = pd.DataFrame(rows)
                table_html, _ = dataframe_to_html_table(df_dd)
                result.update({"visualization_type": "table", "table_html": table_html})
            answer = _llm(
                f"{target_month} 크로스 드릴다운 분석 완료. 상위 원인 항목과 시사점을 4줄로 요약하세요.",
                json.dumps(nodes[:8], ensure_ascii=False, default=str),
                grade="balanced",
                provider=provider,
            )
            result["answer"] = answer

        elif tool == "supplementary":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            p4s = run_phase4_supplementary(df, target_month, outlier_threshold=intent.get("threshold"))
            new_items = p4s.get("new_items", [])
            discontinued = p4s.get("discontinued_items", [])
            outliers = p4s.get("outliers", [])
            all_items = new_items + discontinued + outliers
            if all_items:
                df_items = pd.DataFrame(all_items[:20])
                table_html, _ = dataframe_to_html_table(df_items)
                result.update({"visualization_type": "table", "table_html": table_html})
            answer = _llm(
                f"{target_month} 보조 분석 완료. 신규 {len(new_items)}건, 단종 {len(discontinued)}건, 이상치 {len(outliers)}건. 핵심 내용을 3줄로 요약하세요.",
                json.dumps({"new": new_items[:3], "discontinued": discontinued[:3], "outliers": outliers[:3]},
                           ensure_ascii=False, default=str),
                provider=provider,
            )
            result["answer"] = answer

        elif tool == "validate":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            val = run_data_validation(df, target_month)
            issues = val.get("issues", [])
            if issues:
                df_issues = pd.DataFrame(issues[:20])
                table_html, _ = dataframe_to_html_table(df_issues)
                result.update({"visualization_type": "table", "table_html": table_html})
            answer = _llm(
                f"{target_month} 데이터 검증 완료. 이슈 {len(issues)}건. 주요 오류 패턴을 3줄로 요약하세요.",
                json.dumps(issues[:5], ensure_ascii=False, default=str),
                provider=provider,
            )
            result["answer"] = answer

        elif tool == "anomaly":
            df, err = _load_and_check(target_month, months_back)
            if err:
                result["answer"] = err
                return result
            anom = run_anomaly_detection(df, target_month)
            all_items: list[dict] = []
            for dim_data in anom.get("dimensions", {}).values():
                all_items.extend(dim_data.get("anomalies", []))
            if all_items:
                df_anom = pd.DataFrame(all_items[:20])
                table_html, _ = dataframe_to_html_table(df_anom)
                result.update({"visualization_type": "table", "table_html": table_html})
            achievement = anom.get("overall_achievement", 0)
            answer = _llm(
                f"{target_month} 이상치 감지 완료. 전체 달성률 {achievement:.1%}, 이상 항목 {len(all_items)}건. 심각 항목과 시사점을 3줄로 요약하세요.",
                json.dumps(all_items[:5], ensure_ascii=False, default=str),
                provider=provider,
            )
            result["answer"] = answer

        elif tool == "report":
            from d2insight.report.agent import ReportAgent
            report_type = intent.get("report_type") or "판매분석"
            user_request = intent.get("original_message")
            compare_type = intent.get("compare_type") or config.COMPARE_TYPE

            factor_ctx: dict | None = None
            sales_datasets = None

            if report_type == "판매분석":
                try:
                    from d2insight.pipeline.dataset_builder import build_all_datasets
                    sales_datasets = build_all_datasets(target_month, compare_type)
                    print(f"[dataset_builder] §2~§6 DataSet 빌드 완료 "
                          f"(actual={len(sales_datasets.actual_df):,}행)")
                except Exception as _de:
                    print(f"[dataset_builder] 빌드 실패 (보고서는 계속 진행): {_de}")

                df, err = _load_and_check(target_month, months_back)
                if err:
                    result["answer"] = err
                    return result
                try:
                    change_info = detect_changes(df, target_month, months_back)
                    p2 = run_phase2(df, target_month)
                    p3 = run_phase3(df, target_month, p2["analysis_targets"])
                    shapley_share: dict = p3.get("shapley_share", {})
                    factor_result = select_factors(shapley_share)
                    combos = rank_combinations(factor_result["factors"], factor_result["shares"])
                    factor_ctx = build_factor_context(change_info, factor_result, combos, shapley_share)
                except Exception as _fe:
                    print(f"[factor_selector] 스크리닝 실패 (ReportAgent는 계속 실행): {_fe}")

            agent = ReportAgent(provider=provider)
            report_result = agent.generate(
                report_type, target_month, months_back,
                user_request=user_request,
                factor_context=factor_ctx,
                sales_datasets=sales_datasets,
            )
            md_text = report_result.get("md_text", "")
            md_filename = report_result.get("md_filename", "")

            brief = ""
            if md_text:
                try:
                    brief = _llm(
                        "다음 보고서 내용에서 핵심 내용을 3~4문장으로 요약하세요. 수치 중심으로 간결하게.",
                        md_text[:4000],
                        grade="fast",
                        stepnm="분석 요약",
                        call_type="요약",
                        provider=provider,
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
                    from d2insight.history.supabase_client import upload_report_bytes, build_qas_path
                    from d2insight.history.insight_storage import get_project_info
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

    except SaOperationalError as exc:
        raw = str(exc.orig) if hasattr(exc, "orig") else str(exc)
        if any(kw in raw for kw in ["Timeout", "timeout", "Login timeout", "Unable to complete login"]):
            result["answer"] = (
                "DB 연결 타임아웃이 발생했습니다.\n\n"
                "확인 사항:\n"
                "• DB 서버가 실행 중인지 확인\n"
                "• 네트워크 연결 상태 확인\n"
                "• .env 의 SUPABASE_DB_URL 확인"
            )
        else:
            result["answer"] = f"DB 연결 오류가 발생했습니다.\n{raw[:300]}"

    except Exception as exc:
        result["answer"] = f"분석 중 오류가 발생했습니다.\n{type(exc).__name__}: {str(exc)[:400]}"

    return result
