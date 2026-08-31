"""DB 모드 메타 조립 — 등록된 마스터데이터(datas/datacols/data_chatmetas)에서
엔진이 쓰는 meta_columns와 조회 SQL을 그 자리에서(요청마다) 조립한다.

정적 datasources/<id>.json 파일이 아니라, d2chat과 완전히 같은 소스(사용자가 화면에서
이미 등록해둔 datas/datacols/data_chatmetas)를 쓴다 — 새 정의 파일도, 새 등록 화면도
필요 없다(2026-08-14, 사용자 방침). data_chatmetas.json은 utilsPrj.data_json_utils.
master_data_json_create()가 만드는 그 구조 그대로다:
    {schema, physical_name, default_time_column, reference:{parent_table, join_column:[...]},
     columns: {querycolnm: {logical_name, data_type, aliases}}}

역할(semantic) 판정은 LLM을 쓰지 않는다 — data_type(currency/number→측정값, date→기간,
string→차원)과, 이미 사람이 등록해둔 logical_name/aliases의 키워드만으로 규칙 기반 판정한다.
"""
from __future__ import annotations

import json

import pandas as pd

_AMOUNT_HINTS = ("매출", "금액", "revenue", "amount", "총액", "판매액")
_QUANTITY_HINTS = ("수량", "qty", "quantity", "물량")
_DISCOUNT_HINTS = ("할인", "discount", "에누리")
_ITEM_GROUP_HINTS = ("카테고리", "분류", "category", "대분류", "중분류", "class")
_ITEM_HINTS = ("제품", "상품", "품목", "product", "item", "모델", "model")
_PARTY_HINTS = ("고객", "거래처", "공급", "customer", "party", "account", "협력사", "구매처")
_REGION_HINTS = ("지역", "국가", "권역", "대륙", "region", "territory", "country", "continent", "area")

_MEASURE_TYPES = ("currency", "number", "float", "int", "decimal", "money")
_DATE_TYPES = ("date", "datetime", "timestamp")
_ID_TYPES = ("identifier", "id", "uuid")


class DbMetaError(Exception):
    """등록된 마스터데이터에서 DB 모드 분석에 쓸 정보를 찾지 못한 경우."""


def _service_client():
    from backend.app.config import settings
    from utilsPrj.supabase_client import get_service_client
    return get_service_client(), settings.SUPABASE_SCHEMA


def _match_hint(text: str, hints: tuple[str, ...]) -> bool:
    t = (text or "").lower()
    return any(h.lower() in t for h in hints)


def _measure_role(colnm: str, logical: str, aliases: list[str]) -> str:
    probe = " ".join([colnm, logical or "", " ".join(aliases or [])])
    if _match_hint(probe, _AMOUNT_HINTS):
        return "amount"
    if _match_hint(probe, _QUANTITY_HINTS):
        return "quantity"
    if _match_hint(probe, _DISCOUNT_HINTS):
        return "discount"
    return ""


def _dimension_role(colnm: str, logical: str, aliases: list[str]) -> str:
    probe = " ".join([colnm, logical or "", " ".join(aliases or [])])
    if _match_hint(probe, _ITEM_GROUP_HINTS):
        return "item_group"
    if _match_hint(probe, _ITEM_HINTS):
        return "item"
    if _match_hint(probe, _PARTY_HINTS):
        return "party"
    if _match_hint(probe, _REGION_HINTS):
        return "region"
    return ""


def fetch_registered_data(datauid: str) -> dict:
    """datas + datacols + data_chatmetas(json) → 소스 하나에 대한 통합 dict."""
    client, schema = _service_client()

    data_rows = client.schema(schema).table("datas").select("*").eq("datauid", datauid).execute().data
    if not data_rows:
        raise DbMetaError(f"등록된 데이터를 찾을 수 없습니다 (datauid={datauid}).")
    data_row = data_rows[0]

    meta_rows = client.schema(schema).table("data_chatmetas").select("*").eq("datauid", datauid).execute().data
    if not meta_rows or not meta_rows[0].get("json"):
        raise DbMetaError(
            f"'{data_row.get('datanm') or datauid}'에 챗봇용 메타(data_chatmetas)가 등록되어 있지 않습니다. "
            "먼저 마스터데이터 화면에서 메타 정보를 저장해주세요."
        )
    meta_json = meta_rows[0]["json"]
    if isinstance(meta_json, str):
        # data_chatmetas.json 컬럼 타입에 따라 postgrest가 dict 대신 원문 문자열을 돌려줄 때가
        # 있다(jsonb가 아니라 text로 저장된 경우 등) — 그대로 문자열이면 여기서 파싱한다.
        meta_json = json.loads(meta_json)

    col_rows = (
        client.schema(schema).table("datacols")
        .select("querycolnm, dispcolnm, datatypecd, measureyn, orderno")
        .eq("datauid", datauid).eq("useyn", True).order("orderno")
        .execute().data or []
    )

    return {
        "datauid": datauid,
        "datanm": data_row.get("datanm") or datauid,
        "projectid": data_row.get("projectid"),
        "schema": meta_json.get("schema") or "",
        "physical_name": meta_json.get("physical_name") or "",
        "default_time_column": meta_json.get("default_time_column") or "",
        "reference": meta_json.get("reference"),
        "columns": col_rows,
        "columns_meta": meta_json.get("columns") or {},
    }


def list_db_candidates(project_id: int | None = None) -> list[dict]:
    """DB 기반 마스터데이터(datauid) 중, 챗봇용 메타까지 등록된 것만 반환.

    datasourcecd가 DB 계열('db')이고 data_chatmetas가 있는 것만 후보로 삼는다 —
    등록만 해두고 메타를 안 채운 것은 엔진이 역할을 알 수 없어 후보에서 제외한다.

    project_id로 거르지 않는다 — d2chat이 쓰는 d2shared.meta_loader.load()도 project_id
    없이 data_chatmetas 전체를 스키마 단위로 읽는다(2026-08-14 확인). 여기서만 project_id로
    좁히면 d2chat에서는 보이는 데이터가 d2insight에서는 "등록 안 됨"으로 잘못 나온다.
    project_id 파라미터는 향후 실제로 프로젝트별 필터링이 필요해지면 쓰려고 남겨둔다.
    """
    client, schema = _service_client()
    data_rows = (
        client.schema(schema).table("datas")
        .select("datauid, datanm, datasourcecd, projectid")
        .eq("datasourcecd", "db")
        .execute().data or []
    )
    if not data_rows:
        return []
    datauids = [r["datauid"] for r in data_rows]
    meta_rows = (
        client.schema(schema).table("data_chatmetas")
        .select("datauid").in_("datauid", datauids)
        .execute().data or []
    )
    have_meta = {m["datauid"] for m in meta_rows}
    return [fetch_registered_data(d["datauid"]) for d in data_rows if d["datauid"] in have_meta]


def resolve_source_cluster(project_id: int | None = None) -> list[dict]:
    """등록된 DB 후보들에서 실제로 함께 분석할 소스 묶음을 고른다.

    v1 — 정교한 시나리오 매칭 대신 단순 규칙:
      - reference로 서로 연결된 것이 있으면(예: 상세→헤더) 그 쌍을 우선 사용
      - 없으면 등록된 후보를 그대로(최대 2개) 사용
    """
    candidates = list_db_candidates(project_id)
    if not candidates:
        raise DbMetaError(
            "DB 기반 마스터데이터가 등록되어 있지 않습니다(datasourcecd='db' + "
            "챗봇용 메타 저장 완료 기준). 마스터데이터 화면에서 DB 조회를 등록하고 "
            "메타 정보를 저장해주세요."
        )

    by_physical = {c["physical_name"]: c for c in candidates if c["physical_name"]}
    for c in candidates:
        ref = c.get("reference") or {}
        parent_table = ref.get("parent_table")
        if parent_table and parent_table in by_physical:
            return [c, by_physical[parent_table]]  # [상세(자식), 헤더(부모)]

    return candidates[:2]


def build_meta_columns(sources: list[dict]) -> pd.DataFrame:
    """소스 묶음(1~2개) → 엔진 Schema가 쓰는 meta_columns DataFrame(§1)."""
    rows = []
    for src in sources:
        default_time_col = src.get("default_time_column") or ""
        for col in src["columns"]:
            colnm = col["querycolnm"]
            dtype = (col.get("datatypecd") or "").lower()
            if dtype in _ID_TYPES:
                continue  # SalesOrderID 등 키 컬럼은 분석 차원/측정값으로 쓰지 않는다
            colmeta = src["columns_meta"].get(colnm) or {}
            logical = colmeta.get("logical_name") or col.get("dispcolnm") or colnm
            aliases = colmeta.get("aliases") or []

            is_date = dtype in _DATE_TYPES and colnm == default_time_col
            if is_date:
                field_type, semantic = "Dim", "period"
            elif dtype in _MEASURE_TYPES or col.get("measureyn"):
                field_type = "Measure"
                semantic = _measure_role(colnm, logical, aliases)
            elif dtype in _DATE_TYPES:
                continue  # 기준 기간 컬럼이 아닌 다른 날짜 컬럼(예: 배송일)은 일단 제외
            else:
                field_type = "Dim"
                semantic = _dimension_role(colnm, logical, aliases)

            rows.append({
                "Physical_Name": colnm,
                "Logical_Name": logical,
                "Data_Type": dtype,
                "Field_Type": field_type,
                "Is_Key_Measure": semantic == "amount",
                "Is_Date_for_Analytic": is_date,
                "Semantic_Type": semantic,
                "_source_physical": src["physical_name"],
                "_source_schema": src["schema"],
            })

    if not rows:
        raise DbMetaError("등록된 컬럼 중 분석에 쓸 수 있는 컬럼이 없습니다.")
    return pd.DataFrame(rows)


def build_join_sql(sources: list[dict]) -> tuple[str, str]:
    """소스 묶음의 FROM/JOIN 절과, 기간 조건에 쓸 기준 alias.기간컬럼 을 만든다.

    반환: (from_sql, "alias.기간컬럼")
    """
    aliases = [chr(ord("a") + i) for i in range(len(sources))]
    parts = [f'[{sources[0]["schema"]}].[{sources[0]["physical_name"]}] AS {aliases[0]}']
    date_ref = None
    if sources[0]["default_time_column"]:
        date_ref = f'{aliases[0]}.[{sources[0]["default_time_column"]}]'

    for i in range(1, len(sources)):
        child, parent = sources[0], sources[i]  # sources[0]=자식(상세), sources[i]=부모(헤더) 가정
        ref = child.get("reference") or {}
        joins = ref.get("join_column") or []
        if not joins:
            raise DbMetaError(f"{child['physical_name']}과(와) {parent['physical_name']} 사이의 조인 정보가 없습니다.")
        on_clauses = [
            f'{aliases[0]}.[{j["child_column"]}] = {aliases[i]}.[{j["parent_column"]}]'
            for j in joins
        ]
        parts.append(
            f'INNER JOIN [{parent["schema"]}].[{parent["physical_name"]}] AS {aliases[i]} '
            f'ON {" AND ".join(on_clauses)}'
        )
        if not date_ref and parent["default_time_column"]:
            date_ref = f'{aliases[i]}.[{parent["default_time_column"]}]'

    if not date_ref:
        raise DbMetaError("분석 기준이 될 기간(날짜) 컬럼이 어느 소스에도 등록되어 있지 않습니다.")

    return " ".join(parts), date_ref


_GRAIN_SQL_EXPR: dict[str, str] = {
    "month":   "FORMAT({date}, 'yyyy-MM')",
    "quarter": "CONCAT(YEAR({date}), '-Q', DATEPART(QUARTER, {date}))",
    "year":    "FORMAT({date}, 'yyyy')",
    # ISO 주차. SQL Server에 ISO_WEEK 번호는 있지만 ISO 주차 연도를 직접 주는 함수는 없어
    # DATEPART(YEAR, ...)로 근사한다 — 연말·연초 경계의 극소수 주만 어긋날 수 있다.
    "week":    "CONCAT(YEAR({date}), '-W', "
               "RIGHT('0' + CAST(DATEPART(ISO_WEEK, {date}) AS VARCHAR), 2))",
}


def build_agg_sql(sources: list[dict], meta: pd.DataFrame, grain: str = "month") -> tuple[str, str]:
    """소스 묶음 + meta_columns → 기간×차원별 측정값 합계 집계 SQL.

    출력 컬럼명은 meta_columns의 Physical_Name(원본 DB 컬럼명) 그대로 alias한다 —
    Schema.column(role)이 Physical_Name을 돌려주므로, 쿼리 결과 DataFrame의 컬럼명과
    Schema가 가리키는 이름이 반드시 일치해야 한다.

    반환: (sql, period_colname) — period_colname은 WHERE 파라미터 바인딩과 무관하게
    결과 DataFrame에서 기간 축 컬럼을 찾을 때 쓴다.
    """
    if grain not in _GRAIN_SQL_EXPR:
        raise DbMetaError(f"알 수 없는 grain: '{grain}' (month/quarter/year/week만 지원)")
    from_sql, date_ref = build_join_sql(sources)
    period_expr = _GRAIN_SQL_EXPR[grain].format(date=date_ref)

    period_rows = meta.loc[meta["Semantic_Type"] == "period", "Physical_Name"]
    period_colname = str(period_rows.iloc[0]) if len(period_rows) else "기간"

    dim_rows = meta[(meta["Field_Type"] == "Dim") & (meta["Semantic_Type"] != "period")]
    measure_rows = meta[meta["Field_Type"] == "Measure"]
    if not len(measure_rows):
        raise DbMetaError("등록된 측정값(금액/수량 등) 컬럼이 없어 집계할 수 없습니다.")

    select_parts = [f"{period_expr} AS [{period_colname}]"]
    group_parts = [period_expr]
    for _, row in dim_rows.iterrows():
        ref = col_alias(sources, row["_source_physical"], row["Physical_Name"])
        select_parts.append(f'{ref} AS [{row["Physical_Name"]}]')
        group_parts.append(ref)
    for _, row in measure_rows.iterrows():
        ref = col_alias(sources, row["_source_physical"], row["Physical_Name"])
        select_parts.append(f'SUM({ref}) AS [{row["Physical_Name"]}]')

    sql = (
        "SELECT\n    " + ",\n    ".join(select_parts) + "\n"
        f"FROM {from_sql}\n"
        f"WHERE {date_ref} >= :start_date AND {date_ref} < :end_date\n"
        "GROUP BY\n    " + ",\n    ".join(group_parts)
    )
    return sql, period_colname


def col_alias(sources: list[dict], physical_name: str, colnm: str) -> str:
    """meta_columns의 Physical_Name(원래 컬럼명)이 어느 소스(alias) 소속인지 찾아 `a.[col]` 형태로 돌려준다."""
    aliases = [chr(ord("a") + i) for i in range(len(sources))]
    for src, alias in zip(sources, aliases):
        if src["physical_name"] == physical_name:
            return f'{alias}.[{colnm}]'
    raise DbMetaError(f"컬럼 '{colnm}'의 소속 소스를 찾을 수 없습니다.")
