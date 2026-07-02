"""
visualization.py — DataFrame 시각화 유틸리티 (d2chat · d2insight 공통)

- detect_visualization_type_with_llm : LLM으로 시각화 타입 감지
- dataframe_to_html_table            : DataFrame → HTML 테이블
- dataframe_to_chart_image           : DataFrame → Base64 PNG 차트
- strip_markdown                     : 마크다운 문법 제거
"""
from __future__ import annotations

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

from d2shared.llm_logger import log_llm_call


# ── 마크다운 제거 ────────────────────────────────────────────────

def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`{1,3}.*?`{1,3}', '', text, flags=re.DOTALL)
    text = re.sub(r'\|.+\|', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── 시각화 타입 감지 ──────────────────────────────────────────────

def detect_visualization_type_with_llm(question: str, llm, log_ctx: dict = None) -> dict:
    """LLM으로 시각화 타입 감지"""
    prompt = f"""
다음 형식의 JSON으로만 답하세요.

사용자 질문:
"{question}"

규칙:
- 이미지 항목에 띄어 쓴 것이 있으면 붙여서 진행해주세요.
- 영어와 한글을 혼용하여 사용한 경우는 해석하여 진행합니다.
- 질문에 "테이블로", "표로", "도표로" 라는 표현이 있으면 반드시 visualization_type = "table"
- 질문에 "막대그래프"가 있으면 chart_type = "bar"
- 질문에 "선그래프" 또는 "라인그래프"가 있으면 chart_type = "line"
- 질문에 "원그래프" 또는 "원형그래프", "파이차트"가 있으면 chart_type = "pie"
- 질문에 "산점도", "분포도", "스캐터", "scatter"이 있으면 chart_type = "scatter"
- 질문에 "히스토그램", "histogram"이 있으면 chart_type = "histogram"
- 질문에 "박스플롯", "boxplot"이 있으면 chart_type = "boxplot"
- 질문에 "그래프", "차트", "시각화", "그려주세요"가 있으면 visualization_type = "chart"
- **위 표현이 없을 경우 : 의미를 해석하여 적절한 시각화 형태와 차트 형태를 결정합니다**

이중축(dual_axis) 판단 규칙:
- 단위가 다른 두 종류의 데이터를 함께 표현해야 할 때 chart_type = "dual_axis"

서브플롯(subplot) 판단 규칙:
- "각각", "따로", "별도로", "개별" 같은 단어가 명시적으로 있을 때만 chart_type = "subplot"

결과 JSON:
{{
  "visualization_type": "chart | table | none",
  "chart_type": "bar | line | pie | scatter | histogram | boxplot | dual_axis | subplot | null",
  "confidence": 0.0 ~ 1.0,
  "reasoning": "근거"
}}
"""
    try:
        from datetime import datetime

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
            is_success=True,
            startdts=start,
            enddts=end,
        )

        return parse_llm_json_response(raw_result)

    except Exception as e:
        print(f"[WARN] 시각화 타입 감지 오류: {e}")
        return {"visualization_type": "none", "chart_type": None, "confidence": 0.0,
                "reasoning": f"error: {str(e)}"}


# ── DataFrame 전처리 ────────────────────────────────────────────

def _prepare_dataframe_for_visualization(df: pd.DataFrame, chart_type: str = None) -> pd.DataFrame:
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
        is_time_col = any(kw in col_lower for kw in time_keywords)
        is_year_like = (
            pd.api.types.is_numeric_dtype(df[col]) and df[col].between(1900, 2100).all()
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
        second_last_str = pd.api.types.is_string_dtype(df.iloc[:, -2])
        all_tail_numeric = all(
            pd.api.types.is_numeric_dtype(df.iloc[:, i]) for i in range(1, len(df.columns))
        )
        if last_numeric and second_last_str and not all_tail_numeric and chart_type != 'scatter':
            try:
                df = df.pivot(
                    index=df.columns[0], columns=df.columns[-2], values=df.columns[-1]
                ).reset_index()
                df.columns.name = None
            except Exception as e:
                print(f"[WARN] 피봇 실패: {e}")

    return df


# ── HTML 테이블 변환 ────────────────────────────────────────────

def dataframe_to_html_table(df: pd.DataFrame, max_rows: int = 100) -> tuple:
    """DataFrame → (HTML 테이블 문자열, 전처리된 DataFrame JSON 문자열)"""
    if df.empty:
        return "<p>데이터가 없습니다.</p>", "[]"

    df = _prepare_dataframe_for_visualization(df, chart_type=None)
    data_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str)
    display_df = df.head(max_rows)

    first_col = display_df.columns[0]
    numeric_cols = [col for col in display_df.select_dtypes(include='number').columns if col != first_col]
    text_cols = [col for col in display_df.columns if col not in numeric_cols]

    def smart_format(series):
        abs_max = series.abs().max()
        if pd.isna(abs_max):
            return lambda x: ""
        if abs_max >= 100:
            return lambda x: f"{x:,.0f}" if pd.notna(x) else ""
        else:
            return lambda x: f"{x:,.2f}" if pd.notna(x) else ""

    styler = display_df.style.hide(axis="index")
    styler = styler.format({col: smart_format(display_df[col]) for col in numeric_cols}, na_rep="")
    styler = styler.set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
    if numeric_cols:
        styler = styler.set_properties(subset=numeric_cols, **{"text-align": "right"})
    if text_cols:
        styler = styler.set_properties(subset=text_cols, **{"text-align": "left"})

    return styler.to_html(), data_json


# ── 차트 이미지 변환 ────────────────────────────────────────────

def dataframe_to_chart_image(df: pd.DataFrame, question: str, chart_type: str = None) -> tuple:
    """DataFrame → (Base64 PNG 이미지 문자열, 전처리된 DataFrame JSON 문자열)"""
    import matplotlib.ticker as mticker

    if df.empty or len(df.columns) < 2:
        return None, None

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

    def _format_yaxis(ax):
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    try:
        # 폰트 설정: NanumGothic → Malgun Gothic(Windows) → AppleGothic(macOS) → 기본 폰트 순
        font_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'fonts', 'NanumGothic-Regular.ttf')
        )
        if os.path.exists(font_path):
            fm.fontManager.addfont(font_path)
            font_prop = fm.FontProperties(fname=font_path)
            matplotlib.rcParams['font.family'] = font_prop.get_name()
        else:
            _korean_candidates = ['Malgun Gothic', 'AppleGothic', 'NanumGothic', 'NanumBarunGothic']
            _available = {f.name for f in fm.fontManager.ttflist}
            for _candidate in _korean_candidates:
                if _candidate in _available:
                    matplotlib.rcParams['font.family'] = _candidate
                    break
        matplotlib.rcParams['axes.unicode_minus'] = False

        question_lower = question.lower()
        fig = matplotlib.figure.Figure(figsize=(10, 6))
        ax = fig.add_subplot(111)
        cmap = plt.cm.get_cmap("tab20c")

        df = _prepare_dataframe_for_visualization(df, chart_type=chart_type)
        labels = df.iloc[:, 0]
        values = df.iloc[:, 1:]
        data_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str)

        # 이중축
        if chart_type == 'dual_axis' or any(kw in question_lower for kw in ['이중축', '이중 축']):
            if len(values.columns) < 2:
                values_1d = values.iloc[:, 0].tolist()
                ax.bar(labels, values_1d, color=_make_colors(cmap, len(values_1d)))
                _set_axes(ax, xlabel=df.columns[0], ylabel=values.columns[0], title='비교', rotate_x=True)
                _format_yaxis(ax)
            else:
                ratio_keywords = ['율', '률', '비율', '%', 'rate', 'ratio', 'pct', 'percent']

                def is_ratio_col(col_name, series):
                    col_lower = col_name.lower()
                    if any(kw in col_lower for kw in ratio_keywords):
                        return True
                    if series.max() <= 100 and series.min() >= 0:
                        return True
                    return False

                bar_cols = [col for col in values.columns if not is_ratio_col(col, values[col])]
                line_cols = [col for col in values.columns if is_ratio_col(col, values[col])]
                if not bar_cols:
                    bar_cols = [values.columns[0]]
                    line_cols = list(values.columns[1:])
                elif not line_cols:
                    line_cols = list(values.columns[1:])
                    bar_cols = [values.columns[0]]

                ax2 = ax.twinx()
                x_pos = np.arange(len(labels))
                width = 0.4 if len(bar_cols) == 1 else 0.6 / len(bar_cols)
                for idx, col in enumerate(bar_cols):
                    offset = (idx - len(bar_cols) / 2) * width + width / 2
                    ax.bar(x_pos + offset, values[col], width, color=cmap(idx * 0.2), alpha=0.7, label=col)
                ax.set_ylabel(' / '.join(bar_cols), fontsize=11)
                _format_yaxis(ax)
                for idx, col in enumerate(line_cols):
                    ax2.plot(x_pos, values[col].values, marker='o', color=cmap(0.6 + idx * 0.15),
                             linewidth=2, linestyle='--', label=col)
                ax2.set_ylabel(' / '.join(line_cols), fontsize=11)
                ax.set_xticks(x_pos)
                ax.set_xticklabels(labels, rotation=45, ha='right')
                ax.set_xlabel(df.columns[0], fontsize=12)
                ax.set_title('이중축 차트', fontsize=14, fontweight='bold')
                ax.grid(True, alpha=0.3)
                lines1, labels1 = ax.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        # 서브플롯
        elif chart_type == 'subplot' or any(kw in question_lower for kw in ['각각', '따로', '별도']):
            if any(kw in question_lower for kw in ['선', 'line', '추이', '변화']):
                subplot_type = 'line'
            elif any(kw in question_lower for kw in ['파이', 'pie', '원형', '비율', '점유율']):
                subplot_type = 'pie'
            else:
                subplot_type = 'bar'

            n_cols_data = len(values.columns)
            n_cols_grid = min(n_cols_data, 3)
            n_rows_grid = (n_cols_data + n_cols_grid - 1) // n_cols_grid
            matplotlib.pyplot.close(fig)
            fig, axes = matplotlib.pyplot.subplots(n_rows_grid, n_cols_grid,
                                                    figsize=(6 * n_cols_grid, 4 * n_rows_grid))
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
                    a.plot(x_pos, values[col].values, marker='o', color=color, linewidth=2)
                    a.set_xticks(x_pos)
                    a.set_xticklabels(labels_display, rotation=45, ha='right')
                    a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
                elif subplot_type == 'pie':
                    a.pie(values[col], labels=labels, autopct='%1.1f%%', startangle=90,
                          colors=_make_colors(cmap, len(values[col])))
                else:
                    a.bar(labels, values[col], color=color, alpha=0.8)
                    a.tick_params(axis='x', rotation=45)
                    a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
                a.set_title(col, fontsize=12, fontweight='bold')
                if subplot_type != 'pie':
                    a.set_xlabel(df.columns[0], fontsize=10)
                a.grid(True, alpha=0.3)
            for idx in range(n_cols_data, len(axes)):
                axes[idx].set_visible(False)
            fig.suptitle('항목별 비교', fontsize=14, fontweight='bold', y=1.02)
            fig.tight_layout()

        elif any(kw in question_lower for kw in ['파이', 'pie', '원형', '비율', '점유율']):
            values_1d = values.iloc[:, 0].tolist()
            wedges, _, __ = ax.pie(values_1d, autopct='%1.1f%%', startangle=90,
                                   colors=_make_colors(cmap, len(values_1d)))
            _set_axes(ax, title=df.columns[1], grid=False)
            ax.legend(wedges, labels, title=df.columns[0], loc="best", bbox_to_anchor=(1, 0, 0.5, 1))

        elif any(kw in question_lower for kw in ['선', 'line', '추이', '변화']):
            try:
                labels_display = labels.astype(int).astype(str)
            except (ValueError, TypeError):
                labels_display = labels.astype(str)
            x_pos = list(range(len(labels_display)))
            for idx, col in enumerate(values.columns):
                ax.plot(x_pos, values[col].values, marker="o", label=col,
                        color=cmap(idx / len(values.columns)), linewidth=2)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels_display)
            ax.legend(loc="best")
            _set_axes(ax, xlabel=df.columns[0], ylabel='값', title='추이', rotate_x=True)
            _format_yaxis(ax)

        elif any(kw in question_lower for kw in ['산점도', 'scatter']):
            cols = df.columns.tolist()
            if len(cols) == 3 and pd.api.types.is_string_dtype(df[cols[1]]):
                categories = df[cols[1]].unique()
                for idx, cat in enumerate(sorted(categories)):
                    subset = df[df[cols[1]] == cat]
                    ax.scatter(subset[cols[0]], subset[cols[2]],
                               color=cmap(idx / len(categories)), label=str(cat), alpha=0.7, s=60)
                _set_axes(ax, xlabel=cols[0], ylabel=cols[2])
                _format_yaxis(ax)
                ax.legend(title=cols[1], loc='best')
            else:
                num_cols = df.select_dtypes(include='number').columns
                if len(num_cols) >= 2:
                    ax.scatter(df[num_cols[0]], df[num_cols[1]], color=cmap(0.6), alpha=0.7, s=60)
                    ax.set_xlabel(num_cols[0], fontsize=12)
                    ax.set_ylabel(num_cols[1], fontsize=12)
            ax.set_title('산점도', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)

        elif any(kw in question_lower for kw in ['히스토그램', 'histogram']):
            for idx, col in enumerate(values.columns):
                ax.hist(values[col], bins=15, alpha=0.6, label=col, color=cmap(idx / len(values.columns)))
            ax.legend(loc='best')
            _set_axes(ax, xlabel='값', ylabel='빈도', title='히스토그램')
            _format_yaxis(ax)

        elif any(kw in question_lower for kw in ['박스플롯', 'boxplot']):
            box = ax.boxplot([values[col] for col in values.columns], patch_artist=True, labels=values.columns)
            for patch, idx in zip(box['boxes'], range(len(values.columns))):
                patch.set_facecolor(cmap(idx / len(values.columns)))
            _set_axes(ax, xlabel='항목', ylabel='값', title='박스플롯')
            _format_yaxis(ax)

        else:
            if len(values.columns) == 1:
                values_1d = values.iloc[:, 0].tolist()
                ax.bar(labels, values_1d, color=_make_colors(cmap, len(values_1d)))
                _set_axes(ax, xlabel=df.columns[0], ylabel=values.columns[0], title='비교', rotate_x=True)
                _format_yaxis(ax)
            else:
                x = np.arange(len(labels))
                width = 0.8 / len(values.columns)
                for idx, col in enumerate(values.columns):
                    offset = (idx - len(values.columns) / 2) * width + width / 2
                    ax.bar(x + offset, values[col], width, label=col, color=cmap(idx / len(values.columns)))
                ax.set_xticks(x)
                ax.set_xticklabels(labels)
                ax.legend(loc='best')
                _set_axes(ax, xlabel=df.columns[0], ylabel='값', title='비교', rotate_x=True)
                _format_yaxis(ax)

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        matplotlib.pyplot.close(fig)
        return image_base64, data_json

    except Exception as e:
        print(f"[WARN] 차트 생성 오류: {e}")
        traceback.print_exc()
        plt.close('all')
        return None, None
