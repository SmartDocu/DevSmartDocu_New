"""anomaly_detection 모듈 — 통계적으로 벗어난 항목 탐지 (§14, 개정 2026-07-14).

방침 개정 배경 (보고서작성방안.md 14장 참조)
  구 기준(DVI 상위5 차원 / Is_Main만 / 증감률 ±3σ)은 실데이터에서 **원리적으로 0건**이었다.
  표본 n개에서 |Z| 상한이 (n−1)/√n 이라 ±3σ에는 항목 11개가 필요한데, Is_Main 필터가 대상을
  3~8개로 줄였고, DVI는 집중도를 곱해 항목 적은 차원을 편애했기 때문이다.

현 기준
  - 모집단: 전체 항목(New 제외) — §5에서 σ를 만든 모집단과 **동일**해야 자와 대상이 맞는다.
  - 대상 차원: 전 차원 (DVI 상위 N 제한 없음).
  - 편차 축 2개:
      금액(Variance) 편차  ← 주 기준. 경영 영향이 큰 이탈을 잡는다.
      증감률(Rate) 편차    ← 보조. 금액은 작아도 이례적인 변화를 잡는다.
    둘 중 하나라도 임계를 넘으면 이상. 사유(금액/증감률/양쪽)를 표기한다.
  - 판정 불가 차원(항목 수 부족)은 "이상 없음"이 아니라 **"판정 불가"로 명시**한다.
  - 출력: 금액 기준 상위 top_n(기본 10).

증감률 축의 평균·σ는 dimension_stats(§5)가 이미 계산한 값을 그대로 쓴다(재계산 금지 §6.2).
금액 축의 통계는 §5에 없으므로 여기서 만든다(새 통계지, 재계산이 아니다).

툴(z_score/iqr/mad)은 **편차를 재는 잣대**를 갈아끼우는 스위치다. iqr/mad는 극단값에 덜 흔들려
분포가 치우쳤을 때 견고하다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import d2insight.config as config
from d2insight.engine.modules._llm_render import render_from_dataframe
from d2insight.engine.modules._shared import LIFECYCLE_DORMANT, get_item_lifecycle, get_item_variance
from d2insight.engine.schema import get_schema
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.dataset_builder import build_by_item_summary_dataset

_MAD_SCALE = 0.6745      # 정규분포에서 MAD를 σ에 맞추는 상수


def sample_ceiling(n: int) -> float:
    """표본 n개에서 |Z|가 가질 수 있는 최대값 = (n−1)/√n.

    이 값이 임계값보다 작으면 그 차원은 **어떤 항목도 이상으로 판정될 수 없다**. 조용히 "정상"으로
    처리하면 거짓말이 되므로 '판정 불가'로 분리해 보고한다.
    """
    return (n - 1) / np.sqrt(n) if n > 1 else 0.0


def _z_by_tool(values: pd.Series, tool: str,
               mean: float | None = None, sigma: float | None = None) -> pd.Series | None:
    """선택된 잣대로 편차 점수를 만든다. 흩어짐이 0이면 판정 불가(None)."""
    v = values.astype(float)

    if tool == "z_score":
        # 증감률 축은 §5가 이미 구한 평균·σ를 그대로 받는다(재계산 금지). 금액 축은 여기서 구한다.
        m = v.mean() if mean is None else mean
        s = v.std(ddof=1) if sigma is None else sigma
        return (v - m) / s if s > 0 else None

    if tool == "iqr":
        q1, q3 = np.percentile(v, [25, 75])
        iqr = q3 - q1
        return (v - np.median(v)) / iqr if iqr > 0 else None

    if tool == "mad":
        med = float(np.median(v))
        mad = float(np.median(np.abs(v - med)))
        return _MAD_SCALE * (v - med) / mad if mad > 0 else None

    return None


def _level(score: float, threshold: float) -> str:
    """§14 등급 — ±1σ 정상 / ±2σ 주의 / ±3σ 이상 (임계값 기준으로 비례)."""
    a = abs(score)
    if a >= threshold:
        return "이상"
    if a >= threshold * 2 / 3:
        return "주의"
    return "정상"




def run(ctx, params, tools) -> ModuleResult:
    schema = get_schema(ctx)
    # measure별로 따로 계산한다(2026-07-24 4단계) — 매출 기준 이상징후와 수량 기준 이상징후는
    # 서로 다른 항목을 짚어낼 수 있다(비싼 상품이 조금 더 팔리면 매출은 튀어도 수량은 안 튐).
    measure = params.get("measure") or schema.key_measure

    tool = tools[0] if tools else "z_score"
    if tool == "attainment":
        return ModuleResult(
            status="failed",
            error="달성률 기준 탐지는 계획 데이터가 필요합니다. 현재 데이터원에 계획값이 없어 보류 중입니다.",
        )
    if tool not in ("z_score", "iqr", "mad"):
        return ModuleResult(status="failed", error=f"지원하지 않는 탐지 툴: '{tool}'")

    byitem = get_item_variance(ctx, measure)
    if byitem is None or byitem.empty:
        return ModuleResult(status="failed", error="차원×항목 증감 데이터가 비어 있습니다.")
    byitem = byitem[byitem["New_Lost_Flag"] != "New"]     # §5 σ 모집단과 동일하게 맞춘다

    # 증감률 축(§5) 평균·σ — 이 모듈이 직접 계산한다. dimension_impact가 만드는 dimension_stats는
    # 그 스텝이 고른 measure로 고정된 싱글턴이라, 요청 measure가 다르면 재사용할 수 없다(둘 다
    # key_measure를 쓰는 흔한 경우엔 같은 값이 나오지만, 매번 새로 계산해도 순수 함수라 결과가
    # 달라지지 않으므로 굳이 measure 일치를 추적하는 복잡도를 들이지 않는다).
    stats = build_by_item_summary_dataset(
        byitem, ctx.get("actual_dataset"), ctx.get("compare_dataset"), measure=measure
    )
    if stats is None or stats.empty:
        return ModuleResult(status="failed", error="차원 통계를 계산하지 못했습니다.")

    threshold = float(params.get("sigma") or getattr(config, "ANOMALY_SIGMA", 3.0))
    top_n = int(params.get("top_n") or 10)

    all_dims = stats["Dimension_Logical_Name"].tolist()
    requested = params.get("dimensions") or ([params["dimension"]] if params.get("dimension") else None)
    if requested:
        # 없는 차원을 조용히 건너뛰면 "이상 없음"으로 위장된다. 명확히 실패시킨다.
        unknown = [d for d in requested if d not in all_dims]
        if unknown:
            return ModuleResult(
                status="failed",
                error=f"차원 {unknown}의 통계가 없습니다. 사용 가능: {sorted(all_dims)}",
            )
        target_dims = requested
    else:
        target_dims = all_dims                      # 전 차원 (DVI 상위 N 제한 없음 — §14 개정)

    # 구매 주기에 따른 단발성 미등장('일시미구매')은 이상징후가 아니다(§4 생애주기 개정).
    # 이를 걸러내지 않으면 이상징후 표가 "이번 달에 안 산 고객 목록"으로 채워진다.
    exclude_dormant = params.get("exclude_dormant", True)
    dormant_note = ""
    if exclude_dormant:
        lifecycle = get_item_lifecycle(ctx)
        if lifecycle is None:
            dormant_note = " 이력이 없어 구매 주기(일시미구매) 제외를 적용하지 못했습니다."
        else:
            dormant = lifecycle[lifecycle["Lifecycle"] == LIFECYCLE_DORMANT][
                ["Dimension_Logical_Name", "Item_Name"]
            ]
            before = len(byitem)
            byitem = byitem.merge(dormant.assign(_dormant=1), how="left",
                                  on=["Dimension_Logical_Name", "Item_Name"])
            byitem = byitem[byitem["_dormant"].isna()].drop(columns="_dormant")
            removed = before - len(byitem)
            if removed:
                dormant_note = f" 구매 주기에 따른 일시미구매 {removed:,}건은 이상에서 제외."

    stats_indexed = stats.set_index("Dimension_Logical_Name")

    hits: list[pd.DataFrame] = []
    undecidable: list[str] = []       # 표본 부족·흩어짐 0 → 판정 불가 (정상으로 위장하지 않는다)

    for dim in target_dims:
        sub = byitem[byitem["Dimension_Logical_Name"] == dim].copy()
        if sub.empty:
            continue

        if sample_ceiling(len(sub)) < threshold:
            undecidable.append(f"{dim}({len(sub)}개)")
            continue

        # 증감률 축 — §5의 평균·σ 재사용 (z_score일 때만 의미 있음)
        row = stats_indexed.loc[dim] if dim in stats_indexed.index else None
        mean_rate = float(row["Rate_Mean"]) if row is not None and tool == "z_score" else None
        sigma_rate = float(row["σ"]) if row is not None and tool == "z_score" else None

        z_rate = _z_by_tool(sub["Rate"], tool, mean_rate, sigma_rate)
        z_amount = _z_by_tool(sub["Variance"], tool)

        if z_rate is None and z_amount is None:
            undecidable.append(f"{dim}(편차 0)")
            continue

        sub["Z_rate"] = z_rate if z_rate is not None else np.nan
        sub["Z_amount"] = z_amount if z_amount is not None else np.nan

        over_amount = sub["Z_amount"].abs() >= threshold
        over_rate = sub["Z_rate"].abs() >= threshold
        flagged = sub[over_amount.fillna(False) | over_rate.fillna(False)].copy()
        if flagged.empty:
            continue

        flagged["Reason"] = [
            "금액+증감률" if a and r else ("금액" if a else "증감률")
            for a, r in zip(over_amount[flagged.index].fillna(False),
                            over_rate[flagged.index].fillna(False))
        ]
        # 등급은 두 축 중 더 크게 벗어난 쪽을 따른다.
        flagged["Level"] = [
            _level(max(abs(a) if pd.notna(a) else 0.0, abs(r) if pd.notna(r) else 0.0), threshold)
            for a, r in zip(flagged["Z_amount"], flagged["Z_rate"])
        ]
        hits.append(flagged)

    note = (f" 판정 불가 차원: {', '.join(undecidable)} (항목 수 부족)." if undecidable else "") + dormant_note

    measure_name = schema.logical_name(measure)

    if not hits:
        empty = pd.DataFrame(columns=list(byitem.columns) + ["Z_rate", "Z_amount", "Reason", "Level"])
        return ModuleResult(
            outputs={"outlier_result": empty},
            render=Render(
                summary=(
                    f"{measure_name} 기준 {tool} ±{threshold:g}를 넘는 이상 항목 없음 "
                    f"(판정 대상 {len(target_dims) - len(undecidable)}개 차원).{note}"
                ),
                key_value={"측정값": measure_name, "탐지 기준": tool, "임계값": f"±{threshold:g}",
                           "이상 항목": 0, "판정 불가 차원": len(undecidable)},
            ),
        )

    detected = pd.concat(hits, ignore_index=True)
    detected = (
        detected.reindex(detected["Variance"].abs().sort_values(ascending=False).index)
        .head(top_n)
        .reset_index(drop=True)
    )
    dims_hit = detected["Dimension_Logical_Name"].nunique()

    render = render_from_dataframe(
        detected,
        purpose="금액·증감률 분포에서 크게 벗어난 이상 항목을 탐지.",
        narrative_hint=(
            "금액 영향이 큰 이탈부터 짚고, 어느 축(금액/증감률)에서 벗어났는지 구분해 설명하라. "
            "이상 항목이 없으면 그 자체가 결과임을 밝히고 임계값을 명시하라."
            + (f" {note}" if note else "")
        ),
        params={"측정값": measure_name, "탐지 기준": tool, "임계값": f"±{threshold:g}"},
        label="anomaly_detection", cache=params.get("_llm_render_cache"),
    )
    render.key_value = {
        "측정값": measure_name,
        "탐지 기준": tool,
        "임계값": f"±{threshold:g}",
        "이상 항목": len(detected),
        "해당 차원": dims_hit,
        "판정 불가 차원": len(undecidable),
    }

    return ModuleResult(outputs={"outlier_result": detected}, render=render)
