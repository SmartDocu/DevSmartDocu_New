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

def master_group_docs(request):
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
        page = "master_groupdocs"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")

    groupid = request.GET.get('groupid')
    groupnm = supabase.schema('smartdoc').table('groups').select('*').eq('groupid', groupid).execute().data[0]['groupnm']

    try:# groupdocs 테이블에서 데이터 조회
        response = supabase.schema('smartdoc').table('groupdocs').select('*').eq('groupid', groupid).order('docid', desc=True).execute()
        
        groupdocs = response.data if response.data else []
        
        for i in groupdocs:
            if i.get('createdts'):
                try:
                    dt = parser.parse(i['createdts']) if isinstance(i['createdts'], str) else i['createdts']
                    i['createdts'] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    i['createdts'] = ''
            if i.get('docid'):
                try:
                    user = supabase.schema('smartdoc').table('docs').select('*').eq('docid', i['docid']).execute().data
                    i['docnm'] = user[0]['docnm']
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
            'groupdocs': groupdocs,
            'total_count': len(groupdocs),
            'active_count': len([g for g in groupdocs if g.get('is_active', False)]),
        }
        
        return render(request, 'pages/master_group_docs.html', context)
        
    except Exception as e:
        logger.error(f"그룹 조회 중 오류 발생: {e}")
        return render(request, 'pages/master_group_docs.html', {
            'groups': [],
            'error': f'데이터 조회 중 오류가 발생했습니다: {str(e)}'
        })

@require_http_methods(["POST"])
def master_group_docs_save(request):
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
        docnm = request.POST.get('docnm')
        useyn = request.POST.get('useyn')
        
        if useyn == 'on':
            useyn = True
        else:
            useyn = False
            
        if not docnm:
            return JsonResponse({
                'success': False,
                'message': '문서명은 필수입니다.'
            })
        
        docs = supabase.schema('smartdoc').table('docs').select('*').eq('docnm', docnm).execute().data
        # 존재 여부 체크
        if not docs:
            return JsonResponse({
                'result': 'Failed',
                'message': '존재하지 않는 문서명 입니다.'
            })
        
        docid = docs[0]['docid']
        
        # 기존 존재 여부 파악
        existing = None
        if groupid:
            resp = supabase.schema("smartdoc").table("groupdocs").select("*").eq("groupid", groupid).eq('docid', docid).execute()
            existing = resp.data[0] if resp.data else None
        
        data = {
            "groupid": groupid,
            "docid": docid,
            "useyn": useyn
        }

        if existing:
            response = supabase.schema('smartdoc').table('groupdocs').update(data).eq('groupid', groupid).eq('docid', docid).execute()
        else:
            data["creator"] = user_id
            response = supabase.schema('smartdoc').table('groupdocs').insert(data).execute()
        
        if response.data:
            return JsonResponse({
                'result': 'success',
                'group': response.data[0],
                'message': '문서가 성공적으로 저장되었습니다.'
            })
        else:
            return JsonResponse({
                'result': 'Failed',
                'message': '문서 저장에 실패했습니다.'
            })
            
    except Exception as e:
        logger.error(f"문서 저장 중 오류 발생: {e}")
        return JsonResponse({
            'result': 'Failed',
            'message': f'문서 저장 중 오류가 발생했습니다: {str(e)}'
        })

@require_http_methods(["POST"])
def master_group_docs_delete(request):
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
        docid = data.get('docid')
        
        # 그룹 상태 업데이트
        supabase.schema('smartdoc').table('groupdocs').delete().eq('groupid', groupid).eq('docid', docid).execute()
        
        return JsonResponse({'result': 'success', 'message': '문서가 성공적으로 삭제되었습니다.'})
            
    except Exception as e:
        logger.error(f"문서 삭제 중 오류 발생: {e}")
        return JsonResponse({
            'result': 'Failed',
            'message': f'문서 삭제 중 오류가 발생했습니다: {str(e)}'
        })