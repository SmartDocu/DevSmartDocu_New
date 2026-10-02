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
from d2insight.engine.schema import (
    COUNT_MEASURE, ROLE_PERIOD, Schema,
)
from d2insight.engine.types import ModuleResult, Render
from d2insight.engine.pipeline.dataset_builder import (
    query_step_dataset, build_history_dataset,
    _actual_range, _compare_range,
)
from d2insight.engine.pipeline.data_request import build_history_panel, combine_upload_meta


_GRAIN_LABEL = {"month": "개월", "quarter": "분기", "half": "반기", "year": "년", "week": "주"}


def _period_basis(schema: Schema, hinted: str | None = None) -> str:
    """기간을 자른 기준 날짜 컬럼 — 보고서 '기간 비교' 표에 밝힌다. 주문일이냐 출하일이냐에 따라
    숫자가 달라지므로 읽는 사람이 알 수 있어야 한다(2026-09-29). 요청에서 지정했으면 그렇게 표시."""
    col = schema.column(ROLE_PERIOD)
    if not col:
        return "-"
    logical = str(schema.logical_name(col))
    label = col if logical == col else f"{logical} ({col})"
    if hinted and str(hinted).strip().lower() in (col.lower(), logical.lower()):
        label += " — 요청에서 지정"
    return label


def _fill_count_measure(meta: pd.DataFrame, frames: dict) -> None:
    """메타에 건수 측정값이 있으면 데이터에도 값 1짜리 컬럼을 만들어 준다.

    합산할 숫자가 없는 데이터(로그 등)에는 메타를 만들 때 건수가 측정값으로 들어간다
    (db_meta.count_measure_row). 그 컬럼은 DB에 없으므로 여기서 채운다. 그러면 모듈은
    평소처럼 groupby(...).sum()을 하고 그 결과가 곧 건수가 된다 — 모듈을 고치지 않는다.

    frames의 DataFrame은 제자리로 수정된다.
    """
    if COUNT_MEASURE not in set(meta["Physical_Name"]):
        return
    for df in frames.values():
        # 이미 있으면 그대로 둔다 — 이력은 SQL이 COUNT(*)로 집계해 온 값이라 1로 덮으면 안 된다.
        if df is not None and COUNT_MEASURE not in df.columns:
            df[COUNT_MEASURE] = 1


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
        return _run_from_upload(target_month, compare_type, upload_session_id, upload_dataset_key, grain,
                                auto=bool(params.get("_auto")),
                                dimensions=params.get("dimensions"), measures=params.get("measures"),
                                period_hint=ctx.meta.get("date_column"))

    source_id = params.get("source_id") or ctx.meta.get("source_id") or DEFAULT_SOURCE_ID
    # [진단] 스텝마다 이력을 몇 개월 어떻게 받는지 확인용 — 확인 후 삭제
    print(f"[진단-이력] needs_history={params.get('needs_history')} months_back={months_back} "
          f"(params={params.get('months_back')}, meta={ctx.meta.get('months_back')}) "
          f"dims={params.get('dimensions')} measures={params.get('measures')}")

    # 스텝 단위 쿼리(2026-08-24) — 이 스텝의 모듈들이 선언한 차원/측정값만 LLM이 SQL로 조회
    # 한다(planner.py의 resolve_dependencies가 모아서 params로 넘겨줌). 뿌리 적재 실패는
    # 예외를 그대로 올린다.
    from d2insight import token_tracker
    actual_df, compare_df, generated_sql = query_step_dataset(
        target_month, compare_type, grain, source_id=source_id,
        dimensions=params.get("dimensions"), measures=params.get("measures"),
        log_ctx=token_tracker.get_log_ctx(), existing_sql=params.get("query_sql"),
    )
    # print(f"[period_dataset] 생성 SQL:\n{generated_sql}")  # jeff 로그 줄이기
    # 정기 보고서 SQL 캐싱(Phase 3) — entry.py가 실행 후 이 값을 읽어 applied_steps에
    # 반영한다(다음 회차부터 LLM 재호출 없이 재사용).
    params["query_sql"] = generated_sql

    meta = build_meta_columns(source_id, available_columns=list(actual_df.columns))
    undeclared = undeclared_columns(meta, list(actual_df.columns))

    outputs = {
        "actual_dataset": actual_df,
        "compare_dataset": compare_df,
    }

    history_note = ""
    history_rows = 0
    if params.get("needs_history"):
        try:
            # 이력 표도 스텝 표와 같은 원칙으로 만든다 — 기간마다 전용 조회 + 합계 검사(data_request).
            full_meta = build_meta_columns(source_id)          # 필터 없는 전체 메타
            # 이력 표는 보고서 안에서 스텝마다 같다 — 처음 만든 스텝이 SQL을 실행하고 다음 스텝은 재사용한다.
            history_df = ctx.get_or_compute(
                f"history_panel::{source_id}::{target_month}::{grain}::{months_back}",
                lambda: build_history_panel(
                    dict(ctx.meta, source_id=source_id), full_meta, Schema(full_meta),
                    months_back, grain, params.setdefault("_queries", []),
                ),
            )
            outputs["history_dataset"] = history_df
            history_rows = len(history_df)
        except Exception as e:
            print(f"[period_dataset] 이력 적재 실패: {type(e).__name__}: {e}")
            history_note = f" (이력 적재 실패: {type(e).__name__} — 생애주기·추이 분석 제한됨)"

    _fill_count_measure(meta, outputs)
    outputs["meta_columns"] = meta

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
    # 차원만 요청한 스텝은 측정값이 없을 수 있다 — 그 모듈들은 필요한 값을 직접 요청하므로 실패시키지 않는다.
    key_name = schema.logical_name(schema.key_measure) if measures else "-"
    grain_label = _GRAIN_LABEL.get(grain, grain)

    source_label = ", ".join(dict.fromkeys(meta["_source_label"])) if "_source_label" in meta else source_id
    info_rows = [
        {"항목": "데이터소스", "값": source_label},
        {"항목": "분석기간", "값": f"{a_start} ~ {a_end_incl} (당기)"},
        {"항목": "비교기간", "값": f"{c_start} ~ {c_end_incl} ({compare_type})"},
        {"항목": "기준 날짜", "값": _period_basis(schema)},
        {"항목": "분석 레코드수", "값": f"{len(actual_df):,}"},
        {"항목": "비교 레코드수", "값": f"{len(compare_df):,}"},
    ]
    if params.get("needs_history"):
        info_rows.append({"항목": "이력 구간", "값": f"최근 {months_back}{grain_label} / {history_rows:,}행"})
    info_rows += [
        {"항목": "차원 수", "값": f"{len(dims)}"},
        {"항목": "측정 수", "값": f"{len(measures)} (핵심: {key_name})"},
    ]
    info = pd.DataFrame(info_rows)

    summary = (
        f"{target_month} 분석 대상 자료 확인 — 분석 {len(actual_df):,}행, "
        f"비교({compare_type}) {len(compare_df):,}행, 차원 {len(dims)}개."
        + history_note
    )

    # print(f"[DEBUG-period-run] params._auto={params.get('_auto')!r} -> render {'생략' if params.get('_auto') else '표시'}")  # jeff
    return ModuleResult(
        outputs=outputs,
        render=None if params.get("_auto") else Render(
            summary=summary, table=info,
            key_value={"분석행": len(actual_df), "비교행": len(compare_df)},
        ),
    )


def _pick_upload_entries(datasets: dict, keys: list[str],
                         dimensions, measures) -> list[tuple[str, dict]]:
    """이 스텝이 요구한 컬럼을 가진 파일만 고른다. 요구가 없거나 못 찾으면 전부.

    DB에서 스텝마다 필요한 테이블만 골라 쿼리하는 것과 같은 자리다.
    """
    available = [(k, datasets[k]) for k in keys if datasets.get(k)]
    wanted = set(dimensions or []) | set(measures or [])
    if not wanted or len(available) <= 1:
        return available
    picked = [(k, e) for k, e in available if wanted & set(e["df"].columns)]
    return picked or available


_MIN_KEY_COVERAGE = 0.95   # 연결 키에서 N쪽 값이 1쪽에 들어 있어야 하는 최소 비율


def _key_coverage(rel: dict) -> float | None:
    """연결 키에서 N쪽 값 중 1쪽에도 있는 비율(업로드 때 저장한 값). 저장된 값이 없으면 None.

    N쪽 값의 일부만 1쪽에 있는 연결(예: 고객.지역 5곳 중 창고.지역에 2곳만 있음)은 합치면 나머지 행이
    사라지고, 뜻이 같은 키가 아닐 가능성이 크다.
    """
    card, s_in, o_in = rel.get("cardinality"), rel.get("self_in_other"), rel.get("other_in_self")
    if not card or s_in is None or o_in is None:
        return None
    if card[0] == "N" and card[2] == "1":
        return s_in                  # 이 파일(N쪽) 값이 상대(1쪽)에 있는 비율
    if card[0] == "1" and card[2] == "N":
        return o_in                  # 상대(N쪽) 값이 이 파일(1쪽)에 있는 비율
    return min(s_in, o_in)           # 1:1


def _merge_upload_frames(entries: list[tuple[str, dict]]) -> tuple["pd.DataFrame", list[str]]:
    """여러 파일을 하나의 평평한 표로 병합한다.

    업로드할 때 파일끼리의 조인 키를 이미 추론해 둔다(excel_server.register_dataset →
    metadata["reference"] = [{dataset, left_on, right_on}]). DB의 reference와 같은 자리이므로
    그것을 그대로 쓴다. 선언된 조인 키가 없으면 붙이지 않는다 — 공통 컬럼명으로 짐작해 붙이면
    행이 곱해져 수치가 어긋난다.

    반환: (병합된 표, 실제로 쓴 파일 키 목록)
    """
    base_key, base = entries[0]
    df = base["df"]
    used = [base_key]
    for key, entry in entries[1:]:
        refs = (entry.get("metadata") or {}).get("reference") or []
        rel = next((r for r in refs if r.get("dataset") in used), None)
        if not rel:
            print(f"[period_dataset] 업로드 '{key}'는 조인 정보가 없어 병합하지 않았습니다.")
            continue
        # 두 쪽 키가 모두 N쪽이면 합칠 때 행이 곱해진다 — 합치지 않는다. 방향은 업로드 때 저장한
        # cardinality를 보고(없으면 데이터로 확인), 지금까지 합친 표 쪽은 현재 상태로 다시 확인한다.
        card = rel.get("cardinality")
        entry_one = (card[0] == "1") if card else bool(entry["df"][rel["left_on"]].dropna().is_unique)
        merged_one = bool(df[rel["right_on"]].dropna().is_unique)
        if not entry_one and not merged_one:
            print(f"[period_dataset] 업로드 '{key}'는 연결 키({rel['left_on']})가 양쪽 모두 N쪽이라 "
                  "합치면 행이 곱해져 병합하지 않았습니다.")
            continue
        coverage = _key_coverage(rel)
        if coverage is not None and coverage < _MIN_KEY_COVERAGE:
            print(f"[period_dataset] 업로드 '{key}'는 연결 키({rel['left_on']})의 N쪽 값이 1쪽에 "
                  f"{coverage * 100:.0f}%만 있어 같은 키로 보기 어려워 병합하지 않았습니다.")
            continue
        df = df.merge(entry["df"], left_on=rel["right_on"], right_on=rel["left_on"], how="inner")
        used.append(key)
    return df, used


def _run_from_upload(target_month: str, compare_type: str,
                     session_id: str, dataset_key: str, grain: str = "month",
                     auto: bool = False,
                     dimensions=None, measures=None, period_hint: str | None = None) -> ModuleResult:
    """업로드된 데이터셋에서 뿌리 이름표를 만든다 (2026-07-20, 레벨 2).

    dataset_key는 "key1+key2" 형태로 여러 파일을 담을 수 있다. 그중 이 스텝이 요구한 컬럼을
    가진 파일만 골라 쓰고, 둘 이상이면 공통 컬럼으로 병합한다.

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
    datasets = excel_server.session_datasets.get(session_id) or {}
    entries = _pick_upload_entries(datasets, dataset_key.split("+"), dimensions, measures)
    if not entries:
        return ModuleResult(
            status="failed",
            error=f"업로드 데이터셋 '{dataset_key}'을 세션 '{session_id}'에서 찾을 수 없습니다.",
        )

    if any(not e.get("engine_meta") for _, e in entries):
        return ModuleResult(
            status="failed",
            error="이 업로드 데이터셋에는 엔진용 역할(semantic) 메타가 없습니다 "
                  "(추론이 실패했거나 아직 만들어지지 않았습니다). 다시 업로드해 보세요.",
        )

    engine_meta = entries[0][1]["engine_meta"]
    raw_df, used_keys = _merge_upload_frames(entries)

    # 실제로 병합된 파일의 컬럼만 남긴다 — 조인 정보가 없어 빠진 파일의 컬럼을 스키마에 두면
    # 모듈이 없는 컬럼을 가리킨다(DB 경로가 available_columns로 거르는 것과 같은 자리).
    # 기간 컬럼은 총평 등 다른 경로와 같은 기준으로 하나만 남긴다(data_request.combine_upload_meta).
    meta = combine_upload_meta({k: e for k, e in entries if k in used_keys}, period_hint)
    # 건수는 파일에 없는 컬럼이라 거르면 안 된다(DB 경로의 datasource.build_meta_columns와 같다).
    meta = meta[meta["Physical_Name"].isin(raw_df.columns)
                | (meta["Physical_Name"] == COUNT_MEASURE)]
    schema = Schema(meta)
    period_col = schema.column(ROLE_PERIOD)
    if not period_col:
        return ModuleResult(
            status="failed",
            error="업로드 데이터셋에 기간(period) 역할 컬럼이 없어 기간 비교를 할 수 없습니다.",
        )

    # 이 스텝에 필요한 열만 남긴다(DB 경로와 동일). measure 미지정 시 대표 측정값을 대신 쓴다.
    dims_needed = set(dimensions or [])
    measures_needed = set(measures or [])
    if (dims_needed or measures_needed) and not measures_needed and schema.measures:
        measures_needed = {schema.key_measure}
    needed = dims_needed | measures_needed
    if needed:
        needed.add(period_col)
        raw_df = raw_df[[c for c in raw_df.columns if c in needed]]

    dataset_label = ", ".join(
        (datasets[k].get("filename") or k) for k in used_keys
    )

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

    _fill_count_measure(meta, {"a": actual_df, "c": compare_df, "h": history_df})

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
    # 차원만 요청한 스텝은 측정값이 없을 수 있다 — 그 모듈들은 필요한 값을 직접 요청하므로 실패시키지 않는다.
    key_name = schema.logical_name(schema.key_measure) if measures else "-"

    info_table = pd.DataFrame([
        {"항목": "데이터소스", "값": f"업로드: {dataset_label}"},
        {"항목": "분석기간", "값": f"{a_start} ~ {a_end_incl} (당월)"},
        {"항목": "비교기간", "값": f"{c_start} ~ {c_end_incl} ({compare_type})"},
        {"항목": "기준 날짜", "값": _period_basis(schema, period_hint)},
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

    # print(f"[DEBUG-period-run-upload] auto={auto!r} -> render {'생략' if auto else '표시'}")  # jeff
    return ModuleResult(
        outputs={
            "actual_dataset": actual_df,
            "compare_dataset": compare_df,
            "history_dataset": history_df,
            "meta_columns": meta,
        },
        render=None if auto else Render(
            summary=summary, table=info_table,
            key_value={"분석행": len(actual_df), "비교행": len(compare_df)},
        ),
    )
