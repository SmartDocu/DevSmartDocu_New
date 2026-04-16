import json
import locale
from functools import cmp_to_key
import inspect
from utilsPrj.errorlogs import error_log

locale.setlocale(locale.LC_ALL, '')

def draw_table(request, columns, dict_rows, tablejson, coljson):
    try:
        def style_to_css(style_dict, border_color=None):
            styles = [
                f"background-color: {style_dict.get('bgcolor', '#ffffff')}",
                f"text-align: {style_dict.get('align', 'left')}",
                f"color: {style_dict.get('color', '#000000')}",
                f"font-weight: {700 if style_dict.get('fontweight') == 'bold' else 400}",
                f"font-size: {style_dict.get('fontsize', 14)}pt"
            ]
            if border_color:
                styles.append(f"border: 1px solid {border_color}")
            return '; '.join(styles)

        # 0. 정렬 처리
        def compare_rows(a, b):
            for s in tablejson.get('sort', []):
                col = s['column']
                direction = s.get('direction', 'asc')
                va = a.get(col)
                vb = b.get(col)

                # None 처리 (없으면 뒤로)
                if va is None and vb is None:
                    cmp_result = 0
                elif va is None:
                    cmp_result = 1
                elif vb is None:
                    cmp_result = -1
                else:
                    # 숫자 비교인지 문자열 비교인지 감지
                    if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                        cmp_result = (va > vb) - (va < vb)
                    else:
                        # 문자열 비교, locale.strcoll로 로케일 정렬
                        cmp_result = locale.strcoll(str(va), str(vb))

                if cmp_result != 0:
                    return cmp_result if direction == 'asc' else -cmp_result
            return 0
        
        if 'sort' in tablejson:
            dict_rows = sorted(dict_rows, key=cmp_to_key(compare_rows))

        # ✅ 1. coljson에서 enabled == 'y'인 컬럼만 추출 + 정렬
        enabled_cols = sorted(
            [col for col, conf in coljson.items() if conf.get('enabled', 'y') == 'y'],
            key=lambda col: coljson[col].get('order', 0)
        )

        # ✅ 2. 총 너비 계산
        total_width = sum(coljson.get(col, {}).get("width", 100) for col in enabled_cols)

        html = []

        table_bordercolor = tablejson.get('table_bordercolor', '#000000')
        html.append(f'<table id="preview-result-table" border="1" cellpadding="5" cellspacing="0" '
                    f'style="border-collapse: collapse; border: 1px solid {table_bordercolor}; '
                    f'width: {total_width}px;">')
        
        # ✅ 3. Header 출력
        if tablejson.get('row_visible', 'y') == 'y':
            html.append("<thead><tr>")
            for col in enabled_cols:
                header_style = {
                    "bgcolor": tablejson.get("row_bgcolor", "#eeeeee"),
                    "align": tablejson.get("row_align", "center"),
                    "color": tablejson.get("row_color", "#000000"),
                    "fontweight": tablejson.get("row_fontweight", "normal"),
                    "fontsize": int(tablejson.get("row_fontsize", 14))
                }
                border_color = tablejson.get('row_bordercolor', table_bordercolor)
                style_str = style_to_css(header_style, border_color)
                col_width = coljson.get(col, {}).get("width", 300)
                html.append(f'<th style="width: {col_width}px; {style_str}">{col}</th>')
            html.append("</tr></thead>")

        # ✅ 4. Body
        html.append("<tbody>")
        for row in dict_rows:
            html.append('<tr>')
            for col in enabled_cols:
                val = row.get(col, "")
                col_style = coljson.get(col, {})
                border_color = tablejson.get('row_bordercolor', table_bordercolor)
                css = style_to_css(col_style, border_color)
                col_width = col_style.get("width", 300)

                original = val
                display = val

                if col_style.get("measureyn") == "y" and isinstance(val, (int, float)):
                    decimals = int(col_style.get("decimal", 0))
                    unityn = col_style.get("unityn", "n")

                    if unityn == "y":
                        display = f"{val:,.{decimals}f}"
                    else:
                        display = f"{val:.{decimals}f}"
                else:
                    display = str(display).replace('\n', '<br>').replace('\r', '')

                html.append(f'<td style="width: {col_width}px; {css}" data-original="{original}">{display}</td>')
            html.append("</tr>")
        html.append("</tbody></table>")

        return '\n'.join(html)

    except Exception as e:
        # --------------------------------------------
        # 오류 로그 저장
        # --------------------------------------------
        try:
            error_log(
                request,
                e,
                inspect.currentframe().f_code.co_name,
                request.session.get("user", {}).get("id", None) if request else None,
                tablejson,              # remark1
                coljson,               # remark2
                "TABLE 생성 중 오류"       # remark3
            )
        except Exception as log_err:
            raise log_err  # 로그 저장 실패 시 서버에서 반드시 알도록

        raise e  # 원래 오류 전달