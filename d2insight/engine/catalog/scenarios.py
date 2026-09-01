"""수동 모드용 유형별 기본 세트 (§4.2).

**엔진 바깥의 권장 템플릿**이다(module_catalog_schema.md §7 엔진 분리 원칙). 수동 모드 진입 시
계획기 계층이 get_scenario(report_type)으로 시작 plan을 꺼내 사용자에게 편집용으로 제시할 뿐,
실행 엔진(runner.run_plan)은 report_type도 이 레지스트리도 모른다 → §7.3 준수.

값은 8장 JSON과 동일한 형식(steps 배열)이다.
"""
from __future__ import annotations

SCENARIO_REGISTRY: dict[str, dict] = {
    "판매분석": {
        "report_title": "판매분석 보고서",
        "steps": [
            {"step_id": "data_check"},
            {"step_id": "revenue_overview"},
            {"step_id": "performance_overview"},
            {"step_id": "variance_cause"},
            {"step_id": "anomaly"},
            {"step_id": "cross_drill"},
            {"step_id": "conclusion"},
        ],
    },

    # ── 전개 단계 1 · 시나리오 1 ─────────────────────────────────────────────────
    # 스텝(스텝 프리셋)의 나열로 시나리오를 구성한다. 결론(conclusion)은 모든 시나리오
    # 맨 뒤에 명시적으로 나열한다 — 예전엔 특수 처리로 자동으로 붙었으나, 이제 다른
    # 스텝처럼 옵션 JSON에 보이는 스텝이다(2026-07-28, 7단계 — 결론 스텝화). 다만
    # operations._TAIL_MODULE_IDS로 잠겨 있어 이동·삭제는 안 된다.
    #
    # 원본은 9스텝(기간비교/Variance/Volume/Price/Mix/Customer/Region/Top Products/원인Ranking)
    # 이나, Mix는 뺀 8스텝이 기본 프리셋이다(2026-07-24 결정). Volume·Price의 기본 계산
    # (bridge_decompose)과 Mix(PVM 고정)가 서로 다른 회계 체계라 나란히 두면 검산이 안 맞는다.
    # Mix는 카탈로그(STEP_REGISTRY의 mix)에는 그대로 있어 옵션으로 추가할 수 있다.
    # 근거: 시나리오_스텝_정의.md ※ / 결정기록_2026-07-24_옵션체계.md §1.
    "매출 증감 원인 분석": {
        "report_title": "매출 증감 원인 분석 보고서",
        "steps": [
            {"step_id": "period_compare"},       # 기간비교
            {"step_id": "revenue_overview"},     # Variance
            {"step_id": "volume"},               # Volume
            {"step_id": "price"},                # Price
            {"step_id": "customer_analysis"},    # Customer
            {"step_id": "region_analysis"},      # Region
            {"step_id": "top_products"},         # Top Products
            {"step_id": "cause_ranking"},        # 원인 Ranking
            {"step_id": "anomaly"},              # 이상징후
            {"step_id": "cross_drill"},          # 교차 드릴다운
            {"step_id": "conclusion"},
        ],
    },

    # ── 전개 단계 1 · 시나리오 2 (2026-07-24) ───────────────────────────────────
    # 원본 5스텝 중 매출·이익·재고·이상탐지·원인분석만 등록. 생산성·품질은 카탈로그에
    # 대응 모듈이 없어 제외(결정기록_2026-07-24_옵션체계.md §3).
    "KPI Executive Summary": {
        "report_title": "KPI Executive Summary 보고서",
        "steps": [
            {"step_id": "revenue_kpi"},      # 매출 KPI
            {"step_id": "profit_kpi"},       # 이익 KPI
            {"step_id": "inventory_kpi"},    # 재고 KPI
            {"step_id": "kpi_alert"},        # 이상 KPI 탐지
            {"step_id": "cause_analysis"},   # 원인 분석
            {"step_id": "conclusion"},
        ],
    },

    "고객 분석": {
        "report_title": "고객 분석 보고서",
        "steps": [
            # 원본 순서: 신규 고객 ↓ 이탈 고객 ↓ VIP ↓ 매출 기여도 ↓ 구매주기 ↓ 추천 Action
            {"step_id": "new_customer"},           # 신규 고객
            {"step_id": "lost_customer"},          # 이탈 고객
            {"step_id": "vip_customer"},           # VIP
            {"step_id": "customer_contribution"},  # 매출 기여도
            # 구매주기 스텝은 order_date grain(3군)에서 추가
            {"step_id": "conclusion"},
        ],
    },

    "제품 분석": {
        "report_title": "제품 분석 보고서",
        "steps": [
            # 원본 순서: SKU ↓ 판매량 ↓ 매출 ↓ 이익 ↓ ABC ↓ Life Cycle ↓ 문제 제품 추천
            {"step_id": "sku_status"},       # SKU (2026-07-21 신설 — 제품 구성 신규·단종)
            {"step_id": "product_qty"},      # 판매량
            {"step_id": "product_sales"},    # 매출
            {"step_id": "profit"},           # 이익 (2026-07-21 신설 — pnl_summary 재사용)
            {"step_id": "item_abc"},         # ABC
            {"step_id": "item_lifecycle"},   # Life Cycle
            {"step_id": "item_anomaly"},     # 문제 제품
            {"step_id": "conclusion"},
        ],
    },

    "손익 분석": {
        "report_title": "손익 분석 보고서",
        "steps": [
            {"step_id": "pnl_revenue"},       # Revenue
            {"step_id": "pnl_cogs"},          # COGS
            {"step_id": "pnl_gross_margin"},  # Gross Margin
            {"step_id": "pnl_opex"},          # OPEX
            {"step_id": "pnl_ebit"},          # EBIT
            {"step_id": "pnl_cause"},         # 원인 분석
            {"step_id": "conclusion"},
        ],
    },

    "재고 분석": {
        "report_title": "재고 분석 보고서",
        "steps": [
            # 원본 순서: ABC ↓ 회전율 ↓ Dead Stock ↓ Slow Moving ↓ Safety Stock ↓ 개선안
            {"step_id": "inventory_abc"},   # ABC
            {"step_id": "turnover"},        # 회전율
            {"step_id": "dead_stock"},      # Dead Stock
            {"step_id": "slow_moving"},     # Slow Moving
            {"step_id": "safety_stock"},    # Safety Stock
            {"step_id": "conclusion"},
        ],
    },
}


def get_scenario(report_type: str) -> dict | None:
    """유형별 기본 세트를 반환한다. 없으면 None(수동 진입 시 빈 출발점 대신 자동 계획기로 폴백)."""
    return SCENARIO_REGISTRY.get(report_type)
