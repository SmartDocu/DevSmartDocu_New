"""ReportAgent — LangGraph StateGraph 기반 범용 보고서 생성기.

pr_d2chat MCPAgent 패턴 적용:
  - LangGraph StateGraph (call_model → tools → call_model 루프 자동 관리)
  - ChatAnthropic + bind_tools
  - @tool 데코레이터 기반 도구
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dateutil.relativedelta import relativedelta

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from utilsPrj.ai_chain import build_langchain_llm, get_llm_info
from d2insight import token_tracker
from d2insight.config import REPORT_MAX_WORKERS
from d2insight.data_source.generic_sql import GenericSqlSource
from d2insight.data_source import meta_loader
from d2insight.report.registry import get_config
from d2insight.report.tools import ALL_TOOLS
from d2insight.report.tools.chart_tool import _chart_store
from d2insight.report.tools.query_tool import _data_store


# ── SQL 방언 규칙 ──────────────────────────────────────────────────────────────

def _sql_rules(dialect: str) -> str:
    if "mssql" in dialect:
        return (
            "- SQL Server 문법 사용\n"
            "- 테이블/뷰 명칭은 [dbo].[이름] 형식\n"
            "- TOP 사용 (LIMIT 금지)\n"
            "- 한글 또는 비 ASCII 문자열 비교 시 반드시 N'문자열' 사용\n"
            "- JOIN 시 명시적으로 INNER JOIN 또는 LEFT JOIN 사용\n"
            "- 메타데이터에 명시된 컬럼명만 정확히 사용\n"
            "- 숫자 컬럼에 FORMAT() 등 문자열 변환 함수 사용 금지"
        )
    elif dialect in ("mysql", "postgresql", "sqlite"):
        return (
            "- 해당 DB 고유 문법 사용\n"
            "- LIMIT 사용 (TOP 사용 금지)\n"
            "- 테이블 명칭에 스키마 접두어(dbo) 사용 금지\n"
            "- 문자열 리터럴은 반드시 '문자열' 사용\n"
            "- N'문자열' 사용 금지"
        )
    elif "oracle" in dialect:
        return (
            "- Oracle SQL 문법 사용\n"
            "- FETCH FIRST N ROWS ONLY 사용\n"
            "- SYSDATE 사용\n"
            "- 문자열 리터럴은 '문자열' 사용"
        )
    return f"- {dialect} 문법 사용"


# ── 내부 진행/계획 서술 후처리 필터 ──────────────────────────────────────────
# 시스템 프롬프트의 "절대 금지"(진행 안내 문구 출력 금지) 지시만으로는 모델이 도구 호출
# 사이사이 내뱉는 내레이션을 완전히 막지 못한다(2026-08-19, haiku 실사용 보고서에서
# "이제 차트를 생성하겠습니다", "메타정보를 확인한 결과 ~컬럼이 없습니다",
# "사용자가 '결론' 스텝만 작성하도록 요청했습니다" 등 실제 유출 확인). _run_step()이
# 도구 호출 전후 모든 AIMessage 텍스트를 그대로 이어붙이는 구조라 프롬프트가 뚫리면 바로
# 최종 문서에 노출된다 — 문장 단위로 걸러내는 안전망을 추가한다.
_LEAK_PARAGRAPH_PATTERNS = [
    # "~스텝 작성 계획: 1. ... 2. ... 3. ..." 형태의 번호 목록은 문단 전체가 계획 텍스트라
    # 문장 단위로 쪼개면(숫자+마침표 뒤에서 끊김) "계획:" 부분만 지워지고 목록 항목들이
    # 그대로 살아남는다 — 이런 문단은 통째로 제거한다.
    re.compile(r'스텝\s*작성\s*계획\s*[:：]'),
]

_LEAK_SENTENCE_PATTERNS = [
    # 보고서 본문 서술은 "-습니다/-였습니다/-됩니다"류를 쓰고, "-겠습니다"(화자의 의지/예정)는
    # 쓰지 않는다 — "이제 ~하겠습니다", "~조회하겠습니다", "~작성하겠습니다" 등 접두어와
    # 무관하게 문장이 "겠습니다"로 끝나면 절차 내레이션으로 간주해 제거한다.
    re.compile(r'.*겠습니다[.!]?\s*$'),
    re.compile(r'.*사용자가\s.{0,40}요청했습니다.*'),                        # "사용자가 '결론' 스텝만 작성하도록 요청했습니다"
    re.compile(r'.*메타정보를\s*확인한\s*결과.*'),                            # "메타정보를 확인한 결과, ~컬럼이 없습니다"
    re.compile(r'^[\w가-힣().\s]+스텝(은|의)\s.*(분석하는|작성하는|정리하는)\s*스텝입니다[.!]?$'),  # "OO 스텝은 ~하는 스텝입니다"
]


def _strip_leaked_narration(text: str) -> str:
    """LLM이 절대 금지 지시에도 흘리는 진행/계획/메타 서술을 문단·문장 단위로 제거한다.

    1) 문단(빈 줄 기준) 전체가 계획 목록인 경우 통째로 드롭한다.
    2) 그 외 문단은 문장 단위로 다시 쪼개 판정한다 — 진행 문구와 실제 분석 내용이 한
       문단에 섞여 나오는 경우(예: "메타정보를 확인한 결과 ~없습니다. 주문ID 기준으로
       작성하겠습니다." 뒤에 바로 표가 이어지는 경우)에도 문제되는 문장만 골라 제거한다.
    """
    kept_paragraphs = []
    for para in re.split(r'\n{2,}', text):
        stripped_para = para.strip()
        if not stripped_para:
            continue
        if any(p.search(stripped_para) for p in _LEAK_PARAGRAPH_PATTERNS):
            continue
        sentences = re.split(r'(?<=[.!?다])\s+', stripped_para)
        clean = [
            s for s in sentences
            if s.strip() and not any(p.search(s.strip()) for p in _LEAK_SENTENCE_PATTERNS)
        ]
        cleaned_para = ' '.join(clean).strip()
        if cleaned_para:
            kept_paragraphs.append(cleaned_para)
    return '\n\n'.join(kept_paragraphs)


# ── 구조화 출력 종료 툴 ────────────────────────────────────────────────────────
# 정규식 기반 _strip_leaked_narration()만으로는 LLM이 표현을 바꿔가며 계속 새로운 문구로
# 새는 걸 두 차례 확인했다(2026-08-19 haiku 1차/2차 보고서 리뷰 — "이제 ~하겠습니다" →
# "~계획 -", "메타정보를 확인한 결과" → "메타정보를 다시 확인하니", 심지어 execute_query·
# run_variance_impact 같은 내부 툴 이름까지 노출). 패턴을 계속 추가하는 방식은 근본 해결이
# 아니므로, 스텝 완성 시 자유 텍스트 대신 이 툴을 호출해 최종 결과만 제출하도록 강제한다.
# _run_step()은 이 툴 호출의 인자만 스텝 콘텐츠로 채택하고, 그 밖의 모든 AIMessage
# 텍스트(계획·진행 안내·중간 판단 등)는 구조적으로 버린다 — 정규식이 그 표현을 알아야
# 걸러낼 수 있는 게 아니라, 애초에 그 텍스트가 최종 결과에 반영될 경로 자체가 없어진다.
@tool
def finalize_step(body_markdown: str) -> str:
    """이 스텝의 작성을 완료하고 최종 결과를 제출합니다.

    데이터 조회·차트 생성이 모두 끝나 스텝 본문이 완성되면 반드시 이 도구를 호출해
    최종 body_markdown을 전달하세요. **이 도구의 인자만 최종 보고서에 반영됩니다** —
    이 도구를 호출하기 전에 출력한 텍스트(계획, 진행 안내, 중간 판단 등)는 전부 버려지고
    독자에게 노출되지 않습니다.

    Args:
        body_markdown: 스텝 본문 전체. "## 스텝 제목"으로 시작하고, 도입 문장 → 데이터
            테이블(execute_query가 반환한 markdown_table을 그대로 삽입) 또는 차트
            (create_chart가 반환한 markdown_tag를 그대로 삽입) → 설명 텍스트 순서로
            작성하세요. 계획·진행 안내·내부 판단 근거·도구 이름·컬럼명 등 독자가 볼
            필요 없는 내용은 절대 포함하지 마세요.
    """
    return "스텝이 접수되었습니다."


def _date_range(target_month: str, months_back: int) -> tuple[str, str]:
    end_dt = datetime.strptime(target_month, "%Y-%m")
    end_dt = end_dt + relativedelta(months=1) - relativedelta(days=1)
    start_dt = datetime.strptime(target_month, "%Y-%m") - relativedelta(months=months_back - 1)
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def _compare_range(target_month: str, months_back: int) -> tuple[str, str]:
    """분석 기간(target_month부터 months_back개월) 바로 앞의, 같은 길이의 비교 기간을 계산한다.

    보고서 전체가 공유하는 단일 비교 기준을 만들기 위함이다 — 이전엔 스텝마다 독립된
    LangGraph 컨텍스트에서 실행되다 보니(_run_step 참고) "기간 비교" 스텝은 전월을
    비교 기간으로 스스로 추론해 맞혔지만, "원인 순위" 스텝은 같은 추론을 못 해 "비교
    기간이 명시되지 않았다"며 정적 현황 분석으로 후퇴하는 회귀가 있었다(2026-08-19
    확인). generate()가 이 값을 한 번 계산해 모든 스텝의 공통 시스템 프롬프트에 주입한다.
    """
    prev_target = datetime.strptime(target_month, "%Y-%m") - relativedelta(months=months_back)
    return _date_range(prev_target.strftime("%Y-%m"), months_back)


_MAX_META_CHARS = 40_000


def _condense_meta(meta: dict) -> dict:
    """뷰 이름·설명(앞 120자)·컬럼명 목록만 남긴 요약본 반환."""
    condensed = {}
    for view_name, info in meta.items():
        if not isinstance(info, dict):
            continue
        cols = info.get("columns") or []
        col_names = [
            c.get("name", c) if isinstance(c, dict) else str(c)
            for c in cols[:50]
        ]
        condensed[view_name] = {
            "description": str(info.get("description", ""))[:120],
            "columns": col_names,
        }
    return condensed


def _build_factor_block(factor_context: dict) -> str:
    """판매분석 요인 스크리닝 결과를 시스템 프롬프트 삽입용 텍스트로 변환한다."""
    delta_pct = factor_context.get("total_delta_pct", 0.0)
    direction = factor_context.get("direction", "변화")
    n_sig = factor_context.get("n_significant", 0)
    share_text = factor_context.get("shapley_share_text", "")
    mode = factor_context.get("mode", "single")
    dominant = factor_context.get("dominant_factor")
    combo_text = factor_context.get("combo_text", "")

    lines = [
        "## 사전 요인 스크리닝 결과 (Shapley + ABC-XYZ)",
        f"- 전월평균 대비 매출 {direction}: {abs(delta_pct) * 100:.1f}%",
        f"- 30%+ 유의미 변화 항목: {n_sig}건",
        f"- 차원별 기여도: {share_text}",
        "",
    ]

    if mode == "single" and dominant:
        lines += [
            f"**분석 집중 지시**: '{dominant}' 차원이 압도적 주요 요인입니다.",
            f"보고서 본론에서 '{dominant}' 차원을 중심으로 심층 분석하세요.",
            "다른 차원은 보조 맥락으로만 언급하세요.",
        ]
    else:
        lines += [
            "**분석 집중 지시**: 복수 요인이 유의미합니다. 아래 조합 순위대로 각각 심층 분석하세요.",
            combo_text,
            "- 각 조합마다 별도 스텝을 구성하고 쿼리 → 차트/테이블 → 설명 순서로 작성하세요.",
            "- 상위 조합이 어떻게 함께 작용했는지 교차 분석에 집중하세요.",
        ]

    return "\n".join(lines)


def _build_sales_dataset_context(sales_datasets) -> str:
    """§2~§6 DataSet 요약을 시스템 프롬프트용 텍스트로 변환한다."""
    from d2insight.pipeline.dataset_builder import SalesDatasets
    if not isinstance(sales_datasets, SalesDatasets):
        return ""

    ds = sales_datasets
    lines: list[str] = [
        "",
        "## 사전 계산된 분석 데이터셋 (Python 확정값)",
        f"분석월: {ds.target_month}  비교기준: {ds.compare_type}",
        "",
    ]

    # §3 Summary
    if not ds.summary_df.empty:
        lines += [
            "### §3 매출 전체 요약 (Summary_DataSet)",
            ds.summary_df.to_markdown(index=False),
            "",
        ]

    # §5 By_Item_Summary (DVI 내림차순)
    if not ds.byitem_summary_df.empty:
        df5 = ds.byitem_summary_df.sort_values("DVI", ascending=False)
        cols5 = ["Dimension_Logical_Name", "Count", "Impact_Score",
                 "Shapley_Value", "Average_Z", "HHI", "DVI"]
        cols5 = [c for c in cols5 if c in df5.columns]
        lines += [
            "### §5 차원별 영향도 (By_Item_Summary_DataSet) — DVI 내림차순",
            df5[cols5].to_markdown(index=False),
            "",
        ]

    # §6 Count
    if not ds.byitem_count_df.empty:
        lines += [
            "### §6 신규/손실 현황 (By_Item_Count_DataSet)",
            ds.byitem_count_df.to_markdown(index=False),
            "",
        ]

    # §4 주요 항목 (DVI 상위 5차원, Is_Main=1, 차원당 최대 20개)
    if not ds.byitem_df.empty and not ds.byitem_summary_df.empty:
        top_dims = (ds.byitem_summary_df
                    .sort_values("DVI", ascending=False)["Dimension_Logical_Name"]
                    .head(5).tolist())
        sub4 = ds.byitem_df[
            ds.byitem_df["Dimension_Logical_Name"].isin(top_dims)
            & (ds.byitem_df["Is_Main"] == 1)
        ].copy()
        sub4["_abs_var"] = sub4["Variance"].abs()
        sub4 = (sub4.sort_values(["Dimension_Logical_Name", "_abs_var"], ascending=[True, False])
                .groupby("Dimension_Logical_Name").head(20)
                .drop(columns=["_abs_var"]))
        cols4 = ["Dimension_Logical_Name", "Item_Name",
                 "Comparison_Value", "Actual_Value", "Variance", "Rate", "New_Lost_Flag"]
        lines += [
            "### §4 주요 항목 (By_Item_DataSet — DVI 상위 5차원, Is_Main=1)",
            sub4[cols4].to_markdown(index=False),
            "",
        ]

    # §13 Sales Bridge
    bridge = ds.sales_bridge
    if bridge:
        lines += [
            "### §13 Sales Bridge 분해",
            f"| 항목 | 금액 |",
            f"|------|------|",
            f"| 총 매출 증감 | {bridge.get('total_variance', 0):,.0f} |",
            f"| 수량 효과 | {bridge.get('qty_effect', 0):,.0f} |",
            f"| ASP 효과 | {bridge.get('asp_effect', 0):,.0f} |",
            f"| 할인 효과 | {bridge.get('discount_effect', 0):,.0f} |",
            f"| 신규 상품 효과 | {bridge.get('new_product_effect', 0):,.0f} |",
            f"| 단종 상품 효과 | {bridge.get('lost_product_effect', 0):,.0f} |",
            f"| 신규 고객 효과 | {bridge.get('new_customer_effect', 0):,.0f} |",
            f"| 이탈 고객 효과 | {bridge.get('lost_customer_effect', 0):,.0f} |",
            "",
        ]

    # 보고서 스텝 구조 지시
    lines += [
        "## 보고서 작성 스텝 구조 (방침)",
        "위 데이터를 기반으로 아래 순서로 보고서를 작성하세요.",
        "데이터가 없거나 해당 없는 스텝은 생략합니다.",
        "",
        "**§11. 매출 증감 총평**",
        "  Summary_DataSet 기반. 매출 규모/증감률/수량/ASP/할인율 변화를 서술.",
        "",
        "**§12-A. 차원 영향도 분석 (Dimension Variance Driver Analysis)**",
        "  By_Item_Summary의 DVI·Shapley 순위표 제공. 어느 차원이 가장 큰 영향을 미쳤는지 해석.",
        "",
        "**§12-B. 차원 내 기여도 분석 (Contribution Analysis)**",
        "  DVI 상위 5차원에 대해 항목별 기여도(= 항목 증감액 / 전체 증감액) 상위 20개 표 제공.",
        "",
        "**§13. Sales Bridge 분해**",
        "  수량·ASP·할인·신규상품·단종·신규고객·이탈고객 효과를 Sales Bridge 표로 제시.",
        "  데이터(수량·할인 컬럼)가 없으면 이 스텝은 생략.",
        "",
        "**§14. 이상징후 분석 (Anomaly Detection)**",
        "  Is_Main=1 항목 기준 Z-Score 산출. ±3σ 초과 항목을 DVI 상위 5차원별로 리스팅.",
        "  리스팅 금액 기준 Top 10 재정리.",
        "",
        "**§15. Drill Down / Cross Analysis**",
        "  §14 이상징후 금액 Top5 항목에 대해 다음 영향도 차원으로 교차 분석.",
        "  execute_query 툴로 세부 데이터 조회 후 원인 파악.",
        "",
        "**최종. 경영 인사이트**",
        "  핵심 성장 요인 Top3 / 핵심 감소 요인 Top3 / 신규·이탈 효과 / 이상징후 / Action Item.",
        "  경영진이 3분 이내 핵심 원인을 파악할 수 있도록 간결하게 작성.",
    ]

    return "\n".join(lines)


def _build_system_prompt(
    report_type: str,
    meta: dict,
    dialect: str,
    date_range: tuple[str, str],
    factor_context: dict | None = None,
    include_plan_instruction: bool = True,
    sales_datasets=None,
    has_upload: bool = False,
    compare_range: tuple[str, str] | None = None,
) -> str:
    meta_text = json.dumps(meta, ensure_ascii=False, indent=2)
    if len(meta_text) > _MAX_META_CHARS:
        meta_text = json.dumps(_condense_meta(meta), ensure_ascii=False, indent=2)
    if len(meta_text) > _MAX_META_CHARS:
        meta_text = meta_text[:_MAX_META_CHARS] + "\n...(메타데이터 일부 생략)"
    sql_rules = _sql_rules(dialect)
    start, end = date_range
    meta_header = "## 업로드된 데이터셋" if has_upload else "## 사용 가능한 데이터 (메타정보)"

    if has_upload:
        data_rules_block = (
            "## 데이터 조회 규칙\n"
            "- execute_excel_query 툴에 자연어 질문을 전달하면 내부에서 pandas 코드가 자동 생성되어 실행됩니다.\n"
            "- SQL/pandas 코드를 직접 작성하지 마세요."
        )
        query_block = (
            "2. 각 스텝에 필요한 데이터를 execute_excel_query 툴로 조회하세요.\n"
            "   - pandas 코드를 직접 작성하지 마세요. question에 자연어로 분석 목적을 설명하면 내부에서 코드가 자동 생성됩니다.\n"
            "   - table_name 지정은 필요 없습니다 — 등록된 데이터셋 중 적합한 것이 자동 선택됩니다.\n"
            f"   - question에 분석 기간({start} ~ {end})을 반드시 포함하세요.\n"
            "   - 반드시 집계 데이터를 요청하세요: \"~별 건수/합계/평균\" 형태로 질문하세요.\n"
            "   - 조회 결과가 비어 있거나(row_count=0) error가 있으면 해당 스텝을 작성하지 말고 바로 종료하세요.\n"
            "   - 등록된 데이터셋에 없는 내용은 절대 지어내지 마세요."
        )
    else:
        data_rules_block = f"## SQL 규칙\n{sql_rules}"
        query_block = (
            "2. 각 스텝에 필요한 데이터를 execute_query 툴로 조회하세요.\n"
            "   - SQL을 직접 작성하지 마세요. question에 자연어로 분석 목적을 설명하면 내부에서 SQL이 자동 생성됩니다.\n"
            "   - table_name에 메타정보에서 확인한 뷰 이름을 반드시 지정하세요. 생략 금지.\n"
            f"   - question에 분석 기간({start} ~ {end})을 반드시 포함하세요.\n"
            "   - 반드시 집계 데이터를 요청하세요: \"~별 건수/합계/평균\" 형태로 질문하세요.\n"
            "   - 조회 결과가 비어 있거나(row_count=0) CANNOT_ANSWER이면 해당 스텝을 작성하지 말고 바로 종료하세요.\n"
            f"   - 현재 작성 중인 '{report_type}' 보고서와 무관한 데이터 뷰는 절대 사용하지 마세요."
        )

    factor_block = ""
    if factor_context:
        factor_block = "\n\n" + _build_factor_block(factor_context)

    dataset_block = ""
    if sales_datasets is not None and report_type == "판매분석":
        dataset_block = _build_sales_dataset_context(sales_datasets)

    sales_plan_block = ""
    if include_plan_instruction and report_type == "판매분석":
        sales_plan_block = (
            "\n\n## 판매분석 스텝 계획 지시\n"
            "보고서 본문 작성 전, `<plan>` 태그 안에 스텝 목록을 작성하여 이 달 데이터에 맞는 구성을 결정하세요.\n"
            "`<plan>...</plan>` 블록은 최종 보고서에서 자동으로 제거됩니다.\n\n"
            "예시 형식:\n"
            "<plan>\n"
            "1. 분석 개요\n"
            "2. 월별 매출 추이\n"
            "3. 지역별 매출 심층 분석\n"
            "4. 전월 대비 증감 분석\n"
            "</plan>\n\n"
            "스텝 계획 기준:\n"
            "- **사전 요인 스크리닝 결과**의 기여도 높은 차원을 중심으로 스텝 구성\n"
            "- 분석 개요·월별 매출 추이·Primary Driver 차원 분석·전월 대비 증감은 반드시 포함\n"
            "- 기여도 낮은 차원(noise 판정)은 별도 스텝 없이 간략 언급으로 처리\n"
            "- 데이터에서 유의미한 패턴 발견 시 교차분석 등 스텝을 자율적으로 추가\n\n"
            "`</plan>` 이후 **계획한 모든 스텝을 완성하기 전에는 절대 종료하지 마세요.**\n"
            "각 스텝은 execute_query → create_chart(필요 시) → 설명 텍스트 순서로 작성하세요."
        )

    compare_block = ""
    if compare_range:
        compare_block = (
            f"\n## 비교 기간(전월 대비 — 보고서 전체 공통 기준)\n{compare_range[0]} ~ {compare_range[1]}\n"
            "전월 대비 증감을 다루는 스텝(예: 원인 순위, 증감 분석 등)은 이 기간을 비교 기준으로\n"
            "쓰세요. 스텝마다 비교 기간을 따로 추론하거나 \"비교 기간이 명시되지 않았다\"고 판단해\n"
            "정적 현황 분석으로 후퇴하지 마세요 — 이미 위에 정해져 있습니다.\n"
        )

    return f"""당신은 '{report_type}' 보고서를 작성하는 데이터 분석 전문가입니다.

## 분석 기간
{start} ~ {end}
{compare_block}
{meta_header}
{meta_text}

{data_rules_block}{factor_block}{dataset_block}{sales_plan_block}

## 보고서 작성 절차
1. 사용자의 요청을 정확히 파악하고 그에 맞는 보고서 구조(스텝 목차)를 계획하세요.
   - 판매분석의 경우 "판매분석 스텝 계획 지시"에 따라 <plan> 태그로 먼저 계획하고, 계획한 모든 스텝을 순서대로 완성하세요.
   - 사용자가 특정 분석 방법을 요청하면 반드시 해당 방법을 사용하세요.
   - 지정된 스텝 제목이 요구하는 차원(예: "고객별 분석")의 데이터가 실제로 없어 다른
     차원(예: 주문ID)으로 대체해서 작성해야 하는 경우, **스텝 제목을 실제 분석 내용에
     맞게 바꿔서 출력**하세요(예: "고객별 분석" → "주문별 분석"). 대체한 이유를 본문에
     설명하지 말고, 바뀐 제목과 실제 데이터로 스텝을 완성하세요.
{query_block}
3. 필요시 run_stats / run_trend / run_outlier 툴로 추가 분석하세요.
   - 차원별 증감 영향도(어느 차원이 변화를 주도했는지)가 필요하면 run_variance_impact를 쓰세요.
     이번기간·비교기간을 각각 execute_query로 조회한 뒤 두 결과를 전달하세요.
   - 매출 증감을 항목별 신규/단종/수량효과/단가효과로 분해하려면 run_sales_bridge를 쓰세요.
   - 매출→매출원가→매출총이익→판관비→영업이익 손익 계단이 필요하면 run_pnl_waterfall을 쓰세요
     (각 단계 금액을 execute_query로 미리 집계해서 전달).
4. 데이터가 있는 모든 주요 스텝에서 create_chart 툴로 시각화하세요. (의무)
   - create_chart 호출 후 tool result의 markdown_tag 값을 반드시 해당 위치의 텍스트에 삽입하세요.
   - 예: tool result = {{"markdown_tag": "![오류 추이](data:image/png;base64,...)"}}
          → 텍스트에 그대로 삽입: ![오류 추이](data:image/png;base64,...)
5. 각 스텝은 반드시 다음 순서로 작성하세요.
   a) 스텝 도입 문장 (이 스텝에서 무엇을 분석하는지 1~2문장)
   b) 데이터 테이블 또는 차트
      - 표는 execute_query가 반환한 markdown_table 값을 **그대로** 삽입하세요. data를
        보고 표를 손으로 다시 작성하지 마세요 — 행을 빠뜨리거나 숫자를 잘못 옮기는
        사고를 막기 위함입니다. 특정 정렬(예: 매출액 내림차순)이 필요하면 execute_query
        호출 시 question에 정렬 기준을 명시하세요.
      - 차트는 create_chart가 반환한 markdown_tag를 그대로 삽입하세요.
      - 한 스텝에서 같은 항목을 표와 차트로 같이 보여줄 때는 **반드시 같은 execute_query
        결과 하나**를 표(markdown_table)와 차트(data)에 함께 쓰세요. 표에는 10개만
        보여주면서 차트 제목엔 "상위 20개"라고 쓰는 식으로 범위가 어긋나면 안 됩니다.
   c) 설명 텍스트 — **이 부분이 핵심입니다**:
      - 주요 수치를 구체적으로 언급하세요. (예: "X가 Y% 증가했으며, Z는 최고치를 기록했다.")
      - 언급하는 수치는 반드시 표/차트에 실제로 나온 값과 정확히 일치해야 합니다.
        암산으로 재계산하거나 어림해서 새 숫자를 만들지 마세요.
      - 눈에 띄는 패턴·증감·이상값을 사실에 근거해 서술하세요.
      - 단순 수치 나열에 그치지 말고, 수치가 의미하는 바에 대해 간략한 의견을 덧붙이세요.
   ※ 차트나 테이블만 단독으로 삽입하고 설명 없이 다음 스텝으로 넘어가는 것은 절대 금지입니다.
6. 결론·예측·시사점 스텝은 작성하지 마세요. 해당 스텝은 별도로 추가됩니다.
   - 개별 스텝 안에 "핵심 시사점"/"종합 해석"/"향후 전망" 같은 종합·전망 소제목을
     별도로 넣지 마세요. 그 역할은 별도로 추가되는 결론 스텝의 몫입니다. 각 스텝은
     자기 데이터에 대한 설명으로 끝내세요.
7. 스텝 본문이 완성되면 **반드시 finalize_step 툴을 호출**해 최종 body_markdown을
   제출하고 종료하세요. finalize_step을 호출하기 전에 출력한 텍스트는 독자에게
   전달되지 않으므로, 계획·중간 판단을 텍스트로 미리 출력할 필요가 없습니다 — 데이터
   조회·차트 생성이 끝나면 바로 finalize_step을 호출하세요.

## 출력 형식
- Markdown (## 스텝, ### 소스텝 사용)
- 데이터 테이블: execute_query의 markdown_table을 그대로 삽입 (손으로 재작성 금지)
- 차트: create_chart 툴 호출 후 반환된 markdown_tag를 텍스트에 직접 삽입
- 완성된 최종 결과는 finalize_step 툴 호출로만 제출하세요 (텍스트 직접 출력 금지)

## 차트 유형 선택 지침 (create_chart 호출 시 chart_type 필수 명시)
| 상황 | chart_type |
|---|---|
| 두 계열의 단위/스케일이 크게 다를 때 (예: 매출액 + 변화율%, DVI + Shapley_Value) | **dual_axis** |
| 점유율·구성비·기여도 비율 표시 | **pie** |
| X축이 날짜·월·분기 등 시계열인 경우 기본 | **line** |
| X축이 제품명·지역명·채널 등 범주형인 경우 기본 | **bar** (추이라도 bar 사용) |
| 항목 간 수치 비교 기본값 | **bar** |

**이중축(dual_axis) 사용 기준**: 두 계열 최대값의 비율이 50배 이상이면 반드시 dual_axis 사용.
- DVI(수만~수십만) + Shapley_Value(0~1) → dual_axis
- 매출액(수십만~수백만) + MoM 변화율(-100%~+100%) → dual_axis
- question에 '이중축', '변화율', '점유율+매출' 포함 시 → dual_axis

**두 시점(예: 이번달 vs 지난달)을 비교하는 차트**: execute_query를 시점별로 각각 호출한 뒤,
각 결과의 레코드(원래 컬럼명 그대로)를 리스트로 이어붙여 create_chart의 data에 전달하세요.
값을 컬럼명 자리에 넣지 마세요 — create_chart는 컬럼명이 숫자처럼 보이면 에러를 반환합니다.

## 지표 정의 일관성 (중요)
- 메타정보에 '매출'을 가리킬 수 있는 컬럼이 여러 개 있을 수 있습니다
  (예: 주문 헤더의 세금·배송비 포함 총액 vs 상세 라인의 상품 순매출액).
- 보고서 전체에서 "매출액"/"총매출"이라는 용어는 **하나의 컬럼 기준으로만 통일**해서
  사용하세요. 상단 총계는 A컬럼, 카테고리별 집계는 B컬럼처럼 스텝마다 기준이 다른 컬럼을
  쓰면, 같은 이름의 지표인데 합계가 서로 안 맞는 모순이 문서 안에 생깁니다.
- 부득이하게 서로 다른 두 기준값을 함께 언급해야 한다면, 각 수치 옆에 어떤 기준인지
  괄호로 명시하세요. (예: "총매출 $3,831,606(세금·배송비 포함)",
  "상품 매출 $3,412,069(세금·배송비 제외)")
- 상품/카테고리처럼 **주문 1건에 여러 값이 나올 수 있는 차원으로 건수를 집계**하면
  (예: 카테고리별 건수 합계) 실제 주문 건수보다 커질 수 있습니다(한 주문이 여러
  카테고리를 포함하면 중복 집계됨). 이런 집계에는 "주문 건수"라는 이름을 쓰지 말고
  "판매 건수"/"라인 건수" 등으로 구분하고, 실제 총 주문 건수(예: 지역별/기간별 집계에서
  나온 값)와 헷갈리지 않게 하세요.

## 통화·숫자 표기 규칙 (중요)
- 데이터의 통화 단위를 메타정보/컬럼에서 확인한 그대로 사용하세요. 달러(USD) 데이터를
  원(₩)으로, 또는 그 반대로 표기하지 마세요. 한 문서 안에서 통화 단위를 섞어 쓰면 안 됩니다.
- **"만"/"억" 같은 한글 단위 변환은 원화(KRW)에만 사용하세요.** 달러 등 다른 통화는 원본
  숫자에 천 단위 콤마만 붙여 그대로 쓰세요. (예: 2,878,098 → "2,878,098달러"이지 "2,878만
  달러"가 아닙니다 — 만/억 변환은 암산 오류가 나기 쉬워 자릿수가 틀린 채로 노출된 사례가
  있었습니다.)
- 숫자를 요약·환산해서 서술할 때도 반드시 원본 값과 일치하는지 스스로 검산하세요.

## 절대 금지
- 툴 호출 전후에 진행 안내 문구를 출력하지 마세요.
  ("데이터를 조회하겠습니다", "분석을 시작합니다", "차트를 생성하겠습니다" 등 일체 금지)
- 계획·분석 접근·실행 계획 같은 걸 텍스트로 먼저 출력하지 마세요. 무엇을 할지는 바로
  실행(툴 호출)하고, 결과는 finalize_step으로만 제출하세요.
- 도구 이름(execute_query, create_chart, run_variance_impact 등)이나 DB 테이블/뷰/컬럼
  이름을 본문에 언급하지 마세요. 독자는 이런 내부 구현을 알 필요가 없습니다.
- 텍스트는 오직 finalize_step에 전달할 보고서 스텝 내용만 작성하세요."""


def _build_conclusion_prompt(
    report_type: str,
    md_body: str,
    factor_context: dict | None,
    raw_data: list[dict] | None = None,
) -> str:
    """결론 스텝 작성 프롬프트를 생성한다.

    md_body에서 Markdown 테이블과 Base64 이미지를 제거한 내러티브만 사용하고,
    raw_data(쿼리 원본)를 compact 형식으로 추가한다.
    """
    # 스텝 내러티브만 추출 — 테이블·이미지 제거
    narrative = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', md_body)       # 이미지 제거
    narrative = re.sub(r'(\|[^\n]+\n)+', '', narrative)             # 마크다운 테이블 제거
    narrative = re.sub(r'\n{3,}', '\n\n', narrative).strip()

    # 쿼리 결과를 compact CSV 형식으로 변환
    data_block = ""
    if raw_data:
        parts = []
        for entry in raw_data:
            cols = entry["columns"]
            rows = entry["data"]
            lines = [f"[{entry['question']}]", ", ".join(cols)]
            for row in rows:
                lines.append(", ".join(str(row.get(c, "")) for c in cols))
            parts.append("\n".join(lines))
        data_block = "\n\n[쿼리 데이터]\n" + "\n\n".join(parts)

    base = (
        f"다음은 '{report_type}' 보고서의 분석 결과입니다.\n\n"
        f"[스텝 분석 내용]\n{narrative}"
        f"{data_block}\n\n"
        "위 분석을 바탕으로 **## 결론** 스텝을 Markdown으로 작성하세요.\n\n"
        "결론은 다음 항목을 포함하세요:\n"
        "1. 핵심 발견사항 — 분석에서 드러난 주요 패턴과 수치를 2~4개 항목으로 요약\n"
        "2. 종합 해석 — 발견사항들이 전체적으로 무엇을 의미하는지 2~3문장\n"
        "3. 향후 전망 — 데이터 추이를 근거로 한 간략한 전망 1~2문장\n"
    )

    if factor_context:
        share_text = factor_context.get("shapley_share_text", "")
        direction = factor_context.get("direction", "변화")
        delta_pct = abs(factor_context.get("total_delta_pct", 0.0)) * 100
        base += (
            f"4. 원인 종합 — Shapley 스크리닝 결과({share_text})와 본문 분석을 결합하여 "
            f"매출 {direction}({delta_pct:.1f}%)의 실질적 원인을 2~3문장으로 서술\n"
            "5. 데이터 기반 대응 방향 — 분석된 원인에 대해 데이터가 뒷받침하는 "
            "구체적 조치 방향을 2~3개 항목으로 제시 (추상적 경영 제언 금지)\n"
        )
    else:
        base += "불필요한 경영 제언이나 컨설팅 언어는 사용하지 마세요.\n"

    return base


class ReportAgent:
    """LangGraph StateGraph 기반 범용 보고서 생성기 — pr_d2chat MCPAgent 패턴 적용."""

    def __init__(
        self,
        connection_url: str | None = None,
        project_id: int | None = None,
        tenant_id: int | None = None,
        user_uid: str | None = None,
        account_uid: str | None = None,
        session_id: str | None = None,
    ) -> None:
        src = GenericSqlSource(connection_url)
        self._dialect: str = src._dialect
        self._user_uid = user_uid
        self._account_uid = account_uid
        self._session_id = session_id
        from d2insight.report.excel_registry import get_excel_server
        self._excel_server = get_excel_server()
        self.has_upload = bool(session_id and self._excel_server.has_datasets(session_id))
        # service_code="In"이라 self._models는 문자열이 아니라
        # {"fast":.., "balanced":.., "quality":..} dict다 — 세션 안에서 등급을 바꿔가며
        # 쓸 때마다(_quick_chat) 구독/키 조회를 반복하지 않도록 한 번에 다 받아둔다.
        self._models, self._api_key, self._vendor, _is_customeraikey, _account_uid = get_llm_info(
            project_id=project_id, tenant_id=tenant_id,
            user_uid=user_uid, account_uid=account_uid, service_code="In",
        )
        # token_tracker.add()가 사용하는 공유 log_ctx에 반영 — 이후 이 요청 내 모든 LLM 로그에 적용됨
        _ctx = token_tracker.get_log_ctx()
        if _ctx is not None:
            _ctx["is_customeraikey"] = _is_customeraikey
            if not _ctx.get("account_uid"):
                _ctx["account_uid"] = _account_uid
        self._model_id = self._models["balanced"]
        self._llm = build_langchain_llm(self._vendor, self._api_key, self._model_id)

        self._tools = list(ALL_TOOLS) + [finalize_step]
        if self.has_upload:
            from d2insight.report.tools.excel_query_tool import create_excel_query_tool
            self._tools = [t for t in self._tools if t.name != "execute_query"]
            self._tools.append(create_excel_query_tool(self._session_id, self._llm))

        self._llm_with_tools = self._llm.bind_tools(self._tools)
        self._graph = self._create_graph()

    def _quick_chat(
        self,
        prompt: str,
        *,
        grade: str = "balanced",
        system: str | None = None,
        max_tokens: int = 8192,
        label: str = "",
        stepnm: str = "",
        call_type: str = "",
    ) -> str:
        """단발성 LLM 호출 — bind_tools 없는 일반 텍스트 응답."""
        model_id = self._models[grade]
        llm = build_langchain_llm(self._vendor, self._api_key, model_id)
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))

        _start = datetime.now()
        resp = llm.invoke(messages)
        _end = datetime.now()

        um = getattr(resp, "usage_metadata", None) or {}
        input_t = um.get("input_tokens", 0)
        output_t = um.get("output_tokens", 0)
        token_tracker.add(
            input_t, output_t,
            grade=grade, label=label, is_report=True,
            stepnm=stepnm, call_type=call_type,
            model_id=model_id, provider=self._vendor.lower(),
            startdts=_start, enddts=_end,
        )

        content = resp.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
                if not isinstance(block, dict) or block.get("type") == "text"
            )
        return str(content)

    def _create_graph(self):
        """pr_d2chat MCPAgent._create_agent 패턴 — call_model ↔ tools 루프."""
        tool_node = ToolNode(self._tools)

        def call_model(state: MessagesState):
            _start = datetime.now()
            response = self._llm_with_tools.invoke(state["messages"])
            _end = datetime.now()
            um = getattr(response, "usage_metadata", None) or {}
            input_t = um.get("input_tokens", 0)
            output_t = um.get("output_tokens", 0)
            if not input_t and not output_t:
                rm = getattr(response, "response_metadata", {})
                ru = rm.get("usage", {}) or rm.get("token_usage", {})
                input_t = ru.get("input_tokens", 0) or ru.get("prompt_tokens", 0)
                output_t = ru.get("output_tokens", 0) or ru.get("completion_tokens", 0)
            if hasattr(response, "tool_calls") and response.tool_calls:
                _call_type = "툴 호출"
            else:
                _text = ""
                if isinstance(response.content, str):
                    _text = response.content
                elif isinstance(response.content, list):
                    for _b in response.content:
                        if isinstance(_b, dict) and _b.get("type") == "text":
                            _text += _b.get("text", "")
                if "![" in _text:
                    _call_type = "항목 작성(차트)"
                elif re.search(r'\|[-| ]+\|', _text):
                    _call_type = "항목 작성(테이블)"
                else:
                    _call_type = "항목 작성(문장)"
            token_tracker.add(
                input_t, output_t,
                grade="balanced",
                label="보고서 에이전트",
                is_report=True,
                stepnm="본문",
                steptitle=token_tracker.get_current_step(),
                call_type=_call_type,
                model_id=self._model_id,
                provider=self._vendor.lower(),
                startdts=_start,
                enddts=_end,
            )
            return {"messages": [response]}

        def should_continue(state: MessagesState):
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return END

        graph = StateGraph(MessagesState)
        graph.add_node("call_model", call_model)
        graph.add_node("tools", tool_node)
        graph.add_edge(START, "call_model")
        graph.add_conditional_edges("call_model", should_continue, ["tools", END])
        graph.add_edge("tools", "call_model")
        return graph.compile()

    def _plan_steps(
        self,
        report_type: str,
        user_request: str | None,
        factor_context: dict | None,
        date_range: tuple[str, str],
        meta: dict | None = None,
        sales_datasets=None,
    ) -> list[str]:
        """스텝 목록을 반환한다.

        판매분석 + sales_datasets가 있으면 보고서작성방안 방침 고정 스텝 사용.
        그 외에는 Haiku 1회 호출로 스텝 결정.
        """
        # 판매분석이고 구조화 DataSet이 있으면 방침 기반 고정 스텝 사용
        if report_type == "판매분석" and sales_datasets is not None:
            ds = sales_datasets
            steps = ["§11. 매출 증감 총평"]
            if not ds.byitem_summary_df.empty:
                steps += ["§12-A. 차원 영향도 분석", "§12-B. 차원 내 기여도 분석"]
            bridge = ds.sales_bridge or {}
            if bridge.get("qty_effect") or bridge.get("asp_effect") or bridge.get("discount_effect"):
                steps.append("§13. Sales Bridge 분해")
            if not ds.byitem_df.empty:
                steps += ["§14. 이상징후 분석", "§15. Drill Down / Cross Analysis"]
            steps.append("최종. 경영 인사이트")
            # print(f"[plan_steps] 방침 고정 스텝: {steps}")
            return steps

        # 그 외 보고서 유형: Haiku로 스텝 결정
        factor_hint = ""
        if factor_context:
            share_text = factor_context.get("shapley_share_text", "")
            direction = factor_context.get("direction", "변화")
            delta_pct = abs(factor_context.get("total_delta_pct", 0.0)) * 100
            factor_hint = f"\n매출 {direction} {delta_pct:.1f}%, 주요 차원: {share_text}"

        meta_hint = ""
        if meta:
            view_lines = [
                f"- {vname}: {str(vinfo.get('description', ''))[:80]}"
                for vname, vinfo in meta.items()
                if isinstance(vinfo, dict)
            ]
            if view_lines:
                meta_hint = "\n\n사용 가능한 데이터 뷰:\n" + "\n".join(view_lines[:20])

        prompt = (
            f"'{report_type}' 보고서의 스텝 목록을 JSON 배열로만 반환하세요.\n"
            f"분석 기간: {date_range[0]} ~ {date_range[1]}{factor_hint}\n"
            f"사용자 요청: {user_request or report_type + ' 보고서'}"
            f"{meta_hint}\n\n"
            "위 데이터 뷰에 실제 존재하는 데이터 기반으로 스텝을 계획하세요.\n"
            "스텝은 4~6개. 형식: [\"스텝명1\", \"스텝명2\", ...]\n"
            "JSON 배열 외 다른 텍스트는 절대 출력하지 마세요."
        )

        raw = self._quick_chat(
            prompt,
            grade="balanced",
            max_tokens=200,
            label="스텝 계획",
            stepnm="스텝 계획",
            call_type="계획",
        )

        try:
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                steps = json.loads(match.group())
                if isinstance(steps, list) and len(steps) >= 2:
                    return [str(s) for s in steps]
        except Exception:
            pass

        defaults: dict[str, list[str]] = {
            "판매분석": ["분석 개요", "월별 매출 추이", "채널별 분석", "제품대분류 분석", "전월 대비 증감"],
            "경영분석": ["분석 개요", "핵심 지표", "부문별 현황", "전월 비교"],
        }
        return defaults.get(report_type, ["분석 개요", "핵심 지표", "세부 분석", "종합"])

    def _run_step(
        self, system: str, step_name: str, date_range: tuple[str, str],
    ) -> tuple[str, dict, list[dict]]:
        """스텝 하나를 독립 LangGraph 컨텍스트에서 실행한다.

        Worker 스레드에서 호출될 수 있으므로 token_tracker를 스레드-로컬로 초기화한다.
        Returns: (markdown_text, token_data, tool_calls) — tool_calls는 이 스텝에서 실제로
        호출된 도구명/파라미터 목록이다(우측 옵션 패널이 "이 스텝은 어떤 툴/조건으로
        만들어졌는지" 보여주는 데 쓴다).
        """
        token_tracker.reset()
        token_tracker.set_current_step(step_name)
        from d2insight.report.sql_generator import set_llm_context
        set_llm_context(self._vendor, self._api_key, models=self._models,
                        user_uid=self._user_uid, account_uid=self._account_uid)

        start, end = date_range
        step_msg = (
            f"**{step_name}** 스텝 하나만 작성하세요.\n\n"
            f"분석 기간: {start} ~ {end}\n\n"
            "execute_query → create_chart(필요 시) → finalize_step 순서로 진행하세요.\n"
            "이 스텝만 완성하면 finalize_step을 호출하고 바로 종료하세요. "
            "다른 스텝은 작성하지 마세요."
        )

        result = self._graph.invoke(
            {
                "messages": [
                    SystemMessage(content=[{
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }]),
                    HumanMessage(content=step_msg),
                ]
            },
            config={"recursion_limit": 50},
        )

        tool_calls: list[dict] = []
        finalized_body: str | None = None
        for msg in result["messages"]:
            if isinstance(msg, AIMessage):
                for call in getattr(msg, "tool_calls", None) or []:
                    if call.get("name") == "finalize_step":
                        # 실제 분석 툴이 아니라 종료 신호일 뿐이므로 옵션 패널의 툴
                        # 목록에는 넣지 않는다(전체 본문이 params로 들어가 UI만 지저분해짐).
                        body = (call.get("args") or {}).get("body_markdown")
                        if body and body.strip():
                            finalized_body = body.strip()
                        continue
                    tool_calls.append({"tool": call.get("name"), "params": call.get("args")})

        if finalized_body is not None:
            # 정상 경로 — finalize_step 인자만 채택, 그 밖의 모든 텍스트는 버린다.
            md = finalized_body
        else:
            # 폴백 — 모델이 finalize_step을 호출하지 않고 예전처럼 자유 텍스트로
            # 끝낸 경우에만 쓰인다. 안전망으로 기존 패턴 필터를 그대로 적용한다.
            parts: list[str] = []
            for msg in result["messages"]:
                if isinstance(msg, AIMessage):
                    content = msg.content
                    if isinstance(content, str) and content.strip():
                        cleaned = _strip_leaked_narration(content)
                        if cleaned:
                            parts.append(cleaned)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    cleaned = _strip_leaked_narration(text)
                                    if cleaned:
                                        parts.append(cleaned)
            md = "\n\n".join(p for p in parts if p.strip())

        return md, token_tracker.get(), tool_calls

    def _check_upload_feasibility(
        self, report_type: str, user_request: str | None, date_range: tuple[str, str],
    ) -> str | None:
        """스텝 계획·병렬 스텝 생성(다수 LLM 호출)에 들어가기 전에, 요청 주제/기간에 맞는
        데이터가 실제로 있는지 업로드된 데이터셋에 가벼운 확인 쿼리를 1회 날려본다.

        요청 기간을 별도로 저장/검증하지 않고, 그 기간을 확인 질문 문장에 그대로 넣어
        excel_server에 실제 쿼리(분류 + pandas 코드 실행)를 실행시켜 결과로만 판단한다.
        데이터가 없거나(no_data) 주제가 안 맞으면(not_answerable) 스텝 생성을 아예 시작하지
        않고 사유를 반환 — 없으면(None) 정상적으로 보고서 생성을 진행한다.
        """
        from d2insight.report.classifier import classify_question_and_table

        start, end = date_range
        probe_question = (
            f"{user_request or report_type}. "
            f"{start} ~ {end} 기간에 해당하는 원본 데이터를 최대 3건만 그대로 보여줘 "
            f"(집계하지 말고 필터링만 하세요)."
        )
        try:
            probe = self._excel_server.execute_natural_language_query(
                question=probe_question,
                session_id=self._session_id,
                llm=self._llm,
                classifier_fn=classify_question_and_table,
                log_ctx=token_tracker.get_log_ctx(),
            )
        except Exception:
            return None  # 확인 자체가 실패하면 안전하게 정상 흐름으로 진행(오탐으로 막지 않음)

        status = probe.get("status")
        if status == "not_answerable":
            return probe.get("message") or "등록된 데이터셋이 요청하신 내용과 맞지 않습니다."
        if status in ("no_data", "error", "no_dataset"):
            detail = probe.get("message") or ""
            return f"{start} ~ {end} 기간에 해당하는 데이터를 찾지 못했습니다." + (f" ({detail})" if detail else "")
        return None

    def generate(
        self,
        report_type: str,
        target_month: str,
        months_back: int = 1,
        user_request: str | None = None,
        factor_context: dict | None = None,
        sales_datasets=None,
        step_plan_override: list[str] | None = None,
    ) -> dict:
        """보고서를 생성하고 {md_text, md_filename, report_type}을 반환한다.

        Phase 0: 스텝 계획 (Haiku 1회 호출)
        Phase 1: 스텝별 독립 실행 (스텝마다 새 LangGraph 컨텍스트)
        Phase 2: 결론 생성 (quality 1회 호출, 전체 본문 전달)

        step_plan_override: 옵션 패널 "이대로 작성"에서 확정된 시나리오 스텝 title 목록.
        이 값이 주어지면 Phase 0의 LLM 스텝 계획을 건너뛰고 이 title들을 그대로 스텝 계획으로 쓴다.
        """
        config_entry = get_config(report_type)
        if self.has_upload:
            meta = self._excel_server.get_session_datasets(self._session_id)
        else:
            meta_all = meta_loader.all_metadata()
            view_hints: list[str] = config_entry.get("view_hints", [])
            if view_hints:
                meta = {v: meta_all[v] for v in view_hints if v in meta_all} or meta_all
            else:
                meta = meta_all

        months_back = config_entry.get("months_back", months_back)
        date_range = _date_range(target_month, months_back)
        compare_range = _compare_range(target_month, months_back)

        if self.has_upload:
            skip_reason = self._check_upload_feasibility(report_type, user_request, date_range)
            if skip_reason:
                return {
                    "md_text": "",
                    "md_filename": "",
                    "report_type": report_type,
                    "skipped_reason": skip_reason,
                    "applied_steps": [],
                }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_type = config_entry.get("folder_en") or report_type.replace("/", "_").replace("\\", "_")

        # 스텝 실행용 시스템 프롬프트 — 계획 지시 제외 (Phase 0에서 별도 처리)
        step_system = _build_system_prompt(
            report_type, meta, self._dialect, date_range, factor_context,
            include_plan_instruction=False,
            sales_datasets=sales_datasets,
            has_upload=self.has_upload,
            compare_range=compare_range,
        )

        _chart_store.reset()
        _data_store.reset()

        # Phase 0: 스텝 계획 수립 — override가 있으면 LLM 계획을 건너뛴다.
        if step_plan_override:
            step_plan = list(step_plan_override)
        else:
            step_plan = self._plan_steps(
                report_type, user_request, factor_context, date_range, meta,
                sales_datasets=sales_datasets,
            )

        # Phase 1: 스텝별 병렬 실행 (마지막 항목 = 결론은 모든 스텝 완료 후 순차 실행)
        parallel_steps = step_plan[:-1]
        conclusion_step = step_plan[-1]

        step_results: dict[int, str] = {}
        step_tool_calls: dict[int, list[dict]] = {}
        _t0 = datetime.now()
        # print(f"[parallel] 병렬 스텝 {len(parallel_steps)}개 시작 (max_workers={REPORT_MAX_WORKERS})")

        with ThreadPoolExecutor(max_workers=REPORT_MAX_WORKERS) as executor:
            future_to_idx = {
                executor.submit(self._run_step, step_system, name, date_range): idx
                for idx, name in enumerate(parallel_steps)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                name = parallel_steps[idx]
                try:
                    md, token_data, tool_calls = future.result()
                    step_results[idx] = md
                    step_tool_calls[idx] = tool_calls
                    token_tracker.merge_calls(token_data["calls"])
                    # print(f"[parallel] 완료: {name} ({(datetime.now() - _t0).seconds}s)")
                except Exception as e:
                    # print(f"[parallel] 실패: {name} — {e}")
                    step_results[idx] = ""
                    step_tool_calls[idx] = []

        # 계획 순서 재배열
        step_parts = [
            step_results[i]
            for i in range(len(parallel_steps))
            if step_results.get(i, "").strip()
        ]
        applied_steps = [
            {"step": parallel_steps[i], "tools": step_tool_calls.get(i, [])}
            for i in range(len(parallel_steps))
            if step_results.get(i, "").strip()
        ]

        # 결론 항목: 전체 본문 완성 후 순차 실행
        # print(f"[parallel] 결론 스텝 시작: {conclusion_step}")
        conclusion_md, conclusion_token_data, conclusion_tool_calls = self._run_step(
            step_system, conclusion_step, date_range
        )
        token_tracker.merge_calls(conclusion_token_data["calls"])
        token_tracker.set_current_step("")
        if conclusion_md.strip():
            step_parts.append(conclusion_md)
            applied_steps.append({"step": conclusion_step, "tools": conclusion_tool_calls})
        # print(f"[parallel] 전체 완료 ({(datetime.now() - _t0).seconds}s)")

        md_body = "\n\n".join(step_parts)

        # CHART_PLACEHOLDER_N → 실제 base64 data URI 치환
        for key, data_uri in _chart_store.get_all().items():
            md_body = md_body.replace(f"]({key})", f"]({data_uri})")

        # 보고서 제목 헤더
        year, month = target_month.split("-")
        title_header = (
            f"# {year}년 {int(month)}월 {report_type} 보고서\n\n"
            f"**분석 기간:** {date_range[0]} ~ {date_range[1]}\n\n"
            f"---\n\n"
        )
        md_body = title_header + md_body

        # Phase 2: 결론 생성 (quality 1회 — 내러티브 + 쿼리 원본 데이터 전달)
        stored_data = _data_store.get_all()
        conclusion_prompt = _build_conclusion_prompt(report_type, md_body, factor_context, stored_data)
        conclusion_text = self._quick_chat(
            conclusion_prompt,
            grade="quality",
            label="결론 작성",
            stepnm="종합",
            call_type="결론",
            system=(
                f"당신은 '{report_type}' 보고서의 결론을 작성하는 데이터 분석 전문가입니다. "
                "분석 결과에 근거한 핵심 인사이트를 명확하고 간결하게 작성하세요."
            ),
            max_tokens=2048,
        )
        conclusion_text = _strip_leaked_narration(conclusion_text)

        md_text = md_body + "\n\n" + conclusion_text
        md_filename = f"{safe_type}_{target_month}_{timestamp}.md"

        return {
            "md_text": md_text,
            "md_filename": md_filename,
            "report_type": report_type,
            "applied_steps": applied_steps,
        }
