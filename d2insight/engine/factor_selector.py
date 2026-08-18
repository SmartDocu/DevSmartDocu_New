"""요인 선택 모듈 — Shapley 결과로 집중 분석 요인을 결정한다.

흐름:
  detect_changes     → 전월 대비 30%+ 변화 항목 탐지 (Step 1)
  select_factors     → 누적 기여도 기준 유의미 요인 추출 (Step 3 단독/복수 분기)
  rank_combinations  → 복수 요인의 pairwise 조합 순위 산출
  build_factor_context → ReportAgent 시스템 프롬프트에 주입할 context 패키징
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

CUMULATIVE_THRESHOLD = 0.70   # 누적 기여도 임계값: 이 값 이상이 되는 최소 요인 집합 사용
CHANGE_THRESHOLD = 0.30       # 변화 감지 임계값: 전월평균 대비 이 비율 이상 변화 시 분석 대상


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def detect_changes(df: pd.DataFrame, target_month: str, months_back: int = 3) -> dict:
    """직전 months_back개월 평균 대비 target_month의 매출 변화를 분석한다.

    Returns:
        total_curr        — 당월 총매출
        total_prev_avg    — 직전 N개월 평균 총매출
        total_delta       — 당월 - 평균
        total_delta_pct   — 변화율 (소수)
        significant_items — 30%+ 변화 항목 목록 (변화율 내림차순, 최대 20개)
        n_significant     — 전체 유의미 변화 항목 수
        months_back       — 비교에 사용한 기간
    """
    prev_months = [_shift_month(target_month, -i) for i in range(1, months_back + 1)]

    curr = df[df["월"] == target_month]
    prev = df[df["월"].isin(prev_months)]

    total_curr = float(curr["매출"].sum())
    prev_monthly = prev.groupby("월")["매출"].sum()
    total_prev_avg = float(prev_monthly.mean()) if not prev_monthly.empty else 0.0

    total_delta = total_curr - total_prev_avg
    total_delta_pct = total_delta / total_prev_avg if total_prev_avg else 0.0

    curr_item = curr.groupby(["제품", "채널"])["매출"].sum()
    prev_item = prev.groupby(["제품", "채널"])["매출"].mean()

    significant_items: list[dict] = []
    for item in set(curr_item.index) | set(prev_item.index):
        c = float(curr_item.get(item, 0.0))
        p = float(prev_item.get(item, 0.0))
        if p == 0:
            continue
        pct = (c - p) / p
        if abs(pct) >= CHANGE_THRESHOLD:
            significant_items.append({
                "제품": item[0] if isinstance(item, tuple) else item,
                "채널": item[1] if isinstance(item, tuple) else "",
                "당월매출": round(c, 0),
                "직전평균매출": round(p, 0),
                "변화율": round(pct, 4),
            })

    significant_items.sort(key=lambda x: abs(x["변화율"]), reverse=True)

    return {
        "target_month": target_month,
        "total_curr": total_curr,
        "total_prev_avg": total_prev_avg,
        "total_delta": total_delta,
        "total_delta_pct": total_delta_pct,
        "significant_items": significant_items[:20],
        "n_significant": len(significant_items),
        "months_back": months_back,
    }


def select_factors(
    shapley_share: dict[str, float],
    cumulative_threshold: float = CUMULATIVE_THRESHOLD,
) -> dict:
    """Shapley 기여도에서 집중 분석할 요인 집합을 결정한다.

    정렬 후 누적 기여도가 cumulative_threshold를 넘는 최소 요인 집합을 선택한다.
    선택된 요인이 1개면 'single', 2개 이상이면 'multi'.

    Returns:
        factors          — 선택된 요인 목록 (기여도 내림차순)
        shares           — 요인별 기여도
        mode             — 'single' | 'multi'
        dominant_factor  — single 모드 시 해당 요인, multi 시 None
    """
    if not shapley_share:
        return {"factors": [], "shares": {}, "mode": "single", "dominant_factor": None}

    sorted_items = sorted(shapley_share.items(), key=lambda x: abs(x[1]), reverse=True)

    cumulative = 0.0
    selected: list[str] = []
    for dim, share in sorted_items:
        selected.append(dim)
        cumulative += abs(share)
        if cumulative >= cumulative_threshold:
            break

    mode = "single" if len(selected) == 1 else "multi"
    dominant = selected[0] if mode == "single" else None

    return {
        "factors": selected,
        "shares": {d: round(shapley_share[d], 4) for d in selected},
        "mode": mode,
        "dominant_factor": dominant,
    }


def rank_combinations(
    factors: list[str],
    shares: dict[str, float],
) -> list[dict]:
    """요인 목록에서 pairwise 조합을 기여도 합계 기준으로 내림차순 정렬한다.

    단일 요인도 포함하며, 상위 3개를 반환한다.
    예: [{"combo": ["채널", "지역"], "combined_share": 0.73, "label": "채널×지역"}, ...]
    """
    if not factors:
        return []

    results: list[dict] = []

    for f in factors:
        results.append({
            "combo": [f],
            "combined_share": round(abs(shares.get(f, 0.0)), 4),
            "label": f,
        })

    if len(factors) >= 2:
        for f1, f2 in combinations(factors, 2):
            results.append({
                "combo": [f1, f2],
                "combined_share": round(abs(shares.get(f1, 0.0)) + abs(shares.get(f2, 0.0)), 4),
                "label": f"{f1}×{f2}",
            })

    if len(factors) >= 3:
        for f1, f2, f3 in combinations(factors, 3):
            results.append({
                "combo": [f1, f2, f3],
                "combined_share": round(
                    abs(shares.get(f1, 0.0)) + abs(shares.get(f2, 0.0)) + abs(shares.get(f3, 0.0)), 4
                ),
                "label": f"{f1}×{f2}×{f3}",
            })

    results.sort(key=lambda x: x["combined_share"], reverse=True)
    return results[:3]


def build_factor_context(
    change_info: dict,
    factor_result: dict,
    combinations_ranked: list[dict],
    shapley_share: dict[str, float],
) -> dict:
    """판매분석 요인 스크리닝 결과를 ReportAgent 시스템 프롬프트 주입용으로 패키징한다."""
    share_text = ", ".join(
        f"{dim} {round(abs(s) * 100, 1)}%"
        for dim, s in sorted(shapley_share.items(), key=lambda x: abs(x[1]), reverse=True)
    )

    delta_pct = change_info.get("total_delta_pct", 0.0)
    direction = "증가" if delta_pct > 0 else "감소"

    combo_lines: list[str] = []
    for i, c in enumerate(combinations_ranked):
        combo_lines.append(
            f"  {i + 1}위: {c['label']} (기여도 {round(c['combined_share'] * 100, 1)}%)"
        )
    combo_text = "\n".join(combo_lines)

    return {
        "total_delta_pct": delta_pct,
        "direction": direction,
        "n_significant": change_info.get("n_significant", 0),
        "shapley_share_text": share_text,
        "mode": factor_result["mode"],
        "dominant_factor": factor_result.get("dominant_factor"),
        "selected_factors": factor_result["factors"],
        "combinations_ranked": combinations_ranked,
        "combo_text": combo_text,
    }
