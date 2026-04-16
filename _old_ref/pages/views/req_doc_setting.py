import json
from datetime import datetime
from django.http import JsonResponse
from django.shortcuts import render

from utilsPrj.supabase_client import get_supabase_client

def req_doc_check_params (request):
    print('req_doc_check_params 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    if request.method == "POST":
        data = json.loads(request.body)
        # print(data)
        docid = data.get('docid')
        docnm = data.get('docnm')
        Form = data.get("params", [])

        # print(f'DocID: {docid} / Form: {Form}')
        
        # 데이터 삽입
        try:
            # 2️⃣ 우선 관련 paramuid 들만 조회
            paramuids = [f["paramuid"] for f in Form]
            response = supabase.schema('smartdoc').table("gendoc_params").select("*").in_("paramuid", paramuids).execute()
            rows = response.data

            # 3️⃣ gendocuid 별로 묶기
            from collections import defaultdict
            grouped = defaultdict(list)
            for row in rows:
                grouped[row["gendocuid"]].append(row)

            # 4️⃣ 모든 조건을 만족하는 gendocuid 필터링
            target_docs = []
            for gendocuid, items in grouped.items():
                ok = True
                for cond in Form:
                    match = next(
                        (i for i in items if i["paramuid"] == cond["paramuid"] 
                        and str(i["paramvalue"]).strip() == str(cond["paramvalue"]).strip()),
                        None
                    )
                    if not match:
                        ok = False
                        break
                if ok:
                    target_docs.append(gendocuid)

            # print("✅ 필터링된 gendocuid:", target_docs)

            # return JsonResponse({
            #         'success': True,
            #         'message': f'데이터존재'
            #     })

            if target_docs:
                # print('데이터 존재 하고 있음')
                return JsonResponse({
                    'success': True,
                    'message': f'데이터존재'
                })
            else:
                # print('데이터 미존재 하고 있음')
                return JsonResponse({
                    'success': True,
                    'message': f'데이터미존재'
                })

        except Exception as e:
            print(e)
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

def req_doc_check_objects (request):
    print('req_doc_check_objects 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    if request.method == "POST":
        data = json.loads(request.body)
        # print(data)
        docid = data.get('docid')
        # print(f'DocID: {docid} / Form: {Form}')
        
        # 데이터 삽입
        check_objects = []
        try:
            chapters = supabase.schema('smartdoc').table('chapters').select('*').eq('docid', docid).execute().data

            
            # 각 챕터의 객체들을 조회
            for chapter in chapters:
                chapteruid = chapter["chapteruid"]
                chapternm = chapter["chapternm"]
                objects = supabase.schema('smartdoc').rpc("fn_objects__r", {"p_chapteruid": chapteruid}).execute().data or []
                # print(f'Objects: {objects}')
                # 날짜 포맷팅
                for obj in objects:
                    if obj.get('objectuid'):
                        if obj['useyn']:
                            if not obj['objectsettingyn']:
                                check_objects.append({'text': f'챕터: {chapternm} - 항목: {obj['objectnm']}'})

            # print(check_objects)
            
            if len(check_objects) > 0:
                # print('데이터 존재 하고 있음')
                return JsonResponse({
                    'success': True,
                    'message': f'항목 미설정 존재',
                    'objects': check_objects
                })
            else:
                # print('데이터 미존재 하고 있음')
                return JsonResponse({
                    'success': True,
                    'message': f'항목 미설정 미존재'
                })

        except Exception as e:
            print(e)
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


def req_doc_save_params (request):
    print('req_doc_save_params 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    if request.method == "POST":
        data = json.loads(request.body)
        
        docid = data.get('docid')
        docnm = data.get('docnm')
        Form = data.get("params", [])
        print(f'Form: {Form}')
        user_id = request.session.get("user").get("id")
        
        doc = {'docid': docid, 'gendocnm': docnm, 'creator': user_id}
        now = datetime.now().isoformat()
        
        # 데이터 삽입
        try:
            ##### 1. gendocs 삽입
            ## 테이블 데이터 삽입
            GenDocs = supabase.schema('smartdoc').table('gendocs').insert(doc).execute()
            # print(GenDocs.data)
            gendocuid = GenDocs.data[0]['gendocuid']

            ##### 2. gendoc_params 삽입
            ## Params 값 정렬
            params = []
            for i in Form:
                param_data = {
                    'gendocuid': gendocuid,
                    'paramnm': i['paramnm'],
                    'paramuid': i['paramuid'],
                    'orderno': i['orderno'],
                    'paramvalue': i['paramvalue'],  # 빈값 기본처리
                    'creator': user_id
                }
                params.append(param_data)
            ## 테이블 데이터 삽입
            supabase.schema('smartdoc').table('gendoc_params').insert(params).execute()

            ###### 3. genchapters 삽입
            ## chapteruid 호출
            chapters = supabase.schema('smartdoc').table('chapters').select('*').eq('docid', docid).eq('useyn', True).execute()
            chapters_data = chapters.data

            
            ## chapters 값 정렬
            for i, chapters in enumerate(chapters_data, 1):
                chapters['gendocuid'] = gendocuid
                chapters['creatoruid'] = user_id

            chapter = []
            for i, chapters in enumerate(chapters_data, 1):
                chatper_data = {
                    'docid': chapters['docid'],
                    'chapteruid': chapters['chapteruid'],
                    'gendocuid': chapters['gendocuid'],
                    'texttemplate': chapters['texttemplate'],
                    'createfilestartdts': now,
                    'creator': chapters['creatoruid'],
                    'createdts': now
                }
                chapter.append(chatper_data)
            ## 테이블 데이터 삽입
            supabase.schema('smartdoc').table('genchapters').insert(chapter).execute()

            print('페이지 이동')
            # return render(request, 'pages/req_read_doc.html')
            return JsonResponse({
                'success': True,
                'gendocuid': gendocuid,
                'message': f'데이터 저장이 완료 되었습니다.\n잠시 후 화면이 이동 됩니다.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


def req_doc_update_params (request):
    print('req_doc_update_params 진입')
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
    
    if request.method == "POST":
        data = json.loads(request.body)
        
        gendocuid = data.get('gendocuid')
        docid = data.get('docid')
        docnm = data.get('docnm')
        Form = data.get("params", [])
        user_id = request.session.get("user").get("id")
        
        # print(f'From: {Form}')

        # 데이터 삽입
        try:
            # print(gendocuid)
            if not gendocuid:
                return JsonResponse({'success': False, 'message': 'gendocuid가 없습니다.'}, status=500)
            ##### 1. gendocs 삽입
            ## 테이블 데이터 삽입
            data = {'gendocuid': gendocuid, 'gendocnm': docnm}

            supabase.schema('smartdoc').table('gendocs').upsert(data).execute()

            ##### 2. gendoc_params 삽입
            ## Params 값 정렬
            params = []
            for i in Form:
                # print(i)
                param_data = {
                    'gendocuid': gendocuid,
                    'paramnm': i['paramnm'],
                    'paramuid': i['paramuid'],
                    'paramvalue': i['paramvalue'],  # 빈값 기본처리
                    'orderno': i['orderno'],
                    'creator': user_id
                }

                # print(param_data)
                exist = supabase.schema("smartdoc").table("gendoc_params").select("*").eq("gendocuid", gendocuid).eq('paramuid', i['paramuid']).execute().data
                # print(f'Exist: {exist}')

                if exist:
                    # print('존재')
                    supabase.schema('smartdoc').table('gendoc_params').update(param_data).eq('gendocuid', gendocuid).eq('paramuid', i['paramuid']).execute()
                else:
                    # print('미존재')
                    supabase.schema('smartdoc').table('gendoc_params').insert(param_data).execute()

            return JsonResponse({
                'success': True,
                'gendocuid': gendocuid,
                'message': f'데이터 저장이 완료 되었습니다.\n잠시 후 화면이 이동 됩니다.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
        
def req_doc_close (request):
    print('req_doc_close 진입')
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
        page = "req_write_doc"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    now = datetime.now().isoformat()
    
    if request.method == "POST":
        data = json.loads(request.body)
        
        gendocuid = data.get('gendocuid')
        docid = supabase.schema("smartdoc").table("gendocs").select("docid").execute().data[0]['docid']

        # 데이터 삽입
        try:
            # print(gendocuid)
            if not gendocuid:
                return JsonResponse({'success': False, 'message': 'gendocuid가 없습니다.'}, status=500)
            ##### 1. gendocs 삽입
            ## 테이블 데이터 삽입

            data = {
                "gendocuid": gendocuid,
                "closeyn": True,
                "closeuseruid": user_id,
                "closedts": now
            }

            supabase.schema('smartdoc').table('gendocs').upsert(data).execute()

            data = {
                "gendocuid": gendocuid,
                "docid": docid,
                "closeyn": True,
                "closeuseruid": user_id,
                "closedts": now
            }

            supabase.schema("smartdoc").table("loggendoccloses").upsert(data).execute()

            return JsonResponse({
                'success': True,
                'gendocuid': gendocuid,
                'message': f'데이터 저장이 완료 되었습니다.\n잠시 후 화면이 이동 됩니다.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
        
def req_doc_open (request):
    print('req_doc_open 진입')
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
        page = "req_write_doc"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    now = datetime.now().isoformat()
    
    if request.method == "POST":
        data = json.loads(request.body)
        
        gendocuid = data.get('gendocuid')
        docid = supabase.schema("smartdoc").table("gendocs").select("docid").execute().data[0]['docid']
        
        # 데이터 삽입
        try:
            # print(gendocuid)
            if not gendocuid:
                return JsonResponse({'success': False, 'message': 'gendocuid가 없습니다.'}, status=500)
            ##### 1. gendocs 삽입
            ## 테이블 데이터 삽입

            data = {
                "gendocuid": gendocuid,
                "closeyn": False,
                "closeuseruid": None,
                "closedts": None
            }

            supabase.schema('smartdoc').table('gendocs').upsert(data).execute()

            data = {
                "gendocuid": gendocuid,
                "docid": docid,
                "closeyn": False,
                "closeuseruid": user_id,
                "closedts": now
            }

            supabase.schema("smartdoc").table("loggendoccloses").upsert(data).execute()

            return JsonResponse({
                'success': True,
                'gendocuid': gendocuid,
                'message': f'데이터 저장이 완료 되었습니다.\n잠시 후 화면이 이동 됩니다.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
        
def req_doc_delete (request):
    print('req_doc_delete 진입')
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
        page = "req_write_doc"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    now = datetime.now().isoformat()
    
    if request.method == "POST":
        data = json.loads(request.body)
        
        gendocuid = data.get('gendocuid')

        try:
            # 삭제
            result = delete_gendoc(request, gendocuid)

            if result != gendocuid:
                raise ValueError(result)

            return JsonResponse({
                'success': True,
                'gendocuid': gendocuid,
                'message': f'데이터 저장이 완료 되었습니다.\n잠시 후 화면이 이동 됩니다.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
        
def delete_gendoc (request, gendocuid):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    print(f'Delete GenDocUID: {gendocuid}')

    try:
        #### 삭제 전 정보 획득
        # gendoc
        gendoc = supabase.schema('smartdoc').table('gendocs').select("*").eq("gendocuid", gendocuid).execute().data
        gendoc_create = gendoc[0]['createfileurl']
        gendoc_update = gendoc[0]['updatefileurl']

        # genchapter
        genchapter = supabase.schema("smartdoc").table("genchapters").select("*").eq("gendocuid", gendocuid).execute().data
        genchapter_uids = [gc["genchapteruid"] for gc in genchapter]

        genobject_uids = []
        # genobjects
        if genchapter_uids:
            genobjects = supabase.schema("smartdoc").table("genobjects").select("*").in_("genchapteruid", genchapter_uids).execute().data
            genobject_uids = [go["genobjectuid"] for go in genobjects]
        
        # gendoc_params
        gendoc_params = supabase.schema("smartdoc").table("gendoc_params").select("*").eq("gendocuid", gendocuid).execute().data
        
        #### 삭제 처리 진행 ==> 정보 획득 역순으로 삭제
        # 로그 삭제
        del_loggenobjects = supabase.schema("smartdoc").table("loggenobjects").delete().in_("genobjectuid", genobject_uids).execute().data
        del_loggenchapter = supabase.schema("smartdoc").table("loggenchapters").delete().in_("genchapteruid", genchapter_uids).execute().data
        del_loggendocs = supabase.schema("smartdoc").table("loggendocs").delete().eq("gendocuid", gendocuid).execute().data
        # 결과 파일 삭제
        if gendoc_create:
            fileurl = gendoc_create.split('smartdoc/')[1].rstrip('?')
            supabase.storage.from_("smartdoc").remove([fileurl])
        if gendoc_update:
            fileurl = gendoc_update.split('smartdoc/')[1].rstrip('?')
            supabase.storage.from_("smartdoc").remove([fileurl])

        for gc in genchapter:
            # 자동
            # if gc.get('createfileurl'):
            #     fileurl = gc["createfileurl"].split('smartdoc/')[1].rstrip('?')
            #     supabase.storage.from_("smartdoc").remove([fileurl])
            # 수정
            if gc.get("updatefileurl"):
                fileurl = gc["updatefileurl"].split('smartdoc/')[1].rstrip('?')
                supabase.storage.from_("smartdoc").remove([fileurl])

        # 데이터 삭제 gendoc_params -> genobjects -> genchapter -> gendoc
        del_gendoc_params = supabase.schema("smartdoc").table("gendoc_params").delete().eq("gendocuid", gendocuid).execute().data
        if genchapter_uids:
            del_genobjects = supabase.schema("smartdoc").table("genobjects").delete().in_("genchapteruid", genchapter_uids).execute().data
        del_genchapter = supabase.schema("smartdoc").table("genchapters").delete().eq("gendocuid", gendocuid).execute().data
        del_gendoc = supabase.schema('smartdoc').table('gendocs').delete().eq("gendocuid", gendocuid).execute().data

        return gendocuid
    except Exception as e:
        return str(e)