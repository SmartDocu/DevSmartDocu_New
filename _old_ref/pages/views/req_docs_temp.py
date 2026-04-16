import io
import json
import re
import requests

from django.http import HttpResponse
from django.shortcuts import render, redirect
# from docx import Document  # 이제 필요 없음
from bs4 import BeautifulSoup
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
import platform
from matplotlib import font_manager, rc
import mammoth

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.query_runner import run_query, apply_column_display_mapping
from utilsPrj.table_utils import draw_table
from utilsPrj.chart_utils import draw_chart



def req_docs_temp(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    docs = supabase.schema("smartdoc").table("docs").select("*").execute().data or []
    selected_docid = request.GET.get("docid") or request.POST.get("docid")
    selected_chapteruid = request.GET.get("chapteruid") or request.POST.get("chapteruid")

    if not selected_docid and docs:
        selected_docid = str(docs[0]["docid"])

    chapters = supabase.schema("smartdoc").table("chapters") \
        .select("chapteruid, chapternm, chaptertemplateurl") \
        .eq("docid", selected_docid).order("chapterno").execute().data or []

    if not selected_chapteruid and chapters:
        selected_chapteruid = str(chapters[0]["chapteruid"])
        query = request.GET.copy()
        query["chapteruid"] = selected_chapteruid
        return redirect(f"{request.path}?{query.urlencode()}")

    tables = []
    typed_objects = []
    word_html = ""

    if selected_chapteruid:
        tables = supabase.schema("smartdoc").table("chapters") \
            .select("*").eq("chapteruid", selected_chapteruid).order("tablenm").execute().data or []

        chapter = next((c for c in chapters if c["chapteruid"] == selected_chapteruid), None)
        chaptertemplateurl = chapter.get("chaptertemplateurl", "") if chapter else ""

        if chaptertemplateurl:
            resp = requests.get(chaptertemplateurl)
            if resp.status_code == 200:
                try:
                    with io.BytesIO(resp.content) as docx_file:
                        result = mammoth.convert_to_html(docx_file)
                        word_html = result.value

                        objects = re.findall(r"#(.*?)#", word_html)

                        all_tables = supabase.schema("smartdoc").table("chapters") \
                            .select("tablenm, tableuid, datauid") \
                            .eq("chapteruid", selected_chapteruid).execute().data or []

                        all_charts = supabase.schema("smartdoc").table("charts") \
                            .select("chartnm, chartuid, datauid") \
                            .eq("chapteruid", selected_chapteruid).execute().data or []

                        for obj in objects:
                            obj_trim = obj.strip().lower()

                            matched_table = next((t for t in all_tables if t["tablenm"].strip().lower() == obj_trim), None)
                            if matched_table:
                                datauid = matched_table.get("datauid")
                                datanm = ""
                                if datauid:
                                    data_row = supabase.schema("smartdoc").table("datas") \
                                        .select("datanm").eq("datauid", datauid).single().execute().data
                                    datanm = data_row.get("datanm", "") if data_row else ""

                                typed_objects.append({
                                    "name": obj,
                                    "type": "Table",
                                    "tableuid": matched_table.get("tableuid"),
                                    "datauid": datauid,
                                    "datanm": datanm,
                                })
                                continue

                            matched_chart = next((c for c in all_charts if c["chartnm"].strip().lower() == obj_trim), None)
                            if matched_chart:
                                datauid = matched_chart.get("datauid")
                                datanm = ""
                                if datauid:
                                    data_row = supabase.schema("smartdoc").table("datas") \
                                        .select("datanm").eq("datauid", datauid).single().execute().data
                                    datanm = data_row.get("datanm", "") if data_row else ""

                                typed_objects.append({
                                    "name": obj,
                                    "type": "Chart",
                                    "chartuid": matched_chart.get("chartuid"),
                                    "datauid": datauid,
                                    "datanm": datanm,
                                })
                                continue

                except Exception:
                    word_html = "<p>변환 중 오류 발생</p>"
            else:
                word_html = "<p>첨부 문서를 불러올 수 없습니다.</p>"

    # POST 요청 처리
    if request.method == "POST":
        action = request.POST.get("action")
        updated_html = word_html

        for obj in typed_objects:
            if obj["type"] == "Table":
                tableuid = obj.get("tableuid")
                docid = selected_docid

                table_rec = supabase.schema("smartdoc").table("chapters") \
                    .select("datauid, tablejson, coljson") \
                    .eq("tableuid", tableuid).single().execute()

                if not table_rec.data:
                    continue

                datauid = table_rec.data.get("datauid")
                tablejson_str = table_rec.data.get("tablejson") or "{}"
                coljson_str = table_rec.data.get("coljson") or "{}"

                try:
                    tablejson = json.loads(tablejson_str)
                    coljson = json.loads(coljson_str)
                except json.JSONDecodeError:
                    continue

                data_rec = supabase.schema("smartdoc").table("datas") \
                    .select("query, connectid, connecttype") \
                    .eq("datauid", datauid).single().execute()

                if not data_rec.data:
                    continue

                query = data_rec.data.get("query", "")
                connectid = data_rec.data.get("connectid", "")
                connecttype = data_rec.data.get("connecttype", "")

                params = re.findall(r'@(\w+)', query)
                for param in params:
                    param_rec = supabase.schema("smartdoc").table("dataparams") \
                        .select("samplevalue") \
                        .eq("docid", docid).eq("paramnm", param).single().execute()
                    value = param_rec.data.get("samplevalue") if param_rec.data else ""
                    query = re.sub(f"@{param}\\b", str(value), query)

                raw_result = run_query(connecttype, query, connectid)
                raw_columns = raw_result.get("columns", [])
                raw_rows = raw_result.get("rows", [])
                columns, dict_rows = apply_column_display_mapping(datauid, raw_columns, raw_rows, supabase)

                html = draw_table(request, columns, dict_rows, tablejson, coljson)

                placeholder = f"#{obj['name']}#"
                updated_html = updated_html.replace(placeholder, html)

            if obj["type"] == "Chart":
                chartuid = obj.get("chartuid")
                docid = selected_docid

                # 플랫폼별 폰트 설정
                if platform.system() == 'Windows':
                    font_path = "C:/Windows/Fonts/malgun.ttf"
                elif platform.system() == 'Darwin':  # macOS
                    font_path = "/System/Library/Fonts/AppleGothic.ttf"
                else:  # Linux 등
                    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

                try:
                    font_name = font_manager.FontProperties(fname=font_path).get_name()
                    rc('font', family=font_name)
                except Exception:
                    pass  # 폰트 설정 실패해도 무시

                chart_rec = supabase.schema("smartdoc").table("charts") \
                    .select("datauid, chartjson, charttypecd") \
                    .eq("chartuid", chartuid).single().execute()

                if not chart_rec.data:
                    continue
                
                datauid = chart_rec.data.get("datauid")
                charttypecd = chart_rec.data.get("charttypecd")
                chartjson_str = chart_rec.data.get("chartjson") or "{}"

                try:
                    chartjson = json.loads(chartjson_str)
                except json.JSONDecodeError:
                    continue

                data_rec = supabase.schema("smartdoc").table("datas") \
                    .select("query, connectid, connecttype") \
                    .eq("datauid", datauid).single().execute()

                if not data_rec.data:
                    continue

                query = data_rec.data.get("query", "")
                connectid = data_rec.data.get("connectid", "")
                connecttype = data_rec.data.get("connecttype", "")

                params = re.findall(r'@(\w+)', query)
                for param in params:
                    param_rec = supabase.schema("smartdoc").table("dataparams") \
                        .select("samplevalue") \
                        .eq("docid", docid).eq("paramnm", param).single().execute()
                    value = param_rec.data.get("samplevalue") if param_rec.data else ""
                    query = re.sub(f"@{param}\\b", str(value), query)

                raw_result = run_query(connecttype, query, connectid)
                raw_columns = raw_result.get("columns", [])
                raw_rows = raw_result.get("rows", [])
                columns, dict_rows = apply_column_display_mapping(datauid, raw_columns, raw_rows, supabase)

                # draw_chart 함수로 그래프 생성
                # fig = draw_chart(charttypecd, dict_rows, chartjson)
                fig = draw_chart(request, supabase, charttypecd, dict_rows, chartjson)    # jeff 20251124 1104 추가

                buf = io.BytesIO()
                fig.tight_layout()
                fig.savefig(buf, format="png")
                plt.close(fig)
                buf.seek(0)

                img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                img_html = f'<img src="data:image/png;base64,{img_base64}" alt="{obj["name"]} 차트">'

                placeholder = f"#{obj['name']}#"
                updated_html = updated_html.replace(placeholder, img_html)

        word_html = updated_html

        if action == "download":
            full_html = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    /* 필요한 표 스타일, 기본 텍스트 스타일 추가 가능 */
                    body {{ font-family: Arial, sans-serif; }}
                    table {{ border-collapse: collapse; }}
                    table, th, td {{ border: 1px solid black; }}
                    th, td {{ padding: 5px; }}
                </style>
            </head>
            <body>
                {updated_html}
            </body>
            </html>
            """

            response = HttpResponse(full_html, content_type='application/msword')
            response['Content-Disposition'] = 'attachment; filename="document.doc"'
            return response


    return render(request, 'pages/req_docs_temp.html', {
        'docs': docs,
        'docid': selected_docid,
        'chapters': chapters,
        'chapteruid': selected_chapteruid,
        'tables': tables,
        'objects': typed_objects,
        'word_html': word_html,
    })
