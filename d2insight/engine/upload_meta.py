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

import builtins
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
    {{"physical": "실제컬럼명", "logical": "한글 표시명", "field_type": "Measure 또는 Dim 또는 Exclude",
      "is_key_measure": true 또는 false, "semantic": "위 후보 중 하나 또는 빈 문자열",
      "is_market_axis": true 또는 false}}
  ],
  "period_combine": {{"source_columns": ["실제컬럼명", ...], "expression": "pandas 표현식"}} 또는 null
}}

field_type 판단 기준 (셋 중 하나):
  - Measure: 여러 행에 걸쳐 그대로 합산(SUM)해도 의미가 있는 숫자다(판매금액, 수량 등).
  - Dim: 여러 행이 같은 값을 공유하며, 그 값으로 묶어서 서로 비교하는 진짜 카테고리다
    (브랜드, 지역, 채널 등 — "브랜드별 매출 비교" 같은 분석의 기준이 되는 컬럼).
  - Exclude: 숫자이지만 합산하면 의미가 없어지는 값이다(단가·평균·비율·마진율 등).
    **이런 값을 Dim으로 표시하지 마라** — Dim은 "묶어서 비교하는 카테고리"라는 뜻이라,
    비율값을 Dim으로 표시하면 "마진율 0.17"처럼 숫자 하나하나가 카테고리 항목으로
    잘못 취급된다. 합산도 안 되고 카테고리도 아니면 반드시 Exclude로 표시해라 — 이런
    컬럼은 분석에서 아예 제외된다(의도된 동작이다).
  - **컬럼 이름과 실제 샘플 값이 서로 안 맞으면, 이름이 아니라 실제 값을 기준으로
    판단해라.** 예: 컬럼 이름이 "~금액"인데 샘플 값이 계정ID·이메일 주소·URL 같은
    문자열이면, 그건 금액 컬럼이 아니다 — field_type을 "Exclude"로 표시해라(이런
    컬럼을 Dim으로 표시하면 "포스판매금액: webddle04@kakao.com"처럼 이메일 주소가
    분석 항목으로 잘못 등장한다). 이름만 보고 짐작하지 말고, 반드시 샘플 데이터를
    실제로 확인해서 판단해라.

is_market_axis (field_type이 Dim인 컬럼에만 해당, 그 외는 true로 둬도 무방):
  - true: 브랜드·지역·채널·상품·고객처럼 "무엇이 어떻게 팔렸나"를 나타내는 축 —
    매출 변화의 원인으로 볼 수 있다.
  - false: 법인·부서·사업부처럼 회사 내부 관리/회계용 구분 — 매출이 왜 변했는지의
    "원인"이라기보다 "집계 방식"에 가깝다. 이런 컬럼은 원인분석에서는 빠지지만
    현황 서술(예: "법인별 매출")에는 계속 쓰이니 field_type/semantic은 그대로 판단하고
    is_market_axis만 false로 표시해라.

핵심 규칙:
  - amount 역할은 반드시 1개만 골라라(후보가 여럿이면 가장 대표적인 거래 금액 하나만).
  - is_key_measure=true는 amount 역할을 받은 컬럼에만 줘라.
  - 확신이 없는 역할은 억지로 채우지 말고 빈 문자열로 둬라.
  - columns 배열에는 입력으로 받은 컬럼 전부를 빠짐없이 포함해라(역할이 없어도 포함).

period_combine 규칙(날짜/시각 정보가 pandas가 바로 못 읽는 형태일 때):
  - 날짜/시각 정보가 한 컬럼에 온전한 형태로 없으면(예: 년/월이 따로 있거나, 년/월/일/시/분이
    나뉘어 있거나, "20250101"처럼 pandas가 못 읽는 표기 하나뿐이거나) "period_combine"에
    그 컬럼들을 합쳐 하나의 날짜(또는 일시) 값을 만드는 **pandas 표현식 하나**를 적어라.
    표현식은 df만 참조하며 대입문이 아니라 값 하나를 만드는 식이어야 한다
    (예: pd.to_datetime(df['년'].astype(str) + df['월'].astype(str).str.replace('월','').str.zfill(2), format='%Y%m')).
  - 시(時)·분(分)·초(秒) 컬럼이 있으면 반드시 결과에 포함시켜라 — 날짜만 만들고 시각을
    버리지 마라. 나중에 시간 단위 분석에 쓰일 수 있다.
  - 이미 pandas가 바로 읽을 수 있는 온전한 날짜/일시 컬럼이 하나 있으면 "period_combine"은
    null로 두고, 그 컬럼에 semantic="period"를 줘라.
  - period_combine을 채웠으면, 그 근거가 된 원본 컬럼들(source_columns)의 semantic은
    비워둬라(기간 역할은 새로 만들어질 결합 컬럼이 대신 받는다, 코드가 자동 처리)."""

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

    period_combine = parsed.get("period_combine")
    if not (isinstance(period_combine, dict) and period_combine.get("expression")):
        period_combine = None

    return {
        "columns": cols, "_inferred": True, "_warnings": warnings,
        "_dataset_name": dataset_name, "_period_combine": period_combine,
    }


_FORBIDDEN_EXPR_PATTERNS = ("import", "__", "open(", "exec(", "eval(", "os.", "sys.", "subprocess", ";")


def _combine_period_columns(df: pd.DataFrame, expression: str) -> pd.Series:
    """LLM이 만든 단일 pandas 표현식을 제한된 이름공간에서 평가해 기간 Series를 만든다.

    eval()은 표현식만 받고 대입문·복수문은 애초에 SyntaxError이므로 df를 직접 바꾸는
    코드는 여기서 실행될 수 없다 — 값 하나만 받아 새 컬럼에 대입하는 건 호출부의 몫이다.
    """
    if any(p in expression for p in _FORBIDDEN_EXPR_PATTERNS):
        raise RoleInferenceError(f"기간 결합 표현식에 허용되지 않는 구문이 있습니다: {expression}")
    safe_builtins = {n: getattr(builtins, n) for n in ("str", "int", "float", "len", "round", "min", "max", "abs")}
    namespace = {"df": df, "pd": pd}
    try:
        result = eval(expression, {"__builtins__": safe_builtins}, namespace)
    except Exception as e:
        raise RoleInferenceError(f"기간 결합 표현식 실행 실패: {type(e).__name__}: {e}\n표현식: {expression}")
    return pd.to_datetime(result, errors="coerce")


_GROUPABLE_MAX_UNIQUE_RATIO = 0.5  # 서로 다른 값의 비율이 이보다 크면 "차원"으로 묶어 비교할 수 없다고 본다


def _mark_ungroupable_dims(df: pd.DataFrame, columns: list[dict]) -> list[str]:
    """역할이 없는 Dim 컬럼 중 값이 행마다 거의 다 달라(예: 금액·비율) 묶어서 비교할 항목이
    없는 것을 차원 후보에서 뺀다(is_groupable=False, 제자리 수정). item/party/item_group/
    region처럼 이미 역할이 붙은 컬럼은 값이 많아도(고객명 등) 대상에서 뺀다 — 역할 자체가
    "이건 분석 차원이다"라는 선언이기 때문이다. 반환: 제외된 컬럼명 목록.
    """
    n_rows = len(df)
    excluded = []
    if n_rows == 0:
        return excluded
    for col in columns:
        if col.get("field_type") != "Dim" or col.get("semantic"):
            continue
        physical = col.get("physical")
        print(f"[DEBUG-mark-ungroupable] physical={physical!r} in df.columns={physical in df.columns}")  # jeff
        if physical not in df.columns:
            continue
        ratio = df[physical].nunique(dropna=True) / n_rows
        print(f"[DEBUG-mark-ungroupable]   nunique/n_rows={ratio!r} (threshold={_GROUPABLE_MAX_UNIQUE_RATIO})")  # jeff
        if ratio > _GROUPABLE_MAX_UNIQUE_RATIO:
            col["is_groupable"] = False
            excluded.append(physical)
    return excluded


def resolve_upload_meta_columns(
    df: pd.DataFrame,
    user_definition: dict | None = None,
    dataset_name: str = "업로드 데이터",
    provider: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """업로드 파일의 meta_columns를 만든다 — 사용자 정의가 있으면 그것을, 없으면 LLM 추론을 쓴다.

    날짜/시각이 여러 컬럼에 나뉘어 있거나 pandas가 못 읽는 표기면(LLM이 판단, "period_combine"),
    그 컬럼들을 합친 새 기간 컬럼을 df에 **제자리 추가**한다 — 호출부가 넘긴 df 객체가
    그대로 바뀐다(별도 반환하지 않는 이유: 세션에 저장된 df와 같은 객체라 이미 반영됨).

    반환: (meta_columns DataFrame, info)
      info = {"source": "user_provided" | "llm_inferred", "warnings": [...]}
      warnings가 있어도 meta_columns는 만들어진다 — 판단은 호출부(보고서 상단 안내 등)에 맡긴다.
    """
    columns = list(df.columns.astype(str))

    if user_definition:
        meta = definition_to_meta_columns(user_definition, dataset_name, columns)
        return meta, {"source": "user_provided", "warnings": []}

    definition = infer_definition(df, dataset_name, provider=provider)

    print("[DEBUG-upload-meta] infer_definition 분류 결과:")  # jeff
    for _c in definition["columns"]:  # jeff
        print(f"[DEBUG-upload-meta]   physical={_c.get('physical')!r} "  # jeff
              f"field_type={_c.get('field_type')!r} semantic={_c.get('semantic')!r}")  # jeff

    excluded_dims = _mark_ungroupable_dims(df, definition["columns"])

    print(f"[DEBUG-upload-meta] _mark_ungroupable_dims 제외 목록: {excluded_dims}")  # jeff
    for _c in definition["columns"]:  # jeff
        if _c.get("field_type") == "Dim":  # jeff
            print(f"[DEBUG-upload-meta]   [Dim] physical={_c.get('physical')!r} "  # jeff
                  f"semantic={_c.get('semantic')!r} is_groupable={_c.get('is_groupable', True)!r}")  # jeff

    if excluded_dims:
        definition["_warnings"].append(
            f"값이 거의 다 달라 항목별로 묶어 비교할 수 없는 컬럼은 분석 차원에서 뺐습니다: "
            f"{', '.join(excluded_dims)}."
        )

    combine = definition.get("_period_combine")
    if combine:
        try:
            period_series = _combine_period_columns(df, combine["expression"])
            new_col = "_resolved_period"
            while new_col in df.columns:
                new_col = f"{new_col}_2"
            df[new_col] = period_series
            invalid_n = int(period_series.isna().sum())
            note = f"'{', '.join(combine.get('source_columns') or [])}' 컬럼을 합쳐 기간 컬럼을 만들었습니다."
            if invalid_n:
                note += f" ({invalid_n:,}행은 값을 해석하지 못해 제외됩니다.)"
            definition["_warnings"].append(note)
            definition["columns"].append({
                "physical": new_col, "logical": "기간(자동 결합)",
                "field_type": "Dim", "is_key_measure": False, "semantic": ROLE_PERIOD,
            })
            # 기간 결합에 쓰인 원본 컬럼(예: 년/월)은 분석기간·비교기간을 가르는 축 그
            # 자체라, 일반 차원으로 남겨두면 "월이 변화의 97.8%를 설명한다"처럼 당연한
            # 사실(기간이 다르다는 것)이 원인 분석 결과인 것처럼 세 분석 모듈(변동원인분석·
            # 이상징후·교차드릴다운, 전부 schema.dimensions를 공유)에 섞여 나온다
            # (2026-08-26 확인). 분석 후보에서 제외한다.
            source_cols = set(combine.get("source_columns") or [])
            for _col in definition["columns"]:
                if _col.get("physical") in source_cols:
                    _col["field_type"] = "Exclude"
            columns = list(df.columns.astype(str))
        except RoleInferenceError as e:
            definition["_warnings"].append(f"기간 컬럼 결합 실패: {e}")

    meta = definition_to_meta_columns(definition, dataset_name, columns)
    return meta, {"source": "llm_inferred", "warnings": definition.get("_warnings", [])}
