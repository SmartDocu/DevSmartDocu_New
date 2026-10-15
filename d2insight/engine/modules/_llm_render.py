"""모듈 공용 LLM 실행기 — 계산은 검증된 파이썬 함수가, 선택은 LLM이 한다.

이미 검증된 계산 함수(build_by_item_dataset 등, d2insight/engine/pipeline/dataset_builder.py·
_shared.py)가 만든 DataFrame에서 LLM이 "무엇을 보여줄지"만 고른다. 두 단계:
  1. choose_params  — 계산 함수에 넘길 파라미터(차원 등) 중 스텝이 안 정해준 것만 후보 중에서 고름.
  2. render_from_dataframe — 계산 결과 DataFrame에서 표 열·차트·해설을 고름(열 개수 강제 없음).

정기 보고서 재실행(cache=) 시에는 표열·차트 구성(형식)만 재사용하고, 서술(narrative/summary)은
그 회차 값을 다시 보여주고 매번 새로 쓰게 한다(2026-08-28) — 문장은 형식이 아니라 값에 대한
해석이라 캐시하면 숫자가 바뀌어도 예전 문장이 남는다.
"""
from __future__ import annotations

import json
import logging
import re

import pandas as pd

from d2insight.engine import number_check
from d2insight.engine._llm import chat
from d2insight.engine.chart import chart_spec
from d2insight.engine.format import df_facts, facts_json, table_to_markdown

log = logging.getLogger("d2insight.number_check")
from d2insight.engine.types import Render

MAX_SAMPLE_ROWS = 30
MAX_CHART_ROWS = 20


def column_notes(df: pd.DataFrame | None, notes: dict | None) -> str:
    """표 열 목록 + 열마다의 뜻(임시 메타).

    모듈이 계산으로 만든 열(Variance, Share 등)은 이름만으로 뜻이 안 통한다. 실제로
    sonnet이 Variance를 "1위와 2위의 격차"로 읽어 서술한 사례가 있다(2026-09-04). 등록 메타를
    고치는 게 아니라, 그 표에 대해서만 유효한 설명을 모듈이 그때그때 붙여 여기로 넘긴다.
    """
    if df is None:
        return ""
    notes = notes or {}
    lines = [f"- {c}" + (f"  {notes[c]}" if notes.get(c) else "") for c in df.columns]
    return "[표 열]\n" + "\n".join(lines) + "\n"


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


def _chat_json(prompt: str, system: str, *, label: str, call_type: str) -> dict:
    """LLM 호출 + JSON 파싱. 파싱에 실패하면 한 번 다시 부른다.

    해설 문장 안의 따옴표·줄바꿈 때문에 JSON이 깨지는 일이 가끔 있고, 그때 예외가 그대로 올라가면
    그 단계가 통째로 "실패"로 기록된다(물량 단계가 보고서에서 빠진 사례, 2026-10-13).
    """
    last: Exception | None = None
    for attempt in (1, 2):
        text = chat([{"role": "user", "content": prompt}], grade="balanced", system=system,
                    label=label, call_type=call_type)
        try:
            return _parse_json(text)
        except Exception as e:
            last = e
            log.warning("[%s] JSON 파싱 실패(%d/2): %s", label, attempt, e)
    raise last


_PARAM_SYSTEM = """당신은 데이터 분석 보고서를 설계하는 애널리스트다.
계산 함수를 어떤 파라미터로 부를지 후보 중에서 고른다. 계산은 하지 않는다 — 후보 중 선택만 한다.
출력은 JSON 객체 하나만(키: 항목 이름, 값: 고른 후보). 다른 텍스트를 쓰지 마라."""

_RENDER_SYSTEM = """당신은 데이터 분석 보고서의 애널리스트다.
이미 계산되어 있는 표를 보고, 분석 목적에 맞게 표에 보여줄 열과 차트를 고르고 해설을 쓴다.

규칙
1. 주어진 표에 있는 값만 쓴다. 새 수치를 계산하거나 추정하지 않는다. 분석 대상은 표에 나온
   차원·열 이름 그대로 부른다(예: 표가 '상품명'이면 상품) — 표에 없는 대상(고객·사용자·지역 등)으로
   바꿔 부르거나 새로 만들어 붙이지 않는다.
2. 표의 열 개수·구성은 정해져 있지 않다 — 분석 목적에 맞게 직접 고른다(전부 써도, 일부만 써도 된다).
3. 숫자는 자료에 나온 그대로 옮긴다(천단위 쉼표 포함). 억·만 같은 한글 단위로 환산하지 않는다.
   통화기호는 임의로 붙이지 않는다.
4. narrative: 표를 그대로 나열하지 말고 무엇이 두드러지는지 해석해 3~6문장으로 쓴다. 한국어 평문.
   표에 보이는 행 밖의 항목에 대해 "유일하게", "모든", "대부분" 같은 전체 일반화는 [표 통계]나
   [추가 값]에 근거가 있을 때만 쓴다. 비율·합계·비중은 [표 통계]와 [추가 값]에 있는 값만 쓰고 직접 만들지 않는다.
   "더 크다/작다/절반 이상/상회" 같은 비교는 쓰기 전에 두 숫자의 크기를 확인한다. 비중에는 [추가 값]에 적힌
   분모 이름을 그대로 쓴다. 상위 몇 개를 말할 때는 [표 통계]의 "절댓값 상위 3행"에 적힌 항목과 값을 그대로 쓴다.
   항목 이름은 자료에 적힌 그대로 쓰고 번역하지 않으며, 자료에 없는 이름을 지어내지 않는다.
   [추가 값]에 "요청한 측정값 → 실제 사용한 측정값"이 있으면 그 사실을 한 문장으로 밝힌다.
5. summary: narrative의 핵심만 1~2문장으로 압축한다(다른 스텝 결과와 함께 결론이 읽는 요약이다).
6. 출력은 JSON 객체 하나:
   {"table_columns": ["열이름", ...], "chart": {"x": "열이름", "y": "열이름 또는 [열이름,...](여러 계열)",
   "type": "bar|line|pie", "title": "차트 제목"} 또는 null,
   (차트 제목은 명사형 20자 이내의 짧은 이름이다. "~를 제시", "~를 보여준다" 같은 서술문이나 분석 목적 문장을
   쓰지 않는다. 예: "월별 총 주문 금액 추이", "상품별 물량 효과 상위 10". 시간 순서 추이는 line을 고른다.)
   "narrative": "...", "summary": "..."}
   다른 텍스트는 쓰지 마라."""

_NARRATIVE_SYSTEM = """당신은 데이터 분석 보고서의 애널리스트다.
표 열 구성과 차트는 이미 정해져 있다 — 그 표에 나온 값을 보고 해설만 새로 쓴다.

규칙
1. 주어진 표에 있는 값만 쓴다. 새 수치를 계산하거나 추정하지 않는다. 분석 대상은 표에 나온
   차원·열 이름 그대로 부른다(예: 표가 '상품명'이면 상품) — 표에 없는 대상(고객·사용자·지역 등)으로
   바꿔 부르거나 새로 만들어 붙이지 않는다.
2. 숫자는 자료에 나온 그대로 옮긴다(천단위 쉼표 포함). 억·만 같은 한글 단위로 환산하지 않는다.
   통화기호는 임의로 붙이지 않는다.
3. narrative: 표를 그대로 나열하지 말고 무엇이 두드러지는지 해석해 3~6문장으로 쓴다. 한국어 평문.
   표에 보이는 행 밖의 항목에 대해 "유일하게", "모든", "대부분" 같은 전체 일반화는 [표 통계]나
   [추가 값]에 근거가 있을 때만 쓴다. 비율·합계·비중은 [표 통계]와 [추가 값]에 있는 값만 쓰고 직접 만들지 않는다.
   "더 크다/작다/절반 이상/상회" 같은 비교는 쓰기 전에 두 숫자의 크기를 확인한다. 비중에는 [추가 값]에 적힌
   분모 이름을 그대로 쓴다. 상위 몇 개를 말할 때는 [표 통계]의 "절댓값 상위 3행"에 적힌 항목과 값을 그대로 쓴다.
   항목 이름은 자료에 적힌 그대로 쓰고 번역하지 않으며, 자료에 없는 이름을 지어내지 않는다.
   [추가 값]에 "요청한 측정값 → 실제 사용한 측정값"이 있으면 그 사실을 한 문장으로 밝힌다.
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


_CALC_SYSTEM = """당신은 데이터 분석 보고서를 준비하는 애널리스트다.
서술 지침이 표에 없는 계산된 값을 요구하는지 판단한다. 계산은 하지 않는다 — 필요하면
판다스 수식만 만든다. 표에 있는 열 이름과 +, -, *, /, .cumsum(), .diff(), .shift(n), .mean(),
.sum(), .rank() 같은 판다스 메서드만 쓴다.

출력은 JSON 객체 하나.
필요 없으면 {"needed": false}
필요하면 {"needed": true, "formula": "판다스 수식", "new_column": "새 열 이름(한글)"}
비율을 만들 때는 100을 곱하지 않는다(0.4225처럼 소수로). 이름이 율·비율·비중으로 끝나는 열은 표시할 때
자동으로 %가 붙고 100배 되므로, 이미 100을 곱하면 4225%처럼 부풀어 보인다.
예: {"needed": true, "formula": "Contribution_Rate.cumsum()", "new_column": "누적 기여율"}
다른 텍스트는 쓰지 마라."""


def _decide_calc(df: pd.DataFrame, purpose: str, narrative_hint: str, label: str) -> dict | None:
    """narrative_hint가 표에 없는 값을 요구하는지 판단해, 필요하면 수식을 받는다."""
    if not narrative_hint:
        return None
    prompt = f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint}\n[표 열 목록] {list(df.columns)}"
    try:
        text = chat([{"role": "user", "content": prompt}], grade="fast", system=_CALC_SYSTEM,
                    label=f"{label}:calc", call_type="module_calc_select")
        spec = _parse_json(text)
    except Exception:
        return None
    return spec if spec.get("needed") else None


def _apply_calc(df: pd.DataFrame, spec: dict | None) -> tuple[pd.DataFrame, dict]:
    """LLM이 만든 수식을 판다스로 실행해 열 하나를 추가한다. 계산은 판다스가 한다. 실패하면 원본 그대로."""
    if not spec:
        return df, {}
    formula, new_col = spec.get("formula"), spec.get("new_column")
    if not formula or not new_col or new_col in df.columns:
        return df, {}
    try:
        result = df.eval(formula, engine="python")
        if not isinstance(result, pd.Series) or len(result) != len(df):
            return df, {}
        df = df.copy()
        df[new_col] = result
    except Exception:
        return df, {}
    return df, {new_col: formula}


_DESCRIBE_SYSTEM = """당신은 데이터 분석 보고서를 준비하는 애널리스트다.
표의 열 이름 중 뜻이 바로 안 통하는 것이 있으면 표시명과 설명을 붙인다. 열 이름 자체는
바꾸지 않는다 — 그 옆에 붙일 정보만 만든다. 뜻이 이미 분명한 열(항목명, 차원 이름 등)은
넣지 않는다.

출력은 JSON 객체 하나. 키는 열 이름, 값은 {"표시명": "...", "설명": "..."}.
다른 텍스트는 쓰지 마라."""


def _describe_columns(df: pd.DataFrame, purpose: str, narrative_hint: str, label: str) -> dict:
    """뜻이 안 통하는 열에 표시명·설명을 붙인다(열 이름은 그대로 둔다). 실패하면 빈 채로 진행."""
    prompt = f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint or '-'}\n[표 열 목록] {list(df.columns)}"
    try:
        text = chat([{"role": "user", "content": prompt}], grade="fast", system=_DESCRIBE_SYSTEM,
                    label=f"{label}:describe", call_type="module_column_describe")
        spec = _parse_json(text)
    except Exception:
        return {}
    notes: dict[str, str] = {}
    for col, desc in spec.items():
        if col not in df.columns or not isinstance(desc, dict):
            continue
        name, explain = desc.get("표시명"), desc.get("설명")
        if name and explain:
            notes[col] = f"{name} — {explain}"
        elif name or explain:
            notes[col] = name or explain
    return notes


def _build_chart(c: dict | None, chart_source: pd.DataFrame, purpose: str):
    if not isinstance(c, dict) or c.get("x") not in chart_source.columns:
        return None
    y = c.get("y")
    y_cols = [y] if isinstance(y, str) else [col for col in (y or []) if col in chart_source.columns]
    if y_cols and all(col in chart_source.columns for col in y_cols):
        # 제목은 짧은 이름이어야 한다. 예전엔 분석 목적 문장(purpose)을 그대로 넘겨 "…를 제시." 같은 서술문이
        # 차트 제목이 됐다(2026-10-14). LLM이 준 제목이 없거나 서술문 같으면 열 이름으로 만든다.
        title = str(c.get("title") or "").strip()
        if not title or len(title) > 30 or title.endswith(("다.", "다", "라.", "제시.", "제시")):
            title = f"{', '.join(map(str, y_cols))} ({c['x']}별)"
        return chart_spec(chart_source[[c["x"], *y_cols]].head(MAX_CHART_ROWS), c.get("type") or "bar", title)
    return None


def _ensure_label_column(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """고른 열이 숫자뿐이면 항목 이름(문자열) 열을 앞에 붙인다.

    LLM이 표에 보여줄 열을 고르다 이름 열을 빼면 행이 어느 항목인지 알 수 없는 숫자 표가 된다
    (2026-10-01, 단가 표에서 상품명이 빠진 사례). 숫자 열만 골랐고 df에 문자열 열이 있으면 그 첫 열을 넣는다.
    """
    if not cols or any(not pd.api.types.is_numeric_dtype(df[c]) for c in cols):
        return cols
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            return [c] + cols
    return cols


def _with_required(df: pd.DataFrame, cols: list[str], required) -> list[str]:
    """LLM이 고른 열에 모듈이 필수로 정한 열을 합친다(df의 열 순서 유지).

    모듈이 만든 결과 열 중 문장이 읽는 핵심 열이 표에서 빠지면 표와 문장이 서로 다른 숫자를 말하게 된다
    (단가 효과 표에 총 증감만 보이고 문장은 단가 효과 값을 쓴 사례). required는 열 이름 목록이거나
    "all"(전체)이다. 이름은 모듈이 직접 계산해 붙인 열의 이름이며 사용자 데이터 컬럼명이 아니다.
    """
    if not required:
        return cols
    wanted = set(df.columns) if required == "all" else {c for c in required if c in df.columns}
    keep = wanted | set(cols)
    return [c for c in df.columns if c in keep]


def _drop_uninformative(df: pd.DataFrame, cols: list[str], required) -> list[str]:
    """표에 보여줄 열에서 정보가 없는 열을 뺀다 — 값이 전부 비었거나 한 가지뿐인 열, 0/1(참/거짓) 표시만 있는 열.

    모듈이 계산 중간에 쓰는 표시 열(신규·이탈 표시, 주요 항목 여부 등)이 표에 그대로 나와 헤더만 여러 줄을
    차지하고 값은 비어 있거나 전부 같은 사례가 있었다(2026-10-14). 열 이름은 보지 않고 값의 모양만 본다.
    required에 든 열은 남긴다. cols가 비면(LLM이 열을 안 골랐으면) 전체 열이 대상이다. 행이 3개 미만이면
    값이 하나뿐인 것이 당연하므로 손대지 않는다.
    """
    base = list(cols) if cols else list(df.columns)
    if len(df) < 3:
        return cols
    keep = set(df.columns) if required == "all" else set(required or [])
    out: list[str] = []
    for c in base:
        if c in keep:
            out.append(c)
            continue
        s = df[c].dropna()
        if s.empty or s.astype(str).str.strip().eq("").all() or s.nunique() <= 1:
            continue
        if set(s.unique()) <= {0, 1, True, False}:
            continue
        out.append(c)
    return out or cols


def _facts_block(table: pd.DataFrame, extra_facts: dict | None) -> str:
    """프롬프트에 붙일 값: 표에서 pandas가 계산한 값 + 모듈이 전체 데이터에서 계산해 넘긴 값(둘 다 키: 값)."""
    block = df_facts(table)
    if extra_facts:
        block += "\n[추가 값 — 모듈이 전체 데이터에서 계산한 값(JSON)]\n" + facts_json(extra_facts)
    return block


def _verify_numbers(prompt: str, system: str, narrative: str, summary: str, *, label: str, call_type: str):
    """해설·요약의 숫자가 프롬프트에 준 자료에 있는지 확인한다. 없으면 한 번 다시 쓰게 하고, 그래도
    남으면 그 문장을 뺀다. 반환: (narrative, summary, 처음 감지된 근거 없는 숫자 목록)."""
    allowed = number_check.build_allowed(prompt)
    bad = number_check.find_unverified(narrative, allowed)
    bad += [b for b in number_check.find_unverified(summary, allowed) if b not in bad]
    if not bad:
        return narrative, summary, []
    first = list(bad)
    feedback = (
        "[숫자 검증 실패] 아래 숫자는 위 자료(표·계산된 사실·한글 단위 참고표)에 없다: "
        + ", ".join(bad)
        + "\n자료에 있는 값으로 바꾸거나 그 문장을 빼서, 같은 JSON 형식으로 다시 답하라. 새 수치를 만들지 마라."
    )
    try:
        text = chat(
            [{"role": "user", "content": prompt},
             {"role": "assistant", "content": json.dumps({"narrative": narrative, "summary": summary}, ensure_ascii=False)},
             {"role": "user", "content": feedback}],
            grade="balanced", system=system, label=f"{label}:renumber", call_type=call_type,
        )
        redo = _parse_json(text)
        n2, s2 = str(redo.get("narrative") or "").strip(), str(redo.get("summary") or "").strip()
        redo_bad = number_check.find_unverified(n2, allowed) + number_check.find_unverified(s2, allowed)
        if n2 and len(redo_bad) <= len(bad):
            narrative, summary = n2, s2 or summary
    except Exception as e:
        log.warning("[number_check:%s] 다시 쓰기 실패: %s", label, e)
    narrative, _ = number_check.enforce(narrative, allowed, label=f"{label}:narrative")
    summary, _ = number_check.enforce(summary, allowed, label=f"{label}:summary")
    log.warning("[number_check:%s] 근거 없는 숫자 %d개 처리: %s", label, len(first), first)
    return narrative, summary, first


def render_from_dataframe(
    df: pd.DataFrame | None, *, purpose: str, narrative_hint: str, params: dict,
    label: str = "", empty_summary: str = "해당 조건에 표시할 데이터가 없습니다.",
    chart_df: pd.DataFrame | None = None, cache: dict | None = None,
    columns: dict | None = None,
    required_columns=None, extra_facts: dict | None = None,
) -> Render:
    """계산이 끝난 DataFrame → LLM이 표 열·차트·서술을 고른 Render.

    chart_df: 표와 차트가 서로 다른 단위(예: 표는 차원별 집계, 차트는 개별 항목)일 때만
    지정한다 — 지정하면 차트 후보 열은 df 대신 이 DataFrame에서 고른다.

    columns: {열이름: 뜻} — 이 표에만 해당하는 임시 메타. 등록 메타를 고치지 않는다.
    계산으로 만든 열은 이름만으로 뜻이 안 통하므로 모듈이 붙여 보낸다(column_notes 참조).

    required_columns: 표에 반드시 보일 열(모듈이 만든 결과 열 이름 목록, 또는 "all"). LLM이 열을 골라도
    이 열은 빠지지 않는다 — 문장이 읽은 열과 표에 보이는 열이 어긋나는 것을 막는다.

    extra_facts: 표에 안 보이는 전체 데이터에 대해 모듈이 계산한 값 {키: 값}(예: 전체 항목 수, 비중의
    분모 이름과 값). 키는 값의 뜻이 그것만 보고 분명해야 한다. LLM이 보이는 행만 보고 전체를 일반화하거나
    비중의 분모를 짐작하지 않게 근거로 준다. 문장이 아니라 값만 넘긴다.

    cache: 정기 보고서 재실행용 — 이전에 이 함수가 고른 표열·차트 구성(Render.llm_spec)을
    그대로 주면 그 구성(형식)만 재사용하고 LLM에 다시 묻지 않는다. 서술(narrative/summary)은
    형식이 아니라 그 회차 값에 대한 해석이므로 캐시하지 않는다 — 매번 새 값을 보여주고 다시
    쓰게 한다(구조 선택 없이 해설만 쓰는 좁은 프롬프트라 구조까지 새로 고르는 것보다 가볍다).
    """
    if df is None or df.empty:
        return Render(summary=empty_summary)

    calc_spec = cache.get("calc") if cache else _decide_calc(df, purpose, narrative_hint, label)
    df, calc_notes = _apply_calc(df, calc_spec)

    describe_notes = cache.get("describe") if cache else _describe_columns(df, purpose, narrative_hint, label)
    columns = {**(columns or {}), **calc_notes, **(describe_notes or {})}

    chart_source = chart_df if chart_df is not None else df

    if cache:
        cols = [c for c in (cache.get("table_columns") or []) if c in df.columns]
        cols = _drop_uninformative(df, _with_required(df, cols, required_columns), required_columns)
        cols = _ensure_label_column(df, cols)
        table = df[cols] if cols else df
        chart = _build_chart(cache.get("chart"), chart_source, purpose)

        sample = table.head(MAX_SAMPLE_ROWS)
        prompt = (
            f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint or '-'}\n"
            f"[파라미터] {json.dumps(params, ensure_ascii=False, default=str)}\n"
            + column_notes(table, columns)
            + f"[표]\n{table_to_markdown(sample)}"
            + (f"\n(전체 {len(table):,}행 중 {MAX_SAMPLE_ROWS}행만 표시 — 요약은 전체 기준으로 서술)"
               if len(table) > MAX_SAMPLE_ROWS else "")
            + _facts_block(table, extra_facts)
        )
        n_spec = _chat_json(prompt, _NARRATIVE_SYSTEM, label=f"{label}:narrative", call_type="module_narrative")
        narrative = str(n_spec.get("narrative") or "").strip()
        summary = str(n_spec.get("summary") or "").strip()
        narrative, summary, unverified = _verify_numbers(
            prompt, _NARRATIVE_SYSTEM, narrative, summary, label=label, call_type="module_narrative")
        # llm_spec은 구조(표열·차트)만 다음 회차로 넘긴다 — 서술은 캐시 대상이 아니므로 저장하지 않는다.
        out_spec = {"table_columns": cache.get("table_columns"), "chart": cache.get("chart"),
                    "calc": cache.get("calc"), "describe": cache.get("describe"), "unverified": unverified}
        return Render(summary=summary or narrative or empty_summary, table=table, chart=chart,
                     narrative=narrative or None, llm_spec=out_spec)

    sample = df.head(MAX_SAMPLE_ROWS)
    prompt = (
        f"[분석 목적] {purpose}\n[서술 지침] {narrative_hint or '-'}\n"
        f"[파라미터] {json.dumps(params, ensure_ascii=False, default=str)}\n"
        + column_notes(df, columns)
        + f"[데이터]\n{table_to_markdown(sample)}"
        + (f"\n(전체 {len(df):,}행 중 {MAX_SAMPLE_ROWS}행만 표시 — 요약은 전체 기준으로 서술)"
           if len(df) > MAX_SAMPLE_ROWS else "")
        + (f"\n[차트용 데이터 열 목록] {list(chart_source.columns)}(차트는 이 열 중에서 고른다)"
           if chart_df is not None else "")
        + _facts_block(df, extra_facts)
    )
    spec = _chat_json(prompt, _RENDER_SYSTEM, label=f"{label}:render", call_type="module_render")

    cols = [c for c in (spec.get("table_columns") or []) if c in df.columns]
    cols = _drop_uninformative(df, _with_required(df, cols, required_columns), required_columns)
    cols = _ensure_label_column(df, cols)
    table = df[cols] if cols else df
    chart = _build_chart(spec.get("chart"), chart_source, purpose)

    narrative = str(spec.get("narrative") or "").strip()
    summary = str(spec.get("summary") or "").strip()
    narrative, summary, unverified = _verify_numbers(
        prompt, _RENDER_SYSTEM, narrative, summary, label=label, call_type="module_render")
    spec["unverified"] = unverified
    spec["calc"] = calc_spec
    spec["describe"] = describe_notes
    return Render(summary=summary or narrative or empty_summary, table=table, chart=chart,
                 narrative=narrative or None, llm_spec=spec)
