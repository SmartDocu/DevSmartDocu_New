from dateutil import parser
from django.shortcuts import render

from django.http import StreamingHttpResponse

# from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.supabase_client import get_supabase

def req_doc_status(request):
    # 세션 토큰
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
    
    ##### 0. docs 필터링
    # docs = supabase.schema("smartdoc").rpc("fn_docs_filtered__r_user", {'p_useruid': user_id}).execute().data or []
    # docid = [d["docid"] for d in docs]

    gendocuid = request.GET.get("gendocs")
    # print(f'GenDocUID: {gendocuid}')

    ##### 1. gen 상태
    gendocs_data = supabase.schema('smartdoc').rpc("fn_gendoc_status__r", {"p_gendocuid": gendocuid}).execute().data or []
    # print(f'GenChapter_Data: {genchapter_data}')

    for i in gendocs_data:
        # 시간 포맷 정리
        if i.get('createfiledts'):
            try:
                dt = parser.parse(i['createfiledts']) if isinstance(i['createfiledts'], str) else i['createfiledts']
                i['createfiledts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['createfiledts'] = ''

        if i.get('updatefiledts'):
            try:
                dt = parser.parse(i['updatefiledts']) if isinstance(i['updatefiledts'], str) else i['updatefiledts']
                i['updatefiledts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['updatefiledts'] = ''

    ##### 2. gen 조회
    gendoc_data = supabase.schema('smartdoc').rpc("fn_gendocs__r", {"p_gendocuid": gendocuid}).execute().data or []

    for i in gendoc_data:
        # 시간 포맷 정리
        if i.get('createfiledts'):
            try:
                dt = parser.parse(i['createfiledts']) if isinstance(i['createfiledts'], str) else i['createfiledts']
                i['createfiledts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['createfiledts'] = ''
    
    # 값 분배
    gendocnm = gendoc_data[0]['gendocnm']
    createfiledts = gendoc_data[0]['createfiledts']

    # print(f'GenDocUID: {gendocuid} / GenDocNm: {gendocnm} / CreateFileDTS: {createfiledts}')
    # print(f'GenDoc: {gendocs_data}')
    # print('')
    return render(request, 'pages/req_doc_status.html', {
        'gendocuid': gendocuid,
        'gendocnm': gendocnm,
        'createfiledts': createfiledts,
        'gendocs_data': gendocs_data,
    })