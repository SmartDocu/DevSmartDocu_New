"""Module Registry (§7) — 판매분석 첫 채움 (Step 4-A).

각 모듈의 메타데이터(purpose/kind/requires/produces/params/tools/model_tier)는 실값으로 등록하되,
계산 로직(run)은 증분 B에서 src/pipeline에 배선한다. 지금은 stub이 명확한 오류를 던져
"조용히 잘못 동작"하지 않게 한다.

purpose 문구는 판매("매출")에 묶여 있다. 다른 도메인 재사용 시 Step 8에서 도메인 중립 표현으로
다듬는다(module_catalog_schema.md §10). 모듈 로직·계약은 이미 중립이다.
"""
from __future__ import annotations

from d2insight.engine.types import ModuleSpec

# 세션 공통값(compare_type/months_back/target_month)은 params가 아니라 ctx.meta에서 읽는다.

# 배선 완료된 모듈 run 구현 (src/engine/modules/). 미배선 모듈은 _pending stub을 쓴다.
from d2insight.engine.modules import abc_classification as _abc
from d2insight.engine.modules import aggregate as _aggregate
from d2insight.engine.modules import anomaly as _anomaly
from d2insight.engine.modules import bridge as _bridge
from d2insight.engine.modules import contribution as _contribution
from d2insight.engine.modules import customer_lifecycle as _customer_lifecycle
from d2insight.engine.modules import drilldown as _drilldown
from d2insight.engine.modules import impact as _impact
from d2insight.engine.modules import mix_effect as _mix_effect
from d2insight.engine.modules import new_lost as _new_lost
from d2insight.engine.modules import period as _period
from d2insight.engine.modules import inventory_turnover as _inventory
from d2insight.engine.modules import kpi_alert as _kpi_alert
from d2insight.engine.modules import pnl_driver as _pnl_driver
from d2insight.engine.modules import pnl_summary as _pnl
from d2insight.engine.modules import pnl_steps as _pnl_steps
from d2insight.engine.modules import stock_movement as _stock
from d2insight.engine.modules import product_lifecycle as _plc
from d2insight.engine.modules import safety_stock as _safety_stock
from d2insight.engine.modules import summary as _summary
from d2insight.engine.modules import validation as _validation
from d2insight.engine.catalog import conclusion as _conclusion

_WIRED: dict = {
    "period_dataset": _period.run,                          # 분석/비교/이력 기간 원천 데이터 적재(뿌리 모듈)
    "measure_summary": _summary.run,                        # 측정값별 실적 총평(Actual/Compare/Variance/Rate)
    "dimension_impact": _impact.run,                        # 차원별 영향도(Impact/Shapley/Z/HHI/DVI)
    "within_contribution": _contribution.run,                # 차원 내부 항목별 기여도 순위
    "anomaly_detection": _anomaly.run,                      # 이상징후 탐지(Z-Score/IQR/MAD)
    "new_lost_detection": _new_lost.run,                    # 신규·이탈(생애주기) 항목 탐지(통합, 여러 차원)
    "new_customer_step": _customer_lifecycle.run_new_customers,  # 고객 차원 — 신규 고객만
    "lost_customer_step": _customer_lifecycle.run_lost_customers,  # 고객 차원 — 이탈 고객만
    "sales_bridge": _bridge.run,                            # 매출 증감 브릿지(수량/ASP/할인/신규·이탈)
    "cross_drilldown": _drilldown.run,                      # 이상 항목 하위 차원 교차 분석
    "data_validation": _validation.run,                     # 데이터 신뢰도 사전 점검(누락·중복·단위오류 등)
    "abc_classification": _abc.run,                         # ABC(규모)-XYZ(변동성) 등급 분류
    "product_lifecycle": _plc.run,                          # 항목 수명주기 단계(도입/성장/성숙/쇠퇴)
    "kpi_alert": _kpi_alert.run,                            # 측정값(KPI) 레벨 이력 대비 이상 경보
    # pnl = P&L(Profit and Loss, 손익계산서) — 매출→매출원가→매출총이익→판관비→영업이익 계단
    "pnl_summary": _pnl.run,                                # 손익 계단(Revenue~EBIT) 통합 뷰 1스텝
    "revenue_step": _pnl_steps.run_revenue,                 # 손익 계단 — 매출(Revenue) 단계만
    "cogs_step": _pnl_steps.run_cogs,                       # 손익 계단 — 매출원가(COGS=Cost Of Goods Sold) 단계만
    "gross_margin_step": _pnl_steps.run_gross_margin,       # 손익 계단 — 매출총이익(Gross Margin) 단계만
    "opex_step": _pnl_steps.run_opex,                       # 손익 계단 — 판매관리비(OPEX=Operating Expense) 단계만
    "ebit_step": _pnl_steps.run_ebit,                       # 손익 계단 — 영업이익(EBIT=Earnings Before Interest and Taxes) 단계만
    "pnl_driver": _pnl_driver.run,                          # 영업이익 증감을 매출·원가·판관비 효과로 분해(원인 분석)
    "inventory_turnover": _inventory.run,                   # 재고회전율·재고일수·장기체화 판정(통합 뷰)
    "dead_stock_step": _inventory.run_dead_stock,           # 재고 — 미회전(Dead Stock)만
    "slow_moving_step": _inventory.run_slow_moving,         # 재고 — 장기체화(Slow Moving)만
    "safety_stock": _safety_stock.run,                      # 안전재고 대비 부족 위험 진단(정책값 우선, 없으면 추정)
    "stock_movement": _stock.run,                           # 기초+입고-출고=기말 재고 흐름 정합성 점검
    "mix_effect": _mix_effect.run,                          # PVM 분해 — 구성 이동(Mix) 단계만
    "volume_effect": _mix_effect.run_volume,                # PVM 분해 — 순수 물량(Volume) 단계만
    "price_effect": _mix_effect.run_price,                  # PVM 분해 — 단가(Price) 단계만
    "actual_aggregate": _aggregate.run_actual_aggregate,    # 차원별 실적 집계(리프)
    "composition": _aggregate.run_composition,              # 구성비(전체 대비 비중) 집계(리프)
    "ranking": _aggregate.run_ranking,                      # 차원 항목 순위(Top N) 집계(리프)
    "trend": _aggregate.run_trend,                          # 월별 추이(이력 시계열) 집계(리프)
    "cumulative_progress": _aggregate.run_cumulative_progress,  # 누계·진척률 집계(리프)
    "conclusion": _conclusion.run,                          # 최종 결론(Executive Summary) — 항상 맨 뒤(7단계)
}


def _pending(module_id: str):
    """아직 배선되지 않은 모듈의 계산 자리(stub). 실행되면 명확히 실패한다."""
    def _run(ctx, params, tools):
        raise NotImplementedError(
            f"모듈 '{module_id}'의 계산 로직은 Step 4-B에서 src/pipeline에 배선됩니다."
        )
    return _run


def _spec(module_id, **kw) -> ModuleSpec:
    run = _WIRED.get(module_id) or _pending(module_id)
    return ModuleSpec(module_id=module_id, run=run, **kw)


# ── 집계·실적형 (1급) ─────────────────────────────────────────────────────────
_AGGREGATE = [
    _spec(
        "period_dataset",
        purpose="분석기간·비교기간·최근구간 원천과 컬럼 메타를 적재(§1 분석대상자료확인).",
        kind="aggregate",
        requires=[],
        produces=["actual_dataset", "compare_dataset", "history_dataset", "meta_columns"],
        params={
            # enum: dataset_builder.compare_shift가 인식하는 값은 이 세 개뿐이다. LLM이
            # 임의 문자열("month_over_month" 등)을 지어내면 qoq/yoy 매칭에 실패해 조용히
            # MoM으로 빠진다(2026-07-28 실사용 테스트에서 발견) — chat_options._catalog_digest가
            # 이 목록을 LLM에게 보여줘 애초에 못 지어내게 막는다.
            "compare_type": {"type": "str", "required": False, "default": None,
                              "enum": ["MoM", "QoQ", "YoY"]},
            "months_back":  {"type": "int", "required": False, "default": 3},
            # 기간 단위(2026-07-24 3단계): month(기본)/quarter/year/week.
            "grain":        {"type": "str", "required": False, "default": None,
                              "enum": ["month", "quarter", "year", "week"]},
        },
        tools={},                       # 순수 로드
        model_tier="none",
        narrative_hint="분석 대상 기간·데이터 규모가 분석에 충분한지 짧게 확인해 주는 도입 문단.",
    ),
    _spec(
        "actual_aggregate",
        purpose="차원×measure 실적과 증감을 표·차트로 제시(실적집계, 재사용 핵심).",
        kind="aggregate",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],                    # 리프
        params={
            "dimension": {"type": "str", "required": True},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 20},
        },
        tools={"available": ["group_sum"], "default": "group_sum"},
        model_tier="fast",
        narrative_hint="규모가 큰 항목과 증감이 큰 항목이 다르면 그 차이를 짚어라.",
    ),
    _spec(
        "plan_vs_actual",
        # 보류: AdventureWorks에 계획 데이터가 없어 등록만 하고 실데이터가 붙을 때 사용(§9 그릇 검증).
        purpose="계획/목표 대비 달성률·차이를 제시(계획대비실적, 별도 모듈).",
        kind="aggregate",
        requires=["actual_dataset"],
        produces=[],
        params={
            "dimension":   {"type": "str", "required": False, "default": None},
            "measure":     {"type": "str", "required": False, "default": None},
            "plan_source": {"type": "str", "required": True},
        },
        tools={"available": ["attainment"], "default": "attainment"},
        model_tier="fast",
    ),
    _spec(
        "trend",
        purpose="measure의 기간별 추이를 제시(추이).",
        kind="aggregate",
        requires=["history_dataset"],
        produces=[],
        params={
            "measure":   {"type": "str", "required": False, "default": None},
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 5},
            # None = 이력 전체(기본). 수동 모드에서 사용자가 창을 지정한다.
            "window_months": {"type": "int", "required": False, "default": None},
        },
        tools={"available": ["series"], "default": "series"},
        model_tier="fast",
        narrative_hint="추이의 방향·변곡점·계절성 여부를 짚어라. 단발 등락과 추세를 구분해 서술하라.",
        layout=["chart", "narrative", "table"],   # 추이는 그림을 먼저 보여주는 편이 읽힌다
    ),
    _spec(
        "composition",
        purpose="차원 항목별 구성비와 비중 변화를 제시(구성비).",
        kind="aggregate",
        requires=["actual_dataset", "compare_dataset"],   # 비중 '변화'를 보려면 비교기간이 필요
        produces=[],
        params={
            "dimension": {"type": "str", "required": True},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={"available": ["share"], "default": "share"},
        model_tier="fast",
        narrative_hint="비중이 커진 항목과 줄어든 항목을 짚고, 집중도가 높아졌는지 낮아졌는지 말하라.",
    ),
    _spec(
        "ranking",
        purpose="항목 상/하위 순위를 제시(순위).",
        kind="aggregate",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": True},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
            "order":     {"type": "str", "required": False, "default": "desc"},
            "by":        {"type": "str", "required": False, "default": "actual"},  # actual | variance
        },
        tools={"available": ["rank"], "default": "rank"},
        model_tier="fast",
        narrative_hint="상위권의 규모 차이가 큰지 고른지 짚어라. 순위와 증감 방향이 어긋나면 그 점을 말하라.",
    ),
    _spec(
        "cumulative_progress",
        purpose="기간 누계와 진척률을 제시(누계/진척).",
        kind="aggregate",
        requires=["history_dataset"],
        produces=[],
        params={
            "measure": {"type": "str", "required": False, "default": None},
            "target":  {"type": "float", "required": False, "default": None},
            # None = 이력 전체(기본). 수동 모드에서 사용자가 창을 지정한다.
            "window_months": {"type": "int", "required": False, "default": None},
        },
        tools={"available": ["running_total"], "default": "running_total"},
        model_tier="fast",
        narrative_hint="누계 흐름이 목표 달성에 충분한 속도인지 말하라. 목표가 없으면 기간 평균과 편차를 짚어라.",
    ),
]

# ── 분석형 ────────────────────────────────────────────────────────────────────
_ANALYSIS = [
    _spec(
        "measure_summary",
        purpose="전체 매출 증감 총평(규모/율/수량/ASP/할인율) (§11).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["measure_summary", "total_variance"],
        params={"measures": {"type": "list", "required": False, "default": None}},
        tools={},                       # 집계 계산
        model_tier="balanced",
        narrative_hint=(
            "증감이 물량(수량)에서 왔는지 단가(ASP)에서 왔는지, 할인율 변화가 이를 거들었는지 갈라 설명하라."
        ),
    ),
    _spec(
        "dimension_impact",
        purpose="어느 차원이 변화를 주도했는지 DVI/Shapley 순위로 제시(§12-A).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["dimension_stats"],
        params={
            "measure":    {"type": "str", "required": False, "default": None},
            "dimensions": {"type": "list", "required": False, "default": None},
        },
        tools={"available": ["shapley", "dvi"], "default": "dvi"},
        model_tier="balanced",
        narrative_hint=(
            "상위 차원이 왜 상위인지 임팩트(총 흔들림)·HHI(소수 항목 집중)·Z(편차)로 갈라 설명하라. "
            "항목 수가 많은 차원은 지표가 부풀 수 있음을 감안해 해석하라."
        ),
    ),
    _spec(
        "within_contribution",
        purpose="항목 증감액/전체 증감액 기준 차원 내 기여도 상위 제시(§12-B).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],
        produces=["within_contribution"],
        params={
            "dimension": {"type": "str", "required": True},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 20},
        },
        tools={"available": ["contribution_rate"], "default": "contribution_rate"},
        model_tier="balanced",
        narrative_hint=(
            "증가를 이끈 항목과 그것을 깎아먹은 감소 항목을 함께 짚어라. 상위 항목이 전체 증감을 "
            "얼마나 설명하는지(누적 기여율), 신규·단종 항목이 끼어 있는지도 언급하라."
        ),
    ),
    _spec(
        "anomaly_detection",
        # §14 개정(2026-07-14): 전 차원·전체 항목 대상, 금액·증감률 두 축으로 판정.
        # dimension_stats를 더 이상 requires로 받지 않는다(2026-07-24 4단계) — measure별로
        # 다른 결과가 필요해, dimension_impact가 만든 (특정 measure에 고정된) 싱글턴에 기대지
        # 않고 이 모듈이 요청받은 measure로 직접 통계를 계산한다.
        purpose="금액·증감률 분포에서 크게 벗어난 이상 항목을 탐지(§14).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["outlier_result"],
        params={
            "measure":    {"type": "str", "required": False, "default": None},
            "sigma":      {"type": "float", "required": False, "default": 3.0},
            "dimension":  {"type": "str", "required": False, "default": None},
            "dimensions": {"type": "list", "required": False, "default": None},
            "top_n":      {"type": "int", "required": False, "default": 10},
            # 일시미구매(구매 주기상 미등장) 고객을 이상징후에서 제외할지 — anomaly.py가 읽는데
            # 선언이 빠져 있어 옵션 JSON 지정 시 OptionsError가 났던 갭(2026-07-23 발견·수정).
            "exclude_dormant": {"type": "bool", "required": False, "default": True},
        },
        tools={"available": ["z_score", "iqr", "mad", "attainment"], "default": "z_score"},
        model_tier="balanced",
        narrative_hint=(
            "금액 영향이 큰 이탈부터 짚고, 어느 축(금액/증감률)에서 벗어났는지 구분해 설명하라. "
            "판정 불가 차원이 있으면 '이상 없음'이 아니라 '표본 부족으로 판정하지 못함'임을 분명히 하라. "
            "이상 항목이 없으면 그 자체가 결과임을 밝히고 임계값을 명시하라."
        ),
    ),
    _spec(
        "new_lost_detection",
        purpose="신규·이탈 항목의 건수와 금액 효과를 제시(§6).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["new_lost_items", "count_summary"],
        params={
            "dimension":  {"type": "str", "required": False, "default": None},
            "dimensions": {"type": "list", "required": False, "default": None},
            "top_n":      {"type": "int", "required": False, "default": 10},
        },
        tools={"available": ["new_lost"], "default": "new_lost"},
        model_tier="balanced",
        narrative_hint=(
            "신규 유입과 이탈이 각각 몇 건·얼마이고 순효과가 어느 쪽인지 규모로 설명하라. "
            "개별 이상 항목 나열은 이상징후 분석의 몫이니 여기서는 총량과 구조(신규가 이탈을 "
            "메우는지 여부)에 집중하라."
        ),
    ),
    _spec(
        "new_customer_step",
        purpose="고객(party) 차원의 신규 유입(진성신규·복귀)만 — 시나리오 '고객 분석'의 신규 고객 스텝.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],                        # new_lost_detection과 같은 계산(_shared.get_lifecycle_effects) 공유
        params={"top_n": {"type": "int", "required": False, "default": 10}},
        tools={},
        model_tier="balanced",
        narrative_hint="진성신규와 복귀를 구분해 몇 명이 얼마만큼 유입됐는지 말하라. 이탈은 다른 스텝의 몫이다.",
    ),
    _spec(
        "lost_customer_step",
        purpose="고객(party) 차원의 이탈(진성이탈)만 — 시나리오 '고객 분석'의 이탈 고객 스텝.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={"top_n": {"type": "int", "required": False, "default": 10}},
        tools={},
        model_tier="balanced",
        narrative_hint=(
            "진성이탈 고객 수와 손실 금액을 말하라. 일시미구매(구매 주기상 미등장)는 이탈이 "
            "아니므로 건수만 참고로 밝히고 이탈로 세지 마라."
        ),
    ),
    _spec(
        "sales_bridge",
        # §13 개정(2026-07-14): 상품·고객 두 관점의 가법 분해(각 관점 합계 = 전체 증감액).
        purpose="증감을 수량/정가ASP/할인/신규/이탈 효과로 분해(§13).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],
        produces=["bridge_effects"],
        params={"top_n": {"type": "int", "required": False, "default": 10}},
        tools={"available": ["bridge_decompose"], "default": "bridge_decompose"},
        model_tier="balanced",
        narrative_hint=(
            "증감이 물량에서 왔는지 가격에서 왔는지, 신규 유입이 이탈을 메웠는지 설명하라. "
            "상품 관점과 고객 관점은 같은 증감액을 다른 렌즈로 본 것이니 둘을 더하지 마라."
        ),
    ),
    _spec(
        "cross_drilldown",
        purpose="이상 항목이 어느 하위 항목에서 비롯됐는지 교차 분석(§15).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "outlier_result", "dimension_stats"],
        produces=["drilldown_result"],
        params={
            "top_n":          {"type": "int", "required": False, "default": 5},
            "cross_top_n":    {"type": "int", "required": False, "default": 5},
            "sub_dimensions": {"type": "list", "required": False, "default": None},
        },
        tools={"available": ["cross_cut"], "default": "cross_cut"},
        model_tier="balanced",
        narrative_hint=(
            "이상 항목의 증감이 어느 하위 항목에서 왔는지, 그 원인이 물량인지 가격인지 신규 유입인지 "
            "짚어라. 한 하위 항목이 대부분을 설명하면 그 사실을 분명히 하라."
        ),
    ),
    _spec(
        "data_validation",
        purpose="분석 신뢰도 사전 점검(데이터검증).",
        kind="analysis",
        requires=["history_dataset"],       # 다월(전전월·전월·당월) 비교 → 이력 패널 필요
        produces=["validation_result"],
        params={},
        tools={"available": ["validate"], "default": "validate"},
        model_tier="fast",
    ),
    _spec(
        "abc_classification",
        # 분류 단위(grain)는 item 역할 기본, params.dimensions로 명시 지정(§7.4). CV·등급변동은 진단적.
        purpose="항목을 규모(ABC)·변동성(XYZ)으로 분류하고 등급 변동을 제시.",
        kind="analysis",
        requires=["history_dataset"],       # 다월 패널: XYZ의 CV·ABC 누적점유율·등급 변동
        produces=["abc_xyz_classification", "abc_grade_changes"],
        params={
            "dimensions":    {"type": "list", "required": False, "default": None},   # None → item 역할
            "window_months": {"type": "int",  "required": False, "default": 3},
            "top_n":         {"type": "int",  "required": False, "default": 20},
        },
        tools={},                           # 단일 방식
        model_tier="fast",
        narrative_hint=(
            "규모 등급(ABC)과 변동성 등급(XYZ)이 엇갈리는 항목(예: 크지만 불안정한 AZ)을 짚고, "
            "등급이 하락·상승한 항목의 관리 시사점을 서술하라."
        ),
    ),
    _spec(
        "product_lifecycle",
        purpose="항목을 수명주기 단계(도입/성장/성숙/쇠퇴)로 분류.",
        kind="analysis",
        requires=["history_dataset"],       # 다월 추이(기울기·활동 기간)
        produces=["lifecycle_stages"],
        params={
            "dimensions": {"type": "list", "required": False, "default": None},   # None → item 역할
            "top_n":      {"type": "int",  "required": False, "default": 20},
            # None = 이력 전체(기본). 창을 바꾸면 전반/후반 분할이 이동해 단계 판정이 달라진다.
            "window_months": {"type": "int", "required": False, "default": None},
        },
        tools={},                           # 단일 방식
        model_tier="fast",
        narrative_hint=(
            "쇠퇴 단계로 접어든 주요 항목과, 성장 단계라 밀어줄 항목을 짚어라. "
            "규모가 크면서 쇠퇴하는 항목을 우선 관리 대상으로 지목하라."
        ),
    ),
    _spec(
        "kpi_alert",
        # anomaly_detection(항목 레벨·횡단면)과 다르다 — measure 레벨·시계열 판정이다.
        purpose="measure(KPI)가 이력 대비 평소 범위를 벗어났는지 경보/주의/정상으로 판정.",
        kind="analysis",
        requires=["history_dataset", "measure_summary"],
        produces=["kpi_alerts"],
        params={
            "sigma": {"type": "float", "required": False, "default": None},   # None → config
            "rate":  {"type": "float", "required": False, "default": None},   # threshold 툴용
            # None = 이력 전체(기본). 수동 모드에서 기준선 창을 지정한다.
            "window_months": {"type": "int", "required": False, "default": None},
        },
        tools={"available": ["history_z", "threshold", "attainment"], "default": "history_z"},
        model_tier="balanced",
        narrative_hint=(
            "경보 KPI부터 짚고, 상향·하향 방향과 그것이 좋은 신호인지 나쁜 신호인지 구분해 말하라. "
            "판정 불가 KPI가 있으면 '이상 없음'이 아니라 '기준선이 짧아 판정하지 못함'임을 분명히 하라. "
            "경보가 없으면 그 자체가 결과임을 밝히고 판정 기준을 명시하라."
        ),
    ),
    _spec(
        "pnl_summary",
        purpose="손익 계단(매출→원가→매출총이익→판관비→영업이익)과 이익률 변화를 제시.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],   # 역할(cost/opex)은 모듈이 직접 확인
        produces=["pnl_steps"],
        params={},
        tools={"available": ["margin_ladder"], "default": "margin_ladder"},
        model_tier="balanced",
        narrative_hint=(
            "이익이 줄었다면 그것이 매출 감소 때문인지 원가율 상승 때문인지 판관비 증가 때문인지 "
            "단계별로 갈라 설명하라. 금액 증감과 이익률(%p) 변화를 함께 짚어라. "
            "판관비가 없어 영업이익을 못 냈으면 그 사실을 분명히 하라."
        ),
    ),
    # 손익 계단 5스텝 공통 옵션(2026-07-23 추가): dimension을 지정하면 그 단계 금액을 차원별
    # 상세 표로 분해해 덧붙인다(예: 제품별 매출원가). 미지정 시 총계 요약만(기존 동작).
    _spec(
        "revenue_step",
        purpose="손익 계단의 매출(Revenue) 단계 — 시나리오 '손익 분석'의 첫 스텝.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],                        # 계산은 _shared.get_pnl_ladder 캐시(내부 파생물)
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={},
        model_tier="balanced",
        narrative_hint="매출 증감의 방향과 규모를 말하라. 원인(물량/단가/믹스)은 이 스텝의 몫이 아니다.",
    ),
    _spec(
        "cogs_step",
        purpose="손익 계단의 매출원가(COGS) 단계.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={},
        model_tier="balanced",
        narrative_hint="매출원가가 매출과 같은 방향으로 움직였는지, 매출 대비 비용률이 개선/악화됐는지 말하라.",
    ),
    _spec(
        "gross_margin_step",
        purpose="손익 계단의 매출총이익(Gross Margin) 단계.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={},
        model_tier="balanced",
        narrative_hint="매출총이익 증감이 매출 변화 때문인지 원가율 변화 때문인지 짚고, 이익률(%p) 변화를 말하라.",
    ),
    _spec(
        "opex_step",
        purpose="손익 계단의 판매관리비(OPEX) 단계. 이 역할이 없으면 명시적으로 실패한다.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={},
        model_tier="balanced",
        narrative_hint="판관비가 매출 대비 늘었는지 줄었는지 말하라.",
    ),
    _spec(
        "ebit_step",
        purpose="손익 계단의 영업이익(EBIT) 단계 — 손익 분석의 최종 결과 단계.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={},
        model_tier="balanced",
        narrative_hint="영업이익 증감이 앞선 매출·원가·판관비 스텝 중 무엇의 영향이 컸는지 종합해 말하라.",
    ),
    _spec(
        "pnl_driver",
        purpose="영업이익(EBIT) 증감을 매출·매출원가·판매관리비 효과로 분해 — 손익 분석의 원인 분석 스텝.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],                        # revenue_step~ebit_step과 같은 계산(get_pnl_ladder)을 공유
        # dimension 지정 시(2026-07-23) 항목별 ΔEBIT 분해 표(매출/원가/판관비 효과) 추가.
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
        },
        tools={},
        model_tier="balanced",
        narrative_hint=(
            "영업이익 증감의 가장 큰 요인부터 순서대로 말하고, 그것이 매출 때문인지 원가 때문인지 "
            "판관비 때문인지 밝혀라. 세 효과의 합이 영업이익 증감과 일치한다는 것을 전제로 설명하라."
        ),
    ),
    _spec(
        "inventory_turnover",
        purpose="재고회전율·재고일수와 장기체화 항목을 제시.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],   # 역할(inventory/cost)은 모듈이 직접 확인
        produces=["inventory_metrics", "inventory_summary"],
        params={
            "dimension": {"type": "str",   "required": False, "default": None},  # None → item 역할
            "slow_days": {"type": "float", "required": False, "default": None},  # None → config
            "top_n":     {"type": "int",   "required": False, "default": 20},
        },
        tools={"available": ["turnover"], "default": "turnover"},
        model_tier="balanced",
        narrative_hint=(
            "회전율이 개선됐는지 악화됐는지 말하고, 재고일수가 긴 항목에 묶인 자금을 짚어라. "
            "미회전 항목은 처분·폐기 검토 대상으로 지목하라."
        ),
    ),
    _spec(
        "dead_stock_step",
        purpose="미회전(Dead Stock) 항목만 — 시나리오 '재고 분석'의 Dead Stock 스텝.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "inventory_metrics"],
        produces=[],                        # inventory_turnover가 만든 이름표를 필터링만(재계산 없음)
        params={"top_n": {"type": "int", "required": False, "default": 20}},
        tools={},
        model_tier="balanced",
        narrative_hint="미회전 항목 수와 거기 묶인 재고 규모를 말하고, 처분·폐기 검토 대상임을 밝혀라.",
    ),
    _spec(
        "slow_moving_step",
        purpose="장기체화(Slow Moving) 항목만 — 시나리오 '재고 분석'의 Slow Moving 스텝.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "inventory_metrics"],
        produces=[],
        params={"top_n": {"type": "int", "required": False, "default": 20}},
        tools={},
        model_tier="balanced",
        narrative_hint="재고일수가 긴 항목이 몇 개고 거기 묶인 재고 규모가 얼마인지 말하라(미회전과는 다른 항목군).",
    ),
    _spec(
        "safety_stock",
        purpose="항목별 안전재고 목표치 대비 현재 재고 부족 위험을 진단(정책값 우선, 없으면 Z×σ 공식으로 추정).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],   # 역할(safety_stock/inventory/cost)은 모듈이 직접 확인
        produces=[],
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 20},
        },
        tools={},
        model_tier="balanced",
        narrative_hint=(
            "부족 위험 항목 수와 가장 심각한 항목을 말하라. 안전재고가 정책값이 아니라 추정값이면 "
            "그 사실을 반드시 밝히고(회사가 정한 기준이 아님), 보충 발주가 필요함을 짚어라."
        ),
    ),
    _spec(
        "stock_movement",
        purpose="기초·입고·출고·기말 재고 흐름과 정합성(기초+입고−출고=기말)을 점검.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],   # 역할은 모듈이 직접 확인
        produces=["stock_flow", "stock_movement_detail"],
        params={
            "dimension": {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 20},
        },
        tools={"available": ["stock_reconcile"], "default": "stock_reconcile"},
        model_tier="balanced",
        narrative_hint=(
            "정합성이 어긋나면 분석 결론보다 **데이터 신뢰성 경고를 먼저** 말하라. "
            "정합하면 재고가 쌓이는 항목과 빠지는 항목을 순증감으로 짚어라."
        ),
    ),
    _spec(
        "volume_effect",
        purpose="순수 물량(Volume) 효과 — 믹스·단가를 제외한 판매량 자체의 증감분.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],  # 비중은 total_variance 기준(2026-07-21)
        produces=[],                        # 계산은 _shared.get_pvm_effects/get_bridge_effects 캐시(내부 파생물)
        params={
            "top_n": {"type": "int", "required": False, "default": 10},   # bridge 툴일 때만 항목표에 쓰임
            # dimension은 상품(item) 기준 고정이라 모듈이 실제로 읽지는 않는다(§13) — 옵션 JSON이
            # 그 사실을 명시하려고 넘겨도 검증에서 걸리지 않도록 선언만 해둔다.
            "dimension": {"type": "str", "required": False, "default": "item"},
        },
        tools={"available": ["pvm", "bridge_decompose"], "default": "bridge_decompose"},
        # tools={"available": ["pvm", "bridge_decompose"], "default": "pvm"},
        model_tier="balanced",
        narrative_hint=(
            "판매량 자체가 늘었는지 줄었는지, 그 규모가 전체 증감에서 차지하는 비중을 말하라. "
            "항목별 표가 있으면(bridge 방식) 어떤 상품이 물량 효과를 주도했는지도 짚어라."
        ),
    ),
    _spec(
        "price_effect",
        purpose="단가(Price) 효과 — 물량 변화를 제외한 항목별 판매 단가 변화분.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],
        produces=[],
        params={
            "top_n": {"type": "int", "required": False, "default": 10},
            "dimension": {"type": "str", "required": False, "default": "item"},
        },
        tools={"available": ["pvm", "bridge_decompose"], "default": "bridge_decompose"},
        # tools={"available": ["pvm", "bridge_decompose"], "default": "pvm"},
        model_tier="balanced",
        narrative_hint=(
            "단가가 오른 방향인지 내린 방향인지, 전체 증감에서 차지하는 비중을 말하라. "
            "항목별 표가 있으면(bridge 방식) 어떤 상품의 단가 변화가 주도했는지도 짚어라."
        ),
    ),
    _spec(
        "mix_effect",
        purpose="구성 이동(Mix) 효과 — 물량 총량·단가 변화를 제외한 판매 구성 이동분.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],
        produces=[],                        # volume_effect/price_effect와 같은 계산을 공유(리프)
        params={},
        tools={},                           # 단일 방식(PVM 표준 계산) — 대체 툴 없음
        model_tier="balanced",
        narrative_hint=(
            "판매 구성이 매출에 유리한 쪽으로 옮겨갔는지 불리한 쪽으로 옮겨갔는지 말하고, "
            "물량(volume_effect)·단가(price_effect) 스텝과 이 스텝이 합쳐 매출 변화를 이룬다는 "
            "것을 전제로 설명하라."
        ),
    ),
    _spec(
        "conclusion",
        purpose="모든 스텝의 집계 결과를 바탕으로 최종 경영 인사이트(결론)를 작성.",
        kind="analysis",
        # 어떤 조합의 스텝이 앞에 오든(제외·추가·순서변경) 실행 가능해야 하므로 requires를
        # 선언하지 않는다 — 실제로 무엇을 읽을지는 build_conclusion이 ctx에서 있는 대로
        # 골라 쓴다(2026-07-28, 7단계). "항상 맨 뒤"는 operations._TAIL_MODULE_IDS 잠금으로
        # 보장한다(requires 기반 순서 강제가 아니라 스텝 배치 자체를 고정).
        requires=[],
        produces=[],
        params={},
        tools={},                           # 결론 방식은 하나뿐 — 대체 툴 없음
        model_tier="quality",               # 실서비스에서 상위 모델(Opus 등)로 지정할 자리
        narrative_hint="",                  # 안 쓰임 — 결론은 narrate 단계를 거치지 않고 스스로 완성된 본문을 낸다.
    ),
]

MODULE_REGISTRY: dict[str, ModuleSpec] = {m.module_id: m for m in (_AGGREGATE + _ANALYSIS)}


def get_module_registry() -> dict[str, ModuleSpec]:
    return dict(MODULE_REGISTRY)
