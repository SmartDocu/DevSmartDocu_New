# 20250926

import io
import os
import sys
import re
import json
import warnings

import random
import string

from dotenv import load_dotenv
from dotenv import dotenv_values
from io import BytesIO
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import base64
from PIL import Image
from functools import partial

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableBranch 

from utilsPrj.crypto_helper import encrypt_value, decrypt_value
from utilsPrj.supabase_client import get_service_client, get_supabase_client, SUPABASE_SCHEMA


def process_data_in_supabase(supabase, table_name: str, process_type: str, process_data: dict, conditions: dict, columns: str="*"):

    query = supabase.schema(SUPABASE_SCHEMA) \
            .table(table_name)


    def process_conditions(query, conditions):
        for column, value in conditions.items():
            if value not in (None, ""):
                query = query.eq(column, value)
        return query
    
    if process_type == "select":
        query = query.select(columns)
        query = process_conditions(query, conditions)
    elif process_type == "update":
        query = query.update(process_data)
        query = process_conditions(query, conditions)
    elif process_type == "insert":
        query = query.insert(process_data)
    elif process_type == "delete":
        query = query.delete()
        query = process_conditions(query, conditions)

    data = query.execute()
    return data.data


def get_llm_model(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    if hasattr(request, "projectid"):
        project_id = request.projectid
        tenant_id = process_data_in_supabase(
            supabase, "projects", "select", {}, 
             {"projectid": project_id}, "tenantid"
        )[0]["tenantid"]
    else:
        user = request.session.get("user")
        if user:
            project_id = user.get("projectid")
            tenant_id = user.get("tenantid")
        else:
            tenant_id = process_data_in_supabase(
                supabase, "tenants", "select", {}, 
                {"tenantnm": "SmartDoc"}, "tenantid"
            )[0]["tenantid"]

            project_id = process_data_in_supabase(
                supabase, "projects", "select", {}, 
                {"tenantid": tenant_id, "projectnm": "public"}, "projectid"
            )[0]["projectid"]

    def fetch_llm_config(table_name, conditions):
        """테이블에서 LLM 설정 조회"""
        data = process_data_in_supabase(
            supabase, table_name, "select", {}, 
            conditions, "llmmodelnm, encapikey, tenantid"
        )
        return data[0]["llmmodelnm"], data[0]["encapikey"]

    llm_model, enc_api_key = fetch_llm_config("projects", {"projectid": project_id})
    if not llm_model:
        llm_model, enc_api_key = fetch_llm_config("tenants", {"tenantid": tenant_id})
        
        if not llm_model:
            llm_data = process_data_in_supabase(
                supabase, "llmmodels", "select", {},
                {"useyn": True}, "llmmodelnm, creator"
            )
            choice_model = random.choice(llm_data)
            llm_model = choice_model["llmmodelnm"]

            key_data = process_data_in_supabase(
                supabase, "llmapis", "select", {}, 
                {"usetypecd": "R", "llmmodelnm": llm_model}, "encapikey"
            )
            choice_key = random.choice(key_data)
            enc_api_key = choice_key["encapikey"]

    dec_api_key = decrypt_value(enc_api_key)

    llm_vendor_name = process_data_in_supabase(
        supabase, "llmmodels", "select", {},
        {'llmmodelnm': llm_model}, "llmvendornm"
    )[0]["llmvendornm"]

    if llm_vendor_name == "Anthropic":
        from anthropic import Anthropic
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            anthropic_api_key=dec_api_key,
            model=llm_model,
            temperature=0,
            max_tokens=8192
        )

    if llm_vendor_name == "OpenAI":
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=llm_model,
            api_key=dec_api_key,
            temperature=0,
            max_tokens=8192
        )
    
    elif llm_vendor_name == "Google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=llm_model,
            temperature=0,
            google_api_key=dec_api_key,
            max_output_tokens=8192
        )

    # # llm model test
    # from langchain_openai import ChatOpenAI

    # llm_model = "gpt-4o-mini"
    # dec_api_key = "sk-proj-xxx"
    # llm = ChatOpenAI(
    #     model=llm_model,
    #     api_key=dec_api_key,
    #     temperature=0,
    #     max_tokens=8192
    # )
    # #####

    # print("jeff llm model: ", llm)

    return llm


def calculate_capability_indices(data, spec_lower=None, spec_upper=None):
    """
    공정능력지수(Capability Index) 계산
    Cp, Cpk, Pp, Ppk 등을 반환
    """
    
    data = pd.to_numeric(data, errors='coerce').dropna()
    
    if len(data) == 0:
        return {}
    
    mean = data.mean()
    std = data.std()
    
    result = {
        '평균': mean,
        '표준편차': std,
    }
    
    if spec_lower is not None and spec_upper is not None:
        cp = (spec_upper - spec_lower) / (6 * std)
        cpu = (spec_upper - mean) / (3 * std)
        cpl = (mean - spec_lower) / (3 * std)
        cpk = min(cpu, cpl)
        
        result.update({
            'Cp': cp,
            'Cpk': cpk,
            'CPU': cpu,
            'CPL': cpl,
        })
    
    return result


prompt_common_text = """작업: df 분석 및 처리
- 컬럼: {{column_dict}} 참조, 결과는 사용자명
- 영어값: 대소문자 무관
- **중요**: 합격/불합격 판정 시 실제 데이터 값을 정확히 집계


**중요: 코드에서는 반드시 column_dict의 KEY(DB 컬럼명)를 사용하세요.**
- 예: df['Test Item'] (O)
- 예: df['시험항목'] (X)

사용자 지정 컬럼명(VALUE)은 시각화나 레이블에만 사용하세요.
"""

prompt_common_python_text = """
파이썬 코드 처리:
    - 중요 : 파이썬 명령이 실행될 수 있는 코드로 작성
    - 결과 예시 등은 작성하지 않습니다. 
        - 이 부분이 코드에 들어가는 경우 반드시 주석 형태로 넣어주세요.

데이터 타입 처리:
    - 데이터 타입과 데이터를 사용할 수 있는 함수나 메소드가 일치되어야 합니다.
        - 
        - 예를 들면 데이터는 숫자인데 .str과 같은 메소드를 사용하는 일이 없어야 합니다.
    - 숫자 연산 전: pd.to_numeric(df['col'], errors='coerce')
    - 날짜 연산 전: pd.to_datetime(df['col'])
    - groupby().agg() 형식: Named aggregation(새컬럼명=('원본컬럼명', 집계함수))은 DataFrame의 agg()에서만 사용 가능합니다. Series의 agg()에서는 사용 불가능합니다.

"""


def get_dataframe_information(df):
    date_cols = [col for col in df.columns if 'date' in col.lower()]
    date_info = ""
    if date_cols:
        date_col = date_cols[0]
        date_info = f"\n    - 날짜: {df[date_col].min()}~{df[date_col].max()}"
    
    total_cols = len(df.columns)
    
    # 컬럼이 15개 이상일 때만 간소화
    if total_cols > 15:
        sample_cols = list(df.columns[:3])
        col_info = f"{sample_cols}...외{total_cols-3}개"
    else:
        col_info = str(list(df.columns)).replace('{', '{{').replace('}', '}}')
    
    return f"""df정보: 컬럼={col_info}, 크기={df.shape}{date_info}
"""


# def get_charts_prompt(df, column_dict, question):

#     df_info = get_dataframe_information(df)

#     prompt = f"""{df_info}

# 질문: {question}

# 컬럼 매핑:
# {column_dict}

# {prompt_common_text}

# 요구사항 
#     1. pandas와 matplotlib을 사용
    
#     2. 한글 깨어지는 현상과 운영체제에 따른 오류를 막기 위해 아래 코드를 반드시 포함:
    
#     import matplotlib
#     matplotlib.use('Agg')
    
#     import matplotlib.pyplot as plt
#     import matplotlib.font_manager as fm

#     df = df.copy()

#     # 사용 가능한 한글 폰트 찾기
#     import os
#     font_path = os.path.join(
#         os.path.dirname(__file__), '..', 'static', 'fonts', 'NanumGothic-Regular.ttf'
#     )
#     font_path = os.path.abspath(font_path)

#     fm.fontManager.addfont(font_path)
#     font_name = fm.FontProperties(fname=font_path).get_name()
#     plt.rcParams['font.family'] = font_name
    
#     3. **차트 크기가 A4 용지 크기를 넘어갈 수 있어 다음 figsize를 반드시 코드에 넣어주세요.**

#     fig, ax = plt.figure(figsize=(5, 3))
    
#     4. 그래프 생성 후 plt.show()를 호출하여 표시하세요.
#        (주의: plt.savefig()는 사용하지 마세요. 시스템에서 자동으로 처리합니다)
    
#     5. plt.tight_layout() 사용
#         - 특히 subplot으로 작성되는 차트는 plt.tight_layout()을 사용하세요.
    
#     6. seaborn은 임포트하지 않고 matplotlib 만으로 그래프 구현하세요.
    
#     7. 레이아웃 조정이 필요하면 plt.subplots_adjust(hspace=0.3, wspace=0.3)을 사용하세요
    
#     8. **실행 가능한 Python 코드**로 작성
#         - 응답은 반드시 ```python 으로 시작하고 ``` 로 끝나야 합니다.
#         - 코드 블록 외부에 설명이나 주석을 추가하지 마세요.
#         - 오직 실행 가능한 Python 코드만 반환하세요.

# {prompt_common_python_text}

# matplotlib 설정:
#     - plt.figure(figsize=(width, height)) 크기는 적당한 값을 사용
#         - A4 용지에 좌우 여백 각 3cm를 고려한 크기
#         - width : 최대 6 으로 맞춰주세요. 
#         - height : 최대 10 으로 맞춰주세요.
#     - plt.title(), plt.xlabel(), plt.ylabel() 적절히 설정
#     - 한글 표시 시 unicode 문제 방지


# 코드:"""
    
#     return prompt

def get_charts_prompt(df, column_dict, question):

    df_info = get_dataframe_information(df)

    prompt = f"""{df_info}

질문: {question}

컬럼 매핑:
{column_dict}

{prompt_common_text}

요구사항 
    1. pandas와 matplotlib을 사용
    
    2. 한글 깨짐 방지 및 동시성 문제 해결을 위해 아래 코드를 반드시 포함:
    
    import matplotlib
    matplotlib.use('Agg')
    
    from matplotlib.figure import Figure
    import matplotlib.font_manager as fm
    import os

    df = df.copy()

    # 한글 폰트 설정
    font_path = os.path.join(
        os.path.dirname(__file__), '..', 'static', 'fonts', 'NanumGothic-Regular.ttf'
    )
    font_path = os.path.abspath(font_path)

    fm.fontManager.addfont(font_path)
    font_name = fm.FontProperties(fname=font_path).get_name()
    matplotlib.rcParams['font.family'] = font_name
    
    3. **차트 생성 방법 (반드시 이 방식 사용):**

    # 단일 차트
    fig = Figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    # 또는 서브플롯 (예: 3x2)
    fig = Figure(figsize=(6, 10))
    axes = [fig.add_subplot(3, 2, i+1) for i in range(6)]
    # 또는
    ax1 = fig.add_subplot(321)
    ax2 = fig.add_subplot(322)
    # ... 등등
    
    4. **차트 그리기는 ax 객체 사용:**
       - ax.plot(), ax.bar(), ax.hist(), ax.scatter() 등
       - ax.set_title(), ax.set_xlabel(), ax.set_ylabel()
       - ax.legend(), ax.grid()
       - ax.axvline(), ax.axhline() 등
    
    5. **코드 마지막에 반드시 추가:**
    
    fig.tight_layout()
    output_fig = fig

    6. **색상 사용 방법:**
       - plt.cm 대신 matplotlib.cm 사용
       - 예: colors = matplotlib.cm.tab20(np.linspace(0, 1, n))
       - 또는 직접 색상 리스트 정의: ['red', 'blue', 'green', ...]    

    7. **금지사항:**
       - plt.show() 사용 금지
       - plt.savefig() 사용 금지
       - plt.figure(), plt.subplots() 사용 금지 (Figure() 직접 생성)
       - seaborn 사용 금지
    
    8. 레이아웃 조정이 필요하면 fig.subplots_adjust(hspace=0.3, wspace=0.3) 사용
    
    9. **실행 가능한 Python 코드**로 작성
        - 응답은 반드시 ```python 으로 시작하고 ``` 로 끝나야 합니다.
        - 코드 블록 외부에 설명이나 주석을 추가하지 마세요.
        - 오직 실행 가능한 Python 코드만 반환하세요.

{prompt_common_python_text}

matplotlib 설정:
    - Figure(figsize=(width, height)) 크기는 적당한 값 사용
        - A4 용지에 좌우 여백 각 3cm를 고려한 크기
        - width : 최대 6
        - height : 최대 10
    - ax.set_title(), ax.set_xlabel(), ax.set_ylabel() 적절히 설정
    - 한글 표시 시 unicode 문제 방지

코드:"""
    
    return prompt


# def get_charts_prompt(df, column_dict, question):

#     df_info = get_dataframe_information(df)

#     prompt = f"""{df_info}

# 질문: {question}

# 컬럼 매핑:
# {column_dict}

# {prompt_common_text}

# 요구사항:
#     1. 한글 폰트 설정 (필수):
    
#     import matplotlib
#     matplotlib.use('Agg')
#     import matplotlib.pyplot as plt
#     import matplotlib.font_manager as fm
#     import os

#     df = df.copy()
    
#     font_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts', 'NanumGothic-Regular.ttf')
#     font_path = os.path.abspath(font_path)
#     fm.fontManager.addfont(font_path)
#     plt.rcParams['font.family'] = fm.FontProperties(fname=font_path).get_name()
    
#     2. 차트 생성 (ax 객체 사용):
    
#     fig, ax = plt.subplots(figsize=(5, 3))  # 또는 (3, 2) 등
#     ax.plot(...)  # ax.bar(), ax.hist() 등
#     ax.set_title('제목')
    
#     3. 코드 마지막 (필수):
    
#     fig.tight_layout()
#     output_fig = fig
    
#     4. 금지사항: plt.show(), plt.savefig(), seaborn 사용 금지
    
#     5. figsize: width 최대 6, height 최대 10

# {prompt_common_python_text}

# 코드:"""
    
#     return prompt


def get_tables_prompt(df, column_dict, question):

    df_info = get_dataframe_information(df)

    prompt = f"""{df_info}

질문: {question}

컬럼 매핑:
{column_dict}

{prompt_common_text}
    - result 라는 변수에 결과 값을 대입해주세요.

**중요 제약:**
    - openpyxl, xlsxwriter 등 엑셀 라이브러리 사용 금지
    - to_excel(), wb.save() 등 파일 저장 코드 금지
    - PatternFill, Workbook 등 엑셀 관련 객체 사용 금지
    - 오직 pandas DataFrame만 사용하세요        

제약 조건:
    1. pandas만 사용하세요.
    2. **실행 가능한 Python 코드**로 작성
        - 코드의 시작은 '```python'이고  '```'까지 입니다. 그리고 이 코드를 결과로 반환합니다.
        - 파이썬 코드를 제외한 모든 텍스트는 삭제합니다.
    3. 피벗테이블을 이용하여 표를 작성한 경우라도 컬럼명을 한 행에 표기해주세요.
        - 컬럼명은 그 컬럼을 대표힐 수 있는 명칭을 사용하세요.
        - 표의 컬럼명에는 {{column_dict}}의 밸류값인 사용자 컬럼명을 사용합니다.
    4. 테이블 크기
        - A4 용지에 좌우 여백 각 3cm를 고려한 크기
        - width : 최대 5.5 
        - height : 최대 10 
    5. 데이터프레임을 별도로 저장하지 않습니다. (중요)

{prompt_common_python_text}

코드: """
    return prompt


def get_table_style_combined(df, question):
    first_row = list(df.columns)
    first_column = df.columns[0] if len(df.columns) > 0 else None
    all_columns = list(df.columns)
    
    prompt = f"""
다음 DataFrame에 대한 테이블 스타일을 JSON으로 생성하세요.

DataFrame 컬럼: {all_columns}
첫번째 행(첫 행) : {first_row}
첫번째 열(첫 열) : {first_column}

사용자 요구사항:
{question}


스타일 적용 규칙:
0. 우선규칙
    - **중요** 기본 스타일보다 사용자가 요청한 스타일 적용이 우선입니다. 
        - 기본 스타일은 {question}에서 스타일을 요청하지 않을 경우 적용 
        - 폰트 크기의 단위는 "pt" 입니다. 예를 들어 폰트 크기 : 14 이면 14pt를 의미합니다.

1. 기본스타일
    - 헤더(header) : 헤더틑 표의 첫 행을 말합니다. 데이터프레임의 첫 행인 df[0]이 아니라 테이블의 첫 행입니다. 
        - 글자(font) 크기 : 14pt / 진하기 : 진하게(bold)
        - 배경(background) 색상 : #cccccc
    - 데이터(data) 영역 : 표의 두번째 행부터 마지막행까지입니다.
        - 글자(font) 크기 : 12pt / 진하기 : 보통(normal)
        - 배경(background) 색상 : #ffffff
    - 제일 왼편 열 : 이 부분은 사용자가 요청하지 않으면 데이터(data) 영역의 스타일을 따릅니다
        - 첫 번째 컬럼("{first_column}")이 이 영역에 해당합니다.

2. 스타일은 아래 JSON 형식으로 지정하여 테이블에 적용합니다. **아래는 예시입니다. 이것을 지정하지 않은 부분에 적용하지 않습니다.**
    JSON 형식:
    {{
        "header": {{
            "{all_columns[0]}": {{"bgcolor": "#cccccc", "align": "center", "color": "#000000", "fontweight": "bold", "fontsize": "14pt"}},
            "{all_columns[1]}": {{"bgcolor": "#cccccc", "align": "center", "color": "#000000", "fontweight": "bold", "fontsize": "14pt"}},
            ...
        }},
        "data": {{
            "{all_columns[0]}": {{"bgcolor": "#ffffff", "align": "left", "color": "#000000", "fontweight": "normal", "fontsize": "12pt"}},
            "{all_columns[1]}": {{"bgcolor": "transparent", "align": "right", "color": "#000000", "fontweight": "normal", "fontsize": "12pt"}},
            ...
        }},
    }}

3. 색상 표현:
    - 단색: "#cccccc" 형식 (회색 = #808080 또는 #cccccc)
    - 투명도 포함: "rgba(128, 128, 128, 0.3)" 형식 (30% 투명도 = 0.3)
    - 투명(배경 없음): "transparent"

4. 정렬(align):
    - 텍스트: "left" 또는 "center"
    - 숫자: "right" 또는 "center"

5. 글자 진하기(fontweight):
    - 진하게: "bold"
    - 보통: "normal"

6. 글자 크기(fontsize):
    - 숫자만 (예: "14", "10")

**중요:** 
- DataFrame의 실제 컬럼명만 사용하세요
- 모든 컬럼에 대해 header와 data 스타일을 정의하세요
- 값은 모두 문자열로 표현하세요
- 설명 없이 JSON만 출력하세요

답변(JSON만):
"""
    return prompt


def get_sentences_prompt(df, column_dict, question):
    """
    통계 데이터 추출용 Python 코드 생성 프롬프트 (이상치 탐지 포함)
    
    Args:
        df: 분석 대상 데이터프레임 (익명화된 상태)
        column_dict: 컬럼 매핑 정보
        question: 사용자 질문
        
    Returns:
        str: LLM에 전달할 프롬프트
    """
    df_info = get_dataframe_information(df)

    prompt = f"""{df_info}

질문: {question}

컬럼 매핑:
{column_dict}

{prompt_common_text}

**작업 목표:**
사용자의 질문에 답하기 위한 통계 데이터를 JSON(dict) 형식으로 추출하세요.

**JSON 구조 가이드라인:**
    0. 사용자 질문에 필요한 값들만 결과로 작성하세요.
    1. "기본_통계": 전체적인 요약 정보 (총 건수, 비율, 평균, 표준편차 등)
    2. "상세_분석": 항목별, 그룹별, 카테고리별 세부 통계
    3. "시계열_분석": 월별/분기별/연도별 추이 데이터 (날짜 컬럼이 있는 경우)
    4. "이상치": 평균에서 크게 벗어난 값, 급격한 변화, 특이사항 등
        - 통계적 이상: 평균 ± 2~3 표준편차 벗어난 값
        - 시계열 이상: 전월/전년 대비 급격한 변화 (15%+ 변동)
        - 패턴 이상: 연속 불합격, 특정 카테고리 집중 등
        - 각 이상치에는 유형, 관련 값, 편차 정도, 심각도 포함

**중요 규칙:**
    - 오류없이 실행되는 파이썬 코드를 작성해주세요.
    - result 변수에 dict 타입으로 저장하세요. (절대 문자열 아님)
        - 사용자 질문에 답을 할 때 답변에 필요한 값들만 dict 타입으로 저장하세요.
        - **예를 들면 단순히 "2024년 배치수는 얼마인가요?"하는 경우는 결과는 '배치수: __ 개'의 간단한 dict가 결과입니다.**
    - JSON 키는 한글로 작성하되, 사용자 질문과 관련된 의미 있는 이름을 사용하세요.
    - 숫자는 적절히 반올림하세요 (소수점 1~2자리).
    - 사용자 질문에서 요구하지 않은 분석은 포함하지 마세요.
    - 컬럼명은 column_dict의 VALUE(사용자 친화 이름)를 사용하세요.
    - 이상치는 최대 10개까지만 포함하고, 심각도 순으로 정렬하세요.

{prompt_common_python_text}

**데이터프레임 컬럼 타입 처리 규칙**
    - 코드 작성 시 절대로 컬럼 데이터 타입을 추측하지 마세요.
        - 문자열인지 숫자인지, 날짜인지 등은 반드시 df의 실제 dtype 또는 값 패턴을 보고 판단하세요.
    - 문자열 연산(.str.lower(), .str.contains 등)을 하기 전에 반드시:
            df[col] = df[col].astype(str)
        또는
            df[col] = df[col].astype(str, errors='ignore')
        을 적용하세요.
        - 문자열이 아닌 컬럼에는 .str 접근자를 사용하지 마세요.
    - 숫자 연산(mean, sum, 비교 등)을 하기 전에 반드시:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        를 사용하여 숫자로 변환 가능한지 확인하세요.
    - 날짜 연산을 하기 전에:
            df[col] = pd.to_datetime(df[col], errors='coerce')
        를 사용해 날짜인지 판단하세요.
        - 변환 불가능하면 NaT로 처리하고 날짜 연산을 하지 마세요.
    - 문자열 기반 코드 작성은 값 패턴이 문자열(예: Yes/No, Pass/Fail, product name 등)인 경우에만 적용하세요.
    - 특정 컬럼명에 의존하지 말고, 질문(question)에서 언급된 사용자 컬럼명 또는 동의어를 찾아 column_dict(매핑 테이블)을 사용해 실제 df 컬럼명으로 변환하세요.
    - df의 전체 dtype 정보를 기반으로 "어떤 연산이 가능한지"를 먼저 판단하고, 그 후에 필요한 연산(groupby, 집계, 필터링 등)을 작성하세요.

**파이썬 코드 작성 시 절대 금지사항:**
    1. 코드 안에 보고서 예시나 결과 설명을 절대 포함하지 마세요.
    2. 주석에도 특수문자(→, ·, ■ 등)를 사용하지 마세요. ASCII 문자만 사용하세요.
    3. print문으로 보고서를 출력하지 마세요.
    4. 코드 실행 후 보고서를 생성하지 마세요.
    5. result 변수는 반드시 dict 타입이어야 합니다.

**코드 출력 형식:**
    - 설명 없이 순수 Python 코드만 출력하세요.
    - 코드 실행 가능해야 하며, result 변수에 dict를 저장해야 합니다.
    - 마지막에 json.dumps나 print로 결과를 출력하지 마세요.

**올바른 예시:**
```python
import numpy as np
from scipy import stats

df['OOS'] = df['OOS'].astype(str).str.strip()
total_count = len(df)
pass_count = len(df[df['OOS'].str.upper() != 'YES'])
pass_rate = round((pass_count / total_count * 100), 1)

# 이상치 탐지 예시
mean_rate = pass_rate
std_rate = df.groupby('Month')['pass_rate'].std()

anomalies = []
# 통계적 이상치 탐지
for item in unique_items:
    item_rate = calculate_rate(item)
    z_score = (item_rate - mean_rate) / std_rate
    if abs(z_score) > 2:
        anomalies.append({{
            "유형": "통계적_이상",
            "항목": item,
            "값": item_rate,
            "표준편차_거리": round(z_score, 2),
            "심각도": "높음" if abs(z_score) > 3 else "중간"
        }})

result = {{
    "기본_통계": {{
        "총_건수": int(total_count),
        "합격률": pass_rate,
        "표준편차": round(std_rate, 2)
    }},
    "이상치": anomalies[:10]  # 최대 10개
}}
```

답변:"""

    return prompt


def generate_report_from_statistics(llm, statistics_dict, user_question):
    """
    통계 JSON을 자연어 보고서로 변환
    
    Args:
        llm: Anthropic LLM 인스턴스
        statistics_dict: Python 코드 실행 결과 (dict)
        user_question: 원래 사용자 질문
        
    Returns:
        dict: {
            "result": str (보고서 텍스트),
            "tokens": {"input_tokens": int, "output_tokens": int}
        }
    """
    
    tokens = {"input_tokens": 0, "output_tokens": 0}

    stats_formatted = json.dumps(statistics_dict, ensure_ascii=False, indent=2)
    
    prompt = f"""당신은 데이터 분석 보고서 작성 전문가입니다.
**중요** 답변은 서술형 문장으로 작성합니다.
    - 수치에 대한 집계를 사용자가 요청하는 경우도 이 내용을 서술형으로 작성합니다.
    - 집계치를 마크다운의 테이블 작성 형태를 허용하지 않습니다.

**사용자 요청:**
{user_question}

**분석된 통계 데이터:**
{stats_formatted}

**작성 지침:**
    1. 위 통계 데이터를 바탕으로 사용자가 요청한 형식의 답변을 작성하세요.
        - 사용자의 요청사항이 단순 질문이면 최대한 간단히 답변하세요.
            - 단순 질문에 대한 결과가 숫자일 경우 필요한 경우 아래 예시처럼 적절한 단위를 붙여주세요.
            - 예시) 요청: "몇 건입니까?" / 답변: xx 건
    2. 사용자 요청에 명시된 모든 조건을 준수하세요:
        - 보고서 길이 (예: 1000자 내외)
        - 구조 및 섹션 (예: 현황, 문제점, 개선안)
        - 포함해야 할 내용
        - 작성 스타일이나 톤앤매너
    3. 통계 데이터에 근거한 구체적이고 명확한 문장을 작성하세요.
    4. 전문적이면서도 이해하기 쉬운 문체를 사용하세요.
    5. 데이터에 없는 내용이나 근거 없는 추측은 절대 작성하지 마세요.
    6. 숫자를 인용할 때는 정확하게 표기하세요.
    7. 보고서는 마크다운이 아닌 일반 텍스트 형식으로 작성하세요.

**중요:**
    - 통계 데이터의 모든 정보를 반드시 사용할 필요는 없습니다.
    - 사용자가 요청한 내용에 집중하여 관련 통계만 선택적으로 활용하세요.
    - 보고서의 흐름과 가독성을 최우선으로 고려하세요.

**보고서:**"""

    response = llm.invoke(prompt)
    
    if hasattr(response, "response_metadata") and "usage" in response.response_metadata:
        usage = response.response_metadata["usage"]
        tokens["input_tokens"] = usage.get("input_tokens", 0)
        tokens["output_tokens"] = usage.get("output_tokens", 0)

    return {
        "result": response.content.strip(),
        "tokens": tokens
    }


def generate_column_prefix(column_name, existing_prefixes):
    """
    완전 랜덤 접두사 생성
    
    Args:
        column_name: 컬럼명 (사용 안 함, 시그니처 유지용)
        existing_prefixes: 이미 사용 중인 접두사 set
        
    Returns:
        str: 랜덤 2글자 대문자 (예: "XQ", "KM", "PZ")
    """
    
    # 충돌 방지 루프
    max_attempts = 1000
    for _ in range(max_attempts):
        # 랜덤 2글자 대문자 생성
        prefix = ''.join(random.choices(string.ascii_uppercase, k=2))
        
        if prefix not in existing_prefixes:
            return prefix
    
    # 3글자로 확장
    return ''.join(random.choices(string.ascii_uppercase, k=3))


def generate_value_prefix(column_name, existing_prefixes):
    """
    값용 랜덤 접두사 생성
    
    Returns:
        str: V + 랜덤 2글자 (예: "VXQ", "VKM")
    """
    
    max_attempts = 1000
    for _ in range(max_attempts):
        # V + 랜덤 2글자
        base = ''.join(random.choices(string.ascii_uppercase, k=2))
        prefix = f"V{base}"
        
        if prefix not in existing_prefixes:
            return prefix
    
    # 백업: V + 3글자
    return f"V{''.join(random.choices(string.ascii_uppercase, k=3))}"


def create_anonymization_mapping(df, sensitive_columns=None):
    """
    DataFrame의 컬럼과 값을 동적으로 익명화 매핑 생성
    
    Args:
        df: 원본 DataFrame
        sensitive_columns: 익명화할 컬럼 리스트
                          예: ["Test Item", "product_name", "Analyst"]
                          None이면 모든 문자열 컬럼을 익명화
        
    Returns:
        dict: {
            "column_mapping": {원본컬럼명: 익명컬럼명},
            "value_mapping": {컬럼명: {원본값: 익명값}}
        }
    """
    
    if sensitive_columns is None:
        sensitive_columns = [
            col for col in df.columns 
            if df[col].dtype == 'object' or df[col].dtype.name == 'category'
        ]
    
    column_mapping = {}
    value_mapping = {}
    used_prefixes = set()
    
    # 컬럼명 익명화
    for col in df.columns:
        if col in sensitive_columns:
            prefix = generate_column_prefix(col, used_prefixes)
            used_prefixes.add(prefix)
            column_mapping[col] = f"COL_{prefix}"
        else:
            # 민감하지 않은 컬럼은 그대로
            column_mapping[col] = col
    
    # 컬럼값 익명화
    for col in sensitive_columns:
        if col not in df.columns:
            continue
            
        # 해당 컬럼의 고유값 추출
        unique_values = df[col].dropna().unique()
        
        if len(unique_values) == 0:
            continue
        
        # 값 접두사 생성
        val_prefix = generate_value_prefix(col, used_prefixes)
        used_prefixes.add(val_prefix)
        
        # 번호 부여
        value_mapping[col] = {}
        for idx, value in enumerate(sorted(unique_values.astype(str)), start=1):
            anonymized_value = f"{val_prefix}_{idx:03d}"
            value_mapping[col][str(value)] = anonymized_value
    
    return {
        "column_mapping": column_mapping,
        "value_mapping": value_mapping
    }


def clean_json_response(content):
    """
    LLM 응답에서 순수 JSON만 추출
```json ... ``` 형태나 다른 텍스트를 제거
    """
    
    content = content.strip()
    
    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        content = json_match.group(1).strip()
    else:
        json_match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1).strip()
    
    content = content.strip()
    
    try:
        json.loads(content)  # 파싱 테스트
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 오류: {e}")
        print(f"문제가 된 내용: {content[:200]}...")
    
    return content


def anonymize_text(text, mapping):
    """
    텍스트(사용자 프롬프트)를 익명화
    
    Args:
        text: 원본 텍스트 (사용자 프롬프트)
        mapping: create_anonymization_mapping()의 결과
        
    Returns:
        str: 익명화된 텍스트
    """
    if not text or not isinstance(text, str):
        return text
    
    result = text
    column_mapping = mapping["column_mapping"]
    value_mapping = mapping["value_mapping"]
    
    # 값 익명화 (긴 것부터 처리)
    for col, val_map in value_mapping.items():
        for original, anonymized in sorted(val_map.items(), key=lambda x: len(x[0]), reverse=True):
            result = result.replace(original, anonymized)
    
    # 컬럼명 익명화
    for original, anonymized in sorted(column_mapping.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(original, anonymized)
    
    return result


def anonymize_json(data, mapping):
    """
    JSON 데이터(통계 결과)를 재귀적으로 익명화
    
    Args:
        data: 원본 데이터 (dict, list, str, int 등)
        mapping: create_anonymization_mapping()의 결과
        
    Returns:
        익명화된 데이터 (원본과 같은 타입)
    """
    column_mapping = mapping["column_mapping"]
    value_mapping = mapping["value_mapping"]
    
    # 모든 매핑을 하나로 합침 (원본 -> 익명)
    all_mapping = {}
    
    # 값 매핑 추가
    for col, val_map in value_mapping.items():
        all_mapping.update(val_map)
    
    # 컬럼 매핑 추가
    all_mapping.update(column_mapping)

    def _anonymize_string(text):
        """문자열 내 모든 원본 단어를 익명화"""
        if not isinstance(text, str):
            return text
        
        result = text
        for original, anonymized in sorted(all_mapping.items(), key=lambda x: len(x[0]), reverse=True):
            result = result.replace(original, anonymized)
        return result    
    
    # 재귀 처리
    def _anonymize_recursive(obj):
        if isinstance(obj, dict):
            return {
                _anonymize_string(k): _anonymize_recursive(v) 
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            # list: 각 요소 익명화
            return [_anonymize_recursive(item) for item in obj]
        elif isinstance(obj, str):
            return _anonymize_string(obj)
        else:
            # int, float, bool, None: 그대로 반환
            return obj
    
    return _anonymize_recursive(data)


def reverse_anonymization(text, mapping):
    """
    익명화된 텍스트를 원본으로 역변환
    
    Args:
        text: LLM이 생성한 익명화된 보고서
        mapping: create_anonymization_mapping()의 결과
        
    Returns:
        str: 원본 용어로 복원된 텍스트
    """
    if not text or not isinstance(text, str):
        return text
    
    result = text
    column_mapping = mapping["column_mapping"]
    value_mapping = mapping["value_mapping"]
    
    # 역매핑 생성 (익명 -> 원본)
    reverse_col_map = {v: k for k, v in column_mapping.items()}
    reverse_val_map = {}
    
    for col, val_map in value_mapping.items():
        for original, anonymized in val_map.items():
            reverse_val_map[anonymized] = original
    
    # 값 역변환 (긴 것부터 처리하여 부분 매칭 방지)
    for anonymized in sorted(reverse_val_map.keys(), key=len, reverse=True):
        original = reverse_val_map[anonymized]
        result = result.replace(anonymized, original)
    
    # 컬럼명 역변환
    for anonymized in sorted(reverse_col_map.keys(), key=len, reverse=True):
        original = reverse_col_map[anonymized]
        result = result.replace(anonymized, original)
    
    return result


def log_mapping(mapping, item_index=None):
    """
    매핑 정보 출력 및 로그 기록
    
    Args:
        mapping: create_anonymization_mapping()의 결과
        item_index: 항목 인덱스 (선택)
    """
    
    header = f"=== Anonymization Mapping (Item {item_index}) ===" if item_index else "=== Anonymization Mapping ==="
    
    # print("\n" + "="*60)
    # print(header)
    # print("="*60)
    
    # print("\n[Column Mapping]")
    for original, anonymized in mapping["column_mapping"].items():
        if original != anonymized:  # 변경된 것만 출력
            # print(f"  {original:20s} -> {anonymized}")
            pass
    
    # print("\n[Value Mapping]")
    for col, val_map in mapping["value_mapping"].items():
        # print(f"\n  Column: {col}")
        for original, anonymized in list(val_map.items())[:10]:  # 최대 10개만 출력
            # print(f"    {original:20s} -> {anonymized}")
            pass
        if len(val_map) > 10:
            # print(f"    ... and {len(val_map) - 10} more values")
            pass
    
    # print("="*60 + "\n")
    
    # 필요시 로그 파일에도 기록
    # with open(f'anonymization_log_{item_index}.json', 'w', encoding='utf-8') as f:
    #     json.dump(mapping, f, ensure_ascii=False, indent=2)


def fix_groupby_agg_pattern(code):
    """
    Series.agg()의 named aggregation 패턴을 자동으로 수정
    groupby('col')['col'].agg(name=('col', func)) -> groupby('col').agg(name=('col', func))
    """
    # 패턴: groupby(...)['...'].agg(...)
    # 이를 groupby(...).agg(...)로 변경
    pattern = r"groupby\(([^)]+)\)\['([^']+)'\]\.agg\("
    replacement = r"groupby(\1).agg("
    
    fixed_code = re.sub(pattern, replacement, code)
    
    if fixed_code != code:
        print("[AUTO FIX] groupby().agg() 패턴 자동 수정됨")
    
    return fixed_code


def create_python_code(llm, prompt, df, question, column_dict, output_type):
    import matplotlib.pyplot as plt

    tokens = {"input_tokens": 0, "output_tokens": 0}

    res = llm.invoke(prompt)

    if hasattr(res, "response_metadata") and "usage" in res.response_metadata:
        usage = res.response_metadata["usage"]
        tokens["input_tokens"] += usage.get("input_tokens", 0)
        tokens["output_tokens"] += usage.get("output_tokens", 0)

    code = res.content.strip().replace('```python', '').replace('```', '')

    chart_patterns = ["plt.show()", "fig.show()", "show()"]
    for pattern in chart_patterns:
        code = code.replace(pattern, f"# {pattern}")

    forbidden_patterns = ["openpyxl", "Workbook", "to_excel", "xlsxwriter", "PatternFill"]
    for pattern in forbidden_patterns:
        if pattern in code:
            return {
                "status": "error",
                "error": f"엑셀 파일 생성 코드는 사용할 수 없습니다. pandas DataFrame만 사용하세요.",
                "code": code,
            }

    # print("python_code: \n", code)    # 디버깅용 : 배포시 삭제/주석 처리
    # # if output_type == "TA":
    # #     print("python_code: \n", code)

    warnings.filterwarnings("ignore")
    plt.rcParams["font.family"] = "sans-serif"

    code = code.replace("plt.tight_layout()", "# plt.tight_layout() 제거됨")
    code = code.replace("'Malgun Gothic'", "'sans-serif'")

    code = fix_groupby_agg_pattern(code)

    local_namespace = {
        'df': df,
        'pd': pd,
        'np': np,
        'os': os,
        'sys': sys,
        'calculate_capability_indices': calculate_capability_indices,
        '__file__': os.path.abspath(__file__) if '__file__' in globals() else '',
        '__name__': '__main__',
    }

    try:
        exec(code, local_namespace)
        # exec(code, {"__builtins__": __builtins__}, local_namespace)
    except Exception as e:
        print("Error ", e)
        return {
            "status": "error",
            "error": f"코드 실행 오류: {str(e)}",
            "code": code,
        }

    if output_type == "CA":
        # LLM이 생성한 output_fig 가져오기
        fig = local_namespace.get('output_fig')
        
        if fig is None:
            raise ValueError("LLM이 output_fig를 생성하지 않았습니다.")
        
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        # figure 정리 (메모리 누수 방지)
        import matplotlib.pyplot as plt
        plt.close(fig)
        
        return {
            "image_bytes": img_base64,
            "status": "chart_drawn",
            "question": question,
            "tokens": tokens
        }
        
    elif output_type == "TA":
        if "result" in local_namespace:
            result_obj = local_namespace["result"]

            type_name = type(result_obj).__name__

            if type_name == 'Styler':
                df_result = result_obj.data
            elif isinstance(result_obj, pd.DataFrame):
                df_result = result_obj
            else:
                return {
                    "status": "error",
                    "error": f"Claude가 result 변수에 DataFrame을 반환하지 않았습니다. (type={type_name})",
                    "code": code,
                }

            # df_result = df_result.applymap(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)
            df_result = df_result.map(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)

            table_style_prompt = get_table_style_combined(df_result, question)
            response_style = llm.invoke(table_style_prompt)
            style_json = clean_json_response(response_style.content)

            if hasattr(response_style, "response_metadata") and "usage" in response_style.response_metadata:
                usage = response_style.response_metadata["usage"]
                tokens["input_tokens"] += usage.get("input_tokens", 0)
                tokens["output_tokens"] += usage.get("output_tokens", 0)

            style_dict = json.loads(style_json)
            table_header_json = json.dumps(style_dict.get("header", {}))
            table_data_json = json.dumps(style_dict.get("data", {}))

            data = df_result.to_dict(orient="records")
                
            return {
                "result": data,
                "status": "data_table",
                "question": question,
                "table_header_json": table_header_json,
                "table_data_json": table_data_json,
                "tokens": tokens
            }
        else:
            return {
                "status": "error",
                "error": "AI가 result 변수에 테이블 결과를 저장하지 않았습니다.",
                "code": code,
            }

    elif output_type == "SA":
        # 익명화 적용 여부 확인 (설정 또는 파라미터로 제어)
        use_anonymization = True  # 또는 파라미터로 받기
        
        if use_anonymization:
            # 민감 컬럼 지정 (설정에서 가져오거나 자동 감지)
            sensitive_columns = None
            
            # 익명화 매핑 생성
            anonymization_mapping = create_anonymization_mapping(df, sensitive_columns)
            
            # 매핑 출력/로그
            log_mapping(anonymization_mapping)

        else:
            anonymization_mapping = None
        
        if "result" not in local_namespace:
            return {
                "status": "error",
                "error": "AI가 result 변수를 생성하지 않았습니다.",
                "code": code,
            }
        
        result_obj = local_namespace["result"]
        
        # dict 타입 확인
        if not isinstance(result_obj, dict):
            return {
                "status": "error",
                "error": f"AI가 result 변수에 dict를 반환하지 않았습니다. (type={type(result_obj).__name__})",
                "code": code,
            }

        try:
            # json 익명화
            result_obj_anonymized = anonymize_json(result_obj, anonymization_mapping)
            
            # question 익명화
            question_anonymized = anonymize_text(question, anonymization_mapping)
            
            # 보고서 생성
            report_result = generate_report_from_statistics(
                llm=llm,
                statistics_dict=result_obj_anonymized,
                user_question=question_anonymized
            )

            # 역익명화 (원본 용어로 복원)
            if use_anonymization and anonymization_mapping:
                final_report = reverse_anonymization(
                    report_result["result"], 
                    anonymization_mapping
                )
            else:
                final_report = report_result["result"]
            
            tokens["input_tokens"] += report_result["tokens"]["input_tokens"]
            tokens["output_tokens"] += report_result["tokens"]["output_tokens"]
            
            return {
                "status": "analysis_comment",
                "question": question,
                "result": final_report,
                "tokens": tokens
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"보고서 생성 중 오류 발생: {str(e)}",
                "code": code,
            }
        
    elif output_type == "DF":
        if "result" in local_namespace and isinstance(local_namespace["result"], pd.DataFrame):
            df_result = local_namespace["result"]
            return {
                "result": df_result,
                "status": "dataframe",
                "tokens": tokens
            }
        else:
            return {
                "status": "error",
                "error": "Claude가 result 변수에 결과를 저장하지 않았습니다.",
                "code": code,
                "tokens": tokens
            }

    else:
        return {
            "status": "error",
            "error": "존재하지 않는 Output Type 입니다.",
            "code": code,
        }



def get_full_chain(llm, df, prompt, question, column_dict, output_type):

    tokens_container = {"input_tokens": 0, "output_tokens": 0}
    
    def apply_python_code(x, output_type):
        result = create_python_code(llm, prompt, x["df"], question, column_dict, output_type)
        if isinstance(result, dict) and 'tokens' in result:
            tokens_container['input_tokens'] += result['tokens']['input_tokens']
            tokens_container['output_tokens'] += result['tokens']['output_tokens']
        return result
    
    def extract_and_track_tokens(ai_msg):
        if hasattr(ai_msg, 'response_metadata') and 'usage' in ai_msg.response_metadata:
            usage = ai_msg.response_metadata['usage']
            tokens_container['input_tokens'] += usage.get('input_tokens', 0)
            tokens_container['output_tokens'] += usage.get('output_tokens', 0)
        return {"df": df, "question": ai_msg.content}
    
    generate_prompt_func = partial(apply_python_code, output_type=output_type)
    
    generate_prompt = RunnableLambda(generate_prompt_func)

    # full_chain = PromptTemplate.from_template(prompt) | llm | RunnableLambda(extract_and_track_tokens) | generate_prompt
    full_chain = RunnableLambda(lambda x: prompt) | llm | RunnableLambda(extract_and_track_tokens) | generate_prompt

    def add_tokens_to_result(result):
        if isinstance(result, dict):
            if 'tokens' not in result:
                result['tokens'] = {}
            result['tokens']['input_tokens'] = tokens_container['input_tokens']
            result['tokens']['output_tokens'] = tokens_container['output_tokens']
        return result
    
    return full_chain | RunnableLambda(add_tokens_to_result)
