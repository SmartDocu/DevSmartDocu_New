"""업로드 파일의 meta_columns 생성 — 엔진(ROLE_* 기반 모듈)이 업로드 데이터에서도 돌게 한다.

두 경로 (2026-07-20 결정)
  (1) 사용자가 메타 정의(JSON)를 파일과 함께 올림
      → datasource.definition_to_meta_columns()로 그대로 파싱한다. LLM을 쓰지 않으므로
        DB 데이터소스(datasources/*.json)와 신뢰도가 같다.
  (2) 파일만 올라옴 (메타 없음)
      → 이 모듈이 컬럼명·dtype·표본 행을 LLM에 보여 역할을 추론한다. **DB 쪽 손 작성 정의보다
        부정확할 수 있음을 감안한다** — 결과에 신뢰도 낮음을 숨기지 않고 `_warnings`로 남긴다
        (§11 Step 2, 조용히 넘기지 않는다).

**excel_server.py의 _generate_dataset_metadata()와는 목적이 다르다.** 그건 "이 컬럼이 무슨 뜻인지"
한글 설명만 만들어 단발 질문(execute_excel_query)의 pandas 코드 생성을 돕는다 — 역할이 필요 없다
(매 질문마다 LLM이 새로 코드를 쓰므로). 여기는 "이 컬럼이 amount/quantity/item/party/period 중
무엇인지"를 정해, 새 엔진 모듈(kpi_alert·pnl_summary 등, LLM 없이 파이썬이 직접 계산)이 쓰게
한다. 목적이 달라 함수를 분리한다 — 기존 단발 질문 경로는 이 모듈이 생기기 전과 똑같이 동작한다.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from d2insight.engine.datasource import definition_to_meta_columns
from d2insight.engine.schema import (
    ROLE_AMOUNT, ROLE_DISCOUNT, ROLE_ITEM, ROLE_ITEM_GROUP, ROLE_PARTY,
    ROLE_PERIOD, ROLE_QUANTITY,
)
from d2insight.engine._llm import chat

_VALID_ROLES = {ROLE_AMOUNT, ROLE_QUANTITY, ROLE_DISCOUNT, ROLE_ITEM,
                ROLE_ITEM_GROUP, ROLE_PARTY, ROLE_PERIOD}


class RoleInferenceError(Exception):
    """LLM 역할 추론이 실패하거나 응답을 해석할 수 없는 경우. 조용히 빈 정의로 넘기지 않는다."""


def infer_definition(df: pd.DataFrame, dataset_name: str = "업로드 데이터",
                     provider: str | None = None) -> dict:
    """컬럼명·dtype·표본 행을 보고 LLM이 역할 매핑을 추론해 datasources/*.json과 같은 형태로 돌려준다.

    반환: {"columns": [...], "_inferred": True, "_warnings": [...]}
      _inferred=True로 손 작성 정의와 구분한다 — 신뢰도가 다르다는 사실을 지우지 않는다.
      _warnings에는 amount 역할을 못 찾았거나 여럿인 경우 등을 남긴다.
    """
    columns = list(df.columns.astype(str))
    dtypes = {c: str(t) for c, t in zip(columns, df.dtypes)}
    sample = df.head(5).to_dict(orient="records")

    prompt = f"""다음은 "{dataset_name}" 데이터셋의 정보다.

컬럼: {columns}
컬럼별 데이터 타입: {dtypes}
샘플 데이터(최대 5행): {json.dumps(sample, ensure_ascii=False, default=str)}

각 컬럼이 분석에서 어떤 역할을 하는지 판단해 아래 JSON으로만 답하라(설명 금지).

역할(semantic) 후보 — 해당 없으면 빈 문자열로 둘 것:
  amount      : 금액(합산 가능한 거래 금액). 단가처럼 합산하면 안 되는 값은 이 역할을 주지 말 것.
  quantity    : 수량(합산 가능)
  discount    : 할인·에누리액
  item        : 분석의 최소 단위가 되는 항목(상품명·품목명 등)
  item_group  : item의 상위 분류(카테고리 등)
  party       : 거래 상대(고객·거래처 등)
  period      : 날짜/기간 컬럼

{{
  "columns": [
    {{"physical": "실제컬럼명", "logical": "한글 표시명", "field_type": "Measure 또는 Dim",
      "is_key_measure": true 또는 false, "semantic": "위 후보 중 하나 또는 빈 문자열"}}
  ]
}}

핵심 규칙:
  - amount 역할은 반드시 1개만 골라라(후보가 여럿이면 가장 대표적인 거래 금액 하나만).
  - is_key_measure=true는 amount 역할을 받은 컬럼에만 줘라.
  - 확신이 없는 역할은 억지로 채우지 말고 빈 문자열로 둬라.
  - field_type="Measure"는 **여러 행에 걸쳐 그대로 합산(SUM)된다.** 단가·평균·비율처럼
    합산하면 의미가 없어지는 값은 semantic뿐 아니라 field_type도 "Measure"가 아니라
    "Dim"으로 표시해라(숫자여도 집계 대상이 아니라는 뜻이다).
  - columns 배열에는 입력으로 받은 컬럼 전부를 빠짐없이 포함해라(역할이 없어도 포함)."""

    text = chat(
        [{"role": "user", "content": prompt}],
        grade="balanced",
        system="You infer column semantic roles for a tabular dataset. Output JSON only.",
        max_tokens=4096,
        label="업로드 데이터 역할 추론",
        provider=provider,
    )

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    json_str = match.group(1) if match else text.strip()
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RoleInferenceError(f"LLM 응답을 JSON으로 해석하지 못했습니다: {e}\n응답: {text[:500]}")

    cols = parsed.get("columns")
    if not isinstance(cols, list) or not cols:
        raise RoleInferenceError(f"LLM 응답에 columns 목록이 없습니다: {text[:500]}")

    warnings: list[str] = []
    seen_physical = {c.get("physical") for c in cols}
    missing = [c for c in columns if c not in seen_physical]
    if missing:
        warnings.append(f"LLM 응답에서 누락된 컬럼: {missing} (역할 없이 분석 차원으로만 쓰입니다)")

    amount_cols = [c["physical"] for c in cols if c.get("semantic") == ROLE_AMOUNT]
    if not amount_cols:
        warnings.append("금액(amount) 역할을 찾지 못했습니다 — 총평·손익 등 금액 기반 분석이 불가합니다.")
    elif len(amount_cols) > 1:
        warnings.append(f"금액(amount) 역할 후보가 여럿입니다({amount_cols}) — 판단에 오류가 있을 수 있습니다.")

    for c in cols:
        role = c.get("semantic")
        if role and role not in _VALID_ROLES:
            warnings.append(f"컬럼 '{c.get('physical')}'에 알 수 없는 역할 '{role}' — 무시합니다.")
            c["semantic"] = ""

    return {"columns": cols, "_inferred": True, "_warnings": warnings, "_dataset_name": dataset_name}


def resolve_upload_meta_columns(
    df: pd.DataFrame,
    user_definition: dict | None = None,
    dataset_name: str = "업로드 데이터",
    provider: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """업로드 파일의 meta_columns를 만든다 — 사용자 정의가 있으면 그것을, 없으면 LLM 추론을 쓴다.

    반환: (meta_columns DataFrame, info)
      info = {"source": "user_provided" | "llm_inferred", "warnings": [...]}
      warnings가 있어도 meta_columns는 만들어진다 — 판단은 호출부(보고서 상단 안내 등)에 맡긴다.
    """
    columns = list(df.columns.astype(str))

    if user_definition:
        meta = definition_to_meta_columns(user_definition, dataset_name, columns)
        return meta, {"source": "user_provided", "warnings": []}

    definition = infer_definition(df, dataset_name, provider=provider)
    meta = definition_to_meta_columns(definition, dataset_name, columns)
    return meta, {"source": "llm_inferred", "warnings": definition.get("_warnings", [])}
