# views.py
import json
from dateutil import parser
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render
from urllib.parse import urlparse

from django.views.decorators.http import require_http_methods
import logging

from utilsPrj.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

def master_group_users(request):
    """그룹 관리 메인 페이지"""
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    if not user:
        # return JsonResponse({"result": "Failed", "message": "로그인이 필요합니다. 로그인 부탁드립니다."})
        # return redirect("login")
        code = 'login'
        text = '로그인이 필요합니다.'
        page = "master_groupusers"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")

    groupid = request.GET.get('groupid')
    groupnm = supabase.schema('smartdoc').table('groups').select('*').eq('groupid', groupid).execute().data[0]['groupnm']

    try:# groupusers 테이블에서 데이터 조회
        response = supabase.schema('smartdoc').table('groupusers').select('*').eq('groupid', groupid).order('useruid', desc=True).execute()
        
        groupusers = response.data if response.data else []
        
        for i in groupusers:
            if i.get('createdts'):
                try:
                    dt = parser.parse(i['createdts']) if isinstance(i['createdts'], str) else i['createdts']
                    i['createdts'] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    i['createdts'] = ''
            if i.get('useruid'):
                try:
                    user = supabase.schema('public').table('users').select('*').eq('useruid', i['useruid']).execute().data
                    i['usernm'] = user[0]['full_name']
                    i['email'] = user[0]['email']
                except Exception as e:
                    i['usernm'] = ''
            if i.get('creator'):
                try:
                    creatornm = supabase.schema('public').table('users').select('*').eq('useruid', user_id).execute().data[0]['full_name']
                    i['creatornm'] = creatornm
                except Exception as e:
                    i['creatornm'] = ''

        users = supabase.schema('public').table('users').select('*').execute()

        context = {
            'groupid': groupid,
            'groupnm': groupnm,
            'groupusers': groupusers,
            'total_count': len(groupusers),
            'active_count': len([g for g in groupusers if g.get('is_active', False)]),
        }
        
        return render(request, 'pages/master_group_users.html', context)
        
    except Exception as e:
        logger.error(f"그룹 조회 중 오류 발생: {e}")
        return render(request, 'pages/master_group_users.html', {
            'groupusers': [],
            'error': f'데이터 조회 중 오류가 발생했습니다: {str(e)}'
        })

@require_http_methods(["POST"])
def master_group_users_save(request):
    """새 그룹 생성 (필요시 사용)"""
    try:
        # 세션 토큰
        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_supabase_client(access_token, refresh_token)

        user = request.session.get("user")
        if not user:
            # return JsonResponse({"result": "Failed", "message": "로그인이 필요합니다. 로그인 부탁드립니다."})
            # return redirect("login")
            code = 'login'
            text = '로그인이 필요합니다.'
            page = "master_groupusers"
            return render(request, "pages/home.html", {
            "code": code,
            "text": text,
            "page": page,
            "request": request
        })
        user_id = user.get("id")
        
        # POST 데이터에서 그룹 정보 추출
        groupid = request.POST.get('groupid')
        usernm = request.POST.get('usernm')
        email = request.POST.get('email')
        useyn = request.POST.get('useyn')
        
        if useyn == 'on':
            useyn = True
        else:
            useyn = False
            
        if not email:
            return JsonResponse({
                'success': False,
                'message': '이메일은 필수입니다.'
            })
        
        user = supabase.schema('public').table('users').select('*').eq('email', email).execute().data
        # 존재 여부 체크
        if not user:
            return JsonResponse({
                'result': 'Failed',
                'message': '존재하지 않는 이메일입니다.'
            })
        
        useruid = user[0]['useruid']
        
        # 기존 존재 여부 파악
        existing = None
        if groupid:
            resp = supabase.schema("smartdoc").table("groupusers").select("*").eq("groupid", groupid).eq('useruid', useruid).execute()
            existing = resp.data[0] if resp.data else None
        
        data = {
            "groupid": groupid,
            "useruid": useruid,
            "useyn": useyn
        }
        print(f'Data: {data}')
        if existing:
            response = supabase.schema('smartdoc').table('groupusers').update(data).eq('groupid', groupid).eq('useruid', useruid).execute()
        else:
            data["creator"] = user_id
            response = supabase.schema('smartdoc').table('groupusers').insert(data).execute()
        
        if response.data:
            return JsonResponse({
                'result': 'success',
                'group': response.data[0],
                'message': '사용자가 성공적으로 저장되었습니다.'
            })
        else:
            return JsonResponse({
                'result': 'Failed',
                'message': '사용자 저장에 실패했습니다.'
            })
            
    except Exception as e:
        logger.error(f"사용자 저장 중 오류 발생: {e}")
        return JsonResponse({
            'result': 'Failed',
            'message': f'사용자 저장 중 오류가 발생했습니다: {str(e)}'
        })

@require_http_methods(["POST"])
def master_group_users_delete(request):
    """그룹 활성/비활성 상태 변경 (필요시 사용)"""
    try:
        # 세션 토큰
        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_supabase_client(access_token, refresh_token)

        user = request.session.get("user")
        if not user:
            # return JsonResponse({"result": "Failed", "message": "로그인이 필요합니다. 로그인 부탁드립니다."})
            # return redirect("login")
            code = 'login'
            text = '로그인이 필요합니다.'
            page = "master_groupusers"
            return render(request, "pages/home.html", {
            "code": code,
            "text": text,
            "page": page,
            "request": request
        })
        user_id = user.get("id")
        
        # POST 데이터에서 그룹 정보 추출
        data = json.loads(request.body)
        groupid = data.get('groupid')
        useruid = data.get('useruid')
        
        # 그룹 상태 업데이트
        supabase.schema('smartdoc').table('groupusers').delete().eq('groupid', groupid).eq('useruid', useruid).execute()
        
        return JsonResponse({'result': 'success', 'message': '사용자가 성공적으로 삭제되었습니다.'})
            
    except Exception as e:
        logger.error(f"사용자 삭제 중 오류 발생: {e}")
        return JsonResponse({
            'result': 'Failed',
            'message': f'사용자 삭제 중 오류가 발생했습니다: {str(e)}'
        })