"""Cross drilldown — recursive Δ breakdown starting from Primary Driver."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from d2insight import config


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


def _build_tree(
    sub_curr: pd.DataFrame,
    sub_prev: pd.DataFrame,
    dim_cols: list[str],
    depth: int,
    *,
    total_revenue: float,
    top_n_max: int,
    pareto: float,
    min_cell_share: float,
) -> Optional[dict]:
    if depth >= len(dim_cols):
        return None
    dim = dim_cols[depth]

    g_curr = (
        sub_curr.groupby(dim)["매출"].sum()
        if not sub_curr.empty
        else pd.Series(dtype=float)
    )
    g_prev = (
        sub_prev.groupby(dim)["매출"].sum()
        if not sub_prev.empty
        else pd.Series(dtype=float)
    )
    delta = g_curr.subtract(g_prev, fill_value=0.0)
    rev_total = g_curr.add(g_prev, fill_value=0.0).reindex(delta.index, fill_value=0.0)

    if delta.empty:
        return None

    if total_revenue > 0:
        keep = (rev_total / total_revenue) >= min_cell_share
        delta = delta[keep]

    if delta.empty:
        return None

    order = delta.abs().sort_values(ascending=False).index
    delta = delta.loc[order]
    local_total_abs = float(delta.abs().sum())

    selected: list[tuple[object, float, float]] = []
    cum = 0.0
    for value, d in delta.items():
        share = abs(float(d)) / local_total_abs if local_total_abs > 0 else 0.0
        cum += share
        selected.append((value, float(d), share))
        if cum >= pareto or len(selected) >= top_n_max:
            break

    groups = []
    for value, d, share in selected:
        child_curr = sub_curr[sub_curr[dim] == value]
        child_prev = sub_prev[sub_prev[dim] == value]
        children = _build_tree(
            child_curr, child_prev, dim_cols, depth + 1,
            total_revenue=total_revenue,
            top_n_max=top_n_max, pareto=pareto, min_cell_share=min_cell_share,
        )
        groups.append({
            "value": str(value),
            "curr": float(child_curr["매출"].sum()),
            "prev": float(child_prev["매출"].sum()),
            "delta": d,
            "share_of_local_abs": round(share, 4),
            "children": children,
        })

    return {"dim": dim, "groups": groups}


def run_phase4_drilldown(
    df: pd.DataFrame,
    target_month: str,
    analysis_targets: pd.DataFrame,
    primary_driver_canonical: list[str],
    noise_dims_canonical: list[str],
    shapley_share_canonical: dict[str, float],
) -> dict:
    prev_month = _shift_month(target_month, -1)

    if not primary_driver_canonical or analysis_targets.empty:
        return {
            "target_month": target_month,
            "prev_month": prev_month,
            "drill_path": [],
            "tree": None,
            "complex_primary": False,
            "primary_drivers_all": list(primary_driver_canonical),
        }

    target_keys = set(zip(analysis_targets["제품"], analysis_targets["채널"]))
    item_idx = pd.MultiIndex.from_arrays([df["제품"], df["채널"]])
    filtered = df[item_idx.isin(target_keys)].copy()
    curr = filtered[filtered["월"] == target_month]
    prev = filtered[filtered["월"] == prev_month]

    primary_canonical = primary_driver_canonical[0]
    primary_col = _DIM_COLUMN[primary_canonical]

    candidates = [
        d for d in config.DIMENSIONS
        if d not in primary_driver_canonical and d not in noise_dims_canonical
    ]
    candidates_sorted = sorted(
        candidates, key=lambda d: -shapley_share_canonical.get(d, 0.0)
    )
    secondary_cols = [_DIM_COLUMN[d] for d in candidates_sorted[: config.DRILLDOWN_DEPTH]]

    drill_dims_cols = [primary_col] + secondary_cols
    drill_path = [primary_canonical] + candidates_sorted[: config.DRILLDOWN_DEPTH]

    total_revenue = float(curr["매출"].sum() + prev["매출"].sum())
    tree = _build_tree(
        curr, prev, drill_dims_cols, depth=0,
        total_revenue=total_revenue,
        top_n_max=config.TOP_N_MAX,
        pareto=config.PARETO_THRESHOLD,
        min_cell_share=config.DRILLDOWN_MIN_CELL_SHARE,
    )

    return {
        "target_month": target_month,
        "prev_month": prev_month,
        "drill_path": drill_path,
        "tree": tree,
        "complex_primary": len(primary_driver_canonical) > 1,
        "primary_drivers_all": list(primary_driver_canonical),
    }
