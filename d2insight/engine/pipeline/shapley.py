"""Shapley value attribution at dimension level.

Applied to items filtered by ABC-XYZ (AZ/AX/AY/BZ) only (design §5.5).

Value function v(S) — *explanatory power gained at granularity S*:
    v(∅)    = |total Δ|
    v(S)    = Σ_g |Δ_g|   (groups defined by dims in S)
    v(full) = Σ_cells |Δ_cell|

v is monotonic in S (triangle inequality). Shapley values are therefore
non-negative and capture the "structural variation each dimension uncovers."
We then express each dim's Shapley as a *share* of Σ Shapley so it reads as
"% of explanatory power."

Primary Driver: largest share. If 1·2위 차이 < 10pp it is *complex* (multiple).
Noise: dims with share < `config.MIN_CONTRIBUTION` (default 5%).

For the current set of 4 dimensions exact Shapley over 2⁴=16 subsets is
trivially fast — Monte Carlo (`config.SHAPLEY_ITERATIONS`) is reserved for
future cases with more dimensions.
"""
from __future__ import annotations

from itertools import combinations
from math import factorial
from typing import Callable

import pandas as pd

import d2insight.config as config


# Map canonical dimension names (config.DIMENSIONS) to actual DataFrame columns.
_DIM_COLUMN: dict[str, str] = {
    "채널": "채널",
    "제품대분류": "제품대분류",
    "제품중분류": "제품중분류",
    "지역": "지역_Country",
}


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def _value_fn_factory(curr: pd.DataFrame, prev: pd.DataFrame,
                      measure: str = "매출") -> Callable[[tuple[str, ...]], float]:
    """v(S) = Σ_g |Δ_g| over groups defined by dimension columns in S.

    measure는 호출자가 스키마에서 얻어 넘긴다(기본값은 기존 판매 파이프라인 호환용).
    """
    total_curr = float(curr[measure].sum())
    total_prev = float(prev[measure].sum())

    def v(S: tuple[str, ...]) -> float:
        if not S:
            return abs(total_curr - total_prev)
        g_curr = curr.groupby(list(S))[measure].sum() if not curr.empty else pd.Series(dtype=float)
        g_prev = prev.groupby(list(S))[measure].sum() if not prev.empty else pd.Series(dtype=float)
        return float(g_curr.subtract(g_prev, fill_value=0.0).abs().sum())

    return v


def shapley_exact(value_fn: Callable[[tuple[str, ...]], float], dim_cols: list[str]) -> dict[str, float]:
    """Closed-form Shapley using cached v(S). Suitable for ≤ ~8 dimensions."""
    n = len(dim_cols)
    n_fact = factorial(n)
    cache: dict[frozenset, float] = {}

    def v_cached(S: frozenset) -> float:
        if S not in cache:
            cache[S] = value_fn(tuple(sorted(S)))
        return cache[S]

    shapley = {d: 0.0 for d in dim_cols}
    for dim in dim_cols:
        others = [d for d in dim_cols if d != dim]
        for k in range(len(others) + 1):
            weight = factorial(k) * factorial(n - 1 - k) / n_fact
            for combo in combinations(others, k):
                S = frozenset(combo)
                shapley[dim] += weight * (v_cached(S | {dim}) - v_cached(S))
    return shapley


def select_primary_driver(
    shapley_share: dict[str, float], complex_threshold_pp: float = 0.10
) -> dict:
    """Top dim by absolute share. If 1·2위 차이 < threshold, mark as complex."""
    if not shapley_share:
        return {"primary": [], "is_complex": False, "top_share": 0.0}
    sorted_dims = sorted(shapley_share.items(), key=lambda x: abs(x[1]), reverse=True)
    top_dim, top_val = sorted_dims[0]
    primaries = [top_dim]
    for d, s in sorted_dims[1:]:
        if abs(top_val) - abs(s) < complex_threshold_pp:
            primaries.append(d)
        else:
            break
    return {
        "primary": primaries,
        "is_complex": len(primaries) > 1,
        "top_share": float(abs(top_val)),
    }


def run_phase3(
    df: pd.DataFrame,
    target_month: str,
    analysis_targets: pd.DataFrame,
) -> dict:
    """Compute Shapley dimension attribution for target month vs previous month,
    restricted to items in `analysis_targets` (Phase 2 output)."""
    prev_month = _shift_month(target_month, -1)
    canonical_dims = list(config.DIMENSIONS)
    dim_cols = [_DIM_COLUMN[d] for d in canonical_dims]
    canonical_of = {v: k for k, v in _DIM_COLUMN.items()}

    if analysis_targets.empty:
        return {
            "target_month": target_month,
            "prev_month": prev_month,
            "n_filtered_rows": 0,
            "total_delta": 0.0,
            "shapley_values": {d: 0.0 for d in canonical_dims},
            "shapley_share": {d: 0.0 for d in canonical_dims},
            "primary_driver": {"primary": [], "is_complex": False, "top_share": 0.0},
            "noise_dims": list(canonical_dims),
        }

    target_keys = set(zip(analysis_targets["제품"], analysis_targets["채널"]))
    item_idx = pd.MultiIndex.from_arrays([df["제품"], df["채널"]])
    mask = item_idx.isin(target_keys)
    filtered = df[mask].copy()

    curr = filtered[filtered["월"] == target_month]
    prev = filtered[filtered["월"] == prev_month]

    value_fn = _value_fn_factory(curr, prev)
    shapley = shapley_exact(value_fn, dim_cols)

    total_explanatory = sum(shapley.values())
    if total_explanatory > 0:
        share = {d: v / total_explanatory for d, v in shapley.items()}
    else:
        share = {d: 0.0 for d in shapley}

    primary = select_primary_driver(share, complex_threshold_pp=0.10)
    noise_dims = [d for d, s in share.items() if abs(s) < config.MIN_CONTRIBUTION]
    total_delta = float(curr["매출"].sum() - prev["매출"].sum())

    return {
        "target_month": target_month,
        "prev_month": prev_month,
        "n_filtered_rows": int(len(filtered)),
        "n_curr_cells": int(len(curr)),
        "n_prev_cells": int(len(prev)),
        "total_delta": total_delta,
        "shapley_values": {canonical_of[d]: round(v, 2) for d, v in shapley.items()},
        "shapley_share": {canonical_of[d]: round(s, 4) for d, s in share.items()},
        "primary_driver": {
            "primary": [canonical_of[d] for d in primary["primary"]],
            "is_complex": primary["is_complex"],
            "top_share": round(primary["top_share"], 4),
        },
        "noise_dims": [canonical_of[d] for d in noise_dims],
    }
