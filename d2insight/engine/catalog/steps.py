"""Step Registry (§7) — 스텝 프리셋.

각 프리셋 스텝은 표시 제목과 디폴트 모듈 목록을 갖는다. 빈 스텝은 없다.

── 카탈로그 재구조화 (2026-09-01) ──────────────────────────────────────────────
이 파일은 이제 scenarios.py와 **같은 모양**이다 — 참조만 나열한다.

    scenarios.py :  "steps": [{"step_id": "turnover"}, ...]
    steps.py     :  "default_modules": [{"module_name": "inventory_turnover"}, ...]

바뀐 것 두 가지:

**① step_id에서 시나리오 접두사(s1_~s6_)를 뺐다.**
스텝은 시나리오에 종속되지 않는 재사용 부품이다. `s6_abc`는 "재고 분석 전용"이라는 뜻이
되어 다른 시나리오가 같은 스텝을 쓰지 못하게 막는다. 시나리오는 이 카탈로그에서 필요한
스텝을 골라 쓸 뿐이고, 등록되지 않은 요청이 와도 LLM이 여기서 골라 조립한다.

**② params가 사라지고 module_id가 세 필드 조합이 됐다.**

    이전:  {"module_id": "ranking", "params": {"dimension": "item", "by": "actual"}}
    지금:  {"module_name": "ranking", "sub_name": "item"}

  measure     무엇을 분석하는가 — 생략하면 데이터소스의 핵심 측정값
  module_name 어떻게 분석하는가
  sub_name    무엇별로 보는가 — 생략하면 모듈이 알아서 고른다
              (within_contribution은 Shapley 1위 차원, abc_classification은 item 역할)

`top_n` 같은 "얼마나"는 여전히 params지만, 프리셋은 스펙 기본값을 그대로 쓰므로 여기
적지 않는다. 값을 바꾸는 것은 사용자 편집의 몫이다.

sub_name 값은 **역할 이름**(item/party/item_group/region, schema.py의 ROLE_*)으로 쓴다 —
데이터소스가 바뀌어도 이 파일이 안 깨진다. 역할이 없는 차원(채널·브랜드 등)은 사용자가
요청할 때 물리명으로 채워지며, 프리셋에는 넣지 않는다.
"""
from __future__ import annotations

STEP_REGISTRY: dict[str, dict] = {
    # ── 공통·판매분석 ───────────────────────────────────────────────────────────
    "data_check": {
        "title": "분석 대상 자료 확인",
        "topics": ["any"],
        "default_modules": [
            {"module_name": "period_dataset"},
        ],
    },
    # 옛 revenue_overview와 s1_revenue_variance는 제목·모듈이 완전히 같아 하나로 합쳤다.
    "revenue_overview": {
        "title": "매출 증감 총평",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "measure_summary"},
        ],
    },
    "performance_overview": {
        "title": "실적 개요",
        "topics": ["sales"],
        "default_modules": [
            # 예전에는 actual_aggregate를 한 스텝에 두 번 넣고 params로만 갈랐다. 이제
            # sub_name이 달라 조합이 서로 다른 모듈이 된다 — 스텝 안에서 지목할 수 있다.
            {"module_name": "actual_aggregate", "sub_name": "item_group"},
            {"module_name": "actual_aggregate", "sub_name": "region"},
        ],
    },
    "variance_cause": {
        "title": "변동 원인 분석",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "dimension_impact"},
            {"module_name": "within_contribution"},
            {"module_name": "bridge"},
        ],
    },
    "anomaly": {
        "title": "이상징후",
        "topics": ["any"],
        "default_modules": [
            {"measure": "amount", "module_name": "anomaly_detection"},
            {"module_name": "new_lost_detection"},
        ],
    },
    "cross_drill": {
        "title": "교차 드릴다운",
        "topics": ["any"],
        "default_modules": [
            {"module_name": "cross_drilldown"},
        ],
    },

    # ── 매출 증감 원인 분석 계열 ────────────────────────────────────────────────
    "period_compare": {
        "title": "기간 비교",
        "topics": ["any"],
        "default_modules": [
            {"module_name": "period_dataset"},
            {"module_name": "trend"},
        ],
    },
    "volume": {
        "title": "물량(Volume)",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "volume_effect"},
        ],
    },
    "price": {
        "title": "단가(Price)",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "price_effect"},
        ],
    },
    "mix": {
        "title": "구성 이동(Mix)",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "mix_effect"},
        ],
    },
    "customer_analysis": {
        "title": "고객별 분석",
        "topics": ["customer"],
        "default_modules": [
            {"module_name": "composition", "sub_name": "party"},
            {"module_name": "composition", "sub_name": "item_group"},
        ],
    },
    "region_analysis": {
        "title": "지역별 분석",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "actual_aggregate", "sub_name": "region"},
        ],
    },
    "top_products": {
        "title": "Top 제품",
        "topics": ["item"],
        "default_modules": [
            {"module_name": "ranking", "sub_name": "item"},
            # 매출 큰 순 정렬에 묻히는 감소 항목을 따로 부각. 예전에는 같은 ranking을
            # by/order만 바꿔 두 번 넣었는데, 이제 별도 모듈이라 지목·교체가 된다.
            {"module_name": "decline_ranking", "sub_name": "item"},
        ],
    },
    "cause_ranking": {
        "title": "원인 순위",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "dimension_impact"},
            {"module_name": "within_contribution"},
        ],
    },

    # ── KPI Executive Summary 계열 ──────────────────────────────────────────────
    # 생산성·품질은 카탈로그에 대응 모듈·역할이 없어 제외. 요약 작성/Action Item은
    # 다른 시나리오와 같이 conclusion 스텝이 담당하므로 별도 등록하지 않는다.
    "revenue_kpi": {
        "title": "매출 KPI",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "measure_summary"},
        ],
    },
    "profit_kpi": {
        "title": "이익 KPI",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_summary"},
        ],
    },
    "inventory_kpi": {
        "title": "재고 KPI",
        "topics": ["inventory"],
        "default_modules": [
            {"module_name": "inventory_turnover"},
        ],
    },
    "kpi_alert": {
        "title": "이상 KPI 탐지",
        # measure(KPI) 레벨 스텝 — 금액·이익·재고 지표를 다룬다.
        "topics": ["sales", "pnl", "inventory"],
        "default_modules": [
            {"module_name": "kpi_alert"},
        ],
    },
    "cause_analysis": {
        "title": "원인 분석",
        "topics": ["sales"],
        "default_modules": [
            {"module_name": "dimension_impact"},
            {"module_name": "within_contribution"},
        ],
    },

    # ── 고객 분석 계열 ──────────────────────────────────────────────────────────
    # new_lost_detection은 여러 차원 통합 모듈이라, party만 다루는 new_party/lost_party로
    # 따로 쓴다(계산 로직이 party 고정이라 sub_name을 받지 않는다).
    "new_customer": {
        "title": "신규 고객",
        "topics": ["customer"],
        "default_modules": [
            {"module_name": "new_party"},
        ],
    },
    "lost_customer": {
        "title": "이탈 고객",
        "topics": ["customer"],
        "default_modules": [
            {"module_name": "lost_party"},
        ],
    },
    "vip_customer": {
        "title": "VIP 고객",
        "topics": ["customer"],
        "default_modules": [
            {"module_name": "ranking", "sub_name": "party"},
        ],
    },
    "customer_contribution": {
        "title": "고객 매출 기여도",
        "topics": ["customer"],
        "default_modules": [
            {"module_name": "within_contribution", "sub_name": "party"},
        ],
    },

    # ── 제품 분석 계열 ──────────────────────────────────────────────────────────
    "sku_status": {
        "title": "제품 구성(SKU 현황)",
        "topics": ["item"],
        "default_modules": [
            # sub_name="item"으로 party(고객)가 같이 나오는 걸 막는다.
            {"module_name": "new_lost_detection", "sub_name": "item"},
        ],
    },
    "product_sales": {
        "title": "제품별 매출",
        "topics": ["item"],
        "default_modules": [
            {"module_name": "actual_aggregate", "sub_name": "item"},
        ],
    },
    "profit": {
        "title": "이익",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_summary"},
        ],
    },
    "product_qty": {
        "title": "제품별 판매량",
        "topics": ["item"],
        "default_modules": [
            {"measure": "quantity", "module_name": "actual_aggregate", "sub_name": "item"},
        ],
    },
    "item_abc": {
        "title": "제품 ABC-XYZ",
        "topics": ["item"],
        "default_modules": [
            {"module_name": "abc_classification"},   # sub_name 생략 → item 역할 자동
        ],
    },
    "item_lifecycle": {
        "title": "제품 수명주기",
        "topics": ["item"],
        "default_modules": [
            {"module_name": "product_lifecycle"},
        ],
    },
    "item_anomaly": {
        "title": "문제 제품(이상징후)",
        "topics": ["item"],
        "default_modules": [
            {"module_name": "anomaly_detection"},
        ],
    },

    # ── 손익 분석 계열 ──────────────────────────────────────────────────────────
    # 5스텝(Revenue~EBIT)이 같은 계산(_shared.get_pnl_ladder)을 공유하는 리프 모듈이라
    # 다중 실행 충돌이 없다. pnl_driver는 그 값들을 다시 묶어 EBIT 증감의 원인을 가른다.
    "pnl_revenue": {
        "title": "매출(Revenue)",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_revenue"},
        ],
    },
    "pnl_cogs": {
        "title": "매출원가(COGS)",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_cogs"},
        ],
    },
    "pnl_gross_margin": {
        "title": "매출총이익(Gross Margin)",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_gross_margin"},
        ],
    },
    "pnl_opex": {
        "title": "판매관리비(OPEX)",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_opex"},
        ],
    },
    "pnl_ebit": {
        "title": "영업이익(EBIT)",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_ebit"},
        ],
    },
    "pnl_cause": {
        "title": "원인 분석",
        "topics": ["pnl"],
        "default_modules": [
            {"module_name": "pnl_driver"},
        ],
    },

    # ── 재고 분석 계열 ──────────────────────────────────────────────────────────
    # dead_stock/slow_moving은 inventory_turnover가 만든 "inventory_metrics" 이름표를
    # 필터링만 하는 리프 모듈이다 — 차원도 그쪽이 정한 것을 따라간다.
    "inventory_abc": {
        "title": "재고 ABC",
        "topics": ["inventory"],
        "default_modules": [
            {"module_name": "abc_classification"},
        ],
    },
    "turnover": {
        "title": "재고회전율",
        "topics": ["inventory"],
        "default_modules": [
            {"module_name": "inventory_turnover"},
        ],
    },
    "dead_stock": {
        "title": "Dead Stock",
        "topics": ["inventory"],
        "default_modules": [
            {"module_name": "dead_stock"},
        ],
    },
    "slow_moving": {
        "title": "Slow Moving",
        "topics": ["inventory"],
        "default_modules": [
            {"module_name": "slow_moving"},
        ],
    },
    "safety_stock": {
        "title": "Safety Stock",
        "topics": ["inventory"],
        "default_modules": [
            {"module_name": "safety_stock"},
        ],
    },

    # ── 결론 — 모든 시나리오 공통, 항상 맨 뒤 ───────────────────────────────────
    "conclusion": {
        "title": "결론",
        # 전용 주제 — 결론 스텝에는 결론 모듈만 온다(matrix.EXCLUSIVE).
        "topics": ["closing"],
        "default_modules": [
            {"module_name": "conclusion"},
        ],
    },
}


# 카탈로그에 없는 스텝(LLM이 조합하며 새로 지은 스텝)의 step_id 접두어.
# 스텝을 지목하는 값은 step_id 하나로 통일하되, 이 접두어로 "카탈로그 조회 대상인지"를
# 가른다. 값은 보고서 한 건 안에서만 유일하면 된다 — 다른 보고서와 마주칠 일이 없다.
TMP_STEP_PREFIX = "tmp_"


def is_catalog_step(step_id: str | None) -> bool:
    """카탈로그에서 프리셋을 꺼내도 되는 step_id인가."""
    return bool(step_id) and not step_id.startswith(TMP_STEP_PREFIX)


def get_step_registry() -> dict[str, dict]:
    return dict(STEP_REGISTRY)
