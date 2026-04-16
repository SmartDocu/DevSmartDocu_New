import json, uuid
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from dateutil import parser

from utilsPrj.supabase_client import get_supabase_client


def master_help(request):
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
        page = "master_help"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")

    helps = supabase.schema("smartdoc").table("helps").select("*").execute().data

    
    for i in helps:
        # 시간 포맷 정리
        if i.get('creator'):
            try:
                i['createuser'] = supabase.schema("public").table("users").select("*").eq("useruid", i['creator']).execute().data[0]['full_name']
            except Exception as e:
                print(e)
                i['createuser'] = ''

    # 전달할 데이터 묶기
    initial_data = {
        "helps": helps
    }

    # print('master_help 페이지 로딩 완료..')
    return render(request, 'pages/master_help.html', {"initial_data": mark_safe(json.dumps(initial_data))})

def master_help_save(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
    
    user = request.session.get("user")
    if not user:
        return render(request, 'pages/home.html')
    
    user_id = user.get("id")
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            html_content = data.get('html_content', '')

            data['creator'] = user_id

            helpuid = data['helpuid']

            if not helpuid:
                data['helpuid'] = str(uuid.uuid4())
            # print(f'Save: {data}')
            
            helpuid = data['helpuid']

            creator = supabase.schema("public").table("users").select("*").eq("useruid", user_id).execute().data[0]['full_name']

            response = supabase.schema("smartdoc").table("helps").upsert(data).execute().data
            
            createdts = response[0]['createdts']

            return JsonResponse({"success": True, "message": "저장 성공", "helpuid": helpuid, "creator": creator, "createdts": createdts})
        except Exception as e:
            print(f'Update_Chapter_Objects 오류: {e}')
            return JsonResponse({'success': False, 'message': 'Help 문서 저장 실패'}, status=405)
    else:
        return JsonResponse({"error": "POST만 허용"}, status=405)

def master_help_delete(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
    # supabase.auth.set_session(access_token, refresh_token)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            helpuid = data.get('helpuid', '')

            # print(f'Delete: {data}')

            supabase.schema("smartdoc").table("helps").delete().eq("helpuid", helpuid).execute()
            
            return JsonResponse({"success": True, "message": "저장 성공"})
        except Exception as e:
            print(f'Update_Chapter_Objects 오류: {e}')
            return JsonResponse({'success': False, 'message': 'Help 문서 삭제 실패'}, status=405)
    else:
        return JsonResponse({"error": "POST만 허용"}, status=405)