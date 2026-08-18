"""이름표 사전 (§5) — 공유 컨텍스트 key의 의미 정의.

이름표는 의미 기반·생산자 비의존으로 짓는다. 여기 정의는 재사용을 유도하기 위한 사전이며,
새 모듈 추가 시 먼저 이 사전을 확인해 기존 이름표를 재사용하거나 신규 등록한다.

싱글턴 이름표만 등록한다. 리프 모듈(actual_aggregate 등)은 이름표를 생산하지 않으므로
(produces=[]) 여기 없다 — dimension만 바꿔 여러 번 실행해도 충돌하지 않는다(§3.4-2 회피).
"""
from __future__ import annotations

# 이름표 → 담는 내용 설명
SINGLETON_LABELS: dict[str, str] = {
    "actual_dataset":     "분석기간 원천 레코드",
    "compare_dataset":    "비교기간 원천 레코드",
    "history_dataset":    "최근 N개월 시계열 원천",
    "meta_columns":       "컬럼 메타(Dim/Measure/Date/Key)",
    "measure_summary":    "Measure별 Actual/Compare/Variance/Rate",
    "total_variance":     "전체 증감액(공용 분모) — 최초 1회 계산 후 재사용",
    "dimension_stats":    "차원별 Impact/Shapley/Z/HHI/DVI",
    "outlier_result":     "이상치 항목 목록",
    "new_lost_items":     "신규/단종 항목",
    "count_summary":      "신규/손실 항목수",
    "bridge_effects":     "수량/ASP/할인/신규/이탈 효과 분해",
    "within_contribution": "차원 내 기여도(Contribution_Rate)",
    "drilldown_result":   "하위 차원 교차 결과",
    "validation_result":  "데이터 검증 결과",
    "abc_xyz_classification": "항목별 ABC-XYZ 등급(규모·변동성)",
    "abc_grade_changes":  "등급 변동 항목(당월 창 vs 전월 창)",
    "lifecycle_stages":   "항목별 수명주기 단계(도입/성장/성숙/쇠퇴)",
    "kpi_alerts":         "measure(KPI)별 이력 대비 이탈·등급(경보/주의/정상)",
    "pnl_steps":          "손익 계단(매출→원가→매출총이익→판관비→영업이익)",
    "inventory_metrics":  "항목별 재고회전율·재고일수·장기체화 구분",
    "inventory_summary":  "전체 재고회전율·재고일수·평균재고",
    "stock_flow":         "기초·입고·출고·기말 재고 흐름",
    "stock_movement_detail": "항목별 재고 이동과 정합성 차이",
}


def get_label_dictionary() -> dict[str, str]:
    return dict(SINGLETON_LABELS)
