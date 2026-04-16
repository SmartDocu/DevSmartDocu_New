import json, re, io, uuid, os, requests
from datetime import datetime
from dateutil import parser
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

# from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.supabase_client import get_supabase

# 챕터 만들기
from utilsPrj.chapter_making import replace_doc


def req_chapter_objects_read(request):

    supabase = get_supabase(request)

    user = request.session.get("user")
    if not user:
        return render(request, 'pages/home.html')
    
    if not user:
        # return JsonResponse({"result": "Failed", "message": "로그인이 필요합니다. 로그인 부탁드립니다."})
        # return redirect("login")
        code = 'login'
        text = '로그인이 필요합니다.'
        page = "req_read_chapters"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    
    genchapteruid = request.GET.get("genchapteruid")
    # print(genchapteruid)
    ##### 0. genchapter 필터링
    genchapter = supabase.schema('smartdoc').table('genchapters').select('*').eq('genchapteruid', genchapteruid).execute().data

    for i in genchapter:
        # 시간 포맷 정리
        if i.get('createfiledts'):
            try:
                dt = parser.parse(i['createfiledts']) if isinstance(i['createfiledts'], str) else i['createfiledts']
                i['createfiledts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['createfiledts'] = ''

    ##### 1. doc 필터
    docid = genchapter[0]['docid']

    doc = supabase.schema('smartdoc').table('docs').select('*').eq('docid', docid).execute().data

    ##### 2. GenDocs 필터
    gendocuid = genchapter[0]['gendocuid']

    gendoc = supabase.schema('smartdoc').table('gendocs').select('*').eq('gendocuid', gendocuid).execute().data

    gendocnm = gendoc[0]['gendocnm']
    closeyn = gendoc[0]['closeyn']
    ##### 3. chapternm
    chapter = supabase.schema('smartdoc').table('chapters').select('*').eq('chapteruid', genchapter[0]['chapteruid']).execute().data
    
    chapternm = chapter[0]['chapternm']

    objects_data = supabase.schema('smartdoc').rpc("fn_genobjects__r", {"p_genchapteruid": genchapteruid}).execute().data or []

    for i in objects_data:
        # 시간 포맷 정리
        if i.get('objcreatedts'):
            try:
                dt = parser.parse(i['objcreatedts']) if isinstance(i['objcreatedts'], str) else i['objcreatedts']
                i['objcreatedts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['objcreatedts'] = ''
        # 시간 포맷 정리
        if i.get('genobjcreatedts'):
            try:
                dt = parser.parse(i['genobjcreatedts']) if isinstance(i['genobjcreatedts'], str) else i['genobjcreatedts']
                i['genobjcreatedts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['genobjcreatedts'] = ''
    
    sorted_objects_data = sorted(objects_data, key=lambda x: x["orderno"])
    # print(sorted_objects_data)

    # print(f'{sorted_objects_data}')

    # project에서 나의 권한은??
    projectid = supabase.schema('smartdoc').table('docs').select('*').eq('docid', docid).execute().data[0]['projectid']
    rolecd = supabase.schema('smartdoc').table('projectusers').select('*').eq('projectid', projectid).eq('useruid', user_id).execute().data[0]['rolecd']
    # print(f'DocID: {docid} / ProjectID: {projectid} / RoleCd: {rolecd} / UserUID: {user_id} ')

    return render(request, 'pages/req_chapter_objects_read.html', {
        'gendocuid': gendocuid,
        'objects_data': sorted_objects_data,
        'gendocnm': gendocnm,
        'chapternm': chapternm,
        'genchapteruid': genchapteruid,
        'genchapter': genchapter[0],
        'closeyn': closeyn,
        'rolecd' : rolecd
    })


@csrf_exempt
def object_rewrite(request):

    supabase = get_supabase(request)

    user = request.session.get("user")
    user_id = user.get("id")

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            genchapteruid = data.get("genchapteruid")
            objectuid = data.get("objectuid")
            # print(f'GenChapteruid: {genchapteruid} / Objectuid: {objectuid}')

            genchapters = supabase.schema('smartdoc').table('genchapters').select('*').eq('genchapteruid', genchapteruid).execute().data
            if not genchapters:
                return JsonResponse({'success': False, 'message': '해당 챕터를 찾을 수 없습니다.'})

            gendocuid = genchapters[0]["gendocuid"]

            # 3️⃣ 남아있는 락 확인 (문서 락 OR 현재 챕터 락만)
            genlocks_c = (
                supabase
                .schema('smartdoc')
                .table('genlocks')
                .select('*')
                .eq('gendocuid', gendocuid)
                .eq('genchapteruid', genchapteruid)
                .execute()
                .data
            )

            genlocks_d = (
                supabase
                .schema('smartdoc')
                .table('genlocks')
                .select('*')
                .eq('gendocuid', gendocuid)
                .eq('genchapteruid', '')  # 문서 락 row
                .execute()
                .data
            )

            # 
            is_locked = any(
                row.get('doclocked') is True or row.get('chapterlocked') is True
                for row in genlocks_c + genlocks_d
            )

            if is_locked:
                return JsonResponse({
                    'success': False,
                    'message': '이 문서의 해당 챕터가 이미 작성 중입니다. 나중에 다시 시도해 주십시오.'
                })
            
            # ✅ Generator를 for 루프로 실행
            texttemplate = None
            for progress_data in replace_doc(request, supabase, user_id, genchapteruid, 'create', 'rewrite', objectuid, 
                                             genObjectDirectYn=True):
                if progress_data['type'] == 'complete':
                    texttemplate = progress_data.get('texttemplate', '')
                elif progress_data['type'] == 'error':
                    return JsonResponse({'success': False, 'message': progress_data['message']}, status=500)

            return JsonResponse({'success': True}, status=200)
        except Exception as e:
            print(f'ErrorMessage: {e}')
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    return JsonResponse({'success': False, 'message': 'POST 요청만 허용됨'})


@csrf_exempt
def object_chapter_rewrite(request):
    # 세션 토큰
    supabase = get_supabase(request)

    user = request.session.get("user")
    user_id = user.get("id")

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            genchapteruid = data.get("genchapteruid")
            # print(f'GenChapteruid: {genchapteruid}')

            genchapters = supabase.schema('smartdoc').table('genchapters').select('*').eq('genchapteruid', genchapteruid).execute().data
            if not genchapters:
                return JsonResponse({'success': False, 'message': '해당 챕터를 찾을 수 없습니다.'})

            gendocuid = genchapters[0]["gendocuid"]

            # 3️⃣ 남아있는 락 확인 (문서 락 OR 현재 챕터 락만)
            genlocks_c = (
                supabase
                .schema('smartdoc')
                .table('genlocks')
                .select('*')
                .eq('gendocuid', gendocuid)
                .eq('genchapteruid', genchapteruid)
                .execute()
                .data
            )

            genlocks_d = (
                supabase
                .schema('smartdoc')
                .table('genlocks')
                .select('*')
                .eq('gendocuid', gendocuid)
                .eq('genchapteruid', '')  # 문서 락 row
                .execute()
                .data
            )

            # 2️⃣ 2시간 이상 진행 중인 row 강제 unlock
            is_locked = any(
                row.get('doclocked') is True or row.get('chapterlocked') is True
                for row in genlocks_c + genlocks_d
            )

            if is_locked:
                return JsonResponse({
                    'success': False,
                    'message': '이 문서의 해당 챕터가 이미 작성 중입니다. 나중에 다시 시도해 주십시오.'
                })
            
            ## genchapter 추출
            read_genchapter = supabase.schema('smartdoc').table('genchapters').select('*').eq('genchapteruid', genchapteruid).execute().data
            # print(f'Read_GenChapter: {read_genchapter}')
            gendocuid = read_genchapter[0]['gendocuid']
            chapteruid = read_genchapter[0]['chapteruid']
            read_chapter = supabase.schema('smartdoc').table('chapters').select('texttemplate').eq('chapteruid', chapteruid).execute().data
            
            texttemplate = read_chapter[0]['texttemplate']

            read_texttemplate = supabase.schema('smartdoc').rpc("fn_genchapter_detail__r", {'p_genchapteruid': genchapteruid}).execute().data            
                # print(f'Read_TextTemplate: {read_texttemplate}')
                
            now = datetime.now().isoformat()

            genobjects = []
            if read_texttemplate:

                # print('교체 작업 시작')
                ## datas 추출
                datas = []

                for i in read_texttemplate:

                    
                    # print(i)
                    if i["genobjectuid"]:
                        read_datas = supabase.schema('smartdoc').table("genobjects").select("resulttext").eq('genobjectuid', i["genobjectuid"]).execute().data
                        # print(read_datas)
                        html = read_datas[0]['resulttext']
                        placeholder = f"{{{i['objectnm']}}}"
                        placeholder = f"{{{placeholder}}}"
                        # placeholder = f"<p>{{{placeholder}}}</p>"
                        # print(f'PlaceHolder: {placeholder}')
                        texttemplate = texttemplate.replace(placeholder, html)
                # print(texttemplate)

            
            genchapters = {
                'gentexttemplate': texttemplate
                ,'genchapteruid': genchapteruid
                ,'createuserid': user_id
                ,'createfiledts': now
            }
            
            update_genchapters(supabase, genchapters, genchapteruid)
            # print(genchapters)
            
            gendoc_genchapters = {
                'gendocuid': gendocuid
                ,'genchapteruid': genchapteruid
                ,'creator': user_id
                ,'createdts': now
            }        
            save_gendoc_genchapters(supabase, gendoc_genchapters)
            # print(gendoc_genchapters)

            return JsonResponse({'success': True}, status=200)
        except Exception as e:
            print(f'ErrorMessage: {e}')
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    return JsonResponse({'success': False, 'message': 'POST 요청만 허용됨'})


def update_genchapters (supabase, genchapters, genchapteruid):
    # print('save_genchapters')
    try:
        supabase.schema('smartdoc').table('genchapters').update(genchapters).eq('genchapteruid', genchapteruid).execute()
    except Exception as e:
        print(f'ErrorMessage: {e}')
        return JsonResponse({'success': False, 'message': str(e)})

def save_gendoc_genchapters (supabase, gendoc_genchapters):
    # print('save_gendoc_genchapters')
    try:
        supabase.schema('smartdoc').table('gendoc_genchapters').insert(gendoc_genchapters).execute().data
    except Exception as e:
        print(f'ErrorMessage: {e}')
        return JsonResponse({'success': False, 'message': str(e)})