"""DB 모드 메타 조립 — 등록된 마스터데이터(datas/datacols/data_chatmetas)에서
엔진이 쓰는 meta_columns와 조회 SQL을 그 자리에서(요청마다) 조립한다.

정적 datasources/<id>.json 파일이 아니라, d2chat과 완전히 같은 소스(사용자가 화면에서
이미 등록해둔 datas/datacols/data_chatmetas)를 쓴다 — 새 정의 파일도, 새 등록 화면도
필요 없다(2026-08-14, 사용자 방침). data_chatmetas.json은 utilsPrj.data_json_utils.
master_data_json_create()가 만드는 그 구조 그대로다:
    {schema, physical_name, default_time_column, reference:{parent_table, join_column:[...]},
     columns: {querycolnm: {logical_name, data_type, aliases}}}

Field_Type(측정값/차원/기간)은 등록된 data_type과 default_time_column으로 정하고, 역할
(Semantic_Type)은 meta_roles.infer_roles()가 등록된 메타(표시명·별칭·값 목록·용도)를 읽어
판정한다 — 컬럼 이름을 키워드 목록에 맞춰보는 방식은 쓰지 않는다(2026-09-02).
"""
from __future__ import annotations

import json

import pandas as pd

from d2insight.engine.pipeline.meta_roles import infer_roles

_MEASURE_TYPES = ("currency", "number", "float", "int", "decimal", "money")
_DATE_TYPES = ("date", "datetime", "timestamp")
_ID_TYPES = ("identifier", "id", "uuid")

# 판정된 역할을 컬럼 종류(측정값/차원)에 맞는 것만 받아들인다.
_MEASURE_ROLES = {"amount", "quantity", "discount", "cost", "opex",
                  "inventory", "inbound", "outbound", "safety_stock"}
_DIM_ROLES = {"item", "item_group", "party", "region"}


class DbMetaError(Exception):
    """등록된 마스터데이터에서 DB 모드 분석에 쓸 정보를 찾지 못한 경우."""


def _service_client():
    from backend.app.config import settings
    from utilsPrj.supabase_client import get_service_client
    return get_service_client(), settings.SUPABASE_SCHEMA


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
        # 조회할 실제 테이블·뷰 이름. 표시명으로 대신 채우지 않는다 — 그러면 DB에 없는 이름으로
        # 쿼리가 만들어져 "Invalid object name"으로만 드러난다. 비면 그 사실을 그대로 알린다.
        "physical_name": meta_json.get("physical_name") or "",
        "logical_name": meta_json.get("logical_name") or "",
        "description": meta_json.get("description") or "",
        "purpose": meta_json.get("purpose") or [],
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


def _classify_report_tables(message: str, candidates: list[dict]) -> list[dict] | None:
    """보고서 요청에 필요한 소스를 **전부** 고른다.

    고르지 못하면 None(호출부가 기존 규칙으로 진행). 등록된 데이터 중 어느 것으로도 이 보고서를
    만들 수 없다고 판정되면 그 안내 문구로 DbMetaError를 올린다 — 엉뚱한 데이터로 만들지 않는다.
    """
    from d2shared.meta_loader import all_metadata
    from d2shared.table_classifier import classify_tables_for_report
    from d2insight import token_tracker
    from utilsPrj.ai_chain import get_llm_clients

    # 메타 키는 physical_name이 비어 있으면 logical_name으로 잡힌다(meta_loader와 같은 규칙) —
    # 물리명만 보면 그런 소스가 후보에서 통째로 빠진다.
    by_name: dict[str, dict] = {}
    for c in candidates:
        for name in (c.get("physical_name"), c.get("logical_name"), c.get("datanm")):
            if name:
                by_name.setdefault(name, c)

    available = {name: meta for name, meta in (all_metadata() or {}).items() if name in by_name}
    if len(available) <= 1:
        return None

    ctx = token_tracker.get_log_ctx() or {}
    clients = get_llm_clients(
        project_id=ctx.get("project_id"), tenant_id=ctx.get("tenant_id"),
        user_uid=ctx.get("creator"), account_uid=ctx.get("account_uid"), service_code="In",
    )
    result = classify_tables_for_report(message, clients["fast"], available, log_ctx=ctx)

    if not result.get("is_answerable"):
        raise DbMetaError(
            result.get("suggestion")
            or "등록된 데이터 중 이 보고서에 맞는 것을 찾지 못했습니다."
        )
    picked, seen = [], set()
    for name in result.get("tables") or []:
        src = by_name.get(name)
        if src and src["datauid"] not in seen:
            seen.add(src["datauid"])
            picked.append(src)
    if not picked:
        return None
    print(f"[db_meta] 데이터 선택: {[s['physical_name'] or s['datanm'] for s in picked]} "
          f"— {result.get('reasoning', '')}")
    return picked


def _with_reference_partners(sources: list[dict], candidates: list[dict]) -> list[dict]:
    """고른 소스마다 reference로 이어진 짝(부모/자식)을 함께 담는다."""
    by_physical = {c["physical_name"]: c for c in candidates if c["physical_name"]}
    out, seen = [], set()

    def _add(src: dict) -> None:
        if src["datauid"] not in seen:
            seen.add(src["datauid"])
            out.append(src)

    for src in sources:
        _add(src)
        parent_table = (src.get("reference") or {}).get("parent_table")
        if parent_table and parent_table in by_physical:
            _add(by_physical[parent_table])
        for c in candidates:
            if (c.get("reference") or {}).get("parent_table") == src["physical_name"]:
                _add(c)
    return out


def resolve_source_cluster(project_id: int | None = None, message: str | None = None) -> list[dict]:
    """이 보고서에 필요한 등록 소스를 전부 고른다.

    요청 문장이 있으면 그 문장으로 필요한 소스를 모두 고르고, 각각에 reference로 이어진 짝을
    함께 담는다. 문장이 없거나 고르지 못하면 예전 규칙대로 참조 쌍 → 등록 순서로 진행한다.

    스텝마다 이 목록 안에서 필요한 테이블만 골라 쿼리를 만든다(한 쿼리 조인은 3개까지).
    """
    candidates = list_db_candidates(project_id)
    if not candidates:
        raise DbMetaError(
            "DB 기반 마스터데이터가 등록되어 있지 않습니다(datasourcecd='db' + "
            "챗봇용 메타 저장 완료 기준). 마스터데이터 화면에서 DB 조회를 등록하고 "
            "메타 정보를 저장해주세요."
        )

    by_physical = {c["physical_name"]: c for c in candidates if c["physical_name"]}

    picked = None
    if message:
        try:
            picked = _classify_report_tables(message, candidates)
        except DbMetaError:
            raise
        except Exception as e:
            print(f"[db_meta] 데이터 선택 실패, 등록 순서로 진행: {type(e).__name__}: {e}")

    if picked:
        return _with_reference_partners(picked, candidates)

    for c in candidates:
        ref = c.get("reference") or {}
        parent_table = ref.get("parent_table")
        if parent_table and parent_table in by_physical:
            return [c, by_physical[parent_table]]  # [상세(자식), 헤더(부모)]

    return candidates[:2]


def build_meta_columns(sources: list[dict]) -> pd.DataFrame:
    """소스 묶음(1~2개) → 엔진 Schema가 쓰는 meta_columns DataFrame(§1)."""
    roles = infer_roles(sources)

    rows = []
    for src in sources:
        default_time_col = src.get("default_time_column") or ""
        table = src.get("physical_name") or src.get("datanm") or ""
        # 보고서 표에 찍을 이름 — datauid는 사람이 읽을 수 없다.
        label = src.get("logical_name") or src.get("datanm") or table
        for col in src["columns"]:
            colnm = col["querycolnm"]
            dtype = (col.get("datatypecd") or "").lower()
            if dtype in _ID_TYPES:
                continue  # SalesOrderID 등 키 컬럼은 분석 차원/측정값으로 쓰지 않는다
            colmeta = src["columns_meta"].get(colnm) or {}
            logical = colmeta.get("logical_name") or col.get("dispcolnm") or colnm
            role = roles.get((table, colnm), "")

            is_date = dtype in _DATE_TYPES and colnm == default_time_col
            if is_date:
                field_type, semantic = "Dim", "period"
            elif dtype in _MEASURE_TYPES or col.get("measureyn"):
                field_type = "Measure"
                semantic = role if role in _MEASURE_ROLES else ""
            elif dtype in _DATE_TYPES:
                continue  # 기준 기간 컬럼이 아닌 다른 날짜 컬럼(예: 배송일)은 일단 제외
            else:
                field_type = "Dim"
                semantic = role if role in _DIM_ROLES else ""

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
                "_source_label": label,
            })

    if not rows:
        raise DbMetaError("등록된 컬럼 중 분석에 쓸 수 있는 컬럼이 없습니다.")
    return count_measure_row(pd.DataFrame(rows))


def count_measure_row(meta: pd.DataFrame) -> pd.DataFrame:
    """합산할 측정값이 하나도 없으면 "건수"를 측정값으로 한 줄 넣는다.

    로그·검사이력처럼 행 하나가 사건 하나인 데이터에는 합칠 금액도 수량도 없다. 그런 데이터의
    측정값은 건수다. 계획 단계(schema.key_measure)부터 필요하므로 메타를 만들 때 넣는다.
    데이터에 실제 컬럼을 만들어 주는 것은 period_dataset의 몫이다.

    _source_physical은 비워 둔다 — DB에 실재하는 컬럼이 아니라 SQL로 참조하면 안 된다.
    """
    from d2insight.engine.schema import COUNT_MEASURE, COUNT_MEASURE_LABEL

    if "Field_Type" in meta and (meta["Field_Type"] == "Measure").any():
        return meta
    row = {
        "Physical_Name": COUNT_MEASURE, "Logical_Name": COUNT_MEASURE_LABEL,
        "Data_Type": "int", "Field_Type": "Measure", "Is_Key_Measure": True,
        "Is_Date_for_Analytic": False, "Semantic_Type": "",
        "_source_physical": "", "_source_schema": "", "_source_label": "",
    }
    return pd.concat([meta, pd.DataFrame([{c: row.get(c) for c in meta.columns} | row])],
                     ignore_index=True)


# 한 쿼리에서 조인할 수 있는 테이블 수. 보고서 전체가 쓰는 테이블은 이보다 많을 수 있고,
# 그중 한 쿼리가 함께 묶는 것만 이 수로 제한한다.
MAX_JOIN_TABLES = 3


def _join_clauses(base: dict, other: dict, base_alias: str, other_alias: str) -> list[str] | None:
    """두 소스 사이의 ON 절. 어느 쪽이 부모인지는 reference를 보고 정한다. 없으면 None."""
    ref = base.get("reference") or {}
    if ref.get("parent_table") == other["physical_name"] and ref.get("join_column"):
        return [f'{base_alias}.[{j["child_column"]}] = {other_alias}.[{j["parent_column"]}]'
                for j in ref["join_column"]]
    ref = other.get("reference") or {}
    if ref.get("parent_table") == base["physical_name"] and ref.get("join_column"):
        return [f'{other_alias}.[{j["child_column"]}] = {base_alias}.[{j["parent_column"]}]'
                for j in ref["join_column"]]
    return None


def build_join_sql(sources: list[dict]) -> tuple[str, str, list[dict]]:
    """소스 묶음의 FROM/JOIN 절 + 기간 조건에 쓸 기준 alias.기간컬럼 + 실제로 묶인 소스 목록.

    보고서가 쓰는 소스 전부가 하나로 조인되지는 않는다(판매와 생산은 이어지지 않는다).
    sources[0]을 기준으로 조인 정보가 선언된 것만 최대 MAX_JOIN_TABLES개까지 묶고, 나머지는
    이 쿼리에서 제외한다 — 그 소스가 필요한 스텝은 자기 쿼리를 따로 만든다.

    반환: (from_sql, "alias.기간컬럼", 묶인 소스 목록)
    """
    used = [sources[0]]
    aliases = {sources[0]["datauid"]: "a"}
    parts = [f'[{sources[0]["schema"]}].[{sources[0]["physical_name"]}] AS a']
    date_ref = None
    if sources[0]["default_time_column"]:
        date_ref = f'a.[{sources[0]["default_time_column"]}]'

    for src in sources[1:]:
        if len(used) >= MAX_JOIN_TABLES:
            break
        alias = chr(ord("a") + len(used))
        on_clauses = _join_clauses(sources[0], src, "a", alias)
        if not on_clauses:
            continue
        used.append(src)
        aliases[src["datauid"]] = alias
        parts.append(
            f'INNER JOIN [{src["schema"]}].[{src["physical_name"]}] AS {alias} '
            f'ON {" AND ".join(on_clauses)}'
        )
        if not date_ref and src["default_time_column"]:
            date_ref = f'{alias}.[{src["default_time_column"]}]'

    if not date_ref:
        raise DbMetaError("분석 기준이 될 기간(날짜) 컬럼이 어느 소스에도 등록되어 있지 않습니다.")

    return " ".join(parts), date_ref, used


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
    from_sql, date_ref, sources = build_join_sql(sources)
    period_expr = _GRAIN_SQL_EXPR[grain].format(date=date_ref)

    # 이 쿼리에 실제로 묶인 소스의 컬럼만 남긴다 — 조인되지 않은 소스의 컬럼은 참조할 수 없다.
    meta = meta[meta["_source_physical"].isin([s["physical_name"] for s in sources])]

    period_rows = meta.loc[meta["Semantic_Type"] == "period", "Physical_Name"]
    period_colname = str(period_rows.iloc[0]) if len(period_rows) else "기간"

    dim_rows = meta[(meta["Field_Type"] == "Dim") & (meta["Semantic_Type"] != "period")]
    measure_rows = meta[(meta["Field_Type"] == "Measure") & (meta["_source_physical"] != "")]

    select_parts = [f"{period_expr} AS [{period_colname}]"]
    group_parts = [period_expr]
    for _, row in dim_rows.iterrows():
        ref = col_alias(sources, row["_source_physical"], row["Physical_Name"])
        select_parts.append(f'{ref} AS [{row["Physical_Name"]}]')
        group_parts.append(ref)
    for _, row in measure_rows.iterrows():
        ref = col_alias(sources, row["_source_physical"], row["Physical_Name"])
        select_parts.append(f'SUM({ref}) AS [{row["Physical_Name"]}]')
    if not len(measure_rows):
        # 합칠 숫자가 없는 데이터는 건수가 측정값이다(schema.COUNT_MEASURE와 같은 컬럼명이라
        # actual/compare와 이력이 같은 이름을 쓴다).
        from d2insight.engine.schema import COUNT_MEASURE
        select_parts.append(f"COUNT(*) AS [{COUNT_MEASURE}]")

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
