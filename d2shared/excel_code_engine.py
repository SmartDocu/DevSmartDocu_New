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
        print("[AUTO FIX] groupby().agg() 패턴 자동 수정됨")
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
            print(f"[AUTO FIX] .{func}() → .{func}(numeric_only=True) 수정됨")
            code = new_code
    return code


FORBIDDEN_PATTERNS = [
    "import os", "import sys", "import subprocess", "import shutil", "import socket",
    "open(", "os.system", "os.popen", "os.remove", "os.rmdir",
    "subprocess", "socket", "requests", "urllib", "__import__",
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
) -> str:
    category_values_by_dataset = category_values_by_dataset or {}
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
        dataset_sections.append(f"""데이터셋 "{key}" (변수명: `{var}`)
- 컬럼: {columns}
- dtype: {dtypes}
- 컬럼 설명(컬럼명 -> 설명): {json.dumps(col_desc, ensure_ascii=False)}
- 샘플 데이터(최대 3행, 일부 값 종류가 여기 없을 수 있음): {json.dumps(sample, ensure_ascii=False, default=str)}{category_text}""")
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
질문에 "어제", "오늘", "이번 달" 등이 있으면 위 날짜를 사용하세요.
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
- 컬럼의 실제 dtype을 추측하지 말고, 필요하면 pd.to_numeric/pd.to_datetime으로 변환하세요.
{PROMPT_DTYPE_SAFETY_RULES}
범주형(상태/구분/등급 등) 컬럼 필터링 — 절대 규칙:
- 상태값/구분값 등으로 필터링할 때는 절대 값을 짐작하지 마세요. 위 "범주형 컬럼의 실제 값" 목록에 있는 정확한 문자열만 사용하세요.
- 필터링하려는 컬럼이 그 목록에 없다면(값 종류가 많은 컬럼), 짐작한 문자열로 == 비교하지 말고 실제 값을 코드 안에서 df[col].unique()로 먼저 확인한 뒤 사용하거나, 대소문자/공백 차이에 안전하도록 처리하세요.
- 필터링 결과가 0건이거나 전체 대비 비정상적으로 적으면, 짐작한 값이 실제 데이터에 존재하지 않아서일 수 있습니다. 그대로 0으로 답하지 말고 실제 컬럼 값들을 다시 확인해서 올바른 값으로 재시도하세요.

금지사항:
- 파일/네트워크/프로세스 접근 코드(open, os.system, subprocess, socket, requests 등) 절대 금지
- pandas(pd), numpy(np) 외의 라이브러리 import 금지

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
) -> Dict:
    """
    LLM이 작성한 pandas 코드를 dfs(데이터셋 키 -> DataFrame)에 대해 실행하고 결과를 표준 형태로 반환한다.
    dfs가 2개 이상이면 relations(조인 힌트)를 프롬프트에 포함해 pd.merge()로 조인하도록 유도한다.
    category_values_by_dataset: {데이터셋 키: {컬럼명: [실제 고유값...]}} — 저카디널리티 컬럼의 실제
    값을 미리 알려줘서, 샘플 몇 행만 보고 상태/구분값 등을 잘못 짐작해 필터링하는 것을 방지한다.

    Returns:
        {"status": "success"|"no_data"|"error", "data": list[dict]|None, "code": str, "message": str}
    """
    columns_by_dataset = columns_by_dataset or {}
    var_names = _build_var_names(dfs)
    prompt = _build_prompt(
        dfs, var_names, columns_by_dataset, question, current_date_info, relations,
        category_values_by_dataset=category_values_by_dataset,
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

    result_df = result_df.where(pd.notnull(result_df), other=None)
    for col in result_df.columns:
        if pd.api.types.is_datetime64_any_dtype(result_df[col]):
            result_df[col] = result_df[col].astype(str)

    data = result_df.to_dict(orient="records")

    return {"status": "success", "data": data, "code": code, "message": "데이터 처리 성공"}
