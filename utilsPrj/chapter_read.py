from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

# 워드 만들기
from utilsPrj.html_to_docx import html_to_docx
from docx import Document
from io import BytesIO
from urllib.parse import quote
import base64, json

from utilsPrj.supabase_client import get_supabase, SUPABASE_SCHEMA
# 업로드 용
from utilsPrj.docx_read import convert_docx_to_html_2

def chapter_contents_read(request, gendocuid, genchapteruid, sep, type):
    # print('Chapter 또는 Doc 문서 호출')
    supabase = get_supabase(request)
    # Sep => doc / chapter
    # type => auto / upload
    
    if type == 'auto':
        autoyn = True
    else:
        autoyn = False
    
    if sep == 'doc':
        docyn = True
    else:
        docyn = False
        
    html_contents = ''
    inmemoryyn = False
    file_path = ''
    file_name = ''

    if sep == 'chapter':
        texttemplate = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('chapteruid, gentexttemplate, updatefileurl, flattexttemplate').eq('genchapteruid', genchapteruid).execute().data
        chaptername = supabase.schema(SUPABASE_SCHEMA).table('chapters').select('chapternm').eq('chapteruid', texttemplate[0]['chapteruid']).execute().data[0]['chapternm']
        if type == 'auto':
            if texttemplate[0]['gentexttemplate']:
                ## 2026-05-06 Min
                html_contents = texttemplate[0]['gentexttemplate']
                ## 2026-05-06 Min
                # html_contents = texttemplate[0]['flattexttemplate']
                html_contents_origin = html_contents
                # 페이지 나누기 기능에 대하여 좀 더 시각적으로 표현 처리
                sep_pagebreak = '<div class="page-break" style="page-break-after:always;"><span style="display:none;">&nbsp;</span></div>'
                html_contents = html_contents.replace(sep_pagebreak, '<div class="page-break ck-widget" contenteditable="false"><span class="page-break__label">페이지 나누기</span></div>')

                # Document → BytesIO 저장 → base64 인코딩
                doc: Document = html_to_docx(supabase, genchapteruid, html_contents_origin)
                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                file_path = base64.b64encode(buffer.read()).decode()
                file_name = f"{chaptername}.docx"
                inmemoryyn = True
            else:
                html_contents = '작성된 문서가 없습니다.'
        elif type == 'upload':
            if texttemplate[0]['updatefileurl']:
                file_path = texttemplate[0]['updatefileurl']
                html_contents = convert_docx_to_html_2(file_path, url=True, formyn=False, ckeditor_mode=False, printyn=False);
                file_name = f"{chaptername}.docx"
            else:
                html_contents = '업로드 된 문서가 없습니다.'
    elif sep == 'doc':
        texttemplate = supabase.schema(SUPABASE_SCHEMA).table('gendocs').select('createfileurl, updatefileurl, gendocnm').eq('gendocuid', gendocuid).execute().data
        if type == 'auto':
            if texttemplate[0]['createfileurl']:
                file_path = texttemplate[0]['createfileurl']
                html_contents = convert_docx_to_html_2(file_path, url=True, formyn=False, ckeditor_mode=False, printyn=False);
                file_name = f"{texttemplate[0]['gendocnm']}.docx"
            else:
                html_contents = '작성된 문서가 없습니다.'
        elif type == 'upload':
            if texttemplate[0]['updatefileurl']:
                file_path = texttemplate[0]['updatefileurl']
                html_contents = convert_docx_to_html_2(file_path, url=True, formyn=False, ckeditor_mode=False, printyn=False);
                file_name = f"{texttemplate[0]['gendocnm']}.docx"
                # print(html_contents)
            else:
                html_contents = '업로드 된 문서가 없습니다.'

    # print('Chapter 또는 Doc 문서 호출 완료')

    return {"contents": html_contents, "docyn": docyn, "autoyn": autoyn, "file_path": file_path, "file_name": file_name, "inmemoryyn": inmemoryyn}