"""보고서작성방안.md §2·§4·§5 DataSet 빌더 (엔진 모듈이 개별 호출).

흐름:
  1. build_actual_compare_datasets() — DB에서 당기/비교기 집계 DataFrame 취득
  2. build_history_dataset()         — 기간별 이력 패널(신규/이탈 생애주기·추이용)
  3. build_by_item_dataset()         — §4 차원×항목별 증감 + 파레토 플래그
  4. build_by_item_summary_dataset() — §5 차원별 통계(Impact, Z, HHI, Shapley, DVI)

기간 단위(grain, 2026-07-24 3단계 일반화): "month"(기본, 하위호환) / "quarter" / "year" / "week".
기간 식별자 형식: month="YYYY-MM", quarter="YYYY-Q#", year="YYYY", week="YYYY-Www"(ISO 주차).

비교 기간(compare_type — 이름은 하위호환으로 그대로 두고 grain에 따라 뜻을 일반화):
  MoM(기본) → 전 기간(같은 grain으로 1칸 전). 월 그레인에서는 기존과 동일(전월)
  YoY       → 전년 동기(그레인별 연간 주기만큼 이동)
  QoQ       → 전분기(3개월 전). 월 그레인 전용 의미를 그대로 유지한다
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import d2insight.config as config
from d2insight.engine.pipeline import db_meta
from d2insight.engine.pipeline.shapley import shapley_exact, _value_fn_factory


# ── 상수 ─────────────────────────────────────────────────────────────────────
# 차원 목록·측정값 이름은 더 이상 코드/정적 파일에 고정하지 않는다(2026-08-14) — 등록된
# 마스터데이터(datas/datacols/data_chatmetas)에서 source_id(datauid)별로 그때그때 구성한다
# (d2insight.engine.pipeline.db_meta 참조). 아래 두 상수는 source_id가 없는 옛 호출부를 위한
# 최후의 fallback으로만 남겨둔다 — 정상 경로(엔진)는 항상 source_id를 넘긴다.
DIMENSION_COLS: list[str] = []
KEY_MEASURE = None

PARETO_THRESHOLD: float = config.PARETO_THRESHOLD          # 0.80
ANOMALY_SIGMA:    float = getattr(config, "ANOMALY_SIGMA", 3.0)


def _resolve_sources(source_id: str | None) -> tuple[list[dict], "pd.DataFrame"]:
    if not source_id:
        raise db_meta.DbMetaError(
            "source_id가 지정되지 않았습니다 — DB 모드는 어느 등록된 마스터데이터를 쓸지 "
            "호출부가 프로젝트 기준으로 미리 정해 넘겨야 합니다."
        )
    sources = [db_meta.fetch_registered_data(uid) for uid in source_id.split("+")]
    meta = db_meta.build_meta_columns(sources)
    return sources, meta


# ── DB Engine ─────────────────────────────────────────────────────────────────

def _build_engine() -> Engine:
    # d2chat과 기존(비-엔진) d2insight/data_source/azure_sql.py가 이미 쓰는 것과 같은 경로다:
    # Supabase에 프로젝트/테넌트별로 등록된 커넥터(data_chatmetas → datas → connectors)에서
    # 연결 URL을 가져온다. .env의 고정 DB_SERVER 등을 직접 읽지 않는다 — 그건 스냅샷(단독 앱)
    # 전용이던 방식이고, 이 프로젝트는 테넌트마다 다른 DB를 등록해 쓰는 구조라 이쪽이 맞다.
    from d2shared import meta_loader
    url = meta_loader.get_connection_url()
    if not url:
        raise RuntimeError(
            "Supabase에서 DB 연결 URL을 가져오지 못했습니다 — "
            "connectors 테이블에 이 프로젝트용 DB가 등록되어 있는지 확인하세요."
        )
    return create_engine(url, pool_pre_ping=True)


# ── 기간 유틸 (grain 일반화, 2026-07-24) ────────────────────────────────────
# 그레인마다 "한 칸"의 뜻이 달라 하나의 산식으로 못 묶는다 — 월/분기/연은 정수 나눗셈,
# 주는 ISO 주차 기준 실제 날짜 이동으로 계산한다.

_PERIODS_PER_YEAR: dict[str, int] = {"month": 12, "quarter": 4, "week": 52, "year": 1}
_UNITS_PER_YEAR: dict[str, int] = {"month": 12, "quarter": 4, "year": 1}   # week는 날짜 기반이라 제외


def _parse_period_id(grain: str, period_id: str) -> tuple[int, int]:
    """기간 식별자 → (연, 그레인 내부 번호). year는 (연, 1) 고정."""
    if grain == "month":
        y, m = map(int, period_id.split("-"))
        return y, m
    if grain == "quarter":
        y, q = period_id.split("-Q")
        return int(y), int(q)
    if grain == "week":
        y, w = period_id.split("-W")
        return int(y), int(w)
    if grain == "year":
        return int(period_id), 1
    raise ValueError(f"알 수 없는 grain: '{grain}' (month/quarter/year/week만 지원)")


def _format_period_id(grain: str, year: int, unit: int) -> str:
    if grain == "month":
        return f"{year:04d}-{unit:02d}"
    if grain == "quarter":
        return f"{year:04d}-Q{unit}"
    if grain == "week":
        return f"{year:04d}-W{unit:02d}"
    if grain == "year":
        return f"{year:04d}"
    raise ValueError(f"알 수 없는 grain: '{grain}' (month/quarter/year/week만 지원)")


def shift_period(grain: str, period_id: str, n: int) -> str:
    """같은 grain 안에서 n칸 이동한 기간 식별자로 변환한다."""
    if grain == "week":
        y, w = _parse_period_id(grain, period_id)
        start = date.fromisocalendar(y, w, 1)
        shifted = start + timedelta(weeks=n)
        iso = shifted.isocalendar()
        return _format_period_id(grain, iso[0], iso[1])

    units = _UNITS_PER_YEAR[grain]
    y, u = _parse_period_id(grain, period_id)
    total = y * units + (u - 1) + n
    return _format_period_id(grain, total // units, (total % units) + 1)


def period_bounds(grain: str, period_id: str) -> tuple[date, date]:
    """기간 식별자 → [시작, 끝) 날짜 범위(반열린 구간)."""
    if grain == "month":
        y, m = _parse_period_id(grain, period_id)
        ey, em = _parse_period_id(grain, shift_period(grain, period_id, 1))
        return date(y, m, 1), date(ey, em, 1)
    if grain == "quarter":
        y, q = _parse_period_id(grain, period_id)
        ey, eq = _parse_period_id(grain, shift_period(grain, period_id, 1))
        return date(y, (q - 1) * 3 + 1, 1), date(ey, (eq - 1) * 3 + 1, 1)
    if grain == "year":
        y, _u = _parse_period_id(grain, period_id)
        return date(y, 1, 1), date(y + 1, 1, 1)
    if grain == "week":
        y, w = _parse_period_id(grain, period_id)
        start = date.fromisocalendar(y, w, 1)
        return start, start + timedelta(days=7)
    raise ValueError(f"알 수 없는 grain: '{grain}' (month/quarter/year/week만 지원)")


def compare_shift(grain: str, compare_type: str) -> int:
    """compare_type → 같은 grain 안에서 몇 칸 이동인지.

    MoM/YoY/QoQ 이름은 하위호환으로 그대로 둔다(period_dataset 파라미터·config.COMPARE_TYPE·
    카탈로그 UI 선택지가 이미 이 세 값을 전제) — grain에 따라 뜻만 일반화한다.

    대소문자를 가리지 않는다 — LLM이 사용자 문장에서 뽑아낸 값이 "yoy"처럼 표기가 다르게
    나올 수 있는데, 대소문자로만 비교하면 매치가 안 돼 조용히 기본(전 기간)으로 빠진다
    (2026-07-24 3단계 검증 중 실제로 재현: year grain에선 우연히 결과가 같아 안 드러났지만
    month/quarter/week grain에선 비교 기간이 틀어진다).
    """
    normalized = (compare_type or "").strip().lower()
    if grain == "month" and normalized == "qoq":
        return -3
    if normalized == "yoy":
        return -_PERIODS_PER_YEAR.get(grain, 1)
    return -1                           # MoM(기본) = 전 기간


def _actual_range(target_period: str, grain: str = "month") -> tuple[date, date]:
    return period_bounds(grain, target_period)


def _compare_range(target_period: str, compare_type: str, grain: str = "month") -> tuple[date, date]:
    compare_id = shift_period(grain, target_period, compare_shift(grain, compare_type))
    return period_bounds(grain, compare_id)


# ── §2: Actual + Compare DataFrames ─────────────────────────────────────────

def build_actual_compare_datasets(
    target_period: str,
    compare_type: str = "MoM",
    grain: str = "month",
    engine: Engine | None = None,
    source_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """당기(Actual) + 비교기(Compare) 집계 DataFrame 반환. grain: month(기본)/quarter/year/week.

    source_id: 등록된 마스터데이터의 datauid("+"로 여러 개 조인). 어느 소스를 쓸지는 이미
    호출부(엔진 entry.py)가 프로젝트 기준으로 정해 ctx.meta를 통해 여기까지 넘어온다.
    """
    if engine is None:
        engine = _build_engine()
    sources, meta = _resolve_sources(source_id)
    sql, _period_colname = db_meta.build_agg_sql(sources, meta, grain)

    a_start, a_end = _actual_range(target_period, grain)
    c_start, c_end = _compare_range(target_period, compare_type, grain)

    with engine.connect() as conn:
        actual_df  = pd.read_sql_query(
            text(sql), conn,
            params={"start_date": a_start, "end_date": a_end},
        )
        compare_df = pd.read_sql_query(
            text(sql), conn,
            params={"start_date": c_start, "end_date": c_end},
        )

    print(f"[dataset_builder] Actual({target_period}, {grain}): {len(actual_df):,}행  "
          f"Compare({compare_type}): {len(compare_df):,}행")
    return actual_df, compare_df


# ── 스텝 단위 쿼리 (2026-08-24) ──────────────────────────────────────────────

def query_step_dataset(
    target_period: str,
    compare_type: str = "MoM",
    grain: str = "month",
    source_id: str | None = None,
    dimensions: list[str] | None = None,
    measures: list[str] | None = None,
    log_ctx: dict | None = None,
    existing_sql: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """스텝에 필요한 컬럼만 담은 이번 기간/비교 기간 데이터를 LLM이 쓴 SQL로 가져온다.

    SQL은 필터링(날짜 범위, 필요한 컬럼)만 하고 집계는 하지 않는다 — 합계 등은 돌려받은
    데이터프레임에서 각 모듈이 pandas groupby로 직접 계산한다(예: 모듈1은 dimension='지역'으로,
    모듈2는 dimension='고객'으로 각자 groupby). 이러면 같은 데이터셋을 여러 모듈이 서로 다른
    차원으로 나눠 볼 수 있다. FROM/JOIN은 LLM이 직접 쓴다(reference를 힌트로 제공).

    existing_sql: 정기 보고서 재실행 등 이미 확정된 SQL이 있으면 LLM 재호출 없이 그대로
    쓴다(날짜만 새로 바인딩) — 매번 같은 결과가 보장된다.

    반환: (actual_df, compare_df, generated_sql) — generated_sql은 :start_date/:end_date
    바인드 파라미터를 쓰는 재사용 가능한 SQL 텍스트다(정기 보고서 캐싱에 그대로 쓸 수 있음).
    """
    from d2shared import meta_loader as shared_meta_loader
    from d2shared.mcp_server import MCPServer
    from d2shared.config import DEFAULT_LLM_MODEL

    sources, meta = _resolve_sources(source_id)

    dim_rows = meta[(meta["Field_Type"] == "Dim") & (meta["Semantic_Type"] != "period")]
    measure_rows = meta[meta["Field_Type"] == "Measure"]
    avail_dims = set(dim_rows["Physical_Name"])
    avail_measures = set(measure_rows["Physical_Name"])

    use_dims = [d for d in (dimensions or []) if d in avail_dims]
    use_measures = [m for m in (measures or []) if m in avail_measures] or list(avail_measures)
    if not use_measures:
        raise db_meta.DbMetaError("등록된 측정값(금액/수량 등) 컬럼이 없어 집계할 수 없습니다.")

    if existing_sql:
        a_start, a_end = _actual_range(target_period, grain)
        c_start, c_end = _compare_range(target_period, compare_type, grain)
        server = MCPServer(db_connection=shared_meta_loader.get_connection_url())
        actual_df = server._execute_query(existing_sql, params={"start_date": a_start, "end_date": a_end})
        compare_df = server._execute_query(existing_sql, params={"start_date": c_start, "end_date": c_end})
        keep = [c for c in (use_dims + use_measures) if c in actual_df.columns]
        if keep:
            actual_df = actual_df[keep]
            compare_df = compare_df[[c for c in keep if c in compare_df.columns]]
        print(f"[dataset_builder] 스텝 쿼리(캐시된 SQL 재사용, {target_period}): "
              f"실적 {len(actual_df):,}행 / 비교 {len(compare_df):,}행")
        return actual_df, compare_df, existing_sql

    # d2chat/ReportAgent의 query_tool.py와 같은 shape — 소스별 컬럼 목록 + reference(조인 힌트).
    table_metadata = {
        src["physical_name"]: {
            "description": f'{src["schema"]}.{src["physical_name"]}',
            "reference": src.get("reference"),
            "default_time_column": src.get("default_time_column"),
            "columns": {
                row["Physical_Name"]: {"logical_name": row["Logical_Name"], "data_type": row["Data_Type"]}
                for _, row in meta[meta["_source_physical"] == src["physical_name"]].iterrows()
            },
        }
        for src in sources
    }
    for _src in sources:  # jeff
        print(f"[DEBUG-dataset_builder] source={_src['physical_name']!r} "  # jeff
              f"default_time_column={_src.get('default_time_column')!r}")  # jeff

    dims_text = ", ".join(use_dims) if use_dims else "(없음)"
    question = (
        f"다음 컬럼을 포함해 조회하세요.\n차원 컬럼: {dims_text}\n측정값 컬럼: {', '.join(use_measures)}\n"
        "집계는 하지 마세요 — 조회 결과는 이후 pandas가 직접 집계합니다.\n"
        "날짜 기간이 필요하면 반드시 기준 날짜 컬럼을 이용해 WHERE 절로 기간을 필터링하세요 — "
        "필터링 없이 전체 데이터를 가져오는 것은 허용되지 않습니다."
    )
    extra_rules = (
        "- 집계 함수(SUM/AVG/COUNT 등)나 GROUP BY를 쓰지 마세요. 집계는 이 결과를 받는 쪽이 "
        "pandas로 직접 합니다.\n"
        "- 날짜 조건은 리터럴 날짜값이 아니라 바인드 파라미터로 작성하세요: "
        "기준 날짜 컬럼 >= :start_date AND 기준 날짜 컬럼 < :end_date\n"
        "- SELECT에는 위에 명시된 차원·측정값 컬럼만 포함하세요(다른 컬럼 추가 금지). 특히 "
        "'매출액_한글'처럼 숫자를 조/억/만원 등 한글 단위 문자열로 변환한 파생 컬럼을 "
        "만들지 마세요 — 통화 단위조차 알 수 없는 원본 숫자이므로 이런 변환 자체가 "
        "부정확합니다. 원본 숫자 컬럼만 그대로 반환하세요.\n"
        "- SELECT 컬럼명은 위에 명시된 컬럼명과 정확히 똑같이 쓰세요(별칭을 바꾸지 마세요) — "
        "호출부가 이 컬럼명을 그대로 참조합니다."
    )

    url = shared_meta_loader.get_connection_url()
    if not url:
        raise RuntimeError("Supabase에서 DB 연결 URL을 가져오지 못했습니다.")
    server = MCPServer(db_connection=url)

    MAX_RETRIES = 2    # jeff 20260826 개발에서 5회 반복하니 시간이 너무 지체되어 2회로 수정함 --> 운용에서는 5회로 수정하기
    sql = None
    for attempt in range(1, MAX_RETRIES + 1):
        candidate_sql = server.generate_sql_query(
            question=question, model=DEFAULT_LLM_MODEL, table_metadata=table_metadata,
            extra_rules=extra_rules, log_ctx=log_ctx,
        )
        candidate_sql = server._clean_sql(candidate_sql)

        if ':start_date' in candidate_sql and ':end_date' in candidate_sql:
            sql = candidate_sql
            break

        print(f"[dataset_builder] SQL 생성 재시도 {attempt}/{MAX_RETRIES} — "
              f"날짜 바인드 파라미터(:start_date/:end_date) 누락, 재생성합니다.")

    if sql is None:
        raise RuntimeError(
            f"LLM이 {MAX_RETRIES}회 시도에도 날짜 바인드 파라미터(:start_date, :end_date)가 "
            "포함된 SQL을 생성하지 못했습니다. table_metadata의 default_time_column 설정이나 "
            "extra_rules를 점검해주세요."
        )

    a_start, a_end = _actual_range(target_period, grain)
    c_start, c_end = _compare_range(target_period, compare_type, grain)
    actual_df = server._execute_query(sql, params={"start_date": a_start, "end_date": a_end})
    compare_df = server._execute_query(sql, params={"start_date": c_start, "end_date": c_end})

    # 프롬프트로 금지해도 LLM이 파생 컬럼(예: '매출액_한글')을 만들어 끼워넣을 수 있으므로,
    # 요청한 차원·측정값 컬럼만 남기고 나머지는 코드에서 한 번 더 걸러낸다.
    keep_cols = [c for c in (use_dims + use_measures) if c in actual_df.columns]
    if keep_cols:
        actual_df = actual_df[keep_cols]
        compare_df = compare_df[[c for c in keep_cols if c in compare_df.columns]]

    print(f"[dataset_builder] 스텝 쿼리({target_period}, dims={use_dims or '-'}): "
          f"실적 {len(actual_df):,}행 / 비교 {len(compare_df):,}행")
    return actual_df, compare_df, sql


# ── 기간별 이력 패널 (신규/이탈 생애주기 판정·추이 분석용) ────────────────────

def build_history_dataset(
    target_period: str,
    months_back: int | None = None,
    grain: str = "month",
    engine: Engine | None = None,
    source_id: str | None = None,
) -> pd.DataFrame:
    """분석기간 포함 최근 N개 기간의 **그레인별 패널**. 컬럼 구성은 actual/compare와 동일 + 기간 컬럼.

    months_back: 이름은 하위호환으로 그대로 두되(period_dataset 파라미터·config.HISTORY_MONTHS가
    이미 이 이름을 전제) 이제 "그레인 무관 이전 N개 기간"을 뜻한다.

    쓰임:
      - 신규/이탈 생애주기 판정(§4 개정) — 항목이 과거 몇 기간이나 활동했는지
      - 추이(trend)·누계(cumulative)·ABC-XYZ 등급(abc_classification) 모듈
    """
    if engine is None:
        engine = _build_engine()
    months_back = months_back or getattr(config, "HISTORY_MONTHS", 7)
    sources, meta = _resolve_sources(source_id)
    sql, _period_colname = db_meta.build_agg_sql(sources, meta, grain)

    _, end = period_bounds(grain, target_period)                          # 분석기간 종료(배타적)
    start_id = shift_period(grain, target_period, -(months_back - 1))
    start, _ = period_bounds(grain, start_id)

    with engine.connect() as conn:
        df = pd.read_sql_query(
            text(sql), conn,
            params={"start_date": start, "end_date": end},
        )

    print(f"[dataset_builder] History({start} ~ {end}, {months_back}{grain}): {len(df):,}행")
    return df


# ── §4: By_Item_DataSet ───────────────────────────────────────────────────────

def _pareto_flag(values: pd.Series, threshold: float) -> np.ndarray:
    """상위 threshold 누적 비율에 도달하는 항목들에 1 표시 (내림차순 기준).

    파레토 80%: 누적합이 80%에 도달하기 전까지의 항목을 Is_Main = 1로 표시.
    경계 항목(80%를 처음 넘는 항목)도 포함한다.
    """
    total = values.sum()
    if total <= 0:
        return np.zeros(len(values), dtype=int)

    order    = np.argsort(values.values)[::-1]          # 내림차순 인덱스
    cumsum   = np.cumsum(values.values[order])
    prev_cum = np.concatenate([[0.0], cumsum[:-1]])      # 직전 누적합
    flag     = (prev_cum / total < threshold).astype(int)

    result = np.zeros(len(values), dtype=int)
    result[order] = flag
    return result


def build_by_item_dataset(
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    pareto_threshold: float = PARETO_THRESHOLD,
    measure: str | None = None,
    dimensions: list[str] | None = None,
) -> pd.DataFrame:
    """§4 By_Item_DataSet: 모든 차원 × 항목별 Key_Measure 증감 + 파레토 플래그.

    Contribution_Rate(§12-B 차원 내 기여도 분석용) = 항목 Variance / 전체 매출 증감액.
    전체 매출 증감액은 모든 차원·항목에 공통으로 적용되는 단일 분모(회사 전체 매출
    증감액 하나)이며, 차원별로 다시 계산하지 않는다.
    """
    parts: list[pd.DataFrame] = []
    measure = measure or KEY_MEASURE                # 호출자(엔진)는 스키마에서 얻어 넘긴다
    dimensions = dimensions or DIMENSION_COLS

    total_variance = (
        float(actual_df[measure].sum()) - float(compare_df[measure].sum())
        if measure in actual_df.columns and measure in compare_df.columns
        else 0.0
    )

    for dim in dimensions:
        if dim not in actual_df.columns:
            continue

        agg_a = actual_df.groupby(dim)[measure].sum().rename("Actual_Value")
        agg_c = (compare_df.groupby(dim)[measure].sum().rename("Comparison_Value")
                 if dim in compare_df.columns else pd.Series(dtype=float, name="Comparison_Value"))

        merged = (
            pd.concat([agg_a, agg_c], axis=1)
            .fillna(0.0)
            .reset_index()
            .rename(columns={dim: "Item_Name"})
        )

        merged["Variance"] = merged["Actual_Value"] - merged["Comparison_Value"]
        merged["Rate"] = merged.apply(
            lambda r: r["Variance"] / r["Comparison_Value"] if r["Comparison_Value"] else 0.0,
            axis=1,
        )
        merged["New_Lost_Flag"] = merged.apply(
            lambda r: "New"  if r["Comparison_Value"] == 0 and r["Actual_Value"] > 0
                 else "Lost" if r["Actual_Value"] == 0     and r["Comparison_Value"] > 0
                 else "",
            axis=1,
        )
        merged["Contribution_Rate"] = (
            merged["Variance"] / total_variance if total_variance else 0.0
        )

        merged["Is_Comparison_Main"] = _pareto_flag(merged["Comparison_Value"], pareto_threshold)
        merged["Is_Actual_Main"]     = _pareto_flag(merged["Actual_Value"],     pareto_threshold)
        merged["Is_Main"] = ((merged["Is_Comparison_Main"] == 1) | (merged["Is_Actual_Main"] == 1)).astype(int)

        merged.insert(0, "Dimension_Logical_Name", dim)
        merged.insert(1, "Measure_Logical_Name",   measure)

        parts.append(merged[[
            "Dimension_Logical_Name", "Measure_Logical_Name", "Item_Name",
            "Comparison_Value", "Actual_Value", "Variance", "Rate", "Contribution_Rate",
            "New_Lost_Flag", "Is_Comparison_Main", "Is_Actual_Main", "Is_Main",
        ]])

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ── §5: By_Item_Summary_DataSet ───────────────────────────────────────────────

def _shapley_for_dims(
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    dim_cols: list[str],
    measure: str | None = None,
) -> dict[str, float]:
    """기존 shapley_exact 재활용 — value fn은 Σ|Δ_g| 기준."""
    avail = [d for d in dim_cols if d in actual_df.columns and d in compare_df.columns]
    if not avail:
        return {d: 0.0 for d in dim_cols}

    value_fn = _value_fn_factory(actual_df, compare_df, measure or KEY_MEASURE)
    raw      = shapley_exact(value_fn, avail)

    total = sum(abs(v) for v in raw.values())
    share = {d: (v / total if total else 0.0) for d, v in raw.items()}

    # avail에 없는 차원은 0
    return {d: round(share.get(d, 0.0), 4) for d in dim_cols}


def build_by_item_summary_dataset(
    byitem_df: pd.DataFrame,
    actual_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    measure: str | None = None,
) -> pd.DataFrame:
    """§5 By_Item_Summary_DataSet: 차원별 통계 + Shapley + HHI + DVI."""
    if byitem_df.empty:
        return pd.DataFrame()

    measure       = measure or KEY_MEASURE
    dim_cols      = byitem_df["Dimension_Logical_Name"].unique().tolist()
    shapley_share = _shapley_for_dims(actual_df, compare_df, dim_cols, measure)

    rows = []
    for dim in dim_cols:
        # New 항목 제외
        sub = byitem_df[
            (byitem_df["Dimension_Logical_Name"] == dim)
            & (byitem_df["New_Lost_Flag"] != "New")
        ]
        if sub.empty:
            continue

        rates     = sub["Rate"].values.astype(float)
        variances = sub["Variance"].values.astype(float)

        n            = len(sub)
        rate_mean    = float(np.mean(rates))
        rate_median  = float(np.median(rates))
        sigma        = float(np.std(rates, ddof=1)) if n > 1 else 0.0
        impact_score = float(np.sum(np.abs(variances)))

        z_scores  = (rates - rate_mean) / sigma if sigma > 0 else np.zeros(n)
        avg_z     = float(np.mean(np.abs(z_scores)))

        # HHI = Σ (|Δi| / Impact_Score)²  — 임팩트 집중도
        hhi = float(np.sum((np.abs(variances) / impact_score) ** 2)) if impact_score > 0 else 0.0

        # DVI = Impact × HHI × Average_Z
        dvi = impact_score * hhi * avg_z

        rows.append({
            "Dimension_Logical_Name": dim,
            "Measure_Logical_Name":   measure,
            "Count":         n,
            "Rate_Mean":     round(rate_mean,   4),
            "Rate_Median":   round(rate_median, 4),
            "σ":             round(sigma,       4),
            "Impact_Score":  round(impact_score, 2),
            "Shapley_Value": shapley_share.get(dim, 0.0),
            "-3σ":           round(rate_mean - 3 * sigma, 4),
            "-2σ":           round(rate_mean - 2 * sigma, 4),
            "-1σ":           round(rate_mean - 1 * sigma, 4),
            "+1σ":           round(rate_mean + 1 * sigma, 4),
            "+2σ":           round(rate_mean + 2 * sigma, 4),
            "+3σ":           round(rate_mean + 3 * sigma, 4),
            "Average_Z":     round(avg_z, 4),
            "HHI":           round(hhi,   4),
            "DVI":           round(dvi,   2),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Shapley_Value", ascending=False).reset_index(drop=True)
    return df

