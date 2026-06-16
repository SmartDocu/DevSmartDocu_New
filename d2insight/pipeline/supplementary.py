"""Supplementary analysis: 신규/단종 detection + outlier flagging."""
from __future__ import annotations

import re
import pandas as pd

from d2insight import config


def _parse_outlier_threshold(threshold_str: str | None) -> dict:
    if not threshold_str:
        return {"type": "pct", "value": config.OUTLIER_CHANGE_PCT}
    sigma_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:σ|시그마)", threshold_str, re.IGNORECASE)
    if sigma_m:
        return {"type": "sigma", "value": float(sigma_m.group(1))}
    pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", threshold_str)
    if pct_m:
        return {"type": "pct", "value": float(pct_m.group(1)) / 100}
    return {"type": "pct", "value": config.OUTLIER_CHANGE_PCT}

ITEM_DIMS = ["제품", "채널"]


def _shift_month(yyyymm: str, n: int) -> str:
    y, m = map(int, yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


def run_phase4_supplementary(
    df: pd.DataFrame,
    target_month: str,
    outlier_threshold: str | None = None,
) -> dict:
    prev_month = _shift_month(target_month, -1)
    curr = df[df["월"] == target_month]
    prev = df[df["월"] == prev_month]

    curr_items = curr.groupby(ITEM_DIMS)["매출"].sum()
    prev_items = prev.groupby(ITEM_DIMS)["매출"].sum()

    joined = (
        pd.concat([prev_items.rename("prev"), curr_items.rename("curr")], axis=1)
        .fillna(0.0)
    )

    new_items = joined[(joined["prev"] == 0) & (joined["curr"] > 0)].copy()
    discontinued_items = joined[(joined["prev"] > 0) & (joined["curr"] == 0)].copy()

    total_curr = float(curr["매출"].sum())
    total_prev = float(prev["매출"].sum())
    total_delta = total_curr - total_prev
    abs_delta = abs(total_delta) if total_delta != 0 else 1.0

    new_total = float(new_items["curr"].sum())
    disc_total = float(discontinued_items["prev"].sum())
    new_share = new_total / abs_delta
    disc_share = disc_total / abs_delta
    high_impact = (
        new_share >= config.NEW_DISC_HIGH_IMPACT_RATIO
        or disc_share >= config.NEW_DISC_HIGH_IMPACT_RATIO
    )

    new_items["pct_of_abs_delta"] = (new_items["curr"] / abs_delta).round(4)
    discontinued_items["pct_of_abs_delta"] = (discontinued_items["prev"] / abs_delta).round(4)
    new_items = new_items.reset_index().sort_values("curr", ascending=False)
    discontinued_items = discontinued_items.reset_index().sort_values("prev", ascending=False)

    pool = joined[(joined["prev"] > 0) & (joined["curr"] > 0)].copy()
    pool["delta"] = pool["curr"] - pool["prev"]
    pool["change_pct"] = pool["delta"] / pool["prev"]
    pool["share_of_curr"] = pool["curr"] / total_curr if total_curr > 0 else 0.0

    thr = _parse_outlier_threshold(outlier_threshold)
    if thr["type"] == "sigma" and len(pool) >= 2:
        mean_chg = pool["change_pct"].mean()
        std_chg = pool["change_pct"].std()
        cutoff = thr["value"] * std_chg if std_chg > 0 else config.OUTLIER_CHANGE_PCT
        outlier_mask = (pool["change_pct"] - mean_chg).abs() >= cutoff
    else:
        cutoff = thr["value"]
        outlier_mask = pool["change_pct"].abs() >= cutoff

    outliers = pool[
        outlier_mask & (pool["share_of_curr"] >= config.OUTLIER_MIN_REVENUE_SHARE)
    ].copy()
    outliers["change_pct"] = outliers["change_pct"].round(4)
    outliers["share_of_curr"] = outliers["share_of_curr"].round(4)
    outliers = (
        outliers.reset_index()
        .assign(_abs=lambda d: d["delta"].abs())
        .sort_values("_abs", ascending=False)
        .drop(columns="_abs")
    )

    return {
        "target_month": target_month,
        "prev_month": prev_month,
        "summary": {
            "total_delta": total_delta,
            "total_curr": total_curr,
            "total_prev": total_prev,
            "new_count": int(len(new_items)),
            "new_revenue": new_total,
            "new_share_of_abs_delta": round(new_share, 4),
            "discontinued_count": int(len(discontinued_items)),
            "discontinued_revenue": disc_total,
            "discontinued_share_of_abs_delta": round(disc_share, 4),
            "outlier_count": int(len(outliers)),
            "high_impact": bool(high_impact),
            "thresholds": {
                "new_disc_high_impact": config.NEW_DISC_HIGH_IMPACT_RATIO,
                "outlier_method": thr["type"],
                "outlier_cutoff": round(cutoff, 4),
                "outlier_threshold_input": outlier_threshold or f"±{config.OUTLIER_CHANGE_PCT:.0%}",
                "outlier_min_share_of_curr": config.OUTLIER_MIN_REVENUE_SHARE,
            },
        },
        "new_items": new_items.to_dict(orient="records"),
        "discontinued_items": discontinued_items.to_dict(orient="records"),
        "outlier_items": outliers.to_dict(orient="records"),
    }
