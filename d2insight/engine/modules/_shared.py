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
    ROLE_AMOUNT, ROLE_COST, ROLE_DISCOUNT, ROLE_ITEM, ROLE_ITEM_GROUP, ROLE_OPEX, ROLE_PARTY,
    ROLE_PERIOD, ROLE_QUANTITY, Schema, get_schema, ALL_ROLES,
)
from d2insight.engine.pipeline.data_request import (
    fetch_measure_groups, fetch_series, fetch_wide, load_meta, pick_by_rows, pick_reachable, reachable_dims,
    source_of,
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


def get_frames(ctx, measures: list[str], params: dict | None = None) -> dict:
    """모든 분석 차원과 요청한 측정값을 담은 (실적, 비교) 표 — 최초 1회만 가져와 캐시한다.

    스텝 공용 표(actual_dataset/compare_dataset)는 두 테이블을 조인해 만들어져 '1'쪽 값이 중복
    합산될 수 있어(2026-09-28 사고) 공용 계산과 모듈들이 이 함수를 대신 쓴다. 측정값마다 전용
    조회 + 합계 검사를 거친다(data_request.fetch_wide). 요청한 측정값을 그 기준으로 나눌 수
    없으면 나눌 수 있는 값으로 바뀌어 조회되고, 그 사실이 notes에 담긴다.

    params를 주면 만든 SQL이 params["_queries"]에 남아 정기보고서에 저장된다(첫 호출한 모듈에 붙는다).

    반환: {"actual", "compare", "used": {요청한 이름: 실제 쓴 이름}, "notes": [...]}
    실패하면 ValueError를 올린다(호출 모듈이 §11 Step 2 형태의 실패로 변환한다).
    """
    schema = get_schema(ctx)
    key = "frames::" + ",".join(measures)

    def _compute() -> dict:
        dims = reachable_dims(ctx.meta, list(measures), list(schema.causal_dimensions))
        meta = ctx.get("meta_columns")
        if meta is None or not (set(measures) | set(dims)) <= set(meta["Physical_Name"]):
            meta = load_meta(ctx.meta)          # 스텝 공용 표에 없는 컬럼이면 전체 메타를 쓴다
        queries = params.setdefault("_queries", []) if params is not None else []
        result = fetch_wide(ctx.meta, meta, schema, list(measures), dims, queries)
        if result.get("error"):
            raise ValueError(result["error"])
        return result

    return ctx.get_or_compute(key, _compute)


def get_full_schema(ctx) -> Schema:
    """스텝 공용 표에 없는 컬럼(차원)까지 담은 전체 스키마(역할 조회용).

    스텝의 meta_columns는 그 스텝이 요청한 컬럼만 담는다. 그런데 공용 계산(항목별 증감·생애주기)은
    보고서 전체에서 한 번 만든 전체 차원 표를 재사용하므로, 역할(item/party 등)을 찾을 때는 전체
    스키마를 써야 한다 — 스텝 meta로 찾으면 그 스텝이 요청하지 않은 차원의 역할은 없는 것처럼 보인다.
    """
    def _compute() -> Schema:
        meta = load_meta(ctx.meta)
        # [진단] 의미 표시별로 어느 컬럼이 걸렸는지(컬럼, 측정값/차원/제외) — 확인 후 삭제
        if "Semantic_Type" in meta.columns:
            parts = []
            for role in sorted(ALL_ROLES):
                rows = meta[meta["Semantic_Type"] == role]
                if len(rows):
                    parts.append(f"{role}={[(r.Physical_Name, r.Field_Type) for r in rows.itertuples()]}")
            print("[진단-의미] " + " | ".join(parts))
        return Schema(meta)

    return ctx.get_or_compute("full_schema", _compute)


def pick_dimension(ctx, role: str, measures: list[str]) -> str | None:
    """같은 의미(role)의 컬럼이 여러 파일에 있을 때, 측정값이 든 파일에서 닿는 것을 고른다.

    schema.column(role)은 맨 앞 컬럼을 돌려준다. 업로드 파일이 여럿이면 그것이 측정값 파일과 연결되지
    않는 파일의 컬럼일 수 있다(재고 분석에서 항목으로 라인명이 잡혀 재고와 이어지지 않았다).
    """
    return pick_reachable(ctx.meta, get_full_schema(ctx).columns(role), measures)


def role_column(ctx, role: str, ref: str | None = None) -> str | None:
    """역할 컬럼 하나(합산 제외 컬럼은 이미 빠져 있다). 같은 역할이 여러 파일에 있으면 기준 측정값(ref)이
    든 파일에서 닿는 것을, 기준이 없으면 행이 가장 많은 파일(가장 세분된 거래)의 것을 고른다."""
    cols = get_full_schema(ctx).columns(role)
    if len(cols) <= 1:
        return cols[0] if cols else None
    return pick_reachable(ctx.meta, cols, [ref]) if ref else pick_by_rows(ctx.meta, cols)


def key_measure_of(ctx) -> str:
    """분석의 기준 측정값 — 금액 역할 중 기준 파일의 것, 없으면 메타의 핵심 표시. 총평(measure_summary)과 모든
    모듈이 같은 값을 쓰도록 한 곳에서 정한다(합친 메타의 첫 핵심 표시는 파일 순서에 따라 달라진다)."""
    return role_column(ctx, ROLE_AMOUNT) or get_schema(ctx).key_measure


def get_dim_frames(ctx, measures: list[str], dimension: str | None, params: dict | None = None) -> dict:
    """모듈이 쓰는 차원 하나로 작성된 (실적, 비교) 표 — 전용 조회 + 합계 검사를 거친다.

    get_frames는 모든 차원으로 작성된 표를 가져오지만, 이 함수는 모듈이 쓰는 차원 하나로 작성된 표를
    가져온다(재고 계열처럼 항목 단위 차원 하나만 필요한 모듈용). dimension이 없으면 합계 한 줄짜리 표를
    돌려준다. 요청한 측정값을 그 차원으로 작성할 수 없으면 다른 측정값으로 바뀌어 조회될 수 있다 —
    바뀐 것을 받아들일지는 호출 모듈이 정한다(frames["used"]).

    반환: {"actual", "compare", "used": {요청한 이름: 실제 쓴 이름}, "notes": [...]}
    실패하면 ValueError를 올린다.
    """
    key = "frames::" + (dimension or "-") + "::" + ",".join(measures)

    def _compute() -> dict:
        meta = load_meta(ctx.meta)
        queries = params.setdefault("_queries", []) if params is not None else []
        if dimension:
            result = fetch_wide(ctx.meta, meta, Schema(meta), list(measures), [dimension], queries)
            if result.get("error"):
                raise ValueError(result["error"])
            # [진단] 요청한 측정값의 실적/비교 행 수와 합계 — 확인 후 삭제
            used = list(result["used"].values())
            print(f"[진단-요청] 측정값={measures} 차원={dimension} 실적행={len(result['actual'])} "
                  f"비교행={len(result['compare'])} "
                  f"실적합={ {m: float(result['actual'][m].sum()) for m in used if m in result['actual'].columns} } "
                  f"비교합={ {m: float(result['compare'][m].sum()) for m in used if m in result['compare'].columns} }")
            return result
        actual: dict = {}
        compare: dict = {}
        for g in fetch_measure_groups(ctx.meta, list(measures), meta, queries=queries):
            if g["error"]:
                raise ValueError(f"측정값 {g['measures']} 합계 조회에 실패했습니다: {g['error']}")
            for m in g["measures"]:
                actual[m] = float(g["actual"][m].sum())
                compare[m] = float(g["compare"][m].sum())
        return {"actual": pd.DataFrame([actual]), "compare": pd.DataFrame([compare]),
                "used": {m: m for m in measures}, "notes": []}

    return ctx.get_or_compute(key, _compute)


def get_series(ctx, measure: str, dimension: str | None, params: dict | None = None,
               aggregate: str = "sum") -> pd.DataFrame:
    """측정값 하나의 기간별 값 — [기간, (차원), 측정값] 표를 모듈이 필요할 때 직접 요청한다.

    기간 수는 params.window_months → params.months_back → 보고서 설정 → config 순으로 정한다.
    같은 요청은 한 번만 가져온다(ctx 캐시). 첫 열이 기간 식별자다.
    실패하면 ValueError를 올린다.
    """
    p = params or {}
    months_back = int(p.get("window_months") or p.get("months_back") or ctx.meta.get("months_back")
                      or getattr(config, "HISTORY_MONTHS", 7))
    grain = ctx.meta.get("grain") or "month"
    agg = p.get("aggregate") or aggregate
    key = f"series::{measure}::{dimension or '-'}::{months_back}::{grain}::{agg}"

    def _compute() -> pd.DataFrame:
        return fetch_series(ctx.meta, load_meta(ctx.meta), get_full_schema(ctx), measure, dimension,
                            months_back, grain, agg, p.setdefault("_queries", []) if params is not None else [])

    return ctx.get_or_compute(key, _compute)


def _history_attrs(ctx) -> dict:
    history = ctx.get("history_dataset")
    return getattr(history, "attrs", None) or {}


def history_col(ctx, col: str | None) -> str | None:
    """이력 표에서 실제로 읽을 컬럼 이름.

    요청한 측정값(예: 총 주문 금액)을 상품 같은 기준으로 나눌 수 없어 다른 값(라인 매출)으로 이력을
    만들었으면 그 이름을 돌려준다. 바뀐 게 없으면 받은 이름 그대로.
    """
    if not col:
        return col
    return (_history_attrs(ctx).get("alias") or {}).get(col, col)


def history_notes(ctx) -> str:
    """이력 표에서 측정값이 바뀌었다는 안내를 해설 지시문에 붙일 문장으로 만든다(없으면 빈 문자열)."""
    notes = _history_attrs(ctx).get("notes") or []
    return "".join(f" {n} — 이 사실을 한 문장으로 밝혀라." for n in notes)


def history_totals(ctx) -> pd.DataFrame | None:
    """기간별 측정값 합계 표(기준 없음). 측정값이 바뀌지 않은, 요청한 그대로의 값이다."""
    totals = _history_attrs(ctx).get("totals")
    return totals if totals is not None and len(totals) else None


def get_item_variance(ctx, measure: str | None = None, params: dict | None = None) -> pd.DataFrame:
    """§4 By_Item_DataSet — 차원×항목별 증감/기여율/신규·단종 플래그. measure별로 최초 1회만 계산.

    measure 미지정 시 schema.key_measure(기본 measure, 보통 매출). 다른 measure를 지정하면
    (2026-07-24 4단계) measure별로 따로 캐시한다 — 같은 보고서 안에서 매출 기준과 수량 기준을
    동시에 써도 서로 덮어쓰지 않는다.

    Contribution_Rate의 분모는 공용 분모(total_variance)로 통일하되, 이는 key_measure 기준
    값이라 **다른 measure에는 쓰지 않는다**(단위가 다른 두 수를 나누면 의미 없는 값이 된다).
    key_measure와 다르면 이 measure 자체의 총 증감을 분모로 새로 잡는다.
    """
    schema = get_schema(ctx)              # 컬럼명은 코드가 아니라 데이터 정의에서 온다
    resolved_measure = measure or key_measure_of(ctx)
    cache_key = f"{_ITEM_VARIANCE}::{resolved_measure}"

    def _compute() -> pd.DataFrame:
        frames = get_frames(ctx, [resolved_measure], params)
        actual_df, compare_df = frames["actual"], frames["compare"]
        used = frames["used"][resolved_measure]      # 나눌 수 없어 다른 값으로 바뀌었을 수 있다

        byitem = build_by_item_dataset(
            actual_df, compare_df,
            measure=used,
            # causal_dimensions — 인과분석(원인 순위·이상징후·기여도·교차분석) 공용 파생물이라
            # 관리용 구분(법인·부서 등)은 뺀다. 현황 서술 모듈은 이 함수를 안 쓴다.
            dimensions=[d for d in schema.causal_dimensions if d in actual_df.columns],
        )
        if byitem.empty:
            return byitem

        total_variance = ctx.get("total_variance")
        if used != resolved_measure:
            # 바뀐 값의 기여율은 그 값 자신의 전체 증감으로 나눈다(총평의 핵심 값과 단위가 다르다).
            denom = float(actual_df[used].sum() - compare_df[used].sum())
        elif resolved_measure == key_measure_of(ctx) and total_variance:
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
    """항목별 생애주기 — 차원별 기간별 금액(get_series)의 과거 활동 이력으로 판정한다.

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

    과거 활동 이력을 가져오지 못하면 None을 돌려준다. 호출 모듈은 이를 "판정 불가"로 **명시**해야 하며
    조용히 1개월 정의로 되돌아가서는 안 된다.
    """
    def _compute() -> pd.DataFrame | None:
        byitem = get_item_variance(ctx)
        if byitem.empty:
            print("[진단-생애주기] 판정 불가 — 항목별 증감 표 비어 있음")  # [진단] 확인 후 삭제
            return None

        # 과거 활동은 판정할 차원마다 금액을 기간별로 직접 요청해 구한다(모듈이 필요한 만큼만).
        schema = get_full_schema(ctx)
        amount_col = role_column(ctx, ROLE_AMOUNT) or schema.key_measure
        target_month = ctx.meta.get("target_month")

        min_active = int(getattr(config, "LIFECYCLE_MIN_ACTIVE_MONTHS", 2))
        rows = []

        for dim in byitem["Dimension_Logical_Name"].unique():
            try:
                series = get_series(ctx, amount_col, dim)
            except ValueError as e:
                print(f"[진단-생애주기] '{dim}' 기간별 값 조회 실패: {e}")  # 이 차원은 판정 불가
                continue
            period_col = series.columns[0]
            past = series[series[period_col] != target_month]       # 분석월 제외 = 과거 구간
            # 항목별 과거 활동 기간수 (금액 > 0 인 기간)
            active = past[past[amount_col] > 0].groupby(dim)[period_col].nunique()
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
def get_pvm_effects(ctx, params: dict | None = None) -> dict:
    """물량(Volume)/믹스(Mix)/가격(Price) 분해 — 최초 1회만 계산해 재사용(§6.2 재계산 금지).

    Volume/Price/Mix가 시나리오에서 **각각 독립 스텝**이라(스텝 분리 원칙, 2026-07-20), 세
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
        schema = get_schema(ctx)
        amount = role_column(ctx, ROLE_AMOUNT) or schema.key_measure
        quantity = role_column(ctx, ROLE_QUANTITY, amount)
        item = schema.column(ROLE_ITEM)

        if not quantity:
            raise ValueError("물량(quantity) 역할이 없어 물량·믹스를 가를 수 없습니다. "
                             "데이터소스 정의에 quantity 역할을 선언하세요.")
        if not item:
            raise ValueError("항목(item) 역할이 없어 믹스를 계산할 수 없습니다.")

        # 스텝 공용 표 대신 전용 조회 — 금액이 항목으로 나눌 수 없는 값이면 나눌 수 있는 값으로 바뀐다.
        frames = get_frames(ctx, [amount, quantity], params)
        actual_df, compare_df = frames["actual"], frames["compare"]
        amount, quantity = frames["used"][amount], frames["used"][quantity]
        if item not in actual_df.columns:
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

        # total_variance: 분해에 실제로 쓴 금액 자신의 전체 증감 — 나눌 수 없어 바뀐 값이면 총평의
        # 핵심 측정값과 다르다. 비중은 이 값으로 낸다.
        return {"volume": volume, "mix": mix, "price": price,
                "covered_variance": covered_variance, "notes": frames["notes"],
                "total_variance": float(actual_df[amount].sum() - compare_df[amount].sum())}

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


_UNCLASSIFIED = "(미분류)"


def _bridge_panel(actual_df: pd.DataFrame, compare_df: pd.DataFrame,
                   dim: str, cols: list[str]) -> pd.DataFrame:
    """차원 항목별 두 기간 측정값 대조표.

    groupby는 기본적으로 결측값(NaN) 행을 그룹에서 통째로 뺀다 — dim 컬럼에 빈 값이 섞여
    있으면 그 행의 금액이 어느 항목에도 안 잡혀, 항목별 합계가 전체 증감액에 못 미치는
    검산 실패로 이어진다(2026-08-26 확인). 빈 값도 "(미분류)"로 잡아 반영한다.
    """
    a = actual_df.groupby(actual_df[dim].fillna(_UNCLASSIFIED))[cols].sum()
    c = compare_df.groupby(compare_df[dim].fillna(_UNCLASSIFIED))[cols].sum()
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


def get_bridge_effects(ctx, params: dict | None = None) -> dict:
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
        schema = get_schema(ctx)
        amount = role_column(ctx, ROLE_AMOUNT) or schema.key_measure
        quantity = role_column(ctx, ROLE_QUANTITY, amount)
        discount = role_column(ctx, ROLE_DISCOUNT, amount)

        # 스텝 공용 표 대신 전용 조회 — 금액이 항목으로 나눌 수 없는 값이면 나눌 수 있는 값으로 바뀐다.
        frames = get_frames(ctx, [c for c in (amount, quantity, discount) if c], params)
        actual_df, compare_df = frames["actual"], frames["compare"]
        amount = frames["used"][amount]
        quantity = frames["used"][quantity] if quantity else None
        discount = frames["used"][discount] if discount else None

        # 검산 기준은 분해에 실제로 쓴 금액 자신의 전체 증감이다. 총평의 핵심 측정값과 다를 수 있다
        # (나눌 수 없어 다른 값으로 바뀐 경우) — 그때는 해설에 밝힌다(frames["notes"]).
        total = float(actual_df[amount].sum() - compare_df[amount].sum())
        lifecycle_available = get_item_lifecycle(ctx) is not None
        measure_cols = [c for c in (amount, quantity, discount) if c]

        # 품목(item) 역할이 없으면 상위 분류(item_group, 예: 브랜드)로 대신한다 — 물량/단가
        # 분해가 "품목 없음"만으로 통째로 안 되는 것을 막는다(2026-08-26).
        item_dim = schema.column(ROLE_ITEM) or schema.column(ROLE_ITEM_GROUP)

        views: dict[str, list[dict]] = {}
        for dim, split in ((item_dim, True), (schema.column(ROLE_PARTY), False)):
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
            "notes": frames["notes"],
        }

    return ctx.get_or_compute(_BRIDGE_CALC, _compute)


# ── 손익 계단 (2026-07-21, 시나리오 5 "손익 분석"의 Revenue~EBIT 5스텝 공용) ─────
def additive_cols(ctx, cols: list[str], params: dict | None) -> list[str]:
    """같은 의미의 측정값이 여럿일 때 더해서 쓸 컬럼. 한 컬럼이 나머지의 합과 같으면(합계 열) 그 하나만,
    없으면 전부(구성 항목들)다. 같은 파일의 컬럼끼리만 비교한다 — 값(분석기간 합계)으로 판단한다."""
    if len(cols) <= 1:
        return cols
    meta = load_meta(ctx.meta)
    first_src = source_of(ctx.meta, meta, cols[0])
    cols = [c for c in cols if source_of(ctx.meta, meta, c) == first_src]
    if len(cols) <= 1:
        return cols
    frames = get_dim_frames(ctx, cols, None, params)
    sums = {c: float(frames["actual"][frames["used"][c]].iloc[0]) for c in cols}
    for c in cols:
        others = sum(v for k, v in sums.items() if k != c)
        if others and abs(sums[c] - others) <= max(abs(sums[c]) * 0.005, 0.01):
            return [c]
    return cols


def pnl_role_cols(ctx, params: dict | None = None) -> dict[str, list[str]]:
    """손익에 쓸 금액·원가·판관비 컬럼 목록 {"amount": [...], "cost": [...], "opex": [...]}.

    스텝 범위 메타가 아니라 전체 메타에서 찾는다(원가 파일은 매출 파일과 따로 있을 수 있다). 합산해도
    의미 있는 측정값(Field_Type=Measure)만 쓰고, 금액은 대표 하나, 원가·판관비는 합계 열 하나 또는 구성
    항목 전부다(_additive_cols).
    """
    def _compute() -> dict[str, list[str]]:
        schema = get_full_schema(ctx)
        out: dict[str, list[str]] = {}
        for key, role in (("amount", ROLE_AMOUNT), ("cost", ROLE_COST), ("opex", ROLE_OPEX)):
            cols = [c for c in schema.columns(role) if c in schema.measures]
            if key == "amount":
                continue
            out[key] = additive_cols(ctx, cols, params)
        # 금액은 원가와 같은 파일의 것을 우선한다(같은 표에서 손익이 계산돼야 단계가 맞는다).
        meta = load_meta(ctx.meta)
        anchor = source_of(ctx.meta, meta, out["cost"][0]) if out.get("cost") else None
        amounts = [c for c in schema.columns(ROLE_AMOUNT) if c in schema.measures]
        same = [c for c in amounts if anchor and source_of(ctx.meta, meta, c) == anchor]
        out["amount"] = (same or amounts)[:1] or [role_column(ctx, ROLE_AMOUNT) or schema.key_measure]
        return out

    return ctx.get_or_compute("pnl_role_cols", _compute)


def get_pnl_ladder(ctx, params: dict | None = None) -> dict:
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
        roles = pnl_role_cols(ctx, params)
        amount_cols, cost_cols, opex_cols = roles["amount"], roles["cost"], roles["opex"]

        if not cost_cols:
            raise ValueError("매출원가(cost 역할) 컬럼이 없어 손익 분석을 할 수 없습니다. "
                             "데이터소스 정의에 cost 역할을 선언하세요.")

        # 차원 없이 합계만 필요하다 — 컬럼이 든 파일마다 따로 요청한다(get_dim_frames, 합계 한 줄).
        frames = get_dim_frames(ctx, [*amount_cols, *cost_cols, *opex_cols], None, params)
        actual_df, compare_df = frames["actual"], frames["compare"]

        def _sum(df: pd.DataFrame, cols: list[str]) -> float:
            return float(sum(df[frames["used"][c]].iloc[0] for c in cols if frames["used"][c] in df.columns))

        rev_a, rev_c = _sum(actual_df, amount_cols), _sum(compare_df, amount_cols)
        cogs_a, cogs_c = _sum(actual_df, cost_cols), _sum(compare_df, cost_cols)
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
        has_opex = bool(opex_cols)
        if has_opex:
            opex_a, opex_c = _sum(actual_df, opex_cols), _sum(compare_df, opex_cols)
            ebit_a, ebit_c = gm_a - opex_a, gm_c - opex_c
            steps["판매관리비"] = _step("판매관리비", opex_c, opex_a)
            steps["영업이익"] = _step("영업이익", ebit_c, ebit_a)

        return {"steps": steps, "has_opex": has_opex}

    return ctx.get_or_compute(_PNL_LADDER, _compute)
