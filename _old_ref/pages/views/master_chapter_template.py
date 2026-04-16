import json, uuid
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt

from utilsPrj.supabase_client import get_supabase_client


def master_chapter_template(request):
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

    docid = request.GET.get('docid')
    chapteruid = request.GET.get('chapteruid')

    # print('master_chapter_template 페이지 로딩 중..')

    #### docid 기준 파일 로딩
    chapter_data = Read_Chapter(request, chapteruid)

    texttemplate = chapter_data.data[0]['texttemplate']
    # print(texttemplate)
    template = texttemplate

    objects = Read_Objects(request, chapteruid)
    objects_data = objects.data
    sorted_objects_data = sorted(objects_data, key=lambda x: x['orderno'])

    # print(sorted_objects_data)
    editbuttonyn = request.session.get("user", {}).get("editbuttonyn")

    # print(sorted_objects_data)

    # 전달할 데이터 묶기
    initial_data = {
        "html_content": template,
        "Objects": sorted_objects_data,
        "docid": str(docid),
        "ChapterUID": chapteruid,
        "ChapterNm": chapter_data.data[0]['chapternm'],
        "editbuttonyn": editbuttonyn
        # ,"DocID": chapter_data.data[0]['docid']
    }

    # print('master_chapter_template 페이지 로딩 완료..')
    return render(request, 'pages/master_chapter_template.html', {"initial_data": mark_safe(json.dumps(initial_data)), "ChapterNm": chapter_data.data[0]['chapternm'], "editbuttonyn": editbuttonyn})

def Read_Chapter (request, chapteruid):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    try:
        response = supabase.schema("smartdoc").table("chapters") \
                            .select("*") \
                            .eq("chapteruid", chapteruid) \
                            .execute()
        
        return response
    except Exception as e:
        print(f'Error Message: {e}')
        return [];

def Read_Objects (request, chapteruid):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    try:
        response = supabase.schema("smartdoc").table("objects") \
                            .select("*") \
                            .eq("chapteruid", chapteruid) \
                            .execute()
        
        return response
    except Exception as e:
        return None

@csrf_exempt
def save_chapter_objects (request):  
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
    # supabase.auth.set_session(access_token, refresh_token)
    
    request.supabase = supabase

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            html_content = data.get('html_content', '')
            chapteruid = data.get('ChapterUID', '')
            chapternm = data.get('ChapterNm', '')
            formats = data.get('formats', '')

            user = request.session.get("user")
            user_id = user.get("id")
            billingmodelcd = user.get("billingmodelcd")

            # print(html_content)

            pagebreak = '<p>&nbsp;</p><div class="page-break" style="page-break-after:always;"><span style="display:none;">&nbsp;</span></div>'

            if pagebreak in html_content:
                # print('글자 존재')
                pass
            else:
                html_content = html_content.replace('<div class="page-break" style="page-break-after:always;"><span style="display:none;">&nbsp;</span></div>', pagebreak)
                # print('글자 미존재')

            # print(html_content)
            # html_content.replace()

            # print(f'ChpaterUID: {ChapterUID}');
            Save_Chapter_content(request, chapteruid, html_content)
            
            if billingmodelcd  == "Fr":
                freedoccnt_resp = supabase.schema("smartdoc").table("configs").select("*").execute()
                freeobjectcnt = freedoccnt_resp.data[0]["freeobjectcnt"]

                docid = supabase.schema("smartdoc").table("chapters").select("*").eq("chapteruid", chapteruid).execute().data[0]['docid']
                doc_data = supabase.schema("smartdoc").rpc("fn_doc_count__r", {'p_docid': docid, 'p_chapteruid': chapteruid}).execute().data
                # print(f'Doc_Data: {doc_data}')

                if doc_data:
                    object_cnt = doc_data[0].get('object_cnt', 0) or 0
                else:
                    object_cnt = 0  # 결과가 없으면 0으로 처리

                current_object_count = object_cnt + len(formats)

                # print(f'현재 개수: {current_object_count}')

                if current_object_count > freeobjectcnt:
                    return JsonResponse({'success': False, 'message': f'항목 설정 최대 사용량 {freeobjectcnt}을 초과하였습니다.', 'add': '템플릿은 정상 저장되었습니다.'}, status=405)
                    # return JsonResponse({"result": "fail", "message": "이미 사용량을 초과하였습니다."}, status=400)
            

            # print(f'Formats: {formats}')
            Save_Objects(request, chapteruid, formats)
            
            return JsonResponse({"message": "저장 성공", "ChapterNm": chapternm})
        except Exception as e:
            print(f'Update_Chapter_Objects 오류: {e}')
            return JsonResponse({'success': False, 'message': 'Docs 테이블 업데이트 실패'}, status=405)
    else:
        return JsonResponse({"error": "POST만 허용"}, status=405)

def Save_Chapter_content(request, ChapterUID, content):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
    # supabase.auth.set_session(access_token, refresh_token)
    
    request.supabase = supabase

    # print(content)
    record = {
        "texttemplate": content
    }
    supabase.schema('smartdoc').table('chapters').update(record).eq("chapteruid", ChapterUID).execute()



def Save_Objects(request, ChapterUID, formats):    
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
    # supabase.auth.set_session(access_token, refresh_token)
    
    request.supabase = supabase
    user_id = request.session.get("user").get("id")

    # 🔍 Step 1: 기존 objects 가져오기
    existing_objs_response = supabase.schema('smartdoc').table('objects') \
        .select("objectuid, objectnm") \
        .eq("chapteruid", ChapterUID) \
        .execute()
    existing_objs = existing_objs_response.data if existing_objs_response else []

    # 📌 Step 2: 현재 formats에서 유지할 objectNm 목록 추출
    new_objectnms = set([obj["objectNm"] for obj in formats if obj.get("objectNm")])

    # 🧹 Step 3: 기존 중에서 사라진 항목 찾기
    to_delete_uids = [
        obj["objectuid"]
        for obj in existing_objs
        if obj["objectnm"] not in new_objectnms
    ]

    # ❌ Step 4: 삭제 실행
    if to_delete_uids:
        supabase.schema('smartdoc').table('objects') \
            .delete() \
            .in_("objectuid", to_delete_uids) \
            .execute()

    # ✅ Step 5: 남은/새로운 formats은 upsert 처리
    for idx, i in enumerate(formats):
        objectuid = i.get("objectUID") or str(uuid.uuid4())
        orderno = i.get("orderno", idx + 1)   # ✅ 없으면 인덱스 번호 사용

        # 저장 시 useyn True 로 처리
        data_set = {
            "chapteruid": ChapterUID,
            "objectuid": objectuid,
            "objectnm": i["objectNm"],
            "useyn": True,
            "orderno": orderno,
            "creator": user_id
        }

        # print(f'Data_Set: {data_set}')

        supabase.schema('smartdoc').table('objects').upsert(data_set).execute()