import json
import re

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.http import HttpResponse

from datetime import datetime
# datetime.now().isoformat()

from utilsPrj.table_utils import draw_table
from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.process_data import apply_column_display_mapping
from utilsPrj.process_data import process_data

def master_tables(request):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    # selected_docid = request.GET.get("docid")
    selected_chapteruid = request.GET.get("chapteruid")
    selected_objectnm =  request.GET.get("objectnm")
    selected_datauid = request.GET.get("datauid")
    
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
    
    # 챕터 목록
    chapter_resp  = supabase.schema("smartdoc").table("chapters") \
        .select("chapternm") \
        .eq("chapteruid", selected_chapteruid) \
        .execute()
    chapter_data = chapter_resp.data or []

    selected_chapternm = chapter_data[0]["chapternm"] if chapter_data else ""

    # 항목 목록
    objects = supabase.schema("smartdoc").table("objects") \
        .select("chapteruid, objectuid, objectnm") \
        .eq("objecttypecd", "TU").eq("chapteruid", selected_chapteruid).order("objectnm").execute().data or []

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
        
    if selected_chapteruid and selected_objectnm:
        query = supabase.schema("smartdoc").table("tables").select("datauid, tablejson, coljson")
        query = query.eq("chapteruid", selected_chapteruid)
        query = query.eq("objectnm", selected_objectnm)
        table_list = query.execute().data or []
    else:
        table_list = []
        
    selected_datauid = request.GET.get("datauid")
    db_datauid = None
    
    if table_list:
        db_datauid = table_list[0].get("datauid")
        if not selected_datauid:
            selected_datauid = db_datauid
            
    db_datauid = table_list[0]["datauid"] if table_list else None
    tablejson = {}
    coljson = {}

    # datacols 정보
    datacols = []
    if selected_datauid:
        datacols = supabase.schema("smartdoc").table("datacols") \
            .select("querycolnm, dispcolnm, datatypecd, measureyn") \
            .eq("datauid", selected_datauid).order("orderno").execute().data or []

    # 조건 분기
    if not selected_datauid:
        return render(request, 'pages/master_tables.html', {
            'user' : user,
            # 'docs': docs,
            'selected_docid': selected_docid,
            # 'chapters': chapters,
            'selected_chapteruid': selected_chapteruid,
            'selected_chapternm' : selected_chapternm,
            # 'objects': objects,
            'selected_objectuid' : selected_objectuid,
            'selected_objectnm': selected_objectnm,
            'all_datas': all_datas,
            'selected_datauid': selected_datauid,
        })           

    # 기본값 정의 함수
    def get_default_col(col):
        align = "right" if col["datatypecd"] == "I" else "left"
        base = {
            "bgcolor": "#ffffff",
            "align": align,
            "color": "#000000",
            "fontweight": "normal",
            "fontsize": 14,
        }
        if col.get("measureyn") in ["y", True, "true", "Y", "True"]:
            base["unityn"] = "y"
            base["decimal"] = 0
            base["measureyn"] = "y"
        return base
    
    def get_display_name(col):
        return col["dispcolnm"] or col["querycolnm"]

    if db_datauid is None:
        # 조건 2: db_datauid 없음 → 기본값 설정
        tablejson = {
            "row_bgcolor": "#ffffff",
            "row_align": "center",
            "row_color": "#000000",
            "row_fontweight": "bold",
            "row_fontsize": "20"
        }
        coljson = {}
        for col in datacols:
            coljson[get_display_name(col)] = get_default_col(col)

    elif selected_datauid != db_datauid:
        # 조건 3: selected ≠ db_datauid → 기본값 (datacols 기준)
        try:
            tablejson = json.loads(table_list[0]["tablejson"] or "{}")
        except:
            tablejson = {}
        coljson = {}
        for col in datacols:
            coljson[get_display_name(col)] = get_default_col(col)

    else:
        # 조건 4: 둘 다 있는 경우 → 파싱해서 보여주기
        try:
            tablejson = json.loads(table_list[0]["tablejson"] or "{}")
        except:
            tablejson = {}
        try:
            coljson = json.loads(table_list[0]["coljson"] or "{}")
        except:
            coljson = {}

    updated_html = ""  # 기본값
    result_html = ""
    
    if request.method == "POST" and request.POST.get("action") == "preview":
        try:
            tablejson = json.loads(request.POST.get("tablejson") or "{}")
            coljson = json.loads(request.POST.get("coljson") or "{}")

            df = process_data(request, datauid = selected_datauid, docid = selected_docid)
            raw_columns = df.columns.tolist()
            raw_rows = df.head(15).values.tolist()

            # 컬럼 매핑
            columns, dict_rows = apply_column_display_mapping(selected_datauid, raw_columns, raw_rows, supabase)

            # draw_table 실행
            result_html = draw_table(request, columns, dict_rows, tablejson, coljson)

            html = (
                "<html><head><meta charset='utf-8'></head><body>"
                + result_html
                + "</body></html>"
            )
    
            updated_html = html
            return JsonResponse({"preview_html": updated_html})
        except Exception as e:
            updated_html = f"<p>오류 발생</p>"

    for col in datacols:
        colname = col['dispcolnm'] if col['dispcolnm'] else col['querycolnm']
        order = coljson.get(colname, {}).get('order', 9999)  # order 없으면 큰값 부여
        col['order'] = order
        
    # order 기준 오름차순 정렬
    datacols_sorted = sorted(datacols, key=lambda x: x['order'])
    
    return render(request, 'pages/master_tables.html', {
        'user' : user,
        # 'docs': docs,
        'selected_docid': selected_docid,
        # 'chapters': chapters,
        'selected_chapteruid': selected_chapteruid,
        'selected_chapternm' : selected_chapternm,
        # 'objects': objects,
        'selected_objectuid' : selected_objectuid,
        'selected_objectnm': selected_objectnm,
        'all_datas': all_datas,
        'selected_datauid': selected_datauid,
        'tablejson': tablejson,
        'coljson': coljson,
        'datacols': datacols_sorted,
        'preview_html': updated_html,
        'show_preview': True if updated_html else False,
    })


def master_tables_save(request):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        data = json.loads(request.body)  # JSON body를 dict로 변환
        objectuid = data.get("objectuid")
        chapteruid = data.get("chapteruid")
        objectnm = data.get("objectnm")
        datauid = data.get("datauid")
        tablejson = data.get("tablejson", {})  # 여기 수정
        coljson = data.get("coljson", {})      # 여기 수정
        user = request.session.get("user")
        user_id = user.get("id") if user else "unknown"
        gentypecd = "UI"
        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )
        now = datetime.now().isoformat()

        # 기존 데이터 있는지 확인
        existing = supabase.schema("smartdoc").table("tables") \
            .select("datauid") \
            .eq("chapteruid", chapteruid) \
            .eq("objectnm", objectnm) \
            .execute().data

        if existing:
            # UPDATE
            supabase.schema("smartdoc").table("tables").update({
                "objectuid": objectuid,
                "datauid": datauid,
                "tablejson": tablejson,
                "coljson": coljson,  # 여기에 저장!
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
            supabase.schema("smartdoc").table("objects").update({
                "modifier": user_id,
                "modifydts": now
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
        else:
            # INSERT
            supabase.schema("smartdoc").table("tables").insert({
                "objectuid": objectuid,
                "chapteruid": chapteruid,
                "objectnm": objectnm,
                "datauid": datauid,
                "tablejson": tablejson,
                "coljson": coljson,  # 여기에 저장!
                "creator": user_id,
                "gentypecd" : gentypecd
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

def master_tables_delete(request):
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

        resp = supabase.schema("smartdoc").table("tables") \
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
