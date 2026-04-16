import io
import re
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
import platform
import matplotlib.colors as mcolors
from matplotlib import font_manager, rc

from datetime import datetime
# datetime.now().isoformat()

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.process_data import apply_column_display_mapping
from utilsPrj.process_data import process_data
from utilsPrj.chart_utils import draw_chart
from utilsPrj.chart_definitions import get_chart_types_detail


def master_charts(request):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    # selected_docid = request.GET.get("docid")
    selected_chapteruid = request.GET.get("chapteruid")
    selected_objectnm =  request.GET.get("objectnm")
    selected_datauid = request.GET.get("datauid")

    chart_types_detail = get_chart_types_detail()
    
    # 대신 아래 코드 추가
    chart_types = [{"code": c["code"], "name": c["name"]} for c in chart_types_detail]

    user = request.session.get("user")
    selected_docid = user.get("docid")
    if not user:
        # return JsonResponse({"result": "Failed", "message": "로그인이 필요합니다. 로그인 부탁드립니다."})
        # return redirect("login")
        code = 'login'
        text = '로그인이 필요합니다.'
        page = "master_object"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    
    # 문서 목록
    # docs = supabase.schema("smartdoc").rpc("fn_docs_filtered__r_user_manager", {'p_useruid': user_id}).execute().data or []

    # if not selected_docid and docs:
    #     selected_docid = str(docs[0]["docid"])

    # 챕터 목록
    chapter_resp  = supabase.schema("smartdoc").table("chapters") \
        .select("chapternm") \
        .eq("chapteruid", selected_chapteruid) \
        .execute()
    chapter_data = chapter_resp.data or []

    # selected_docid와 같은 docid인 챕터만 필터링
    # filtered_chapters = [ch for ch in chapters if str(ch['docid']) == str(selected_docid)]

    # selected_chapteruid가 없거나 filtered_chapters 안에 존재하지 않는다면
    # if not selected_chapteruid or not any(str(ch['chapteruid']) == str(selected_chapteruid) for ch in filtered_chapters):
    #     if filtered_chapters:
    #         selected_chapteruid = str(filtered_chapters[0]['chapteruid'])
    #         query = request.GET.copy()
    #         query['chapteruid'] = selected_chapteruid
    #         return redirect(f"{request.path}?{query.urlencode()}")

    selected_chapternm = chapter_data[0]["chapternm"] if chapter_data else ""
    
    # 항목 목록
    objects = supabase.schema("smartdoc").table("objects") \
        .select("chapteruid, objectuid, objectnm") \
        .eq("objecttypecd", "CU").eq("chapteruid", selected_chapteruid).order("objectnm").execute().data or []

    selected_objectuid = None
    for obj in objects:
        if obj["objectnm"] == selected_objectnm:
            selected_objectuid = obj["objectuid"]
            break

    # 데이터 목록
    docs = supabase.schema("smartdoc").table("docs") \
        .select("*") .eq("docid", selected_docid).execute().data or []

    if docs:
        projectid = str(docs[0]["projectid"])

    if selected_docid:
        all_datas = supabase.schema("smartdoc").table("datas") \
            .select("datauid, datanm") \
            .eq("projectid", projectid) \
            .order("datanm").execute().data or []
    else:
        all_datas = []

    # 테이블 정보 조회
    # chart_list = supabase.schema("smartdoc").table("charts") \
    #     .select("datauid, displaytype, chartjson, chart_width, chart_height") \
    #     .eq("chapteruid", selected_chapteruid) \
    #     .eq("objectnm", selected_objectnm) \
    #     .execute().data or []
    
    # 차트 정보 조회 - chapteruid와 objectnm가 모두 유효할 때만 조회
    if selected_chapteruid and selected_objectnm:
        query = supabase.schema("smartdoc").table("charts") \
            .select("datauid, displaytype, chartjson, chart_width, chart_height") \
            .eq("chapteruid", selected_chapteruid) \
            .eq("objectnm", selected_objectnm)
        chart_list = query.execute().data or []
    else:
        chart_list = []


    selected_datauid = request.GET.get("datauid")
    selected_chart_type = request.GET.get("chart_type")
    db_datauid = None
    db_chart_type = None
    chart_width_default = 500  # fallback 기본값
    chart_height_default = 250

    if selected_datauid == "None":
        selected_datauid = None
        
    if chart_list:
        chart_data = chart_list[0]  # 첫 번째 차트만 사용한다면
        db_datauid = chart_list[0].get("datauid")
        db_chart_type = chart_list[0].get("displaytype")

        if not selected_datauid:
            selected_datauid = db_datauid
        if not selected_chart_type:
            selected_chart_type = db_chart_type

        # 👉 chart_width / chart_height 설정
        chart_width_default = chart_data.get("chart_width") or chart_width_default
        chart_height_default = chart_data.get("chart_height") or chart_height_default
        
    # ▶️ datacols 조회
    datacols = []
    if selected_datauid:
        datacols = supabase.schema("smartdoc").table("datacols") \
            .select("querycolnm, dispcolnm, datatypecd, measureyn") \
            .eq("datauid", selected_datauid).order("orderno").execute().data or []

    def get_select_options(field_filter=None):
        if not field_filter:
            return datacols
        elif field_filter == 'category':
            return [col for col in datacols if not col.get("measureyn")]
        elif field_filter == 'numeric':
            return [col for col in datacols if col.get("measureyn")]
        return []
    
    # ▶️ 미리보기 관련 처리
    value_settings = []
    chart_config = {}

    # 저장된 설정 불러오기 조건
    if selected_chart_type == db_chart_type and selected_datauid == db_datauid:
        try:
            chart_config = json.loads(chart_list[0].get("chartjson", "{}"))
        except Exception:
            chart_config = {}
    else:
        chart_config = {}
    
    # 해당 chart_type 의 속성 가져오기
    for chart_type in chart_types_detail:
        if chart_type["code"] == selected_chart_type:
            value_settings = chart_type["properties"]

            # 여기서 selectbox 필드에 options 주입
            for field in value_settings:
                if field["type"] == "select":

                    if field["key"] == "colorPalette":
                        colormap_data = supabase.schema("smartdoc").table("p_colormaps") \
                            .select("colormapcd, colormapnm, mapgrpnm, mapgrporderno, orderno") \
                            .eq("useyn", True) \
                            .order("mapgrporderno") \
                            .order("orderno") \
                            .execute().data or []

                        grouped_options = {}
                        for row in colormap_data:
                            group = row["mapgrpnm"]
                            if group not in grouped_options:
                                grouped_options[group] = []

                            # gradient 생성
                            try:
                                cmap = plt.get_cmap(row["colormapcd"])
                                colors = [mcolors.to_hex(cmap(i / 4)) for i in range(5)]
                                gradient = ", ".join(colors)
                            except Exception:
                                gradient = None

                            grouped_options[group].append({
                                "value": row["colormapcd"],
                                "label": row["colormapnm"] or row["colormapcd"],
                                "preview_gradient": gradient
                            })

                        field["options"] = [
                            {"group": group, "children": options}
                            for group, options in grouped_options.items()
                        ]


                    else:
                        # 이미 options가 명시된 경우 (예: marker, lineStyle) 그대로 사용
                        if "options" in field and field["options"]:
                            continue  # 수정 없이 유지
                        else:
                            # options 없으면 get_select_options 호출
                            if field.get("fieldFilter") == "category":
                                options = get_select_options("category")
                            elif field.get("fieldFilter") == "numeric":
                                options = get_select_options("numeric")
                            else:
                                options = get_select_options(None)  # 전체 목록 반환
                            
                            field["options"] = [
                                {
                                    "value": col["dispcolnm"] or col["querycolnm"],
                                    "label": col["dispcolnm"] or col["querycolnm"]
                                }
                                for col in options
                            ]
                    
                    # field["options"].sort(key=lambda opt: opt["label"])

            break

    return render(request, 'pages/master_charts.html', {
        'user' : user,
        # 'docs': docs,
        'selected_docid': selected_docid,
        # 'chapters': chapters,
        'selected_chapteruid': selected_chapteruid,
        'selected_chapternm' : selected_chapternm,
        # 'objects': objects,
        'selected_objectnm': selected_objectnm,
        'selected_objectuid': selected_objectuid,
        'all_datas': all_datas,
        'selected_datauid': selected_datauid,
        'selected_chart_type': selected_chart_type,
        'chart_types': chart_types,   

        # 'chart_types_detail' : chart_types_detail,

        'value_settings': value_settings,
        'chart_config': chart_config,

        'chart_width_default': chart_width_default,
        'chart_height_default': chart_height_default,
    })




def master_charts_save(request):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        objectuid = request.POST.get("objectuid")
        chapteruid = request.POST.get("chapteruid")
        objectnm = request.POST.get("objectnm")
        datauid = request.POST.get("datauid")
        displaytype = request.POST.get("displaytype")
        chartjson = request.POST.get("chartjson", "{}")
        chart_width = request.POST.get("chart_width")
        chart_height = request.POST.get("chart_height")
        now = datetime.now().isoformat()
        gentypecd = "UI"

        user = request.session.get("user")
        user_id = user.get("id") if user else "unknown"

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        existing = supabase.schema("smartdoc").table("charts") \
            .select("datauid") \
            .eq("chapteruid", chapteruid) \
            .eq("objectnm", objectnm) \
            .execute().data
        

        if existing:
            supabase.schema("smartdoc").table("charts").update({
                "chapteruid": chapteruid,
                "objectuid": objectuid,
                "objectnm": objectnm,
                "datauid": datauid,
                "displaytype": displaytype,
                "chartjson": chartjson,
                "creator": user_id,
                "chart_width": chart_width,       # ← 추가
                "chart_height": chart_height      # ← 추가
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
            supabase.schema("smartdoc").table("objects").update({
                "modifier": user_id,
                "modifydts": now
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
        else:
            # new_uid = str(uuid.uuid4())
            supabase.schema("smartdoc").table("charts").insert({
                # "chartuid": new_uid,
                "chapteruid": chapteruid,
                "objectuid": objectuid,
                "objectnm": objectnm,
                "datauid": datauid,
                "displaytype": displaytype,
                "chartjson": chartjson,
                "creator": user_id,
                "gentypecd" : gentypecd,
                "chart_width": chart_width,       # ← 추가
                "chart_height": chart_height      # ← 추가
            }).execute()

            # 신규 저장 시 objectsettingyn true로 업데이트
            supabase.schema("smartdoc").table("objects").update({
                "objectsettingyn": True,
                "modifydts": datetime.now().isoformat(),
                "modifier": user_id
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


def master_charts_delete(request):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        data = json.loads(request.body)
        chapteruid = data.get("chapteruid")
        objectnm = data.get("objectnm")

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        resp = supabase.schema("smartdoc").table("charts") \
            .delete() \
            .eq("chapteruid", chapteruid) \
            .eq("objectnm", objectnm) \
            .execute()

        # 신규 저장 시 objectsettingyn true로 업데이트
        supabase.schema("smartdoc").table("objects").update({
            "objectsettingyn": False
        }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
        
        # 삭제된 행이 없으면 실패로 처리
        if resp.count == 0:
            return JsonResponse({"success": False, "error": "삭제할 데이터가 없습니다."}, status=404)

        # 삭제 성공 시
        return JsonResponse({"success": True})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def master_chart_preview_png(request):
    if request.method != 'POST':
        return JsonResponse({"error": "POST 요청만 지원"}, status=405)

    # 플랫폼별 폰트 설정
    # if platform.system() == 'Windows':
    #     font_path = "C:/Windows/Fonts/malgun.ttf"
    # elif platform.system() == 'Darwin':  # macOS
    #     font_path = "/System/Library/Fonts/AppleGothic.ttf"
    # else:  # Linux 등
    #     font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

    # try:
    #     font_name = font_manager.FontProperties(fname=font_path).get_name()
    #     rc('font', family=font_name)
    # except Exception:
    #     pass  # 폰트 설정 실패해도 무시

    # POST 데이터에서 필요한 값 추출
    # 예를 들어 JSON payload로 { "selected_datauid": "...", "selected_chart_type": "...", "properties": {...} } 형태라고 가정
    try:
        payload = json.loads(request.body)
    except Exception as e:
        return JsonResponse({"error": "잘못된 JSON 형식"}, status=400)

    selected_datauid = payload.get("selected_datauid")
    selected_chart_type = payload.get("selected_chart_type")
    properties = payload.get("properties", {})

    user = request.session.get("user")
    selected_docid = user.get("docid")

    if not selected_datauid or not selected_chart_type:
        return JsonResponse({"error": "필수 값 누락"}, status=400)

    # supabase 클라이언트 가져오기 (토큰이 필요하면 헤더 등에서 받아 처리 필요)
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    # 3) 쿼리 실행
    df = process_data(request, datauid = selected_datauid, docid = selected_docid)
    raw_columns = df.columns.tolist()
    raw_rows = df.values.tolist()
    print("df", df)
    # 4) 컬럼 매핑
    columns, dict_rows = apply_column_display_mapping(selected_datauid, raw_columns, raw_rows, supabase)

    # 5) 차트 생성
    try:
        fig = draw_chart(request, supabase, selected_chart_type, dict_rows, properties, selected_datauid)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"차트 생성 중 오류가 발생했습니다: {e}"}, status=500)


    # # 이미지 크기 조정 (가로 10인치, 세로 6인치 예시)
    # fig.set_size_inches(5, 2.5)
    try:
        chart_width = float(properties.get("chart_width") or chart_width or 500)
        chart_height = float(properties.get("chart_height") or chart_height or 250)
        dpi = 96
        fig.set_size_inches(chart_width / dpi, chart_height / dpi)
    except Exception:
        fig.set_size_inches(5, 2.5)
                     
    # 6) 이미지 변환 및 반환
    buf = io.BytesIO()
    fig.tight_layout()
    # fig.savefig(buf, format="png")
    fig.savefig(buf, format="png", dpi=96)
    plt.close(fig)
    buf.seek(0)

    return HttpResponse(buf.getvalue(), content_type="image/png")
