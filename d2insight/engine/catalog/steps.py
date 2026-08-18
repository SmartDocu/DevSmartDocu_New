"""Step Registry (§7) — 판매분석 프리셋 섹션.

각 프리셋 섹션은 표시 제목과 디폴트 모듈 목록을 갖는다. 빈 섹션은 없다(§3.1).
step_id는 영문 식별자, title은 독자에게 보이는 한글 제목이다(§ 마커 없음).

차원(dimension)·측정값(measure) 값은 역할 이름(schema.py의 ROLE_*: item/party/amount/
quantity 등)으로 쓴다 — 데이터소스가 바뀌어도 이 파일이 안 깨진다(2026-07-24, G9).
다만 아래 두 경우는 역할이 없거나 모호해 물리명을 그대로 둔다:
  - item_group 역할은 이 데이터소스에서 제품모델/제품중분류/제품대분류 세 컬럼이 공유해
    schema.column()이 첫 번째 것만 돌려준다(모호) — "제품중분류"는 물리명 그대로.
  - "지역_국가"/"채널"은 schema.py에 대응 역할 자체가 없다(region/channel 역할 미정의).
  - dimensions(복수, 리스트) 파라미터는 options.py의 options_to_plan 경로만 역할→물리명
    변환을 지원한다(planner.py의 validate_plan은 단수만) — 그래서 아직 물리명 그대로 둔다.
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
            {"module_id": "actual_aggregate", "params": {"dimension": "제품중분류"}},
            {"module_id": "actual_aggregate", "params": {"dimension": "지역_국가"}},
        ],
    },
    "variance_cause": {
        "title": "변동 원인 분석",
        "default_modules": [
            {"module_id": "dimension_impact"},
            {"module_id": "within_contribution", "params": {"dimension": "item"}},
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

    # ── 시나리오 1 "매출 증감 원인 분석" 전용 스텝 (전개 단계 1) ──────────────────
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
            {"module_id": "actual_aggregate", "params": {"dimension": "party"}},
        ],
    },
    "s1_region": {
        "title": "지역별 분석",
        "default_modules": [
            {"module_id": "actual_aggregate", "params": {"dimension": "지역_국가"}},
        ],
    },
    "s1_top_products": {
        "title": "Top 제품",
        "default_modules": [
            {"module_id": "ranking", "params": {"dimension": "item", "by": "actual"}},
        ],
    },
    "s1_cause_ranking": {
        "title": "원인 순위",
        "default_modules": [
            {"module_id": "dimension_impact"},
            {"module_id": "within_contribution", "params": {"dimension": "item"}},
        ],
    },

    # ── 시나리오 2 "KPI Executive Summary" 전용 스텝 (2026-07-24) ───────────────
    # 원본 스텝: 매출·이익·재고·생산성·품질(KPI 총괄) ↓ 이상 KPI 탐지 ↓ 원인 분석 ↓
    # 요약 작성 ↓ Action Item. 생산성·품질은 카탈로그에 대응 모듈·역할이 아예 없어
    # 이번엔 제외(사용자 결정 2026-07-24) — 필요 시 요청 → 신규 모듈 추가로 카탈로그를 넓힌다
    # (결정기록_2026-07-24_옵션체계.md §3). 요약 작성/Action Item은 다른 시나리오와 같이
    # conclusion 스텝(scenarios.py에서 맨 뒤에 명시)이 담당하므로 별도 등록하지 않는다.
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
            {"module_id": "within_contribution", "params": {"dimension": "item"}},
        ],
    },

    # ── 시나리오 3 "고객 분석" 전용 스텝 ────────────────────────────────────────
    # 원본 스텝: 신규 고객 ↓ 이탈 고객(별도) — new_lost_detection은 통합 모듈이라 리프
    # customer_lifecycle의 두 함수로 나눔(2026-07-21, mix_effect 분리와 같은 패턴).
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
    # SKU 스텝(2026-07-21): "제품별 매출"과 합쳐져 있던 것을 분리 — 제품 구성 자체(신규·단종
    # SKU 수)를 먼저 보여주고, 그다음 매출·판매량 실적을 본다(원본 스텝 순서: SKU→판매량→매출).
    "s4_sku": {
        "title": "제품 구성(SKU 현황)",
        "default_modules": [
            {"module_id": "new_lost_detection", "params": {"dimensions": ["제품"]}},
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
            {"module_id": "abc_classification", "params": {"dimensions": ["제품"]}},
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

    # ── 시나리오 5 "손익 분석" 전용 스텝 (2026-07-21) ───────────────────────────
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

    # ── 시나리오 6 "재고 분석" 전용 스텝 (2026-07-21) ───────────────────────────
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

    # ── 결론 — 모든 시나리오 공통, 항상 맨 뒤(2026-07-28, 7단계) ───────────────
    "conclusion": {
        "title": "결론",
        "default_modules": [
            {"module_id": "conclusion"},
        ],
    },
}


def get_step_registry() -> dict[str, dict]:
    return dict(STEP_REGISTRY)
