"""Module Registry (§7) — 판매분석 첫 채움 (Step 4-A).

각 모듈의 메타데이터(purpose/kind/requires/produces/params/tools/model_tier)는 실값으로 등록하되,
계산 로직(run)은 증분 B에서 src/pipeline에 배선한다. 지금은 stub이 명확한 오류를 던져
"조용히 잘못 동작"하지 않게 한다.

purpose 문구는 판매("매출")에 묶여 있다. 다른 도메인 재사용 시 Step 8에서 도메인 중립 표현으로
다듬는다(module_catalog_schema.md §10). 모듈 로직·계약은 이미 중립이다.

── 카탈로그 재구조화 (2026-09-01) ──────────────────────────────────────────────
module_id는 **{measure, module_name, sub_name} 세 필드의 조합**이 됐다. 이 파일이
등록하는 것은 그중 `module_name` 하나뿐이고, 조합마다 스펙을 따로 두지 않는다.

    {"measure": "amount", "module_name": "ranking", "sub_name": "brand"}

각 스펙은 자기가 measure·sub_name을 받는지를 선언하기만 한다(`sub_name_pool`,
`accepts_measure`, types.py 참고). 실행 직전에 그 값들이 `sub_name_param`이 가리키는
params 키로 펼쳐지므로, **아래 params 선언과 engine/modules/*.py의 계산 로직은
그대로다.** 조립 표현은 카탈로그·JSON·편집 연산 층에만 있다.

이름 규칙 두 가지:
  - 특정 스텝·시나리오 전용이라는 뜻의 접미사(`_step`)를 붙이지 않는다. 모듈은 중립
    부품이고, 스텝이 그 부품을 골라 조립한다.
  - 방법론적 변형(by/order 같은 것)은 필드로 두지 않고 module_name을 나눠 흡수한다
    (`ranking` / `decline_ranking`). 데이터의 축(measure·sub_name)과 성격이 다르다.
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
    "new_party": _customer_lifecycle.run_new_customers,     # party 차원 — 신규 유입만
    "lost_party": _customer_lifecycle.run_lost_customers,   # party 차원 — 이탈만
    "bridge": _bridge.run,                                  # 증감 브릿지(수량/ASP/할인/신규·이탈)
    "cross_drilldown": _drilldown.run,                      # 이상 항목 하위 차원 교차 분석
    "data_validation": _validation.run,                     # 데이터 신뢰도 사전 점검(누락·중복·단위오류 등)
    "abc_classification": _abc.run,                         # ABC(규모)-XYZ(변동성) 등급 분류
    "product_lifecycle": _plc.run,                          # 항목 수명주기 단계(도입/성장/성숙/쇠퇴)
    "kpi_alert": _kpi_alert.run,                            # 측정값(KPI) 레벨 이력 대비 이상 경보
    # pnl = P&L(Profit and Loss, 손익계산서) — 매출→매출원가→매출총이익→판관비→영업이익 계단
    "pnl_summary": _pnl.run,                                # 손익 계단(Revenue~EBIT) 통합 뷰 1스텝
    "pnl_revenue": _pnl_steps.run_revenue,                  # 손익 계단 — 매출(Revenue) 단계만
    "pnl_cogs": _pnl_steps.run_cogs,                        # 손익 계단 — 매출원가(COGS=Cost Of Goods Sold) 단계만
    "pnl_gross_margin": _pnl_steps.run_gross_margin,        # 손익 계단 — 매출총이익(Gross Margin) 단계만
    "pnl_opex": _pnl_steps.run_opex,                        # 손익 계단 — 판매관리비(OPEX=Operating Expense) 단계만
    "pnl_ebit": _pnl_steps.run_ebit,                        # 손익 계단 — 영업이익(EBIT=Earnings Before Interest and Taxes) 단계만
    "pnl_driver": _pnl_driver.run,                          # 영업이익 증감을 매출·원가·판관비 효과로 분해(원인 분석)
    "inventory_turnover": _inventory.run,                   # 재고회전율·재고일수·장기체화 판정(통합 뷰)
    "dead_stock": _inventory.run_dead_stock,                # 재고 — 미회전(Dead Stock)만
    "slow_moving": _inventory.run_slow_moving,              # 재고 — 장기체화(Slow Moving)만
    "safety_stock": _safety_stock.run,                      # 안전재고 대비 부족 위험 진단(정책값 우선, 없으면 추정)
    "stock_movement": _stock.run,                           # 기초+입고-출고=기말 재고 흐름 정합성 점검
    "mix_effect": _mix_effect.run,                          # PVM 분해 — 구성 이동(Mix) 단계만
    "volume_effect": _mix_effect.run_volume,                # PVM 분해 — 순수 물량(Volume) 단계만
    "price_effect": _mix_effect.run_price,                  # PVM 분해 — 단가(Price) 단계만
    "actual_aggregate": _aggregate.run_actual_aggregate,    # 차원별 실적 집계(리프)
    "composition": _aggregate.run_composition,              # 구성비(전체 대비 비중) 집계(리프)
    "ranking": _aggregate.run_ranking,                      # 차원 항목 상위 순위(Top N) 집계(리프)
    "decline_ranking": _aggregate.run_ranking,              # 같은 계산, 감소 큰 순 — params 기본값만 다르다
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


# ── 모듈 주제(topic) — 스텝-모듈 매트릭스의 근거 (2026-09-01) ──────────────────
# 스텝도 같은 주제를 단다(steps.py). 주제가 겹치면 그 칸이 O, 안 겹치면 빈칸이다.
# "any"는 어느 스텝에나 어울린다는 뜻 — 대개 차원만 바꾸면 어디든 쓰이는 집계 모듈이다.
#
# 스텝과 모듈이 **서로를 나열하지 않는다.** 각자 자기 주제만 적으므로, 스텝이 늘어도 이
# 표를 안 고치고 모듈이 늘어도 스텝을 안 고친다.
#
# 여기서 보는 것은 "의미가 맞는가"뿐이다. 실행 가능한가(선행 모듈·역할 유무·이름표 충돌)는
# planner/options가 실행 시점에 따로 검사한다.
_TOPICS = ("sales", "customer", "item", "pnl", "inventory", "closing", "any")

_MODULE_TOPICS: dict[str, list[str]] = {
    # 뿌리·공통 — 어느 보고서에나 들어간다
    "period_dataset":      ["any"],
    "data_validation":     ["any"],
    # 결론은 도메인 주제가 아니라 보고서에서의 자리다. "closing"은 전용 주제라 any가
    # 뚫지 못한다(matrix.EXCLUSIVE) — 결론 모듈이 다른 스텝에 끼어들지 않고, 결론 스텝에
    # 다른 모듈이 들어오지도 않는다.
    "conclusion":          ["closing"],
    # 집계 리프 — sub_name만 바꾸면 어느 주제에나 쓰인다
    "actual_aggregate":    ["any"],
    "composition":         ["any"],
    "ranking":             ["any"],
    "decline_ranking":     ["any"],
    "trend":               ["any"],
    # 원인·이상 — 대상 차원을 가리지 않는다
    "dimension_impact":    ["any"],
    "within_contribution": ["any"],
    "anomaly_detection":   ["any"],
    "new_lost_detection":  ["any"],
    # 항목 레벨이 아니라 measure(KPI) 레벨 시계열 판정이라, 고객·제품 같은 항목 주제에는
    # 어울리지 않는다 — 금액·이익·재고 지표를 보는 스텝에서 쓴다.
    "kpi_alert":           ["sales", "pnl", "inventory"],
    "cross_drilldown":     ["any"],
    # 매출 증감 분해
    "measure_summary":     ["sales"],
    "bridge":              ["sales"],
    "volume_effect":       ["sales"],
    "price_effect":        ["sales"],
    "mix_effect":          ["sales"],
    "cumulative_progress": ["sales"],
    "plan_vs_actual":      ["sales"],
    # 고객(party) 고정
    "new_party":           ["customer"],
    "lost_party":          ["customer"],
    # 제품
    "product_lifecycle":   ["item"],
    # 규모·변동성 분류 — 제품 ABC와 재고 ABC 양쪽에서 쓴다
    "abc_classification":  ["item", "inventory"],
    # 손익
    "pnl_summary":         ["pnl"],
    "pnl_revenue":         ["pnl"],
    "pnl_cogs":            ["pnl"],
    "pnl_gross_margin":    ["pnl"],
    "pnl_opex":            ["pnl"],
    "pnl_ebit":            ["pnl"],
    "pnl_driver":          ["pnl"],
    # 재고
    "inventory_turnover":  ["inventory"],
    "dead_stock":          ["inventory"],
    "slow_moving":         ["inventory"],
    "safety_stock":        ["inventory"],
    "stock_movement":      ["inventory"],
}


def _spec(module_id, **kw) -> ModuleSpec:
    run = _WIRED.get(module_id) or _pending(module_id)
    kw.setdefault("topics", _MODULE_TOPICS.get(module_id, ["any"]))
    return ModuleSpec(module_id=module_id, run=run, **kw)


# ── 집계·실적형 (1급) ─────────────────────────────────────────────────────────
_AGGREGATE = [
    _spec(
        "period_dataset",
        purpose="분석기간·비교기간·최근구간 원천과 컬럼 메타를 적재.",
        kind="aggregate",
        requires=[],
        produces=["actual_dataset", "compare_dataset", "history_dataset", "meta_columns"],
        params={
            # enum: dataset_builder.compare_shift가 인식하는 값은 이 세 개뿐이다. LLM이 임의
            # 문자열을 지어내면 조용히 MoM으로 빠지므로, chat_options._catalog_digest가 이
            # 목록을 LLM에게 보여줘 못 지어내게 막는다.
            "compare_type": {"type": "str", "required": False, "default": None,
                              "enum": ["MoM", "QoQ", "YoY"]},
            "months_back":  {"type": "int", "required": False, "default": 3},
            # 기간 단위: month(기본)/quarter/year/week.
            "grain":        {"type": "str", "required": False, "default": None,
                              "enum": ["month", "quarter", "year", "week"]},
            # 스텝 단위 쿼리(2026-08-24) — resolve_dependencies가 같은 스텝의 다른 모듈들
            # 파라미터를 모아 자동으로 채운다(사용자가 직접 지정하는 값이 아니다).
            "dimensions":    {"type": "list", "required": False, "default": None},
            "measures":      {"type": "list", "required": False, "default": None},
            "needs_history": {"type": "bool", "required": False, "default": False},
            # 정기 보고서 SQL 캐싱(Phase 3) — 있으면 LLM 재생성 없이 이 SQL을 그대로 재사용.
            "query_sql":     {"type": "str", "required": False, "default": None},
        },
        tools={},                       # 순수 로드
        model_tier="none",
        narrative_hint="분석 대상 기간·데이터 규모가 분석에 충분한지 짧게 확인해 주는 도입 문단.",
        # 뿌리 모듈 — 대상 차원을 사용자가 고르지 않는다. dimensions/measures는
        # resolve_dependencies가 같은 스텝의 다른 모듈들에서 모아 채운다.
        sub_name_pool=None,
        accepts_measure=False,
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
        sub_name_pool="dimensions",
        sub_name_required=True,
        accepts_measure=True,
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
        sub_name_pool="dimensions",
        accepts_measure=True,
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
        sub_name_pool="dimensions",
        accepts_measure=True,
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
        sub_name_pool="dimensions",
        sub_name_required=True,
        accepts_measure=True,
    ),
    _spec(
        "ranking",
        purpose="항목 상위 순위(규모가 큰 순)를 제시(순위).",
        kind="aggregate",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": True},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
            # by/order는 이 모듈의 정체성이라 기본값이 곧 고정값이다 — 감소 큰 순을 보려면
            # 파라미터를 바꾸는 게 아니라 decline_ranking 모듈을 쓴다(2026-09-01).
            "order":     {"type": "str", "required": False, "default": "desc"},
            "by":        {"type": "str", "required": False, "default": "actual"},  # actual | variance
        },
        tools={"available": ["rank"], "default": "rank"},
        model_tier="fast",
        narrative_hint="상위권의 규모 차이가 큰지 고른지 짚어라. 순위와 증감 방향이 어긋나면 그 점을 말하라.",
        sub_name_pool="dimensions",
        sub_name_required=True,
        accepts_measure=True,
    ),
    _spec(
        "decline_ranking",
        # ranking과 같은 계산(run_ranking)이되 보는 방향이 반대다. 매출 큰 순 정렬에 묻히는
        # 감소 항목을 따로 부각하려고 둔다 — 예전에는 같은 스텝에 ranking을 두 번 넣어
        # 파라미터만 다르게 줬는데, 그러면 스텝 안에서 모듈을 지목할 수 없었다.
        purpose="많이 줄어든 항목 순위를 제시(감소 순위).",
        kind="aggregate",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={
            "dimension": {"type": "str", "required": True},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 10},
            "order":     {"type": "str", "required": False, "default": "asc"},
            "by":        {"type": "str", "required": False, "default": "variance"},
        },
        tools={"available": ["rank"], "default": "rank"},
        model_tier="fast",
        narrative_hint=(
            "감소폭이 큰 항목부터 짚어라. 규모가 큰 항목의 감소인지 작은 항목의 급감인지 "
            "구분해 말하라."
        ),
        sub_name_pool="dimensions",
        sub_name_required=True,
        accepts_measure=True,
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
        sub_name_pool=None,             # 기간축 누계 — 차원별로 나누지 않는다
        accepts_measure=True,
    ),
]

# ── 분석형 ────────────────────────────────────────────────────────────────────
_ANALYSIS = [
    _spec(
        "measure_summary",
        purpose="전체 매출 증감 총평(규모/율/수량/ASP/할인율).",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["measure_summary", "total_variance"],
        params={"measures": {"type": "list", "required": False, "default": None}},
        tools={},                       # 집계 계산
        model_tier="balanced",
        narrative_hint=(
            "증감이 물량(수량)에서 왔는지 단가(ASP)에서 왔는지, 할인율 변화가 이를 거들었는지 갈라 설명하라."
        ),
        # 전체 총평 — 측정값을 하나 고르는 게 아니라 전부 나열하는 것이 정체성이다.
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "dimension_impact",
        purpose="어느 차원이 변화를 가장 크게 설명하는지 제시.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["dimension_stats"],
        params={
            "measure":    {"type": "str", "required": False, "default": None},
            "dimensions": {"type": "list", "required": False, "default": None},
        },
        # shapley 기본 — dvi는 항목 수 적은 차원(예: 관리용 구분)이 과대평가되기 쉽다.
        tools={"available": ["shapley", "dvi"], "default": "shapley"},
        model_tier="balanced",
        narrative_hint=(
            "1위 차원이 전체 변화의 몇 %를 설명하는지만 짧게 말하라. DVI·HHI·집중도·평균Z 같은 "
            "내부 지표 용어는 본문에 쓰지 마라 — 구체적으로 어떤 항목이 얼마나 움직였는지는 "
            "다음 스텝(항목별 증감)이 다룬다."
        ),
        # sub_name 없음 — "여러 차원을 견줘 어느 것이 큰가"가 목적이라 하나를 고르면
        # 의미가 깨진다. "고객 안에서만 보고 싶다"는 within_contribution의 몫이다.
        sub_name_pool=None,
        accepts_measure=True,
    ),
    _spec(
        "within_contribution",
        purpose="항목 증감액/전체 증감액 기준 차원 내 기여도 상위 제시.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],
        produces=["within_contribution"],
        params={
            # required=False — 안 주면 dimension_impact의 Shapley 1위 차원으로 자동 대체(contribution.py).
            "dimension": {"type": "str", "required": False, "default": None},
            "measure":   {"type": "str", "required": False, "default": None},
            "top_n":     {"type": "int", "required": False, "default": 20},
        },
        tools={"available": ["contribution_rate"], "default": "contribution_rate"},
        model_tier="balanced",
        narrative_hint=(
            "증가를 이끈 항목과 그것을 깎아먹은 감소 항목을 함께 짚어라. 상위 항목이 전체 증감을 "
            "얼마나 설명하는지(누적 기여율), 신규·단종 항목이 끼어 있는지도 언급하라."
        ),
        # sub_name=None이 "알아서 골라라"(Shapley 1위)를 그대로 뜻한다 — 기능을 잃지 않고
        # 이름 층으로 올라간 자리다.
        sub_name_pool="dimensions",
        accepts_measure=True,
    ),
    _spec(
        "anomaly_detection",
        # 전 차원·전체 항목 대상, 금액·증감률 두 축으로 판정. dimension_impact가 만든 특정
        # measure 고정 싱글턴에 기대지 않고, 요청받은 measure로 직접 통계를 계산한다.
        purpose="금액·증감률 분포에서 크게 벗어난 이상 항목을 탐지.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=["outlier_result"],
        params={
            "measure":    {"type": "str", "required": False, "default": None},
            "sigma":      {"type": "float", "required": False, "default": 3.0},
            "dimension":  {"type": "str", "required": False, "default": None},
            "dimensions": {"type": "list", "required": False, "default": None},
            "top_n":      {"type": "int", "required": False, "default": 10},
            # 일시미구매(구매 주기상 미등장) 고객을 이상징후에서 제외할지.
            "exclude_dormant": {"type": "bool", "required": False, "default": True},
        },
        tools={"available": ["z_score", "iqr", "mad", "attainment"], "default": "z_score"},
        model_tier="balanced",
        narrative_hint=(
            "금액 영향이 큰 이탈부터 짚고, 어느 축(금액/증감률)에서 벗어났는지 구분해 설명하라. "
            "판정 불가 차원이 있으면 '이상 없음'이 아니라 '표본 부족으로 판정하지 못함'임을 분명히 하라. "
            "이상 항목이 없으면 그 자체가 결과임을 밝히고 임계값을 명시하라."
        ),
        sub_name_pool="dimensions",
        accepts_measure=True,
    ),
    _spec(
        "new_lost_detection",
        purpose="신규·이탈 항목의 건수와 금액 효과를 제시.",
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "new_party",
        # 옛 이름 new_customer_step. "고객"은 판매 도메인에서 party가 불리는 이름일 뿐이라
        # 역할 이름을 그대로 쓴다(구매 도메인이면 공급사, 생산이면 설비).
        purpose="party 차원의 신규 유입(진성신규·복귀)만 — 신규/이탈을 나눠 보는 스텝용.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],                        # new_lost_detection과 같은 계산(_shared.get_lifecycle_effects) 공유
        params={"top_n": {"type": "int", "required": False, "default": 10}},
        tools={},
        required_roles=["party"],
        model_tier="balanced",
        narrative_hint="진성신규와 복귀를 구분해 몇 명이 얼마만큼 유입됐는지 말하라. 이탈은 다른 스텝의 몫이다.",
        # 계산 로직이 party 고정이라 sub_name을 받지 않는다(required_roles가 그 제약을
        # 이미 선언한다). 임의 차원으로 일반화하려면 customer_lifecycle 쪽을 고쳐야 한다.
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "lost_party",
        purpose="party 차원의 이탈(진성이탈)만 — 신규/이탈을 나눠 보는 스텝용.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],
        params={"top_n": {"type": "int", "required": False, "default": 10}},
        tools={},
        required_roles=["party"],
        model_tier="balanced",
        narrative_hint=(
            "진성이탈 고객 수와 손실 금액을 말하라. 일시미구매(구매 주기상 미등장)는 이탈이 "
            "아니므로 건수만 참고로 밝히고 이탈로 세지 마라."
        ),
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "bridge",
        # 옛 이름 sales_bridge — 도메인 접두사를 뺐다. 계산은 이미 중립이다.
        # 상품·고객 두 관점의 가법 분해(각 관점 합계 = 전체 증감액).
        purpose="증감을 수량/정가ASP/할인/신규/이탈 효과로 분해.",
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
        sub_name_pool=None,             # 두 관점을 한꺼번에 내는 것이 정체성
        accepts_measure=False,
    ),
    _spec(
        "cross_drilldown",
        purpose="이상 항목이 어느 하위 항목에서 비롯됐는지 교차 분석.",
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
        # 상위 차원을 스스로 고르지 않고 앞 모듈 결과(outlier_result/dimension_stats)에서
        # 받아오는 2계층 구조라 sub_name이 맞지 않는다.
        sub_name_pool=None,
        accepts_measure=False,
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
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "abc_classification",
        # 분류 단위(grain)는 item 역할 기본, sub_name으로 명시 지정(§7.4). CV·등급변동은 진단적.
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
        # 계산이 리스트 파라미터를 읽으므로 sub_name은 dimensions로 펼쳐진다.
        sub_name_pool="dimensions",
        sub_name_param="dimensions",
        accepts_measure=False,
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
        sub_name_pool="dimensions",
        sub_name_param="dimensions",
        accepts_measure=False,
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
        # 전체 KPI를 한꺼번에 판정하는 것이 정체성이라 measure 하나를 고르지 않는다.
        sub_name_pool=None,
        accepts_measure=False,
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
        sub_name_pool=None,
        accepts_measure=False,
    ),
    # 손익 계단 5모듈 (옛 이름 revenue_step ~ ebit_step — `_step` 접미사를 빼고 계단 소속을
    # 드러내는 pnl_ 접두사로 바꿨다. opex_step→opex로 줄이면 ROLE_OPEX와 겹쳐 헷갈린다).
    #
    # 다섯을 measure 하나로 합치는 안은 기각했다(2026-09-01) — gross_margin·ebit은 계산으로
    # 만들어진 파생값이라 대응 역할이 없고, 억지로 ROLE에 넣으면 "도메인 지식은 데이터소스
    # 정의에 둔다"는 schema.py의 원칙이 깨진다. 게다가 다섯은 이미 _shared.get_pnl_ladder
    # 캐시를 공유해 계산 중복이 없으므로 합쳐서 얻을 것도 없다.
    #
    # 공통 옵션: sub_name을 지정하면 그 단계 금액을 차원별 상세 표로 분해해 덧붙인다
    # (예: 제품별 매출원가). 미지정 시 총계 요약만.
    _spec(
        "pnl_revenue",
        purpose="손익 계단의 매출(Revenue) 단계.",
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "pnl_cogs",
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "pnl_gross_margin",
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "pnl_opex",
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "pnl_ebit",
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "pnl_driver",
        purpose="영업이익(EBIT) 증감을 매출·매출원가·판매관리비 효과로 분해 — 손익의 원인 분석.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset"],
        produces=[],                        # pnl_revenue~pnl_ebit과 같은 계산(get_pnl_ladder)을 공유
        # sub_name 지정 시 항목별 ΔEBIT 분해 표(매출/원가/판관비 효과) 추가.
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
        sub_name_pool="dimensions",
        accepts_measure=False,
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "dead_stock",
        # 옛 이름 dead_stock_step.
        purpose="미회전(Dead Stock) 항목만 — 재고 분석의 Dead Stock 스텝용.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "inventory_metrics"],
        produces=[],                        # inventory_turnover가 만든 이름표를 필터링만(재계산 없음)
        params={"top_n": {"type": "int", "required": False, "default": 20}},
        tools={},
        model_tier="balanced",
        narrative_hint="미회전 항목 수와 거기 묶인 재고 규모를 말하고, 처분·폐기 검토 대상임을 밝혀라.",
        # 차원은 inventory_turnover가 정한 것을 따라간다 — 스스로 고르지 않는다.
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "slow_moving",
        # 옛 이름 slow_moving_step.
        purpose="장기체화(Slow Moving) 항목만 — 재고 분석의 Slow Moving 스텝용.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "inventory_metrics"],
        produces=[],
        params={"top_n": {"type": "int", "required": False, "default": 20}},
        tools={},
        model_tier="balanced",
        narrative_hint="재고일수가 긴 항목이 몇 개고 거기 묶인 재고 규모가 얼마인지 말하라(미회전과는 다른 항목군).",
        sub_name_pool=None,
        accepts_measure=False,
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
        sub_name_pool="dimensions",
        accepts_measure=False,
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
        sub_name_pool="dimensions",
        accepts_measure=False,
    ),
    _spec(
        "volume_effect",
        purpose="순수 물량(Volume) 효과 — 믹스·단가를 제외한 판매량 자체의 증감분.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],  # 비중은 total_variance 기준
        required_roles=["quantity"],
        produces=[],                        # 계산은 _shared.get_pvm_effects/get_bridge_effects 캐시(내부 파생물)
        params={
            "top_n": {"type": "int", "required": False, "default": 10},   # bridge 툴일 때만 항목표에 쓰임
            # dimension 없음 — 실제로 안 읽는 파라미터라 뺐다(있으면 품목 없는 데이터셋에서 스텝째로 빠짐).
        },
        tools={"available": ["pvm", "bridge_decompose"], "default": "bridge_decompose"},
        # tools={"available": ["pvm", "bridge_decompose"], "default": "pvm"},
        model_tier="balanced",
        narrative_hint=(
            "판매량 자체가 늘었는지 줄었는지, 그 규모가 전체 증감에서 차지하는 비중을 말하라. "
            "항목별 표가 있으면(bridge 방식) 어떤 상품이 물량 효과를 주도했는지도 짚어라."
        ),
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "price_effect",
        purpose="단가(Price) 효과 — 물량 변화를 제외한 항목별 판매 단가 변화분.",
        kind="analysis",
        requires=["actual_dataset", "compare_dataset", "total_variance"],
        required_roles=["quantity"],
        produces=[],
        params={
            "top_n": {"type": "int", "required": False, "default": 10},
        },
        tools={"available": ["pvm", "bridge_decompose"], "default": "bridge_decompose"},
        # tools={"available": ["pvm", "bridge_decompose"], "default": "pvm"},
        model_tier="balanced",
        narrative_hint=(
            "단가가 오른 방향인지 내린 방향인지, 전체 증감에서 차지하는 비중을 말하라. "
            "항목별 표가 있으면(bridge 방식) 어떤 상품의 단가 변화가 주도했는지도 짚어라."
        ),
        sub_name_pool=None,
        accepts_measure=False,
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
        sub_name_pool=None,
        accepts_measure=False,
    ),
    _spec(
        "conclusion",
        purpose="모든 스텝의 집계 결과를 바탕으로 최종 경영 인사이트(결론)를 작성.",
        kind="analysis",
        # 어떤 조합의 스텝이 앞에 오든 실행 가능해야 하므로 requires를 선언하지 않는다 —
        # build_conclusion이 ctx에서 있는 대로 골라 쓴다. "항상 맨 뒤"는
        # operations._TAIL_MODULE_IDS 잠금으로 보장한다.
        requires=[],
        produces=[],
        params={},
        tools={},                           # 결론 방식은 하나뿐 — 대체 툴 없음
        model_tier="quality",               # 실서비스에서 상위 모델(Opus 등)로 지정할 자리
        narrative_hint="",                  # 안 쓰임 — 결론은 narrate 단계를 거치지 않고 스스로 완성된 본문을 낸다.
        sub_name_pool=None,
        accepts_measure=False,
    ),
]

MODULE_REGISTRY: dict[str, ModuleSpec] = {m.module_id: m for m in (_AGGREGATE + _ANALYSIS)}


def get_module_registry() -> dict[str, ModuleSpec]:
    return dict(MODULE_REGISTRY)
