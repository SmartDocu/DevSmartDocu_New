from django.http import HttpResponse
from django.shortcuts import render, redirect
from dateutil import parser

from django.views.decorators.csrf import csrf_exempt
from bs4 import BeautifulSoup

# 워드 만들기
from utilsPrj.html_to_docx import html_to_docx
from docx import Document
from io import BytesIO
from urllib.parse import quote
import base64, json

from utilsPrj.supabase_client import get_supabase_client
# 업로드 용
from utilsPrj.docx_read import convert_docx_to_html_2
from utilsPrj.chapter_read import chapter_contents_read


def chapter_read(request):
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
        page = "read_chapter"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")

    gendocuid = request.GET.get("gendocuid")
    genchapteruid = request.GET.get("genchapteruid")
    sep = request.GET.get("sep")
    type = request.GET.get("type")
    # print(f'GenDocUID: {gendocuid} / GenChapterUID: {genchapteruid} / Sep: {sep} / Type: {type}')
    
    gendocnm = supabase.schema("smartdoc").table("gendocs").select("gendocnm").eq("gendocuid", gendocuid).execute().data[0]["gendocnm"]

    seq = 2
    docs = []
    # 문서 / 업로드
    for i in range(0, seq):
        doc = supabase.schema("smartdoc").table("gendocs").select("*").eq("gendocuid", gendocuid).execute().data

        in_sep = "doc"
        if i == 0:
            in_type = "auto"
        else:
            in_type = "upload"
        # print(f'In_Type: {in_type}')
        result = chapter_contents_read(request, gendocuid, genchapteruid, in_sep, in_type)
        doc[0]["contents"] = result["contents"]
        doc[0]["docyn"] = result["docyn"]
        doc[0]["autoyn"] = result["autoyn"]
        doc[0]["file_path"] = result["file_path"]
        doc[0]["file_name"] = result['file_name']
        doc[0]["inmemoryyn"] = result['inmemoryyn']
        docs.append(doc)

    docs = list(docs)
    docs_json = json.dumps(docs, ensure_ascii=False)
    # print(docs[0])
    # print(docs[1])

    doc_cnt = supabase.schema('smartdoc').rpc('fn_gendoc_newcount__r', {'p_gendocuid': gendocuid}).execute().data
    doc_cnt_json = json.dumps(doc_cnt, ensure_ascii=False)

    doc_info = supabase.schema("smartdoc").table("gendocs").select("*").eq("gendocuid", gendocuid).execute().data
    # print(f'BeFore: {doc_info}')
    for i in doc_info:
        # 시간 포맷 정리
        if i.get('createfiledts'):
            try:
                i['createuser'] = supabase.schema("public").table("users").select("*").eq("useruid", i['createuserid']).execute().data[0]['full_name']

                dt = parser.parse(i['createfiledts']) if isinstance(i['createfiledts'], str) else i['createfiledts']
                i['createfiledts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                print(e)
                i['createuser'] = ''
                i['createfiledts'] = ''

        if i.get('updatefiledts'):
            try:
                i['updateuser'] = supabase.schema("public").table("users").select("*").eq("useruid", i['updateuserid']).execute().data[0]['full_name']

                dt = parser.parse(i['updatefiledts']) if isinstance(i['updatefiledts'], str) else i['updatefiledts']
                i['updatefiledts'] = dt.strftime("%y-%m-%d %H:%M")
            except Exception as e:
                i['updateuser'] = ''
                i['updatefiledts'] = ''

    # print(f'Doc_Info: {doc_info[0]}')

    return render(request, "pages/req_chapter_read.html", {"docs": docs_json, "doc_info": doc_info[0], "doc_cnt": doc_cnt_json, "gendocnm": gendocnm})

# === 추가: 메모리 파일 다운로드 뷰 ===
@csrf_exempt
def download_inmemory_docx(request):
    """메모리에 저장된 base64 DOCX를 내려주는 뷰"""
    if request.method == "POST":
        body = json.loads(request.body.decode("utf-8"))
        file_data = body.get("file_data")
        file_name = body.get("file_name", "document.docx")
    else:
        file_data = request.GET.get("file_data")
        file_name = request.GET.get("file_name", "document.docx")

    if not file_data:
        return HttpResponse("No file data", status=400)

    file_bytes = base64.b64decode(file_data)

    # 한글/특수문자 지원: filename + filename*
    ascii_fname = ''.join(c if ord(c) < 128 else '_' for c in file_name).strip() or "document.docx"
    quoted = quote(file_name)
    disposition = f'attachment; filename="{ascii_fname}"; filename*=UTF-8\'\'{quoted}'

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    response["Content-Disposition"] = disposition
    return response


 