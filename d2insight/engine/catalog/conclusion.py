"""결론 스텝 — 최종 경영 인사이트 (방침 §14, Step 7).

본문이 모두 끝난 뒤 **한 번** 실행되는 특수 스텝이다. 경영진이 3분 안에 핵심을 잡도록 쓴다.

두 가지 규율이 이 스텝의 생명이다.
  1. **재계산 금지(§6.2)** — 결론은 계산하지 않는다. 본문 모듈이 이미 산출한 공용 수치
     (total_variance, bridge_effects, count_summary, outlier_result …)와 각 모듈의 summary만 읽는다.
     결론이 숫자를 다시 구하면 본문과 어긋나고, 그 순간 보고서 전체의 신뢰가 무너진다.
  2. **생략을 감추지 않는다(§11 Step 2)** — 실패·생략된 분석이 있으면 결론에 사유와 함께 명시한다.
     "이상징후 없음"과 "이상징후를 못 봤음"은 완전히 다른 말이다.

LLM에는 **이미 계산된 사실표**만 넘기고, 새 수치를 만들지 말라고 못박는다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.format import korean_money_reference, table_to_markdown
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine._llm import chat

MAX_ROWS = 5          # 결론에 넘기는 표는 상위 몇 줄이면 충분하다

_BASE_RULES = """당신은 경영진 보고서의 결론을 쓰는 애널리스트다.
본문 분석이 모두 끝난 뒤, 아래 '확정된 사실'만 근거로 최종 경영 인사이트를 쓴다.

규칙
1. 주어진 사실표·요약에 있는 숫자만 인용한다. **새 수치·비율을 계산하거나 추정하지 않는다.**
   - 표에 없는 합계·비율을 만들지 마라. "두 항목 합계 -77,210", "전체 감소의 36%", "손실의 33%"처럼
     직접 더하거나 나눈 값은 금지다. 개별 값을 그대로 나열하라.
   - 단위 환산(만/억)은 기본적으로 하지 않는다. 쓰고 싶으면 반드시 [한글 단위 참고표]의 값을
     그대로 옮기고 직접 환산하지 마라(직접 계산하면 자릿수를 틀린 사례가 있다). 통화기호는
     임의로 붙이지 않는다.
2. **이상징후라고 부를 수 있는 것은 [이상징후] 표에 있는 항목뿐이다.** 다른 표(기여도·순위 등)의
   항목에 "이상 판정", "z-score 기준 이상" 같은 표현을 붙이지 마라. 감소가 크다는 사실만 말하라.
3. 인과를 단정하지 마라. 데이터가 보여주는 것과 추정을 구분해 쓴다(추정이면 추정이라고 밝힌다).
4. 자료가 없어 말할 수 없는 항목은 비워 두지 말고 "해당 분석 없음"이라고 명시한다.
5. 실패·생략된 분석이 있으면 반드시 "OO 분석은 [사유]로 생략됨"이라고 밝힌다. 감추지 않는다.
6. 경영진이 3분 안에 파악하도록 쓴다. 항목당 1~3문장. 불필요한 수식어를 쓰지 않는다.
7. '§' 기호나 모듈 이름(module_id)을 문장에 노출하지 않는다.
8. Action Item은 실행 가능한 행동으로 쓴다("모니터링한다" 같은 공허한 문장 금지).
9. **본문 요약 중 특정 차원·항목의 수치가 유난히 크거나(임팩트·Shapley 등), 별도로 "참고"·
   "주의"라고 표시된 캐치(예: 무의미한 비교, 척도 차이, 카디널리티 효과)가 있으면 절대 무시하지
   말고 핵심 성장/감소 요인이나 Action Item에 반드시 반영하라.** 표를 단순 나열하지 말고, 그
   신호가 "그래서 무엇을 봐야 하는가"로 이어지게 써라.
10. **종합 판단은 성장/감소 요인을 다시 나열하지 마라.** 그 요인들을 종합했을 때 이번 기간의
    변화가 어떤 **성격**인지(예: 물량이 이끈 건강한 성장인지, 신규 유입·할인에 기댄 성장인지,
    구조적 약화가 겉으로만 가려진 것인지) 하나의 평가로 판정하라. 근거 없이 낙관하거나
    비관하지 말고, 왜 그렇게 판단하는지 위 사실에 연결해 밝혀라.
11. **전망은 감시 리스트가 아니라 예측이다.** 이미 계산된 추이(trend)·생애주기·구성비
    변화 신호를 근거로 "다음 기간엔 이렇게 될 가능성이 있다"를 써라. 반드시 추정임을 명시하는
    완전한 문장으로 쓰고(예: "이 추세가 이어지면 다음 분기 매출은 추가로 감소할 가능성이 높다"),
    물결표(~)로 문장을 줄여 쓰지 마라 — 본문에 물결표가 두 번 나오면 마크다운이 그 사이를
    취소선으로 잘못 해석한다. 근거가 된 사실을 함께 인용하라. 새 수치를
    계산해 전망을 뒷받침하지 마라(규칙 1과 동일).
12. **맨 처음 "### 핵심 요약"은 숫자 나열이 아니라 3줄로 "무엇이 일어났고 무엇을 봐야 하는가"를
    압축한다.** 새 사실을 만들지 말고, 가장 중요한 3가지만 골라 짧게 쓴다.
    예: "전체 +2.8% 성장했으나 성장의 질은 카카오 한 채널에 편중. 브랜드 6곳은 감소 지속.
    카카오페이 단독 급락(-14.3%)은 다른 채널과 다른 패턴이라 별도 점검 필요."
13. **모니터링 권장 항목은 막연한 지켜보기가 아니라, 다음 기간에 확인할 구체적 질문으로
    쓴다.** "OO 추세를 지켜본다" 대신 "OO가 다음 기간에도 재현되는지 확인 필요"처럼, 검증
    가능한 질문 형태로 1~2개를 짚어라.
14. **"### 결론" 본문은 소제목으로 쪼개지 말고 하나로 이어지는 서술형 문단으로 쓴다.**
    핵심 수치·항목명은 **볼드**로 강조한다. 순서는 성장 요인(구체 항목·금액) → 감소 요인
    (구체 항목·금액) → 종합 판단(규칙 10) → 전망(규칙 11) → 다음 기간 확인할 점(규칙 13) →
    확대/방어해야 할 실행 방향(Action Item)이되, 각 앞에 소제목을 달지 말고 문단을 나눠
    자연스럽게 이어 써라.

출력은 "### 핵심 요약"과 "### 결론" 두 소제목만 그대로 쓴 마크다운 본문이다. 그 외 소제목을
새로 만들지 말고, 다른 텍스트를 덧붙이지 않는다."""


def _build_system(ctx) -> str:
    """결론 프롬프트 — 소제목은 "핵심 요약"/"결론" 둘뿐이고, 나머지는 규칙(§14)이 정한 순서로
    한 본문 안에서 문단으로 다룬다.
    """
    return _BASE_RULES


def _table_block(title: str, df, cols: list[str] | None = None) -> list[str]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    view = df[[c for c in (cols or df.columns) if c in df.columns]].head(MAX_ROWS)
    return [f"[{title}]", table_to_markdown(view) + korean_money_reference(view), ""]


def _grouped_table_block(title: str, df, group_col: str, cols: list[str] | None = None) -> list[str]:
    """`_table_block`과 달리 그룹(예: 이상 항목)별로 최소 1행씩은 살아남게 자른다.

    drilldown_result처럼 "이상 항목 하나당 하위 행 여러 개"가 이어 붙은 표를 그냥
    head(MAX_ROWS)로 자르면 맨 앞 그룹의 하위 행만 남고 나머지 그룹은 통째로 사라진다
    (2026-07-21 발견 — 결론이 실제로는 분석된 항목을 "해당 분석 없음"이라 잘못 씀).
    각 그룹의 대표 행(그 그룹 안에서 이미 가장 설명력 큰 첫 행)만 골라 그룹 수 기준으로 자른다.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or group_col not in df.columns:
        return []
    top_per_group = df.groupby(group_col, sort=False).head(1).head(MAX_ROWS)
    view = top_per_group[[c for c in (cols or df.columns) if c in top_per_group.columns]]
    return [f"[{title} — 이상 항목별 최대 설명 하위 그룹]",
           table_to_markdown(view) + korean_money_reference(view), ""]


def _facts(ctx) -> str:
    """이미 계산된 값만 모아 사실표를 만든다. 여기서 새로 계산하는 것은 없다."""
    lines: list[str] = []
    meta = ctx.meta or {}
    lines.append(f"[분석 대상] 기준 {meta.get('target_month', '미지정')}, "
                 f"비교 {meta.get('compare_type', '미지정')}")

    tv = ctx.get("total_variance")
    if tv:
        lines.append(
            f"[전체 증감] {tv['measure']} {tv['actual_value']:,.0f} "
            f"(비교 {tv['compare_value']:,.0f}, 증감 {tv['variance']:+,.0f}, "
            f"{tv['rate'] * 100:+.1f}%)"
        )
    lines.append("")

    lines.append("[본문 모듈 요약]")
    for s in ctx.all_summaries():
        lines.append(f"- {s['ref']}: {s['text']}")
    lines.append("")

    bridge = ctx.get("bridge_effects")
    if bridge:
        lines.append("[증감 분해 — 관점별 합계는 전체 증감액과 같다]")
        for view, effects in bridge.get("views", {}).items():
            parts = ", ".join(f"{k} {v:+,.0f}" for k, v in effects.items())
            lines.append(f"- {view}: {parts}")
        lines.append("")

    lines += _table_block("차원 영향도(상위)", ctx.get("dimension_stats"),
                          ["Dimension_Logical_Name", "Impact_Score", "HHI", "DVI", "Shapley_Value"])
    lines += _table_block("차원 내 기여도(상위)", ctx.get("within_contribution"),
                          ["Item_Name", "Variance", "Rate", "Contribution_Rate"])
    lines += _table_block("이상징후(금액순)", ctx.get("outlier_result"),
                          ["Dimension_Logical_Name", "Item_Name", "Variance", "Rate", "Reason", "Level"])
    lines += _grouped_table_block("교차 분석", ctx.get("drilldown_result"), "Outlier",
                                  ["Outlier", "Cross_Dimension", "Cross_Item", "Variance", "Share", "Factor"])
    lines += _table_block("신규·이탈 현황", ctx.get("count_summary"))

    notes = ctx.notes()
    if notes:
        lines.append("[실패·생략된 분석 — 결론에 반드시 명시할 것]")
        for n in notes:
            verb = "실패" if n["kind"] == "failed" else "생략"
            lines.append(f"- {n['ref']}: {n['reason']} → {verb}")
    else:
        lines.append("[실패·생략된 분석] 없음")

    return "\n".join(lines)


def _fallback(ctx) -> Render:
    """LLM 실패 시 — 결론을 통째로 날리지 않고 확정된 요약만 이어 붙인다(사실만, 해석 없음)."""
    summaries = ctx.all_summaries()
    body = ["### 본문 요약"] + [f"- {s['text']}" for s in summaries]
    notes = ctx.notes()
    if notes:
        body.append("")
        body.append("### 생략된 분석")
        for n in notes:
            body.append(f"- {n['ref']}: {n['reason']}")
    return Render(
        summary="결론 작성에 실패해 본문 요약으로 대체했습니다.",
        narrative="\n".join(body),
        layout=["narrative"],
    )


def build_conclusion(ctx, provider: str | None = None) -> Render:
    """결론 1회 작성 — quality 등급."""
    facts = _facts(ctx)
    try:
        text = chat(
            [{"role": "user", "content": facts}],
            grade="quality",
            system=_build_system(ctx),
            label="conclusion",
            is_report=True,
            call_type="conclusion",
            stepnm="결론",
            provider=provider,
        )
    except Exception as e:
        ctx.mark_failed("결론", f"{type(e).__name__}: {e} (본문 요약으로 대체)")
        return _fallback(ctx)

    body = (text or "").strip()
    if not body:
        ctx.mark_failed("결론", "LLM이 빈 응답을 반환 (본문 요약으로 대체)")
        return _fallback(ctx)

    tv = ctx.get("total_variance")
    summary = (
        f"{tv['measure']} {tv['variance']:+,.0f}({tv['rate'] * 100:+.1f}%)에 대한 최종 경영 인사이트."
        if tv else "최종 경영 인사이트."
    )
    return Render(summary=summary, narrative=body, layout=["narrative"])


def run(ctx, params, tools) -> ModuleResult:
    """module_id "conclusion"의 실행 함수 — 카탈로그의 다른 모듈과 같은 시그니처를 맞추기
    위한 얇은 래퍼일 뿐, 계산·프롬프트는 전부 build_conclusion 그대로다(2026-07-28,
    7단계 — 결론 스텝화). params/tools는 안 쓴다 — 결론은 본문이 이미 낸 값만 읽는다.

    이 모듈은 narrative를 스스로 채워서 반환한다(다른 모듈과 다른 유일한 예외) — runner.narrate가
    이미 채워진 narrative는 다시 쓰지 않고 건너뛴다.
    """
    render = build_conclusion(ctx, provider=(ctx.meta or {}).get("provider"))
    return ModuleResult(render=render)
