
def get_legend_options():
    return [
        {"value": "best", "label": "자동"},
        {"value": "upper right", "label": "오른쪽 위"},
        {"value": "upper left", "label": "왼쪽 위"},
        {"value": "lower left", "label": "왼쪽 아래"},
        {"value": "lower right", "label": "오른쪽 아래"},
        {"value": "right", "label": "오른쪽"},
        {"value": "center left", "label": "중앙 왼쪽"},
        {"value": "center right", "label": "중앙 오른쪽"},
        {"value": "lower center", "label": "하단 중앙"},
        {"value": "upper center", "label": "상단 중앙"},
        {"value": "center", "label": "중앙"},
    ]

def add_legend_option(properties):
    properties.append({
        "key": "legendPosition",
        "label": "범례 위치",
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
            "properties": add_legend_option([
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "xField", "label": "X축 필드", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "xLabel", "label": "X축 제목", "type": "text", "required": False},
                {"key": "yField", "label": "Y축 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "yLabel", "label": "Y축 제목", "type": "text", "required": False},
                {"key": "categoryField", "label": "범주", "type": "select", "required": False, "fieldFilter": "category"},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": True},
                {"key": "barWidth", "label": "막대 너비", "type": "number", "required": False, "default": 0.2},
                {"key": "barGap", "label": "막대 간 간격", "type": "number", "required": False, "default": 0.05}
            ])
        },
        {
            "code": "horizontalBar",
            "name": "Horizontal Bar Chart",
            "properties": add_legend_option([
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "yField", "label": "x축 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "yLabel", "label": "x축 제목", "type": "text", "required": False},
                {"key": "xField", "label": "y축 필드", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "xLabel", "label": "y축 제목", "type": "text", "required": False},
                {"key": "categoryField", "label": "범주", "type": "select", "required": False, "fieldFilter": "category"},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": True},
                {"key": "barWidth", "label": "막대 너비", "type": "number", "required": False, "default": 0.2},
                {"key": "barGap", "label": "막대 간 간격", "type": "number", "required": False, "default": 0.05}
            ])
        },
        {
            "code": "line",
            "name": "Line Chart",
            "properties": add_legend_option([
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "xLabel", "label": "X축 제목", "type": "text", "required": False},
                {"key": "xField", "label": "X축 필드", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "yLabel", "label": "Y축 제목", "type": "text", "required": False},
                {"key": "yField", "label": "Y축 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "categoryField", "label": "범주", "type": "select", "required": False, "fieldFilter": "category"},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "showMarkers", "label": "마커 노출", "type": "boolean", "required": False, "default": False},
                {
                    "key": "lineStyle", "label": "선 스타일", "type": "select", "required": False,
                    "options": [
                        {"label": "실선", "value": "solid"},
                        {"label": "점선", "value": "dotted"},
                        {"label": "대시선", "value": "dashed"},
                        {"label": "대시-점선", "value": "dash_dot"}
                    ],
                    "default": "solid"
                },
                {"key": "lineWidth", "label": "선 두께", "type": "number", "required": False, "default": 2},
                {
                    "key": "marker", "label": "마커 모양", "type": "select", "required": False, "default": "circle",
                    "options": [
                        {"label": "원", "value": "circle"},
                        {"label": "사각형", "value": "square"},
                        {"label": "삼각형", "value": "triangle"},
                        {"label": "다이아몬드", "value": "diamond"}
                    ]
                },
                {"key": "markerSize", "label": "마커 크기", "type": "number", "required": False, "default": 6},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": False}
            ])
        },
        {
            "code": "pie",
            "name": "Pie Chart",
            "properties": [
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "labelField", "label": "범주 필드", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "valueField", "label": "값 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": False},
                {
                    "key": "valueFormat",
                    "label": "값 포맷",
                    "type": "select",
                    "required": False,
                    "default": "value+percent",
                    "options": [
                        {"label": "값", "value": "value"},
                        {"label": "백분율", "value": "percent"},
                        {"label": "값 + 백분율", "value": "value+percent"}
                    ]
                }
            ]
        },
        {
            "code": "doughnut",
            "name": "Doughnut Chart",
            "properties": [
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "labelField", "label": "범주 필드", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "valueField", "label": "값 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "cutout", "label": "구멍 크기 (%)", "type": "number", "required": False},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": False},
                {
                    "key": "valueFormat",
                    "label": "값 포맷",
                    "type": "select",
                    "required": False,
                    "default": "value+percent",
                    "options": [
                        {"label": "값", "value": "value"},
                        {"label": "백분율", "value": "percent"},
                        {"label": "값 + 백분율", "value": "value+percent"}
                    ]
                }
            ]
        },
        {
            "code": "bubble",
            "name": "Bubble Chart",
            "properties": add_legend_option([
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "xLabel", "label": "X축 제목", "type": "text", "required": False},
                {"key": "xField", "label": "X축 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "yLabel", "label": "Y축 제목", "type": "text", "required": False},
                {"key": "yField", "label": "Y축 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "sizeField", "label": "원 크기 필드", "type": "select", "required": False, "fieldFilter": "numeric"},
                {"key": "categoryField", "label": "범주", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": False},
                {"key": "showGroupLabels", "label": "그룹 라벨 표시", "type": "select", "required": False, "default": "N", "options": ["Y", "N"]}
            ])
        },
        {
            "code": "hist",
            "name": "Histogram",
            "properties": [
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "valueField", "label": "값 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "bins", "label": "빈 개수", "type": "number", "required": False},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "xLabel", "label": "X축 제목", "type": "text", "required": False},
                {"key": "yLabel", "label": "Y축 제목", "type": "text", "required": False},
                {"key": "showDataLabels", "label": "값 라벨 표시", "type": "boolean", "required": False, "default": False},
                {"key": "rwidth", "label": "막대 폭 비율", "type": "number", "required": False, "default": 0.9}
            ]
        },
        {
            "code": "box",
            "name": "Box Plot",
            "properties": [
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "xLabel", "label": "X축 제목", "type": "text", "required": False},
                {"key": "categoryField", "label": "X축 필드", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "yLabel", "label": "Y축 제목", "type": "text", "required": False},
                {"key": "valueField", "label": "Y축 필드", "type": "select", "required": True, "fieldFilter": "numeric"},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False},
                {"key": "notch", "label": "노치 노출", "type": "boolean", "required": False, "default": False},
                {"key": "showMeans", "label": "평균값 노출", "type": "boolean", "required": False, "default": False},
                {"key": "showFliers", "label": "이상치 노출", "type": "boolean", "required": False, "default": True},
                {"key": "widths", "label": "박스 너비", "type": "number", "required": False, "default": 0.5},
                {"key": "whis", "label": "수염 범위", "type": "number", "required": False, "default": 1.5}
            ]
        },
        {
            "code": "pareto",
            "name": "Pareto Chart",
            "properties": [
                {"key": "title", "label": "그래프 제목", "type": "text", "required": False},
                {"key": "xLabel", "label": "X축 제목", "type": "text", "required": False},
                {"key": "labelField", "label": "X축 데이터", "type": "select", "required": True, "fieldFilter": "category"},
                {"key": "yField", "label": "Y축 데이터", "type": "select", "required": True, "fieldFilter": "numeric"},
                {
                    "key": "lineStyle", "label": "선 스타일", "type": "select", "required": False,
                    "options": [
                        {"label": "실선", "value": "-"},
                        {"label": "점선", "value": ":"},
                        {"label": "대시선", "value": "--"},
                        {"label": "대시-점선", "value": "-."}
                    ],
                    "default": "-"
                },
                {"key": "lineWidth", "label": "선 두께", "type": "number", "required": False, "default": 2},
                {"key": "colorPalette", "label": "색상 테마", "type": "select", "required": False}
            ]
        }
    ]