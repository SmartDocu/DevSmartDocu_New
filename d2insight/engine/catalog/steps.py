"""Step Registry (§7) — 판매분석 프리셋 스텝.

각 프리셋 스텝은 표시 제목과 디폴트 모듈 목록을 갖는다. 빈 스텝은 없다.
step_id는 영문 식별자, title은 독자에게 보이는 한글 제목이다.

차원(dimension)·측정값(measure) 값은 역할 이름(schema.py의 ROLE_*: item/party/amount/
quantity/item_group/region 등)으로 쓴다 — 데이터소스가 바뀌어도 이 파일이 안 깨진다.
"채널"만 대응 역할이 없어 물리명을 직접 써야 한다.

dimensions(복수, 리스트) 파라미터는 validate_plan의 역할→물리명 자동 변환을 지원하지
않는다(options.py의 options_to_plan 경로만 지원) — 여러 차원을 한 번에 지정해야 하면
물리명을 그대로 써야 한다. 차원이 1개뿐이면 단수 dimension(역할명)을 쓰거나(s4_sku),
파라미터를 생략해 모듈 자체의 기본 역할에 맡긴다(s4_abc).
"""
from __future__ import annotations

STEP_REGISTRY: dict[str, dict] = {
    "data_check": {
        "title": "분석 대상 자료 확인",
        "default_modules": [
            {"module_id": "period_dataset"},
        ],
    },
    "revenue_overview": {
        "title": "매출 증감 총평",
        "default_modules": [
            {"module_id": "measure_summary"},
        ],
    },
    "performance_overview": {
        "title": "실적 개요",
        "default_modules": [
            {"module_id": "actual_aggregate", "params": {"dimension": "item_group"}},
            {"module_id": "actual_aggregate", "params": {"dimension": "region"}},
        ],
    },
    "variance_cause": {
        "title": "변동 원인 분석",
        "default_modules": [
            {"module_id": "dimension_impact"},
            {"module_id": "within_contribution"},
            {"module_id": "sales_bridge"},
        ],
    },
    "anomaly": {
        "title": "이상징후",
        "default_modules": [
            {"module_id": "anomaly_detection", "params": {"measure": "amount"}},
            {"module_id": "new_lost_detection"},
        ],
    },
    "cross_drill": {
        "title": "교차 드릴다운",
        "default_modules": [
            {"module_id": "cross_drilldown"},
        ],
    },

    # ── 시나리오 1 "매출 증감 원인 분석" 전용 스텝 ──────────────────────────────
    # within_contribution은 싱글턴 이름표를 생산하므로 한 계획에 1회만(원인 순위 스텝).
    # Customer/Region/Top은 리프 모듈(actual_aggregate/ranking)로 두어 다중 실행 충돌을 피한다.
    "s1_period_compare": {
        "title": "기간 비교",
        "default_modules": [
            {"module_id": "period_dataset"},
            {"module_id": "trend"},
        ],
    },
    "s1_revenue_variance": {
        "title": "매출 증감 총평",
        "default_modules": [
            {"module_id": "measure_summary"},
        ],
    },
    "s1_volume": {
        "title": "물량(Volume)",
        "default_modules": [
            {"module_id": "volume_effect"},
        ],
    },
    "s1_price": {
        "title": "단가(Price)",
        "default_modules": [
            {"module_id": "price_effect"},
        ],
    },
    "s1_mix": {
        "title": "구성 이동(Mix)",
        "default_modules": [
            {"module_id": "mix_effect"},
        ],
    },
    "s1_customer": {
        "title": "고객별 분석",
        "default_modules": [
            {"module_id": "composition", "params": {"dimension": "party"}},
            {"module_id": "composition", "params": {"dimension": "item_group", "top_n": 10}},
        ],
    },
    "s1_region": {
        "title": "지역별 분석",
        "default_modules": [
            {"module_id": "actual_aggregate", "params": {"dimension": "region"}},
        ],
    },
    "s1_top_products": {
        "title": "Top 제품",
        "default_modules": [
            {"module_id": "ranking", "params": {"dimension": "item", "by": "actual"}},
            # 매출 큰 순 정렬에 묻히는 감소 항목을 따로 부각.
            {"module_id": "ranking", "params": {"dimension": "item", "by": "variance", "order": "asc"}},
        ],
    },
    "s1_cause_ranking": {
        "title": "원인 순위",
        "default_modules": [
            {"module_id": "dimension_impact"},
            {"module_id": "within_contribution"},
        ],
    },

    # ── 시나리오 2 "KPI Executive Summary" 전용 스텝 ────────────────────────────
    # 생산성·품질은 카탈로그에 대응 모듈·역할이 없어 제외. 요약 작성/Action Item은
    # 다른 시나리오와 같이 conclusion 스텝이 담당하므로 별도 등록하지 않는다.
    "s2_revenue_kpi": {
        "title": "매출 KPI",
        "default_modules": [
            {"module_id": "measure_summary"},
        ],
    },
    "s2_profit_kpi": {
        "title": "이익 KPI",
        "default_modules": [
            {"module_id": "pnl_summary"},
        ],
    },
    "s2_inventory_kpi": {
        "title": "재고 KPI",
        "default_modules": [
            {"module_id": "inventory_turnover"},
        ],
    },
    "s2_kpi_alert": {
        "title": "이상 KPI 탐지",
        "default_modules": [
            {"module_id": "kpi_alert"},
        ],
    },
    "s2_kpi_cause": {
        "title": "원인 분석",
        "default_modules": [
            {"module_id": "dimension_impact"},
            {"module_id": "within_contribution"},
        ],
    },

    # ── 시나리오 3 "고객 분석" 전용 스텝 ────────────────────────────────────────
    # new_lost_detection은 item+party 통합 모듈이라, party만 다루는 customer_lifecycle의
    # 두 함수(신규/이탈)로 따로 쓴다.
    "s3_new_customer": {
        "title": "신규 고객",
        "default_modules": [
            {"module_id": "new_customer_step"},
        ],
    },
    "s3_lost_customer": {
        "title": "이탈 고객",
        "default_modules": [
            {"module_id": "lost_customer_step"},
        ],
    },
    "s3_vip": {
        "title": "VIP 고객",
        "default_modules": [
            {"module_id": "ranking", "params": {"dimension": "party", "by": "actual"}},
        ],
    },
    "s3_customer_contribution": {
        "title": "고객 매출 기여도",
        "default_modules": [
            {"module_id": "within_contribution", "params": {"dimension": "party"}},
        ],
    },

    # ── 시나리오 4 "제품 분석" 전용 스텝 ────────────────────────────────────────
    "s4_sku": {
        "title": "제품 구성(SKU 현황)",
        "default_modules": [
            # dimension(단수, 역할명 "item")을 써서 party(고객)가 같이 나오는 걸 막는다.
            {"module_id": "new_lost_detection", "params": {"dimension": "item"}},
        ],
    },
    "s4_product_sales": {
        "title": "제품별 매출",
        "default_modules": [
            {"module_id": "actual_aggregate", "params": {"dimension": "item"}},
        ],
    },
    "s4_profit": {
        "title": "이익",
        "default_modules": [
            {"module_id": "pnl_summary"},
        ],
    },
    "s4_product_qty": {
        "title": "제품별 판매량",
        "default_modules": [
            {"module_id": "actual_aggregate", "params": {"dimension": "item", "measure": "quantity"}},
        ],
    },
    "s4_abc": {
        "title": "제품 ABC-XYZ",
        "default_modules": [
            {"module_id": "abc_classification"},   # dimensions 생략 → item 역할 자동 사용
        ],
    },
    "s4_lifecycle": {
        "title": "제품 수명주기",
        "default_modules": [
            {"module_id": "product_lifecycle"},
        ],
    },
    "s4_problem": {
        "title": "문제 제품(이상징후)",
        "default_modules": [
            {"module_id": "anomaly_detection"},
        ],
    },

    # ── 시나리오 5 "손익 분석" 전용 스텝 ─────────────────────────────────────────
    # 5스텝(Revenue~EBIT)이 같은 계산(_shared.get_pnl_ladder)을 공유하는 리프 모듈이라
    # 다중 실행 충돌이 없다. pnl_driver는 그 값들을 다시 묶어 EBIT 증감의 원인을 가른다.
    "s5_revenue": {
        "title": "매출(Revenue)",
        "default_modules": [
            {"module_id": "revenue_step"},
        ],
    },
    "s5_cogs": {
        "title": "매출원가(COGS)",
        "default_modules": [
            {"module_id": "cogs_step"},
        ],
    },
    "s5_gross_margin": {
        "title": "매출총이익(Gross Margin)",
        "default_modules": [
            {"module_id": "gross_margin_step"},
        ],
    },
    "s5_opex": {
        "title": "판매관리비(OPEX)",
        "default_modules": [
            {"module_id": "opex_step"},
        ],
    },
    "s5_ebit": {
        "title": "영업이익(EBIT)",
        "default_modules": [
            {"module_id": "ebit_step"},
        ],
    },
    "s5_cause": {
        "title": "원인 분석",
        "default_modules": [
            {"module_id": "pnl_driver"},
        ],
    },

    # ── 시나리오 6 "재고 분석" 전용 스텝 ─────────────────────────────────────────
    # 원본 순서: ABC↓회전율↓Dead Stock↓Slow Moving↓Safety Stock↓개선안. Dead/Slow는
    # inventory_turnover가 만든 "inventory_metrics" 이름표를 필터링만 하는 리프 모듈이다.
    "s6_abc": {
        "title": "재고 ABC",
        "default_modules": [
            {"module_id": "abc_classification"},
        ],
    },
    "s6_turnover": {
        "title": "재고회전율",
        "default_modules": [
            {"module_id": "inventory_turnover"},
        ],
    },
    "s6_dead_stock": {
        "title": "Dead Stock",
        "default_modules": [
            {"module_id": "dead_stock_step"},
        ],
    },
    "s6_slow_moving": {
        "title": "Slow Moving",
        "default_modules": [
            {"module_id": "slow_moving_step"},
        ],
    },
    "s6_safety_stock": {
        "title": "Safety Stock",
        "default_modules": [
            {"module_id": "safety_stock"},
        ],
    },

    # ── 결론 — 모든 시나리오 공통, 항상 맨 뒤 ───────────────────────────────────
    "conclusion": {
        "title": "결론",
        "default_modules": [
            {"module_id": "conclusion"},
        ],
    },
}


def get_step_registry() -> dict[str, dict]:
    return dict(STEP_REGISTRY)
