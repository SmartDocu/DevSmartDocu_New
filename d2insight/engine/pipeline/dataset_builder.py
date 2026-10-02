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

import re
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


def _run_sql(server, sql: str, params: dict, sources: list[dict]):
    """SQL 실행. DB가 이름을 못 찾으면 무엇을 고쳐야 하는지로 바꿔 알린다.

    ODBC 원문("Invalid object name 'dbo.xxx'")만 보여주면 담당자가 어디를 손봐야 할지
    알 수 없다. 등록된 테이블·뷰 이름이 실제 DB와 다른 것이 원인이다.
    """
    try:
        return server._execute_query(sql, params=params)
    except Exception as e:
        if "Invalid object name" not in str(e):
            raise
        names = ", ".join(f'{s["schema"]}.{s["physical_name"]}' for s in sources)
        raise db_meta.DbMetaError(
            f"등록된 테이블·뷰({names})를 DB에서 찾지 못했습니다. 마스터데이터 화면에서 "
            "이름이 실제 DB와 같은지 확인하고 메타 정보를 다시 저장한 뒤 요청해주세요."
        ) from e


def _resolve_sources(source_id: str | None) -> tuple[list[dict], "pd.DataFrame"]:
    if not source_id:
        raise db_meta.DbMetaError(
            "source_id가 지정되지 않았습니다 — DB 모드는 어느 등록된 마스터데이터를 쓸지 "
            "호출부가 프로젝트 기준으로 미리 정해 넘겨야 합니다."
        )
    sources = [db_meta.fetch_registered_data(uid) for uid in source_id.split("+")]
    # 이름이 없으면 SQL이 "FROM [dbo].[]"로 만들어져 실행 직전에야 알 수 있다. 여기서 막는다.
    nameless = [s["datanm"] for s in sources if not s["physical_name"]]
    if nameless:
        raise db_meta.DbMetaError(
            f"'{', '.join(nameless)}'의 테이블·뷰 이름이 등록되어 있지 않아 조회할 수 없습니다. "
            "마스터데이터 화면에서 조회 SQL의 FROM 절이 올바른지 확인하고 메타 정보를 다시 "
            "저장한 뒤 요청해주세요."
        )
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

_PERIODS_PER_YEAR: dict[str, int] = {"month": 12, "quarter": 4, "half": 2, "week": 52, "year": 1}
_UNITS_PER_YEAR: dict[str, int] = {"month": 12, "quarter": 4, "half": 2, "year": 1}   # week는 날짜 기반이라 제외


def _parse_period_id(grain: str, period_id: str) -> tuple[int, int]:
    """기간 식별자 → (연, 그레인 내부 번호). year는 (연, 1) 고정."""
    if grain == "month":
        y, m = map(int, period_id.split("-"))
        return y, m
    if grain == "quarter":
        y, q = period_id.split("-Q")
        return int(y), int(q)
    if grain == "half":
        y, h = period_id.split("-H")
        return int(y), int(h)
    if grain == "week":
        y, w = period_id.split("-W")
        return int(y), int(w)
    if grain == "year":
        return int(period_id), 1
    raise ValueError(f"알 수 없는 grain: '{grain}' (month/quarter/half/year/week만 지원)")


def _format_period_id(grain: str, year: int, unit: int) -> str:
    if grain == "month":
        return f"{year:04d}-{unit:02d}"
    if grain == "quarter":
        return f"{year:04d}-Q{unit}"
    if grain == "half":
        return f"{year:04d}-H{unit}"
    if grain == "week":
        return f"{year:04d}-W{unit:02d}"
    if grain == "year":
        return f"{year:04d}"
    raise ValueError(f"알 수 없는 grain: '{grain}' (month/quarter/half/year/week만 지원)")


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
    if grain == "half":
        y, h = _parse_period_id(grain, period_id)
        ey, eh = _parse_period_id(grain, shift_period(grain, period_id, 1))
        return date(y, (h - 1) * 6 + 1, 1), date(ey, (eh - 1) * 6 + 1, 1)
    if grain == "year":
        y, _u = _parse_period_id(grain, period_id)
        return date(y, 1, 1), date(y + 1, 1, 1)
    if grain == "week":
        y, w = _parse_period_id(grain, period_id)
        start = date.fromisocalendar(y, w, 1)
        return start, start + timedelta(days=7)
    raise ValueError(f"알 수 없는 grain: '{grain}' (month/quarter/half/year/week만 지원)")


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
    if normalized == "qoq":
        if grain == "month":
            return -3
        raise ValueError(f"QoQ 비교는 month grain에서만 지원합니다 (현재 grain: '{grain}')")
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

_ROW_CAP = 1_000_000


def _unlimit_rows(sql: str) -> str:
    """LLM이 붙인 작은 행 수 제한(TOP N / LIMIT N)을 큰 값으로 바꾼다.

    스텝 쿼리는 합계·순위를 구하려고 조건에 맞는 모든 행이 필요하다. LLM이 d2chat 관성으로
    TOP 100을 붙이면 100행만 합산되어 숫자가 조용히 틀린다(2026-09-29, 총평 수량이 100으로
    나온 사고). 이미 충분히 큰 제한은 그대로 둔다.
    """
    def _top(m: re.Match) -> str:
        return m.group(0) if int(m.group(1)) >= _ROW_CAP else f"TOP {_ROW_CAP}"

    def _limit(m: re.Match) -> str:
        return m.group(0) if int(m.group(1)) >= _ROW_CAP else f"LIMIT {_ROW_CAP}"

    # 뒤따르는 공백은 건드리지 않는다(TOP 100 컬럼명 → TOP 1000000 컬럼명). TOP n PERCENT는
    # 전체 행을 뜻하는 관용구라 그대로 둔다(1000000PERCENT로 깨지면 SQL 오류).
    sql = re.sub(r"\bTOP\s*\(\s*(\d+)\s*\)(?!\s*PERCENT\b)", _top, sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bTOP\s+(\d+)(?!\d)(?!\s*PERCENT\b)", _top, sql, flags=re.IGNORECASE)
    return re.sub(r"\bLIMIT\s+(\d+)", _limit, sql, flags=re.IGNORECASE)


def query_step_dataset(
    target_period: str,
    compare_type: str = "MoM",
    grain: str = "month",
    source_id: str | None = None,
    dimensions: list[str] | None = None,
    measures: list[str] | None = None,
    log_ctx: dict | None = None,
    existing_sql: str | None = None,
    natural_question: str | None = None,
    flexible: bool = False,
    date_range: tuple[date, date] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """스텝에 필요한 컬럼만 담은 이번 기간/비교 기간 데이터를 LLM이 쓴 SQL로 가져온다.

    SQL은 필터링(날짜 범위, 필요한 컬럼)만 하고 집계는 하지 않는다 — 합계 등은 돌려받은
    데이터프레임에서 각 모듈이 pandas groupby로 직접 계산한다(예: 모듈1은 dimension='지역'으로,
    모듈2는 dimension='고객'으로 각자 groupby). 이러면 같은 데이터셋을 여러 모듈이 서로 다른
    차원으로 나눠 볼 수 있다. FROM/JOIN은 LLM이 직접 쓴다(reference를 힌트로 제공).

    existing_sql: 정기 보고서 재실행 등 이미 확정된 SQL이 있으면 LLM 재호출 없이 그대로
    쓴다(날짜만 새로 바인딩) — 매번 같은 결과가 보장된다.

    date_range: (시작, 끝) 반열린 구간을 주면 여러 기간을 SQL 한 번으로 가져온다(이력 표용, 2026-09-30).
    이때 실적/비교 구분 없이 한 표만 조회하고, 반환은 (표, 빈 표, SQL)이다. 기간 컬럼도 남긴다.

    반환: (actual_df, compare_df, generated_sql) — generated_sql은 :start_date/:end_date
    바인드 파라미터를 쓰는 재사용 가능한 SQL 텍스트다(정기 보고서 캐싱에 그대로 쓸 수 있음).
    """
    from d2shared import meta_loader as shared_meta_loader
    from d2shared.mcp_server import MCPServer
    from d2shared.config import DEFAULT_LLM_MODEL

    sources, meta = _resolve_sources(source_id)

    from d2insight.engine.schema import COUNT_MEASURE

    dim_rows = meta[(meta["Field_Type"] == "Dim") & (meta["Semantic_Type"] != "period")]
    # 건수는 DB에 없는 가짜 컬럼이다 — SQL로 조회하면 안 된다(period_dataset이 만들어 준다).
    measure_rows = meta[(meta["Field_Type"] == "Measure")
                        & (meta["Physical_Name"] != COUNT_MEASURE)]
    avail_dims = set(dim_rows["Physical_Name"])
    avail_measures = set(measure_rows["Physical_Name"])
    avail_period = set(meta.loc[meta["Semantic_Type"] == "period", "Physical_Name"])

    use_dims =[d for d in (dimensions or []) if d in avail_dims]
    # 측정값이 없어도 조회한다 — 합칠 숫자가 없는 데이터(로그 등)는 행 자체가 측정값이고,
    # period_dataset이 건수 컬럼을 넣어준다(schema.COUNT_MEASURE).
    use_measures = [m for m in (measures or []) if m in avail_measures]
    if not use_dims and not use_measures:
        # 아무것도 지정하지 않은 스텝(자료 확인 등)은 등록된 컬럼 전부를 가져온다.
        # 등록 순서를 그대로 쓴다 — set으로 풀면 실행마다 순서가 달라져 같은 스텝이 매번
        # 다른 SQL을 만든다(정기 보고서가 어긋난다).
        use_dims = list(dim_rows["Physical_Name"])
        use_measures = list(measure_rows["Physical_Name"])
    if not use_dims and not use_measures:
        raise db_meta.DbMetaError("등록된 컬럼 중 조회할 수 있는 것이 없습니다.")

    if existing_sql:
        # 이미 저장된 SQL(정기보고서 등)에 예전에 붙은 TOP 100이 남아 있어도 풀어서 쓴다.
        existing_sql = _unlimit_rows(existing_sql)
        if date_range:
            server = MCPServer(db_connection=shared_meta_loader.get_connection_url())
            df = _run_sql(server, existing_sql, {"start_date": date_range[0], "end_date": date_range[1]}, sources)
            keep = [c for c in df.columns if c in avail_dims or c in avail_measures or c in avail_period]
            if keep:
                df = df[keep]
            print(f"[dataset_builder] 기간 범위 쿼리(캐시된 SQL 재사용, {date_range[0]}~{date_range[1]}): {len(df):,}행")
            return df, df.iloc[0:0], existing_sql
        a_start, a_end = _actual_range(target_period, grain)
        c_start, c_end = _compare_range(target_period, compare_type, grain)
        server = MCPServer(db_connection=shared_meta_loader.get_connection_url())
        actual_df = _run_sql(server, existing_sql, {"start_date": a_start, "end_date": a_end}, sources)
        compare_df = _run_sql(server, existing_sql, {"start_date": c_start, "end_date": c_end}, sources)
        if flexible:
            keep = [c for c in actual_df.columns if c in avail_dims or c in avail_measures]
        else:
            keep = [c for c in (use_dims + use_measures) if c in actual_df.columns]
        if keep:
            actual_df = actual_df[keep]
            compare_df = compare_df[[c for c in keep if c in compare_df.columns]]
        # print(f"[dataset_builder] 스텝 쿼리(캐시된 SQL 재사용, {target_period}): "  # jeff 로그 줄이기
        #       f"실적 {len(actual_df):,}행 / 비교 {len(compare_df):,}행")
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
    # for _src in sources:  # jeff
    #     print(f"[DEBUG-dataset_builder] source={_src['physical_name']!r} "  # jeff
    #           f"default_time_column={_src.get('default_time_column')!r}")  # jeff

    dims_text = ", ".join(use_dims) if use_dims else "(없음)"
    measures_text = ", ".join(use_measures) if use_measures else "(없음 — 행 자체를 셉니다)"
    if natural_question:
        # 체크리스트 문구("차원 컬럼: (없음)\n측정값 컬럼: ...")는 요청 테이블에 없는 컬럼(예:
        # 상세 테이블에 없는 날짜)을 헤더 테이블에서 JOIN해 와야 한다는 판단을 LLM이 놓치게
        # 만드는 경우가 있었다(2026-09-28, d2chat 자연어 질의와의 비교 테스트로 확인) — 호출자가
        # 자연스러운 문장을 준 경우 그대로 쓴다. SELECT 컬럼 제한/집계 금지는 extra_rules가 맡는다.
        question = natural_question
    else:
        question = (
            f"다음 컬럼을 포함해 조회하세요.\n차원 컬럼: {dims_text}\n측정값 컬럼: {measures_text}\n"
            "집계는 하지 마세요 — 조회 결과는 이후 pandas가 직접 집계합니다.\n"
            "날짜 기간이 필요하면 반드시 기준 날짜 컬럼을 이용해 WHERE 절로 기간을 필터링하세요 — "
            "필터링 없이 전체 데이터를 가져오는 것은 허용되지 않습니다."
        )
    extra_rules = (
        "- 집계 함수(SUM/AVG/COUNT 등)나 GROUP BY를 쓰지 마세요. 집계는 이 결과를 받는 쪽이 "
        "pandas로 직접 합니다.\n"
        "- 날짜 조건은 리터럴 날짜값이 아니라 바인드 파라미터로 작성하세요: "
        "기준 날짜 컬럼 >= :start_date AND 기준 날짜 컬럼 < :end_date\n"
        f"- SELECT에는 다음 차원·측정값 컬럼만 포함하세요(다른 컬럼 추가 금지) — 차원: {dims_text} / "
        f"측정값: {measures_text}. 특히 '매출액_한글'처럼 숫자를 조/억/만원 등 한글 단위 문자열로 "
        "변환한 파생 컬럼을 만들지 마세요 — 통화 단위조차 알 수 없는 원본 숫자이므로 이런 변환 "
        "자체가 부정확합니다. 원본 숫자 컬럼만 그대로 반환하세요.\n"
        "- SELECT 컬럼명은 위에 명시된 컬럼명과 정확히 똑같이 쓰세요(별칭을 바꾸지 마세요) — "
        "호출부가 이 컬럼명을 그대로 참조합니다. 이 컬럼들이 다른 테이블에 있으면 reference를 "
        "보고 JOIN하세요 — 지금 SELECT할 컬럼이 없는 테이블이라도, 그 테이블에만 있는 기준 "
        "날짜 컬럼으로 WHERE 필터링을 해야 한다면 그 테이블도 JOIN 대상입니다.\n"
        f"- 주어진 테이블 중 이번 조회에 **실제로 필요한 것만** 쓰세요. 한 쿼리에서 조인하는 "
        f"테이블은 최대 {db_meta.MAX_JOIN_TABLES}개입니다. 조인 정보(reference)가 없는 "
        "테이블끼리는 조인하지 마세요.\n"
        "- 행 수를 제한하지 마세요. TOP·LIMIT을 쓰지 말고 조건에 맞는 모든 행을 조회하세요."
    )

    if natural_question and flexible:
        # 차원이 측정값과 다른 테이블에 있는 조회 — 컬럼을 못박으면 LLM이 '1'쪽 금액을 그대로
        # 조인·합산해 부풀린다(2026-09-28 사고). 의미로 묻고, LLM이 나눌 수 있는 값을 고르게 한다.
        # d2chat에서 같은 질문을 자연어로 했을 때 LLM이 스스로 올바른 값을 골랐다(2026-09-28).
        extra_rules = (
            "- 날짜 조건은 리터럴 날짜값이 아니라 바인드 파라미터로 작성하세요: "
            "기준 날짜 컬럼 >= :start_date AND 기준 날짜 컬럼 < :end_date\n"
            "- 필요한 기준(차원)별로 GROUP BY 집계(SUM 등)해서 조회해도 됩니다.\n"
            "- 주문 단위처럼 '1'쪽 테이블에만 있는 금액을 '여러 줄'쪽 테이블의 기준(상품·분류 등)으로 "
            "나누려고 조인한 뒤 합산하면 그 금액이 줄 수만큼 복사되어 합계가 부풀려집니다 — 이렇게 "
            "하지 마세요. 그 기준으로 나눌 수 있는 같은 의미의 값(줄 단위 금액 등)이 있으면 그 값을 "
            "쓰고, 없으면 SELECT 'CANNOT_ANSWER' AS result 로 답하세요.\n"
            "- 결과 컬럼명은 차원은 원래 컬럼명 그대로, 값은 집계해도 그 값이 원래 있던 컬럼명을 "
            "별칭으로 쓰세요(예: SUM(d.LineTotal) AS LineTotal). 다른 이름으로 바꾸지 마세요.\n"
            "- 요청한 값 대신 다른 값으로 조회했다면, 결과 컬럼명은 반드시 조회한 그 값의 원래 컬럼명으로 "
            "쓰세요. 요청한 값의 이름을 붙이면 다른 값이 요청한 값인 것처럼 표시되어 틀린 보고서가 "
            "됩니다.\n"
            f"- 주어진 테이블 중 이번 조회에 **실제로 필요한 것만** 쓰세요. 한 쿼리에서 조인하는 "
            f"테이블은 최대 {db_meta.MAX_JOIN_TABLES}개입니다. 조인 정보(reference)가 없는 "
            "테이블끼리는 조인하지 마세요.\n"
            "- 행 수를 제한하지 마세요. TOP·LIMIT을 쓰지 말고 조건에 맞는 모든 행을 조회하세요."
        )

    url = shared_meta_loader.get_connection_url()
    if not url:
        raise RuntimeError("Supabase에서 DB 연결 URL을 가져오지 못했습니다.")
    server = MCPServer(db_connection=url)

    MAX_RETRIES = 2   # jeff 20260826 개발에서 5회 반복하니 시간이 너무 지체되어 2회로 수정함 --> 운용에서는 5회로 수정하기
    sql = None
    for attempt in range(1, MAX_RETRIES + 1):
        candidate_sql = server.generate_sql_query(
            question=question, model=DEFAULT_LLM_MODEL, table_metadata=table_metadata,
            extra_rules=extra_rules, log_ctx=log_ctx,
        )
        candidate_sql = _unlimit_rows(server._clean_sql(candidate_sql))

        if "CANNOT_ANSWER" in candidate_sql.upper():
            raise RuntimeError(
                "쿼리 생성기가 이 조합(차원과 값)으로는 답할 수 없다고 판단했습니다(CANNOT_ANSWER).")

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

    if date_range:
        df = _run_sql(server, sql, {"start_date": date_range[0], "end_date": date_range[1]}, sources)
        keep = [c for c in df.columns if c in avail_dims or c in avail_measures or c in avail_period]
        if keep:
            df = df[keep]
        print(f"[dataset_builder] 기간 범위 쿼리({date_range[0]}~{date_range[1]}, dims={use_dims or '-'}): {len(df):,}행")
        return df, df.iloc[0:0], sql

    a_start, a_end = _actual_range(target_period, grain)
    c_start, c_end = _compare_range(target_period, compare_type, grain)
    actual_df = _run_sql(server, sql, {"start_date": a_start, "end_date": a_end}, sources)
    compare_df = _run_sql(server, sql, {"start_date": c_start, "end_date": c_end}, sources)

    # 프롬프트로 금지해도 LLM이 파생 컬럼(예: '매출액_한글')을 만들어 끼워넣을 수 있으므로,
    # 요청한 차원·측정값 컬럼만 남기고 나머지는 코드에서 한 번 더 걸러낸다.
    if flexible:
        # LLM이 요청한 값 대신 같은 의미의 다른 측정값을 골랐을 수 있다 — 등록된 차원·측정값이면 남긴다.
        keep_cols = [c for c in actual_df.columns if c in avail_dims or c in avail_measures]
    else:
        keep_cols = [c for c in (use_dims + use_measures) if c in actual_df.columns]
    if keep_cols:
        actual_df = actual_df[keep_cols]
        compare_df = compare_df[[c for c in keep_cols if c in compare_df.columns]]

    # print(f"[dataset_builder] 스텝 쿼리({target_period}, dims={use_dims or '-'}): "  # jeff 로그 줄이기
    #       f"실적 {len(actual_df):,}행 / 비교 {len(compare_df):,}행")
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
            "Shapley_Share": shapley_share.get(dim, 0.0),
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
        df = df.sort_values("Shapley_Share", ascending=False).reset_index(drop=True)
    return df

