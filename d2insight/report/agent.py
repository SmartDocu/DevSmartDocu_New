"""ReportAgent — LangGraph StateGraph 기반 범용 보고서 생성기.

pr_d2chat MCPAgent 패턴 적용:
  - LangGraph StateGraph (call_model → tools → call_model 루프 자동 관리)
  - ChatAnthropic + bind_tools
  - @tool 데코레이터 기반 도구
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from backend.app.config import settings
from d2insight import token_tracker
from d2insight.config import ANTHROPIC_MODELS
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


def _date_range(target_month: str, months_back: int) -> tuple[str, str]:
    end_dt = datetime.strptime(target_month, "%Y-%m")
    end_dt = end_dt + relativedelta(months=1) - relativedelta(days=1)
    start_dt = datetime.strptime(target_month, "%Y-%m") - relativedelta(months=months_back - 1)
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


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


def _build_factor_section(factor_context: dict) -> str:
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
            "- 각 조합마다 별도 섹션을 구성하고 쿼리 → 차트/테이블 → 설명 순서로 작성하세요.",
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

    # 보고서 섹션 구조 지시
    lines += [
        "## 보고서 작성 섹션 구조 (방침)",
        "위 데이터를 기반으로 아래 순서로 보고서를 작성하세요.",
        "데이터가 없거나 해당 없는 섹션은 생략합니다.",
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
        "  데이터(수량·할인 컬럼)가 없으면 이 섹션은 생략.",
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
) -> str:
    meta_text = json.dumps(meta, ensure_ascii=False, indent=2)
    if len(meta_text) > _MAX_META_CHARS:
        meta_text = json.dumps(_condense_meta(meta), ensure_ascii=False, indent=2)
    if len(meta_text) > _MAX_META_CHARS:
        meta_text = meta_text[:_MAX_META_CHARS] + "\n...(메타데이터 일부 생략)"
    sql_rules = _sql_rules(dialect)
    start, end = date_range

    factor_section = ""
    if factor_context:
        factor_section = "\n\n" + _build_factor_section(factor_context)

    dataset_section = ""
    if sales_datasets is not None and report_type == "판매분석":
        dataset_section = _build_sales_dataset_context(sales_datasets)

    sales_section_plan = ""
    if include_plan_instruction and report_type == "판매분석":
        sales_section_plan = (
            "\n\n## 판매분석 섹션 계획 지시\n"
            "보고서 본문 작성 전, `<plan>` 태그 안에 섹션 목록을 작성하여 이 달 데이터에 맞는 구성을 결정하세요.\n"
            "`<plan>...</plan>` 블록은 최종 보고서에서 자동으로 제거됩니다.\n\n"
            "예시 형식:\n"
            "<plan>\n"
            "1. 분석 개요\n"
            "2. 월별 매출 추이\n"
            "3. 지역별 매출 심층 분석\n"
            "4. 전월 대비 증감 분석\n"
            "</plan>\n\n"
            "섹션 계획 기준:\n"
            "- **사전 요인 스크리닝 결과**의 기여도 높은 차원을 중심으로 섹션 구성\n"
            "- 분석 개요·월별 매출 추이·Primary Driver 차원 분석·전월 대비 증감은 반드시 포함\n"
            "- 기여도 낮은 차원(noise 판정)은 별도 섹션 없이 간략 언급으로 처리\n"
            "- 데이터에서 유의미한 패턴 발견 시 교차분석 등 섹션을 자율적으로 추가\n\n"
            "`</plan>` 이후 **계획한 모든 섹션을 완성하기 전에는 절대 종료하지 마세요.**\n"
            "각 섹션은 execute_query → create_chart(필요 시) → 설명 텍스트 순서로 작성하세요."
        )

    return f"""당신은 '{report_type}' 보고서를 작성하는 데이터 분석 전문가입니다.

## 분석 기간
{start} ~ {end}

## 사용 가능한 데이터 (메타정보)
{meta_text}

## SQL 규칙
{sql_rules}{factor_section}{dataset_section}{sales_section_plan}

## 보고서 작성 절차
1. 사용자의 요청을 정확히 파악하고 그에 맞는 보고서 구조(섹션 목차)를 계획하세요.
   - 판매분석의 경우 "판매분석 섹션 계획 지시"에 따라 <plan> 태그로 먼저 계획하고, 계획한 모든 섹션을 순서대로 완성하세요.
   - 사용자가 특정 분석 방법을 요청하면 반드시 해당 방법을 사용하세요.
2. 각 섹션에 필요한 데이터를 execute_query 툴로 조회하세요.
   - SQL을 직접 작성하지 마세요. question에 자연어로 분석 목적을 설명하면 내부에서 SQL이 자동 생성됩니다.
   - table_name에 메타정보에서 확인한 뷰 이름을 반드시 지정하세요. 생략 금지.
   - question에 분석 기간({start} ~ {end})을 반드시 포함하세요.
   - 반드시 집계 데이터를 요청하세요: "~별 건수/합계/평균" 형태로 질문하세요.
   - 조회 결과가 비어 있거나(row_count=0) CANNOT_ANSWER이면 해당 섹션을 작성하지 말고 바로 종료하세요.
   - 현재 작성 중인 '{report_type}' 보고서와 무관한 데이터 뷰는 절대 사용하지 마세요.
3. 필요시 run_stats / run_trend / run_outlier 툴로 추가 분석하세요.
4. 데이터가 있는 모든 주요 섹션에서 create_chart 툴로 시각화하세요. (의무)
   - create_chart 호출 후 tool result의 markdown_tag 값을 반드시 해당 위치의 텍스트에 삽입하세요.
   - 예: tool result = {{"markdown_tag": "![오류 추이](data:image/png;base64,...)"}}
          → 텍스트에 그대로 삽입: ![오류 추이](data:image/png;base64,...)
5. 각 섹션은 반드시 다음 순서로 작성하세요.
   a) 섹션 도입 문장 (이 섹션에서 무엇을 분석하는지 1~2문장)
   b) 데이터 테이블 또는 차트 (markdown_tag 삽입)
   c) 설명 텍스트 — **이 부분이 핵심입니다**:
      - 주요 수치를 구체적으로 언급하세요. (예: "X가 Y% 증가했으며, Z는 최고치를 기록했다.")
      - 눈에 띄는 패턴·증감·이상값을 사실에 근거해 서술하세요.
      - 단순 수치 나열에 그치지 말고, 수치가 의미하는 바에 대해 간략한 의견을 덧붙이세요.
   ※ 차트나 테이블만 단독으로 삽입하고 설명 없이 다음 섹션으로 넘어가는 것은 절대 금지입니다.
6. 결론·예측·시사점 섹션은 작성하지 마세요. 해당 섹션은 별도로 추가됩니다.

## 출력 형식
- Markdown (## 섹션, ### 소섹션 사용)
- 데이터 테이블: Markdown 표 형식
- 차트: create_chart 툴 호출 후 반환된 markdown_tag를 텍스트에 직접 삽입
- 섹션을 완성하는 즉시 텍스트를 출력하세요

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

## 절대 금지
- 툴 호출 전후에 진행 안내 문구를 출력하지 마세요.
  ("데이터를 조회하겠습니다", "분석을 시작합니다", "차트를 생성하겠습니다" 등 일체 금지)
- 텍스트는 오직 보고서 섹션 내용만 출력하세요."""


def _build_conclusion_prompt(
    report_type: str,
    md_body: str,
    factor_context: dict | None,
    raw_data: list[dict] | None = None,
) -> str:
    """결론 섹션 작성 프롬프트를 생성한다.

    md_body에서 Markdown 테이블과 Base64 이미지를 제거한 내러티브만 사용하고,
    raw_data(쿼리 원본)를 compact 형식으로 추가한다.
    """
    # 섹션 내러티브만 추출 — 테이블·이미지 제거
    narrative = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', md_body)       # 이미지 제거
    narrative = re.sub(r'(\|[^\n]+\n)+', '', narrative)             # 마크다운 테이블 제거
    narrative = re.sub(r'\n{3,}', '\n\n', narrative).strip()

    # 쿼리 결과를 compact CSV 형식으로 변환
    data_section = ""
    if raw_data:
        parts = []
        for entry in raw_data:
            cols = entry["columns"]
            rows = entry["data"]
            lines = [f"[{entry['question']}]", ", ".join(cols)]
            for row in rows:
                lines.append(", ".join(str(row.get(c, "")) for c in cols))
            parts.append("\n".join(lines))
        data_section = "\n\n[쿼리 데이터]\n" + "\n\n".join(parts)

    base = (
        f"다음은 '{report_type}' 보고서의 분석 결과입니다.\n\n"
        f"[섹션 분석 내용]\n{narrative}"
        f"{data_section}\n\n"
        "위 분석을 바탕으로 **## 결론** 섹션을 Markdown으로 작성하세요.\n\n"
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

    def __init__(self, connection_url: str | None = None) -> None:
        src = GenericSqlSource(connection_url)
        self._dialect: str = src._dialect
        self._model_id = ANTHROPIC_MODELS["balanced"]
        self._llm = ChatAnthropic(
            model=self._model_id,
            max_tokens=8192,
            api_key=settings.CLAUDE_API_KEY,
            model_kwargs={"extra_headers": {"anthropic-beta": "prompt-caching-2024-07-31"}},
        )
        self._llm_with_tools = self._llm.bind_tools(ALL_TOOLS)
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
        model_id = ANTHROPIC_MODELS[grade]
        llm = ChatAnthropic(model=model_id, max_tokens=max_tokens, api_key=settings.CLAUDE_API_KEY)
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
            model_id=model_id, provider="anthropic",
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
        tool_node = ToolNode(ALL_TOOLS)

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
                steptitle=token_tracker.get_current_section(),
                call_type=_call_type,
                model_id=self._model_id,
                provider="anthropic",
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

    def _plan_sections(
        self,
        report_type: str,
        user_request: str | None,
        factor_context: dict | None,
        date_range: tuple[str, str],
        meta: dict | None = None,
        sales_datasets=None,
    ) -> list[str]:
        """섹션 목록을 반환한다.

        판매분석 + sales_datasets가 있으면 보고서작성방안 방침 고정 섹션 사용.
        그 외에는 Haiku 1회 호출로 섹션 결정.
        """
        # 판매분석이고 구조화 DataSet이 있으면 방침 기반 고정 섹션 사용
        if report_type == "판매분석" and sales_datasets is not None:
            ds = sales_datasets
            sections = ["§11. 매출 증감 총평"]
            if not ds.byitem_summary_df.empty:
                sections += ["§12-A. 차원 영향도 분석", "§12-B. 차원 내 기여도 분석"]
            bridge = ds.sales_bridge or {}
            if bridge.get("qty_effect") or bridge.get("asp_effect") or bridge.get("discount_effect"):
                sections.append("§13. Sales Bridge 분해")
            if not ds.byitem_df.empty:
                sections += ["§14. 이상징후 분석", "§15. Drill Down / Cross Analysis"]
            sections.append("최종. 경영 인사이트")
            print(f"[plan_sections] 방침 고정 섹션: {sections}")
            return sections

        # 그 외 보고서 유형: Haiku로 섹션 결정
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
            f"'{report_type}' 보고서의 섹션 목록을 JSON 배열로만 반환하세요.\n"
            f"분석 기간: {date_range[0]} ~ {date_range[1]}{factor_hint}\n"
            f"사용자 요청: {user_request or report_type + ' 보고서'}"
            f"{meta_hint}\n\n"
            "위 데이터 뷰에 실제 존재하는 데이터 기반으로 섹션을 계획하세요.\n"
            "섹션은 4~6개. 형식: [\"섹션명1\", \"섹션명2\", ...]\n"
            "JSON 배열 외 다른 텍스트는 절대 출력하지 마세요."
        )

        raw = self._quick_chat(
            prompt,
            grade="balanced",
            max_tokens=200,
            label="섹션 계획",
            stepnm="섹션 계획",
            call_type="계획",
        )

        try:
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                sections = json.loads(match.group())
                if isinstance(sections, list) and len(sections) >= 2:
                    return [str(s) for s in sections]
        except Exception:
            pass

        defaults: dict[str, list[str]] = {
            "판매분석": ["분석 개요", "월별 매출 추이", "채널별 분석", "제품대분류 분석", "전월 대비 증감"],
            "경영분석": ["분석 개요", "핵심 지표", "부문별 현황", "전월 비교"],
        }
        return defaults.get(report_type, ["분석 개요", "핵심 지표", "세부 분석", "종합"])

    def _run_section(self, system: str, section_name: str, date_range: tuple[str, str]) -> str:
        """섹션 하나를 독립 LangGraph 컨텍스트에서 실행한다."""
        start, end = date_range
        section_msg = (
            f"**{section_name}** 섹션 하나만 작성하세요.\n\n"
            f"분석 기간: {start} ~ {end}\n\n"
            "execute_query → create_chart(필요 시) → 설명 텍스트 순서로 작성하세요.\n"
            "이 섹션만 완성하면 바로 종료하세요. 다른 섹션은 작성하지 마세요."
        )

        result = self._graph.invoke(
            {
                "messages": [
                    SystemMessage(content=[{
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }]),
                    HumanMessage(content=section_msg),
                ]
            },
            config={"recursion_limit": 50},
        )

        parts: list[str] = []
        for msg in result["messages"]:
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str) and content.strip():
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                parts.append(text)

        return "\n\n".join(p for p in parts if p.strip())

    def generate(
        self,
        report_type: str,
        target_month: str,
        months_back: int = 1,
        user_request: str | None = None,
        factor_context: dict | None = None,
        sales_datasets=None,
    ) -> dict:
        """보고서를 생성하고 {md_text, md_filename, report_type}을 반환한다.

        Phase 0: 섹션 계획 (Haiku 1회 호출)
        Phase 1: 섹션별 독립 실행 (섹션마다 새 LangGraph 컨텍스트)
        Phase 2: 결론 생성 (quality 1회 호출, 전체 본문 전달)
        """
        meta_all = meta_loader.all_metadata()
        config_entry = get_config(report_type)
        view_hints: list[str] = config_entry.get("view_hints", [])
        if view_hints:
            meta = {v: meta_all[v] for v in view_hints if v in meta_all} or meta_all
        else:
            meta = meta_all

        months_back = config_entry.get("months_back", months_back)
        date_range = _date_range(target_month, months_back)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_type = config_entry.get("folder_en") or report_type.replace("/", "_").replace("\\", "_")

        # 섹션 실행용 시스템 프롬프트 — 계획 지시 제외 (Phase 0에서 별도 처리)
        section_system = _build_system_prompt(
            report_type, meta, self._dialect, date_range, factor_context,
            include_plan_instruction=False,
            sales_datasets=sales_datasets,
        )

        _chart_store.reset()
        _data_store.reset()

        # Phase 0: 섹션 계획 수립 (Haiku 1회 — 경량, 메타정보 전달로 실제 데이터 기반 계획)
        section_plan = self._plan_sections(
            report_type, user_request, factor_context, date_range, meta,
            sales_datasets=sales_datasets,
        )

        # Phase 1: 섹션별 독립 실행 (섹션마다 새 LangGraph 컨텍스트, 누적 없음)
        section_parts: list[str] = []
        for section_name in section_plan:
            token_tracker.set_current_section(section_name)
            section_md = self._run_section(section_system, section_name, date_range)
            if section_md.strip():
                section_parts.append(section_md)
        token_tracker.set_current_section("")

        md_body = "\n\n".join(section_parts)

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

        md_text = md_body + "\n\n" + conclusion_text
        md_filename = f"{safe_type}_{target_month}_{timestamp}.md"

        return {
            "md_text": md_text,
            "md_filename": md_filename,
            "report_type": report_type,
        }
