"""
visualization.py — DataFrame 시각화 유틸리티 (d2chat · d2insight 공통)

- strip_markdown                     : 마크다운 문법 제거
- detect_visualization_type_with_llm : LLM으로 시각화 타입(표/차트/없음) 1차 감지
- decide_chart_type                  : 실제 데이터프레임 + 질문을 보고 차트 종류 최종 확정
- audit_chart_type_mismatch          : 사용자가 명시한 차트 종류와 최종 결정이 다르면 로그용 경고 반환
- decide_bar_orientation             : 막대류 차트 방향(세로/가로) 결정
- split_by_unit / split_by_magnitude : 단위(금액/비율)·규모 격차에 따라 여러 시각화로 분리
- detect_suspicious_uniform_ratio    : 비율 컬럼이 부자연스럽게 전부 동일하면 경고 (집계 오류 감지)
- dataframe_to_html_table            : DataFrame → HTML 테이블
- dataframe_to_chart_image           : DataFrame → (Base64 PNG, 데이터 JSON, 실패 사유 또는 None)

2026-08 pr_d2chat(단독앱)에서 이식 — 시각화 안정성/표현력 개선(원인 A~E, 막대 방향,
bubble/diverging 차트, 색상·값라벨·단위축약 등). dataframe_to_chart_image 반환값이
2-tuple → 3-tuple(실패 사유 추가)로 바뀌었으니 호출부는 항상 3개 값을 받을 것.
"""
import re
import os
import io
import json
import base64
import traceback
from typing import Optional

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker

# pr_module_insight(단독앱)에서 역이식(2026-08-20) — 폰트 설정은 프로세스당 한 번만
# 하면 되는데 dataframe_to_chart_image() 안에서 호출마다 반복 계산했었다.
_FONT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts', 'NanumGothic-Regular.ttf')
)
_font_loaded = False


def _ensure_font() -> None:
    global _font_loaded
    if _font_loaded:
        return
    if os.path.exists(_FONT_PATH):
        fm.fontManager.addfont(_FONT_PATH)
        font_prop = fm.FontProperties(fname=_FONT_PATH)
        matplotlib.rcParams['font.family'] = font_prop.get_name()
    else:
        _korean_candidates = ['Malgun Gothic', 'AppleGothic', 'NanumGothic', 'NanumBarunGothic']
        _available = {f.name for f in fm.fontManager.ttflist}
        for _candidate in _korean_candidates:
            if _candidate in _available:
                matplotlib.rcParams['font.family'] = _candidate
                break
    matplotlib.rcParams['axes.unicode_minus'] = False
    _font_loaded = True


# ========================================
# 마크다운 제거
# ========================================

def strip_markdown(text: str) -> str:
    """답변 텍스트에서 마크다운 문법 제거"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`{1,3}.*?`{1,3}', '', text, flags=re.DOTALL)
    text = re.sub(r'\|.+\|', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ========================================
# 시각화 타입 감지
# ========================================

def detect_visualization_type_with_llm(question: str, llm, log_ctx: dict = None) -> dict:
    """LLM으로 시각화 타입 감지"""
    prompt = f"""
다음 형식의 JSON으로만 답하세요.

사용자 질문:
"{question}"

규칙:
- 이미지 항목에 띄어 쓴 것이 있으면 붙여서 진행해주세요.
    - 예시 : "막대 그래프" -> "막대그래프", "원형 그래프" -> "원형그래프", "라인 차트" -> "라인차트"
- 영어와 한글을 혼용하여 사용한 경우는 해석하여 진행합니다.
    - 예시 : "파이차트" -> "원형그래프"
- 질문에 "테이블로", "표로", "도표로" 라는 표현이 있으면 반드시 visualization_type = "table"
- 질문에 "막대그래프"가 있으면 chart_type = "bar"
- 질문에 "선그래프" 또는 "라인그래프"가 있으면 chart_type = "line"
- 질문에 "원그래프" 또는 "원형그래프", "파이차트"가 있으면 chart_type = "pie"
- 질문에 "산점도", "분포도", "스캐터", "scatter"이 있으면 chart_type = "scatter"
- 질문에 "히스토그램", "histogram"이 있으면 chart_type = "histogram"
- 질문에 "박스플롯", "boxplot"이 있으면 chart_type = "boxplot"
- 질문에 "그래프", "차트", "시각화", "그려주세요"가 있으면 visualization_type = "chart"
- 질문에 "테이블", "표로 그려주세요" 등의 표현이 표작성을 의미하면 visualization_type = "table"
- **위 표현이 없을 경우 : 의미를 해석하여 적절한 시각화 형태(visualization_type)와 차트 형태(chart_type)를 결정합니다**

막대(bar) vs 선(line) 구분 규칙 - 매우 중요:
- 몇 개(2~3개)의 특정 시점을 카테고리(쇼핑몰/브랜드 등)별로 비교하는 질문(예: "작년 6월과 올해 6월을 쇼핑몰별로 비교")은 chart_type = "bar"(카테고리마다 시점별 막대를 나란히)로 표현하세요. 시점이 몇 개 안 되는데 line을 쓰면 마치 연속된 추이처럼 보여 오해를 줍니다.
- chart_type = "line"은 "추이", "변화 추이", "트렌드", "매달/매주 어떻게 변해왔는지"처럼 연속적인 시간 흐름 자체를 묻는 질문에만 사용하세요.

이중축(dual_axis) 판단 규칙:
- 질문에서 단위가 다른 두 종류의 데이터를 함께 표현해야 할 때 chart_type = "dual_axis"
- 예: "건수와 오류율을 함께", "매출액과 증감률을 같이", "수량과 비율을 하나의 그래프로"
- 한쪽은 절대값(건수/금액), 다른 한쪽은 비율/퍼센트인 경우 dual_axis가 적합

서브플롯(subplot) 판단 규칙:
- 질문에 "각각", "따로", "별도로", "개별" 같은 단어가 명시적으로 있을 때만 chart_type = "subplot"
- 예: "인터페이스별로 각각 그래프를 그려주세요", "항목별로 따로 차트로", "개별 그래프로"
- 명시적 키워드가 없으면 subplot을 선택하지 않고, 하나의 차트에 여러 시리즈로 표현

누적 막대(stacked) 판단 규칙:
- 대상(브랜드/그룹 등)마다 "매출/원가/비용이 어떤 항목들로 얼마나 구성되는지"를 비교해야 할 때 chart_type = "stacked" (기본값)
- 예: "매출에서 수수료와 배송비를 얼마나 떼이는지", "비용 구성을 비교해줘", "항목별로 얼마씩 나가는지 보여줘"
- 막대의 총 높이가 대상별 규모(예: 매출액) 차이를 그대로 보여주면서, 그 안에서 항목별 절대 금액이 쌓여서 비교됨
- 항목들의 합이 하나의 전체를 이루고, 그 구성을 대상끼리 비교하는 성격이면 dual_axis보다 stacked를 우선 선택

100% 누적 막대(stacked100) 판단 규칙:
- 대상마다 규모(예: 매출액) 차이는 무시하고 오직 "비중(%)"만 비교하고 싶다고 명시적으로 말했을 때만 chart_type = "stacked100"
- 예: "규모와 상관없이 구성비만 비교해줘", "비중으로만 봐줘", "100% 기준으로 비교"
- 명시적으로 비중만 요청한 게 아니라면 stacked100 대신 stacked를 선택

폭포수(waterfall) 판단 규칙:
- 하나의 시작값(예: 매출)에서 여러 증감 요인(비용, 할인 등)을 거쳐 최종값(예: 순이익)에 도달하는 "단계별 증감 과정"을 보여줘야 할 때 chart_type = "waterfall"
- 예: "매출에서 수수료, 배송비를 각각 빼면 순이익까지 어떻게 되는지", "단계별로 얼마씩 깎이는지 폭포수 차트로", "브릿지 차트로"
- 대상끼리의 비교가 아니라, 하나의 대상 안에서 항목별 증감이 누적되어 최종값으로 이어지는 구조일 때 stacked보다 waterfall이 적합

파레토(pareto) 판단 규칙:
- "상위 몇 개가 전체의 몇 %를 차지하는지", 항목을 큰 순서로 정렬하고 누적 비중을 함께 봐야 할 때 chart_type = "pareto"
- 예: "매출 상위 브랜드가 전체의 몇 %를 차지하는지", "파레토 차트로", "80/20 법칙으로 봐줘", "누적 비중과 함께 보여줘"

히트맵(heatmap) 판단 규칙:
- 두 개의 범주(예: 요일×시간대, 지역×카테고리)를 교차시켜 값의 크고 작음을 색으로 한눈에 봐야 할 때 chart_type = "heatmap"
- 예: "요일별 시간대별 오류 건수를 히트맵으로", "지역과 카테고리를 교차해서 매출을 보여줘"

결과 JSON:
{{
  "visualization_type": "chart | table | none",
  "chart_type": "bar | line | pie | scatter | histogram | boxplot | dual_axis | subplot | stacked | stacked100 | waterfall | pareto | heatmap | diverging_bar | null",
  "confidence": 0.0 ~ 1.0,
  "reasoning": "근거"
}}
"""
    try:
        from datetime import datetime
        from d2shared.llm_logger import log_llm_call

        def parse_llm_json_response(result):
            text = result.content.strip()
            json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
            json_str = json_match.group(1) if json_match else text
            return json.loads(json_str)

        start = datetime.now()
        raw_result = llm.invoke(prompt)
        end = datetime.now()

        usage = getattr(raw_result, 'usage_metadata', None) or {}
        log_llm_call(
            log_ctx=log_ctx,
            stepnm='viz_detect',
            steptitle='시각화 유형 감지',
            llmmodelnm=getattr(llm, 'model', 'unknown'),
            inputtoken=usage.get('input_tokens', 0),
            outputtoken=usage.get('output_tokens', 0),
            startdts=start,
            enddts=end,
        )

        return parse_llm_json_response(raw_result)

    except Exception as e:
        # print(f"[WARN] 시각화 타입 감지 오류: {e}")
        # 파싱 실패라고 해서 "시각화 필요 없음"으로 단정하면 안 된다. 질문에 시각화 관련
        # 키워드가 있으면 최소한 chart/table로 안전하게 처리한다. 별도 키워드 리스트를 새로
        # 만들지 않고, decide_chart_type()이 쓰는 기존 리스트들을 그대로 재사용한다 (모듈
        # 하단에서 정의되지만 이 함수는 호출 시점에 평가되므로 참조 가능).
        q = (question or '').lower()
        table_kw = ['표로', '테이블로', '도표로']
        chart_kw = set().union(
            _PIE_KEYWORDS, _LINE_KEYWORDS, _BAR_KEYWORDS, _HEATMAP_KEYWORDS,
            _WATERFALL_KEYWORDS, _PARETO_KEYWORDS, _SCATTER_KEYWORDS,
            _HIST_KEYWORDS, _BOX_KEYWORDS, {'그래프', '차트', '시각화', '그려'},
        )
        if any(kw in q for kw in table_kw):
            viz = 'table'
        elif any(kw in q for kw in chart_kw):
            viz = 'chart'
        else:
            viz = 'none'
        return {
            "visualization_type": viz,
            "chart_type": None,
            "confidence": 0.0,
            "reasoning": f"LLM 파싱 실패, 키워드 기반 안전 fallback 적용: {str(e)}"
        }


# ========================================
# 차트 종류 최종 결정 (데이터프레임이 나온 뒤, 실제 모양을 보고 확정)
# ========================================

_LINE_KEYWORDS = ['선', 'line', '추이', '변화', '트렌드', '매달', '매주', '라인차트']
_PIE_KEYWORDS = ['파이', 'pie', '원형', '점유율', '도넛', '도너츠', '원그래프', '구성비', '점유']
_SCATTER_KEYWORDS = ['산점도', 'scatter', '분포도']
_HIST_KEYWORDS = ['히스토그램', 'histogram']
_BOX_KEYWORDS = ['박스플롯', 'boxplot']
_DUAL_KEYWORDS = ['이중축', '이중 축']
_WATERFALL_KEYWORDS = ['폭포수', 'waterfall', '브릿지']
_PARETO_KEYWORDS = ['파레토', 'pareto', '80/20', '누적 비중']
_DIVERGING_KEYWORDS = ['평균 기준', '평균 대비', '기준선', 'diverging', '발산형']
_HEATMAP_KEYWORDS = ['히트맵', 'heatmap']
_STACKED100_KEYWORDS = ['100% 기준', '비중으로만', '규모와 상관없이', '구성비만']
_BAR_KEYWORDS = ['막대그래프', '막대 그래프']
_TIME_LABEL_KEYWORDS = ['월', 'year', '연도', '분기', 'quarter', 'date', '일자', '날짜']

# 질문의 "의미"를 분류하는 소프트 키워드 (명시적 차트 지정이 아니라, 질문이 어떤 성격을
# 묻는지 판단하는 용도. decide_chart_type() 2단계에서 데이터 특성과 함께 조합해서 쓴다)
_SHARE_KEYWORDS = ['비중', '구성', '차지', '떼이는지', '나뉘는지', '내역']            # 비율/구성을 묻는 질문
_CONTRIBUTION_KEYWORDS = ['대부분', '소수', '몇 %를 차지', '차지하는지', '집중하고', '얼마나 차지']  # 누적 기여도/쏠림을 묻는 질문
_RANK_KEYWORDS = ['상위', '하위', '순위', '가장 큰', '가장 작은', '많은 순', '적은 순']              # 규모/서열을 묻는 질문


def _looks_like_time_labels(series: pd.Series) -> bool:
    """라벨 컬럼이 시간(월/분기/날짜 등) 순서를 나타내는지 판단"""
    name = str(getattr(series, 'name', '') or '').lower()
    if any(kw in name for kw in _TIME_LABEL_KEYWORDS):
        return True
    try:
        sample = series.astype(str).head(5)
        return bool(sample.str.match(r'^\d{4}[-./]?\d{0,2}$|^\d{1,2}월$|^\d{4}년').any())
    except Exception:
        return False


_TIME_PREFIX_RE = re.compile(r'^\d{4}[-./]?\d{0,2}|^\d{1,2}월|^\d{4}년')


def _column_names_look_like_time(names) -> bool:
    """컬럼 '이름' 문자열 자체가 시간을 나타내는지 판단한다 (라벨 "값"이 아니라 컬럼명).
    "4월"처럼 정확히 일치하는 경우뿐 아니라 "4월_판매수량"처럼 시간 토큰 뒤에 설명이 덧붙은
    경우도 인식하도록 접두어만 맞으면 인정한다 — _looks_like_time_labels()는 값 전체가
    정확히 시간형이어야 하는 라벨 컬럼용이라 이 경우엔 너무 엄격하다."""
    names = [str(n) for n in names]
    if not names:
        return False
    hits = sum(1 for n in names if _TIME_PREFIX_RE.match(n))
    return hits >= max(2, int(len(names) * 0.6))


def _row_magnitude_ratio(df: pd.DataFrame, numeric_cols: list) -> float:
    """비교 대상(행)별 수치 규모(지정된 컬럼들의 합)가 최대 몇 배 차이 나는지 반환한다.
    계산할 수 없으면(컬럼 없음/비교 가능한 행이 1개 이하/전부 0 이하) 격차 없음을 뜻하는
    1.0을 반환한다."""
    if not numeric_cols or df.empty:
        return 1.0
    totals = df[numeric_cols].apply(pd.to_numeric, errors='coerce').abs().sum(axis=1)
    positive = totals[totals > 0]
    if len(positive) < 2:
        return 1.0
    return float(positive.max() / positive.min())


def _has_negative_values(df: pd.DataFrame) -> bool:
    """파이차트가 못 그리는 음수 값이 라벨 뒤 숫자 컬럼에 있는지 확인한다.
    matplotlib의 ax.pie()는 음수 조각을 그리지 못하고 예외를 낸다(반품/환불 등으로
    순매출이 마이너스인 항목이 섞여 있으면 발생) — 파이를 고르기 전에 미리 걸러낸다."""
    if df is None or df.empty or len(df.columns) < 2:
        return False
    for col in df.columns[1:]:
        if pd.api.types.is_numeric_dtype(df[col]):
            if (pd.to_numeric(df[col], errors='coerce') < 0).any():
                return True
    return False


def decide_chart_type(df: pd.DataFrame, question: str, hint: str = None) -> str:
    """실제 데이터프레임과 질문 문장을 함께 보고 차트 종류를 최종 결정한다.

    특정 질문 문구 하나하나에 대응하는 규칙을 계속 추가하는 대신, 아래 두 축의 조합으로
    판단하는 공통 로직을 쓴다:
      1) 사용자가 차트 종류를 콕 집어 요청했는가 (명시적 키워드 - 최우선)
      2) 아니라면, 데이터의 실제 특성(비교 대상 개수, 대상 간 규모 격차, 지표들의 단위가
         같은지)과 질문의 의미(비중/구성을 묻는지, 규모/순위를 묻는지, 누적 기여도를
         묻는지, 추이를 묻는지)를 함께 봐서 결정한다.
    hint(질문 텍스트만 보고 쿼리 실행 전에 미리 낸 추정치)는 최종 fallback으로도 신뢰하지
    않는다 - 데이터 모양과 안 맞는 힌트를 그대로 썼다가 반복적으로 어색한 차트(예: 규모
    격차가 큰데도 파이, 명시적 요청도 없는데 서브플롯)가 나온 원인이었다."""
    q = (question or '').lower()
    q_nospace = q.replace(' ', '')

    def has(keywords):
        # 띄어쓰기 차이("원 그래프" vs "원형")로 매칭이 빠지지 않도록 공백을 무시하고 비교한다.
        return any(kw.replace(' ', '') in q_nospace for kw in keywords)

    # 1) 명시적 키워드 (사용자가 콕 집어 요청한 것 - 최우선, 데이터 모양보다 우선)
    if has(_HEATMAP_KEYWORDS):
        return 'heatmap'
    if has(_WATERFALL_KEYWORDS):
        return 'waterfall'
    if has(_PARETO_KEYWORDS):
        return 'pareto'
    if has(_DIVERGING_KEYWORDS):
        return 'diverging_bar'
    if has(_DUAL_KEYWORDS):
        return 'dual_axis'
    # 서브플롯 자동 트리거는 제거함 — "각각" 같은 단어가 사용자 원문이 아니라 LLM이 재구성한
    # 조회 문장에 우연히 섞여 들어가면서 의도치 않게 서브플롯으로 빠지는 문제가 있었고,
    # 실사용 빈도도 낮아 자동 판별 대상에서 제외하기로 함 (렌더링 코드 자체는 남겨둠).
    if has(_BOX_KEYWORDS):
        return 'boxplot'
    if has(_HIST_KEYWORDS):
        return 'histogram'
    if has(_SCATTER_KEYWORDS):
        return 'scatter'
    if has(_PIE_KEYWORDS):
        return 'bar' if _has_negative_values(df) else 'pie'
    if has(_STACKED100_KEYWORDS):
        return 'stacked100'
    if has(_BAR_KEYWORDS):
        return 'bar'
    if has(_LINE_KEYWORDS):
        # "선/추이"라고 해도 실제 시점이 2~3개뿐이면 bar가 더 적절 (연속 추이처럼 오해되는 것 방지)
        if df is not None and not df.empty and len(df) <= 3:
            return 'bar'
        return 'line'

    if df is None or df.empty or len(df.columns) < 2:
        return 'bar'

    label_col = df.columns[0]
    value_cols = list(df.columns[1:])
    numeric_value_cols = [c for c in value_cols if pd.api.types.is_numeric_dtype(df[c])]

    # 3컬럼[문자,문자,숫자]이고 두 번째 문자열 컬럼이 여러 행에 걸쳐 반복되면 교차표(heatmap) 후보.
    # 단, 두 번째 범주가 2~3개뿐이면(예: "작년 6월"/"올해 6월" 딱 2개 시점) 매트릭스로 볼 이유가
    # 없고 그룹형 막대가 더 잘 읽힌다 — 그래서 그 축의 고유값이 최소 이 개수는 돼야 히트맵을 허용한다.
    _MIN_HEATMAP_CATEGORIES = 4
    if len(df.columns) == 3 and numeric_value_cols == [df.columns[-1]]:
        cat_col = df.columns[-2]
        if (not pd.api.types.is_numeric_dtype(df[cat_col])
                and df[cat_col].nunique() >= _MIN_HEATMAP_CATEGORIES):
            repeats = len(df) / max(df[cat_col].nunique(), 1)
            if repeats >= 1.5:
                return 'heatmap'

    # 순수 시계열: 라벨이 시간형이고 지점이 4개 이상
    if _looks_like_time_labels(df[label_col]) and len(df) >= 4:
        return 'line'

    if not numeric_value_cols:
        return 'bar'

    # 2) 데이터 특성 추출 - 이후 판단의 공통 근거
    amount_cols = [c for c in numeric_value_cols if not _is_ratio_column(c, df[c])]
    ratio_cols = [c for c in numeric_value_cols if _is_ratio_column(c, df[c])]
    n_entities = len(df)
    magnitude_ratio = _row_magnitude_ratio(df, amount_cols)  # 대상(행)별 규모가 몇 배 벌어지는지
    has_negative = bool(amount_cols) and any(
        (pd.to_numeric(df[c], errors='coerce') < 0).any() for c in amount_cols
    )

    is_share_q = has(_SHARE_KEYWORDS)               # 비율/비중/구성을 묻는가
    is_contribution_q = has(_CONTRIBUTION_KEYWORDS)  # 누적 기여도/쏠림(소수가 대부분을 차지)을 묻는가
    is_rank_q = has(_RANK_KEYWORDS)                  # 규모/순위를 묻는가

    # 2-0) "평균을 기준으로 상위/하위를 비교" 류 질문 — "소수 브랜드가 이익 대부분을 만들고
    #      있다면"처럼 쏠림 표현(_CONTRIBUTION_KEYWORDS)이 함께 있어도, 사용자가 "평균 기준"
    #      이라는 구체적인 계산 방식을 직접 지정했다면 그 명시적 지시가 더 우선한다. 그래서
    #      2-1(파레토)보다 먼저 체크한다. "평균을 기준으로"처럼 두 단어 사이에 조사가 끼어도
    #      잡히도록 "평균"과 "기준"이 (붙어 있지 않아도) 함께 있는지로 판단한다.
    if '평균' in q_nospace and ('기준' in q_nospace or is_rank_q) and len(amount_cols) == 1:
        return 'diverging_bar'

    # 2-1) 누적 기여도: "소수가 대부분을 차지하는지" 류의 쏠림/집중도 질문이면 정렬된 막대 +
    #      누적 비중선(파레토)으로 "상위 몇 개가 몇 %인지"를 바로 보여준다. 비교 대상이 너무
    #      적으면(<4) 파레토의 의미가 없고, 음수(적자 등)가 섞이면 누적 비중 계산이 왜곡되므로 제외.
    # 파레토는 렌더링에서 values.columns[0] 하나만 그리고 나머지는 버리므로, breakdown 지표가
    # 2개 이상인 데이터(예: 매출-수수료-배송비 비교)엔 구조적으로 안 맞는다.
    # 그런 경우는 아래 2-2(stacked/stacked100)로 넘겨서 지표를 전부 반영한다.
    if is_contribution_q and len(amount_cols) == 1 and n_entities >= 4 and not has_negative:
        return 'pareto'

    # 2-2) 비중/구성: 대상마다 금액 지표 2개 이상으로 "구성"을 비교하는 질문. 대상 간 규모
    #      격차가 크면(8배 이상) 절대금액 스택은 큰 대상이 작은 대상을 가려버리므로, 규모를
    #      무시하고 비중(%)만 비교하는 stacked100으로 자동 전환한다.
    if is_share_q and len(amount_cols) >= 2:
        return 'stacked100' if magnitude_ratio >= 8 else 'stacked'

    # 2-3) 단위(금액 vs 비율)가 다른 지표를 함께 다뤄야 하면 같은 y축에 나열하지 않는다.
    #      실제로 하나의 이중축 그래프로 그릴지, 별도 플롯 여러 개로 쪼갤지는 호출자의
    #      split_by_unit()이 판단하며, 여기서는 그 판단이 필요한 후보라는 것만 표시한다.
    if amount_cols and ratio_cols:
        return 'dual_axis'

    # 2-4) 규모/순위 비교: "상위/하위/순위"를 묻는 질문은 정렬된 막대가 파이보다 항상 정확하다
    if is_rank_q:
        return 'bar'

    # 2-5) 단일 금액 지표 비교: 대상이 2~5개이고 규모 격차가 크지 않으면 파이도 가능하지만,
    #      대상이 6개 이상이거나 격차가 크면(파이는 조각이 안 보이거나 왜곡) 막대를 우선한다.
    if len(amount_cols) == 1:
        if 2 <= n_entities <= 5 and magnitude_ratio < 8 and not _has_negative_values(df):
            return 'pie'
        return 'bar'

    return 'bar'


# 각 chart_type이 대응하는 명시적 키워드 리스트. decide_chart_type()이 이미 쓰는 리스트를
# 그대로 재사용해서, 감사(audit) 로직이 실제 매칭 로직과 따로 놀지(드리프트) 않게 한다.
_CHART_TYPE_KEYWORD_MAP = {
    'pie': _PIE_KEYWORDS, 'line': _LINE_KEYWORDS, 'bar': _BAR_KEYWORDS,
    'heatmap': _HEATMAP_KEYWORDS, 'waterfall': _WATERFALL_KEYWORDS, 'pareto': _PARETO_KEYWORDS,
    'boxplot': _BOX_KEYWORDS, 'histogram': _HIST_KEYWORDS, 'scatter': _SCATTER_KEYWORDS,
    'dual_axis': _DUAL_KEYWORDS, 'stacked100': _STACKED100_KEYWORDS,
    'diverging_bar': _DIVERGING_KEYWORDS,
    # 'subplot'은 자동 트리거를 껐으므로 감사 대상에서도 제외 (안 그러면 "각각" 있는데
    # subplot이 아니라고 매번 거짓 MISMATCH 경고가 찍힘)
}


def audit_chart_type_mismatch(question: str, final_chart_type: str) -> Optional[str]:
    """사용자가 질문에서 명시한 차트 종류와 최종 결정된 chart_type이 다르면 감사용 경고
    문자열을 반환한다 (UI 노출 없이 운영 로그 추적 전용). 이상 없으면 None."""
    q = (question or '').lower().replace(' ', '')
    for expected, keywords in _CHART_TYPE_KEYWORD_MAP.items():
        if any(kw.replace(' ', '') in q for kw in keywords) and final_chart_type != expected:
            return f"[MISMATCH] 질문에 '{expected}' 계열 키워드가 포함되었으나 최종 chart_type='{final_chart_type}'로 결정됨"
    return None


def decide_bar_orientation(df: pd.DataFrame, question: str) -> str:
    """막대류 차트를 세로('v')로 그릴지 가로('h')로 그릴지 결정한다.
    순위/기준대비 성격의 질문이거나, 라벨이 길거나 항목이 많으면 가로가 더 읽기 좋다."""
    q = (question or '').lower()
    if any(kw in q for kw in _RANK_KEYWORDS) or '대비' in q:
        return 'h'
    if df is None or df.empty:
        return 'v'
    label_col = df.columns[0]
    if df[label_col].astype(str).map(len).max() >= 6 or len(df) >= 7:
        return 'h'
    return 'v'


# ========================================
# DataFrame 전처리
# ========================================

def _looks_like_time_part_values(series: pd.Series) -> bool:
    """실제 값이 월/일/분기 같은 시간의 '부분'처럼 작은 범위인지 확인한다.
    컬럼명에 우연히 시간 키워드가 들어간 값 컬럼(예: "월별_매출합계")을 시간 컬럼으로
    오인해 진짜 날짜 컬럼과 합쳐버리는 것을 막기 위한 안전장치 — 이름만 보지 않고 값도 본다."""
    try:
        if pd.api.types.is_numeric_dtype(series):
            return bool(series.between(1, 100).all())
        sample = series.astype(str).head(10)
        return bool(sample.str.match(r'^\d{1,2}(월|일|분기)?$').all())
    except Exception:
        return False


def _prepare_dataframe_for_visualization(df: pd.DataFrame, chart_type: str = None) -> pd.DataFrame:
    """DataFrame을 시각화에 적합한 형태로 변환"""
    if df.empty or len(df.columns) < 2:
        return df

    df = df.copy()

    time_keywords = ['년도', 'year', '연', '월', 'month', '일', 'day', '분기', 'quarter']
    exclude_keywords = ['요일', 'weekday', 'dayofweek', 'dow']

    time_cols = []
    for col in df.columns:
        col_lower = str(col).lower()
        if any(kw in col_lower for kw in exclude_keywords):
            break
        is_time_col = any(kw in col_lower for kw in time_keywords) and _looks_like_time_part_values(df[col])
        is_year_like = (
            pd.api.types.is_numeric_dtype(df[col]) and
            df[col].between(1900, 2100).all()
        ) if len(df) > 0 else False

        if is_time_col or is_year_like:
            time_cols.append(col)
        else:
            break

    if len(time_cols) >= 2:
        def combine_time_parts(row):
            parts = []
            for col in time_cols:
                val = row[col]
                if isinstance(val, str) and '-' in val:
                    return val
                try:
                    if '월' in str(col).lower() or 'month' in str(col).lower():
                        parts.append(f"{int(val):02d}")
                    elif '일' in str(col).lower() or 'day' in str(col).lower():
                        parts.append(f"{int(val):02d}")
                    else:
                        parts.append(str(int(val)))
                except Exception:
                    parts.append(str(val))
            return '-'.join(parts)

        combined_name = '-'.join(time_cols)
        df[combined_name] = df.apply(combine_time_parts, axis=1)
        df = df.drop(columns=time_cols)
        cols = [combined_name] + [c for c in df.columns if c != combined_name]
        df = df[cols]

    if len(df.columns) >= 3:
        last_numeric = pd.api.types.is_numeric_dtype(df.iloc[:, -1])
        cat_col_series = df.iloc[:, -2]
        # 문자열 컬럼뿐 아니라, "년"처럼 숫자형이지만 값 종류가 적은(범주형) 컬럼도 피벗 기준으로
        # 인정한다. 안 그러면(기존엔 is_string_dtype만 인정) 예: [쇼핑몰, 년(int), 판매금액] 같은
        # 데이터에서 피벗이 아예 안 걸려서, "년" 컬럼이 두 번째 값(시리즈)인 것처럼 잘못 그려진다
        # (범례에 "년"이라는 컬럼명 자체가 뜨고 2025/2026 숫자가 막대 높이로 잘못 들어감).
        # 단, 이 숫자형 범주 허용은 정확히 3컬럼([라벨,범주,값])일 때만 적용한다 — 컬럼이 4개
        # 이상이면(예: [브랜드,매출,수수료,배송비]) 전부 진짜 지표일 수 있으므로, 그런 경우까지
        # 숫자형이라는 이유만으로 범주로 오판해 피벗해버리지 않도록 기존처럼 문자열만 인정한다.
        second_last_categorical = (
            pd.api.types.is_string_dtype(cat_col_series)
            or (
                len(df.columns) == 3
                and pd.api.types.is_numeric_dtype(cat_col_series)
                and len(df) > 0
                and cat_col_series.nunique() <= max(10, len(df) // 2)
            )
        )
        if last_numeric and second_last_categorical and chart_type != 'scatter':
            try:
                # line 차트일 때만 시간축을 index(=피벗 후 첫 컬럼, x축)로 강제한다. 원본 조회
                # 결과가 [엔티티, 시간, 값] 순서로 오면 무조건 df.columns[0]을 index로 쓸 때
                # 엔티티가 x축, 시간이 범례가 되어 line 방향이 뒤집히기 때문. 반대로 bar류(예:
                # "작년 6월 vs 올 6월 쇼핑몰별 비교")는 엔티티(쇼핑몰)가 x축, 시간(년)이 범례로
                # 남아야 그룹형 막대로 자연스럽게 비교되므로 여기서 순서를 건드리지 않는다.
                first_col, cat_col = df.columns[0], df.columns[-2]
                if (chart_type == 'line'
                        and not _looks_like_time_labels(df[first_col])
                        and _looks_like_time_labels(df[cat_col])):
                    index_col, columns_col = cat_col, first_col
                else:
                    index_col, columns_col = first_col, cat_col
                pivoted = df.pivot(
                    index=index_col,
                    columns=columns_col,
                    values=df.columns[-1]
                ).reset_index()
                # 행마다 두 번째 컬럼(피벗 기준)이 사실상 다 다른 값이면(예: 브랜드마다 고유한
                # "순위_번호" 라벨), 피벗 결과 대부분이 빈 칸인 희소 행렬이 된다. 이건 진짜
                # "카테고리 비교"가 아니라 우연히 3컬럼 조건에 걸린 것이므로 피벗을 취소한다.
                value_cols = pivoted.columns[1:]
                fill_ratio = pivoted[value_cols].notna().mean().mean() if len(value_cols) else 1.0
                if fill_ratio >= 0.4:
                    pivoted.columns.name = None
                    df = pivoted
            except Exception:
                pass

    # line 차트인데 이미 wide-format으로 와 있고(피벗 불필요) 방향이 반대인 경우: 라벨 컬럼
    # (0번째)은 시간처럼 안 보이는데, 나머지 값 컬럼들의 "이름" 자체가 시간처럼 보이면
    # (예: 컬럼명이 "4월","5월","6월") 엔티티가 행, 시간이 열로 온 것 — 표를 전치해서
    # 시간을 행(x축)으로, 엔티티를 열(선 하나씩)로 바로잡는다.
    if chart_type == 'line' and len(df.columns) >= 3:
        label_col = df.columns[0]
        if not _looks_like_time_labels(df[label_col]) and _column_names_look_like_time(df.columns[1:]):
            entity_names = df[label_col].astype(str).tolist()
            transposed = df.set_index(label_col).T.reset_index()
            transposed.columns = ['기간'] + entity_names
            df = transposed

    return df


# ========================================
# HTML 테이블 변환
# ========================================

def dataframe_to_html_table(df: pd.DataFrame, max_rows: int = 100) -> tuple:
    """DataFrame → (HTML 테이블, 전처리된 DataFrame JSON 문자열)"""
    if df.empty:
        return "<p>데이터가 없습니다.</p>", "[]"

    df = _prepare_dataframe_for_visualization(df, chart_type=None)
    data_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str)
    display_df = df.head(max_rows)

    first_col = display_df.columns[0]
    numeric_cols = [
        col for col in display_df.select_dtypes(include='number').columns
        if col != first_col
    ]
    text_cols = [col for col in display_df.columns if col not in numeric_cols]

    def smart_format(series):
        abs_max = series.abs().max()
        if pd.isna(abs_max):
            return lambda x: ""
        if abs_max >= 100:
            return lambda x: f"{x:,.0f}" if pd.notna(x) else ""
        elif abs_max >= 1:
            return lambda x: f"{x:,.2f}" if pd.notna(x) else ""
        else:
            return lambda x: f"{x:,.2f}" if pd.notna(x) else ""

    styler = display_df.style.hide(axis="index")
    styler = styler.format(
        {col: smart_format(display_df[col]) for col in numeric_cols},
        na_rep=""
    )
    styler = styler.set_table_styles([
        {"selector": "th", "props": [("text-align", "center")]}
    ])
    if numeric_cols:
        styler = styler.set_properties(subset=numeric_cols, **{"text-align": "right"})
    if text_cols:
        styler = styler.set_properties(subset=text_cols, **{"text-align": "left"})

    return styler.to_html(), data_json


# ========================================
# 차트 이미지 변환
# ========================================

_RATIO_KEYWORDS = ['율', '률', '비율', '%', 'rate', 'ratio', 'pct', 'percent']
_WHOLE_KEYWORDS = ['매출', '판매금액', '판매액', '전체금액', '합계금액', '총매출', '총액']
_PROFITABILITY_KEYWORDS = ['순이익률', '마진율', '수익률', '이익률', '수익성', 'margin', 'profit']
# 건수/수량류 컬럼 — 금액(단가·매출 등)과 같은 축에 그리면 서로 다른 단위(개 vs $)가
# 비슷한 막대 길이로 표시돼 오독을 유발한다(2026-08-19, 단가 차트에서 평균단가($)와
# 판매건수(개)가 같은 축에 그려진 것 확인) — 비율 컬럼과 별개로 이 컬럼도 금액 컬럼과
# 섞이면 dual_axis로 분리한다.
_COUNT_KEYWORDS = ['건수', '수량', '개수', 'count', 'qty', 'quantity', 'cnt']

# 의미 기반 색상 팔레트 (차트 종류에 관계없이 공용으로 사용)
_C_GREEN = '#1baf7a'        # 증가/달성/집중
_C_RED = '#e34948'          # 감소/미달/적자/정리검토
_C_RED_STRONG = '#c0392b'   # 감소폭이 두드러지는 경우 강조
_C_GRAY = '#b4b2a9'         # 기준값/평균 근처/유지·관찰/보합
_C_BLUE = '#2a78d6'         # 평균 이상/집중(파레토)
_C_ORANGE = '#eb6834'       # 평균 이하/최댓값 강조
_C_LIGHT_BLUE = '#9fc5f0'   # highlight_max에서 강조 대상 외 나머지


def _is_ratio_column(col_name, series: pd.Series) -> bool:
    """컬럼명 또는 값 범위로 비율(%) 컬럼인지 판단"""
    col_lower = str(col_name).lower()
    if any(kw in col_lower for kw in _RATIO_KEYWORDS):
        return True
    try:
        return bool(len(series) and series.max() <= 100 and series.min() >= 0)
    except Exception:
        return False


def _is_count_column(col_name) -> bool:
    """컬럼명으로 건수/수량류(단위: 개)인지 판단 — 값 범위만으로는 금액과 구분 안 됨."""
    col_lower = str(col_name).lower()
    return any(kw in col_lower for kw in _COUNT_KEYWORDS)


def _pick_color_strategy(chart_type, col_name, series: pd.Series) -> str:
    """색상 전략을 데이터 특성으로 자동 판단한다 (적용 우선순위: waterfall > 음수 포함 > 수익성 컬럼명 > 기본).
    LLM 판단 없이도 대부분의 경우를 결정론적으로 커버한다."""
    if chart_type == 'waterfall':
        return 'delta'
    try:
        numeric = pd.to_numeric(series, errors='coerce')
        if (numeric < 0).any():
            return 'delta'
    except Exception:
        pass
    if any(kw in str(col_name) for kw in _PROFITABILITY_KEYWORDS):
        return 'profitability'
    return 'default'


def _colors_for_strategy(series: pd.Series, strategy: str) -> list:
    """전략 이름에 따라 막대 하나하나의 색상 리스트를 반환한다."""
    numeric = pd.to_numeric(series, errors='coerce').fillna(0)

    if strategy == 'delta':
        return [_C_GRAY if v == 0 else (_C_GREEN if v > 0 else _C_RED) for v in numeric]

    if strategy == 'profitability':
        avg = numeric.mean()
        band = abs(avg) * 0.2
        colors = []
        for v in numeric:
            if v <= 0:
                colors.append(_C_RED)
            elif abs(v - avg) <= band:
                colors.append(_C_GRAY)
            elif v > avg:
                colors.append(_C_BLUE)
            else:
                colors.append(_C_ORANGE)
        return colors

    if strategy == 'highlight_max':
        if numeric.empty:
            return []
        max_pos = numeric.abs().values.argmax()
        return [_C_ORANGE if i == max_pos else _C_LIGHT_BLUE for i in range(len(numeric))]

    return [_C_BLUE] * len(numeric)


def split_by_unit(df: pd.DataFrame) -> list:
    """금액(절대값)과 비율(%) 컬럼이 함께 있으면 단위별로 별도 플롯을 그리도록 데이터프레임을
    쪼갠다. 억지로 이중축(dual_axis) 하나에 우겨넣는 것보다, 각자 스케일에 맞는 단일 지표
    차트 여러 개로 나누는 편이 대개 더 잘 읽힌다. 나눌 필요 없으면 [df] 그대로 반환."""
    if df.empty or len(df.columns) < 3:
        return [df]

    label_col = df.columns[0]
    value_cols = list(df.columns[1:])
    ratio_cols = [c for c in value_cols if _is_ratio_column(c, df[c])]
    amount_cols = [c for c in value_cols if c not in ratio_cols]
    if not ratio_cols or not amount_cols:
        return [df]

    # 비율 컬럼과 이름이 대응되는 금액 컬럼(예: "순이익률" ↔ "순이익금액")은 중복 정보라 제외
    def _ratio_stem(col_name):
        s = str(col_name)
        for suf in ('비율', '률', '율'):
            if s.endswith(suf):
                return s[:-len(suf)]
        return None

    stems = [st for st in (_ratio_stem(c) for c in ratio_cols) if st]
    filtered_amounts = [c for c in amount_cols if not any(stem in str(c) for stem in stems)]
    amount_cols = filtered_amounts or amount_cols

    return [df[[label_col] + amount_cols], df[[label_col] + ratio_cols]]


def split_by_magnitude(df: pd.DataFrame) -> list:
    """엔티티(행)별 규모(수치 컬럼 합)가 극심하게(8배 이상) 벌어지면 상위/하위 그룹으로 나눠
    반환한다. 100%로 정규화하지 않고도, 그룹 안에서는 절대금액 스케일이 유지되면서 작은
    엔티티가 큰 엔티티에 가려 안 보이는 것을 막기 위함. 나눌 필요 없으면 [df] 그대로 반환."""
    if df.empty or len(df.columns) < 2 or len(df) < 4:
        return [df]

    numeric_cols = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return [df]

    # 비율(%) 컬럼끼리는 이미 0~100 좁은 범위라 "규모 격차"라는 개념 자체가 적용되지 않는다.
    # (예: 브랜드별 수수료율·배송비율은 8배 차이가 나도 나눠서 비교할 이유가 없음)
    if all(_is_ratio_column(c, df[c]) for c in numeric_cols):
        return [df]

    totals = df[numeric_cols].abs().sum(axis=1)
    order = totals.sort_values(ascending=False).index
    sorted_df = df.loc[order].reset_index(drop=True)
    sorted_totals = totals.loc[order].reset_index(drop=True)

    if sorted_totals.iloc[-1] <= 0:
        return [df]

    # 인접한 두 엔티티 사이에 규모가 8배 이상 벌어지는 지점을 찾아 그 경계로 상/하위를 나눈다
    split_idx = None
    for i in range(1, len(sorted_totals)):
        prev, cur = sorted_totals.iloc[i - 1], sorted_totals.iloc[i]
        if cur > 0 and prev / cur >= 8:
            split_idx = i
            break

    if split_idx is None or split_idx >= len(sorted_df) - 1:
        return [df]

    upper = sorted_df.iloc[:split_idx].reset_index(drop=True)
    lower = sorted_df.iloc[split_idx:].reset_index(drop=True)
    return [upper, lower]


def detect_suspicious_uniform_ratio(data) -> str:
    """조회 결과(list[dict])에서 비율/증감률처럼 보이는 컬럼의 값이 3개 이상 행에서
    완전히 동일하면, 그룹별로 제대로 계산되지 않았을 가능성(예: 전체 집계값이 실수로
    모든 그룹에 재사용됨)을 경고 문자열로 반환한다. 이상 없으면 None.
    Tool 계층에서 SQL/pandas 결과를 반환하기 직전에 호출하는 용도."""
    if not isinstance(data, list) or len(data) < 3:
        return None
    first_row = next((row for row in data if isinstance(row, dict)), None)
    if not first_row:
        return None

    for col in first_row.keys():
        if not any(kw in str(col).lower() for kw in _RATIO_KEYWORDS):
            continue
        numeric_values = [
            row.get(col) for row in data
            if isinstance(row, dict) and isinstance(row.get(col), (int, float)) and not isinstance(row.get(col), bool)
        ]
        if len(numeric_values) >= 3 and len(set(round(v, 4) for v in numeric_values)) == 1:
            return (
                f"'{col}' 값이 {len(numeric_values)}개 행 모두 {numeric_values[0]}로 동일합니다. "
                f"그룹별로 올바르게 계산됐는지 재확인이 필요합니다."
            )
    return None


def dataframe_to_chart_image(df: pd.DataFrame, question: str, chart_type: str = None) -> tuple:
    """DataFrame → (Base64 PNG 이미지, 전처리된 DataFrame JSON 문자열, 실패 사유 또는 None).
    렌더링이 실패하면 (None, None, 에러메시지)를 반환한다 — 호출부가 실패 사실을 알 수 있게
    사유를 함께 돌려준다 (예전에는 (None, None)만 반환해 실패가 조용히 사라졌었다)."""
    import matplotlib.ticker as mticker

    if df.empty or len(df.columns) < 2:
        return None, None, None

    def _make_colors(cmap, n):
        return [cmap(i / n) for i in range(n)]

    def _set_axes(ax, xlabel='', ylabel='', title='', grid=True, rotate_x=False):
        if xlabel: ax.set_xlabel(xlabel, fontsize=12)
        if ylabel: ax.set_ylabel(ylabel, fontsize=12)
        if title:  ax.set_title(title, fontsize=14, fontweight='bold')
        if grid:   ax.grid(True, alpha=0.3)
        if rotate_x:
            ax.tick_params(axis='x', rotation=45)
            for label in ax.get_xticklabels():
                label.set_ha('right')

    def _decimals_for_range(vmin: float, vmax: float) -> int:
        """축 눈금 소수 자리 수 — 값 범위가 작으면(비율·%p 등) 정수 반올림 시 전부 0으로
        뭉개지므로 자리수를 늘린다."""
        max_abs = max(abs(vmin), abs(vmax))
        if max_abs < 1:
            return 2
        if max_abs < 10:
            return 1
        return 0

    def _format_yaxis(ax):
        vmin, vmax = ax.get_ylim()
        digits = _decimals_for_range(vmin, vmax)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.{digits}f}'))

    def _format_xaxis(ax):
        """가로 막대(barh)의 값축(x축) 버전 — 비율 등 작은 값이 정수 반올림으로 전부 0이 되는 것을 막는다."""
        vmin, vmax = ax.get_xlim()
        digits = _decimals_for_range(vmin, vmax)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.{digits}f}'))

    # 차트 제목 — 예전엔 '비교'/'이중축 차트' 같은 자리표시자 문자열이 그대로 렌더링됐다
    # (2026-08-19, 고객 데모용 보고서 리뷰에서 발견). 호출부가 넘겨준 question(예: "2013년
    # 3월 카테고리별 매출 비교")이 섹션 맥락을 담고 있으므로 이걸 제목으로 쓰고, question이
    # 없을 때만 기존 자리표시자로 폴백한다. 차트 폭에 비해 너무 길면 잘라낸다.
    def _chart_title(fallback: str) -> str:
        q = (question or '').strip()
        if not q:
            return fallback
        return q if len(q) <= 40 else q[:39] + '…'

    try:
        _ensure_font()

        question_lower = question.lower()
        fig = matplotlib.figure.Figure(figsize=(10, 6))
        ax = fig.add_subplot(111)
        cmap = plt.cm.get_cmap("tab20c")

        df = _prepare_dataframe_for_visualization(df, chart_type=chart_type)

        # 문자열 컬럼이 맨 앞에 2개 이상 연달아 있으면(예: "순위_번호", "브랜드"), 실제 카테고리
        # 라벨은 숫자 값 바로 앞의 마지막 문자열 컬럼이다. 그 앞의 보조 라벨(정렬용 태그 등)은
        # 버린다 - 안 그러면 그 보조 라벨이 x축으로, 진짜 라벨(브랜드명)이 숫자 값 취급되어 깨진다.
        _lead_non_numeric = 0
        for _c in df.columns:
            if pd.api.types.is_numeric_dtype(df[_c]):
                break
            _lead_non_numeric += 1
        if _lead_non_numeric >= 2:
            df = df.iloc[:, _lead_non_numeric - 1:]

        # 값 기준 내림차순 정렬 - 막대류 차트는 크기 순으로 나열돼야 한눈에 비교된다.
        # 시간축(line)·단계 순서가 의미 있는(waterfall)·이미 자체 정렬 로직이 있는(pareto)·
        # 순서가 의미 없는(heatmap 등) 차트는 원래 순서를 그대로 둔다.
        _SORT_EXCLUDED_TYPES = {'line', 'waterfall', 'heatmap', 'scatter', 'histogram', 'boxplot', 'subplot', 'pareto', 'diverging_bar'}
        if chart_type not in _SORT_EXCLUDED_TYPES and len(df.columns) >= 2:
            _sort_col = df.columns[1]
            if pd.api.types.is_numeric_dtype(df[_sort_col]):
                df = df.sort_values(_sort_col, ascending=False).reset_index(drop=True)

        labels = df.iloc[:, 0]
        values = df.iloc[:, 1:]

        # 맨 위 df.empty/len(df.columns)<2 가드는 _prepare_dataframe_for_visualization()
        # 호출 전 기준이라, 그 안에서 컬럼이 줄어들면(피봇/정리 등) 여기 시점엔 값 컬럼이
        # 0개일 수 있다 — 이후 모든 분기가 len(values.columns)로 나누므로 여기서 미리 막는다
        # (2026-08-19, ZeroDivisionError로 확인됨).
        if len(values.columns) == 0:
            return None, None, "차트로 그릴 값(숫자) 컬럼이 없습니다"

        # 막대류 차트의 세로/가로 방향 - 실제 렌더링에 쓰일 라벨/행 수 기준으로 판단한다.
        orientation = decide_bar_orientation(df, question)

        data_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str)

        # 금액(절대값)과 비율(%) 컬럼이 섞여 있을 때 이 함수를 단독 호출하는 경우를 대비해
        # 이중축으로 최소한의 안전 처리는 남겨둔다. 다만 자동 분리(여러 플롯으로 쪼개기)가
        # 우선이며, 그 판단은 split_by_unit()을 통해 호출자(mcp_agent.py)가 먼저 수행한다.
        if chart_type in (None, 'bar') and len(values.columns) >= 2:
            _ratio_detected = [c for c in values.columns if _is_ratio_column(c, values[c])]
            _count_detected = [c for c in values.columns if c not in _ratio_detected and _is_count_column(c)]
            _other_detected = [
                c for c in values.columns if c not in _ratio_detected and c not in _count_detected
            ]
            # 비율(%) 컬럼과 금액 컬럼이 섞였거나, 건수(개)와 금액 컬럼이 섞인 경우 —
            # 둘 다 서로 다른 단위를 같은 축에 그리면 오독을 유발하므로 dual_axis로 분리.
            if (_ratio_detected and (_count_detected or _other_detected)) or (_count_detected and _other_detected):
                chart_type = 'dual_axis'

        # 이중축 (막대 + 선)
        if chart_type == 'dual_axis':
            if len(values.columns) < 2:
                values_1d = values.iloc[:, 0].tolist()
                ax.bar(labels, values_1d, color=_make_colors(cmap, len(values_1d)))
                _set_axes(ax, xlabel=df.columns[0], ylabel=values.columns[0], title=_chart_title('비교'), rotate_x=True)
                _format_yaxis(ax)
            else:
                # 막대(왼쪽 축) / 선(오른쪽 축) 분류 — 비율(%)뿐 아니라 건수(개)도 금액과
                # 단위가 다르므로 같은 취급으로 오른쪽 축(선)에 분리한다.
                bar_cols = []
                line_cols = []
                for col in values.columns:
                    if _is_ratio_column(col, values[col]) or _is_count_column(col):
                        line_cols.append(col)
                    else:
                        bar_cols.append(col)

                # 모두 같은 유형이면 첫 번째는 막대, 나머지는 선으로
                if not bar_cols:
                    bar_cols = [values.columns[0]]
                    line_cols = list(values.columns[1:])
                elif not line_cols:
                    line_cols = list(values.columns[1:])
                    bar_cols = [values.columns[0]]

                # 비율 컬럼과 이름이 대응되는 금액 컬럼(예: "순이익률" ↔ "순이익금액")은
                # 그 비율로 이미 파생 가능한 중복 정보이므로 막대에서 제외한다.
                def _ratio_stem(col_name):
                    s = str(col_name)
                    for suf in ('비율', '률', '율'):
                        if s.endswith(suf):
                            return s[:-len(suf)]
                    return None

                _ratio_stems = [st for st in (_ratio_stem(c) for c in line_cols) if st]
                if _ratio_stems:
                    _filtered_bar_cols = [c for c in bar_cols if not any(stem in str(c) for stem in _ratio_stems)]
                    if _filtered_bar_cols:
                        bar_cols = _filtered_bar_cols

                ax2 = ax.twinx()
                x_pos = np.arange(len(labels))
                width = 0.4 if len(bar_cols) == 1 else 0.6 / len(bar_cols)

                # 막대 → 왼쪽 축
                for idx, col in enumerate(bar_cols):
                    offset = (idx - len(bar_cols) / 2) * width + width / 2
                    ax.bar(x_pos + offset, values[col], width,
                           color=cmap(idx * 0.2), alpha=0.7, label=col)
                ax.set_ylabel(' / '.join(str(c) for c in bar_cols), fontsize=11)
                ax.tick_params(axis='y')
                _format_yaxis(ax)

                # 선 → 오른쪽 축
                for idx, col in enumerate(line_cols):
                    ax2.plot(x_pos, values[col].values, marker='o',
                             color=cmap(0.6 + idx * 0.15), linewidth=2,
                             linestyle='--', label=col)
                ax2.set_ylabel(' / '.join(str(c) for c in line_cols), fontsize=11)
                ax2.tick_params(axis='y')

                ax.set_xticks(x_pos)
                ax.set_xticklabels(labels, rotation=45, ha='right')
                ax.set_xlabel(df.columns[0], fontsize=12)
                ax.set_title(_chart_title('이중축 차트'), fontsize=14, fontweight='bold')
                ax.grid(True, alpha=0.3)

                lines1, labels1 = ax.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        # 서브플롯
        elif chart_type == 'subplot':
            # 사용자가 요청한 서브플롯 내 차트 유형 감지
            if any(kw in question_lower for kw in ['선', 'line', '추이', '변화']):
                subplot_type = 'line'
            elif any(kw in question_lower for kw in ['파이', 'pie', '원형', '비율', '점유율']):
                subplot_type = 'pie'
            else:
                subplot_type = 'bar'  # 기본값

            n_cols_data = len(values.columns)
            n_cols_grid = min(n_cols_data, 3)
            n_rows_grid = (n_cols_data + n_cols_grid - 1) // n_cols_grid

            matplotlib.pyplot.close(fig)
            fig, axes = matplotlib.pyplot.subplots(
                n_rows_grid, n_cols_grid,
                figsize=(6 * n_cols_grid, 4 * n_rows_grid)
            )
            axes = np.array(axes).flatten() if n_cols_data > 1 else [axes]

            for idx, col in enumerate(values.columns):
                a = axes[idx]
                color = cmap(idx / n_cols_data)

                if subplot_type == 'line':
                    try:
                        labels_display = labels.astype(int).astype(str)
                    except (ValueError, TypeError):
                        labels_display = labels.astype(str)
                    x_pos = list(range(len(labels_display)))
                    a.plot(x_pos, values[col].values, marker='o',
                           color=color, linewidth=2)
                    a.set_xticks(x_pos)
                    a.set_xticklabels(labels_display, rotation=45, ha='right')
                    _format_yaxis(a)

                elif subplot_type == 'pie':
                    a.pie(values[col], labels=labels, autopct='%1.1f%%',
                          startangle=90, colors=_make_colors(cmap, len(values[col])))

                else:  # bar
                    # 지표마다 의미 있는 정렬 기준이 다를 수 있다(예: 순이익금액 순서 그대로면
                    # 순이익률 패널에서 높은/낮은 브랜드가 뒤섞여 보임). 패널마다 자기 값 기준으로
                    # 독립적으로 재정렬한다.
                    if pd.api.types.is_numeric_dtype(values[col]):
                        order = values[col].sort_values(ascending=False).index
                        panel_labels = labels.loc[order].astype(str)
                        panel_values = values[col].loc[order]
                    else:
                        panel_labels, panel_values = labels.astype(str), values[col]
                    if orientation == 'h':
                        # barh는 아래→위로 그려지므로, 이미 내림차순인 순서를 뒤집어 상위 항목이 위로 오게 한다.
                        panel_labels = panel_labels.iloc[::-1].reset_index(drop=True)
                        panel_values = panel_values.iloc[::-1].reset_index(drop=True)
                        a.barh(panel_labels, panel_values, color=color, alpha=0.8)
                        _format_xaxis(a)
                    else:
                        a.bar(panel_labels, panel_values, color=color, alpha=0.8)
                        a.tick_params(axis='x', rotation=45)
                        _format_yaxis(a)

                a.set_title(col, fontsize=12, fontweight='bold')
                if subplot_type == 'bar' and orientation == 'h':
                    a.set_ylabel(df.columns[0], fontsize=10)
                elif subplot_type != 'pie':
                    a.set_xlabel(df.columns[0], fontsize=10)
                a.grid(True, alpha=0.3)

            for idx in range(n_cols_data, len(axes)):
                axes[idx].set_visible(False)

            fig.suptitle(_chart_title('항목별 비교'), fontsize=14, fontweight='bold', y=1.02)
            fig.tight_layout()

        # 누적 막대 (대상별 비용/구성 비교) - stacked: 절대금액 그대로, stacked100: 100% 비중
        elif chart_type in ('stacked', 'stacked100'):
            # 비율(%) 컬럼은 구성 항목이 아니므로 스택에서 제외 (금액과 섞이면 왜곡됨)
            amount_cols = [c for c in values.columns if not _is_ratio_column(c, values[c])]
            numeric_amounts = (values[amount_cols] if amount_cols else values).apply(pd.to_numeric, errors='coerce').fillna(0)

            # "매출/판매금액"처럼 전체(모수)를 나타내는 컬럼이 섞여 있으면, 그 자체를 조각으로 쌓지 않고
            # 기준(절대 스택의 총 높이 / 100% 스택의 분모)으로만 쓰고, 나머지는 "잔여" 조각으로 표시한다.
            whole_col = next((c for c in numeric_amounts.columns if any(kw in str(c) for kw in _WHOLE_KEYWORDS)), None)
            component_cols = [c for c in numeric_amounts.columns if c != whole_col]
            plot_df = (numeric_amounts[component_cols] if component_cols else numeric_amounts).copy()

            if whole_col:
                residual = (numeric_amounts[whole_col] - plot_df.sum(axis=1)).clip(lower=0)
                if (residual > 0).any():
                    plot_df['기타(잔여)'] = residual

            def _pct_fmt(x, _):
                return f'{x:,.0f}%'

            def _plain_fmt(x, _):
                return f'{x:,.0f}'

            if chart_type == 'stacked100':
                denom = (numeric_amounts[whole_col] if whole_col else plot_df.sum(axis=1)).replace(0, np.nan)
                plot_values = plot_df.div(denom, axis=0).fillna(0) * 100
                y_fmt = _pct_fmt
                y_label, title, y_lim = '비중(%)', _chart_title('구성비 비교'), (0, 100)
            else:
                plot_values = plot_df
                y_fmt = _plain_fmt
                y_label = whole_col or (values.columns[0] if len(values.columns) == 1 else '금액')
                title, y_lim = _chart_title('구성 비교'), None

            n_series = max(len(plot_values.columns), 1)
            if orientation == 'h':
                # barh는 아래→위로 그려지므로, 값이 큰(정렬된) 항목이 위로 오도록 순서를 뒤집는다.
                rev = list(range(len(labels)))[::-1]
                h_labels = labels.iloc[rev].astype(str).reset_index(drop=True)
                y_pos = np.arange(len(labels))
                left = np.zeros(len(labels))
                for idx, col in enumerate(plot_values.columns):
                    col_values = plot_values[col].iloc[rev].reset_index(drop=True)
                    ax.barh(y_pos, col_values, left=left, label=col, color=cmap(idx / n_series))
                    left += col_values.values
                ax.set_yticks(y_pos)
                ax.set_yticklabels(h_labels)
                if y_lim:
                    ax.set_xlim(*y_lim)
                ax.xaxis.set_major_formatter(mticker.FuncFormatter(y_fmt))
                ax.legend(loc='upper left', bbox_to_anchor=(1.0, 1.0))
                _set_axes(ax, xlabel=y_label, ylabel=df.columns[0], title=title)
            else:
                x_pos = np.arange(len(labels))
                bottom = np.zeros(len(labels))
                for idx, col in enumerate(plot_values.columns):
                    ax.bar(x_pos, plot_values[col], bottom=bottom, label=col, color=cmap(idx / n_series))
                    bottom += plot_values[col].values
                ax.set_xticks(x_pos)
                ax.set_xticklabels(labels, rotation=45, ha='right')
                if y_lim:
                    ax.set_ylim(*y_lim)
                ax.yaxis.set_major_formatter(mticker.FuncFormatter(y_fmt))
                ax.legend(loc='upper left', bbox_to_anchor=(1.0, 1.0))
                _set_axes(ax, xlabel=df.columns[0], ylabel=y_label, title=title)

        elif chart_type == 'pie':
            values_1d = values.iloc[:, 0].tolist()
            total = sum(v for v in values_1d if v) or 1

            # 비중이 작은 조각(대략 3% 미만)은 퍼센트 라벨을 파이 위에 그리면 서로 겹쳐
            # 판독 불가능해진다(2026-08-19, 고객 데모용 보고서 리뷰에서 발견). 처음엔
            # 작은 조각의 라벨을 아예 생략했으나, 그러면 수치 자체가 안 보이는 정보
            # 손실이 생긴다(2026-08-19, 후속 리뷰에서 지적) — 대신 파이 위 라벨은
            # 겹치지 않게 3% 미만만 생략하고, 그 수치는 범례 항목에 퍼센트로 병기해
            # 정보는 보존한다.
            def _autopct_hide_small(pct):
                return f'{pct:.1f}%' if pct >= 3 else ''

            wedges, _, __ = ax.pie(values_1d, autopct=_autopct_hide_small, startangle=90,
                                   colors=_make_colors(cmap, len(values_1d)))
            _set_axes(ax, title=df.columns[1], grid=False)
            legend_labels = [f'{lbl} ({v / total * 100:.1f}%)' for lbl, v in zip(labels, values_1d)]
            ax.legend(wedges, legend_labels, title=df.columns[0], loc="best", bbox_to_anchor=(1, 0, 0.5, 1))

        elif chart_type == 'line':
            try:
                labels_display = labels.astype(int).astype(str)
            except (ValueError, TypeError):
                labels_display = labels.astype(str)
            x_pos = list(range(len(labels_display)))

            if len(values.columns) == 1:
                # 시리즈가 하나면 구간별로 상승=초록/하락=빨강/보합=회색으로 색을 나눠 그린다
                y = pd.to_numeric(values.iloc[:, 0], errors='coerce').fillna(0).tolist()
                for i in range(len(x_pos) - 1):
                    if y[i + 1] > y[i]:
                        seg_color = _C_GREEN
                    elif y[i + 1] < y[i]:
                        seg_color = _C_RED
                    else:
                        seg_color = _C_GRAY
                    ax.plot(x_pos[i:i + 2], y[i:i + 2], color=seg_color, linewidth=2)
                ax.scatter(x_pos, y, color=_C_GRAY, zorder=3, s=24)
            else:
                for idx, col in enumerate(values.columns):
                    ax.plot(x_pos, values[col].values, marker="o", label=col,
                            color=cmap(idx / len(values.columns)), linewidth=2)
                ax.legend(loc="best")

            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels_display)
            _set_axes(ax, xlabel=df.columns[0], ylabel='값', title='추이', rotate_x=True)
            _format_yaxis(ax)

        elif chart_type == 'scatter':
            cols = df.columns.tolist()

            def scatter_by_category(x_col, cat_col, y_col):
                categories = df[cat_col].unique()
                for idx, cat in enumerate(sorted(categories)):
                    subset = df[df[cat_col] == cat]
                    ax.scatter(subset[x_col], subset[y_col],
                               color=cmap(idx / len(categories)), label=str(cat), alpha=0.7, s=60)
                _set_axes(ax, xlabel=x_col, ylabel=y_col)
                _format_yaxis(ax)
                ax.legend(title=cat_col, loc='best')

            if len(cols) == 3 and pd.api.types.is_string_dtype(df[cols[1]]):
                scatter_by_category(cols[0], cols[1], cols[2])
            elif len(cols) == 4 and pd.api.types.is_string_dtype(df[cols[2]]):
                scatter_by_category(cols[1], cols[2], cols[3])
            else:
                num_cols = df.select_dtypes(include='number').columns
                if len(num_cols) >= 2:
                    ax.scatter(df[num_cols[0]], df[num_cols[1]], color=cmap(0.6), alpha=0.7, s=60)
                    ax.set_xlabel(num_cols[0], fontsize=12)
                    ax.set_ylabel(num_cols[1], fontsize=12)
            ax.set_title('산점도', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)

        elif chart_type == 'histogram':
            for idx, col in enumerate(values.columns):
                ax.hist(values[col], bins=15, alpha=0.6, label=col,
                        color=cmap(idx / len(values.columns)))
            ax.legend(loc='best')
            _set_axes(ax, xlabel='값', ylabel='빈도', title='히스토그램')
            _format_yaxis(ax)

        elif chart_type == 'boxplot':
            box = ax.boxplot([values[col] for col in values.columns],
                             patch_artist=True, labels=values.columns)
            for patch, idx in zip(box['boxes'], range(len(values.columns))):
                patch.set_facecolor(cmap(idx / len(values.columns)))
            _set_axes(ax, xlabel='항목', ylabel='값', title='박스플롯')
            _format_yaxis(ax)

        # 폭포수 (하나의 대상 안에서 단계별 증감 → 최종값)
        elif chart_type == 'waterfall':
            vals = pd.to_numeric(values.iloc[:, 0], errors='coerce').fillna(0).tolist()
            n = len(vals)
            # 감소폭이 시작값의 20% 이상이면 더 진한 빨강으로 강조
            base = abs(vals[0]) if vals else 0

            bottoms, heights, colors_list, cum_after = [], [], [], []
            running = 0.0
            for i, v in enumerate(vals):
                if i == 0 or i == n - 1:
                    bottoms.append(0)
                    heights.append(v)
                    colors_list.append(_C_GRAY)
                    running = v
                else:
                    bottom = running if v >= 0 else running + v
                    bottoms.append(bottom)
                    heights.append(abs(v))
                    if v >= 0:
                        colors_list.append(_C_GREEN)
                    else:
                        is_major_drop = bool(base) and abs(v) / base >= 0.2
                        colors_list.append(_C_RED_STRONG if is_major_drop else _C_RED)
                    running += v
                cum_after.append(running)

            x_pos = np.arange(n)
            ax.bar(x_pos, heights, bottom=bottoms, color=colors_list, width=0.6)

            for i in range(n - 1):
                ax.plot([x_pos[i] + 0.3, x_pos[i + 1] - 0.3], [cum_after[i], cum_after[i]],
                        color='gray', linewidth=1, linestyle='--')

            for i, (b, h, v) in enumerate(zip(bottoms, heights, vals)):
                ax.text(x_pos[i], b + h, f'{v:,.0f}', ha='center', va='bottom', fontsize=9)

            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels, rotation=45, ha='right')
            _format_yaxis(ax)
            _set_axes(ax, xlabel=df.columns[0], ylabel=values.columns[0], title='폭포수(단계별 증감)')

        # 파레토 (정렬된 막대 + 누적 비중선, 80/20 확인용)
        elif chart_type == 'pareto':
            col = values.columns[0]
            sort_df = pd.DataFrame({'label': labels.astype(str), 'value': pd.to_numeric(values[col], errors='coerce').fillna(0)})
            sort_df = sort_df.sort_values('value', ascending=False).reset_index(drop=True)
            total = sort_df['value'].sum()
            sort_df['cum_pct'] = (sort_df['value'].cumsum() / total * 100) if total else 0.0

            # 누적 비중 구간별로 실행 그룹을 나눠 막대 색으로 표시 (파레토 법칙의 핵심 정보)
            focus_color, watch_color, review_color, line_color = _C_BLUE, _C_GRAY, _C_RED, _C_ORANGE

            def _zone_color(cum_pct):
                if cum_pct <= 80:
                    return focus_color
                elif cum_pct <= 95:
                    return watch_color
                return review_color

            bar_colors = [_zone_color(p) for p in sort_df['cum_pct']]

            from matplotlib.patches import Patch
            legend_handles = [
                Patch(facecolor=focus_color, label='집중(상위 80%)'),
                Patch(facecolor=watch_color, label='유지·관찰'),
                Patch(facecolor=review_color, label='정리 검토'),
            ]

            if orientation == 'h':
                # barh는 아래→위로 그려지므로, 이미 내림차순인 순서를 뒤집어 상위 항목이 위로 오게 한다.
                plot_df = sort_df.iloc[::-1].reset_index(drop=True)
                plot_colors = list(reversed(bar_colors))
                y_pos = np.arange(len(plot_df))
                ax.barh(y_pos, plot_df['value'], color=plot_colors)
                ax.set_yticks(y_pos)
                ax.set_yticklabels(plot_df['label'])
                ax.set_xlabel(col, fontsize=12)
                ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

                ax2 = ax.twiny()
                ax2.plot(plot_df['cum_pct'], y_pos, color=line_color, marker='o', linewidth=2)
                ax2.set_xlim(0, 110)
                ax2.axvline(80, color='gray', linestyle='--', linewidth=1)
                ax2.set_xlabel('누적 비중(%)', fontsize=11)
                ax2.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}%'))

                ax.legend(handles=legend_handles, loc='best')
                ax.set_ylabel(df.columns[0], fontsize=12)
            else:
                x_pos = np.arange(len(sort_df))
                ax.bar(x_pos, sort_df['value'], color=bar_colors)
                ax.set_xticks(x_pos)
                ax.set_xticklabels(sort_df['label'], rotation=45, ha='right')
                ax.set_ylabel(col, fontsize=12)
                _format_yaxis(ax)

                ax2 = ax.twinx()
                ax2.plot(x_pos, sort_df['cum_pct'], color=line_color, marker='o', linewidth=2)
                ax2.set_ylim(0, 110)
                ax2.axhline(80, color='gray', linestyle='--', linewidth=1)
                ax2.set_ylabel('누적 비중(%)', fontsize=11)
                ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}%'))

                ax.legend(handles=legend_handles, loc='best')
                ax.set_xlabel(df.columns[0], fontsize=12)

            ax.set_title('파레토(상위 항목 누적 기여도)', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)

        # 발산형 막대: 평균 등 기준값에서 좌우(또는 위아래)로 뻗어 "기준보다 얼마나 높은/낮은지"를
        # 바로 보여준다. 절대값 순위 막대와 달리 0(=기준) 위치가 항상 표시된다.
        elif chart_type == 'diverging_bar':
            col = values.columns[0]
            numeric = pd.to_numeric(values[col], errors='coerce').fillna(0)
            baseline = numeric.mean()
            plot_df = pd.DataFrame({'label': labels.astype(str), 'value': numeric})
            plot_df['diff'] = plot_df['value'] - baseline
            plot_df = plot_df.sort_values('diff', ascending=False).reset_index(drop=True)
            bar_colors = [_C_GREEN if d >= 0 else _C_RED for d in plot_df['diff']]

            if orientation == 'h':
                # barh는 아래→위로 그려지므로, diff가 큰 항목이 위로 오도록 순서를 뒤집는다.
                plot_df = plot_df.iloc[::-1].reset_index(drop=True)
                bar_colors = list(reversed(bar_colors))
                y_pos = np.arange(len(plot_df))
                ax.barh(y_pos, plot_df['diff'], color=bar_colors)
                ax.set_yticks(y_pos)
                ax.set_yticklabels(plot_df['label'])
                ax.axvline(0, color=_C_GRAY, linewidth=1.5)
                ax.set_xlabel(f'{col} (평균 {baseline:,.0f} 대비)', fontsize=12)
                ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:+,.0f}'))
                for y, diff, val in zip(y_pos, plot_df['diff'], plot_df['value']):
                    ax.annotate(f'{val:,.0f}', (diff, y), xytext=(6 if diff >= 0 else -6, 0),
                                textcoords='offset points', va='center',
                                ha='left' if diff >= 0 else 'right', fontsize=9)
            else:
                x_pos = np.arange(len(plot_df))
                ax.bar(x_pos, plot_df['diff'], color=bar_colors)
                ax.set_xticks(x_pos)
                ax.set_xticklabels(plot_df['label'], rotation=45, ha='right')
                ax.axhline(0, color=_C_GRAY, linewidth=1.5)
                ax.set_ylabel(f'{col} (평균 {baseline:,.0f} 대비)', fontsize=12)
                _format_yaxis(ax)
                for x, diff, val in zip(x_pos, plot_df['diff'], plot_df['value']):
                    ax.annotate(f'{val:,.0f}', (x, diff), xytext=(0, 4 if diff >= 0 else -12),
                                textcoords='offset points', ha='center', fontsize=9)

            ax.set_title(f'{col} 평균({baseline:,.0f}) 대비 비교', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)

        # 히트맵 (두 범주 교차 비교)
        elif chart_type == 'heatmap':
            matrix = values.to_numpy(dtype=float)
            im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
            ax.set_xticks(np.arange(len(values.columns)))
            ax.set_xticklabels(values.columns, rotation=45, ha='right')
            ax.set_yticks(np.arange(len(labels)))
            ax.set_yticklabels(labels)

            vmax = np.nanmax(matrix) if matrix.size else 0
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    val = matrix[i, j]
                    if not np.isnan(val):
                        ax.text(j, i, f'{val:,.0f}', ha='center', va='center', fontsize=8,
                                color='white' if vmax and val > vmax * 0.5 else 'black')

            fig.colorbar(im, ax=ax, shrink=0.8)
            ax.set_ylabel(df.columns[0], fontsize=12)
            ax.set_title('히트맵', fontsize=14, fontweight='bold')
            ax.grid(False)

        else:
            if len(values.columns) == 1:
                col = values.columns[0]
                values_1d = values.iloc[:, 0]
                strategy = _pick_color_strategy(chart_type, col, values_1d)
                bar_colors = _colors_for_strategy(values_1d, strategy)
                if orientation == 'h':
                    # barh는 아래→위로 그려지므로, 값이 큰 게 위로 오도록 오름차순으로 다시 정렬한다.
                    order = list(values_1d.sort_values(ascending=True).index)
                    h_labels = labels.loc[order].astype(str)
                    h_values = values_1d.loc[order]
                    h_colors = [bar_colors[i] for i in order]
                    ax.barh(h_labels, h_values.tolist(), color=h_colors)
                    _set_axes(ax, xlabel=col, ylabel=df.columns[0], title=_chart_title('비교'))
                    _format_xaxis(ax)
                else:
                    ax.bar(labels, values_1d.tolist(), color=bar_colors)
                    _set_axes(ax, xlabel=df.columns[0], ylabel=col, title=_chart_title('비교'), rotate_x=True)
                    _format_yaxis(ax)
            else:
                if orientation == 'h':
                    rev = list(range(len(labels)))[::-1]
                    h_labels = labels.iloc[rev].astype(str).reset_index(drop=True)
                    y = np.arange(len(labels))
                    height = 0.8 / len(values.columns)
                    for idx, col in enumerate(values.columns):
                        offset = (idx - len(values.columns) / 2) * height + height / 2
                        col_values = values[col].iloc[rev].reset_index(drop=True)
                        ax.barh(y + offset, col_values, height, label=col,
                                color=cmap(idx / len(values.columns)))
                    ax.set_yticks(y)
                    ax.set_yticklabels(h_labels)
                    ax.legend(loc='best')
                    _set_axes(ax, xlabel='값', ylabel=df.columns[0], title=_chart_title('비교'))
                    _format_xaxis(ax)
                else:
                    x = np.arange(len(labels))
                    width = 0.8 / len(values.columns)
                    for idx, col in enumerate(values.columns):
                        offset = (idx - len(values.columns) / 2) * width + width / 2
                        ax.bar(x + offset, values[col], width, label=col,
                               color=cmap(idx / len(values.columns)))
                    ax.set_xticks(x)
                    ax.set_xticklabels(labels)
                    ax.legend(loc='best')
                    _set_axes(ax, xlabel=df.columns[0], ylabel='값', title=_chart_title('비교'), rotate_x=True)
                    _format_yaxis(ax)

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        matplotlib.pyplot.close(fig)
        return image_base64, data_json, None

    except Exception as e:
        # print(f"[ERROR] 차트 생성 실패({chart_type}): {e}")
        traceback.print_exc()
        plt.close('all')
        return None, None, str(e)
