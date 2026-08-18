"""data_validation 모듈 — 분석 전 데이터 신뢰도 점검 (§1 검증).

분석 결과를 믿기 전에 **입력 데이터 자체의 오류 패턴**을 먼저 걸러낸다. 급락 후 급상승(누락 후
합산), 전월 대비 급증(중복 입력), 역대 최고치·2위 대비 과다(단위 오류), 합계는 비슷한데 개별
항목만 크게 이동(항목 간 이동) 등을 감지한다.

패턴 판정 로직은 `src/pipeline/validator.run_data_validation`에 있고, 이 모듈은 **스키마 역할로
컬럼을 찾아** 넘긴다(period→기간, amount→금액, item→개별 항목 차원). 컬럼명을 코드에 박지 않으므로
구매·생산 등 다른 도메인에서도 그대로 동작한다(§7.3).

다월(전전월·전월·당월) 비교가 필요하므로 history_dataset(월별 패널)에 의존한다. 이력이 없으면
"이상 없음"으로 위장하지 않고 명시적으로 실패한다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.schema import ROLE_AMOUNT, ROLE_ITEM, ROLE_PERIOD, get_schema
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.validator import run_data_validation


def _issues_table(issues: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({
        "심각도": [i.get("severity", "") for i in issues],
        "오류 패턴": [i.get("description", "") for i in issues],
        "근거": [i.get("detail", "") for i in issues],
    })


def run(ctx, params, tools) -> ModuleResult:
    history = ctx.get("history_dataset")
    if history is None or getattr(history, "empty", True):
        # 다월 비교가 불가능하다. "이상 없음"으로 조용히 넘기면 검증을 안 한 것과 같다.
        return ModuleResult(
            status="failed",
            error="이력(history_dataset)이 없어 데이터 검증(다월 비교)을 할 수 없습니다.",
        )

    target_month = ctx.meta.get("target_month")
    if not target_month:
        return ModuleResult(status="failed", error="ctx.meta에 target_month가 없습니다.")

    schema = get_schema(ctx)
    period_col = schema.column(ROLE_PERIOD)
    amount_col = schema.column(ROLE_AMOUNT) or schema.key_measure
    item_col = schema.column(ROLE_ITEM)

    if not period_col or period_col not in history.columns:
        return ModuleResult(
            status="failed",
            error="이력에 기간(period) 역할 컬럼이 없어 다월 비교를 할 수 없습니다. "
                  "데이터소스 정의에 period 역할을 선언하세요.",
        )
    if amount_col not in history.columns:
        return ModuleResult(
            status="failed", error=f"이력에 금액 컬럼 '{amount_col}'이 없습니다.",
        )

    # 항목 간 이동 패턴에 쓸 개별 항목 차원 — item 역할만 사용(채널 등 무역할 차원은 배제).
    item_dims = [item_col] if item_col and item_col in history.columns else []

    result = run_data_validation(
        history, target_month,
        period_col=period_col, amount_col=amount_col,
        amount_label=schema.logical_name(amount_col),   # 이슈 설명 표시명(구매="구매액") — 도메인 어휘 차단
        item_dims=item_dims,
    )

    issues = result.get("issues", [])
    count = result.get("issue_count", len(issues))
    dim_note = "" if item_dims else " (항목 차원 없음 — '항목 간 이동' 패턴은 건너뜀)"

    if not issues:
        summary = f"데이터 검증 — 오류 패턴 없음. 분석 결과를 신뢰할 수 있음.{dim_note}"
        return ModuleResult(
            outputs={"validation_result": result},
            render=Render(summary=summary,
                          key_value={"검증 결과": "이상 없음", "감지 이슈": 0}),
        )

    patterns = ", ".join(i.get("description", "") for i in issues)
    summary = f"데이터 검증 — 오류 의심 {count}건: {patterns}. 해석 시 주의 필요.{dim_note}"
    return ModuleResult(
        outputs={"validation_result": result},
        render=Render(
            summary=summary,
            table=_issues_table(issues),
            key_value={"검증 결과": "주의", "감지 이슈": count},
        ),
    )
