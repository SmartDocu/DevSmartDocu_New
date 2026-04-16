# master_object.py
import json
from dateutil import parser
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render
from urllib.parse import urlparse

from utilsPrj.supabase_client import get_supabase_client

def master_object(request):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    if not user:
        code = 'login'
        text = '로그인이 필요합니다.'
        page = "master_object"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    # user_id = user.get("id")
    docid = user.get("docid")
    # 문서 목록 조회
    # docs = supabase.schema("smartdoc").rpc("fn_docs_filtered__r_user_manager", {'p_useruid': user_id}).execute().data or []
    
    docs_resp = supabase.schema("smartdoc").table("docs").select("*").eq("docid", docid).execute()
    docs = docs_resp.data if docs_resp.data else []

    # 모든 챕터 데이터를 한번에 조회
    all_chapters = {}
    all_objects = {}
    
    for doc in docs:
        # docid = doc["docid"]
        # 각 문서의 챕터들을 조회
        chapters = supabase.schema("smartdoc").table("chapters").select("*").eq("docid", docid).order("chapterno").execute().data or []
        all_chapters[str(docid)] = chapters
        # print("chapters", chapters)
        # 각 챕터의 객체들을 조회
        for chapter in chapters:
            chapteruid = chapter["chapteruid"]
            objects = supabase.schema('smartdoc').rpc("fn_objects__r", {"p_chapteruid": chapteruid}).execute().data or []
            
            # 날짜 포맷팅
            for obj in objects:
                if obj.get('createdts'):
                    try:
                        dt = parser.parse(obj['createdts']) if isinstance(obj['createdts'], str) else obj['createdts']
                        obj['createdts'] = dt.strftime("%y-%m-%d %H:%M")
                    except Exception as e:
                        obj['createdts'] = ''
                
                if obj["objecttypenm"] != "":
                    obj["objecttypenm_full"] = obj["objecttypenm"] + ' (' + obj["gentypecd"] + ')'
                else:
                    obj["objecttypenm_full"] = ""
            
            sorted_objects_data = sorted(objects, key=lambda x: x["orderno"])
            
            all_objects[str(chapteruid)] = sorted_objects_data
        
    # print(all_objects)

    # 선택된 값들
    # selected_docid = docid #request.GET.get('docid') or (str(docs[0]["docid"]) if docs else "")
    selected_chapteruid = request.GET.get('chapteruid') or ""
    selected_objectuid =  request.GET.get("objectuid") or ""

    objecttype_resp = supabase.schema("smartdoc").table("p_objecttypes").select("*").order("orderno").execute()
    objecttype = objecttype_resp.data if objecttype_resp.data else []

    return render(request, 'pages/master_object.html', {
        'user' : user,
        'docs': docs,
        'docid': docid,
        'chapteruid': selected_chapteruid,
        'objectuid': selected_objectuid,
        'all_chapters': json.dumps(all_chapters),  # JSON으로 전달
        'all_objects': json.dumps(all_objects),    # JSON으로 전달
        'objecttype': objecttype,
    })

def master_object_get_chapter (request):
    # print('master_object_get_chapter 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    # docid = request.GET.get('docid')
    user = request.session.get("user")
    docid = user.get("docid")

    try:
        docid_int = int(docid)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("유효한 docid가 필요합니다.")

    chapters_resp = get_chapter(request, docid_int)
    # print(chapters_resp.data)
    return JsonResponse(chapters_resp, safe=False)

def get_chapter(request, docid):
    # print('chapter 호출')
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token) 
    
    chapters_resp = supabase.schema("smartdoc").table("chapters").select("*").eq("docid", docid).order("chapterno").execute().data

    return chapters_resp

def master_object_save_object (request):
    # print('master_object_save_object 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    if not user:
        return render(request, 'pages/home.html')
    
    if not user:
        # return JsonResponse({"result": "Failed", "message": "로그인이 필요합니다. 로그인 부탁드립니다."})
        # return redirect("login")
        code = 'login'
        text = '로그인이 필요합니다.'
        page = "master_chapter_template"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    billingmodelcd = user.get("billingmodelcd")

    if request.method == "POST":
        body = json.loads(request.body)
        chapteruid = body.get("chapteruid")
        objectuid = body.get("objectuid")
        objectdesc = body.get("objectdesc")
        objecttypecd_orig = body.get("objecttypecd_orig")
        objecttypecd = body.get("objecttypecd")
        useyn = body.get("useyn")
        orderno = body.get("orderno")

        transdata = {
            'chapteruid': chapteruid
            ,'objectuid': objectuid or None
            ,'objectdesc': objectdesc
            ,'objecttypecd': objecttypecd
            ,'useyn': useyn
            ,'orderno': orderno
        }
        # print(objecttypecd, ' / ', objecttypecd_orig)
        # 기존 데이터 삭제
        if objecttypecd != objecttypecd_orig:
            del_tables = supabase.schema('smartdoc').table('tables').delete().eq('objectuid', objectuid).execute()
            del_charts = supabase.schema('smartdoc').table('charts').delete().eq('objectuid', objectuid).execute()
            del_sentences = supabase.schema('smartdoc').table('sentences').delete().eq('objectuid', objectuid).execute()
            transdata['objectsettingyn'] = False

        # 기존 사용 여부 체크
        useyn_orig = supabase.schema("smartdoc").table("objects").select("useyn").eq("objectuid", objectuid).execute().data[0]['useyn']
        # print(f'UseYN: {useyn} / UseYN_Orig: {useyn_orig}')
        if useyn != useyn_orig and useyn_orig == False:
            freedoccnt_resp = supabase.schema("smartdoc").table("configs").select("*").execute()
            freeobjectcnt = freedoccnt_resp.data[0]["freeobjectcnt"]

            docid = supabase.schema("smartdoc").table("chapters").select("*").eq("chapteruid", chapteruid).execute().data[0]['docid']
            doc_data = supabase.schema("smartdoc").rpc("fn_doc_count__r", {'p_docid': docid, 'p_chapteruid': None}).execute().data
            if doc_data:
                object_cnt = doc_data[0].get('object_cnt', 0) or 0
            else:
                object_cnt = 0  # 결과가 없으면 0으로 처리
            # print(object_cnt)

            if object_cnt >= freeobjectcnt and billingmodelcd == "Fr":
                    return JsonResponse({'success': False, 'message': f'항목 설정 최대 사용량 {freeobjectcnt}을 초과하였습니다.'}, status=405)

        try:
            supabase.schema('smartdoc').table('objects').upsert(transdata).execute()
            return JsonResponse({"result": "success"})
        except Exception as e:
            print(f'에러 발생?? {e}')
            return JsonResponse({"result": "error", "message": "항목 없음"}, status=404)
    return JsonResponse({"result": "error", "message": "잘못된 요청"}, status=400)

def master_object_delete_object (request):
    # print('master_object_delete_object 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    if request.method == "POST":
        try:
            body = json.loads(request.body)
            objectuid = body.get("objectuid")
            if not objectuid:
                return JsonResponse({"result": "error", "message": "objectuid 누락"}, status=400)

            supabase.schema("smartdoc").table("objects").delete().eq("objectuid", objectuid).execute()
            return JsonResponse({"result": "success"})
        except Exception as e:
            print(f"삭제 실패: {e}")
            return JsonResponse({"result": "error", "message": str(e)}, status=500)

    return JsonResponse({"result": "error", "message": "잘못된 요청"}, status=400)
