"""모듈 공용 파생 계산 — 최초 1회만 계산하고 재사용 (§6.2 재계산 금지).

여기 있는 값은 **이름표(produces/requires)가 아니다.** 이름표는 "모듈이 다른 모듈에게 넘기는
결과"이고, 여기 있는 것은 "여러 모듈이 각자 필요해서 만드는 중간 파생물"이다. 둘을 구분하는 이유:

  item_variance(§4 By_Item_DataSet)를 어떤 모듈의 produces로 등록하면, 그것을 필요로 하는 모듈은
  그 생산자 모듈을 반드시 계획에 끌어들여야 한다(예: within_contribution만 쓰고 싶어도
  dimension_impact가 딸려옴). 이는 §5 "생산자 비의존" 원칙을 깨뜨린다.

  item_variance는 actual_dataset/compare_dataset만 있으면 누구나 똑같이 유도할 수 있는 순수 파생물이다.
  따라서 생산자를 두지 않고, 먼저 필요해진 모듈이 계산해 컨텍스트에 캐시하고 나머지는 그대로 쓴다.

실행 순서에 영향을 주지 않는다(actual/compare는 이미 각 모듈의 requires에 있다).
"""
from __future__ import annotations

import pandas as pd

import d2insight.config as config
from d2insight.engine.schema import (
    ROLE_AMOUNT, ROLE_COST, ROLE_DISCOUNT, ROLE_ITEM, ROLE_OPEX, ROLE_PARTY, ROLE_PERIOD,
    ROLE_QUANTITY, get_schema,
)
from d2insight.engine.pipeline.dataset_builder import build_by_item_dataset

_ITEM_VARIANCE = "item_variance"     # 캐시 키 (이름표 사전에 없는 내부 파생물)
_ITEM_LIFECYCLE = "item_lifecycle"
_PVM_EFFECTS = "pvm_effects"
_PNL_LADDER = "pnl_ladder"           # "pnl_steps"(이름표)와 다른 값 — pnl_summary가 그 이름표를 생산한다
_LIFECYCLE_EFFECTS = "lifecycle_effects"


# ── 이력 창 슬라이스 ─────────────────────────────────────────────────────────
def slice_history_window(
    history: pd.DataFrame,
    period_col: str,
    window_months: int | None,
) -> tuple[pd.DataFrame, str]:
    """history_dataset(월별 패널)에서 **최근 window_months개월**만 잘라 돌려준다.

    왜 모듈이 직접 자르는가: history_dataset은 period_dataset이 한 번만 만드는 뿌리 이름표라
    모듈마다 다시 적재할 수 없다(§6.2 재계산 금지). 그래서 뿌리는 넉넉히 담고, 창이 필요한 모듈이
    자기 창으로 잘라 쓴다. abc_classification이 이미 쓰는 방식과 같다.

    window_months가 None이면 **자르지 않는다** — 이력 전체가 기본이다. 자동 보고서의 기본 동작을
    바꾸지 않으려는 것이고, 창 지정은 수동 모드에서 params로 들어온다.

    반환: (잘린 패널, 안내 문구)
      안내할 것이 없으면 빈 문자열이다 — 호출부가 summary에 그대로 이어붙일 수 있게
      **None을 돌려주지 않는다**(호출부마다 None 방어를 기억해야 하는 것을 막는다).
      요청한 창보다 이력이 짧으면 조용히 넘기지 않고 문구로 알린다(§11 Step 2).
    """
    if not window_months or period_col not in history.columns:
        return history, ""

    months = sorted(history[period_col].unique())
    if len(months) <= window_months:
        # 이력이 요청 창에 못 미친다. 있는 만큼 쓰되 그 사실을 밝힌다.
        return history, (f" 요청 창 {window_months}개월보다 이력이 짧아 "
                         f"{len(months)}개월로 판정했습니다.")

    keep = set(months[-window_months:])
    return history[history[period_col].isin(keep)], ""


def get_item_variance(ctx, measure: str | None = None) -> pd.DataFrame:
    """§4 By_Item_DataSet — 차원×항목별 증감/기여율/신규·단종 플래그. measure별로 최초 1회만 계산.

    measure 미지정 시 schema.key_measure(기본 measure, 보통 매출). 다른 measure를 지정하면
    (2026-07-24 4단계) measure별로 따로 캐시한다 — 같은 보고서 안에서 매출 기준과 수량 기준을
    동시에 써도 서로 덮어쓰지 않는다.

    Contribution_Rate의 분모는 공용 분모(total_variance)로 통일하되, 이는 key_measure 기준
    값이라 **다른 measure에는 쓰지 않는다**(단위가 다른 두 수를 나누면 의미 없는 값이 된다).
    key_measure와 다르면 이 measure 자체의 총 증감을 분모로 새로 잡는다.
    """
    schema = get_schema(ctx)              # 컬럼명은 코드가 아니라 데이터 정의에서 온다
    resolved_measure = measure or schema.key_measure
    cache_key = f"{_ITEM_VARIANCE}::{resolved_measure}"

    def _compute() -> pd.DataFrame:
        actual_df = ctx.get("actual_dataset")
        compare_df = ctx.get("compare_dataset")
        if actual_df is None or compare_df is None:
            raise ValueError("item_variance 계산에 actual_dataset/compare_dataset이 필요합니다.")

        byitem = build_by_item_dataset(
            actual_df, compare_df,
            measure=resolved_measure,
            dimensions=[d for d in schema.dimensions if d in actual_df.columns],
        )
        if byitem.empty:
            return byitem

        total_variance = ctx.get("total_variance")
        if resolved_measure == schema.key_measure and total_variance:
            denom = float(total_variance.get("variance") or 0.0)
        else:
            denom = float(byitem["Variance"].sum())
        byitem["Contribution_Rate"] = byitem["Variance"] / denom if denom else 0.0
        return byitem

    return ctx.get_or_compute(cache_key, _compute)


# ── 생애주기 판정 (§4 개정 2026-07-14) ───────────────────────────────────────
LIFECYCLE_NEW = "진성신규"        # 과거 구간에 활동 없음 → 이번에 처음 등장
LIFECYCLE_RETURN = "복귀"         # 직전 기간엔 없었으나 과거엔 활동 있었음 (재구매)
LIFECYCLE_CHURN = "진성이탈"      # 반복 활동하던 항목이 이번에 사라짐
LIFECYCLE_DORMANT = "일시미구매"  # 단발성 항목이 이번에 안 나타남 (구매 주기일 뿐 이탈 아님)
LIFECYCLE_KEEP = "유지"           # 두 기간 모두 활동


def get_item_lifecycle(ctx) -> pd.DataFrame | None:
    """항목별 생애주기 — history_dataset(월별 패널)의 과거 활동 이력으로 판정한다.

    왜 필요한가: 1개월 비교만으로 신규/이탈을 판정하면, **구매 주기가 긴 업종에서 거의 모든 고객이
    매달 신규 또는 이탈로 분류된다.** (AdventureWorks 2014-01 실측: 고객 2,073명 중 1,993명이 '신규',
    지난달 1,970명 중 1,890명이 '이탈' — 두 달 모두 구매한 고객은 80명뿐.) 이는 이탈이 아니라
    "이번 달에 안 샀다"일 뿐이다. 이탈 고객 관리가 중요한 업종(쇼핑몰·백화점·의류·식품)에서
    이런 수치는 쓸모가 없다.

    판정 기준 (과거 구간 = 분석월 이전의 이력 개월)
      진성신규   : 분석기간 활동 O, 과거 활동 개월수 = 0
      복귀       : 분석기간 활동 O, 비교기간 활동 X, 과거 활동 개월수 >= 1
      유지       : 분석기간 활동 O, 비교기간 활동 O
      진성이탈   : 분석기간 활동 X, 비교기간 활동 O, 과거 활동 개월수 >= LIFECYCLE_MIN_ACTIVE_MONTHS
      일시미구매 : 분석기간 활동 X, 비교기간 활동 O, 과거 활동 개월수 < 임계 (단발 구매자)

    history_dataset이 없으면 None을 돌려준다. 호출 모듈은 이를 "판정 불가"로 **명시**해야 하며
    조용히 1개월 정의로 되돌아가서는 안 된다.
    """
    def _compute() -> pd.DataFrame | None:
        history = ctx.get("history_dataset")
        byitem = get_item_variance(ctx)
        if history is None or history.empty or byitem.empty:
            return None

        schema = get_schema(ctx)
        period_col = schema.column(ROLE_PERIOD)
        amount_col = schema.column(ROLE_AMOUNT) or schema.key_measure
        if not period_col or period_col not in history.columns or amount_col not in history.columns:
            return None                                     # 이력에 기간·금액이 없으면 판정 불가

        target_month = ctx.meta.get("target_month")
        past = history[history[period_col] != target_month]  # 분석월 제외 = 과거 구간
        if past.empty:
            return None

        min_active = int(getattr(config, "LIFECYCLE_MIN_ACTIVE_MONTHS", 2))
        rows = []

        for dim in byitem["Dimension_Logical_Name"].unique():
            if dim not in past.columns:
                continue                                    # 이력에 없는 차원은 판정 불가
            # 항목별 과거 활동 기간수 (금액 > 0 인 기간)
            active = (
                past[past[amount_col] > 0]
                .groupby([dim, period_col])[amount_col].sum()
                .reset_index()
                .groupby(dim)[period_col].nunique()
            )
            sub = byitem[byitem["Dimension_Logical_Name"] == dim]
            for _, r in sub.iterrows():
                item = r["Item_Name"]
                past_months = int(active.get(item, 0))
                has_actual = float(r["Actual_Value"]) > 0
                has_compare = float(r["Comparison_Value"]) > 0

                if has_actual and not has_compare:
                    stage = LIFECYCLE_NEW if past_months == 0 else LIFECYCLE_RETURN
                elif has_actual:
                    stage = LIFECYCLE_KEEP
                elif has_compare:
                    stage = LIFECYCLE_CHURN if past_months >= min_active else LIFECYCLE_DORMANT
                else:
                    continue

                rows.append({
                    "Dimension_Logical_Name": dim,
                    "Item_Name": item,
                    "Past_Active_Months": past_months,
                    "Lifecycle": stage,
                })

        return pd.DataFrame(rows) if rows else None

    return ctx.get_or_compute(_ITEM_LIFECYCLE, _compute)


def get_lifecycle_effects(ctx) -> pd.DataFrame | None:
    """항목×차원별 생애주기에 금액효과(Effect)를 붙인 표 — 최초 1회만 계산해 재사용(§6.2).

    new_lost_detection(여러 차원을 한 번에 보는 통합 스텝)과, 고객 신규/이탈을 독립 스텝으로
    나눈 리프 모듈(2026-07-21, 시나리오 3 "고객 분석")이 이 표를 나눠 쓴다. 두 곳이 각자
    item_variance×item_lifecycle을 merge하면 같은 계산을 두 번 하게 되므로 여기서 한 번만 한다.

    Effect: 진성신규·복귀(등장)는 분석기간 금액, 진성이탈·일시미구매(소멸)는 비교기간 금액(손실),
    유지는 Variance. 항목 증감(item_variance)·생애주기(item_lifecycle) 중 하나라도 없으면 None
    (호출 모듈이 "이력이 없어 판정 불가"로 명시적 실패 처리한다, §11 Step 2).
    """
    def _compute() -> pd.DataFrame | None:
        byitem = get_item_variance(ctx)
        lifecycle = get_item_lifecycle(ctx)
        if byitem is None or byitem.empty or lifecycle is None or lifecycle.empty:
            return None

        merged = byitem.merge(lifecycle, on=["Dimension_Logical_Name", "Item_Name"], how="inner")
        merged["Effect"] = merged.apply(
            lambda r: float(r["Actual_Value"]) if r["Lifecycle"] in (LIFECYCLE_NEW, LIFECYCLE_RETURN)
            else (-float(r["Comparison_Value"]) if r["Lifecycle"] in (LIFECYCLE_CHURN, LIFECYCLE_DORMANT)
                  else float(r["Variance"])),
            axis=1,
        )
        return merged

    return ctx.get_or_compute(_LIFECYCLE_EFFECTS, _compute)


# ── PVM(물량·믹스·가격) 분해 (2026-07-20, 시나리오 1의 Volume/Price/Mix 3스텝 공용) ───
def get_pvm_effects(ctx) -> dict:
    """물량(Volume)/믹스(Mix)/가격(Price) 분해 — 최초 1회만 계산해 재사용(§6.2 재계산 금지).

    Volume/Price/Mix가 시나리오에서 **각각 독립 스텝**이라(스텝=섹션 원칙, 2026-07-20), 세
    모듈(volume_effect/price_effect/mix_effect)이 이 값을 나눠 쓴다. 여기서 한 번만 계산해야
    세 스텝의 숫자가 항상 같은 계산에서 나온다 — 모듈마다 따로 계산하면 반올림·데이터 스냅샷
    차이로 세 스텝의 합이 어긋날 수 있다.

    규약(두 기간 모두 존재하는 항목만 대상 — 신규·이탈은 new_lost_detection이 다룬다):
        Volume = (Qa − Qc) × (ΣAmt_c / Qc)                 순수 물량(믹스 불변)
        Mix    = Σ(q_ia − q_ic)·p_ic  −  Volume             구성 이동
        Price  = Σ q_ia·(p_ia − p_ic)                        단가 변화
        검산: Volume + Mix + Price = 공통 항목 매출 변화(covered_variance)

    실패하면 ValueError를 올린다(호출 모듈이 §11 Step 2 형태의 실패로 변환한다).
    """
    def _compute() -> dict:
        actual_df = ctx.get("actual_dataset")
        compare_df = ctx.get("compare_dataset")
        if actual_df is None or compare_df is None:
            raise ValueError("선행 데이터(actual/compare)가 없습니다.")

        schema = get_schema(ctx)
        amount = schema.column(ROLE_AMOUNT) or schema.key_measure
        quantity = schema.column(ROLE_QUANTITY)
        item = schema.column(ROLE_ITEM)

        if not quantity or quantity not in actual_df.columns:
            raise ValueError("물량(quantity) 역할이 없어 물량·믹스를 가를 수 없습니다. "
                             "데이터소스 정의에 quantity 역할을 선언하세요.")
        if not item or item not in actual_df.columns:
            raise ValueError("항목(item) 역할이 없어 믹스를 계산할 수 없습니다.")

        a = actual_df.groupby(item)[[amount, quantity]].sum()
        c = compare_df.groupby(item)[[amount, quantity]].sum()
        panel = a.join(c, how="outer", lsuffix="_a", rsuffix="_c").fillna(0.0)

        # 두 기간 모두 물량이 있는 항목만 — 단가·믹스가 정의된다(신규·이탈은 다른 모듈이 다룸).
        qa, qc = f"{quantity}_a", f"{quantity}_c"
        aa, ac = f"{amount}_a", f"{amount}_c"
        keep = panel[(panel[qa] > 0) & (panel[qc] > 0)].copy()
        if keep.empty:
            raise ValueError("두 기간 모두 존재하는 항목이 없어 PVM 분해가 불가합니다.")

        Q_c = float(keep[qc].sum())
        Q_a = float(keep[qa].sum())
        avg_price_c = float(keep[ac].sum()) / Q_c if Q_c else 0.0

        p_ic = keep[ac] / keep[qc]                       # 항목별 비교기간 단가
        p_ia = keep[aa] / keep[qa]                       # 항목별 분석기간 단가

        quantity_effect = float(((keep[qa] - keep[qc]) * p_ic).sum())   # 물량효과(비교단가 기준)
        volume = (Q_a - Q_c) * avg_price_c                              # 순수 물량(믹스 불변)
        mix = quantity_effect - volume                                 # 구성 이동
        price = float((keep[qa] * (p_ia - p_ic)).sum())                # 단가 변화
        covered_variance = float(keep[aa].sum() - keep[ac].sum())      # 공통 항목 매출 변화(검산)

        return {"volume": volume, "mix": mix, "price": price,
                "covered_variance": covered_variance}

    return ctx.get_or_compute(_PVM_EFFECTS, _compute)


# ── 브리지 분해(§13, 2026-07-14 개정) — sales_bridge 모듈과 Volume/Price 스텝의 "bridge" ──
# 툴이 공유한다(2026-07-22, 옵션 검증 작업). 분해 규칙·가법성 검산은 원래 bridge.py 그대로이고,
# 계산 코드는 여기 한 곳뿐이다 — sales_bridge와 volume_effect/price_effect(tool="bridge")가
# 같은 보고서에 함께 있어도 숫자가 한 벌에서 나온다.
_BRIDGE_CALC = "bridge_decompose_calc"   # 캐시 키. sales_bridge의 이름표("bridge_effects")와
                                          # 문자열이 겹치면 ctx._store에서 충돌하므로 다르게 둔다.

_BRIDGE_APPEAR = (LIFECYCLE_NEW, LIFECYCLE_RETURN)        # 이번 기간에만 존재 → 유입
_BRIDGE_DISAPPEAR = (LIFECYCLE_CHURN, LIFECYCLE_DORMANT)  # 비교 기간에만 존재 → 손실


def _bridge_lifecycle_map(ctx, dim: str) -> dict[str, str] | None:
    lc = get_item_lifecycle(ctx)
    if lc is None or lc.empty:
        return None
    sub = lc[lc["Dimension_Logical_Name"] == dim]
    return dict(zip(sub["Item_Name"], sub["Lifecycle"])) if not sub.empty else None


def _bridge_panel(actual_df: pd.DataFrame, compare_df: pd.DataFrame,
                   dim: str, cols: list[str]) -> pd.DataFrame:
    """차원 항목별 두 기간 측정값 대조표."""
    a = actual_df.groupby(dim)[cols].sum()
    c = compare_df.groupby(dim)[cols].sum()
    return a.join(c, how="outer", lsuffix="_a", rsuffix="_c").fillna(0.0)


def _bridge_stage_of(item: str, row: pd.Series, lc_map: dict | None, amount: str) -> str:
    """생애주기 라벨. 이력이 없으면 산술 구분으로 폴백(가법성은 그대로 성립)."""
    if lc_map and item in lc_map:
        return lc_map[item]
    if row[f"{amount}_a"] > 0 and row[f"{amount}_c"] > 0:
        return LIFECYCLE_KEEP
    return LIFECYCLE_NEW if row[f"{amount}_a"] > 0 else LIFECYCLE_CHURN


def _bridge_decompose(panel: pd.DataFrame, lc_map: dict | None, *,
                       amount: str, quantity: str | None, discount: str | None) -> list[dict]:
    """한 관점의 가법 분해. quantity 역할이 있으면 기존 항목을 수량/정가ASP/할인으로 쪼갠다."""
    stages = {item: _bridge_stage_of(item, row, lc_map, amount) for item, row in panel.iterrows()}
    stage_s = pd.Series(stages)
    a_col, c_col = f"{amount}_a", f"{amount}_c"

    effects: list[dict] = []
    for stage in _BRIDGE_APPEAR:                 # 유입 = 분석기간 금액 전액
        items = stage_s[stage_s == stage].index
        if len(items):
            effects.append({"효과": f"{stage} 효과", "금액": float(panel.loc[items, a_col].sum()),
                            "항목수": len(items)})
    for stage in _BRIDGE_DISAPPEAR:               # 손실 = 비교기간 금액 전액(음수)
        items = stage_s[stage_s == stage].index
        if len(items):
            effects.append({"효과": f"{stage} 효과", "금액": -float(panel.loc[items, c_col].sum()),
                            "항목수": len(items)})

    keep = panel.loc[stage_s[stage_s == LIFECYCLE_KEEP].index]
    if keep.empty:
        return effects

    if not quantity:
        effects.append({"효과": "유지 항목 증감", "금액": float((keep[a_col] - keep[c_col]).sum()),
                        "항목수": len(keep)})
        return effects

    qa, qc = keep[f"{quantity}_a"], keep[f"{quantity}_c"]
    da = keep[f"{discount}_a"] if discount else 0.0
    dc = keep[f"{discount}_c"] if discount else 0.0
    # 정가ASP = (순금액 + 할인액) / 물량 — 할인을 걷어낸 가격
    gross_a = ((keep[a_col] + da) / qa.where(qa > 0)).fillna(0.0)
    gross_c = ((keep[c_col] + dc) / qc.where(qc > 0)).fillna(0.0)

    effects.extend([
        {"효과": "기존 항목 수량 효과", "금액": float(((qa - qc) * gross_c).sum()), "항목수": len(keep)},
        {"효과": "기존 항목 정가(ASP) 효과", "금액": float(((gross_a - gross_c) * qa).sum()),
         "항목수": len(keep)},
    ])
    if discount:
        effects.append({"효과": "기존 항목 할인 효과", "금액": float(-((da - dc).sum())),
                        "항목수": len(keep)})
    return effects


def get_bridge_effects(ctx) -> dict:
    """상품·고객 관점의 매출 증감 가법 분해(§13) — 최초 1회만 계산해 재사용(§6.2).

    실패(선행 데이터 없음·item/party 역할 없음·가법성 검산 불일치)하면 ValueError를 올린다
    (호출 모듈이 §11 Step 2 형태의 실패로 변환한다).

    반환:
        total_variance: float
        views: {관점명: [{"효과","금액","항목수"}, ...]}  — 각 관점 합계는 total_variance와 같다(검산 통과)
        item_effects: DataFrame[Item_Name,증감,수량효과,ASP효과,할인효과] | None
                      (상품 관점, 두 기간 모두 존재하는 항목만 — top_n으로 자르지 않는다, 호출부 몫)
        lifecycle_based: bool
        quantity_available: bool  — False면 volume/price 분해가 무의미(수량 역할 없음)
    """
    def _compute() -> dict:
        actual_df = ctx.get("actual_dataset")
        compare_df = ctx.get("compare_dataset")
        total_variance = ctx.get("total_variance")
        if actual_df is None or compare_df is None or not total_variance:
            raise ValueError("선행 데이터(actual/compare/total_variance)가 없습니다.")

        schema = get_schema(ctx)
        amount = schema.column(ROLE_AMOUNT) or schema.key_measure
        quantity = schema.column(ROLE_QUANTITY)
        discount = schema.column(ROLE_DISCOUNT)
        if quantity and quantity not in actual_df.columns:
            quantity = None
        if discount and discount not in actual_df.columns:
            discount = None

        total = float(total_variance["variance"])
        lifecycle_available = get_item_lifecycle(ctx) is not None
        measure_cols = [c for c in (amount, quantity, discount) if c]

        views: dict[str, list[dict]] = {}
        for role, split in ((ROLE_ITEM, True), (ROLE_PARTY, False)):
            dim = schema.column(role)
            if not dim or dim not in actual_df.columns:
                continue
            views[f"{schema.logical_name(dim)} 관점"] = _bridge_decompose(
                _bridge_panel(actual_df, compare_df, dim, measure_cols),
                _bridge_lifecycle_map(ctx, dim),
                amount=amount,
                quantity=quantity if split else None,     # 가격 분해는 개체(item) 관점에서만 의미가 있다
                discount=discount if split else None,
            )
        if not views:
            raise ValueError("item·party 역할 차원이 없어 분해할 수 없습니다. 데이터소스 정의를 확인하세요.")

        # 검산 — 각 관점의 합이 전체 증감액과 맞아야 브리지가 성립한다.
        mismatch = []
        for view, effects in views.items():
            gap = sum(e["금액"] for e in effects) - total
            if abs(gap) > max(1.0, abs(total) * 1e-6):
                mismatch.append(f"{view} 합계가 전체 증감액과 {gap:+,.0f} 어긋남")
        if mismatch:
            raise ValueError("브리지 분해 검산 실패: " + "; ".join(mismatch))

        item_effects = None
        item_dim = schema.column(ROLE_ITEM)
        if item_dim and quantity and item_dim in actual_df.columns:
            panel = _bridge_panel(actual_df, compare_df, item_dim, measure_cols)
            a_col, c_col = f"{amount}_a", f"{amount}_c"
            keep = panel[(panel[a_col] > 0) & (panel[c_col] > 0)].copy()
            if not keep.empty:
                qa, qc = keep[f"{quantity}_a"], keep[f"{quantity}_c"]
                da = keep[f"{discount}_a"] if discount else 0.0
                dc = keep[f"{discount}_c"] if discount else 0.0
                ga = ((keep[a_col] + da) / qa.where(qa > 0)).fillna(0.0)
                gc = ((keep[c_col] + dc) / qc.where(qc > 0)).fillna(0.0)
                keep["수량효과"] = (qa - qc) * gc
                keep["ASP효과"] = (ga - gc) * qa
                keep["할인효과"] = -(da - dc) if discount else 0.0
                keep["증감"] = keep[a_col] - keep[c_col]
                item_effects = (
                    keep.reindex(keep["증감"].abs().sort_values(ascending=False).index)
                    [["증감", "수량효과", "ASP효과", "할인효과"]]
                    .round(2).reset_index()
                )

        return {
            "total_variance": total,
            "views": views,
            "item_effects": item_effects,
            "lifecycle_based": lifecycle_available,
            "quantity_available": quantity is not None,
        }

    return ctx.get_or_compute(_BRIDGE_CALC, _compute)


# ── 손익 계단 (2026-07-21, 시나리오 5 "손익 분석"의 Revenue~EBIT 5스텝 공용) ─────
def get_pnl_ladder(ctx) -> dict:
    """매출→매출원가→매출총이익→판관비→영업이익 각 단계 값 — 최초 1회만 계산해 재사용.

    5개 리프 모듈(revenue_step/cogs_step/gross_margin_step/opex_step/ebit_step)과
    pnl_summary(§ 제품 분석의 단일 "이익" 스텝용 통합 뷰)가 나눠 쓴다. 여기서 한 번만 계산해야
    다섯 스텝의 숫자가 항상 같은 계산에서 나온다.

    반환: {"steps": {단계명: {Comparison_Value, Actual_Value, Variance, Rate, Comparison_Margin,
      Actual_Margin}}, "has_opex": bool}
    이익률·비용률(Margin)은 매출 대비 비율이라 기간별로 따로 낸다(합산이 성립하지 않음).

    cost 역할이 없으면 손익 계단 자체가 성립하지 않으므로 ValueError(호출 모듈이 §11 Step 2
    실패로 변환). opex 역할만 없으면 has_opex=False — 매출총이익까지만 유효하고, 판관비·
    영업이익 스텝은 호출 모듈이 각자 명시적으로 실패 처리한다(조용히 생략하지 않는다).
    """
    def _compute() -> dict:
        actual_df = ctx.get("actual_dataset")
        compare_df = ctx.get("compare_dataset")
        if actual_df is None or compare_df is None:
            raise ValueError("선행 데이터(actual/compare)가 없습니다.")

        schema = get_schema(ctx)
        amount_col = schema.column(ROLE_AMOUNT) or schema.key_measure
        cost_col = schema.column(ROLE_COST)
        opex_col = schema.column(ROLE_OPEX)

        if amount_col not in actual_df.columns:
            raise ValueError(f"금액 컬럼 '{amount_col}'이 데이터에 없습니다.")
        if not cost_col or cost_col not in actual_df.columns:
            raise ValueError("매출원가(cost 역할) 컬럼이 없어 손익 분석을 할 수 없습니다. "
                             "데이터소스 정의에 cost 역할을 선언하세요.")

        def _sum(df: pd.DataFrame, col: str | None) -> float:
            return float(df[col].sum()) if col and col in df.columns else 0.0

        rev_a, rev_c = _sum(actual_df, amount_col), _sum(compare_df, amount_col)
        cogs_a, cogs_c = _sum(actual_df, cost_col), _sum(compare_df, cost_col)
        gm_a, gm_c = rev_a - cogs_a, rev_c - cogs_c

        def _step(name: str, compare: float, actual: float) -> dict:
            variance = actual - compare
            return {
                "Step": name,
                "Comparison_Value": compare,
                "Actual_Value": actual,
                "Variance": variance,
                "Rate": variance / compare if compare else 0.0,
                "Comparison_Margin": compare / rev_c if rev_c else 0.0,
                "Actual_Margin": actual / rev_a if rev_a else 0.0,
            }

        steps = {
            "매출": _step("매출", rev_c, rev_a),
            "매출원가": _step("매출원가", cogs_c, cogs_a),
            "매출총이익": _step("매출총이익", gm_c, gm_a),
        }
        has_opex = bool(opex_col) and opex_col in actual_df.columns
        if has_opex:
            opex_a, opex_c = _sum(actual_df, opex_col), _sum(compare_df, opex_col)
            ebit_a, ebit_c = gm_a - opex_a, gm_c - opex_c
            steps["판매관리비"] = _step("판매관리비", opex_c, opex_a)
            steps["영업이익"] = _step("영업이익", ebit_c, ebit_a)

        return {"steps": steps, "has_opex": has_opex}

    return ctx.get_or_compute(_PNL_LADDER, _compute)
