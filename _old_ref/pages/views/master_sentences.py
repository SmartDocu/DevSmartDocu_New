from django.shortcuts import render, redirect
from django.http import JsonResponse
import json
from datetime import datetime
# datetime.now().isoformat()

from utilsPrj.sentences_utils import draw_sentences
from utilsPrj.process_data import apply_column_display_mapping
from utilsPrj.process_data import process_data
from utilsPrj.supabase_client import get_supabase_client

def master_sentences(request):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
      # GET 파라미터
    selected_chapteruid = request.GET.get("chapteruid")
    selected_objectnm =  request.GET.get("objectnm")
    selected_datauid = request.GET.get("datauid")
    

    template_text = ""
    converted_result = ""
    dict_rows = []

    user = request.session.get("user")
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
    selected_docid = user.get("docid")

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
        .eq("objecttypecd", "SU").eq("chapteruid", selected_chapteruid).order("objectnm").execute().data or []

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

    # 문장 정보 (템플릿, 연결된 datauid)
    # sentences_list = supabase.schema("smartdoc").table("sentences") \
    #     .select("datauid, sentencestext") \
    #     .eq("chapteruid", selected_chapteruid) \
    #     .eq("objectnm", selected_objectnm) \
    #     .execute().data or []

    # 문장 정보 (템플릿, 연결된 datauid)
    if selected_chapteruid and selected_objectnm:
        sentences_list = supabase.schema("smartdoc").table("sentences") \
            .select("datauid, sentencestext") \
            .eq("chapteruid", selected_chapteruid) \
            .eq("objectnm", selected_objectnm) \
            .execute().data or []
    else:
        sentences_list = []


    db_datauid = None
    if sentences_list:
        db_datauid = sentences_list[0].get("datauid")
        if not selected_datauid:
            selected_datauid = db_datauid

    # 데이터 실행
    if selected_datauid:
        # 쿼리 실행 및 컬럼 매핑
        df = process_data(request, datauid = selected_datauid, docid = selected_docid)
        # raw_columns = df.columns.tolist()
        # raw_rows = df.values.tolist()
        raw_columns = df.columns.tolist()
        raw_rows = df.head(15).values.tolist()

        columns, dict_rows = apply_column_display_mapping(
            selected_datauid, raw_columns, raw_rows, supabase
        )

    # POST 요청 처리
    if request.method == "POST":
        template_text = request.POST.get("template_text", "")

        converted_result = draw_sentences(request, supabase, dict_rows, template_text, selected_datauid)    # jeff 20251124 1104 supabase 추가

    # GET 요청이면서, DB에 템플릿이 있을 경우 자동 변환
    elif request.method == "GET" and db_datauid and selected_datauid and db_datauid == selected_datauid:
        template_text = sentences_list[0].get("sentencestext", "")
        if template_text and dict_rows:
            converted_result = draw_sentences(request, supabase, dict_rows, template_text, selected_datauid)

    return render(request, 'pages/master_sentences.html', {
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
        'dict_rows': dict_rows,
        # 'dict_rows_json': json.dumps(dict_rows, ensure_ascii=False, default=str),
        'template_text': template_text,
        'converted_result': converted_result,
    })



def master_sentences_save(request):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        data = json.loads(request.body)  # JSON body를 dict로 변환
        objectuid = data.get("objectuid")
        chapteruid = data.get("chapteruid")
        objectnm = data.get("objectnm")
        datauid = data.get("datauid")
        sentencestext = data.get("sentencestext", ) 
        now = datetime.now().isoformat()

        user = request.session.get("user")
        user_id = user.get("id") if user else "unknown"
        gentypecd = "UI"

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        # 기존 데이터 있는지 확인
        existing = supabase.schema("smartdoc").table("sentences") \
            .select("datauid") \
            .eq("chapteruid", chapteruid) \
            .eq("objectnm", objectnm) \
            .execute().data

        if existing:
            # UPDATE
            supabase.schema("smartdoc").table("sentences").update({
                "objectuid": objectuid,
                "datauid": datauid,
                "sentencestext": sentencestext,
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
            supabase.schema("smartdoc").table("objects").update({
                "modifier": user_id,
                "modifydts": now
            }).eq("chapteruid", chapteruid).eq("objectnm", objectnm).execute()
        else:
            # INSERT
            supabase.schema("smartdoc").table("sentences").insert({
                "objectuid": objectuid,
                "chapteruid": chapteruid,
                "objectnm": objectnm,
                "datauid": datauid,
                "sentencestext": sentencestext,
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

def master_sentences_delete(request):
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

        resp = supabase.schema("smartdoc").table("sentences") \
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
