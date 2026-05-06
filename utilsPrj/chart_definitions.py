
def get_legend_options():
    return [
        {"value": "best",         "label": "자동",       "term_key": "lbl.chart.legendpos.best"},
        {"value": "upper right",  "label": "오른쪽 위",  "term_key": "lbl.chart.legendpos.upper_right"},
        {"value": "upper left",   "label": "왼쪽 위",    "term_key": "lbl.chart.legendpos.upper_left"},
        {"value": "lower left",   "label": "왼쪽 아래",  "term_key": "lbl.chart.legendpos.lower_left"},
        {"value": "lower right",  "label": "오른쪽 아래","term_key": "lbl.chart.legendpos.lower_right"},
        {"value": "right",        "label": "오른쪽",     "term_key": "lbl.chart.legendpos.right"},
        {"value": "center left",  "label": "중앙 왼쪽",  "term_key": "lbl.chart.legendpos.center_left"},
        {"value": "center right", "label": "중앙 오른쪽","term_key": "lbl.chart.legendpos.center_right"},
        {"value": "lower center", "label": "하단 중앙",  "term_key": "lbl.chart.legendpos.lower_center"},
        {"value": "upper center", "label": "상단 중앙",  "term_key": "lbl.chart.legendpos.upper_center"},
        {"value": "center",       "label": "중앙",       "term_key": "lbl.chart.legendpos.center"},
    ]

def add_legend_option(properties):
    properties.append({
        "key": "legendPosition",
        "label": "범례 위치",
        "term_key": "lbl.chart.prop.legendPosition",
        "type": "select",
        "required": False,
        "options": get_legend_options()
    })
    return properties


def get_chart_types_detail():
    return [
        {
            "code": "bar",
            "name": "Bar Chart",
            "term_key": "cod.ui_chart.bar",
            "properties": add_legend_option([
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "xField",          "label": "X축 필드",     "term_key": "lbl.chart.prop.xField",         "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "xLabel",          "label": "X축 제목",     "term_key": "lbl.chart.prop.xLabel",         "type": "text",    "required": False},
                {"key": "yField",          "label": "Y축 필드",     "term_key": "lbl.chart.prop.yField",         "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "yLabel",          "label": "Y축 제목",     "term_key": "lbl.chart.prop.yLabel",         "type": "text",    "required": False},
                {"key": "categoryField",   "label": "범주",         "term_key": "lbl.chart.prop.categoryField",  "type": "select",  "required": False, "fieldFilter": "category"},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "showDataLabels",  "label": "값 라벨 표시", "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": True},
                {"key": "barWidth",        "label": "막대 너비",    "term_key": "lbl.chart.prop.barWidth",       "type": "number",  "required": False, "default": 0.2},
                {"key": "barGap",          "label": "막대 간 간격", "term_key": "lbl.chart.prop.barGap",         "type": "number",  "required": False, "default": 0.05}
            ])
        },
        {
            "code": "horizontalBar",
            "name": "Horizontal Bar Chart",
            "term_key": "cod.ui_chart.horizontalBar",
            "properties": add_legend_option([
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "yField",          "label": "x축 필드",     "term_key": "lbl.chart.prop.hbar.yField",    "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "yLabel",          "label": "x축 제목",     "term_key": "lbl.chart.prop.hbar.yLabel",    "type": "text",    "required": False},
                {"key": "xField",          "label": "y축 필드",     "term_key": "lbl.chart.prop.hbar.xField",    "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "xLabel",          "label": "y축 제목",     "term_key": "lbl.chart.prop.hbar.xLabel",    "type": "text",    "required": False},
                {"key": "categoryField",   "label": "범주",         "term_key": "lbl.chart.prop.categoryField",  "type": "select",  "required": False, "fieldFilter": "category"},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "showDataLabels",  "label": "값 라벨 표시", "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": True},
                {"key": "barWidth",        "label": "막대 너비",    "term_key": "lbl.chart.prop.barWidth",       "type": "number",  "required": False, "default": 0.2},
                {"key": "barGap",          "label": "막대 간 간격", "term_key": "lbl.chart.prop.barGap",         "type": "number",  "required": False, "default": 0.05}
            ])
        },
        {
            "code": "line",
            "name": "Line Chart",
            "term_key": "cod.ui_chart.line",
            "properties": add_legend_option([
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "xLabel",          "label": "X축 제목",     "term_key": "lbl.chart.prop.xLabel",         "type": "text",    "required": False},
                {"key": "xField",          "label": "X축 필드",     "term_key": "lbl.chart.prop.xField",         "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "yLabel",          "label": "Y축 제목",     "term_key": "lbl.chart.prop.yLabel",         "type": "text",    "required": False},
                {"key": "yField",          "label": "Y축 필드",     "term_key": "lbl.chart.prop.yField",         "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "categoryField",   "label": "범주",         "term_key": "lbl.chart.prop.categoryField",  "type": "select",  "required": False, "fieldFilter": "category"},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "showMarkers",     "label": "마커 노출",    "term_key": "lbl.chart.prop.showMarkers",    "type": "boolean", "required": False, "default": False},
                {
                    "key": "lineStyle", "label": "선 스타일", "term_key": "lbl.chart.prop.lineStyle", "type": "select", "required": False,
                    "options": [
                        {"label": "실선",     "value": "solid",    "term_key": "lbl.chart.linestyle.solid"},
                        {"label": "점선",     "value": "dotted",   "term_key": "lbl.chart.linestyle.dotted"},
                        {"label": "대시선",   "value": "dashed",   "term_key": "lbl.chart.linestyle.dashed"},
                        {"label": "대시-점선","value": "dash_dot", "term_key": "lbl.chart.linestyle.dash_dot"}
                    ],
                    "default": "solid"
                },
                {"key": "lineWidth",       "label": "선 두께",      "term_key": "lbl.chart.prop.lineWidth",      "type": "number",  "required": False, "default": 2},
                {
                    "key": "marker", "label": "마커 모양", "term_key": "lbl.chart.prop.marker", "type": "select", "required": False, "default": "circle",
                    "options": [
                        {"label": "원",        "value": "circle",   "term_key": "lbl.chart.marker.circle"},
                        {"label": "사각형",    "value": "square",   "term_key": "lbl.chart.marker.square"},
                        {"label": "삼각형",    "value": "triangle", "term_key": "lbl.chart.marker.triangle"},
                        {"label": "다이아몬드","value": "diamond",  "term_key": "lbl.chart.marker.diamond"}
                    ]
                },
                {"key": "markerSize",      "label": "마커 크기",    "term_key": "lbl.chart.prop.markerSize",     "type": "number",  "required": False, "default": 6},
                {"key": "showDataLabels",  "label": "값 라벨 표시", "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": False}
            ])
        },
        {
            "code": "pie",
            "name": "Pie Chart",
            "term_key": "cod.ui_chart.pie",
            "properties": [
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "labelField",      "label": "범주 필드",    "term_key": "lbl.chart.prop.labelField",     "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "valueField",      "label": "값 필드",      "term_key": "lbl.chart.prop.valueField",     "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "showDataLabels",  "label": "값 라벨 표시", "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": False},
                {
                    "key": "valueFormat", "label": "값 포맷", "term_key": "lbl.chart.prop.valueFormat", "type": "select", "required": False,
                    "default": "value+percent",
                    "options": [
                        {"label": "값",          "value": "value",        "term_key": "lbl.chart.valueformat.value"},
                        {"label": "백분율",      "value": "percent",      "term_key": "lbl.chart.valueformat.percent"},
                        {"label": "값 + 백분율", "value": "value+percent","term_key": "lbl.chart.valueformat.value_percent"}
                    ]
                }
            ]
        },
        {
            "code": "doughnut",
            "name": "Doughnut Chart",
            "term_key": "cod.ui_chart.doughnut",
            "properties": [
                {"key": "title",           "label": "그래프 제목",    "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "labelField",      "label": "범주 필드",      "term_key": "lbl.chart.prop.labelField",     "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "valueField",      "label": "값 필드",        "term_key": "lbl.chart.prop.valueField",     "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "cutout",          "label": "구멍 크기 (%)",  "term_key": "lbl.chart.prop.cutout",         "type": "number",  "required": False},
                {"key": "colorPalette",    "label": "색상 테마",      "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "showDataLabels",  "label": "값 라벨 표시",   "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": False},
                {
                    "key": "valueFormat", "label": "값 포맷", "term_key": "lbl.chart.prop.valueFormat", "type": "select", "required": False,
                    "default": "value+percent",
                    "options": [
                        {"label": "값",          "value": "value",        "term_key": "lbl.chart.valueformat.value"},
                        {"label": "백분율",      "value": "percent",      "term_key": "lbl.chart.valueformat.percent"},
                        {"label": "값 + 백분율", "value": "value+percent","term_key": "lbl.chart.valueformat.value_percent"}
                    ]
                }
            ]
        },
        {
            "code": "bubble",
            "name": "Bubble Chart",
            "term_key": "cod.ui_chart.bubble",
            "properties": add_legend_option([
                {"key": "title",           "label": "그래프 제목",   "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "xLabel",          "label": "X축 제목",      "term_key": "lbl.chart.prop.xLabel",         "type": "text",    "required": False},
                {"key": "xField",          "label": "X축 필드",      "term_key": "lbl.chart.prop.xField",         "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "yLabel",          "label": "Y축 제목",      "term_key": "lbl.chart.prop.yLabel",         "type": "text",    "required": False},
                {"key": "yField",          "label": "Y축 필드",      "term_key": "lbl.chart.prop.yField",         "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "sizeField",       "label": "원 크기 필드",  "term_key": "lbl.chart.prop.sizeField",      "type": "select",  "required": False, "fieldFilter": "numeric"},
                {"key": "categoryField",   "label": "범주",          "term_key": "lbl.chart.prop.categoryField",  "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "colorPalette",    "label": "색상 테마",     "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "showDataLabels",  "label": "값 라벨 표시",  "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": False},
                {"key": "showGroupLabels", "label": "그룹 라벨 표시","term_key": "lbl.chart.prop.showGroupLabels","type": "select",  "required": False, "default": "N", "options": ["Y", "N"]}
            ])
        },
        {
            "code": "hist",
            "name": "Histogram",
            "term_key": "cod.ui_chart.hist",
            "properties": [
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",          "type": "text",    "required": False},
                {"key": "valueField",      "label": "값 필드",      "term_key": "lbl.chart.prop.valueField",     "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "bins",            "label": "빈 개수",      "term_key": "lbl.chart.prop.bins",           "type": "number",  "required": False},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",   "type": "select",  "required": False},
                {"key": "xLabel",          "label": "X축 제목",     "term_key": "lbl.chart.prop.xLabel",         "type": "text",    "required": False},
                {"key": "yLabel",          "label": "Y축 제목",     "term_key": "lbl.chart.prop.yLabel",         "type": "text",    "required": False},
                {"key": "showDataLabels",  "label": "값 라벨 표시", "term_key": "lbl.chart.prop.showDataLabels", "type": "boolean", "required": False, "default": False},
                {"key": "rwidth",          "label": "막대 폭 비율", "term_key": "lbl.chart.prop.rwidth",         "type": "number",  "required": False, "default": 0.9}
            ]
        },
        {
            "code": "box",
            "name": "Box Plot",
            "term_key": "cod.ui_chart.box",
            "properties": [
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",               "type": "text",    "required": False},
                {"key": "xLabel",          "label": "X축 제목",     "term_key": "lbl.chart.prop.xLabel",              "type": "text",    "required": False},
                {"key": "categoryField",   "label": "X축 필드",     "term_key": "lbl.chart.prop.box.categoryField",   "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "yLabel",          "label": "Y축 제목",     "term_key": "lbl.chart.prop.yLabel",              "type": "text",    "required": False},
                {"key": "valueField",      "label": "Y축 필드",     "term_key": "lbl.chart.prop.box.valueField",      "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",        "type": "select",  "required": False},
                {"key": "notch",           "label": "노치 노출",    "term_key": "lbl.chart.prop.notch",               "type": "boolean", "required": False, "default": False},
                {"key": "showMeans",       "label": "평균값 노출",  "term_key": "lbl.chart.prop.showMeans",           "type": "boolean", "required": False, "default": False},
                {"key": "showFliers",      "label": "이상치 노출",  "term_key": "lbl.chart.prop.showFliers",          "type": "boolean", "required": False, "default": True},
                {"key": "widths",          "label": "박스 너비",    "term_key": "lbl.chart.prop.widths",              "type": "number",  "required": False, "default": 0.5},
                {"key": "whis",            "label": "수염 범위",    "term_key": "lbl.chart.prop.whis",                "type": "number",  "required": False, "default": 1.5}
            ]
        },
        {
            "code": "pareto",
            "name": "Pareto Chart",
            "term_key": "cod.ui_chart.pareto",
            "properties": [
                {"key": "title",           "label": "그래프 제목",  "term_key": "lbl.chart.prop.title",              "type": "text",    "required": False},
                {"key": "xLabel",          "label": "X축 제목",     "term_key": "lbl.chart.prop.xLabel",             "type": "text",    "required": False},
                {"key": "labelField",      "label": "X축 데이터",   "term_key": "lbl.chart.prop.pareto.labelField",  "type": "select",  "required": True,  "fieldFilter": "category"},
                {"key": "yField",          "label": "Y축 데이터",   "term_key": "lbl.chart.prop.pareto.yField",      "type": "select",  "required": True,  "fieldFilter": "numeric"},
                {
                    "key": "lineStyle", "label": "선 스타일", "term_key": "lbl.chart.prop.lineStyle", "type": "select", "required": False,
                    "options": [
                        {"label": "실선",     "value": "-",   "term_key": "lbl.chart.linestyle.solid"},
                        {"label": "점선",     "value": ":",   "term_key": "lbl.chart.linestyle.dotted"},
                        {"label": "대시선",   "value": "--",  "term_key": "lbl.chart.linestyle.dashed"},
                        {"label": "대시-점선","value": "-.",  "term_key": "lbl.chart.linestyle.dash_dot"}
                    ],
                    "default": "-"
                },
                {"key": "lineWidth",       "label": "선 두께",      "term_key": "lbl.chart.prop.lineWidth",          "type": "number",  "required": False, "default": 2},
                {"key": "colorPalette",    "label": "색상 테마",    "term_key": "lbl.chart.prop.colorPalette",       "type": "select",  "required": False}
            ]
        }
    ]
