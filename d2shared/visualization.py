"""공통 시각화 유틸리티 — d2chat/d2insight 공유.

출처: pr_d2chat/mcp_agent/visualization.py + pr_d2insight/visualization/chart.py
통합 변경:
  - 폰트 경로: d2shared/fonts/NanumGothic-Regular.ttf
  - detect_visualization_type_with_llm: log_fn 파라미터로 로거 주입 (역방향 의존 제거)
  - _is_time_like / _needs_dual_axis: d2insight 헬퍼 추가
  - 차트 유형: d2chat의 histogram/boxplot/subplot 포함
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import traceback
from typing import Callable, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.figure
import matplotlib.font_manager as fm
import matplotlib.ticker as mticker

_FONT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fonts", "NanumGothic-Regular.ttf")
)
_font_loaded = False


def _ensure_font() -> None:
    global _font_loaded
    if not _font_loaded and os.path.exists(_FONT_PATH):
        fm.fontManager.addfont(_FONT_PATH)
        fp = fm.FontProperties(fname=_FONT_PATH)
        matplotlib.rcParams["font.family"] = fp.get_name()
        matplotlib.rcParams["axes.unicode_minus"] = False
        _font_loaded = True


# ── 마크다운 제거 ─────────────────────────────────────────────────────────────

def strip_markdown(text: str) -> str:
    """답변 텍스트에서 마크다운 문법 제거 (d2chat 전용)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.DOTALL)
    text = re.sub(r"\|.+\|", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── 시각화 타입 감지 (d2chat 전용) ───────────────────────────────────────────

def detect_visualization_type_with_llm(
    question: str,
    llm,
    log_ctx: dict = None,
    log_fn: Optional[Callable] = None,
) -> dict:
    """LLM으로 시각화 타입 감지.

    log_fn: log_llm_call 함수 (d2chat.history.llm_logger.log_llm_call 등)
            None이면 로깅 건너뜀.
    """
    prompt = f"""
다음 형식의 JSON으로만 답하세요.

사용자 질문:
"{question}"

규칙:
- 질문에 "테이블로", "표로", "도표로" 라는 표현이 있으면 반드시 visualization_type = "table"
- 질문에 "막대그래프"가 있으면 chart_type = "bar"
- 질문에 "선그래프" 또는 "라인그래프"가 있으면 chart_type = "line"
- 질문에 "원그래프" 또는 "원형그래프", "파이차트"가 있으면 chart_type = "pie"
- 질문에 "산점도", "분포도", "스캐터", "scatter"이 있으면 chart_type = "scatter"
- 질문에 "히스토그램", "histogram"이 있으면 chart_type = "histogram"
- 질문에 "박스플롯", "boxplot"이 있으면 chart_type = "boxplot"
- 질문에 "그래프", "차트", "시각화", "그려주세요"가 있으면 visualization_type = "chart"
- 위 표현이 없을 경우: 의미를 해석하여 적절한 시각화 형태와 차트 형태를 결정합니다

이중축(dual_axis) 판단 규칙:
- 단위가 다른 두 종류의 데이터를 함께 표현해야 할 때 chart_type = "dual_axis"
- 예: "건수와 오류율을 함께", "매출액과 증감률을 같이"

서브플롯(subplot) 판단 규칙:
- 질문에 "각각", "따로", "별도로", "개별" 같은 단어가 명시적으로 있을 때만 chart_type = "subplot"

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

        def _parse(result):
            text = result.content.strip()
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
            return json.loads(m.group(1) if m else text)

        start = datetime.now()
        raw = llm.invoke(prompt)
        end = datetime.now()

        if log_fn and log_ctx:
            usage = getattr(raw, "usage_metadata", None) or {}
            try:
                log_fn(
                    log_ctx=log_ctx,
                    stepnm="viz_detect",
                    steptitle="시각화 유형 감지",
                    llmmodelnm=getattr(llm, "model", "unknown"),
                    inputtoken=usage.get("input_tokens", 0),
                    outputtoken=usage.get("output_tokens", 0),
                    startdts=start,
                    enddts=end,
                )
            except Exception:
                pass

        return _parse(raw)

    except Exception as e:
        print(f"[WARN] 시각화 타입 감지 오류: {e}")
        return {
            "visualization_type": "none",
            "chart_type": None,
            "confidence": 0.0,
            "reasoning": f"error: {e}",
        }


# ── DataFrame 전처리 ──────────────────────────────────────────────────────────

_TIME_PATTERNS = [
    r"^\d{4}$", r"^\d{4}-\d{2}$", r"^\d{4}-\d{2}-\d{2}$",
    r"^\d{1,2}월$", r"^\d+분기$", r"^Q\d$", r"^\d{4}Q\d$",
]


def _is_time_like(series: pd.Series) -> bool:
    """X축 값이 날짜/월/연도 형식이면 True."""
    if pd.api.types.is_numeric_dtype(series):
        return bool(series.between(1990, 2030).all() and len(series) <= 12)
    sample = series.dropna().head(10).astype(str)
    return any(
        re.match(pat, v.strip()) for v in sample for pat in _TIME_PATTERNS
    )


def _needs_dual_axis(values: pd.DataFrame, threshold: float = 50.0) -> bool:
    """두 계열의 최대값 비율이 threshold 배 이상이면 이중축이 필요하다."""
    if len(values.columns) != 2:
        return False
    m0 = values.iloc[:, 0].abs().max()
    m1 = values.iloc[:, 1].abs().max()
    if m0 == 0 or m1 == 0:
        return False
    return max(m0, m1) / min(m0, m1) > threshold


def _prepare_df(df: pd.DataFrame, chart_type: str = None) -> pd.DataFrame:
    """DataFrame을 시각화에 적합한 형태로 변환 (시간 컬럼 결합 + 피봇)."""
    if df.empty or len(df.columns) < 2:
        return df
    df = df.copy()

    time_kw = ["년도", "year", "연", "월", "month", "일", "day", "분기", "quarter"]
    excl_kw = ["요일", "weekday", "dayofweek", "dow"]

    time_cols = []
    for col in df.columns:
        cl = str(col).lower()
        if any(k in cl for k in excl_kw):
            break
        is_time = any(k in cl for k in time_kw)
        is_year = (
            pd.api.types.is_numeric_dtype(df[col]) and df[col].between(1900, 2100).all()
        ) if len(df) > 0 else False
        if is_time or is_year:
            time_cols.append(col)
        else:
            break

    if len(time_cols) >= 2:
        def _combine(row):
            parts = []
            for c in time_cols:
                v = row[c]
                if isinstance(v, str) and "-" in v:
                    return v
                try:
                    cl = str(c).lower()
                    if "월" in cl or "month" in cl:
                        parts.append(f"{int(v):02d}")
                    elif "일" in cl or "day" in cl:
                        parts.append(f"{int(v):02d}")
                    else:
                        parts.append(str(int(v)))
                except Exception:
                    parts.append(str(v))
            return "-".join(parts)

        combined = "-".join(time_cols)
        df[combined] = df.apply(_combine, axis=1)
        df = df.drop(columns=time_cols)
        df = df[[combined] + [c for c in df.columns if c != combined]]

    if len(df.columns) >= 3 and chart_type not in ("scatter", "dual_axis"):
        last_num = pd.api.types.is_numeric_dtype(df.iloc[:, -1])
        second_str = pd.api.types.is_string_dtype(df.iloc[:, -2])
        all_tail_num = all(
            pd.api.types.is_numeric_dtype(df.iloc[:, i]) for i in range(1, len(df.columns))
        )
        if last_num and second_str and not all_tail_num:
            try:
                df = df.pivot(
                    index=df.columns[0],
                    columns=df.columns[-2],
                    values=df.columns[-1],
                ).reset_index()
                df.columns.name = None
            except Exception:
                pass

    return df


# ── HTML 테이블 ───────────────────────────────────────────────────────────────

def dataframe_to_html_table(df: pd.DataFrame, max_rows: int = 100) -> tuple:
    """DataFrame → (HTML 테이블 문자열, data_json 문자열)."""
    if df.empty:
        return "<p>데이터가 없습니다.</p>", "[]"

    df = _prepare_df(df)
    data_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str)
    display_df = df.head(max_rows)

    first_col = display_df.columns[0]
    num_cols = [c for c in display_df.select_dtypes(include="number").columns if c != first_col]
    txt_cols = [c for c in display_df.columns if c not in num_cols]

    def _fmt(series: pd.Series):
        mx = series.abs().max()
        if pd.isna(mx):
            return lambda x: ""
        if mx >= 100:
            return lambda x: f"{x:,.0f}" if pd.notna(x) else ""
        return lambda x: f"{x:,.2f}" if pd.notna(x) else ""

    styler = display_df.style.hide(axis="index")
    styler = styler.format({c: _fmt(display_df[c]) for c in num_cols}, na_rep="")
    styler = styler.set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
    if num_cols:
        styler = styler.set_properties(subset=num_cols, **{"text-align": "right"})
    if txt_cols:
        styler = styler.set_properties(subset=txt_cols, **{"text-align": "left"})

    return styler.to_html(), data_json


# ── 차트 이미지 ───────────────────────────────────────────────────────────────

def dataframe_to_chart_image(
    df: pd.DataFrame,
    question: str,
    chart_type: str = None,
) -> tuple:
    """DataFrame → (Base64 PNG 문자열, data_json 문자열).

    chart_type: bar | line | pie | scatter | histogram | boxplot | dual_axis | subplot | None(자동)
    """
    _ensure_font()

    if df.empty or len(df.columns) < 2:
        return None, None

    cmap = plt.cm.get_cmap("tab20c")

    def _colors(n):
        return [cmap(i / max(n, 1)) for i in range(n)]

    def _decorate(ax, xlabel="", ylabel="", title="", grid=True, rotate_x=False):
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=12)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=12)
        if title:
            ax.set_title(title, fontsize=14, fontweight="bold")
        if grid:
            ax.grid(True, alpha=0.3)
        if rotate_x:
            ax.tick_params(axis="x", rotation=45)
            for lbl in ax.get_xticklabels():
                lbl.set_ha("right")

    def _fmty(ax):
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    try:
        ql = question.lower()
        fig = matplotlib.figure.Figure(figsize=(10, 6))
        ax = fig.add_subplot(111)

        df = _prepare_df(df, chart_type=chart_type)
        labels = df.iloc[:, 0]
        values = df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce").fillna(0)
        data_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str)

        # ── 차트 유형 결정 ──────────────────────────────────────────────────
        PIE_KW = ["파이", "pie", "원형", "비율", "점유율", "구성비", "점유"]
        TREND_KW = ["선", "line", "추이", "변화"]
        RATIO_KW = ["율", "률", "비율", "%", "rate", "ratio", "pct", "percent"]

        if chart_type == "subplot" or any(k in ql for k in ["각각", "따로", "별도", "개별"]):
            resolved = "subplot"
        elif chart_type == "pie" or any(k in ql for k in PIE_KW):
            resolved = "pie"
        elif chart_type == "histogram" or any(k in ql for k in ["히스토그램", "histogram"]):
            resolved = "histogram"
        elif chart_type == "boxplot" or any(k in ql for k in ["박스플롯", "boxplot"]):
            resolved = "boxplot"
        elif chart_type == "scatter" or any(k in ql for k in ["산점도", "scatter"]):
            resolved = "scatter"
        elif chart_type == "dual_axis" or any(k in ql for k in ["이중축", "이중 축"]):
            resolved = "dual_axis"
        elif chart_type == "line":
            resolved = "line"
        elif chart_type == "bar":
            resolved = "bar"
        elif any(k in ql for k in TREND_KW):
            resolved = "line" if _is_time_like(labels) else "bar"
        elif _needs_dual_axis(values):
            resolved = "dual_axis"
        else:
            resolved = "bar"

        # ── 파이 ─────────────────────────────────────────────────────────
        if resolved == "pie":
            vals = values.iloc[:, 0].abs().tolist()
            wedges, _, autotexts = ax.pie(
                vals, autopct="%1.1f%%", startangle=90,
                colors=_colors(len(vals)), pctdistance=0.82,
            )
            for at in autotexts:
                at.set_fontsize(9)
            ax.set_title(question, fontsize=13, fontweight="bold")
            ax.legend(wedges, labels, title=df.columns[0], loc="best",
                      bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)

        # ── 선 ───────────────────────────────────────────────────────────
        elif resolved == "line":
            try:
                labels_d = labels.astype(int).astype(str)
            except (ValueError, TypeError):
                labels_d = labels.astype(str)
            xp = list(range(len(labels_d)))
            for i, col in enumerate(values.columns):
                ax.plot(xp, values[col].values, marker="o", label=col,
                        color=cmap(i / max(len(values.columns), 1)), linewidth=2)
            ax.set_xticks(xp)
            ax.set_xticklabels(labels_d, rotation=45, ha="right")
            ax.legend(loc="best")
            _decorate(ax, xlabel=df.columns[0], ylabel="값", title=question)
            _fmty(ax)

        # ── 이중축 ────────────────────────────────────────────────────────
        elif resolved == "dual_axis":
            if len(values.columns) < 2:
                ax.bar(labels, values.iloc[:, 0].tolist(), color=_colors(len(labels)))
                _decorate(ax, xlabel=df.columns[0], ylabel=values.columns[0], title=question, rotate_x=True)
                _fmty(ax)
            else:
                ratio_kw = RATIO_KW

                def is_ratio(col_name, series):
                    if any(k in col_name.lower() for k in ratio_kw):
                        return True
                    return series.max() <= 100 and series.min() >= 0

                bar_cols = [c for c in values.columns if not is_ratio(c, values[c])]
                line_cols = [c for c in values.columns if is_ratio(c, values[c])]
                if not bar_cols:
                    bar_cols, line_cols = [values.columns[0]], list(values.columns[1:])
                elif not line_cols:
                    line_cols = list(values.columns[1:])
                    bar_cols = [values.columns[0]]

                ax2 = ax.twinx()
                x = np.arange(len(labels))
                w = 0.4 if len(bar_cols) == 1 else 0.6 / len(bar_cols)
                for i, col in enumerate(bar_cols):
                    off = (i - len(bar_cols) / 2) * w + w / 2
                    ax.bar(x + off, values[col], w, color=cmap(i * 0.2), alpha=0.7, label=col)
                ax.set_ylabel(" / ".join(bar_cols), fontsize=11)
                _fmty(ax)
                for i, col in enumerate(line_cols):
                    ax2.plot(x, values[col].values, marker="o",
                             color=cmap(0.6 + i * 0.15), linewidth=2, linestyle="--", label=col)
                ax2.set_ylabel(" / ".join(line_cols), fontsize=11)
                ax.set_xticks(x)
                ax.set_xticklabels(labels.astype(str), rotation=45, ha="right")
                ax.set_xlabel(df.columns[0], fontsize=12)
                ax.set_title(question, fontsize=14, fontweight="bold")
                ax.grid(True, alpha=0.3)
                h1, l1 = ax.get_legend_handles_labels()
                h2, l2 = ax2.get_legend_handles_labels()
                ax.legend(h1 + h2, l1 + l2, loc="upper left")

        # ── 서브플롯 ──────────────────────────────────────────────────────
        elif resolved == "subplot":
            subplot_type = (
                "line" if any(k in ql for k in ["선", "line", "추이", "변화"]) else
                "pie" if any(k in ql for k in PIE_KW) else
                "bar"
            )
            n = len(values.columns)
            nc = min(n, 3)
            nr = (n + nc - 1) // nc
            plt.close(fig)
            fig, axes = plt.subplots(nr, nc, figsize=(6 * nc, 4 * nr))
            axes = np.array(axes).flatten() if n > 1 else [axes]
            for i, col in enumerate(values.columns):
                a = axes[i]
                color = cmap(i / n)
                if subplot_type == "line":
                    try:
                        ld = labels.astype(int).astype(str)
                    except Exception:
                        ld = labels.astype(str)
                    xp = list(range(len(ld)))
                    a.plot(xp, values[col].values, marker="o", color=color, linewidth=2)
                    a.set_xticks(xp)
                    a.set_xticklabels(ld, rotation=45, ha="right")
                    a.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
                elif subplot_type == "pie":
                    a.pie(values[col], labels=labels, autopct="%1.1f%%",
                          startangle=90, colors=_colors(len(values[col])))
                else:
                    a.bar(labels, values[col], color=color, alpha=0.8)
                    a.tick_params(axis="x", rotation=45)
                    a.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
                a.set_title(col, fontsize=12, fontweight="bold")
                if subplot_type != "pie":
                    a.set_xlabel(df.columns[0], fontsize=10)
                a.grid(True, alpha=0.3)
            for i in range(n, len(axes)):
                axes[i].set_visible(False)
            fig.suptitle(question, fontsize=14, fontweight="bold", y=1.02)
            fig.tight_layout()

        # ── 산점도 ────────────────────────────────────────────────────────
        elif resolved == "scatter":
            cols = df.columns.tolist()
            if len(cols) >= 3 and pd.api.types.is_string_dtype(df[cols[1]]):
                cats = df[cols[1]].unique()
                for i, cat in enumerate(sorted(cats)):
                    sub = df[df[cols[1]] == cat]
                    ax.scatter(sub[cols[0]], sub[cols[2]],
                               color=cmap(i / len(cats)), label=str(cat), alpha=0.7, s=60)
                ax.legend(title=cols[1], loc="best")
                _decorate(ax, xlabel=cols[0], ylabel=cols[2], title=question)
            else:
                num_cols = df.select_dtypes(include="number").columns
                if len(num_cols) >= 2:
                    ax.scatter(df[num_cols[0]], df[num_cols[1]],
                               color=cmap(0.6), alpha=0.7, s=60)
                    ax.set_xlabel(num_cols[0], fontsize=12)
                    ax.set_ylabel(num_cols[1], fontsize=12)
            ax.set_title(question, fontsize=14, fontweight="bold")
            ax.grid(True, alpha=0.3)

        # ── 히스토그램 ────────────────────────────────────────────────────
        elif resolved == "histogram":
            for i, col in enumerate(values.columns):
                ax.hist(values[col], bins=15, alpha=0.6, label=col,
                        color=cmap(i / max(len(values.columns), 1)))
            ax.legend(loc="best")
            _decorate(ax, xlabel="값", ylabel="빈도", title=question)
            _fmty(ax)

        # ── 박스플롯 ──────────────────────────────────────────────────────
        elif resolved == "boxplot":
            box = ax.boxplot(
                [values[col] for col in values.columns],
                patch_artist=True,
                labels=values.columns,
            )
            for patch, i in zip(box["boxes"], range(len(values.columns))):
                patch.set_facecolor(cmap(i / max(len(values.columns), 1)))
            _decorate(ax, xlabel="항목", ylabel="값", title=question)
            _fmty(ax)

        # ── 막대 (기본) ───────────────────────────────────────────────────
        else:
            if len(values.columns) == 1:
                ax.bar(labels, values.iloc[:, 0].tolist(), color=_colors(len(labels)))
                _decorate(ax, xlabel=df.columns[0], ylabel=values.columns[0], title=question, rotate_x=True)
            else:
                x = np.arange(len(labels))
                w = 0.8 / len(values.columns)
                for i, col in enumerate(values.columns):
                    off = (i - len(values.columns) / 2) * w + w / 2
                    ax.bar(x + off, values[col], w, label=col,
                           color=cmap(i / max(len(values.columns), 1)))
                ax.set_xticks(x)
                ax.set_xticklabels(labels.astype(str), rotation=45, ha="right")
                ax.legend(loc="best")
                _decorate(ax, xlabel=df.columns[0], ylabel="값", title=question)
            _fmty(ax)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("utf-8")
        plt.close(fig)
        return b64, data_json

    except Exception as e:
        print(f"[WARN] 차트 생성 오류: {e}")
        traceback.print_exc()
        plt.close("all")
        return None, None
