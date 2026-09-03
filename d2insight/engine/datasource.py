"""데이터소스 정의 로더 — meta_columns(§1)의 출처.

컬럼의 역할(semantic)과 표시명(logical)은 **데이터**다. 코드에 두면 데이터셋마다 코드를 고쳐야 한다.

DB 모드는 정적 파일이 아니라 **등록된 마스터데이터(datas/datacols/data_chatmetas)** 에서
요청마다 조립한다(2026-08-14 정정) — d2chat이 쓰는 것과 완전히 같은 소스다. `source_id`는
그 마스터데이터의 datauid(다중 소스면 "+"로 연결)이며, 어느 datauid를 쓸지는
`d2insight.chat.pipeline_runner`가 프로젝트 기준으로 미리 정해 넘겨준다
(`d2insight.engine.pipeline.db_meta.resolve_source_cluster` 참조).

업로드 모드는 여전히 이 파일의 `definition_to_meta_columns()`를 쓴다(사용자 정의 JSON 또는
LLM 추론 결과, `upload_meta.py` 참조) — 그쪽은 그대로 둔다.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_SOURCE_ID = None  # DB 모드는 항상 호출부가 실제 datauid로 채워 넘긴다(암묵적 기본값 없음)


class DataSourceError(Exception):
    """데이터소스 정의를 찾을 수 없거나 형식이 잘못된 경우."""


def definition_to_meta_columns(definition: dict, source_label: str = "",
                               available_columns: list[str] | None = None) -> pd.DataFrame:
    """정의(dict) → meta_columns DataFrame(§1). 파일이든, 업로드 메타 JSON이든, LLM이 만든
    dict든 **형식만 같으면** 여기 하나로 처리한다 — 출처(파일/업로드/LLM추론)는 이 함수의 관심사가
    아니다(§7.3, 역할은 데이터일 뿐 코드가 출처를 가리지 않는다).

    available_columns를 주면 실제 데이터에 없는 컬럼은 제외한다(이력 전용 컬럼 등).
    """
    rows = []
    for col in definition.get("columns", []):
        physical = col["physical"]
        # history_only 컬럼(기간 등)은 actual/compare에는 없고 이력 패널에만 있다. 걸러내면 안 된다.
        if (available_columns is not None and physical not in available_columns
                and not col.get("history_only")):
            continue
        rows.append({
            "Physical_Name": physical,
            "Logical_Name": col.get("logical", physical),
            "Data_Type": col.get("data_type", ""),
            "Field_Type": col.get("field_type", "Dim"),
            "Is_Key_Measure": bool(col.get("is_key_measure", False)),
            "Is_Date_for_Analytic": col.get("semantic") == "period",
            "Semantic_Type": col.get("semantic", ""),
            "Is_Groupable": bool(col.get("is_groupable", True)),
            "Is_Market_Axis": bool(col.get("is_market_axis", True)),
        })
    if not rows:
        raise DataSourceError(f"데이터소스 '{source_label}' 정의에 사용할 수 있는 컬럼이 없습니다.")
    from d2insight.engine.pipeline.db_meta import count_measure_row
    return count_measure_row(pd.DataFrame(rows))


def build_meta_columns(source_id: str = DEFAULT_SOURCE_ID,
                       available_columns: list[str] | None = None) -> pd.DataFrame:
    """등록된 마스터데이터(source_id="datauid" 또는 "datauid1+datauid2") → meta_columns(§1).

    호출부(entry.py 등)가 이미 프로젝트 기준으로 resolve해 넘긴 source_id를 그대로 datauid로
    해석한다 — 정의 파일을 다시 찾지 않는다.
    """
    if not source_id:
        raise DataSourceError(
            "source_id가 지정되지 않았습니다 — DB 모드는 어느 등록된 마스터데이터를 쓸지 "
            "호출부(pipeline_runner._run_via_engine)가 프로젝트 기준으로 미리 정해 넘겨야 합니다."
        )
    from d2insight.engine.pipeline import db_meta
    from d2insight.engine.schema import COUNT_MEASURE

    sources = [db_meta.fetch_registered_data(uid) for uid in source_id.split("+")]
    meta = db_meta.build_meta_columns(sources)
    if available_columns is not None:
        # 건수는 DB 컬럼이 아니라 조회 결과에 없다 — 거르면 안 된다.
        meta = meta[meta["Physical_Name"].isin(available_columns)
                    | meta["Is_Date_for_Analytic"]
                    | (meta["Physical_Name"] == COUNT_MEASURE)]
    return meta


def undeclared_columns(meta: pd.DataFrame, available_columns: list[str]) -> list[str]:
    """실제 데이터에는 있는데 정의에 없는 컬럼. 역할 없이 분석되므로 보고서에 알린다."""
    declared = set(meta["Physical_Name"])
    return [c for c in available_columns if c not in declared]
