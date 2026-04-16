from bs4 import BeautifulSoup

def render_preview_table(table_header_json, table_data_json, data):
    """
    JS llm/static/js/ai_actions.js 의 renderPreviewTable을 Python으로 변환한 버전.
    table_header_json, table_data_json: dict (컬럼 스타일)
    data: list of dict (행 데이터)
    반환값: HTML 문자열
    """

    # def safe_px(value, default=14):
    #     """값이 숫자가 아니거나 리스트/None이면 기본값 사용"""
    #     try:
    #         return f"{float(value)}px"
    #     except (TypeError, ValueError):
    #         return f"{default}px"

    # jeff 202602021140 수정
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

    soup = BeautifulSoup("<div id='output-box'></div>", "html.parser")
    box = soup.find(id="output-box")

    table = soup.new_tag("table")
    table["style"] = "border-collapse: collapse; width: 100%;"

    if not data:
        # 데이터가 없으면 빈 테이블 반환
        box.append(table)
        return str(soup)

    columns = list(data[0].keys())

    # === 헤더 생성 ===
    thead = soup.new_tag("thead")
    tr_head = soup.new_tag("tr")

    for col in columns:
        th = soup.new_tag("th")
        th.string = str(col)
        header_conf = table_header_json.get(col, {})

        th["style"] = (
            # f"font-size: {safe_px(header_conf.get('fontsize', 14))};"
            f"font-size: {safe_size(header_conf.get('fontsize', '14px'))};"    # jeff 202602021140 추가
            f"font-weight: {header_conf.get('fontweight', 'normal')};"
            f"text-align: {header_conf.get('align', 'center')};"
            f"background-color: {header_conf.get('bgcolor', '#f0f0f0')};"
            f"color: {header_conf.get('color', '#000000')};"
            f"padding: 4px 8px;"
            f"border: 1px solid #000000;"    # jeff 202602021140 추가
        )

        tr_head.append(th)
    thead.append(tr_head)
    table.append(thead)

    # === 데이터 행 ===
    tbody = soup.new_tag("tbody")

    for row in data:
        tr = soup.new_tag("tr")
        for col in columns:
            td = soup.new_tag("td")
            td.string = str(row.get(col, ""))
            conf = table_data_json.get(col, {})

            td["style"] = (
                # f"font-size: {safe_px(conf.get('fontsize', 14))};"
                f"font-size: {safe_size(conf.get('fontsize', 14))};"    # jeff 202602021140 추가
                f"font-weight: {conf.get('fontweight', 'normal')};"
                f"text-align: {conf.get('align', 'center')};"
                f"color: {conf.get('color', '#000000')};"
                f"background-color: {conf.get('bgcolor', '#ffffff')};"
                f"padding: 2px 6px;"
                f"border: 1px solid #000000;"    # jeff 202602021140 추가
            )

            tr.append(td)
        tbody.append(tr)
    table.append(tbody)
    box.append(table)

    return str(soup)
