import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from collections import defaultdict
# from sklearn.preprocessing import MinMaxScaler
import numpy as np
from matplotlib import font_manager, rc
import os
from utilsPrj.supabase_client import get_supabase_client
import inspect
from utilsPrj.errorlogs import error_log

def get_colors_from_palette(palette_name, count):
    if palette_name in plt.colormaps():
        cmap = plt.get_cmap(palette_name)
        if count == 1:
            return [cmap(0.5)]
        return [cmap(i / (count - 1)) for i in range(count)]
    else:
        return [palette_name]


# draw_bar_chart_common (bar, horizontalBar)
def draw_bar_chart_common(ax, dict_rows, properties, horizontal=False):
    x_field = properties.get("xField")
    y_field = properties.get("yField")
    category_field = properties.get("categoryField")

    if not x_field or not y_field:
        raise ValueError("xField와 yField가 필요합니다.")

    legend_position = properties.get("legendPosition", "best")
    show_data_labels = properties.get("showDataLabels", False)

    try:
        custom_bar_width = float(properties.get("barWidth", 0.0) or 0.0)
    except ValueError:
        custom_bar_width = 0.0

    try:
        bar_gap = float(properties.get("barGap", 0.0) or 0.0)
    except ValueError:
        bar_gap = 0.0
        

    if category_field:
        grouped = defaultdict(lambda: defaultdict(float))
        x_categories = set()
        category_labels = set()

        for row in dict_rows:
            x_val = row.get(x_field)
            cat_val = row.get(category_field)
            y_val = row.get(y_field)

            if x_val is None or cat_val is None or y_val is None:
                continue

            try:
                y_val = float(y_val)
            except:
                continue

            grouped[x_val][cat_val] += y_val
            x_categories.add(x_val)
            category_labels.add(cat_val)

        x_categories = sorted(x_categories)
        category_labels = sorted(category_labels)

        if not category_labels or not x_categories:
            raise ValueError("카테고리 데이터가 없습니다.")

        x_idx = range(len(x_categories))
        total_bar_space = 0.8
        bar_width = custom_bar_width if custom_bar_width else (total_bar_space - bar_gap * (len(category_labels) - 1)) / len(category_labels)

        colors = get_colors_from_palette(properties.get("colorPalette", "tab10"), len(category_labels))

        for i, cat in enumerate(category_labels):
            heights = [grouped[x].get(cat, 0) for x in x_categories]
            offset = [xi + i * (bar_width + bar_gap) for xi in x_idx]

            bars = ax.barh(offset, heights, bar_width, label=cat, color=colors[i % len(colors)]) if horizontal \
                else ax.bar(offset, heights, bar_width, label=cat, color=colors[i % len(colors)])

            # ▶ 데이터 라벨 표시 (겹침 방지 추가)
            if show_data_labels:
                last_label_pos = -float('inf')  # 마지막 표시된 라벨 위치 (픽셀 기준)
                min_pixel_distance = 20  # 라벨 최소 픽셀 간격, 필요에 따라 조절

                for bar in bars:
                    value = bar.get_width() if horizontal else bar.get_height()
                    # 데이터 좌표계에서 라벨 위치 (x, y)
                    if horizontal:
                        x_data = value
                        y_data = bar.get_y() + bar.get_height() / 2
                    else:
                        x_data = bar.get_x() + bar.get_width() / 2
                        y_data = value

                    # 데이터 좌표 -> 픽셀 좌표 변환
                    x_disp, y_disp = ax.transData.transform((x_data, y_data))

                    # 가로막대면 y 좌표(세로 방향) 기준으로, 세로막대면 x 좌표(가로 방향) 기준으로 거리 비교
                    label_pos = y_disp if horizontal else x_disp

                    if label_pos - last_label_pos > min_pixel_distance:
                        if horizontal:
                            ax.text(x_data, y_data, f"{value:,.0f}", va='center', ha='left', fontsize=9)
                        else:
                            ax.text(x_data, y_data, f"{value:,.0f}", va='bottom', ha='center', fontsize=9)
                        last_label_pos = label_pos

        tick_pos = [xi + ((bar_width + bar_gap) * len(category_labels)) / 2 - (bar_gap / 2) for xi in x_idx]
        if horizontal:
            ax.set_yticks(tick_pos)
            ax.set_yticklabels(x_categories, rotation=45, ha='right')
        else:
            ax.set_xticks(tick_pos)
            ax.set_xticklabels(x_categories, rotation=45, ha='right')

        # ax.set_xlabel(properties.get("xLabel", x_field))
        # ax.set_ylabel(properties.get("yLabel", y_field))
        if horizontal:
            ax.set_xlabel(properties.get("yLabel", y_field))  # 가로 막대: x축은 값
            ax.set_ylabel(properties.get("xLabel", x_field))  # 가로 막대: y축은 범주
        else:
            ax.set_xlabel(properties.get("xLabel", x_field))  # 세로 막대: x축은 범주
            ax.set_ylabel(properties.get("yLabel", y_field))  # 세로 막대: y축은 값
            
        ax.set_title(properties.get("title", "Bar Chart Preview"))
        ax.legend(loc=legend_position)

        if horizontal:
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        else:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

    else:
        x = [row[x_field] for row in dict_rows]
        y = [float(row[y_field]) if isinstance(row[y_field], (int, float, str)) else 0 for row in dict_rows]
        bar_width = custom_bar_width if custom_bar_width else 0.8

        colors = get_colors_from_palette(properties.get("colorPalette", "blue"), len(x))

        bars = ax.barh(x, y, height=bar_width, color=colors) if horizontal else ax.bar(x, y, width=bar_width, color=colors)

        if horizontal:
            ax.set_ylabel(properties.get("xLabel", x_field))
            ax.set_xlabel(properties.get("yLabel", y_field))
        else:
            ax.set_xlabel(properties.get("xLabel", x_field))
            ax.set_ylabel(properties.get("yLabel", y_field))
            ax.set_xticklabels(x, rotation=45, ha='right')

        ax.set_title(properties.get("title", "Bar Chart Preview"))

        if show_data_labels:
            last_label_pos = -float('inf')
            min_pixel_distance = 20

            for bar in bars:
                value = bar.get_width() if horizontal else bar.get_height()
                if horizontal:
                    x_data = value
                    y_data = bar.get_y() + bar.get_height() / 2
                else:
                    x_data = bar.get_x() + bar.get_width() / 2
                    y_data = value

                x_disp, y_disp = ax.transData.transform((x_data, y_data))
                label_pos = y_disp if horizontal else x_disp

                if label_pos - last_label_pos > min_pixel_distance:
                    if horizontal:
                        ax.text(x_data, y_data, f"{value:,.0f}", va='center', ha='left', fontsize=9)
                    else:
                        ax.text(x_data, y_data, f"{value:,.0f}", va='bottom', ha='center', fontsize=9)
                    last_label_pos = label_pos

        if horizontal:
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        else:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

def draw_bar_chart(ax, dict_rows, properties):
    draw_bar_chart_common(ax, dict_rows, properties, horizontal=False)

def draw_horizontal_bar_chart(ax, dict_rows, properties = None):
    draw_bar_chart_common(ax, dict_rows, properties, horizontal=True)

def draw_line_chart(ax, dict_rows, properties):
    ##### jeff 20251124 1330 추가
    import logging
    logger = logging.getLogger(__name__)
    
    logger.error(f"=== DRAW_LINE_CHART START ===")
    logger.error(f"dict_rows type: {type(dict_rows)}")
    logger.error(f"dict_rows length: {len(dict_rows) if isinstance(dict_rows, list) else 'not a list'}")
    
    # 🔥 방어 코드
    if not isinstance(dict_rows, list):
        logger.error(f"ERROR: dict_rows is not a list! type={type(dict_rows)}, value={dict_rows}")
        raise TypeError(f"dict_rows must be a list, got {type(dict_rows)}")
    
    for i, row in enumerate(dict_rows):
        logger.error(f"Processing row {i}, type: {type(row)}")
        
        if not isinstance(row, dict):
            logger.error(f"ERROR: row {i} is not dict! type={type(row)}, value={row}")
            raise TypeError(f"Row {i} must be dict, got {type(row)}")
    #####

    x_field = properties.get("xField")
    y_field = properties.get("yField")
    category_field = properties.get("categoryField")
    legend_position = properties.get("legendPosition", "best")

    if not x_field or not y_field:
        raise ValueError("xField와 yField가 필요합니다.")

    # lineStyle 처리: matplotlib 스타일 문자인 경우 그대로 사용, 아니면 맵핑
    line_style_user = properties.get("lineStyle", "-")
    valid_styles = ["-", ":", "--", "-."]
    if line_style_user in valid_styles:
        line_style = line_style_user
    else:
        line_style_map = {
            "solid": "-",
            "dotted": ":",
            "dashed": "--",
            "dash_dot": "-."
        }
        line_style = line_style_map.get(line_style_user, "-")

    # 마커 매핑 (사용자용 이름 → matplotlib 마커 문자)
    marker_map = {
        "circle": "o",
        "square": "s",
        "triangle": "^",
        "diamond": "D"
    }

    show_markers = properties.get("showMarkers", False)
    show_data_labels = properties.get("showDataLabels", False)

    # float 변환, 기본값 처리
    try:
        line_width = float(properties.get("lineWidth", 2))
    except Exception:
        line_width = 2

    try:
        marker_size = float(properties.get("markerSize", 6))
    except Exception:
        marker_size = 6

    marker_user = properties.get("marker", "circle")
    marker_style = marker_map.get(marker_user, "o") if show_markers else None

    grouped = defaultdict(lambda: defaultdict(list))
    x_categories = set()
    category_labels = set()

    for row in dict_rows:
        x_val = row.get(x_field)
        y_val = row.get(y_field)
        cat_val = row.get(category_field) if category_field else None

        if x_val is None or y_val is None:
            continue

        try:
            y_val = float(y_val)
        except:
            continue

        if category_field:
            grouped[cat_val][x_val].append(y_val)
            category_labels.add(cat_val)
        else:
            grouped[None][x_val].append(y_val)

        x_categories.add(x_val)

    x_categories = sorted(x_categories)
    categories = sorted(category_labels) if category_field else [None]

    colors = get_colors_from_palette(properties.get("colorPalette", "tab10"), len(categories))

    for i, cat in enumerate(categories):
        ys = []
        for x in x_categories:
            vals = grouped[cat].get(x, [])
            ys.append(sum(vals) / len(vals) if vals else float("nan"))

        label = cat if cat is not None else y_field

        line = ax.plot(
            x_categories,
            ys,
            label=label,
            linestyle=line_style,
            linewidth=line_width,
            color=colors[i % len(colors)],
            marker=marker_style,
            markersize=marker_size if show_markers else 0
        )[0]

        if show_data_labels:
            for x_val, y_val in zip(x_categories, ys):
                if y_val == y_val:  # NaN 체크
                    ax.text(x_val, y_val, f"{y_val:,.0f}", fontsize=9, ha='center', va='bottom')

    ax.set_xlabel(properties.get("xLabel", x_field))
    ax.set_ylabel(properties.get("yLabel", y_field))
    ax.set_title(properties.get("title", "Line Chart Preview"))
    ax.legend(loc=legend_position)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

    ax.set_xticks(range(len(x_categories)))
    ax.set_xticklabels(x_categories, rotation=45, ha='right')

def draw_pie_chart_common(ax, dict_rows, properties, doughnut=False):
    label_field = properties.get("labelField")
    value_field = properties.get("valueField")

    if not label_field or not value_field:
        raise ValueError("labelField와 valueField가 필요합니다.")

    if not dict_rows or label_field not in dict_rows[0] or value_field not in dict_rows[0]:
        raise ValueError(f"데이터에 '{label_field}' 또는 '{value_field}' 필드가 없습니다.")

    labels = [row[label_field] for row in dict_rows]
    raw_sizes = [row[value_field] for row in dict_rows]

    sizes = []
    for i, v in enumerate(raw_sizes):
        try:
            value = float(v)
        except Exception:
            raise ValueError(
                f"❌ 값 변환 오류: '{value_field}' 컬럼의 값 '{v}'은(는) 숫자가 아닙니다.\n"
                f"👉 '{label_field}' = '{labels[i]}' 항목에서 오류가 발생했습니다."
            )

        if value < 0:
            raise ValueError(
                f"❌ 파이 차트에는 음수 값이 허용되지 않습니다.\n"
                f"👉 항목 '{labels[i]}'의 '{value_field}' 값이 음수({value})입니다.\n"
                f"➡️ 값을 0 이상으로 수정하거나, 다른 차트 유형을 사용해주세요."
            )

        sizes.append(value)
         
    color_palette_name = properties.get("colorPalette")
    colors = get_colors_from_palette(color_palette_name, len(labels)) if color_palette_name else None

    show_data_labels = properties.get("showDataLabels", False)
    value_format = properties.get("valueFormat", "value+percent")

    # ▶ 값 표기 포맷 설정
    if show_data_labels:
        if value_format == "value":
            total = sum(sizes)
            autopct = lambda pct: f'{(pct/100)*total:,.0f}'
        elif value_format == "percent":
            autopct = '%1.1f%%'
        elif value_format == "value+percent":
            total = sum(sizes)
            autopct = lambda pct: f'{(pct/100)*total:,.0f}\n({pct:.1f}%)'
        else:
            autopct = None
    else:
        autopct = None

    if autopct:
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct=autopct,
            colors=colors,
            startangle=90
        )
    else:
        wedges, texts = ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            startangle=90
        )

    if doughnut:
        cutout_ratio = properties.get("cutout")
        try:
            cutout_ratio = float(cutout_ratio) / 100 if cutout_ratio is not None else 0.7
            if not (0 <= cutout_ratio <= 1):
                cutout_ratio = 0.7
        except Exception:
            cutout_ratio = 0.7

        centre_circle = plt.Circle((0, 0), cutout_ratio, fc='white')
        ax.add_artist(centre_circle)

    ax.set_title(properties.get("title", "Pie Chart Preview"))

    legend_position = properties.get("legendPosition")
    if legend_position:
        ax.legend(wedges, labels, loc=legend_position)

def draw_pie_chart(ax, dict_rows, properties):
    draw_pie_chart_common(ax, dict_rows, properties, doughnut=False)

def draw_doughnut_chart(ax, dict_rows, properties):
    draw_pie_chart_common(ax, dict_rows, properties, doughnut=True)

def draw_bubble_chart(ax, dict_rows, properties):
    x_field = properties.get("xField")
    y_field = properties.get("yField")
    size_field = properties.get("sizeField")
    category_field = properties.get("categoryField")
    color_palette_name = properties.get("colorPalette")
    legend_position = properties.get("legendPosition", 'center left')
    show_data_labels = properties.get("showDataLabels", False)
    show_group_labels = properties.get("showGroupLabels", "N").lower()

    if not x_field or not y_field:
        raise ValueError("xField와 yField가 필요합니다.")

    # ▶ 크기 정규화
    raw_sizes = []
    for row in dict_rows:
        try:
            sv = float(row.get(size_field)) if size_field else 20
        except:
            sv = 20
        raw_sizes.append(sv)

    # if size_field:
    #     scaler = MinMaxScaler()
    #     normalized_sizes = scaler.fit_transform([[s] for s in raw_sizes])
    #     scaled_sizes = [s[0] * 90 + 10 for s in normalized_sizes]  # 10~100
    # else:
    #     scaled_sizes = [20] * len(dict_rows)

    if size_field:
        # numpy를 사용한 MinMax scaling
        import numpy as np
        raw_sizes_array = np.array(raw_sizes)
        min_val = raw_sizes_array.min()
        max_val = raw_sizes_array.max()
        
        if max_val != min_val:  # 0으로 나누기 방지
            normalized_sizes = (raw_sizes_array - min_val) / (max_val - min_val)
        else:
            normalized_sizes = np.zeros_like(raw_sizes_array)
        
        scaled_sizes = [s * 90 + 10 for s in normalized_sizes]  # 10~100
    else:
        scaled_sizes = [20] * len(dict_rows)

    # ▶ 그룹 분류 처리
    if category_field:
        category_data = {}
        for i, row in enumerate(dict_rows):
            try:
                xv = float(row.get(x_field))
                yv = float(row.get(y_field))
                sv = scaled_sizes[i]
                raw_sv = raw_sizes[i]
                category = row.get(category_field, "기타")

                if category not in category_data:
                    category_data[category] = {"x": [], "y": [], "s": [], "raw_s": [], "rows": []}
                category_data[category]["x"].append(xv)
                category_data[category]["y"].append(yv)
                category_data[category]["s"].append(sv)
                category_data[category]["raw_s"].append(raw_sv)
                category_data[category]["rows"].append(row)
            except:
                continue

        categories = list(category_data.keys())
        colors = get_colors_from_palette(color_palette_name, len(categories)) if color_palette_name else ["blue"] * len(categories)

        scatters = []
        for i, category in enumerate(categories):
            data = category_data[category]
            sc = ax.scatter(data["x"], data["y"], s=data["s"], color=colors[i], alpha=0.7, label=str(category))
            scatters.append(sc)

            # ▶ 원 크기 값 텍스트로 표기
            if show_data_labels and size_field:
                for x, y, raw_size in zip(data["x"], data["y"], data["raw_s"]):
                    ax.text(x, y, f'{raw_size}', fontsize=8, ha='center', va='center')

        # ▶ 그룹 분류 라벨 (그룹명) 표시
        if show_group_labels == 'y':
            y_min, y_max = ax.get_ylim()
            y_offset = (y_max - y_min) * 0.03
            for category in categories:
                data = category_data[category]
                if data["x"] and data["y"]:
                    x0 = data["x"][0]
                    y0 = data["y"][0]
                    ax.text(
                        x0,
                        y0 + y_offset,
                        str(category),
                        fontsize=9,
                        ha='center',
                        va='bottom',
                        color='black',
                        zorder=5
                    )

        # ▶ 범례 위치
        bbox_anchor = None
        if legend_position in ['center left', 'upper left', 'lower left']:
            bbox_anchor = (1.0, 0.5)
        elif legend_position in ['center right', 'upper right', 'lower right']:
            bbox_anchor = (-0.3, 0.5)

        ax.legend(handles=scatters, title=category_field, loc=legend_position, bbox_to_anchor=bbox_anchor)

    else:
        # ▶ 그룹 필드가 없을 경우 단일 scatter
        x, y, sizes, rows_for_labels = [], [], [], []
        for i, row in enumerate(dict_rows):
            try:
                x.append(float(row.get(x_field)))
                y.append(float(row.get(y_field)))
                sizes.append(scaled_sizes[i])
                rows_for_labels.append(row)
            except:
                continue

        colors = get_colors_from_palette(color_palette_name, len(x)) if color_palette_name else "blue"
        ax.scatter(x, y, s=sizes, c=colors, alpha=0.7)

        if show_data_labels and size_field:
            for xi, yi, row in zip(x, y, rows_for_labels):
                raw_size = row.get(size_field)
                ax.text(xi, yi, f'{raw_size}', fontsize=8, ha='center', va='center')

    # ▶ 축, 제목
    ax.set_xlabel(properties.get("xLabel", x_field))
    ax.set_ylabel(properties.get("yLabel", y_field))
    ax.set_title(properties.get("title", "Scatter Plot Preview"))

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

    plt.tight_layout(rect=[0, 0, 0.85, 1])

def draw_histogram(ax, dict_rows, properties):
    value_field = properties.get("valueField")
    if not value_field:
        raise ValueError("valueField가 필요합니다.")

    bins_input = str(properties.get("bins", "")).strip()
    try:
        bins = int(bins_input)
        if bins <= 0:
            bins = "auto"
    except:
        bins = "auto"

    rwidth = properties.get("rwidth", 0.9)
    try:
        rwidth = float(rwidth)
        if not (0 < rwidth <= 1):
            rwidth = 0.9
    except:
        rwidth = 0.9

    values = []
    for row in dict_rows:
        try:
            values.append(float(row.get(value_field)))
        except:
            continue

    color = get_colors_from_palette(properties.get("colorPalette", "blue"), 1)[0]

    # ▶ 테두리 제거, rwidth 적용
    counts, bins_edges, patches = ax.hist(
        values,
        bins=bins,
        color=color,
        edgecolor=None,
        rwidth=rwidth
    )

    # showDataLabels 옵션
    if properties.get("showDataLabels", False):
        for count, x in zip(counts, bins_edges[:-1]):
            ax.text(x + (bins_edges[1] - bins_edges[0]) / 2, count, f'{int(count)}',
                    ha='center', va='bottom', fontsize=8)

    ax.set_xlabel(properties.get("xLabel", value_field))
    ax.set_ylabel(properties.get("yLabel", "Frequency"))
    ax.set_title(properties.get("title", "Histogram Preview"))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

    plt.tight_layout(rect=[0, 0, 0.85, 1])

def draw_box_plot(ax, dict_rows, properties):
    value_field = properties.get("valueField")
    category_field = properties.get("categoryField")

    if not value_field:
        raise ValueError("valueField가 필요합니다.")

    widths = properties.get("widths", 0.5)
    try:
        widths = float(widths)
    except Exception:
        widths = 0.5

    whis = properties.get("whis", 1.5)
    try:
        whis = float(whis)
    except Exception:
        whis = 1.5
        
    show_fliers = properties.get("showFliers", False)
    notch = properties.get("notch", False)
    show_means = properties.get("showMeans", False)


    if category_field:
        grouped = defaultdict(list)
        for row in dict_rows:
            cat_val = row.get(category_field)
            val = row.get(value_field)
            if cat_val is None or val is None:
                continue
            try:
                val = float(val)
            except:
                continue
            grouped[cat_val].append(val)

        categories = sorted(grouped.keys())
        data = [grouped[cat] for cat in categories]

        if not categories or not data:
            raise ValueError("유효한 카테고리 또는 값 데이터가 없습니다.")

        color_palette_name = properties.get("colorPalette", "tab10")
        colors = get_colors_from_palette(color_palette_name, len(categories))

        box = ax.boxplot(
            data,
            patch_artist=True,
            widths=widths,
            notch=notch,
            showmeans=show_means,
            showfliers=show_fliers,
            whis=whis
        )

        for patch, color in zip(box['boxes'], colors):
            patch.set_facecolor(color)

        # ✅ 중앙값 표기
        # for i, median in enumerate(box['medians']):
        #     x = median.get_xdata().mean()
        #     y = median.get_ydata().mean()
        #     ax.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=8, color='black')

        # ✅ 평균값 표기
        if show_means and 'means' in box:
            for mean in box['means']:
                x = mean.get_xdata().mean()
                y = mean.get_ydata().mean()
                ax.text(x, y, f"{y:.1f}", ha='center', va='top', fontsize=8, color='blue')

        # ✅ 이상치 값 표기
        if show_fliers and 'fliers' in box:
            for flier in box['fliers']:
                for x, y in zip(flier.get_xdata(), flier.get_ydata()):
                    ax.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=7, color='red')

        ax.set_xticklabels(categories)
        ax.set_xlabel(properties.get("xLabel", category_field))
        ax.set_ylabel(properties.get("yLabel", value_field))
        ax.set_title(properties.get("title", "Box Plot Preview"))

        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

    else:
        values = []
        for row in dict_rows:
            try:
                v = float(row.get(value_field))
                values.append(v)
            except:
                continue

        if not values:
            raise ValueError("유효한 값 데이터가 없습니다.")

        box = ax.boxplot(
            values,
            patch_artist=True,
            widths=widths,
            notch=notch,
            showmeans=show_means,
            showfliers=show_fliers,
            whis=whis
        )

        #  중앙값
        # for median in box['medians']:
        #     x = median.get_xdata().mean()
        #     y = median.get_ydata().mean()
        #     ax.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=8, color='black')

        # ✅ 평균값
        if show_means and 'means' in box:
            for mean in box['means']:
                x = mean.get_xdata().mean()
                y = mean.get_ydata().mean()
                ax.text(x, y, f"{y:.1f}", ha='center', va='top', fontsize=8, color='blue')

        # ✅ 이상치
        if show_fliers and 'fliers' in box:
            for flier in box['fliers']:
                for x, y in zip(flier.get_xdata(), flier.get_ydata()):
                    ax.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=7, color='red')

        ax.set_ylabel(properties.get("yLabel", value_field))
        ax.set_title(properties.get("title", "Box Plot Preview"))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

def draw_pareto_chart(ax, dict_rows, properties):
    label_field = properties.get("labelField")
    value_field = properties.get("valueField")

    if not label_field or not value_field:
        raise ValueError("labelField와 valueField가 필요합니다.")

    color_palette_name = properties.get("colorPalette", "tab10")
    show_values = properties.get("showValues", False)

    # 추가 속성
    try:
        bar_width = float(properties.get("barWidth", 0.8))
    except Exception:
        bar_width = 0.8

    line_style = properties.get("lineStyle", "-")

    try:
        line_width = float(properties.get("lineWidth", 1.5))
    except Exception:
        line_width = 1.5

    marker_map = {
        "circle": "o",
        "square": "s",
        "triangle": "^",
        "diamond": "D"
    }
    marker_user = properties.get("marker", "circle")
    marker = marker_map.get(marker_user, "o")
    marker_size = properties.get("markerSize", 6)

    # 데이터 추출 및 정렬 (값 내림차순)
    data = []
    for row in dict_rows:
        try:
            val = float(row.get(value_field))
            label = str(row.get(label_field))
            data.append((label, val))
        except:
            continue

    if not data:
        raise ValueError("유효한 데이터가 없습니다.")

    data.sort(key=lambda x: x[1], reverse=True)
    labels = [d[0] for d in data]
    values = [d[1] for d in data]

    total = sum(values)
    cumulative = [sum(values[:i + 1]) / total * 100 for i in range(len(values))]

    bar_color = get_colors_from_palette(color_palette_name, 1)[0]
    line_color = get_colors_from_palette(color_palette_name, 2)[-1]

    # 막대 그래프
    bars = ax.bar(labels, values, color=bar_color, width=bar_width)

    # 막대 위에 값 표시 (show_values=True일 때만)
    if show_values:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height,
                    f"{height:,.0f}", ha='center', va='bottom', fontsize=9)

    # 누적 비율 라인 차트
    ax2 = ax.twinx()
    ax2.plot(
        labels,
        cumulative,
        color=line_color,
        marker=marker,
        markersize=marker_size,
        linestyle=line_style,
        linewidth=line_width,
        label='누적 비율 (%)'
    )

    # 라인 위에 값 표시 (show_values=True일 때만)
    if show_values:
        for x, y in zip(labels, cumulative):
            ax2.text(x, y, f"{y:.1f}%", ha='center', va='bottom', fontsize=8, color=line_color)

    ax.set_xlabel(properties.get("xLabel", label_field))
    ax.set_ylabel(properties.get("yLabel", value_field))
    ax2.set_ylabel("누적 비율 (%)")

    ax.set_title(properties.get("title", "Pareto Chart Preview"))

    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))
    ax2.yaxis.set_major_formatter(ticker.PercentFormatter())

    ax.tick_params(axis='x', rotation=45)
    ax2.legend(loc='upper right')

chart_draw_functions = {
    "bar": draw_bar_chart,
    "horizontalBar": draw_horizontal_bar_chart,
    "pie": draw_pie_chart,
    "line": draw_line_chart,
    "doughnut": draw_doughnut_chart,
    # "scatter": draw_scatter_plot,
    "hist": draw_histogram,
    "bubble": draw_bubble_chart,
    "box": draw_box_plot,
    "pareto": draw_pareto_chart,
}

def draw_chart(request, supabase, charttypecd, dict_rows, properties, datauid):
    try:
        # supabase = get_supabase_client(
        #     request.session.get("access_token"),
        #     request.session.get("refresh_token")
        # )    # jeff 20251124 1104 

        col_resp = (
            supabase.schema("smartdoc")
            .table("datacols")
            .select("querycolnm, dispcolnm")
            .eq("datauid", datauid)
            .order("orderno")
            .execute()
        )
        col_map_data = col_resp.data or []

        # querycolnm → dispcolnm 매핑 dict
        q2d = {c["querycolnm"]: c["dispcolnm"] for c in col_map_data}
        # dispcolnm → dispcolnm (그대로)
        d2d = {c["dispcolnm"]: c["dispcolnm"] for c in col_map_data}


        # 하나의 통합 매핑
        # (properties에 어떤 값이 와도 dispcolnm으로 변환됨)
        col_map = {**q2d, **d2d}
        
        # ---------------------------------------------
        # ② properties.labelField / valueField 보정
        # ---------------------------------------------
        def normalize_field(fieldname):
            """properties에 온 필드명을 dispcolnm으로 변환 (querycolnm도 허용)"""
            return col_map.get(fieldname, fieldname)  # 못 찾으면 원래 필드 유지

        properties["labelField"] = normalize_field(properties.get("labelField"))
        properties["valueField"] = normalize_field(properties.get("valueField"))
        
        # 폰트 경로 지정 (프로젝트 내 경로)
        font_path = os.path.join(
            os.path.dirname(__file__), '..', 'static', 'fonts', 'NanumGothic-Regular.ttf'
        )
        font_path = os.path.abspath(font_path)

        if os.path.exists(font_path):
            try:
                font_manager.fontManager.addfont(font_path)
                font_name = font_manager.FontProperties(fname=font_path).get_name()
                plt.rcParams['font.family'] = font_name
            except Exception as font_err:
                # 폰트 오류는 그대로 exception 발생시켜 아래 except에서 처리되도록
                raise font_err

        if charttypecd not in chart_draw_functions:
            raise ValueError("지원하지 않는 차트 타입입니다.")
        
        fig, ax = plt.subplots(figsize=(6, 4))
        chart_draw_functions[charttypecd](ax, dict_rows, properties)
        plt.tight_layout()

        return fig

    except Exception as e:
        # --------------------------
        #  오류 로그 저장
        # --------------------------
        try:
            # (request, errormessage, errorobject, creator, remark1, remark2, remark3)
            error_log(request,
                      e, 
                      inspect.currentframe().f_code.co_name, 
                      request.session.get("user", {}).get("id", None),
                      charttypecd,                      #remarks1
                      properties,                       #remarks2
                      "CHART 생성 중 오류",              #remarks3
                    )

        except Exception as log_err:
            # 로그 저장 자체가 실패하면 서버에서 반드시 확인하도록 raise
            raise log_err

        # 원래 오류를 상위로 전달
        raise e