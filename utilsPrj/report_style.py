"""
d2doc 보고서 기본 스타일 — 표(TA)·차트(CA)의 모양은 이 파일 한 곳에서만 정한다.

- 프롬프트에 모양 지정이 없으면 여기 값이 적용되고, 지정이 있으면 지정값이 우선한다.
  · 표: 서식 LLM이 "사용자가 말한 속성만" 돌려주고, chapter_making_ai_table.render_table_html이
    이 기본값 위에 덮어쓴다.
  · 차트: LLM 코드가 축을 만든 직후 style_axes(ax)를 불러 기본값을 입히고, 그 뒤에 직접 적은 값
    (사용자가 지정한 색 등)이 덮어쓴다. matplotlib 전역 설정은 바꾸지 않는다.
- 값은 채팅창 보고서 PDF(jeff_docs/report/report_20260928/2013년9월_매출증감_원인분석.pdf)
  에서 실측한 색·크기다.
- 숫자 서식 함수는 화면 표시용 문자열만 만든다. 계산된 값은 바꾸지 않는다.
"""
import math
import numbers
import re

# ── 색 ───────────────────────────────────────────────────────────────────────
PRIMARY = "#1F4E79"     # 주색 (남색)
SECONDARY = "#7FA7CF"   # 보조색 (옅은 파랑)
ACCENT = "#E39B3B"      # 강조색 (주황)
INCREASE = "#2E8B57"    # 증가
DECREASE = "#C0392B"    # 감소
NEUTRAL = "#555555"     # 중립 (진한 회색)
NEUTRAL_LIGHT = "#AAAAAA"
TEXT = "#222222"

# 차트 색 순서: 주색 → 보조색 → 강조색 → 회색 계열.
# 원형차트처럼 항목마다 색이 달라야 하는 경우를 위해 같은 계열로 늘려 둔다.
CATEGORICAL = [
    PRIMARY, SECONDARY, ACCENT, NEUTRAL_LIGHT,
    "#4A7FB0", "#BFD3E8", "#F2C894", NEUTRAL,
]

# ── 표 ───────────────────────────────────────────────────────────────────────
# 속성 키는 서식 LLM이 돌려주는 키와 같다: bgcolor, color, fontsize(pt), fontweight, align
TABLE = {
    "font_size_pt": 9,
    "header": {"bgcolor": PRIMARY, "color": "#FFFFFF", "fontweight": "bold"},
    "body": {"bgcolor": "#FFFFFF", "color": TEXT, "fontweight": "normal"},
    "stripe_bgcolor": "#F4F8FB",            # 한 줄 걸러 옅은 바탕
    "total": {"color": PRIMARY, "fontweight": "bold"},
    "line": "1px solid #DDDDDD",            # 가로줄만 (세로선 없음)
    "padding": "3px 6px",
}

# ── 숫자 서식 ────────────────────────────────────────────────────────────────
# 컬럼 종류(kind)는 서식 LLM이 이름표만 붙인다. 계산은 하지 않는다.
#   number         : 일반 수 (정수면 소수점 없이, 아니면 소수 2자리까지)
#   percent        : 이미 % 단위인 값 (3.6 → "3.6%")
#   ratio          : 0~1 비율 (0.036 → "3.6%")
#   change         : 증감 (+1,234 / -56)
#   change_percent : 증감률, 이미 % 단위 (+3.6%)
#   text           : 서식 적용 안 함
NUMBER_KINDS = ("number", "percent", "ratio", "change", "change_percent", "text")


def is_number(v) -> bool:
    """int·float·numpy 숫자·Decimal이면 True (bool은 제외)."""
    return isinstance(v, numbers.Number) and not isinstance(v, (bool, complex))


def _plain(v: float, decimals) -> str:
    if decimals is not None:
        return f"{v:,.{int(decimals)}f}"
    if float(v).is_integer():
        return f"{v:,.0f}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def format_number(v, kind: str = "number", decimals=None) -> str:
    """숫자 → 표시용 문자열. 숫자가 아니면 그대로 문자열로 돌려준다."""
    if v is None:
        return ""
    if not is_number(v):
        return str(v)
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return ""
    kind = kind if kind in NUMBER_KINDS else "number"
    if kind == "text":
        return str(v)
    if kind in ("percent", "ratio", "change_percent"):
        pct = f * 100 if kind == "ratio" else f
        d = 1 if decimals is None else int(decimals)
        sign = "+" if kind == "change_percent" and pct > 0 else ""
        return f"{sign}{pct:,.{d}f}%"
    text = _plain(f, decimals)
    if kind == "change" and f > 0:
        text = "+" + text
    return text


# ── 차트 ─────────────────────────────────────────────────────────────────────
# matplotlib 전역 설정(rcParams)은 건드리지 않는다. LLM 코드가 만든 축(ax) 하나하나에만
# 스타일을 입힌다 — 동시에 여러 사용자의 차트가 그려져도 서로 섞이지 않는다.
CHART_DPI = 200
DEFAULT_FIGSIZE = (6.0, 3.6)       # A4 좌우 여백 3cm 기준 폭
MAX_FIG_WIDTH_IN = 6.2             # 문서 본문 폭 — 이보다 넓은 그림은 DOCX에서 잘린다

CHART = {
    "title_size": 11,
    "label_size": 9,
    "tick_size": 8.5,
    "legend_size": 8.5,
    "value_label_size": 7.5,
    "pie_text_size": 8.5,
    "text_size": 9,
    "tick_color": "#444444",
    "spine_color": "#888888",
    "grid_color": "#E3E3E3",
    "grid_width": 0.8,
    "frame_color": (217, 217, 217),     # 그림 전체를 두르는 옅은 회색 테두리
    "frame_px": 2,
    "pad_inches": 0.15,
}

# 프롬프트에 이런 말이 있으면 사용자가 직접 지정한 것으로 보고 해당 항목은 코드가 맞추지 않는다
_USER_SIZE = re.compile(r"글자\s*크기|글씨\s*크기|폰트|font|\d+\s*pt\b", re.IGNORECASE)
_USER_COLOR = re.compile(
    r"색상|색은|색으로|색:|컬러|colou?r|cmap|#[0-9a-f]{6}\b|빨간|빨강|파란|파랑|노란|노랑|초록|녹색|주황|보라|"
    r"검정|검은|회색|남색|하늘색|분홍",
    re.IGNORECASE,
)


def style_axes(ax):
    """축을 만든 직후 호출 — 색 순서, 테두리, 격자, 눈금 글자."""
    ax.set_prop_cycle(color=CATEGORICAL)
    _style_frame(ax, twin=False)
    return ax


def _style_frame(ax, twin):
    ax.spines["top"].set_visible(False)
    if twin:
        ax.spines["right"].set_color(CHART["spine_color"])
        ax.grid(False)
    else:
        ax.spines["right"].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(CHART["spine_color"])
        ax.set_axisbelow(True)
        ax.grid(axis="y", color=CHART["grid_color"], linewidth=CHART["grid_width"])
    ax.tick_params(colors=CHART["tick_color"])
    ax._d2_styled = True


def _value_text(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() or abs(v) >= 100 else f"{v:,.1f}"


def add_value_labels(ax):
    """막대 위(가로 막대는 오른쪽)에 값을 천 단위 구분으로 표시."""
    from matplotlib.container import BarContainer
    for container in ax.containers:
        if not isinstance(container, BarContainer):
            continue
        values = getattr(container, "datavalues", None)
        if values is None:
            continue
        labels = ["" if (v is None or (isinstance(v, float) and math.isnan(v))) else _value_text(v)
                  for v in values]
        ax.bar_label(container, labels=labels, padding=2,
                     fontsize=CHART["value_label_size"], color=TEXT)


def twinx(ax):
    """이중 Y축. 오른쪽 축의 색 순서를 왼쪽 축에서 이미 쓴 색 다음부터 이어 간다."""
    ax2 = ax.twinx()
    used = len(ax.containers) + len(ax.lines)
    ax2.set_prop_cycle(color=CATEGORICAL[used:] + CATEGORICAL[:used])
    _style_frame(ax2, twin=True)
    return ax2


def finish_axes(*axes):
    """다 그린 뒤 호출 — 천 단위 축, 겹치는 x축 눈금 기울이기. 사용자가 이미 지정한 것은 건드리지 않는다.
    (저장 직전 save_chart_png 가 한 번 더 부르므로 LLM이 빠뜨려도 적용된다)"""
    from matplotlib.container import BarContainer
    from matplotlib.ticker import FuncFormatter, ScalarFormatter

    def _thousands(axis_obj, lim):
        if isinstance(axis_obj.get_major_formatter(), ScalarFormatter) and max(abs(lim[0]), abs(lim[1])) >= 1000:
            axis_obj.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))

    for ax in axes:
        if ax is None or _is_pie(ax):
            continue
        horizontal = any(isinstance(c, BarContainer) and getattr(c, "orientation", None) == "horizontal"
                         for c in ax.containers)
        if horizontal:
            _thousands(ax.xaxis, ax.get_xlim())
        else:
            _thousands(ax.yaxis, ax.get_ylim())
            ticks = ax.get_xticklabels()
            labels = [t.get_text() for t in ticks]
            crowded = len(labels) > 8 or max((len(s) for s in labels), default=0) > 8
            if crowded and all(t.get_rotation() == 0 for t in ticks):
                ax.tick_params(axis="x", labelrotation=45)
                for t in ax.get_xticklabels():
                    t.set_horizontalalignment("right")


# ── 저장 직전 마무리 ─────────────────────────────────────────────────────────
# LLM이 보조 함수를 빠뜨려도 기본 스타일이 적용되도록, PNG로 저장하기 직전에 코드가 직접
# 마무리한다. 이 그림(fig) 하나만 다루므로 다른 사용자의 차트와 섞이지 않는다.

def _is_pie(ax):
    from matplotlib.patches import Wedge
    return any(isinstance(p, Wedge) for p in ax.patches)


def _is_twin(ax):
    """ax.twinx()로 만든 오른쪽 축인가 (눈금이 오른쪽에만 있다)."""
    return ax.yaxis.get_ticks_position() == "right"


def _matplotlib_default_colors():
    import matplotlib
    from matplotlib.colors import to_hex
    colors = list(matplotlib.rcParamsDefault["axes.prop_cycle"].by_key()["color"])
    for name in ("tab10", "tab20", "Set2", "Set3", "Pastel1"):
        try:
            cmap = matplotlib.colormaps[name]
            colors += [to_hex(c) for c in getattr(cmap, "colors", [])]
        except Exception:
            pass
    return {c.lower() for c in colors}


def _recolor(fig):
    """matplotlib 기본 색표 색으로 그려진 것만 기본 스타일 색으로 바꾼다 (등장 순서대로)."""
    from matplotlib.colors import to_hex, to_rgba
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    defaults = _matplotlib_default_colors()
    mapping = {}

    def new_color(c):
        try:
            rgba = to_rgba(c)
        except (ValueError, TypeError):
            return None
        key = to_hex(rgba).lower()
        if key not in defaults:
            return None
        if key not in mapping:
            mapping[key] = CATEGORICAL[len(mapping) % len(CATEGORICAL)]
        return to_rgba(mapping[key], rgba[3])

    def paint(artist):
        if isinstance(artist, Patch):
            c = new_color(artist.get_facecolor())
            if c is not None:
                artist.set_facecolor(c)
        elif isinstance(artist, Line2D):
            for get, set_ in ((artist.get_color, artist.set_color),
                              (artist.get_markerfacecolor, artist.set_markerfacecolor),
                              (artist.get_markeredgecolor, artist.set_markeredgecolor)):
                c = new_color(get())
                if c is not None:
                    set_(c)

    for ax in fig.axes:
        for artist in list(ax.patches) + list(ax.lines):
            paint(artist)
    for ax in fig.axes:                       # 범례 견본도 같은 색으로
        legend = ax.get_legend()
        if legend is not None:
            for h in legend.legend_handles:
                paint(h)


def _apply_sizes(fig):
    from matplotlib.text import Annotation
    if fig._suptitle is not None:
        fig._suptitle.set_fontsize(CHART["title_size"])
    for ax in fig.axes:
        if ax.title.get_text():
            ax.title.set_fontsize(CHART["title_size"])
            ax.title.set_fontweight("bold")
        ax.xaxis.label.set_fontsize(CHART["label_size"])
        ax.yaxis.label.set_fontsize(CHART["label_size"])
        ax.tick_params(labelsize=CHART["tick_size"])
        pie = _is_pie(ax)
        for t in ax.texts:
            if pie:
                t.set_fontsize(CHART["pie_text_size"])
            elif isinstance(t, Annotation):          # 막대 값 표시
                t.set_fontsize(CHART["value_label_size"])
            else:
                t.set_fontsize(CHART["text_size"])
        legend = ax.get_legend()
        if legend is not None:
            for t in legend.get_texts():
                t.set_fontsize(CHART["legend_size"])


def _legend_one_row(ax):
    """범례를 테두리 없이 한 줄로 편다 (항목 4개 이하). 위치는 LLM/사용자가 정한 곳 유지."""
    legend = ax.get_legend()
    if legend is None:
        return None
    legend.get_frame().set_visible(False)
    handles = list(legend.legend_handles)
    labels = [t.get_text() for t in legend.get_texts()]
    if _is_pie(ax) or not handles or len(handles) > 4 or legend._ncols == len(handles):
        return legend
    loc = legend._loc if legend._loc != 0 else 2       # 'best'(0) → 왼쪽 위
    size = legend.get_texts()[0].get_fontsize() if legend.get_texts() else CHART["legend_size"]
    return ax.legend(handles, labels, loc=loc, ncol=len(handles), frameon=False, fontsize=size)


def _inches(fig, ax):
    pos = ax.get_position()
    w, h = fig.get_size_inches()
    return pos.width * w, pos.height * h


def _make_room(fig):
    """막대 값 표시가 겹치면 세워 쓰고, 값 표시·범례가 들어갈 만큼 y축 위쪽을 늘린다."""
    import numpy as np
    from matplotlib.container import BarContainer
    from matplotlib.text import Annotation

    # 범례가 그래프 안쪽 위에 있으면 그 높이만큼 모든 축의 위쪽을 비운다
    legend_frac = 0.0
    for ax in fig.axes:
        legend = ax.get_legend()
        if legend is not None and not _is_pie(ax) and legend._loc in (0, 1, 2, 9):
            _, ax_h = _inches(fig, ax)
            rows = max(1, math.ceil(len(legend.legend_handles) / max(1, legend._ncols)))
            legend_frac = max(legend_frac, rows * CHART["legend_size"] * 1.8 / 72 / max(ax_h, 0.1))

    for ax in fig.axes:
        if _is_pie(ax):
            continue
        ax_w, ax_h = _inches(fig, ax)
        bars = [c for c in ax.containers if isinstance(c, BarContainer)
                and getattr(c, "orientation", "vertical") == "vertical"]
        labels = [t for t in ax.texts if isinstance(t, Annotation) and t.get_text()]
        top_data = None

        if bars:
            heights = [p.get_y() + p.get_height() for c in bars for p in c.patches]
            top_data = max(heights) if heights else None
        elif ax.lines:
            ys = [np.nanmax(np.asarray(l.get_ydata(), dtype=float)) for l in ax.lines
                  if len(l.get_ydata()) and np.isfinite(np.asarray(l.get_ydata(), dtype=float)).any()]
            top_data = max(ys) if ys else None

        label_frac = 0.0
        if bars and labels:
            x0, x1 = ax.get_xlim()
            bar_w = min(p.get_width() for c in bars for p in c.patches)
            slot_in = ax_w * bar_w / max(abs(x1 - x0), 1e-9)
            size = labels[0].get_fontsize()
            text_in = max(len(t.get_text()) for t in labels) * size * 0.6 / 72
            if text_in > slot_in * 1.05:
                for t in labels:
                    t.set_rotation(90)
                    t.set_horizontalalignment("center")
                    t.set_verticalalignment("bottom")
                label_frac = (text_in + 4 / 72) / max(ax_h, 0.1)
            else:
                label_frac = (size * 1.6 / 72) / max(ax_h, 0.1)
        elif ax.lines:
            label_frac = 0.06                                   # 선 끝 마커 여유

        need = min(label_frac + legend_frac + 0.03, 0.6)
        if top_data is not None and top_data > 0:
            bottom, top = ax.get_ylim()
            new_top = bottom + (top_data - bottom) / (1 - need)
            if new_top > top:
                ax.set_ylim(bottom, new_top)


def save_chart_png(fig, user_text: str = "") -> bytes:
    """차트를 문서용 PNG로 저장한다 (CA 미리보기와 문서가 같은 그림을 쓴다).
    - 그림 폭이 본문 폭보다 넓으면 비율을 유지한 채 그림판을 줄여 다시 그린다 (글자 크기 유지)
    - 프롬프트에 색 지정이 없으면 matplotlib 기본 색표 색을 기본 스타일 색으로 바꾼다
    - 프롬프트에 글자 크기 지정이 없으면 제목·축·범례·값 표시 글자를 기본 크기로 맞춘다
    - 원형 조각 사이 흰 구분선, 범례 한 줄, 값 표시·범례 자리만큼 위쪽 여유
    - 그림 전체에 옅은 회색 테두리 (문서에서 그래프 경계가 보이도록)
    """
    from io import BytesIO
    from PIL import Image, ImageDraw

    user_text = user_text or ""
    w, h = fig.get_size_inches()
    if w > MAX_FIG_WIDTH_IN:
        fig.set_size_inches(MAX_FIG_WIDTH_IN, h * MAX_FIG_WIDTH_IN / w)

    for ax in fig.axes:
        if _is_pie(ax):
            ax.grid(False)
            for p in ax.patches:
                p.set_edgecolor("white")
                p.set_linewidth(1.2)
        elif not getattr(ax, "_d2_styled", False):
            _style_frame(ax, twin=_is_twin(ax))
            ax.tick_params(labelsize=CHART["tick_size"])

    if not _USER_COLOR.search(user_text):
        _recolor(fig)
    if not _USER_SIZE.search(user_text):
        _apply_sizes(fig)

    finish_axes(*fig.axes)
    for ax in fig.axes:
        _legend_one_row(ax)

    def _layout():
        try:
            fig.tight_layout()
        except Exception:
            pass

    _layout()
    _make_room(fig)
    _layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=CHART["pad_inches"],
                dpi=CHART_DPI, facecolor="white")

    img = Image.open(BytesIO(buf.getvalue())).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i in range(CHART["frame_px"]):
        draw.rectangle([i, i, img.width - 1 - i, img.height - 1 - i], outline=CHART["frame_color"])
    out = BytesIO()
    img.save(out, format="PNG", dpi=(CHART_DPI, CHART_DPI))
    return out.getvalue()


# LLM 코드 실행 환경에 넣어 주는 보조 함수·값
CHART_HELPERS = {
    "DEFAULT_FIGSIZE": DEFAULT_FIGSIZE,
    "style_axes": style_axes,
    "add_value_labels": add_value_labels,
    "twinx": twinx,
    "finish_axes": finish_axes,
}
