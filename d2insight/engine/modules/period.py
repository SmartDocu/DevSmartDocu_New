"""period_dataset 모듈 — 분석기간·비교기간·이력과 컬럼 메타 적재 (§1).

모든 분석·집계 모듈의 뿌리 이름표(actual_dataset/compare_dataset/history_dataset/meta_columns)를 만든다.

meta_columns는 **데이터소스 정의**(datasources/<source_id>.json)에서 온다. 컬럼의 역할(semantic)과
표시명(logical)이 코드에 없으므로, 구매·생산 등 다른 데이터소스는 정의 파일만 추가하면 되고
모듈 코드는 바뀌지 않는다(§7.3).

history 적재는 best-effort다: 실패해도 actual/compare/meta는 내보낸다. 다만 history가 없으면
신규/이탈 생애주기 판정(§4.1)과 추이 분석을 할 수 없고, 해당 모듈이 그 사실을 명시한다.
actual/compare 적재 실패는 뿌리이므로 예외를 그대로 올린다(runner가 실패 기록, 후속 전부 생략).
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

import d2insight.config as config
from d2insight.engine.datasource import DEFAULT_SOURCE_ID, build_meta_columns, undeclared_columns
from d2insight.engine.schema import ROLE_PERIOD, Schema
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.dataset_builder import (
    build_actual_compare_datasets, build_history_dataset,
    _actual_range, _compare_range,
)


_GRAIN_LABEL = {"month": "개월", "quarter": "분기", "year": "년", "week": "주"}


def run(ctx, params, tools) -> ModuleResult:
    target_month = ctx.meta.get("target_month")
    if not target_month:
        return ModuleResult(status="failed", error="ctx.meta에 target_month가 없습니다.")

    compare_type = params.get("compare_type") or ctx.meta.get("compare_type") or config.COMPARE_TYPE
    months_back = (params.get("months_back") or ctx.meta.get("months_back")
                   or getattr(config, "HISTORY_MONTHS", 7))
    # 기간 단위(grain, 2026-07-24 3단계) — month(기본, 하위호환)/quarter/year/week.
    grain = params.get("grain") or ctx.meta.get("grain") or "month"

    upload_session_id = ctx.meta.get("upload_session_id")
    upload_dataset_key = ctx.meta.get("upload_dataset_key")
    if upload_session_id and upload_dataset_key:
        return _run_from_upload(target_month, compare_type, upload_session_id, upload_dataset_key, grain)

    source_id = params.get("source_id") or ctx.meta.get("source_id") or DEFAULT_SOURCE_ID

    # 뿌리 적재 — 실패 시 예외를 그대로 올린다.
    actual_df, compare_df = build_actual_compare_datasets(
        target_month, compare_type, grain, source_id=source_id,
    )

    meta = build_meta_columns(source_id, available_columns=list(actual_df.columns))
    undeclared = undeclared_columns(meta, list(actual_df.columns))

    outputs = {
        "actual_dataset": actual_df,
        "compare_dataset": compare_df,
        "meta_columns": meta,
    }

    history_note = ""
    try:
        history_df = build_history_dataset(target_month, months_back, grain, source_id=source_id)
        outputs["history_dataset"] = history_df
        history_rows = len(history_df)
    except Exception as e:
        history_rows = 0
        history_note = f" (이력 적재 실패: {type(e).__name__} — 생애주기·추이 분석 제한됨)"

    if undeclared:
        # 정의에 없는 컬럼은 역할이 없어 브리지·생애주기 계산에서 빠진다. 조용히 넘기지 않는다.
        history_note += f" 데이터소스 정의에 없는 컬럼: {', '.join(undeclared)}."

    a_start, a_end = _actual_range(target_month, grain)
    c_start, c_end = _compare_range(target_month, compare_type, grain)
    # 범위는 반열린 구간 [시작, 끝)이라 끝값(다음 기간 시작일)은 포함되지 않는다.
    # 표시는 실제 포함되는 마지막 날(상한 − 1일)로 찍는다.
    a_end_incl = a_end - timedelta(days=1)
    c_end_incl = c_end - timedelta(days=1)
    schema = Schema(meta)
    dims = schema.dimensions                       # 기간 컬럼은 분석 차원이 아니므로 빠진다
    measures = schema.measures
    key_name = schema.logical_name(schema.key_measure)
    grain_label = _GRAIN_LABEL.get(grain, grain)

    info = pd.DataFrame([
        {"항목": "데이터소스", "값": source_id},
        {"항목": "분석기간", "값": f"{a_start} ~ {a_end_incl} (당기)"},
        {"항목": "비교기간", "값": f"{c_start} ~ {c_end_incl} ({compare_type})"},
        {"항목": "분석 레코드수", "값": f"{len(actual_df):,}"},
        {"항목": "비교 레코드수", "값": f"{len(compare_df):,}"},
        {"항목": "이력 구간", "값": f"최근 {months_back}{grain_label} / {history_rows:,}행"},
        {"항목": "차원 수", "값": f"{len(dims)}"},
        {"항목": "측정 수", "값": f"{len(measures)} (핵심: {key_name})"},
    ])

    summary = (
        f"{target_month} 분석 대상 자료 확인 — 분석 {len(actual_df):,}행, "
        f"비교({compare_type}) {len(compare_df):,}행, 차원 {len(dims)}개."
        + history_note
    )

    return ModuleResult(
        outputs=outputs,
        render=Render(summary=summary, table=info,
                      key_value={"분석행": len(actual_df), "비교행": len(compare_df)}),
    )


def _run_from_upload(target_month: str, compare_type: str,
                     session_id: str, dataset_key: str, grain: str = "month") -> ModuleResult:
    """업로드된 데이터셋에서 뿌리 이름표를 만든다 (2026-07-20, 레벨 2).

    DB 경로(build_actual_compare_datasets)는 SQL이 기간별로 나눠서 가져오지만, 업로드는
    **평평한 표 하나**뿐이다. 그래서 여기서 직접 기간(period) 역할 컬럼을 기준으로
    실적/비교 구간을 잘라낸다 — 날짜 계산(_actual_range/_compare_range)은 DB 경로와
    동일한 함수를 그대로 재사용한다(반열린 구간 규약이 어긋나면 안 된다).

    이력(history_dataset)은 전체 유효 기간을 담되, 기간 컬럼을 **월 단위 문자열**('YYYY-MM')로
    뭉갠다 — trend·abc_classification 등 이력 소비 모듈이 월별 그룹핑을 기대하기 때문이다.
    grain이 month가 아니어도 이 뭉개기는 월 단위 그대로다(2026-07-24 3단계 범위 밖 — 업로드
    경로의 메타는 세션 메모리 전용이라 이번 일반화 대상이 아니라고 확인됨). actual/compare
    구간 자르기(a_start~a_end 등)만 grain을 반영한다.

    역할 메타가 없거나(engine_meta 미생성) 기간 역할이 없으면 조용히 넘기지 않고 명시적으로
    실패한다(§11 Step 2) — 업로드 데이터로는 무엇을 할 수 있는지 알 수 없는 상태이기 때문이다.
    """
    from d2insight.report.excel_registry import get_excel_server

    excel_server = get_excel_server()
    entry = (excel_server.session_datasets.get(session_id) or {}).get(dataset_key)
    if entry is None:
        return ModuleResult(
            status="failed",
            error=f"업로드 데이터셋 '{dataset_key}'을 세션 '{session_id}'에서 찾을 수 없습니다.",
        )

    engine_meta = entry.get("engine_meta")
    if not engine_meta:
        return ModuleResult(
            status="failed",
            error="이 업로드 데이터셋에는 엔진용 역할(semantic) 메타가 없습니다 "
                  "(추론이 실패했거나 아직 만들어지지 않았습니다). 다시 업로드해 보세요.",
        )

    meta = engine_meta["meta_columns"]
    schema = Schema(meta)
    period_col = schema.column(ROLE_PERIOD)
    if not period_col:
        return ModuleResult(
            status="failed",
            error="업로드 데이터셋에 기간(period) 역할 컬럼이 없어 기간 비교를 할 수 없습니다.",
        )

    raw_df = entry["df"]
    if period_col not in raw_df.columns:
        return ModuleResult(status="failed",
                            error=f"기간 역할 컬럼 '{period_col}'이 데이터에 없습니다.")

    period_dt = pd.to_datetime(raw_df[period_col], errors="coerce")
    invalid_n = int(period_dt.isna().sum())
    valid = raw_df[period_dt.notna()].copy()
    valid_dt = period_dt[period_dt.notna()]

    a_start, a_end = _actual_range(target_month, grain)
    c_start, c_end = _compare_range(target_month, compare_type, grain)
    a_start_ts, a_end_ts = pd.Timestamp(a_start), pd.Timestamp(a_end)
    c_start_ts, c_end_ts = pd.Timestamp(c_start), pd.Timestamp(c_end)

    actual_df = valid[(valid_dt >= a_start_ts) & (valid_dt < a_end_ts)].reset_index(drop=True)
    compare_df = valid[(valid_dt >= c_start_ts) & (valid_dt < c_end_ts)].reset_index(drop=True)

    # 이력 — 월 단위로 뭉갠 별도 사본. actual/compare는 원본 날짜 그대로 둔다(모듈이 요구하지 않음).
    history_df = valid.copy()
    history_df[period_col] = valid_dt.dt.strftime("%Y-%m")
    history_df = history_df.reset_index(drop=True)

    undeclared = undeclared_columns(meta, list(raw_df.columns))

    note = ""
    if invalid_n:
        note += f" 기간 값을 해석하지 못한 {invalid_n:,}행은 제외했습니다."
    if undeclared:
        note += f" 데이터소스 정의에 없는 컬럼: {', '.join(undeclared)}."
    warnings = engine_meta.get("info", {}).get("warnings") or []
    if warnings:
        note += " 역할 추론 경고: " + " / ".join(warnings)

    a_end_incl = a_end - timedelta(days=1)
    c_end_incl = c_end - timedelta(days=1)
    dims = schema.dimensions
    measures = schema.measures
    key_name = schema.logical_name(schema.key_measure) if measures else "-"

    info_table = pd.DataFrame([
        {"항목": "데이터소스", "값": f"업로드: {dataset_key}"},
        {"항목": "분석기간", "값": f"{a_start} ~ {a_end_incl} (당월)"},
        {"항목": "비교기간", "값": f"{c_start} ~ {c_end_incl} ({compare_type})"},
        {"항목": "분석 레코드수", "값": f"{len(actual_df):,}"},
        {"항목": "비교 레코드수", "값": f"{len(compare_df):,}"},
        {"항목": "이력 구간", "값": f"{len(history_df):,}행"},
        {"항목": "차원 수", "값": f"{len(dims)}"},
        {"항목": "측정 수", "값": f"{len(measures)} (핵심: {key_name})"},
        {"항목": "역할 메타 출처", "값": engine_meta.get("info", {}).get("source", "-")},
    ])

    summary = (
        f"{target_month} 분석 대상 자료 확인(업로드) — 분석 {len(actual_df):,}행, "
        f"비교({compare_type}) {len(compare_df):,}행, 차원 {len(dims)}개." + note
    )

    return ModuleResult(
        outputs={
            "actual_dataset": actual_df,
            "compare_dataset": compare_df,
            "history_dataset": history_df,
            "meta_columns": meta,
        },
        render=Render(summary=summary, table=info_table,
                      key_value={"분석행": len(actual_df), "비교행": len(compare_df)}),
    )
