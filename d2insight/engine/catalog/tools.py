"""Tool Registry (§7) — 계산 방법 카탈로그. 여러 모듈이 공유한다.

증분 A에서는 메타데이터(tool_id·purpose)만 등록한다. 실제 계산 함수는 증분 B에서
src/pipeline 로직에 배선한다. `attainment`는 집계(계획대비)와 분석(이상치 달성률 툴)
양쪽에서 재사용되는 공유 툴이다(N:M).
"""
from __future__ import annotations

# tool_id → 메타데이터
TOOL_REGISTRY: dict[str, dict] = {
    # ── 집계형 ────────────────────────────────────────────────────────────
    "group_sum":     {"purpose": "차원×measure 합계·증감(Actual/Compare/Variance/Rate)"},
    "attainment":    {"purpose": "계획/목표 대비 달성률·차이 (계획대비·이상치 달성률 공용)"},
    "series":        {"purpose": "기간축 시계열 값"},
    "share":         {"purpose": "구성비(비중 %)"},
    "rank":          {"purpose": "값 기준 순위"},
    "running_total": {"purpose": "누계·진척률"},
    # ── 분석형 ────────────────────────────────────────────────────────────
    "pvm":               {"purpose": "물량×믹스×단가 표준 분해(두 기간 공통 항목만 대상, 신규·단종 제외)"},
    "shapley":           {"purpose": "차원별 Shapley 기여도"},
    "dvi":               {"purpose": "DVI = Impact×HHI×평균Z"},
    "contribution_rate": {"purpose": "항목 증감 / 전체 증감액"},
    "z_score":           {"purpose": "표준편차 기반 이상치 점수(±1/2/3σ)"},
    "iqr":               {"purpose": "사분위 범위 기반 이상치"},
    "mad":               {"purpose": "중앙값 절대편차 기반 이상치"},
    "new_lost":          {"purpose": "신규/단종 판정(New_Lost_Flag)"},
    "bridge_decompose":  {"purpose": "수량/ASP/할인/신규/이탈 효과 분해"},
    "cross_cut":         {"purpose": "하위 차원 교차 분해"},
    "validate":          {"purpose": "결측·이상·정합성 점검"},
    "history_z":         {"purpose": "measure의 이력 대비 Z(분석월 제외 기준선) — KPI 시계열 이상"},
    "threshold":         {"purpose": "고정 증감률 임계 초과 판정(이력이 짧을 때의 보조 잣대)"},
    "margin_ladder":     {"purpose": "손익 계단 분해(매출→원가→매출총이익→판관비→영업이익)"},
    "turnover":          {"purpose": "재고회전율·재고일수(매출원가/평균재고)"},
    "stock_reconcile":   {"purpose": "기초+입고−출고=기말 정합성 점검"},
}


def get_tool_registry() -> dict[str, dict]:
    return dict(TOOL_REGISTRY)
