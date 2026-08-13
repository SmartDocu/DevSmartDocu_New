"""
excel_code_engine.py
업로드된 DataFrame에 대해 LLM이 짧은 pandas 코드를 생성해 실행하는 경량 엔진.
d2chat·d2insight 공용 — DB 의존 없음.
"""
import re
import json
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from d2shared.llm_logger import log_llm_call


# dtype 안전 규칙 텍스트
PROMPT_DTYPE_SAFETY_RULES = """
파이썬 코드 처리:
    - 중요 : 파이썬 명령이 실행될 수 있는 코드로 작성
    - 결과 예시 등은 작성하지 않습니다.
        - 이 부분이 코드에 들어가는 경우 반드시 주석 형태로 넣어주세요.

데이터 타입 처리:
    - 데이터 타입과 데이터를 사용할 수 있는 함수나 메소드가 일치되어야 합니다.
        - 예를 들면 데이터는 숫자인데 .str과 같은 메소드를 사용하는 일이 없어야 합니다.
    - 숫자 연산 전: pd.to_numeric(df['col'], errors='coerce')
    - 날짜 연산 전: pd.to_datetime(df['col'])
    - groupby().agg() 형식: Named aggregation(새컬럼명=('원본컬럼명', 집계함수))은 DataFrame의 agg()에서만 사용 가능합니다. Series의 agg()에서는 사용 불가능합니다.
"""


def fix_groupby_agg_pattern(code: str) -> str:
    """
    Series.agg()의 named aggregation 패턴을 자동으로 수정
    groupby('col')['col'].agg(name=('col', func)) -> groupby('col').agg(name=('col', func))
    """
    pattern = r"groupby\(([^)]+)\)\['([^']+)'\]\.agg\("
    replacement = r"groupby(\1).agg("
    fixed_code = re.sub(pattern, replacement, code)
    if fixed_code != code:
        # print("[AUTO FIX] groupby().agg() 패턴 자동 수정됨")
        pass
    return fixed_code


def fix_numeric_only_pattern(code: str) -> str:
    """
    object 타입 컬럼에 집계 함수 적용 시 발생하는 오류 방지.
    인자 없는 집계 호출에 numeric_only=True 추가.
    """
    agg_funcs = ['mean', 'sum', 'median', 'std', 'var']
    for func in agg_funcs:
        pattern = rf'\.{func}\(\)'
        replacement = rf'.{func}(numeric_only=True)'
        new_code = re.sub(pattern, replacement, code)
        if new_code != code:
            # print(f"[AUTO FIX] .{func}() → .{func}(numeric_only=True) 수정됨")
            pass
            code = new_code
    return code


FORBIDDEN_PATTERNS = [
    "import os", "import sys", "import subprocess", "import shutil", "import socket",
    "open(", "os.system", "os.popen", "os.remove", "os.rmdir",
    "subprocess", "socket", "requests", "urllib", "__import__",
    # 시각화는 visualization.py가 전담한다 (한글 폰트가 설정된 곳). 생성된 pandas 코드
    # 안에서 matplotlib을 직접 쓰면 폰트 미설정 상태로 그려져 한글 깨짐 경고가 발생하므로 차단.
    "matplotlib", ".plot(",
]


def _safe_identifier(key: str, used: set) -> str:
    """데이터셋 키를 exec 네임스페이스에 쓸 수 있는 파이썬 변수명으로 변환 (충돌 시 접미사 추가)"""
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", str(key))
    if not ident or ident[0].isdigit():
        ident = f"ds_{ident}"
    base = ident
    i = 2
    while ident in used:
        ident = f"{base}_{i}"
        i += 1
    used.add(ident)
    return ident


def _build_var_names(dfs: Dict[str, pd.DataFrame]) -> Dict[str, str]:
    """{데이터셋 키: df} -> {데이터셋 키: 안전한 파이썬 변수명}"""
    used: set = set()
    return {key: _safe_identifier(key, used) for key in dfs}


def _build_prompt(
    dfs: Dict[str, pd.DataFrame],
    var_names: Dict[str, str],
    columns_by_dataset: Dict[str, Dict],
    question: str,
    current_date_info: Optional[Dict],
    relations: Optional[List[Dict]] = None,
    category_values_by_dataset: Optional[Dict[str, Dict[str, List[str]]]] = None,
    meta_by_dataset: Optional[Dict[str, Dict]] = None,
) -> str:
    category_values_by_dataset = category_values_by_dataset or {}
    meta_by_dataset = meta_by_dataset or {}
    dataset_sections = []
    for key, df in dfs.items():
        var = var_names[key]
        columns = list(df.columns)
        dtypes = {col: str(df[col].dtype) for col in columns}
        sample = df.head(3).to_dict(orient="records")
        col_desc = columns_by_dataset.get(key) or {c: c for c in columns}
        category_values = category_values_by_dataset.get(key) or {}
        category_text = ""
        if category_values:
            category_text = (
                f"\n- 범주형 컬럼의 실제 값(전체 목록, 이 값 외에는 존재하지 않음): "
                f"{json.dumps(category_values, ensure_ascii=False)}"
            )

        meta = meta_by_dataset.get(key) or {}
        extra_lines = []
        if meta.get("grain"):
            extra_lines.append(f"- 행 단위(grain): {meta['grain']}")
        if meta.get("primary_key"):
            extra_lines.append(f"- 행을 유일하게 식별하는 컬럼(primary_key, 추정): {meta['primary_key']}")
        extra_text = ("\n" + "\n".join(extra_lines)) if extra_lines else ""

        dataset_sections.append(f"""데이터셋 "{key}" (변수명: `{var}`)
- 컬럼: {columns}
- dtype: {dtypes}
- 컬럼 설명(컬럼명 -> 설명): {json.dumps(col_desc, ensure_ascii=False)}
- 샘플 데이터(최대 3행, 일부 값 종류가 여기 없을 수 있음): {json.dumps(sample, ensure_ascii=False, default=str)}{category_text}{extra_text}""")
    datasets_text = "\n\n".join(dataset_sections)

    relation_text = ""
    if relations:
        rel_lines = [
            f'- `{var_names.get(rel["left"], rel["left"])}`.{rel["left_on"]} <-> '
            f'`{var_names.get(rel["right"], rel["right"])}`.{rel["right_on"]}'
            for rel in relations
        ]
        relation_text = "\n\n**데이터셋 간 조인 가능한 컬럼(추정):**\n" + "\n".join(rel_lines)

    date_context = ""
    if current_date_info:
        date_context = f"""
현재 날짜 정보: {json.dumps(current_date_info, ensure_ascii=False)}
질문에 "어제", "오늘", "이번 달" 등이 있으면 위 날짜를 사용하세요. 질문에 특정 연도(예: "2026년")가 명시되어 있으면 그 연도로 먼저 필터링하세요.
"""

    multi_note = ""
    if len(dfs) > 1:
        multi_note = "\n- 여러 데이터셋이 주어졌습니다. 필요하면 위 조인 가능한 컬럼을 참고해 pd.merge()로 조인한 뒤 사용하세요."

    return f"""당신은 pandas 코드를 작성하는 데이터 분석가입니다.

이미 만들어진 pandas DataFrame(들):

{datasets_text}{relation_text}
{date_context}
질문:
"{question}"

작업:
- 위 데이터프레임 변수(들)를 사용해서 질문에 답하기 위한 데이터 가공(필터/조인/집계/정렬 등)을 수행하는 코드를 작성하세요.{multi_note}
- 최종 결과는 반드시 변수 `result`에 저장하세요. `result`는 pandas DataFrame이어야 합니다.
    - 여러 항목을 표/차트로 표현해야 하면 여러 행의 DataFrame
    - 단순 수치 하나로 답할 수 있는 질문이면 1행짜리 DataFrame (컬럼명은 질문 의미를 나타내는 한글 이름)
- **`result`에는 질문에서 명시적으로 요청한 지표만 포함하세요.** 예를 들어 "오류율을 그려주세요"라고 했으면 오류율 컬럼만 넣고, 참고가 될 것 같다는 이유로 오류 건수 같은 요청하지 않은 지표를 임의로 추가하지 마세요. 계산 과정에서 필요한 중간 컬럼(전체 건수 등)은 최종 `result`에서 제외하세요.
- 질문에 "그래프로", "차트로", "선그래프로" 같은 표현이 있어도, 여기서는 그림을 그리지 마세요. 당신이 할 일은 그래프에 쓰일 데이터를 `result` DataFrame으로 정확히 만드는 것뿐입니다. 실제 그래프 렌더링은 이 코드가 아니라 별도 시스템이 담당합니다.
- 컬럼의 실제 dtype을 추측하지 말고, 필요하면 pd.to_numeric/pd.to_datetime으로 변환하세요.
- 정규식(re.match, str.contains, str.extract 등)에 백슬래시가 들어간 패턴(숫자는 \\d, 공백은 \\s 등)을 쓸 때는 반드시 raw string(접두사 r)으로 작성하세요. 일반 문자열에 쓰면 SyntaxWarning이 발생합니다.
- 조인(merge)이나 그룹화 집계를 할 때는 각 데이터셋의 행 단위(grain)를 고려하세요. grain을 넘어서는 기준으로 조인하면 행이 중복되어 합계가 부풀려질 수 있습니다.
- 그룹별(예: 쇼핑몰별/브랜드별) 비율·증감률을 계산할 때는 반드시 groupby 등으로 각 그룹 자신의 분자·분모를 집계한 뒤 나누세요. 그룹화 없이 계산한 값이나 다른 그룹의 값을 실수로 재사용해서 여러 그룹의 결과가 우연히 동일한 값으로 나오지 않도록 주의하세요.
- "상위 5개", "하위 5개"처럼 순위/그룹을 나눠서 요청받아도, 그 구분을 "상위 1", "하위 3" 같은 새 문자열 라벨 컬럼으로 만들지 마세요. 브랜드/항목명은 그 컬럼 그대로 두고, 값 기준으로 정렬만 하면 순서 자체가 상위/하위를 나타냅니다. 굳이 구분이 필요하면 "구분"처럼 "상위"/"하위" 두 값만 갖는 별도 컬럼을 쓰고, 항목명과 합치지 마세요.
- 배송비율/광고비율/할인율처럼 비율(%) 지표로 "상위 N개"를 뽑을 때는 규모 왜곡에 주의하세요. 분모(매출/거래건수 등)가 아주 작은 항목은 우연히 비율이 극단적으로 높게 나와 별 의미 없는 항목이 최상단을 차지할 수 있습니다. 이런 요청에서는 비율만 정렬하지 말고, 그 비율의 분모가 되는 규모 지표(매출액, 거래건수 등)도 함께 result에 포함시켜서 사용자가 그 상위 항목이 실제로 의미 있는지 판단할 수 있게 하세요. 질문에 최소 규모 기준이 명시되지 않았다면 임의로 필터링하지 말고, 규모 지표를 같이 보여주는 것으로 판단 근거를 제공하세요.
- "수수료가 유독 높은 몰은 재협상해야 할지"처럼 실제 조치(재협상/예산 재배치 등)를 결정하는 질문이면, result의 정렬 기준을 비율(%) 자체가 아니라 그 비율의 절대 금액(예: 수수료액, 광고비 등)으로 하세요. 비율이 아무리 높아도 절대 금액이 작으면 조치할 실익이 작고, 비율이 낮아도 절대 금액이 크면 그게 실제 레버리지가 있는 대상입니다. 단순 현황 비교 질문(조치 여부를 묻지 않는 경우)이면 비율 정렬도 무방합니다.
- "월별" 집계를 요청받았을 때 데이터에 "년"(연도) 컬럼이 별도로 있고 "월" 컬럼 값이 "01월"~"12월"처럼 연도 구분 없이 반복되는 경우, 단순히 "월"로만 groupby하면 서로 다른 연도의 같은 월이 하나로 합쳐집니다. 질문에 특정 연도(예: "2026년")가 명시되어 있으면 먼저 그 연도로 필터링한 뒤 월별로 집계하고, 연도가 명시되지 않았다면 "년"과 "월"을 함께 groupby(또는 결과에 "년" 컬럼을 포함)하여 연도가 섞이지 않게 하세요.
{PROMPT_DTYPE_SAFETY_RULES}
범주형(상태/구분/등급 등) 컬럼 필터링 — 절대 규칙:
- 상태값/구분값 등으로 필터링할 때는 절대 값을 짐작하지 마세요. 위 "범주형 컬럼의 실제 값" 목록에 있는 정확한 문자열만 사용하세요.
- 필터링하려는 컬럼이 그 목록에 없다면(값 종류가 많은 컬럼), 짐작한 문자열로 == 비교하지 말고 실제 값을 코드 안에서 df[col].unique()로 먼저 확인한 뒤 사용하거나, 대소문자/공백 차이에 안전하도록 처리하세요.
- 필터링 결과가 0건이거나 전체 대비 비정상적으로 적으면, 짐작한 값이 실제 데이터에 존재하지 않아서일 수 있습니다. 그대로 0으로 답하지 말고 실제 컬럼 값들을 다시 확인해서 올바른 값으로 재시도하세요.

금지사항:
- 파일/네트워크/프로세스 접근 코드(open, os.system, subprocess, socket, requests 등) 절대 금지
- pandas(pd), numpy(np) 외의 라이브러리 import 금지
- matplotlib 등 그래프를 그리는 코드(plt.figure, plt.plot, .plot() 등) 절대 금지 — 이 코드의 역할은 `result` 데이터를 만드는 것까지입니다

**실행 가능한 Python 코드만** 반환하세요. 코드는 ```python 으로 시작하고 ``` 로 끝나야 합니다. 코드 밖에는 어떤 설명도 쓰지 마세요.

코드:"""


def _check_forbidden(code: str) -> Optional[str]:
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in code:
            return pattern
    return None


def _coerce_to_dataframe(result_obj) -> pd.DataFrame:
    if isinstance(result_obj, pd.DataFrame):
        return result_obj
    if isinstance(result_obj, pd.Series):
        return result_obj.to_frame().reset_index()
    if isinstance(result_obj, dict):
        return pd.DataFrame([result_obj])
    return pd.DataFrame([{"결과": result_obj}])


def run_pandas_code(
    llm,
    dfs: Dict[str, pd.DataFrame],
    question: str,
    columns_by_dataset: Optional[Dict[str, Dict]] = None,
    current_date_info: Optional[Dict] = None,
    relations: Optional[List[Dict]] = None,
    category_values_by_dataset: Optional[Dict[str, Dict[str, List[str]]]] = None,
    log_ctx: Optional[Dict] = None,
    meta_by_dataset: Optional[Dict[str, Dict]] = None,
) -> Dict:
    """
    LLM이 작성한 pandas 코드를 dfs(데이터셋 키 -> DataFrame)에 대해 실행하고 결과를 표준 형태로 반환한다.
    dfs가 2개 이상이면 relations(조인 힌트)를 프롬프트에 포함해 pd.merge()로 조인하도록 유도한다.
    category_values_by_dataset: {데이터셋 키: {컬럼명: [실제 고유값...]}} — 저카디널리티 컬럼의 실제
    값을 미리 알려줘서, 샘플 몇 행만 보고 상태/구분값 등을 잘못 짐작해 필터링하는 것을 방지한다.
    meta_by_dataset: {데이터셋 키: {"grain": ..., "primary_key": [...]}} — 조인/집계 시 중복 집계 방지.

    Returns:
        {"status": "success"|"no_data"|"error", "data": list[dict]|None, "code": str, "message": str}
    """
    columns_by_dataset = columns_by_dataset or {}
    var_names = _build_var_names(dfs)
    prompt = _build_prompt(
        dfs, var_names, columns_by_dataset, question, current_date_info, relations,
        category_values_by_dataset=category_values_by_dataset,
        meta_by_dataset=meta_by_dataset,
    )

    start = datetime.now()
    response = llm.invoke(prompt)
    end = datetime.now()

    usage = getattr(response, "usage_metadata", None) or {}
    log_llm_call(
        log_ctx=log_ctx,
        stepnm="excel_code_generate",
        steptitle="업로드 데이터 pandas 코드 생성",
        llmmodelnm=getattr(llm, "model", "unknown"),
        inputtoken=usage.get("input_tokens", 0),
        outputtoken=usage.get("output_tokens", 0),
        is_success=True,
        startdts=start,
        enddts=end,
    )

    code = response.content.strip()
    code = re.sub(r"^```python\s*", "", code)
    code = re.sub(r"^```\s*", "", code)
    code = re.sub(r"```\s*$", "", code)
    code = code.strip()

    forbidden = _check_forbidden(code)
    if forbidden:
        return {
            "status": "error",
            "data": None,
            "code": code,
            "message": f"허용되지 않는 코드 패턴이 감지되었습니다: {forbidden}",
        }

    code = fix_groupby_agg_pattern(code)
    code = fix_numeric_only_pattern(code)

    local_namespace = {"pd": pd, "np": np}
    for key, df in dfs.items():
        local_namespace[var_names[key]] = df.copy()

    try:
        exec(code, local_namespace)
    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "code": code,
            "message": f"코드 실행 오류: {str(e)}",
        }

    if "result" not in local_namespace:
        return {
            "status": "error",
            "data": None,
            "code": code,
            "message": "AI가 result 변수를 생성하지 않았습니다.",
        }

    result_df = _coerce_to_dataframe(local_namespace["result"])

    if result_df.empty:
        return {"status": "no_data", "data": [], "code": code, "message": "결과 데이터가 없습니다."}

    # inf/-inf(0으로 나누기 등)도 표준 JSON으로 표현할 수 없으므로 NaN과 함께 None으로 정리한다.
    # astype(object)로 먼저 바꾸지 않으면 float64 컬럼은 None을 다시 NaN으로 되돌린다.
    result_df = result_df.replace([np.inf, -np.inf], np.nan)
    result_df = result_df.astype(object).where(pd.notnull(result_df), other=None)
    for col in result_df.columns:
        if pd.api.types.is_datetime64_any_dtype(result_df[col]):
            result_df[col] = result_df[col].astype(str)

    data = result_df.to_dict(orient="records")

    return {"status": "success", "data": data, "code": code, "message": "데이터 처리 성공"}
