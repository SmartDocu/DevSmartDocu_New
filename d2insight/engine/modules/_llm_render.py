"""모듈 공용 LLM 실행기 — 계산은 검증된 파이썬 함수가, 선택은 LLM이 한다.

원칙(2026-08-27 재설계): LLM은 계산하지 않는다. 이미 검증된 계산 함수(build_by_item_dataset 등,
d2insight/engine/pipeline/dataset_builder.py·_shared.py)가 만든 DataFrame에서 "무엇을 보여줄지"만
고른다. 두 단계:
  1. choose_params  — 계산 함수에 넘길 파라미터(차원 등) 중 스텝이 안 정해준 것만 후보 중에서 고름.
  2. render_from_dataframe — 계산 결과 DataFrame에서 표 열·차트·해설을 고름(열 개수 강제 없음).

정기 보고서 재실행(cache=) 시에는 표열·차트 구성(형식)만 재사용하고, 서술(narrative/summary)은
그 회차 값을 다시 보여주고 매번 새로 쓰게 한다(2026-08-28) — 문장은 형식이 아니라 값에 대한
해석이라 캐시하면 숫자가 바뀌어도 예전 문장이 남는다.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from d2insight.engine._llm import chat
from d2insight.engine.chart import chart_spec
from d2insight.engine.format import korean_money_reference, table_to_markdown
from d2insight.engine.types import Render

MAX_SAMPLE_ROWS = 30
MAX_CHART_ROWS = 20


def _parse_json(text: str) -> dict:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM 응답이 JSON 객체가 아닙니다.")
    return data


_PARAM_SYSTEM = """당신은 데이터 분석 보고서를 설계하는 애널리스트다.
계산 함수를 어떤 파라미터로 부를지 후보 중에서 고른다. 계산은 하지 않는다 — 후보 중 선택만 한다.
출력은 JSON 객체 하나만(키: 항목 이름, 값: 고른 후보). 다른 텍스트를 쓰지 마라."""

_RENDER_SYSTEM = """당신은 데이터 분석 보고서의 애널리스트다.
이미 계산되어 있는 표를 보고, 분석 목적에 맞게 표에 보여줄 열과 차트를 고르고 해설을 쓴다.

규칙
1. 주어진 표에 있는 값만 쓴다. 새 수치를 계산하거나 추정하지 않는다.
2. 표의 열 개수·구성은 정해져 있지 않다 — 분석 목적에 맞게 직접 고른다(전부 써도, 일부만 써도 된다).
3. 숫자는 원본 그대로 옮기는 게 기본이다. 억/만 등 한글 단위로 쓰고 싶으면 반드시 [한글 단위
   참고표]에 나온 값을 그대로 옮기고, 직접 억/만으로 환산하지 마라 — 직접 계산하면 자릿수를
   틀린 사례가 있다(예: 1.34억을 "134억"으로 100배 부풀림). 통화기호는 임의로 붙이지 않는다.
4. narrative: 표를 그대로 나열하지 말고 무엇이 두드러지는지 해석해 3~6문장으로 쓴다. 한국어 평문.
5. summary: narrative의 핵심만 1~2문장으로 압축한다(다른 스텝 결과와 함께 결론이 읽는 요약이다).
6. 출력은 JSON 객체 하나:
   {"table_columns": ["열이름", ...], "chart": {"x": "열이름", "y": "열이름 또는 [열이름,...](여러 계열)",
   "type": "bar|line|pie"} 또는 null,
   "narrative": "...", "summary": "..."}
   다른 텍스트는 쓰지 마라."""

_NARRATIVE_SYSTEM = """당신은 데이터 분석 보고서의 애널리스트다.
표 열 구성과 차트는 이미 정해져 있다 — 그 표에 나온 값을 보고 해설만 새로 쓴다.

규칙
1. 주어진 표에 있는 값만 쓴다. 새 수치를 계산하거나 추정하지 않는다.
2. 숫자는 원본 그대로 옮기는 게 기본이다. 억/만 등 한글 단위로 쓰고 싶으면 반드시 [한글 단위
   참고표]에 나온 값을 그대로 옮기고, 직접 억/만으로 환산하지 마라 — 직접 계산하면 자릿수를
   틀린 사례가 있다(예: 1.34억을 "134억"으로 100배 부풀림). 통화기호는 임의로 붙이지 않는다.
3. narrative: 표를 그대로 나열하지 말고 무엇이 두드러지는지 해석해 3~6문장으로 쓴다. 한국어 평문.
4. summary: narrative의 핵심만 1~2문장으로 압축한다(다른 스텝 결과와 함께 결론이 읽는 요약이다).
5. 출력은 JSON 객체 하나: {"narrative": "...", "summary": "..."} 다른 텍스트는 쓰지 마라."""


def choose_params(
    *, purpose: str, narrative_hint: str, candidates: dict[str, list[str]],
    fixed: dict, label: str = "",
) -> dict:
    """계산 함수에 넘길 파라미터. candidates가 비어 있으면 LLM 호출 없이 fixed 그대로 반환."""
    if not candidates:
        return dict(fixed)
    prompt = (
        f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint or '-'}\n"
        f"[이미 정해진 값] {json.dumps(fixed, ensure_ascii=False)}\n"
        f"[골라야 할 항목과 후보]\n"
        + "\n".join(f"- {k}: {v}" for k, v in candidates.items())
        + "\n\n각 항목에 대해 후보 중 하나를 골라 JSON으로 답하라. 키는 항목 이름, 값은 고른 후보."
    )
    text = chat([{"role": "user", "content": prompt}], grade="fast", system=_PARAM_SYSTEM,
                label=f"{label}:params", call_type="module_param_select")
    chosen = _parse_json(text)
    result = dict(fixed)
    for k, cand in candidates.items():
        picked = chosen.get(k)
        result[k] = picked if picked in cand else cand[0]
    return result


def _build_chart(c: dict | None, chart_source: pd.DataFrame, purpose: str):
    if not isinstance(c, dict) or c.get("x") not in chart_source.columns:
        return None
    y = c.get("y")
    y_cols = [y] if isinstance(y, str) else [col for col in (y or []) if col in chart_source.columns]
    if y_cols and all(col in chart_source.columns for col in y_cols):
        return chart_spec(chart_source[[c["x"], *y_cols]].head(MAX_CHART_ROWS), c.get("type") or "bar", purpose)
    return None


def render_from_dataframe(
    df: pd.DataFrame | None, *, purpose: str, narrative_hint: str, params: dict,
    label: str = "", empty_summary: str = "해당 조건에 표시할 데이터가 없습니다.",
    chart_df: pd.DataFrame | None = None, cache: dict | None = None,
) -> Render:
    """계산이 끝난 DataFrame → LLM이 표 열·차트·서술을 고른 Render.

    chart_df: 표와 차트가 서로 다른 단위(예: 표는 차원별 집계, 차트는 개별 항목)일 때만
    지정한다 — 지정하면 차트 후보 열은 df 대신 이 DataFrame에서 고른다.

    cache: 정기 보고서 재실행용 — 이전에 이 함수가 고른 표열·차트 구성(Render.llm_spec)을
    그대로 주면 그 구성(형식)만 재사용하고 LLM에 다시 묻지 않는다. 서술(narrative/summary)은
    형식이 아니라 그 회차 값에 대한 해석이므로 캐시하지 않는다 — 매번 새 값을 보여주고 다시
    쓰게 한다(구조 선택 없이 해설만 쓰는 좁은 프롬프트라 구조까지 새로 고르는 것보다 가볍다).
    """
    if df is None or df.empty:
        return Render(summary=empty_summary)
    chart_source = chart_df if chart_df is not None else df

    if cache:
        cols = [c for c in (cache.get("table_columns") or []) if c in df.columns]
        table = df[cols] if cols else df
        chart = _build_chart(cache.get("chart"), chart_source, purpose)

        sample = table.head(MAX_SAMPLE_ROWS)
        prompt = (
            f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint or '-'}\n"
            f"[파라미터] {json.dumps(params, ensure_ascii=False, default=str)}\n"
            f"[표]\n{table_to_markdown(sample)}"
            + (f"\n(전체 {len(table):,}행 중 {MAX_SAMPLE_ROWS}행만 표시 — 요약은 전체 기준으로 서술)"
               if len(table) > MAX_SAMPLE_ROWS else "")
            + korean_money_reference(sample)
        )
        text = chat([{"role": "user", "content": prompt}], grade="balanced", system=_NARRATIVE_SYSTEM,
                    label=f"{label}:narrative", call_type="module_narrative")
        n_spec = _parse_json(text)
        narrative = str(n_spec.get("narrative") or "").strip()
        summary = str(n_spec.get("summary") or "").strip()
        # llm_spec은 구조(표열·차트)만 다음 회차로 넘긴다 — 서술은 캐시 대상이 아니므로 저장하지 않는다.
        out_spec = {"table_columns": cache.get("table_columns"), "chart": cache.get("chart")}
        return Render(summary=summary or narrative or empty_summary, table=table, chart=chart,
                     narrative=narrative or None, llm_spec=out_spec)

    sample = df.head(MAX_SAMPLE_ROWS)
    prompt = (
        f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint or '-'}\n"
        f"[파라미터] {json.dumps(params, ensure_ascii=False, default=str)}\n"
        f"[표 열 목록] {list(df.columns)}\n"
        f"[데이터]\n{table_to_markdown(sample)}"
        + (f"\n(전체 {len(df):,}행 중 {MAX_SAMPLE_ROWS}행만 표시 — 요약은 전체 기준으로 서술)"
           if len(df) > MAX_SAMPLE_ROWS else "")
        + (f"\n[차트용 데이터 열 목록] {list(chart_source.columns)}(차트는 이 열 중에서 고른다)"
           if chart_df is not None else "")
        + korean_money_reference(sample)
    )
    text = chat([{"role": "user", "content": prompt}], grade="balanced", system=_RENDER_SYSTEM,
                label=f"{label}:render", call_type="module_render")
    spec = _parse_json(text)

    cols = [c for c in (spec.get("table_columns") or []) if c in df.columns]
    table = df[cols] if cols else df
    chart = _build_chart(spec.get("chart"), chart_source, purpose)

    narrative = str(spec.get("narrative") or "").strip()
    summary = str(spec.get("summary") or "").strip()
    return Render(summary=summary or narrative or empty_summary, table=table, chart=chart,
                 narrative=narrative or None, llm_spec=spec)
