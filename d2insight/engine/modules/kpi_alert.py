"""kpi_alert 모듈 — measure(KPI) 레벨 이상 경보 (시나리오 2 'KPI Executive Summary').

anomaly_detection과 무엇이 다른가
    anomaly_detection : **항목** 레벨. 같은 달의 다른 항목들과 비교하는 **횡단면** 판정.
                        "어떤 상품이 튀었나"
    kpi_alert         : **measure** 레벨. 같은 measure의 과거 개월들과 비교하는 **시계열** 판정.
                        "이번 달 매출 자체가 평소 범위를 벗어났나"

판정 규약 (2026-07-20 확정) — 기본은 '이력 대비 Z'(history_z)
    기준선 = 분석월을 **제외한** 과거 개월들의 평균·σ.
    Z = (분석월 값 − 기준선 평균) / 기준선 σ

    분석월을 기준선에서 빼는 이유: 분석월이 모집단 안에 있으면 |Z| 상한이 (n−1)/√n로 묶여
    표본이 적을 때 임계에 **원리적으로 도달할 수 없다**(anomaly가 §14 개정 전에 겪은 문제).
    분석월을 모집단 밖에 두면 Z가 묶이지 않는다.

    기준선 개월수가 config.KPI_ALERT_MIN_MONTHS 미만이거나 σ가 0이면 "이상 없음"이 아니라
    **'판정 불가'로 명시**한다(§11 Step 2). 조용히 정상 처리하지 않는다.

툴(잣대 스위치)
    history_z  : 위 규약. 기본값.
    threshold  : 보조. |증감률| ≥ config.KPI_ALERT_RATE면 경보. 이력이 짧을 때 쓴다.
    attainment : 계획(목표) 대비 달성률. 계획 역할이 선언된 데이터소스에서만 동작하며,
                 없으면 명시적 실패한다(anomaly_detection의 attainment와 같은 처리).

대상 measure는 measure_summary가 이미 만든 목록을 그대로 쓴다(재계산 금지 §6.2). 파생 measure
(단가·할인율)는 이력에 컬럼이 없으므로 스키마 역할로 월별 재구성한다 — 컬럼명을 코드에 박지 않는다(§7.4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import d2insight.config as config
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import slice_history_window
from d2insight.engine.modules.summary import DERIVED_DISCOUNT_RATE, DERIVED_UNIT_PRICE
from d2insight.engine.schema import (
    ROLE_AMOUNT, ROLE_DISCOUNT, ROLE_PERIOD, ROLE_QUANTITY, get_schema,
)
from d2insight.engine.types import ModuleResult, Render

LEVEL_ALERT = "경보"
LEVEL_WATCH = "주의"
LEVEL_NORMAL = "정상"
LEVEL_UNDECIDABLE = "판정 불가"

_RATIO_MEASURES = {DERIVED_DISCOUNT_RATE}     # 비율 measure — 서식이 다르다


def _level(score: float, threshold: float) -> str:
    """anomaly와 같은 등급 규약 — 임계 이상 '경보', 임계의 2/3 이상 '주의', 그 외 '정상'."""
    a = abs(score)
    if a >= threshold:
        return LEVEL_ALERT
    if a >= threshold * 2 / 3:
        return LEVEL_WATCH
    return LEVEL_NORMAL


def _monthly_series(history: pd.DataFrame, period_col: str, schema,
                    physical_name: str) -> pd.Series | None:
    """measure 하나의 월별 시계열. 파생 measure는 역할로 재구성한다.

    이력에 없는 measure는 None — 호출부가 '판정 불가'로 남긴다(조용히 빼지 않는다).
    """
    if physical_name in history.columns:
        return history.groupby(period_col)[physical_name].sum().sort_index()

    amount_col = schema.column(ROLE_AMOUNT) or schema.key_measure

    if physical_name == DERIVED_UNIT_PRICE:
        qty_col = schema.column(ROLE_QUANTITY)
        if not qty_col or qty_col not in history.columns or amount_col not in history.columns:
            return None
        grouped = history.groupby(period_col)[[amount_col, qty_col]].sum().sort_index()
        qty = grouped[qty_col]
        return (grouped[amount_col] / qty.where(qty != 0)).dropna()

    if physical_name == DERIVED_DISCOUNT_RATE:
        disc_col = schema.column(ROLE_DISCOUNT)
        if not disc_col or disc_col not in history.columns or amount_col not in history.columns:
            return None
        grouped = history.groupby(period_col)[[amount_col, disc_col]].sum().sort_index()
        gross = grouped[amount_col] + grouped[disc_col]      # 금액이 할인 후 순액이라는 전제
        return (grouped[disc_col] / gross.where(gross != 0)).dropna()

    return None


def _fmt(value: float, physical_name: str) -> str:
    if physical_name in _RATIO_MEASURES:
        return f"{value * 100:.2f}%"
    if physical_name == DERIVED_UNIT_PRICE:
        return f"{value:,.2f}"
    return f"{value:,.0f}"


def _display_table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({
        "KPI": [r["Logical_Name"] for r in rows],
        "분석월": [r["Actual_Display"] for r in rows],
        "기준선 평균": [r["Baseline_Display"] for r in rows],
        "기준선 개월": [r["Baseline_Months"] for r in rows],
        "증감률": [f"{r['Rate'] * 100:+.1f}%" for r in rows],
        "Z": [f"{r['Z']:+.2f}" if pd.notna(r["Z"]) else "-" for r in rows],
        "방향": [r["Direction"] for r in rows],
        "등급": [r["Level"] for r in rows],
    })


def run(ctx, params, tools) -> ModuleResult:
    tool = tools[0] if tools else "history_z"

    if tool == "attainment":
        # 계획 역할이 선언된 데이터소스에서만 가능하다. 없으면 조용히 다른 잣대로 바꾸지 않는다.
        return ModuleResult(
            status="failed",
            error="달성률 기준 KPI 경보는 계획(목표) 데이터가 필요합니다. "
                  "데이터소스 정의에 계획 역할을 선언하세요.",
        )
    if tool not in ("history_z", "threshold"):
        return ModuleResult(status="failed", error=f"지원하지 않는 KPI 경보 툴: '{tool}'")

    summary_df = ctx.get("measure_summary")
    if summary_df is None or getattr(summary_df, "empty", True):
        return ModuleResult(status="failed", error="measure_summary가 없어 KPI 목록을 정할 수 없습니다.")

    schema = get_schema(ctx)
    target_month = ctx.meta.get("target_month")
    if not target_month:
        return ModuleResult(status="failed", error="ctx.meta에 target_month가 없습니다.")

    sigma_threshold = float(params.get("sigma") or getattr(config, "KPI_ALERT_SIGMA", 2.0))
    rate_threshold = float(params.get("rate") or getattr(config, "KPI_ALERT_RATE", 0.20))
    min_months = int(getattr(config, "KPI_ALERT_MIN_MONTHS", 3))

    rows: list[dict] = []
    undecidable: list[str] = []
    window_note = ""

    # ── threshold 툴: 이력 없이 measure_summary의 증감률만으로 판정 ──────────────
    if tool == "threshold":
        for _, r in summary_df.iterrows():
            rate = float(r["Rate"])
            rows.append({
                "Physical_Name": r["Physical_Name"],
                "Logical_Name": r["Logical_Name"],
                "Actual_Value": float(r["Actual_Value"]),
                "Actual_Display": _fmt(float(r["Actual_Value"]), r["Physical_Name"]),
                "Baseline_Value": float(r["Comparison_Value"]),
                "Baseline_Display": _fmt(float(r["Comparison_Value"]), r["Physical_Name"]),
                "Baseline_Months": 1,               # 비교기간 1개 — 기준선이 아니라 직전 값
                "Rate": rate,
                "Z": np.nan,
                "Direction": "상향" if rate >= 0 else "하향",
                "Level": _level(rate / rate_threshold if rate_threshold else 0.0, 1.0),
            })
        basis = f"증감률 ±{rate_threshold * 100:.0f}% 기준(비교기간 대비)"

    # ── history_z 툴: 분석월 제외 과거 개월로 기준선을 만든다 ────────────────────
    else:
        history = ctx.get("history_dataset")
        if history is None or getattr(history, "empty", True):
            return ModuleResult(
                status="failed",
                error="이력(history_dataset)이 없어 KPI 시계열 판정을 할 수 없습니다. "
                      "이력 없이 판정하려면 threshold 툴을 쓰세요.",
            )
        period_col = schema.column(ROLE_PERIOD)
        if not period_col or period_col not in history.columns:
            return ModuleResult(
                status="failed",
                error="이력에 기간(period) 역할 컬럼이 없어 시계열 판정을 할 수 없습니다. "
                      "데이터소스 정의에 period 역할을 선언하세요.",
            )

        window = params.get("window_months") or getattr(config, "KPI_ALERT_WINDOW", None)
        history, window_note = slice_history_window(history, period_col, window)

        for _, r in summary_df.iterrows():
            physical = r["Physical_Name"]
            logical = r["Logical_Name"]
            series = _monthly_series(history, period_col, schema, physical)
            if series is None or series.empty:
                undecidable.append(f"{logical}(이력 없음)")
                continue

            baseline = series[series.index != target_month]     # 분석월 제외 = 기준선
            if len(baseline) < min_months:
                undecidable.append(f"{logical}(기준선 {len(baseline)}개월 < {min_months})")
                continue

            mean = float(baseline.mean())
            std = float(baseline.std(ddof=1))
            if not std > 0:
                # 과거가 완전히 평평하면 어떤 값도 무한대 Z가 된다 — 판정 불가로 분리한다.
                undecidable.append(f"{logical}(기준선 편차 0)")
                continue

            actual = float(r["Actual_Value"])       # 총평이 이미 낸 값 재사용(재계산 금지 §6.2)
            z = (actual - mean) / std
            rows.append({
                "Physical_Name": physical,
                "Logical_Name": logical,
                "Actual_Value": actual,
                "Actual_Display": _fmt(actual, physical),
                "Baseline_Value": mean,
                "Baseline_Display": _fmt(mean, physical),
                "Baseline_Months": len(baseline),
                "Rate": (actual - mean) / mean if mean else 0.0,
                "Z": z,
                "Direction": "상향" if z >= 0 else "하향",
                "Level": _level(z, sigma_threshold),
            })
        basis = f"이력 대비 ±{sigma_threshold:g}σ 기준(분석월 제외 기준선)"

    note = (f" 판정 불가 KPI: {', '.join(undecidable)}." if undecidable else "") + window_note

    if not rows:
        return ModuleResult(
            outputs={"kpi_alerts": pd.DataFrame()},
            render=Render(
                summary=f"{basis}으로 판정할 수 있는 KPI가 없습니다.{note}",
                key_value={"판정 기준": basis, "판정 불가": len(undecidable)},
            ),
        )

    # 경보 > 주의 > 정상 순, 같은 등급 안에서는 이탈이 큰 순
    order = {LEVEL_ALERT: 0, LEVEL_WATCH: 1, LEVEL_NORMAL: 2}
    rows.sort(key=lambda r: (order.get(r["Level"], 3),
                             -abs(r["Z"] if pd.notna(r["Z"]) else r["Rate"])))

    alerts = [r for r in rows if r["Level"] == LEVEL_ALERT]
    watches = [r for r in rows if r["Level"] == LEVEL_WATCH]

    result_df = pd.DataFrame(rows)
    render = render_from_dataframe(
        _display_table(rows),
        purpose="측정값(KPI)이 평소 범위를 벗어났는지 시계열로 판정.",
        narrative_hint=(
            f"경보 {len(alerts)}건, 주의 {len(watches)}건을 먼저 밝히고 어느 KPI가 왜(방향·증감률) "
            f"벗어났는지 짚어라. 판정 기준: {basis}.{note}"
        ),
        params={"판정 기준": basis}, label="kpi_alert",
        cache=params.get("_llm_render_cache"),
    )
    render.key_value = {
        "판정 기준": basis, "경보": len(alerts), "주의": len(watches), "판정 불가": len(undecidable),
    }
    return ModuleResult(outputs={"kpi_alerts": result_df}, render=render)
