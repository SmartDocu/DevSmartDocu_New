"""data_validation 모듈 — 분석 전 데이터 신뢰도 점검 (§1 검증).

분석 결과를 믿기 전에 **입력 데이터 자체의 오류 패턴**을 먼저 걸러낸다. 급락 후 급상승(누락 후
합산), 전월 대비 급증(중복 입력), 역대 최고치·2위 대비 과다(단위 오류), 합계는 비슷한데 개별
항목만 크게 이동(항목 간 이동) 등을 감지한다.

패턴 판정 로직은 `src/pipeline/validator.run_data_validation`에 있고, 이 모듈은 **스키마 역할로
컬럼을 찾아** 넘긴다(period→기간, amount→금액, item→개별 항목 차원). 컬럼명을 코드에 박지 않으므로
구매·생산 등 다른 도메인에서도 그대로 동작한다(§7.3).

다월(전전월·전월·당월) 비교가 필요하므로 금액을 항목별·기간별로 직접 요청한다(get_series). 조회에
실패하면 "이상 없음"으로 위장하지 않고 명시적으로 실패한다.
"""
from __future__ import annotations

import pandas as pd

from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import get_full_schema, get_series, pick_dimension, role_column
from d2insight.engine.schema import ROLE_AMOUNT, ROLE_ITEM
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.validator import run_data_validation


def _issues_table(issues: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({
        "심각도": [i.get("severity", "") for i in issues],
        "오류 패턴": [i.get("description", "") for i in issues],
        "근거": [i.get("detail", "") for i in issues],
    })


def run(ctx, params, tools) -> ModuleResult:
    target_month = ctx.meta.get("target_month")
    if not target_month:
        return ModuleResult(status="failed", error="ctx.meta에 target_month가 없습니다.")

    schema = get_full_schema(ctx)
    amount_col = params.get("measure") or role_column(ctx, ROLE_AMOUNT) or schema.key_measure
    # 항목 간 이동 패턴에 쓸 개별 항목 차원 — item 의미 표시가 있는 컬럼만 사용(채널 등은 배제).
    item_col = pick_dimension(ctx, ROLE_ITEM, [amount_col])
    item_dims = [item_col] if item_col else []

    # 다월 비교가 불가능하면 "이상 없음"으로 조용히 넘기지 않는다 — 검증을 안 한 것과 같다.
    try:
        history = get_series(ctx, amount_col, item_col, params)
    except ValueError as e:
        return ModuleResult(status="failed", error=f"데이터 검증(다월 비교)에 필요한 기간별 값 조회에 실패했습니다: {e}")
    period_col = history.columns[0]

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

    render = render_from_dataframe(
        _issues_table(issues),
        purpose="분석 전 데이터 신뢰도(오류 패턴)를 점검.",
        narrative_hint=(
            f"오류 의심 {count}건이 감지됐다는 것과 각 패턴이 무엇을 뜻하는지 밝혀라 — 다른 분석 "
            "결과보다 이 데이터 신뢰성 경고를 먼저 읽어야 한다는 것을 분명히 하라." + dim_note
        ),
        params={"감지 이슈": count}, label="data_validation",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {"검증 결과": "주의", "감지 이슈": count}
    return ModuleResult(outputs={"validation_result": result}, render=render)
