"""데이터 요청 공통 함수 — 모듈은 "이 기간의 이 측정값을 이 기준으로 달라"고만 요청한다.

DB 소스는 SQL로, 업로드 파일은 판다스로 답한다(2026-09-29). 모듈은 데이터가 어디서 왔는지
모른다 — 요청하는 모양이 같다.

두 경로 모두 요청한 측정값을 **원래 테이블(파일)별로 묶어서** 따로 가져온다. 서로 다른 테이블의
측정값을 한 표에 섞어 조인하면 '1'쪽 값(주문 총액 등)이 'N'쪽 행 수만큼 복사되어 합계가
부풀려진다(헤더-디테일 fan-out, 2026-09-28 실사고). 기준(차원)이 측정값과 다른 테이블에 있을
때만 조인하며, 조인은 '1'쪽의 속성을 'N'쪽 행에 붙이는 방향만 허용한다.

  DB      : 테이블별로 자연어 질문을 만들어 쿼리 생성기에 묻는다(d2chat과 같은 방식). 조인이
            필요하면 LLM이 쓴다. 날짜만 :start_date/:end_date로 고정된다.
  업로드  : 파일별 표를 합치지 않고 그대로 쓴다. 기간 컬럼이 없는 파일은 연결 정보로
            기간만 붙인다(1쪽 → N쪽, 방향 검사).

반환하는 표는 행 단위다 — 합계·순위는 모듈이 계산한다.
"""
from __future__ import annotations

import pandas as pd

from d2insight import token_tracker
from d2insight.engine.datasource import build_meta_columns
from d2insight.engine.pipeline.dataset_builder import (
    _actual_range, _compare_range, period_bounds, query_step_dataset, shift_period,
)
from d2insight.engine.schema import COUNT_MEASURE, ROLE_PERIOD, Schema  # noqa: F401


def is_upload(ctx_meta: dict) -> bool:
    return bool(ctx_meta.get("upload_session_id") and ctx_meta.get("upload_dataset_key"))


def _upload_entries(ctx_meta: dict) -> dict[str, dict]:
    from d2insight.report.excel_registry import get_excel_server

    datasets = get_excel_server().session_datasets.get(ctx_meta["upload_session_id"]) or {}
    keys = ctx_meta["upload_dataset_key"].split("+")
    return {k: datasets[k] for k in keys if datasets.get(k)}


def _parent_file(entries: dict[str, dict]) -> str | None:
    """연결 관계에서 '1쪽'(부모) 파일을 찾는다 — 연결 컬럼 값이 유일한 쪽이다. 컬럼 이름이 아니라
    값의 유일성으로 판단한다. 부모가 하나로 정해지지 않으면 None."""
    score = {k: 0 for k in entries}
    for key, e in entries.items():
        df = e["df"]
        for r in (e.get("metadata") or {}).get("reference") or []:
            other = entries.get(r.get("dataset"))
            if other is None or r["left_on"] not in df.columns or r["right_on"] not in other["df"].columns:
                continue
            if df[r["left_on"]].is_unique and not other["df"][r["right_on"]].is_unique:
                score[key] += 1
    best = max(score.values(), default=0)
    owners = [k for k, v in score.items() if v == best and v > 0]
    return owners[0] if len(owners) == 1 else None


def _find_column(entries: dict[str, dict], name: str) -> tuple[str, str] | None:
    """사용자가 말한 날짜 컬럼 이름을 실제 (파일, 컬럼)에 맞춘다 — 원래 이름이나 표시명, 대소문자 무시."""
    want = str(name).strip().lower()
    if not want:
        return None
    for key, e in entries.items():
        meta = (e.get("engine_meta") or {}).get("meta_columns")
        logical = dict(zip(meta["Physical_Name"], meta["Logical_Name"])) if meta is not None else {}
        for col in e["df"].columns:
            if str(col).lower() == want or str(logical.get(col, "")).strip().lower() == want:
                return key, col
    return None


_TIME_VARYING_ROLES = {"amount", "quantity", "discount", "cost", "opex", "inventory", "inbound", "outbound"}


def combine_upload_meta(entries: dict[str, dict], period_hint: str | None = None) -> pd.DataFrame:
    """업로드 파일들의 메타를 하나로 합친다. 기간(period) 컬럼은 하나만 남긴다.

    우선순위: ① 사용자가 지정한 날짜 컬럼 → ② 연결 관계의 '1쪽'(부모) 파일의 기간 → ③ 그대로.
    자식 파일의 날짜는 부모의 날짜를 물려받으므로(DB의 상세 테이블에 날짜가 없는 것과 같다)
    자식이 자기 기간 역할을 갖고 있어도 쓰지 않는다.
    """
    metas: dict[str, pd.DataFrame] = {
        k: e["engine_meta"]["meta_columns"].copy()
        for k, e in entries.items() if e.get("engine_meta")
    }
    if not metas:
        raise ValueError("업로드 데이터셋에 엔진용 역할(semantic) 메타가 없습니다. 다시 업로드해 보세요.")

    # 시간에 따라 쌓이는 값(금액·수량·재고 등)은 날짜가 있는 파일(또는 날짜 있는 파일에서 붙일 수 있는 파일)에만
    # 있을 수 있다. 제품·고객 마스터처럼 날짜가 닿지 않는 파일의 이런 표시는 정책값·속성값(재주문점 등)을
    # 잘못 짚은 것이라 지운다. 안전재고 같은 정책 기준값(safety_stock)은 시간과 무관하므로 건드리지 않는다.
    orig_periods = {k: set(m.loc[m["Semantic_Type"] == ROLE_PERIOD, "Physical_Name"]) for k, m in metas.items()}
    if len(metas) > 1 and any(orig_periods.values()):
        def _has_time(k: str) -> bool:
            if orig_periods[k] & set(entries[k]["df"].columns):
                return True
            return any(cols and _can_attach(k, k2, entries) for k2, cols in orig_periods.items() if k2 != k)

        for k in list(metas):
            if not _has_time(k):
                m = metas[k].copy()
                m.loc[m["Semantic_Type"].isin(_TIME_VARYING_ROLES), "Semantic_Type"] = ""
                metas[k] = m

    def _demote(m: pd.DataFrame, keep_col: str | None) -> pd.DataFrame:
        drop = (m["Semantic_Type"] == ROLE_PERIOD) & (m["Physical_Name"] != keep_col)
        return m[~drop]

    hinted = _find_column(entries, period_hint) if period_hint else None
    if hinted:
        hkey, hcol = hinted
        for k in list(metas):
            metas[k] = _demote(metas[k], hcol if k == hkey else None)
        m = metas.get(hkey)
        if m is not None:
            if hcol in set(m["Physical_Name"]):
                m.loc[m["Physical_Name"] == hcol, ["Semantic_Type", "Is_Date_for_Analytic", "Field_Type"]] = [ROLE_PERIOD, True, "Dim"]
            else:
                m.loc[len(m)] = {"Physical_Name": hcol, "Logical_Name": hcol, "Data_Type": "datetime",
                                 "Field_Type": "Dim", "Is_Key_Measure": False, "Is_Date_for_Analytic": True,
                                 "Semantic_Type": ROLE_PERIOD, "Is_Groupable": False, "Is_Market_Axis": False}
            metas[hkey] = m
    elif len(metas) > 1:
        owner = _parent_file(entries)
        if owner in metas and (metas[owner]["Semantic_Type"] == ROLE_PERIOD).any():
            for k in list(metas):
                if k != owner:
                    metas[k] = _demote(metas[k], None)

    parts = list(metas.values())
    if len(parts) == 1:
        return parts[0]
    return pd.concat(parts, ignore_index=True).drop_duplicates(subset=["Physical_Name"])


def load_meta(ctx_meta: dict) -> pd.DataFrame:
    """이 보고서가 쓰는 데이터의 meta_columns(역할이 그대로 잡힌 전체 스키마)."""
    if is_upload(ctx_meta):
        return combine_upload_meta(_upload_entries(ctx_meta), ctx_meta.get("date_column"))

    source_id = ctx_meta.get("source_id")
    if not source_id:
        raise ValueError("ctx.meta에 source_id가 없습니다.")
    return build_meta_columns(source_id)


def _logical(meta: pd.DataFrame, cols: list[str]) -> str:
    names = dict(zip(meta["Physical_Name"], meta["Logical_Name"]))
    return ", ".join(str(names.get(c, c)) for c in cols)


# ── DB ────────────────────────────────────────────────────────────────────────

def _group_by_table(columns: list[str], meta: pd.DataFrame) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for c in columns:
        rows = meta.loc[meta["Physical_Name"] == c, "_source_physical"]
        table = str(rows.iloc[0]) if len(rows) else ""
        groups.setdefault(table, []).append(c)
    return groups


def _find_query(queries: list | None, measures: list[str], dimensions: list[str],
                kind: str = "") -> dict | None:
    """모듈이 저장해 둔 쿼리 목록에서 같은 것(종류·측정값·기준이 같은 항목)을 찾는다.
    kind: ""는 한 기간 조회, "history"는 여러 기간을 한 번에 가져오는 이력 조회."""
    for q in queries or []:
        if ((q.get("kind") or "") == kind
                and sorted(q.get("measures") or []) == sorted(measures)
                and sorted(q.get("dimensions") or []) == sorted(dimensions)):
            return q
    return None


def _count_rows_db(ctx_meta: dict, dimensions: list[str], meta: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """건수(행 수)는 DB에 없는 가상 컬럼이다 — 행을 그대로 가져와 한 행을 1건으로 센다(집계는 받는 쪽이 한다).
    차원이 없으면 합계만 필요하지만 행을 가져오려면 컬럼이 하나는 있어야 해서, 첫 차원 컬럼을 대신 가져온다."""
    dims = list(dimensions)
    if not dims:
        cand = meta[(meta["Field_Type"] == "Dim") & (meta["Semantic_Type"] != ROLE_PERIOD)]
        dims = cand["Physical_Name"].head(1).tolist()
    actual_df, compare_df, _ = query_step_dataset(
        ctx_meta.get("target_month"), ctx_meta.get("compare_type"), ctx_meta.get("grain", "month"),
        source_id=ctx_meta.get("source_id"), dimensions=dims, measures=[],
        log_ctx=token_tracker.get_log_ctx(), flexible=False,
    )
    for df in (actual_df, compare_df):
        df[COUNT_MEASURE] = 1
    if not dimensions:
        actual_df, compare_df = actual_df[[COUNT_MEASURE]], compare_df[[COUNT_MEASURE]]
    return actual_df, compare_df


def _fetch_db_group(ctx_meta: dict, group_measures: list[str], dimensions: list[str],
                    meta: pd.DataFrame, queries: list | None = None,
                    split_candidates: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if COUNT_MEASURE in group_measures:
        real = [m for m in group_measures if m != COUNT_MEASURE]
        count_a, count_c = _count_rows_db(ctx_meta, dimensions, meta)
        if not real:
            return count_a, count_c
        part_a, part_c = _fetch_db_group(ctx_meta, real, dimensions, meta, queries, split_candidates)

        def _join(part: pd.DataFrame, cnt: pd.DataFrame) -> pd.DataFrame:
            if dimensions:
                c = cnt.groupby(dimensions, dropna=False)[COUNT_MEASURE].sum().reset_index()
                out = part.merge(c, on=dimensions, how="outer")
                out[[COUNT_MEASURE]] = out[[COUNT_MEASURE]].fillna(0.0)
                out[real] = out[real].fillna(0.0)
                return out
            out = part.copy()
            out[COUNT_MEASURE] = float(cnt[COUNT_MEASURE].sum())
            return out

        return _join(part_a, count_a), _join(part_c, count_c)

    target = ctx_meta.get("target_month")
    saved = _find_query(queries, group_measures, dimensions)
    names = _logical(meta, group_measures)
    if dimensions:
        dim_names = _logical(meta, dimensions)
        question = f"{target}의 {dim_names}별 {names}를 조회해주세요."
        if split_candidates:
            # 측정값이 '1'쪽(주문 단위) 테이블 값이고 기준이 '여러 줄'쪽 테이블에 있으면, 조인해서
            # 합산하는 순간 값이 줄 수만큼 복사되어 부풀려진다. 그 기준으로 나눌 수 있는 값을
            # 알려 줘서 LLM이 그 중 의미가 가까운 값을 고르게 한다(2026-09-30).
            question += (f" 단, {dim_names}(으)로 나눌 수 있는 값은 {_logical(meta, split_candidates)}뿐입니다. "
                         f"{names}이(가) 그 기준으로 나눌 수 없는 값이면 이 중 의미가 가장 가까운 값으로 "
                         "조회해주세요.")
    else:
        question = f"{target}의 {names} 합계를 계산해주세요."
    actual_df, compare_df, _sql = query_step_dataset(
        target, ctx_meta.get("compare_type"), ctx_meta.get("grain", "month"),
        source_id=ctx_meta.get("source_id"),
        dimensions=dimensions, measures=group_measures,
        log_ctx=token_tracker.get_log_ctx(),
        natural_question=question,
        flexible=bool(dimensions),
        # 정기보고서 재실행 — 저장된 SQL이 있으면 LLM을 다시 부르지 않고 날짜만 새로 바인딩한다.
        existing_sql=(saved or {}).get("sql"),
    )
    if dimensions:  # [진단] 기준별 조회가 실제로 어떤 SQL을 썼는지 확인용 — 확인 후 삭제
        print(f"[진단-SQL] 질문: {question}\n{_sql}")
    if queries is not None and saved is None:
        queries.append({"measures": list(group_measures), "dimensions": list(dimensions),
                        "question": question, "sql": _sql})
    return actual_df, compare_df


def sums_mismatch(part: dict, total: dict, measure: str) -> str | None:
    """기준(차원)별 조회의 합이 차원 없는 총합과 같은지 본다. 다르면 사유 문장, 같으면 None.

    조인으로 '1'쪽 값이 중복 합산되면 기준별 합이 총합보다 커진다. LLM이 프롬프트 지시를
    어겨도 틀린 숫자가 보고서에 들어가지 않게 하는 검사다.
    """
    for label, p, t in (("분석기간", part["actual"], total["actual"]),
                        ("비교기간", part["compare"], total["compare"])):
        if measure not in p.columns or measure not in t.columns:
            return f"{label} 합계를 확인할 수 없습니다."
        by_dim, whole = float(p[measure].sum()), float(t[measure].sum())
        if abs(by_dim - whole) > max(abs(whole) * 0.005, 0.01):
            return (f"{label} 기준별 합계 {by_dim:,.0f}이(가) 전체 합계 {whole:,.0f}와 다릅니다"
                    "(조인으로 값이 중복 합산되었거나 일부만 조회된 것으로 보입니다).")
    return None


def fetch_frame(ctx_meta: dict, meta: pd.DataFrame, schema, measure: str, dimensions: list[str],
                queries: list | None = None) -> dict:
    """측정값 하나를 기준(차원)들로 나눠 실적/비교 표로 가져온다. 기준 단위로 합산해 돌려준다.

    - 측정값과 기준이 서로 다른 테이블에 있으면, 기준이 있는 테이블의 다른 측정값을 후보로 알려
      LLM이 나눌 수 있는 값으로 바꿔 조회하게 한다(요청한 값을 못 쓰면 바뀐 값의 이름으로 돌려준다).
    - 조회 뒤 기준별 합계를 차원 없는 총합과 대조한다. 다르면 쓰지 않고 오류로 돌려준다.

    반환: {"actual", "compare", "measure"(실제 쓴 측정값), "note", "error"}
    """
    dims = list(dimensions)
    dim_name = ", ".join(str(schema.logical_name(d)) for d in dims)
    measure_name = schema.logical_name(measure)

    m_src = source_of(ctx_meta, meta, measure)
    dim_srcs = {source_of(ctx_meta, meta, d) for d in dims} - {None}
    candidates = None
    if m_src and (dim_srcs - {m_src}):
        other = dim_srcs - {m_src}
        candidates = [m for m in schema.measures
                      if m != measure and source_of(ctx_meta, meta, m) in other] or None

    group = fetch_measure_groups(ctx_meta, [measure], meta, dimensions=dims, queries=queries,
                                 split_candidates=candidates)[0]
    if group["error"]:
        return {"error": f"'{dim_name}' 기준 '{measure_name}' 조회에 실패했습니다: {group['error']}"}

    actual, compare = group["actual"], group["compare"]
    used, note = measure, ""
    if measure not in actual.columns:
        returned = [m for m in schema.measures if m in actual.columns]
        if len(returned) != 1:
            return {"error": f"'{dim_name}' 기준 '{measure_name}' 조회 결과에서 측정값을 찾지 못했습니다."}
        used = returned[0]
        note = (f"요청한 '{measure_name}'은(는) '{dim_name}' 기준으로 나눌 수 없어 "
                f"'{schema.logical_name(used)}'로 조회했다.")

    total = fetch_measure_groups(ctx_meta, [used], meta, queries=queries)[0]
    if total["error"]:
        return {"error": f"'{schema.logical_name(used)}' 전체 합계 확인에 실패했습니다: {total['error']}"}
    reason = sums_mismatch({"actual": actual, "compare": compare}, total, used)
    if reason and candidates:
        # LLM이 나눌 수 없는 값 대신 다른 값을 조회하고 요청한 값의 이름을 붙였을 수 있다(이름 규칙을
        # 어기는 경우). 이름을 믿지 않고 합계 숫자로 가린다 — 나눌 수 있는 후보 중 전체 합계와 맞는
        # 값이 있으면 그 이름으로 바로잡는다.
        for cand in candidates:
            cand_total = fetch_measure_groups(ctx_meta, [cand], meta, queries=queries)[0]
            if cand_total["error"]:
                continue
            renamed = {"actual": actual.rename(columns={used: cand}),
                       "compare": compare.rename(columns={used: cand})}
            if sums_mismatch(renamed, cand_total, cand) is None:
                actual, compare = renamed["actual"], renamed["compare"]
                used, total, reason = cand, cand_total, None
                note = (f"요청한 '{measure_name}'은(는) '{dim_name}' 기준으로 나눌 수 없어 "
                        f"'{schema.logical_name(used)}'로 조회했다.")
                break
    if reason:
        print(f"[data_request] '{dim_name}' 기준 '{schema.logical_name(used)}' 검사 실패: {reason}")
        return {"error": f"'{dim_name}' 기준 '{schema.logical_name(used)}' 조회 결과를 쓸 수 없습니다. {reason}"}

    def _agg(df: pd.DataFrame) -> pd.DataFrame:
        keep = [d for d in dims if d in df.columns]
        return df.groupby(keep, dropna=False)[used].sum().reset_index()

    return {"actual": _agg(actual), "compare": _agg(compare), "measure": used, "note": note, "error": None}


def fetch_wide(ctx_meta: dict, meta: pd.DataFrame, schema, measures: list[str], dimensions: list[str],
               queries: list | None = None) -> dict:
    """여러 측정값을 같은 기준(차원)들로 나눠 한 표에 합친다(기준 단위 외부 결합).

    측정값마다 fetch_frame으로 따로 조회·검사하므로, 요청한 값이 나눌 수 없어 다른 값으로 바뀐
    경우에도 그 이름으로 합쳐진다.

    반환: {"actual", "compare", "used"({요청한 이름: 실제 쓴 이름}), "notes", "error"}
    """
    parts: list[dict] = []
    used: dict[str, str] = {}
    notes: list[str] = []
    for m in measures:
        r = fetch_frame(ctx_meta, meta, schema, m, dimensions, queries)
        if r.get("error"):
            return {"error": r["error"]}
        used[m] = r["measure"]
        if r["note"]:
            notes.append(r["note"])
        if all(p["measure"] != r["measure"] for p in parts):     # 같은 값으로 바뀐 중복은 한 번만
            parts.append(r)

    common = [d for d in dimensions if all(d in p["actual"].columns for p in parts)]

    def _merge(key: str) -> pd.DataFrame:
        out = None
        for p in parts:
            df = p[key][common + [p["measure"]]]
            out = df if out is None else out.merge(df, on=common, how="outer")
        cols = [p["measure"] for p in parts]
        out[cols] = out[cols].fillna(0.0)
        return out

    return {"actual": _merge("actual"), "compare": _merge("compare"),
            "used": used, "notes": notes, "error": None}


def source_of(ctx_meta: dict, meta: pd.DataFrame, col: str) -> str | None:
    """컬럼이 어느 테이블(업로드면 파일)에 있는지."""
    if is_upload(ctx_meta):
        return _file_of(col, _upload_entries(ctx_meta))
    if "_source_physical" not in meta.columns:
        return None
    rows = meta.loc[meta["Physical_Name"] == col, "_source_physical"]
    return str(rows.iloc[0]) if len(rows) else None


def needs_join(ctx_meta: dict, meta: pd.DataFrame, columns: list[str]) -> bool:
    """이 컬럼들이 둘 이상의 테이블(파일)에 걸쳐 있어 조인해야 하는가."""
    sources = {source_of(ctx_meta, meta, c) for c in columns}
    sources.discard(None)
    return len(sources) > 1


# ── 업로드 ────────────────────────────────────────────────────────────────────

def _file_of(col: str, entries: dict[str, dict]) -> str | None:
    for key, e in entries.items():
        if col in e["df"].columns:
            return key
    return None


def _attach(df: pd.DataFrame, own_key: str, cols: list[str], entries: dict[str, dict]) -> pd.DataFrame:
    """다른 파일에 있는 컬럼을 연결 정보로 붙인다. 그 파일이 '1'쪽(연결 컬럼 값이 유일)일 때만
    붙인다 — 'N'쪽 값을 붙이면 행이 곱해져 합계가 어긋난다."""
    by_file: dict[str, list[str]] = {}
    for c in cols:
        src = _file_of(c, entries)
        if src is None:
            raise ValueError(f"컬럼 '{c}'을(를) 가진 업로드 파일이 없습니다.")
        by_file.setdefault(src, []).append(c)

    for src, src_cols in by_file.items():
        refs = (entries[own_key].get("metadata") or {}).get("reference") or []
        rel = next((r for r in refs if r.get("dataset") == src), None)
        if not rel:
            raise ValueError(f"업로드 파일 '{own_key}'와 '{src}'는 조인 정보가 없어 함께 쓸 수 없습니다.")
        other = entries[src]["df"]
        if not other[rel["right_on"]].is_unique:
            raise ValueError(
                f"'{src}'의 '{rel['right_on']}' 값이 유일하지 않아(N쪽) 그 컬럼 {src_cols}을(를) "
                f"'{own_key}'의 행에 붙일 수 없습니다.")
        right = other[[rel["right_on"], *src_cols]]
        df = df.merge(right, left_on=rel["left_on"], right_on=rel["right_on"],
                      how="inner", validate="m:1", suffixes=("", "__r"))
        if rel["right_on"] != rel["left_on"] and rel["right_on"] in df.columns:
            df = df.drop(columns=[rel["right_on"]])
    return df


def _can_attach(own_key: str, src: str, entries: dict[str, dict]) -> bool:
    """src 파일의 컬럼을 own_key 파일의 행에 붙일 수 있는가 — 같은 파일이거나, 연결 정보가 있고 src 쪽
    연결 키가 유일(1쪽)해야 한다(_attach와 같은 규칙)."""
    if own_key == src:
        return True
    refs = (entries[own_key].get("metadata") or {}).get("reference") or []
    rel = next((r for r in refs if r.get("dataset") == src), None)
    if not rel:
        return False
    other = entries[src]["df"]
    return rel["right_on"] in other.columns and bool(other[rel["right_on"]].dropna().is_unique)


def pick_by_rows(ctx_meta: dict, columns: list[str]) -> str | None:
    """같은 의미의 컬럼이 여러 파일에 있고 기준이 되는 다른 컬럼도 없을 때, 행이 가장 많은 파일(가장 세분된
    거래 기록)의 컬럼을 고른다. DB이거나 판단할 근거가 없으면 첫 번째."""
    if not columns:
        return None
    if not is_upload(ctx_meta):
        return columns[0]
    entries = _upload_entries(ctx_meta)

    def _rows(col: str) -> int:
        src = _file_of(col, entries)
        return len(entries[src]["df"]) if src else -1

    return max(columns, key=lambda c: (_rows(c), -columns.index(c)))


def reachable_dims(ctx_meta: dict, measures: list[str], dims: list[str]) -> list[str]:
    """측정값들이 든 파일 모두에서 닿는 차원만 남긴다(업로드). 닿는다 = 그 파일에 컬럼이 있거나 연결 정보로
    1쪽에서 붙일 수 있다. 닿지 않는 차원 하나가 조회 전체를 실패시키지 않게 하려는 것이다. DB는 그대로."""
    if not is_upload(ctx_meta) or not measures:
        return list(dims)
    entries = _upload_entries(ctx_meta)
    owners = {o for o in (_file_of(m, entries) for m in measures if m != COUNT_MEASURE) if o}
    if not owners:
        return list(dims)

    def _ok(col: str) -> bool:
        src = _file_of(col, entries)
        return all(col in entries[o]["df"].columns or (src and _can_attach(o, src, entries)) for o in owners)

    return [d for d in dims if _ok(d)]


def pick_reachable(ctx_meta: dict, columns: list[str], measures: list[str]) -> str | None:
    """같은 의미(예: 항목)의 컬럼이 여러 파일에 있을 때, 측정값 파일에서 닿을 수 있는 것을 고른다.

    측정값이 든 파일에 그 컬럼이 있거나, 연결 정보로 붙일 수 있으면 닿는 것이다. 닿는 측정값 파일이
    많은 컬럼을 먼저 고르고, 같으면 원래 순서를 따른다. DB이거나 판단할 근거가 없으면 첫 번째를 그대로 쓴다.
    """
    if not columns:
        return None
    if not is_upload(ctx_meta) or not measures:
        return columns[0]
    entries = _upload_entries(ctx_meta)
    owners = {o for o in (_file_of(m, entries) for m in measures) if o}
    if not owners:
        return columns[0]

    def _score(col: str) -> int:
        src = _file_of(col, entries)
        score = 0
        for o in owners:
            if col in entries[o]["df"].columns or (src and _can_attach(o, src, entries)):
                score += 1
        return score

    return max(columns, key=lambda c: (_score(c), -columns.index(c)))


def _count_owner(entries: dict[str, dict], needed: list[str]) -> str | None:
    """건수(행 수)를 셀 파일. 건수는 파일에 없는 가상 컬럼이라, 필요한 컬럼(차원·기간) 모두에 닿는
    — 자기 컬럼이거나 1쪽 파일에서 붙일 수 있는 — 파일 중 행이 가장 많은 파일(보통 거래를 담은 N쪽)을 고른다.
    닿는 파일이 없으면 첫 파일."""
    best = None
    for key, e in entries.items():
        reachable = True
        for col in needed:
            if col in e["df"].columns:
                continue
            src = _file_of(col, entries)
            if not (src and _can_attach(key, src, entries)):
                reachable = False
                break
        if reachable and (best is None or len(e["df"]) > len(entries[best]["df"])):
            best = key
    return best or next(iter(entries), None)


def _period_col_for(entries: dict[str, dict], own: str, meta: pd.DataFrame) -> str | None:
    """측정값이 든 파일(own)에서 쓸 기간 컬럼. 합쳐진 메타의 기간 중 그 파일에 있는 것 → 1쪽 파일에서 붙일 수
    있는 것 → 그 파일 자신의 메타에 표시된 기간 순으로 고른다."""
    periods = Schema(meta).columns(ROLE_PERIOD)
    df = entries[own]["df"]
    for p in periods:
        if p in df.columns:
            return p
    for p in periods:
        src = _file_of(p, entries)
        if src and _can_attach(own, src, entries):
            return p
    own_meta = (entries[own].get("engine_meta") or {}).get("meta_columns")
    if own_meta is not None:
        for p in own_meta.loc[own_meta["Semantic_Type"] == ROLE_PERIOD, "Physical_Name"]:
            if p in df.columns:
                return p
    return periods[0] if periods else None


def _fetch_upload_group(ctx_meta: dict, own_key: str, group_measures: list[str],
                        dimensions: list[str], meta: pd.DataFrame,
                        entries: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_col = _period_col_for(entries, own_key, meta)
    if not period_col:
        raise ValueError("업로드 데이터셋에 기간(period) 역할 컬럼이 없어 기간 비교를 할 수 없습니다.")

    df = entries[own_key]["df"]
    real_measures = [m for m in group_measures if m != COUNT_MEASURE]
    # 기간 컬럼·다른 파일의 기준 컬럼은 연결 정보로 붙인다(1쪽 → N쪽).
    missing = [d for d in dimensions if d not in df.columns]
    if period_col not in df.columns:
        missing.append(period_col)
    if missing:
        df = _attach(df, own_key, missing, entries)

    period_dt = pd.to_datetime(df[period_col], errors="coerce")
    grain = ctx_meta.get("grain", "month")
    a_start, a_end = _actual_range(ctx_meta.get("target_month"), grain)
    c_start, c_end = _compare_range(ctx_meta.get("target_month"), ctx_meta.get("compare_type"), grain)
    actual = df[(period_dt >= pd.Timestamp(a_start)) & (period_dt < pd.Timestamp(a_end))].reset_index(drop=True)
    compare = df[(period_dt >= pd.Timestamp(c_start)) & (period_dt < pd.Timestamp(c_end))].reset_index(drop=True)

    keep = [c for c in [*dimensions, *real_measures] if c in actual.columns]
    actual, compare = actual[keep].copy(), compare[keep].copy()
    if COUNT_MEASURE in group_measures:
        actual[COUNT_MEASURE] = 1
        compare[COUNT_MEASURE] = 1
    return actual, compare


# ── 공통 진입점 ───────────────────────────────────────────────────────────────

def fetch_measure_groups(ctx_meta: dict, measures: list[str], meta: pd.DataFrame,
                         dimensions: list[str] | None = None,
                         queries: list | None = None,
                         split_candidates: list[str] | None = None) -> list[dict]:
    """측정값을 원래 테이블(파일)별로 묶어 각각 실적/비교 표를 가져온다.

    queries: 모듈이 가진 쿼리 목록 [{"measures", "dimensions", "question", "sql"}, ...]. DB 조회는
      같은 항목이 있으면 그 SQL을 재사용하고, 없으면 새로 만든 SQL을 여기에 추가한다 — entry.py가
      정기보고서 등록 때 이것을 스냅샷에 저장한다. 업로드는 SQL이 없어 쓰이지 않는다.

    반환: [{"measures": [...], "actual": df|None, "compare": df|None, "error": str|None}, ...]
    한 묶음의 실패가 다른 묶음을 막지 않는다 — 호출한 모듈이 실패한 묶음을 어떻게 다룰지 정한다.
    """
    dims = list(dimensions or [])
    out: list[dict] = []

    if is_upload(ctx_meta):
        entries = _upload_entries(ctx_meta)
        groups: dict[str, list[str]] = {}
        # 같이 요청된 측정값이 있으면 건수는 그 측정값이 든 파일의 행 수다(같은 거래 기록의 건수). 요청된 측정값
        # 파일 중 차원에 닿는 파일 가운데 행이 가장 많은 것을 고른다. 없으면 차원·기간에 닿는 파일을 고른다.
        owners = [o for o in (_file_of(m, entries) for m in measures if m != COUNT_MEASURE) if o]
        count_key = None
        if owners:
            ok = [o for o in dict.fromkeys(owners)
                  if all(d in entries[o]["df"].columns
                         or ((src := _file_of(d, entries)) and _can_attach(o, src, entries)) for d in dims)]
            count_key = max(ok, key=lambda o: len(entries[o]["df"])) if ok else None
        for m in measures:
            if m == COUNT_MEASURE:
                key = count_key or _count_owner(
                    entries, [*dims, *filter(None, [Schema(meta).column(ROLE_PERIOD)])])
            else:
                key = _file_of(m, entries)
            groups.setdefault(key or "", []).append(m)
        for key, group_measures in groups.items():
            try:
                if not key:
                    raise ValueError(f"측정값 {group_measures}을(를) 가진 업로드 파일이 없습니다.")
                a, c = _fetch_upload_group(ctx_meta, key, group_measures, dims, meta, entries)
                out.append({"measures": group_measures, "actual": a, "compare": c, "error": None})
            except Exception as e:
                print(f"[data_request] {group_measures} 조회 실패: {type(e).__name__}: {e}")
                out.append({"measures": group_measures, "actual": None, "compare": None,
                            "error": f"{type(e).__name__}: {e}"})
        return out

    for group_measures in _group_by_table(measures, meta).values():
        try:
            a, c = _fetch_db_group(ctx_meta, group_measures, dims, meta, queries, split_candidates)
            out.append({"measures": group_measures, "actual": a, "compare": c, "error": None})
        except Exception as e:
            print(f"[data_request] {group_measures} 조회 실패: {type(e).__name__}: {e}")
            out.append({"measures": group_measures, "actual": None, "compare": None,
                        "error": f"{type(e).__name__}: {e}"})
    return out


# ── 이력 표 ───────────────────────────────────────────────────────────────────

_GRAIN_WORD = {"month": "월", "quarter": "분기", "half": "반기", "week": "주", "year": "연"}


def _period_id_of(grain: str, ts: pd.Timestamp) -> str:
    """날짜 → 기간 식별자(shift_period가 쓰는 형식과 같다)."""
    if grain == "quarter":
        return f"{ts.year:04d}-Q{(ts.month - 1) // 3 + 1}"
    if grain == "half":
        return f"{ts.year:04d}-H{(ts.month - 1) // 6 + 1}"
    if grain == "year":
        return f"{ts.year:04d}"
    if grain == "week":
        iso = ts.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    return f"{ts.year:04d}-{ts.month:02d}"


def _fetch_history_group(ctx_meta: dict, meta: pd.DataFrame, period_col: str, grain: str,
                         rng: tuple, measures: list[str], dims: list[str],
                         queries: list | None, candidates: list[str] | None = None) -> pd.DataFrame:
    """여러 기간을 SQL 한 번으로 가져온다. 기간 컬럼은 기간 식별자로 바꿔서 돌려준다.

    SQL이 기간별로 묶어 주면 좋지만, 더 잘게(일 단위 등) 가져와도 판다스가 기간 식별자로 다시 합산하므로
    결과는 같다.
    """
    saved = _find_query(queries, measures, dims, "history")
    word = _GRAIN_WORD.get(grain, grain)
    head = f"{rng[0]} 이상 {rng[1]} 미만 기간의 {word}별"
    if dims:
        head += f", {_logical(meta, dims)}별"
    question = (f"{head} {_logical(meta, measures)}를 조회해주세요. 결과에 기간 컬럼을 '{period_col}'이라는 "
                f"이름으로 넣고, 각 {word}의 첫날 날짜 값으로 하세요(예: 월 단위면 그 달 1일).")
    if dims and candidates:
        question += (f" 단, {_logical(meta, dims)}(으)로 나눌 수 있는 값은 {_logical(meta, candidates)}뿐입니다. "
                     f"{_logical(meta, measures)}이(가) 그 기준으로 나눌 수 없는 값이면 이 중 의미가 가장 "
                     "가까운 값으로 조회해주세요.")
    df, _, sql = query_step_dataset(
        ctx_meta.get("target_month"), "MoM", grain,
        source_id=ctx_meta.get("source_id"),
        dimensions=dims, measures=measures,
        log_ctx=token_tracker.get_log_ctx(),
        natural_question=question, flexible=True,
        existing_sql=(saved or {}).get("sql"),
        date_range=rng,
    )
    print(f"[진단-SQL] 이력 질문: {question}\n{sql}")     # [진단] 확인 후 삭제
    if queries is not None and saved is None:
        queries.append({"kind": "history", "measures": list(measures), "dimensions": list(dims),
                        "question": question, "sql": sql})
    if period_col not in df.columns:
        raise ValueError(f"이력 조회 결과에 기간 컬럼 '{period_col}'이 없습니다.")
    stamps = pd.to_datetime(df[period_col], errors="coerce")
    if stamps.isna().any():
        raise ValueError(f"이력 조회 결과의 기간 컬럼 '{period_col}'을(를) 날짜로 읽을 수 없습니다.")
    df = df.copy()
    df[period_col] = stamps.map(lambda t: _period_id_of(grain, t))
    return df


def _agg_by(df: pd.DataFrame, keys: list[str], cols: list[str]) -> pd.DataFrame:
    keep = [k for k in keys if k in df.columns]
    return df.groupby(keep, dropna=False)[cols].sum().reset_index()


def _same_sums(df: pd.DataFrame, col: str, totals: pd.DataFrame, total_col: str, period_col: str) -> bool:
    """df[col]의 기간별 합계가 totals[total_col]과 (허용 오차 안에서) 모두 같은가."""
    part = df.groupby(period_col)[col].sum()
    whole = totals.set_index(period_col)[total_col].fillna(0.0)
    idx = part.index.union(whole.index)
    part, whole = part.reindex(idx, fill_value=0.0), whole.reindex(idx, fill_value=0.0)
    return bool(((part - whole).abs() <= (whole.abs() * 0.005).clip(lower=0.01)).all())


def build_history_panel(ctx_meta: dict, meta: pd.DataFrame, schema, months_back: int, grain: str,
                        queries: list | None = None) -> pd.DataFrame:
    """이력 표 — 여러 기간을 테이블별로 SQL 한 번씩만 가져와 판다스로 기간별 정리한다(2026-09-30).

    예전 이력 표(dataset_builder.build_history_dataset)는 두 테이블을 조인하고 모든 측정값을 그대로
    합산해 '1'쪽 값(주문 총액 등)이 부풀려졌다. 여기서는
      ① 합계 조회   : 측정값을 테이블별로 묶어 기간별 합계를 한 번씩,
      ② 기준별 조회 : 측정값을 테이블별로 묶어 (기간 × 기준)으로 한 번씩
    가져오고, 기간마다 ②의 합이 ①과 같은지 검사한다(다르면 쓰지 않고 오류). 나눌 수 없는 값을 다른
    값으로 조회하면서 이름을 잘못 붙인 경우는 ①의 숫자로 가려 이름을 바로잡는다.

    반환한 표의 attrs에 세 가지를 붙인다(이력을 읽는 모듈이 _shared의 history_* 함수로 꺼낸다).
      alias  : {요청한 측정값: 실제 쓴 측정값} — 나눌 수 없어 바뀐 것만
      notes  : 바뀌었다는 안내 문장들
      totals : 기간별 측정값 합계 표(기준 없음) — 추이·KPI 경보처럼 기준이 필요 없는 모듈용.
               측정값을 바꾸지 않은 요청한 그대로의 값이다.
    """
    from d2insight.engine.schema import (
        ROLE_AMOUNT, ROLE_COST, ROLE_DISCOUNT, ROLE_OPEX, ROLE_QUANTITY,
    )

    period_col = schema.column(ROLE_PERIOD)
    if not period_col:
        raise ValueError("기간(period) 역할 컬럼이 없어 이력 표를 만들 수 없습니다.")
    dims = list(schema.dimensions)
    wanted: list[str] = []
    for role in (ROLE_AMOUNT, ROLE_QUANTITY, ROLE_DISCOUNT, ROLE_COST, ROLE_OPEX):
        col = schema.column(role)
        if col and col not in wanted:
            wanted.append(col)
    if schema.key_measure not in wanted:
        wanted.append(schema.key_measure)
    all_measures = [m for m in schema.measures if m != COUNT_MEASURE]

    target = ctx_meta["target_month"]
    start, _ = period_bounds(grain, shift_period(grain, target, -(months_back - 1)))
    _, end = period_bounds(grain, target)
    rng = (start, end)

    dim_srcs = {source_of(ctx_meta, meta, d) for d in dims} - {None}
    dim_name = _logical(meta, dims)

    # ① 합계 조회 — 기준 없이 기간별 합계. 테이블마다 한 번(기준별 조회를 맞춰 보는 데도 쓴다)
    totals = None
    for gm in _group_by_table(all_measures, meta).values():
        try:
            df = _fetch_history_group(ctx_meta, meta, period_col, grain, rng, gm, [], queries)
        except Exception as e:
            print(f"[data_request] 이력 합계 {gm} 조회 실패: {type(e).__name__}: {e}")
            continue
        cols = [m for m in gm if m in df.columns]
        if not cols:
            continue
        sub = _agg_by(df, [period_col], cols)
        totals = sub if totals is None else totals.merge(sub, on=period_col, how="outer")
    if totals is None:
        raise ValueError("이력 합계를 조회하지 못해 기준별 조회 결과를 검사할 수 없습니다.")
    totals = totals.sort_values(period_col).reset_index(drop=True)

    # ② 기준별 조회 — 테이블(측정값이 있는 곳)마다 한 번
    parts: list[dict] = []
    alias: dict[str, str] = {}
    notes: list[str] = []
    for gm in _group_by_table(wanted, meta).values():
        m_src = source_of(ctx_meta, meta, gm[0])
        other = (dim_srcs - {m_src}) if m_src else set()
        candidates = ([m for m in schema.measures
                       if m not in gm and source_of(ctx_meta, meta, m) in other] or None) if other else None
        df = _fetch_history_group(ctx_meta, meta, period_col, grain, rng, gm, dims, queries, candidates)

        # LLM이 나눌 수 없는 값 대신 다른 값을 조회하고 요청한 값의 이름을 붙였을 수 있다(이름 규칙을
        # 어기는 경우). 이름을 믿지 않고 합계 숫자로 가린다 — 요청한 값의 전체 합계와 다르고, 나눌 수 있는
        # 후보 중 어느 하나의 전체 합계와 같으면 그 후보로 이름을 바로잡는다.
        for m in gm:
            if m in df.columns and m in totals.columns and candidates \
                    and not _same_sums(df, m, totals, m, period_col):
                match = next((c for c in candidates if c in totals.columns and c not in df.columns
                              and _same_sums(df, m, totals, c, period_col)), None)
                if match:
                    df = df.rename(columns={m: match})

        present = [m for m in gm if m in df.columns]
        missing = [m for m in gm if m not in df.columns]
        cols = list(present)
        if missing:
            extras = [c for c in schema.measures if c in df.columns and c not in gm]
            if len(extras) != 1:
                raise ValueError(f"'{dim_name}' 기준 이력 조회 결과에서 '{_logical(meta, missing)}'을(를) "
                                 "찾지 못했습니다.")
            for m in missing:
                alias[m] = extras[0]
            notes.append(f"요청한 '{_logical(meta, missing)}'은(는) '{dim_name}' 기준으로 나눌 수 없어 "
                         f"'{_logical(meta, extras)}'로 조회했다.")
            cols += extras
        cols = [c for c in cols if all(c not in p["cols"] for p in parts)]    # 같은 값으로 바뀐 중복은 한 번만
        if cols:
            parts.append({"df": df, "cols": cols})
    if not parts:
        raise ValueError("이력 표에 담을 측정값을 조회하지 못했습니다.")

    common = [period_col] + [d for d in dims if all(d in p["df"].columns for p in parts)]
    panel = None
    for p in parts:
        sub = _agg_by(p["df"], common, p["cols"])
        panel = sub if panel is None else panel.merge(sub, on=common, how="outer")
    measure_cols = [c for p in parts for c in p["cols"]]
    panel[measure_cols] = panel[measure_cols].fillna(0.0)

    # 검사 — 기간마다 기준별 합계가 전체 합계와 같아야 한다(조인으로 부풀려지면 다르다).
    for m in measure_cols:
        if m not in totals.columns:
            raise ValueError(f"'{_logical(meta, [m])}' 전체 합계를 확인하지 못해 이력 표를 쓸 수 없습니다.")
        part_sum = panel.groupby(period_col)[m].sum()
        whole = totals.set_index(period_col)[m].fillna(0.0)
        idx = part_sum.index.union(whole.index)
        part_sum, whole = part_sum.reindex(idx, fill_value=0.0), whole.reindex(idx, fill_value=0.0)
        bad = idx[((part_sum - whole).abs() > (whole.abs() * 0.005).clip(lower=0.01)).to_numpy()]
        if len(bad):
            pid = bad[0]
            raise ValueError(
                f"이력 표 '{_logical(meta, [m])}' 검사 실패 — {pid} 기준별 합계 {part_sum[pid]:,.0f}이(가) "
                f"전체 합계 {whole[pid]:,.0f}와 다릅니다(조인으로 값이 중복 합산되었거나 일부만 조회된 것으로 "
                f"보입니다). 어긋난 기간 {len(bad)}개.")

    panel = panel.sort_values(period_col).reset_index(drop=True)
    panel.attrs["alias"] = alias
    panel.attrs["notes"] = notes
    panel.attrs["totals"] = totals
    return panel


# ── 기간별 값 (모듈이 필요한 만큼만 요청) ─────────────────────────────────────

_AGGREGATES = ("sum", "avg", "last")


def fetch_attribute(ctx_meta: dict, column: str, dimension: str) -> pd.Series:
    """항목마다 하나인 값(안전재고 정책값처럼 기간과 상관없는 속성)을 차원 항목별로 가져온다.

    같은 값이 여러 줄에 반복돼도 부풀지 않도록 합산하지 않고 max로 읽는다. 업로드 전용 — 그 컬럼이 든
    파일에서 직접 읽는다(다른 파일의 행과 합쳐지지 않는다).
    """
    if not is_upload(ctx_meta):
        raise ValueError("DB 데이터의 항목별 속성 조회는 아직 지원하지 않습니다.")
    entries = _upload_entries(ctx_meta)
    src = _file_of(column, entries)
    if not src:
        raise ValueError(f"컬럼 '{column}'을(를) 가진 업로드 파일이 없습니다.")
    df = entries[src]["df"]
    if dimension not in df.columns:
        df = _attach(df, src, [dimension], entries)
    return df.groupby(dimension, dropna=False)[column].max()


def fetch_series(ctx_meta: dict, meta: pd.DataFrame, schema, measure: str, dimension: str | None,
                 months_back: int, grain: str, aggregate: str = "sum",
                 queries: list | None = None) -> pd.DataFrame:
    """측정값 하나를 차원 하나로 나눠 기간별 값으로 가져온다 — [기간, 차원, 측정값] 표.
    dimension이 None이면 차원 없이 기간별 값만(기간, 측정값) 돌려준다.

    aggregate: 한 기간 안의 여러 날짜 값을 어떻게 하나로 만들지.
      sum  — 흐름 값(매출·출고)의 기간 합계
      avg  — 잔액 값(재고)의 기간 평균(날짜별 값의 평균)
      last — 잔액 값의 기간 말일 값
    같은 날짜에 같은 차원 항목의 행이 여럿(창고별 등)이면 먼저 날짜별로 합친 뒤 집계한다.
    업로드: 측정값이 든 파일의 기간 컬럼을 쓰고, 차원이 다른 파일에 있으면 연결 정보로 붙인다(1쪽만).
    DB: 합계만 지원한다.
    """
    if aggregate not in _AGGREGATES:
        raise ValueError(f"집계 방식 '{aggregate}'을(를) 알 수 없습니다(sum/avg/last 중 선택).")
    target = ctx_meta["target_month"]
    start, _ = period_bounds(grain, shift_period(grain, target, -(months_back - 1)))
    _, end = period_bounds(grain, target)
    periods = schema.columns(ROLE_PERIOD)

    if not is_upload(ctx_meta):
        if aggregate != "sum":
            raise ValueError(f"DB 데이터는 기간 집계 방식 '{aggregate}'을(를) 아직 지원하지 않습니다(합계만 가능).")
        if not periods:
            raise ValueError("기간(period) 역할 컬럼이 없어 기간별 값을 가져올 수 없습니다.")
        pcol = periods[0]
        dims = [dimension] if dimension else []
        # 측정값이 차원과 다른 테이블의 값(주문 총액 등 '1'쪽 값)이면 그 차원으로 나눌 수 없다 — 나눌 수 있는
        # 같은 의미의 값(줄 단위 금액 등)을 후보로 알려 LLM이 바꿔 조회하게 한다(fetch_frame과 같은 방식).
        cands = None
        if dimension:
            m_src, d_src = source_of(ctx_meta, meta, measure), source_of(ctx_meta, meta, dimension)
            if m_src and d_src and m_src != d_src:
                cands = [m for m in schema.measures if m != measure
                         and source_of(ctx_meta, meta, m) == d_src] or None
        def _named(frame: pd.DataFrame, col: str) -> pd.DataFrame:
            """조회 결과의 값 컬럼 이름이 요청한 것과 다르면(건수는 'COUNT(*) AS 건수'처럼 온다) 기간·차원을 뺀
            컬럼이 하나일 때 그 컬럼을 요청한 이름으로 받는다."""
            if col in frame.columns:
                return frame
            extras = [c for c in frame.columns if c not in (pcol, *dims)]
            return frame.rename(columns={extras[0]: col}) if len(extras) == 1 else frame

        df = _named(_fetch_history_group(ctx_meta, meta, pcol, grain, (start, end), [measure], dims, queries, cands),
                    measure)
        out = _agg_by(df, [pcol, *dims], [measure])
        if dimension:
            # 기준별 합계가 전체 합계와 같아야 한다(조인으로 부풀려지면 다르다). 이름을 믿지 않고 숫자로 가린다 —
            # 요청한 값의 합계와 다르면, 나눌 수 있는 후보 값의 전체 합계와 같은지 본다(같으면 그 값으로 조회된 것).
            whole = _agg_by(_named(_fetch_history_group(ctx_meta, meta, pcol, grain, (start, end), [measure], [],
                                                        queries), measure), [pcol], [measure])
            if not _same_sums(out, measure, whole, measure, pcol):
                for cand in cands or []:
                    whole_c = _agg_by(_named(_fetch_history_group(ctx_meta, meta, pcol, grain, (start, end), [cand],
                                                                  [], queries), cand), [pcol], [cand])
                    if _same_sums(out, measure, whole_c, cand, pcol):
                        out.attrs["substituted"] = cand
                        break
                else:
                    raise ValueError(f"'{_logical(meta, [dimension])}' 기준 기간별 합계가 전체 합계와 다릅니다"
                                     "(조인으로 값이 중복 합산되었거나 일부만 조회된 것으로 보입니다).")
        return out

    entries = _upload_entries(ctx_meta)
    own = _file_of(measure, entries)
    if not own:
        raise ValueError(f"측정값 '{measure}'을(를) 가진 업로드 파일이 없습니다.")
    period_col = _period_col_for(entries, own, meta)
    if not period_col:
        raise ValueError("기간(period) 역할 컬럼이 없어 기간별 값을 가져올 수 없습니다.")

    df = entries[own]["df"]
    dims = [dimension] if dimension else []
    missing = [c for c in (*dims, period_col) if c not in df.columns]
    if missing:
        df = _attach(df, own, missing, entries)
    df = df[[period_col, *dims, measure]].copy()
    df["_ts"] = pd.to_datetime(df[period_col], errors="coerce").dt.normalize()
    df = df[(df["_ts"] >= pd.Timestamp(start)) & (df["_ts"] < pd.Timestamp(end))]
    if df.empty:
        raise ValueError(f"{start} 이상 {end} 미만 기간에 '{measure}' 값이 없습니다.")

    daily = df.groupby(["_ts", *dims], dropna=False)[measure].sum().reset_index()
    daily[period_col] = daily["_ts"].map(lambda t: _period_id_of(grain, t))
    if aggregate == "sum":
        grouped = daily.groupby([period_col, *dims], dropna=False)[measure].sum()
    elif aggregate == "avg":
        grouped = daily.groupby([period_col, *dims], dropna=False)[measure].mean()
    else:
        grouped = daily.sort_values("_ts").groupby([period_col, *dims], dropna=False)[measure].last()
    return grouped.reset_index()
