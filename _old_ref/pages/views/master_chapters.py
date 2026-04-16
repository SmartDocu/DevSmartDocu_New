from django.shortcuts import render
from django.http import JsonResponse
import json
from django.http import HttpResponseBadRequest
import uuid
import os
# import tempfile
from urllib.parse import urlparse

from utilsPrj.supabase_client import get_supabase_client

def master_chapters(request):
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
        page = "req_read_doc"
        return render(request, "pages/home.html", {
        "code": code,
        "text": text,
        "page": page,
        "request": request
    })
    user_id = user.get("id")
    docid = user.get("docid")
    docnm = user.get("docnm")

    # docs = supabase.schema("smartdoc").rpc("fn_docs_filtered__r_user_manager", {'p_useruid': user_id}).execute().data or []

    # docid = request.GET.get('docid') or (str(docs[0]["docid"]) if docs else None)

    docs_resp = supabase.schema("smartdoc").table("docs").select("*").eq("docid", docid).execute()
    docs = docs_resp.data if docs_resp.data else []

    # try:
    #     docid_int = int(docid)
    # except (TypeError, ValueError):
    #     return HttpResponseBadRequest("유효한 docid가 필요합니다.")

    try:
        docid_int = int(docid) if docid else None
    except ValueError:
        docid_int = None

    # chapters_resp = supabase.schema("smartdoc").table("chapters").select("*").eq("docid", docid_int).order("chapterno").execute()
    # chapters = chapters_resp.data if chapters_resp.data else []

    if docid is not None:
        chapters_resp = (
            supabase
            .schema("smartdoc")
            .table("chapters")
            .select("*")
            .eq("docid", docid_int)
            .order("chapterno")
            .execute()
        )
        chapters = chapters_resp.data if chapters_resp.data else []
    else:
        chapters = []
        # chapters_resp = (
        #     supabase
        #     .schema("smartdoc")
        #     .table("chapters")
        #     .select("*")
        #     .order("chapterno")
        #     .execute()
        # )

    return render(request, 'pages/master_chapters.html', {
        'user' : user,
        'docs' : docs,
        'docid' : docid,
        'docnm' : docnm,
        'chapters': chapters,
    })


def master_chapters_save(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST 요청만 허용됩니다.")

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    try:
        chapteruid = request.POST.get("chapteruid")  # 신규인 경우 None or 빈값 예상
        # docid = request.POST.get("docid")        
        chapternm = request.POST.get("chapternm")
        chapterno = request.POST.get("chapterno")
        useyn = request.POST.get("useyn") == "on" or request.POST.get("useyn") == "true"  # 체크박스 처리
        chaptertemplate_file = request.FILES.get("templatefile")

        user = request.session.get("user")
        user_id = user.get("id")
        docid = user.get("docid")
        
        if not docid or not chapternm or not chapterno:
            return JsonResponse({"error": "필수값이 누락되었습니다."}, status=400)

        existing = None
        if chapteruid:
            resp = supabase.schema("smartdoc").table("chapters").select("*").eq("chapteruid", chapteruid).execute()
            existing = resp.data[0] if resp.data else None


        data = {
            "docid": int(docid),
            "chapternm": chapternm,
            "chapterno": int(chapterno),
            "useyn": useyn,
        }

        # 템플릿 파일 처리
        if chaptertemplate_file:
            # 기존 파일 삭제
            if existing and existing.get("chaptertemplateurl"):
                try:
                    parsed = urlparse(existing["chaptertemplateurl"])
                    storage_prefix = "/storage/v1/object/public/smartdoc/"
                    if storage_prefix in parsed.path:
                        path_to_delete = parsed.path.split(storage_prefix)[-1]
                        supabase.storage.from_("smartdoc").remove([path_to_delete])
                    else:
                        print(f"⚠️ 예상치 못한 chaptertemplateurl 형식: {existing['chaptertemplateurl']}")
                except Exception as e:
                    print("⚠️ 기존 챕터 템플릿 삭제 중 오류:", str(e))

            # 새 파일 업로드
            original_filename = chaptertemplate_file.name
            ext = os.path.splitext(original_filename)[1]
            uuid_filename = f"{uuid.uuid4()}{ext}"
            supabase_path = f"template/chaptertemplate/{uuid_filename}"

            file_bytes = chaptertemplate_file.read()
            supabase.storage.from_("smartdoc").upload(supabase_path, file_bytes, {
                "content-type": chaptertemplate_file.content_type
            })

            public_url = supabase.storage.from_("smartdoc").get_public_url(supabase_path).split("?")[0]

            data["chaptertemplatenm"] = original_filename
            data["chaptertemplateurl"] = public_url

        # 항목 건수 체크
        if existing:
            useyn_orig = supabase.schema("smartdoc").table("chapters").select("useyn").eq("chapteruid", chapteruid).execute().data[0]['useyn']
            # print(f'UseYN: {useyn} / UseYN_Orig: {useyn_orig}')
            if useyn != useyn_orig and useyn_orig == False:
                freedoccnt_resp = supabase.schema("smartdoc").table("configs").select("*").execute()
                freeobjectcnt = freedoccnt_resp.data[0]["freeobjectcnt"]

                doc_data = supabase.schema("smartdoc").rpc("fn_doc_count__r", {'p_docid': docid, 'p_chapteruid': chapteruid}).execute().data
                if doc_data:
                    object_cnt = doc_data[0].get('object_cnt', 0) or 0
                else:
                    object_cnt = 0  # 결과가 없으면 0으로 처리

                chapter_object = supabase.schema("smartdoc").table("objects").select("*").eq("useyn", True).eq("chapteruid", chapteruid).execute().data

                current_object_count = object_cnt + len(chapter_object)

                # print(f'현재 개수: {current_object_count}')

                if current_object_count > freeobjectcnt:
                    return JsonResponse({'success': False, 'message': f'항목 설정 최대 사용량 {freeobjectcnt}을 초과하였습니다.', 'add': '템플릿은 정상 저장되었습니다.'}, status=405)


        if existing:
            resp = supabase.schema("smartdoc").table("chapters").update(data).eq("chapteruid", chapteruid).execute()
            # print('업데이트 완료')
        else:
            data["creator"] = user_id
            resp = supabase.schema("smartdoc").table("chapters").insert(data).execute()
            # print('삽입 완료')

        if not resp.data:
            return JsonResponse({"result": "fail", "message": "DB 저장 후 데이터가 없습니다."}, status=500)

        return JsonResponse({"result": "success", "chapteruid": resp.data[0].get("chapteruid")})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"result": "fail", "message": f"DB 저장 실패: {str(e)}"}, status=500)



def master_chapters_delete(request):
    try:
        data = json.loads(request.body)
        chapteruid = data.get("chapteruid")
        if not chapteruid:
            return JsonResponse({"result": "fail", "message": "chapteruid가 필요합니다."}, status=400)

        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_supabase_client(access_token, refresh_token)

        # 먼저 삭제할 챕터 정보 조회 (템플릿 파일 삭제용)
        resp = supabase.schema("smartdoc").table("chapters").select("*").eq("chapteruid", chapteruid).execute()
        if not resp.data:
            return JsonResponse({"result": "fail", "message": "삭제할 챕터를 찾을 수 없습니다."}, status=404)

        chapter = resp.data[0]

        # 템플릿 파일 삭제
        chaptertemplateurl = chapter.get("chaptertemplateurl")
        if chaptertemplateurl:
            try:
                parsed = urlparse(chaptertemplateurl)
                storage_prefix = "/storage/v1/object/public/smartdoc/"
                if storage_prefix in parsed.path:
                    path_to_delete = parsed.path.split(storage_prefix)[-1]
                    supabase.storage.from_("smartdoc").remove([path_to_delete])
                else:
                    print(f"⚠️ 예상치 못한 chaptertemplateurl 형식: {chaptertemplateurl}")
            except Exception as e:
                print("⚠️ 파일 삭제 중 오류:", str(e))


        # 챕터 레코드 삭제
        delete_resp = supabase.schema("smartdoc").table("chapters").delete().eq("chapteruid", chapteruid).execute()

        if not delete_resp.data:
            return JsonResponse({"result": "fail", "message": "삭제 실패: 데이터가 없습니다."}, status=500)

        return JsonResponse({"result": "success"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"result": "fail", "message": f"삭제 중 오류 발생: {str(e)}"}, status=500)