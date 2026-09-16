from bs4 import BeautifulSoup

# 선 모양(style)별·굵기(weight)별 실제 두께(px). double은 두 줄이 보이도록 더 두껍게 잡는다.
BORDER_WIDTH_PX = {
    "solid":  {"thin": 1, "normal": 2, "thick": 4},
    "dashed": {"thin": 1, "normal": 2, "thick": 4},
    "double": {"thin": 3, "normal": 4, "thick": 6},
}
BORDER_DEFAULT_CONF = {"color": "#000000", "style": "solid", "weight": "normal"}


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


def render_preview_table(table_header_json, table_data_json, data, table_border_json=None):
    """
    JS llm/static/js/ai_actions.js 의 renderPreviewTable을 Python으로 변환한 버전.
    table_header_json, table_data_json: dict (컬럼 스타일)
    data: list of dict (행 데이터)
    table_border_json: dict, {"outer": {"color","style","weight"}, "header_sep": {...},
        "col_sep": {...}, "inner": {...}} — 지정 안 된 키/속성은 기본값(검정·실선·보통).
        - outer      : 표 전체를 감싸는 바깥 테두리
        - header_sep : 1행(헤더)과 2행(첫 데이터 행) 사이 구분선
        - col_sep    : 1열과 2열 사이 구분선
        - inner      : 나머지 내부 선
    반환값: HTML 문자열
    """
    border = table_border_json or {}
    outer_conf      = _normalize_border_conf(border.get("outer"))
    header_sep_conf = _normalize_border_conf(border.get("header_sep"))
    col_sep_conf    = _normalize_border_conf(border.get("col_sep"))
    inner_conf      = _normalize_border_conf(border.get("inner"))

    def safe_size(value, default="14px"):
        """폰트 사이즈를 그대로 반환 (pt, px 등 단위 포함)"""
        try:
            if isinstance(value, str) and (value.endswith('pt') or value.endswith('px')):
                return value
            elif isinstance(value, (int, float)):
                return f"{value}px"
            else:
                return default
        except:
            return default

    def edge_conf(idx, total, sep_idx, sep_conf):
        """idx번째 경계선(0=맨 앞 바깥, total=맨 뒤 바깥, sep_idx=구분선)의 스타일을 반환"""
        if idx == 0 or idx == total:
            return outer_conf
        if idx == sep_idx:
            return sep_conf
        return inner_conf

    def border_style(row_idx, col_idx, total_rows, total_cols):
        top    = edge_conf(row_idx,     total_rows, 1, header_sep_conf)
        bottom = edge_conf(row_idx + 1, total_rows, 1, header_sep_conf)
        left   = edge_conf(col_idx,     total_cols, 1, col_sep_conf)
        right  = edge_conf(col_idx + 1, total_cols, 1, col_sep_conf)
        return (
            f"border-top: {_border_css(top)};"
            f"border-bottom: {_border_css(bottom)};"
            f"border-left: {_border_css(left)};"
            f"border-right: {_border_css(right)};"
        )

    soup = BeautifulSoup("<div id='output-box'></div>", "html.parser")
    box = soup.find(id="output-box")

    table = soup.new_tag("table")
    table["style"] = "border-collapse: collapse; width: 100%;"

    if not data:
        # 데이터가 없으면 빈 테이블 반환
        box.append(table)
        return str(soup)

    columns = list(data[0].keys())
    total_cols = len(columns)
    total_rows = 1 + len(data)  # 헤더 1행 + 데이터 행

    # === 헤더 생성 ===
    thead = soup.new_tag("thead")
    tr_head = soup.new_tag("tr")

    for col_idx, col in enumerate(columns):
        th = soup.new_tag("th")
        th.string = str(col)
        header_conf = table_header_json.get(col, {})

        th["style"] = (
            f"font-size: {safe_size(header_conf.get('fontsize', '14px'))};"
            f"font-weight: {header_conf.get('fontweight', 'normal')};"
            f"text-align: {header_conf.get('align', 'center')};"
            f"background-color: {header_conf.get('bgcolor', '#f0f0f0')};"
            f"color: {header_conf.get('color', '#000000')};"
            f"padding: 4px 8px;"
            f"{border_style(0, col_idx, total_rows, total_cols)}"
        )

        tr_head.append(th)
    thead.append(tr_head)
    table.append(thead)

    # === 데이터 행 ===
    tbody = soup.new_tag("tbody")

    for row_idx, row in enumerate(data, start=1):
        tr = soup.new_tag("tr")
        for col_idx, col in enumerate(columns):
            td = soup.new_tag("td")
            td.string = str(row.get(col, ""))
            conf = table_data_json.get(col, {})

            td["style"] = (
                f"font-size: {safe_size(conf.get('fontsize', 14))};"
                f"font-weight: {conf.get('fontweight', 'normal')};"
                f"text-align: {conf.get('align', 'center')};"
                f"color: {conf.get('color', '#000000')};"
                f"background-color: {conf.get('bgcolor', '#ffffff')};"
                f"padding: 2px 6px;"
                f"{border_style(row_idx, col_idx, total_rows, total_cols)}"
            )

            tr.append(td)
        tbody.append(tr)
    table.append(tbody)
    box.append(table)

    return str(soup)
