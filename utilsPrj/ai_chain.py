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


def _omits_temperature(vendor_name: str, model: str) -> bool:
    """온도(temperature) 파라미터 자체를 거부하는 추론 전용 모델인지 판정합니다.
    추론 모델은 내부적으로 온도가 고정되어 있어 클라이언트가 값을 얼마로 주든 (0 포함)
    API가 400(invalid_request_error)으로 거부합니다. 
    - "낮은 값으로"가 아니라 "아예 안 보냄"으로 대응해야 합니다.
    """
    m = model.lower()
    if vendor_name == "Anthropic":
        return "opus" in m or "fable" in m
    if vendor_name == "OpenAI":
        # o-series (o1, o3, o3-mini, o4-mini) 
        return m.startswith("o1") or m.startswith("o3") or m.startswith("o4")
    if vendor_name == "Google":
        return "thinking" in m
    return False


def build_langchain_llm(vendor_name: str, api_key: str, model: str):
    """벤더명·API키·모델명으로 LangChain LLM 인스턴스를 생성한다.
    get_llm_model 내부의 LLM 생성 로직(Anthropic/OpenAI/Google)을 독립 함수로 추출.
    d2shared.mcp_server, d2chat.mcp_agent 등에서 임포트해 공통 사용.
    """

    skip_temperature = _omits_temperature(vendor_name, model)

    if vendor_name == "Anthropic":
        kwargs = dict(anthropic_api_key=api_key, model=model, max_tokens=8192)
        if not skip_temperature:
            kwargs["temperature"] = 0
        return ChatAnthropic(**kwargs)
    if vendor_name == "OpenAI":
        from langchain_openai import ChatOpenAI
        kwargs = dict(model=model, api_key=api_key, max_tokens=8192)
        if not skip_temperature:
            kwargs["temperature"] = 0
        return ChatOpenAI(**kwargs)
    # ===================================================================
    # TEMP: 로컬 Llama(Together.ai) 테스트용 — 품질 비교 테스트 종료로 주석처리 (2026-08-20)
    # 재활성화 시 이 블록의 주석만 해제하면 된다.
    # if vendor_name == "Llama":
    #     # Together.ai(https://api.together.ai) — OpenAI 호환 API로 Llama 3.3 70B를
    #     # 양자화 없는 정식 버전으로 서빙. ChatOpenAI에 base_url만 바꿔서 그대로 재사용한다
    #     # (2026-08-19, 로컬 Llama 테스트용 — 새 패키지 설치 불필요.
    #     #  aimlapi 결제 문제 → Groq(Llama 미제공) → Together.ai로 최종 교체).
    #     from langchain_openai import ChatOpenAI
    #     kwargs = dict(
    #         model=model, api_key=api_key, max_tokens=8192,
    #         base_url="https://api.together.xyz/v1",
    #     )
    #     if not skip_temperature:
    #         kwargs["temperature"] = 0
    #     return ChatOpenAI(**kwargs)
    # ===================================================================
    elif vendor_name == "Google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        kwargs = dict(model=model, google_api_key=api_key, max_output_tokens=8192)
        if not skip_temperature:
            kwargs["temperature"] = 0
        return ChatGoogleGenerativeAI(**kwargs)
    raise ValueError(f"지원하지 않는 LLM 벤더: {vendor_name}")


_GRADE_MODEL_COLUMNS = {
    "fast": "llmmodelnm",
    "balanced": "llmmodelnm_smart",
    "quality": "llmmodelnm_expert",
}


def get_llm_info(supabase=None, project_id=None, tenant_id=None, user_uid=None, service_code=None, account_uid=None):
    """Supabase에서 LLM 설정을 조회해 (model, dec_api_key, vendor_name, is_customeraikey, account_uid) 반환.

    supabase 미전달 시 서비스 역할 클라이언트를 자동 사용.
    service_code: 앱 구분 ("Do"=d2doc, "Ch"=d2chat, "In"=d2insight)
    account_uid 전달 시 serviceusers 조회를 건너뛰고 바로 subscriptions 조회.
    user_uid 전달 시(account_uid 없을 때) serviceusers에서 account_uid 조회.
    구독 플랜(is_customeraikey)에 따라 키 조회 경로가 분기된다:
      - is_customeraikey=True  → 고객 등록 키: projects → llmapikeys(accountuid+servicecd)
      - is_customeraikey=False → 서비스 제공 키: 시스템 테넌트의 llmapikeys 사용
    user_uid/account_uid 미전달 시 기본 fallback(llmmodels/llmapis) 사용.
    반환되는 is_customeraikey/account_uid는 llmdoclogs/llmchatlogs/llminsightlogs 기록에 사용된다.

    service_code="In"(d2insight)일 때는 반환 튜플의 첫 값(model)이 문자열이 아니라 등급별 dict
    {"fast": ..., "balanced": ..., "quality": ...}다 — projects/llmapikeys에 등급별 컬럼
    (llmmodelnm/llmmodelnm_smart/llmmodelnm_expert)이 있어 한 번의 조회로 세 등급을 모두
    가져온다(agent.py처럼 세션 하나에서 등급을 바꿔가며 여러 번 쓰는 곳이 등급마다 구독/키
    조회를 반복하지 않도록). 반환 튜플 자리 수는 그대로 5개다 — "Do"/"Ch"/그 밖의 기존
    호출부는 손댈 필요 없이 지금처럼 model을 문자열로 받는다.
    """
    # ===================================================================
    # TEMP: 로컬 Llama(Together.ai) 테스트용 하드코딩 오버라이드 — 품질 비교 테스트
    # 종료로 주석처리, 원래 Supabase 조회 로직으로 복원 (2026-08-20)
    # 재활성화 시 아래 블록의 주석만 해제하면 된다.
    # d2insight("In")·d2chat("Ch")에만 적용 — d2doc("Do")는 그대로 Supabase 조회를 탄다.
    # (2026-08-20: aimlapi 결제 미반영 → Groq(Llama 미제공) → Together.ai로 최종 교체)
    # _LLAMA_TEST_MODE = True
    # if _LLAMA_TEST_MODE and service_code in ("In", "Ch"):
    #     _llama_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    #     _llama_api_key = os.getenv("LLAMA_API_KEY")  # .env: LLAMA_API_KEY (평문 하드코딩 금지)
    #     if service_code == "In":
    #         return (
    #             {grade: _llama_model for grade in _GRADE_MODEL_COLUMNS},
    #             _llama_api_key, "Llama", True, account_uid,
    #         )
    #     return (_llama_model, _llama_api_key, "Llama", True, account_uid)
    # ===================================================================

    import random as _random

    if supabase is None:
        supabase = get_service_client()

    multi_grade = service_code == "In"

    def _fetch(table, conditions):
        if multi_grade:
            cols = ", ".join(_GRADE_MODEL_COLUMNS.values())
            data = process_data_in_supabase(
                supabase, table, "select", {}, conditions, f"{cols}, encapikey"
            )
            if data:
                row = data[0]
                models = {grade: row.get(col) for grade, col in _GRADE_MODEL_COLUMNS.items()}
                return models, row["encapikey"]
            return None, None
        data = process_data_in_supabase(
            supabase, table, "select", {}, conditions, "llmmodelnm, encapikey"
        )
        if data:
            return data[0]["llmmodelnm"], data[0]["encapikey"]
        return None, None

    # ── 구독 플랜으로 is_customeraikey 판단 ─────────────────────────────
    is_customeraikey = True

    if account_uid or user_uid:
        try:
            if not account_uid:
                # account_uid 미전달 시 serviceusers에서 조회 (service_code + tenant_id로 필터)
                # tenant_id 없이 useruid+servicecd만으로 조회하면, 같은 유저가 여러 테넌트에
                # servicecd='Do' 등으로 소속된 경우(system tenant 개인 계정 + 다른 기업 테넌트 소속 등)
                # 행이 여러 개 나와 임의의(엉뚱한) accountuid가 선택될 수 있다.
                su_cond = {"useruid": user_uid}
                if service_code:
                    su_cond["servicecd"] = service_code
                if tenant_id:
                    su_cond["tenantid"] = tenant_id
                su = process_data_in_supabase(
                    supabase, "serviceusers", "select", {}, su_cond, "accountuid"
                )
                if su:
                    account_uid = su[0]["accountuid"]

            if account_uid:
                sub = process_data_in_supabase(
                    supabase, "subscriptions", "select", {}, {"accountuid": account_uid}, "productcd"
                )
                if sub:
                    product_cd = sub[0]["productcd"]
                    prod = process_data_in_supabase(
                        supabase, "products", "select", {}, {"productcd": product_cd}, "is_customeraikey"
                    )
                    if prod:
                        is_customeraikey = bool(prod[0]["is_customeraikey"])
        except Exception as _e:
            # print(f"[get_llm_info] 구독 플랜 조회 실패, 기본값(is_customeraikey=True) 사용: {_e}")
            pass

    llm_model, enc_api_key = None, None

    if is_customeraikey:
        # 고객 등록 키: projects 우선, 없으면 llmapikeys(accountuid+servicecd), 없으면 tenantid 폴백
        if project_id:
            llm_model, enc_api_key = _fetch("projects", {"projectid": project_id})
        if not llm_model and account_uid and service_code:
            llm_model, enc_api_key = _fetch("llmapikeys", {"accountuid": account_uid, "servicecd": service_code})
        if not llm_model and tenant_id:
            tenant_cond = {"tenantid": tenant_id}
            if service_code:
                tenant_cond["servicecd"] = service_code
            llm_model, enc_api_key = _fetch("llmapikeys", tenant_cond)
        if not llm_model:
            # BYOK 계정은 반드시 본인 키로만 동작해야 한다 — 아래 공용 fallback(시스템/무관 계정
            # llmapikeys 풀에서 무작위로 조회)으로 넘어가면 시스템 키나 심하면 다른 계정의 키가
            # 대신 사용될 수 있다(2026-08-14 발견). 본인 키 미등록 시에는 즉시 에러로 막는다.
            raise ValueError(
                "AI 키가 등록되지 않았습니다. 프로젝트 또는 계정 설정에서 사용할 LLM API 키를 등록해주세요."
            )
    else:
        # 서비스 제공 키: 시스템 테넌트의 llmapikeys 사용
        try:
            sys_tenant = process_data_in_supabase(
                supabase, "tenants", "select", {}, {"issystemtenant": True}, "tenantid"
            )
            if sys_tenant:
                tenant_id_supplier = sys_tenant[0]["tenantid"]
                au = process_data_in_supabase(
                    supabase, "accounts", "select", {}, {"tenantid": tenant_id_supplier, "accounttype": "T"}, "accountuid"
                )
                account_uid_supplier = au[0]["accountuid"]
                llmapikeys_cond = {
                    "tenantid": tenant_id_supplier,
                    "accountuid": account_uid_supplier,
                }
                if service_code:
                    llmapikeys_cond["servicecd"] = service_code
                llm_model, enc_api_key = _fetch("llmapikeys", llmapikeys_cond)
        except Exception as _e:
            # print(f"[get_llm_info] 서비스 제공 키 조회 실패: {_e}")
            pass

    if not llm_model:
        try:
            llm_data = process_data_in_supabase(
                supabase, "llmmodels", "select", {}, {"useyn": True, "is_doc": True}, "llmmodelnm"
            )
            fallback_model = _random.choice(llm_data)["llmmodelnm"]
            key_data = process_data_in_supabase(
                supabase, "llmapikeys", "select", {}, {"llmmodelnm": fallback_model, "useyn": True}, "encapikey"
            )
            enc_api_key = _random.choice(key_data)["encapikey"]
            # multi_grade면 세 등급 모두 이 폴백 모델로 채운다 — 그래야 호출부의 models[grade]
            # 접근이 등급과 무관하게 항상 값을 받는다(문자열로 되돌리면 "In" 호출부가
            # 딕셔너리 접근 중 TypeError를 낸다).
            llm_model = {grade: fallback_model for grade in _GRADE_MODEL_COLUMNS} if multi_grade else fallback_model
        except Exception:
            raise ValueError(
                "LLM 설정을 찾을 수 없습니다. "
                "projects 또는 llmapikeys 테이블에 llmmodelnm/encapikey를 설정하세요."
            )

    dec_api_key = decrypt_value(enc_api_key)
    # vendor 조회는 항상 모델명 문자열 하나가 필요하다 — multi_grade면 dict에서 하나 뽑아온다.
    # 세 등급은 같은 벤더(예: 전부 Anthropic)라는 전제이므로 어느 등급 값이든 상관없다.
    if multi_grade:
        vendor_lookup_model = llm_model.get("fast") or next((v for v in llm_model.values() if v), None)
        if not vendor_lookup_model:
            raise ValueError(
                "등급별 LLM 모델이 모두 비어 있습니다. "
                "projects 또는 llmapikeys 테이블에 llmmodelnm/llmmodelnm_smart/llmmodelnm_expert를 설정하세요."
            )
    else:
        vendor_lookup_model = llm_model
    vendor_name = process_data_in_supabase(
        supabase, "llmmodels", "select", {}, {"llmmodelnm": vendor_lookup_model}, "llmvendornm"
    )[0]["llmvendornm"]

    return llm_model, dec_api_key, vendor_name, is_customeraikey, account_uid


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

**중요: df는 이미 실행 환경에 실제 데이터로 정의되어 있습니다.**
- df = pd.DataFrame({{...}}) 형태로 df를 새로 생성하거나 샘플/예시 데이터로 재정의하지 마세요.
- 주석으로도 샘플 데이터 생성 코드를 작성하지 마세요.
- 주어진 df를 그대로 사용해서 분석 코드만 작성하세요.
"""


def detect_question_language(question: str) -> str:
    """
    질문 텍스트의 언어를 탐지하여 명시적 언어 지시문을 반환한다.
    한글/일어/중문은 유니코드 범위로 판별, 나머지는 langdetect 또는 영어 기본값.
    """
    if not question:
        return "IMPORTANT: Write ALL output text in English only."

    total = len([c for c in question if not c.isspace()])
    if total == 0:
        return "IMPORTANT: Write ALL output text in English only."

    korean_chars = sum(1 for c in question if '가' <= c <= '힣' or '㄰' <= c <= '㆏')
    if korean_chars / total > 0.05:
        return "IMPORTANT: 사용자 질문이 한국어입니다. 모든 출력 텍스트(차트 제목, 축 레이블, 범례, 테이블 컬럼명, 보고서 문장 등)를 한국어로 작성하세요."

    japanese_chars = sum(1 for c in question if '぀' <= c <= 'ヿ')
    if japanese_chars / total > 0.05:
        return "IMPORTANT: The user's question is in Japanese (日本語). Write ALL output text (chart titles, axis labels, legends, column names, report sentences, etc.) in Japanese only."

    chinese_chars = sum(1 for c in question if '一' <= c <= '鿿')
    if chinese_chars / total > 0.05:
        return "IMPORTANT: The user's question is in Chinese (中文). Write ALL output text (chart titles, axis labels, legends, column names, report sentences, etc.) in Chinese only."

    try:
        from langdetect import detect as _langdetect
        lang_code = _langdetect(question)
        lang_map = {
            "fr": "French (Français)",
            "de": "German (Deutsch)",
            "es": "Spanish (Español)",
            "it": "Italian (Italiano)",
            "pt": "Portuguese (Português)",
            "nl": "Dutch (Nederlands)",
            "ru": "Russian (Русский)",
        }
        if lang_code in lang_map:
            lang_name = lang_map[lang_code]
            return f"IMPORTANT: The user's question is in {lang_name}. Write ALL output text (chart titles, axis labels, legends, column names, report sentences, etc.) in {lang_name} only."
    except Exception:
        pass

    return "IMPORTANT: The user's question is in English. Write ALL output text (chart titles, axis labels, legends, column names, report sentences, etc.) in English only."

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


def detect_date_type_issues(df):
    """
    컬럼명에 'date'가 포함된 열에서, 날짜로 파싱되지 않는 값을 탐지한다.
    (예: 2025년은 윤년이 아닌데 "2025-02-29"처럼 존재하지 않는 날짜가 입력된 경우)

    Returns:
        list[dict]: [{"column": str, "invalid_count": int, "examples": [str, ...]}, ...]
    """
    issues = []
    date_cols = [col for col in df.columns if 'date' in col.lower()]
    for col in date_cols:
        original = df[col]
        parsed = pd.to_datetime(original, errors='coerce')
        invalid_mask = parsed.isna() & original.notna() & (original.astype(str).str.strip() != '')
        if invalid_mask.any():
            examples = original[invalid_mask].astype(str).unique().tolist()[:5]
            issues.append({
                "column": col,
                "invalid_count": int(invalid_mask.sum()),
                "examples": examples,
            })
    return issues


def get_dataframe_information(df):
    date_cols = [col for col in df.columns if 'date' in col.lower()]
    date_info = ""
    if date_cols:
        date_col = date_cols[0]
        parsed_dates = pd.to_datetime(df[date_col], errors='coerce')
        if parsed_dates.notna().any():
            date_info = f"\n    - 날짜: {parsed_dates.min()}~{parsed_dates.max()}"
    
    total_cols = len(df.columns)
    
    # 컬럼이 15개 이상일 때만 간소화
    if total_cols > 15:
        sample_cols = list(df.columns[:3])
        col_info = f"{sample_cols}...외{total_cols-3}개"
    else:
        col_info = str(list(df.columns)).replace('{', '{{').replace('}', '}}')
    
    return f"""df정보: 컬럼={col_info}, 크기={df.shape}{date_info}
"""


def get_charts_prompt(df, column_dict, question, ai_filter_json={}):

    lang_instruction = detect_question_language(question)
    df_info = get_dataframe_information(df)

    prompt = f"""{lang_instruction}

{df_info}

질문: {question}

컬럼 매핑:
{column_dict}

데이터 필터:
{ai_filter_json}

{prompt_common_text}

**중요 제약:**
    - 데이터 필터
         - ai_filter_json의 key는 컬럼명, value는 해당 컬럼에서 같은 값을 가지는 항목만 추출
         - ai_filter_json가 빈 딕셔너리일 경우는 필터가 적용되지 않음

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


def get_tables_prompt(df, column_dict, question, ai_filter_json={}):
    lang_instruction = detect_question_language(question)
    df_info = get_dataframe_information(df)

    prompt = f"""{lang_instruction}

{df_info}

질문: {question}

컬럼 매핑:
{column_dict}

데이터 필터:
{ai_filter_json}

{prompt_common_text}
    - result 라는 변수에 결과 값을 대입해주세요.

**중요 제약:**
    - openpyxl, xlsxwriter 등 엑셀 라이브러리 사용 금지
    - to_excel(), wb.save() 등 파일 저장 코드 금지
    - PatternFill, Workbook 등 엑셀 관련 객체 사용 금지
    - 오직 pandas DataFrame만 사용하세요
    - 데이터 필터
         - ai_filter_json의 key는 컬럼명, value는 해당 컬럼에서 같은 값을 가지는 항목만 추출
         - ai_filter_json가 빈 딕셔너리일 경우는 필터가 적용되지 않음

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


def get_sentences_prompt(df, column_dict, question, ai_filter_json={}):
    """
    통계 데이터 추출용 Python 코드 생성 프롬프트 (이상치 탐지 포함)

    Args:
        df: 분석 대상 데이터프레임 (익명화된 상태)
        column_dict: 컬럼 매핑 정보
        question: 사용자 질문

    Returns:
        str: LLM에 전달할 프롬프트
    """
    lang_instruction = detect_question_language(question)
    df_info = get_dataframe_information(df)

    prompt = f"""{lang_instruction}

{df_info}

질문: {question}

컬럼 매핑:
{column_dict}

데이터 필터:
{ai_filter_json}

{prompt_common_text}

**중요 제약:**
    - 데이터 필터
         - ai_filter_json의 key는 컬럼명, value는 해당 컬럼에서 같은 값을 가지는 항목만 추출
         - ai_filter_json가 빈 딕셔너리일 경우는 필터가 적용되지 않음

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
    - JSON 키는 위 언어 지시에 따라 작성하되, 사용자 질문과 관련된 의미 있는 이름을 사용하세요.
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


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


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

    lang_instruction = detect_question_language(user_question)
    stats_formatted = json.dumps(statistics_dict, ensure_ascii=False, indent=2, cls=NumpyEncoder)

    prompt = f"""{lang_instruction}

당신은 데이터 분석 보고서 작성 전문가입니다.
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
        # print(f"JSON 파싱 오류: {e}")
        pass
        # print(f"문제가 된 내용: {content[:200]}...")
    
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
        pass
        for original, anonymized in list(val_map.items())[:10]:  # 최대 10개만 출력
            # print(f"    {original:20s} -> {anonymized}")
            pass
        if len(val_map) > 10:
            # print(f"    ... and {len(val_map) - 10} more values")
            pass
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
        # print("[AUTO FIX] groupby().agg() 패턴 자동 수정됨")
        pass

    return fixed_code


def fix_numeric_only_pattern(code):
    """
    object 타입 컬럼에 집계 함수 적용 시 발생하는 오류 방지.
    인자 없는 집계 호출에 numeric_only=True 추가.
    예: .mean() → .mean(numeric_only=True)
    """
    agg_funcs = ['mean', 'sum', 'median', 'std', 'var']
    changed = False
    for func in agg_funcs:
        pattern = rf'\.{func}\(\)'
        replacement = rf'.{func}(numeric_only=True)'
        new_code = re.sub(pattern, replacement, code)
        if new_code != code:
            # print(f"[AUTO FIX] .{func}() → .{func}(numeric_only=True) 수정됨")
            pass
            code = new_code
            changed = True
    return code


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
    code = fix_numeric_only_pattern(code)

    aggregation_function = [
        ".sum", ".mean", ".median", ".min", ".max",
        ".count", ".size", ".std", ".var", ".prod", ".agg"
    ]

    is_single_in_code = ('groupby' not in code) and any(func in code for func in aggregation_function) 

    is_groupby_in_code = not is_single_in_code

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

    # object 타입 컬럼: null이 새로 생기지 않은 경우에만 숫자로 변환
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors='coerce')
            original_null = df[col].isna().sum()
            if converted.notna().any() and converted.isna().sum() == original_null:
                df[col] = converted

    try:
        exec(code, local_namespace)
        # exec(code, {"__builtins__": __builtins__}, local_namespace)
    except Exception as e:
        err_msg = str(e)
        # object dtype 컬럼 집계 오류 시 numeric_only 강제 적용 후 재시도
        if 'agg function failed' in err_msg and 'dtype->object' in err_msg:
            # print("[AUTO FIX] agg/dtype->object 오류 감지, numeric_only 강제 적용 후 재시도")
            pass
            retry_code = re.sub(r'\.(mean|sum|median|std|var)\((?!numeric_only)', r'.\1(numeric_only=True, ', code)
            try:
                exec(retry_code, local_namespace)
                code = retry_code
            except Exception as e2:
                # print("Error ", e2)
                pass
                return {
                    "status": "error",
                    "error": f"코드 실행 오류: {str(e2)}",
                    "code": retry_code,
                }
        else:
            # print("Error ", e)
            pass
            return {
                "status": "error",
                "error": f"코드 실행 오류: {err_msg}",
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
            
            num_cols = df_result.select_dtypes(include=["number"]).columns
            df_result[num_cols] = df_result[num_cols].round(2)

            table_style_prompt = get_table_style_combined(df_result, question)
            response_style = llm.invoke(table_style_prompt)
            style_json = clean_json_response(response_style.content)

            if hasattr(response_style, "response_metadata") and "usage" in response_style.response_metadata:
                usage = response_style.response_metadata["usage"]
                tokens["input_tokens"] += usage.get("input_tokens", 0)
                tokens["output_tokens"] += usage.get("output_tokens", 0)

            try:
                style_dict = json.loads(style_json)
            except (json.JSONDecodeError, ValueError):
                style_dict = {}
            table_header_json = json.dumps(style_dict.get("header", {}))
            table_data_json = json.dumps(style_dict.get("data", {}))

            # NaN → None 변환 (JSON 직렬화 안전, std() 단일항목 등)
            df_result = df_result.where(pd.notnull(df_result), other=None)
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

        def _fix_nans(obj):
            """NaN/Infinity → None 변환 (JSON 직렬화 안전)"""
            if isinstance(obj, dict):
                return {k: _fix_nans(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_fix_nans(item) for item in obj]
            if isinstance(obj, float) and not (obj == obj):  # NaN
                return None
            if isinstance(obj, float) and obj in (float('inf'), float('-inf')):
                return None
            if isinstance(obj, (np.floating,)) and np.isnan(obj):
                return None
            return obj
        result_obj = _fix_nans(result_obj)

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

    elif output_type == "DF_PREVIEW":

        if "result" in local_namespace and isinstance(local_namespace["result"], pd.DataFrame):
            df_result = local_namespace["result"]

            meta_info = {}
            for col in df_result.columns:
                dtype = str(df_result[col].dtype)
                meta_info[col] = {
                    "데이터형": dtype,
                    "측정값": dtype.startswith(("int", "float"))
                }
            meta_info["is_table_value"] = is_groupby_in_code
            cols_result = json.dumps(meta_info, ensure_ascii=False, indent=2)

            return {
                "result": df_result,
                "status": "dataframe",
                "tokens": tokens,
                "cols_info": cols_result
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
