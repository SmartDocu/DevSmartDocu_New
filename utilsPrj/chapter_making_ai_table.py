"""
AI 표(TA)를 HTML로 그린다. 미리보기 화면과 문서 생성(→ DOCX 변환)이 이 함수 하나를 쓴다.

모양은 utilsPrj/report_style.py 의 기본 스타일 위에, 서식 LLM이 돌려준
"사용자가 지정한 속성"만 덮어써서 정한다.
"""
import html as _html
import re

from utilsPrj import report_style as rs

# 선 모양(style)별·굵기(weight)별 실제 두께(px). double은 두 줄이 보이도록 더 두껍게 잡는다.
BORDER_WIDTH_PX = {
    "solid":  {"thin": 1, "normal": 2, "thick": 4},
    "dashed": {"thin": 1, "normal": 2, "thick": 4},
    "double": {"thin": 3, "normal": 4, "thick": 6},
}
BORDER_DEFAULT_CONF = {"color": "#000000", "style": "solid", "weight": "normal"}

_STYLE_KEYS = ("bgcolor", "color", "fontsize", "fontweight", "align")
_NUMERIC_TEXT = re.compile(r"^[+\-−]?[\d,]+(\.\d+)?%?$")


def _normalize_border_conf(conf):
    if isinstance(conf, str):
        return {**BORDER_DEFAULT_CONF, "color": conf}
    if isinstance(conf, dict):
        return {**BORDER_DEFAULT_CONF, **{k: v for k, v in conf.items() if k in BORDER_DEFAULT_CONF and v}}
    return dict(BORDER_DEFAULT_CONF)


def _border_css(conf):
    """{"color","style","weight"} → "2px dashed #ff1493" 같은 CSS 변 선언 값"""
    style = conf.get("style", "solid")
    weight = conf.get("weight", "normal")
    width = BORDER_WIDTH_PX.get(style, BORDER_WIDTH_PX["solid"]).get(weight, 2)
    return f"{width}px {style} {conf.get('color', '#000000')}"


def _user_props(d):
    """서식 LLM 응답에서 유효한 속성만 골라낸다 (빈 값은 '지정 안 함')."""
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if k in _STYLE_KEYS and v not in (None, "")}


def _font_size_css(v):
    s = str(v).strip().lower()
    if s.endswith("pt") or s.endswith("px"):
        return s
    try:
        return f"{float(s):g}pt"     # 서식 프롬프트의 글자 크기 단위는 pt
    except ValueError:
        return f"{rs.TABLE['font_size_pt']}pt"


def _cell_css(props, borders):
    parts = [
        f"background-color: {props.get('bgcolor', '#FFFFFF')}",
        f"color: {props.get('color', rs.TEXT)}",
        f"font-size: {_font_size_css(props.get('fontsize', rs.TABLE['font_size_pt']))}",
        f"font-weight: {props.get('fontweight', 'normal')}",
        f"text-align: {props.get('align', 'left')}",
        f"padding: {rs.TABLE['padding']}",
    ]
    parts += [f"border-{side}: {val}" for side, val in borders.items()]
    return "; ".join(parts) + ";"


def _format_spec(formats, col):
    spec = (formats or {}).get(col)
    if isinstance(spec, str):
        return spec, None
    if isinstance(spec, dict):
        return spec.get("kind", "number"), spec.get("decimals")
    return "number", None


def _looks_numeric(values):
    present = [v for v in values if v is not None and v != ""]
    if not present:
        return False
    return all(rs.is_number(v) or (isinstance(v, str) and _NUMERIC_TEXT.match(v.strip())) for v in present)


def render_table_html(data, user_style=None, formats=None, total_row_labels=None):
    """
    data            : list of dict (행 데이터, 컬럼 순서는 첫 행의 키 순서)
    user_style      : 사용자가 지정한 속성만 담긴 dict (없으면 기본 스타일 그대로)
        {"header": {...}, "data": {...}, "first_column": {...},
         "columns": {컬럼명: {...}},
         "border": {"outer","header_sep","col_sep","inner"}}
        각 {...} 의 키: bgcolor, color, fontsize(pt), fontweight, align
    formats         : {컬럼명: kind 또는 {"kind","decimals"}} — report_style.format_number 참고
    total_row_labels: 첫 컬럼 값이 이 목록에 있으면 합계 줄로 표시
    반환값: <table> HTML 문자열
    """
    user_style = user_style if isinstance(user_style, dict) else {}
    if not data:
        return '<table style="border-collapse: collapse; width: 100%;"></table>'

    columns = list(data[0].keys())
    total_cols = len(columns)
    total_rows = 1 + len(data)
    totals = {str(x).strip() for x in (total_row_labels or []) if str(x).strip()}

    header_user = _user_props(user_style.get("header"))
    data_user = _user_props(user_style.get("data"))
    first_col_user = _user_props(user_style.get("first_column"))
    col_user = {c: _user_props(v) for c, v in (user_style.get("columns") or {}).items()} \
        if isinstance(user_style.get("columns"), dict) else {}

    numeric_cols = {c for c in columns if _looks_numeric([row.get(c) for row in data])}

    # ── 테두리: 사용자가 지정했으면 4구간(바깥/머리줄 구분/1열 구분/안쪽), 아니면 가로줄만 ──
    user_border = user_style.get("border")
    if isinstance(user_border, dict) and user_border:
        conf = {k: _normalize_border_conf(user_border.get(k)) for k in ("outer", "header_sep", "col_sep", "inner")}

        def edge(idx, total, sep_conf):
            if idx == 0 or idx == total:
                return conf["outer"]
            return sep_conf if idx == 1 else conf["inner"]

        def borders_for(r, c):
            return {
                "top": _border_css(edge(r, total_rows, conf["header_sep"])),
                "bottom": _border_css(edge(r + 1, total_rows, conf["header_sep"])),
                "left": _border_css(edge(c, total_cols, conf["col_sep"])),
                "right": _border_css(edge(c + 1, total_cols, conf["col_sep"])),
            }
    else:
        def borders_for(r, c):
            return {"top": "none", "bottom": rs.TABLE["line"], "left": "none", "right": "none"}

    def align_of(col):
        return "right" if col in numeric_cols else "left"

    out = ['<table style="border-collapse: collapse; width: 100%;">', "<thead><tr>"]
    for c_idx, col in enumerate(columns):
        props = {**rs.TABLE["header"], "align": align_of(col), **header_user}
        out.append(f'<th style="{_cell_css(props, borders_for(0, c_idx))}">{_html.escape(str(col))}</th>')
    out.append("</tr></thead><tbody>")

    for r_idx, row in enumerate(data, start=1):
        is_total = bool(totals) and str(row.get(columns[0], "")).strip() in totals
        out.append("<tr>")
        for c_idx, col in enumerate(columns):
            props = {**rs.TABLE["body"], "align": align_of(col)}
            if r_idx % 2 == 0:
                props["bgcolor"] = rs.TABLE["stripe_bgcolor"]
            if is_total:
                props.update(rs.TABLE["total"])
            props.update(data_user)
            if c_idx == 0:
                props.update(first_col_user)
            props.update(col_user.get(col, {}))

            kind, decimals = _format_spec(formats, col)
            text = rs.format_number(row.get(col), kind, decimals)
            text = _html.escape(text).replace("\r", "").replace("\n", "<br>")
            out.append(f'<td style="{_cell_css(props, borders_for(r_idx, c_idx))}">{text}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)
