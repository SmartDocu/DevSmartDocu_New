from django.shortcuts import render
from django.http import JsonResponse
import json

import os
import uuid
from types import SimpleNamespace
from urllib.parse import urlparse

from utilsPrj.supabase_client import get_supabase_client
from .req_doc_setting import delete_gendoc
from .login import set_session

def master_docs(request):
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

    project_list = supabase.schema("smartdoc").rpc("fn_project_filtered__r_user_manager_viewer", {'p_useruid': user_id}).execute().data or []
    project_manager = supabase.schema("smartdoc").rpc("fn_project_filtered__r_user_manager", {'p_useruid': user_id}).execute().data or []

    docids_result = supabase.schema("smartdoc").rpc("fn_docs_filtered__r_user_manager_viewer", {'p_useruid': user_id}).execute().data or []
    docid_list = [item["docid"] for item in docids_result]


    projects_data = supabase.schema("smartdoc").table("projects") \
        .select("projectid, projectnm, tenantid, useyn") \
        .eq("useyn", True) \
        .execute().data or []

    # ✅ useyn=True 인 projectid만 Set으로
    active_project_ids = {p["projectid"] for p in projects_data}

    project_list = [
        p for p in project_list
        if p.get("projectid") in active_project_ids
    ]

    project_manager = [
        p for p in project_manager
        if p.get("projectid") in active_project_ids
    ]


    docs = []
    if docid_list:
        docs_resp = supabase.schema("smartdoc").table("docs") \
            .select("*") \
            .in_("docid", docid_list) \
            .order("projectid") \
            .order("docnm") \
            .execute()
        docs = docs_resp.data if docs_resp.data else []

    # projectnm 추가
    project_map = {p['projectid']: p['projectnm'] for p in project_list}

    valid_project_ids = {p["projectid"] for p in project_list}

    filtered_docs = []
    for doc in docs:
        projectid = doc.get("projectid")

        # ❌ project_list에 없으면 제외
        if projectid not in valid_project_ids:
            continue

        # ✅ 있는 경우만 projectnm 추가
        doc["projectnm"] = project_map.get(projectid)
        filtered_docs.append(doc)

    docs = filtered_docs
        
    params_resp = supabase.schema("smartdoc").table("dataparams") \
        .select("*") \
        .order("orderno", desc=False) \
        .execute()
    params = params_resp.data if params_resp.data else []

    user_roleid = user.get("roleid")

    for doc in docs:
        sampleyn = doc.get("sampleyn", False)  # None이면 False 처리

        if not sampleyn:
            doc["editbuttonyn"] = "Y"
        elif sampleyn is True and user_roleid == 7:
            doc["editbuttonyn"] = "Y"
        else:
            doc["editbuttonyn"] = "N"

    return render(request, 'pages/master_docs.html', {
        'user' : user,
        'docs': docs,
        'project_list': project_manager,
        'params': params,
    })

def master_docs_save(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)
    
    if request.method != "POST":
        return JsonResponse({"result": "fail", "message": "잘못된 요청 방식입니다."}, status=405)

    data = request.POST
    files = request.FILES

    projectid = data.get("projectid")
    docid = data.get("docid")
    docnm = data.get("docnm")
    docdesc = data.get("docdesc")
    template_file = files.get("templatefile")

    user = request.session.get("user")
    user_id = user.get("id")
    billingmodelcd = user.get("billingmodelcd")

    projectid_int = int(data.get("projectid"))

    project_check = supabase.schema("smartdoc").rpc("fn_project_filtered__r_user_manager", {'p_useruid': user_id}).execute().data or []

    # project_check 안에 projectid 가 있는지 확인
    allowed_projectids = [row.get("projectid") for row in project_check]

    if projectid_int not in allowed_projectids:
        return JsonResponse({
            "result": "fail",
            "message": "해당 Project는 편집 불가능한 Project 입니다."
        }, status=400)

    if billingmodelcd  == "Fr":
        freedoccnt_resp = supabase.schema("smartdoc").table("configs").select("*").execute()
        freedoccnt = freedoccnt_resp.data[0]["freedoccnt"]

        frdoc_resp = supabase.schema("smartdoc").table("docs").select("*", count="exact").eq("creator", user_id).execute()
        current_doc_count = frdoc_resp.count or 0

        if current_doc_count >= freedoccnt:
            return JsonResponse({"result": "fail", "message": "이미 사용량을 초과하였습니다."}, status=400)

    # 기존 문서 확인
    existing = None
    if docid:
        try:
            docid_int = int(docid)
        except ValueError:
            return JsonResponse({"result": "fail", "message": "잘못된 docid입니다."}, status=400)

        existing_resp = supabase.schema("smartdoc").table("docs").select("*").eq("docid", docid_int).execute()
        existing = existing_resp.data[0] if existing_resp.data else None
    else:
        docid_int = None

    # =========================
    # docnm 중복 확인
    # =========================
    duplicate_resp = supabase.schema("smartdoc").table("docs").select("*").eq("docnm", docnm).execute()
    # docid가 있을 경우, 자기 자신 제외
    duplicates = [
        d for d in (duplicate_resp.data or [])
        if docid_int is None or d["docid"] != docid_int
    ]

    if duplicates:
        return JsonResponse({"result": "fail", "message": f"이미 동일한 이름({docnm})의 문서가 존재합니다."}, status=400)

    # 저장할 필드 구성
    record = {
        "projectid": projectid,
        "docnm": docnm,
        "docdesc": docdesc,
    }

    try:
        # 템플릿 파일이 존재하는 경우
        if template_file:
            # 기존 파일 삭제
            if existing and existing.get("basetemplateurl"):
                existing_url = existing["basetemplateurl"]

                try:
                    parsed = urlparse(existing_url)
                    storage_prefix = "/storage/v1/object/public/smartdoc/"
                    if storage_prefix in parsed.path:
                        path_to_delete = parsed.path.split(storage_prefix)[-1]
                        supabase.storage.from_("smartdoc").remove([path_to_delete])
                    else:
                        print(f"⚠️ 예상치 못한 basetemplateurl 형식: {existing_url}")
                except Exception as e:
                    print("⚠️ 기존 템플릿 삭제 중 오류:", str(e))

            # 새 파일 저장
            original_filename = template_file.name
            ext = os.path.splitext(original_filename)[1]
            uuid_filename = f"{uuid.uuid4()}{ext}"
            supabase_path = f"template/basetemplate/{uuid_filename}"

            # 업로드
            file_bytes = template_file.read()
            supabase.storage.from_("smartdoc").upload(supabase_path, file_bytes, {
                "content-type": template_file.content_type
            })
            # 파일 URL 생성
            public_url = supabase.storage.from_("smartdoc").get_public_url(supabase_path).split("?")[0]

            # DB 저장 필드 추가
            record["basetemplatenm"] = original_filename
            record["basetemplateurl"] = public_url

        if existing:
            supabase.schema("smartdoc").table("docs").update(record).eq("docid", docid_int).execute()
            # return JsonResponse({"result": "success", "docid": docid_int})
        else:
            record["creator"] = user_id
            
            insert_res = supabase.schema("smartdoc").table("docs").insert(record).execute()
            docid_int = insert_res.data[0]["docid"] if insert_res.data else None
            # return JsonResponse({"result": "success", "docid": new_docid})

        # ✅ 본인이 속한 projectid 가져오기
        # project_res = supabase.schema("smartdoc").table("projectusers").select("projectid").eq("useruid", user_id).execute()
        # project_ids = [g["projectid"] for g in project_res.data] if project_res.data else []

        # ✅ projectdocs 테이블에 insert
        # for project_id in project_ids:
        #     supabase.schema("smartdoc").table("projectdocs").insert({
        #         "projectid": project_id,
        #         "docid": docid_int,
        #         "useyn": True,
        #         "creator":user_id
        #     }).execute()

        return JsonResponse({"result": "success", "docid": docid_int})
                  
    except Exception as e:
        return JsonResponse({"result": "fail", "message": f"DB 저장 실패: {str(e)}"}, status=500)

def master_docs_delete(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST 요청만 허용됩니다."})

    try:
        data = json.loads(request.body)
        docid = data.get("docid")
        if not docid:
            return JsonResponse({"success": False, "error": "docid가 없습니다."})

        # 1) 삭제할 문서 정보 조회 (basetemplateurl 확인용)
        select_resp = supabase.schema("smartdoc").table("docs").select("*").eq("docid", docid).execute()
        doc = select_resp.data[0] if select_resp.data else None

        if not doc:
            return JsonResponse({"success": False, "error": "문서를 찾을 수 없습니다."})

        base_template_url = doc.get("basetemplateurl")
        if base_template_url:
            try:
                parsed = urlparse(base_template_url)
                storage_prefix = "/storage/v1/object/public/smartdoc/"
                if storage_prefix in parsed.path:
                    path_to_delete = parsed.path.split(storage_prefix)[-1]
                    supabase.storage.from_("smartdoc").remove([path_to_delete])
                else:
                    print(f"⚠️ 예상치 못한 basetemplateurl 형식: {base_template_url}")
            except Exception as e:
                print("⚠️ 파일 삭제 중 오류:", str(e))


        user = request.session.get("user")
        user_id = user.get("id")
        
        # 2) docs 테이블 및 하위 영역에서 문서 삭제
        gendocs = supabase.schema("smartdoc").table("gendocs").select("*").eq("docid", docid).execute().data
        gendoc_uids = [gd["gendocuid"] for gd in gendocs]

        for gdu in gendoc_uids:
            gendocui = delete_gendoc(request, gdu)

        delete_doc_resp = supabase.schema("smartdoc").table("docs").delete().eq("docid", docid).execute()
        supabase.schema("smartdoc").table("dataparams").delete().eq("docid", docid).execute()

        if not delete_doc_resp.data:
            return JsonResponse({"success": False, "error": "문서 삭제 실패: 삭제된 데이터가 없습니다."})

        # 정상 동작 시 삭제된 문서를 잡고 있을 경우 문서 교체 해야 함.
        send_user = DictObj(request.session.get("user"))

        session_docid = send_user.docid

        if int(session_docid) == int(docid):
            set_session(request, send_user, 'doc_setting')

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

class DictObj:
    def __init__(self, data):
        self.__dict__.update(data)

def master_params_save(request):
    if request.method == "POST":
        try:
            supabase = get_supabase_client(
                request.session.get("access_token"), 
                request.session.get("refresh_token")
            )

            data = json.loads(request.body)
            paramuid = data.get("paramuid")
            paramnm = data.get("paramnm")
            samplevalue = data.get("samplevalue")
            operator = data.get("operator")
            orderno = data.get("orderno")
            docid = data.get("docid")
            datauid = data.get("datauid")
            keycolnm = data.get("dataset_key") or None
            nmcolnm = data.get("dataset_name") or None
            ordercolnm = data.get("dataset_order") or None

            if paramuid in ("", None, "None"):
                paramuid = None

            if datauid in ("", None):
                datauid = None

            if datauid:
                keycolnm_resp = supabase.schema("smartdoc").table("datacols").select("*").eq("datauid", datauid).eq("querycolnm", keycolnm).execute()
                keycoldatatypecd = keycolnm_resp.data[0]["datatypecd"]
            else:
                keycoldatatypecd = None

            # orderno가 빈 문자열이거나 None일 경우 0으로 처리
            orderno = data.get("orderno")
            if orderno == "" or orderno is None:
                orderno = None
            else:
                orderno = int(orderno)

            record = {
                "paramnm": paramnm,
                "samplevalue" : samplevalue,
                "operator" : operator,
                "orderno": orderno,
                "docid": int(docid),
                "datauid": datauid,
                "keycolnm": keycolnm,
                "keycoldatatypecd" : keycoldatatypecd,
                "nmcolnm": nmcolnm,
                "ordercolnm": ordercolnm,
            }

            if paramuid:
                supabase.schema("smartdoc").table("dataparams").update(record).eq("paramuid", paramuid).execute()
            else:
                user = request.session.get("user")
                user_id = user.get("id")
                record["creator"] = user_id

                supabase.schema("smartdoc").table("dataparams").insert(record).execute()

            return JsonResponse({"result": "success"})
        except Exception as e:
            return JsonResponse({"result": "fail", "message": str(e)})

def master_params_delete(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            paramuid = data.get("paramuid")
            if not paramuid:
                return JsonResponse({"success": False, "error": "paramuid가 없습니다."})

            supabase = get_supabase_client(
                request.session.get("access_token"), 
                request.session.get("refresh_token")
            )
            supabase.schema("smartdoc").table("dataparams").delete().eq("paramuid", paramuid).execute()
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


def master_params_datasets(request):
    if request.method == "POST":
        supabase = get_supabase_client(
            request.session.get("access_token"), 
            request.session.get("refresh_token")
        )

        body = json.loads(request.body)
        docid = body.get("docid")

        docs = supabase.schema("smartdoc").table("docs") \
            .select("*") .eq("docid", docid).execute().data or []

        if docs:
            projectid = str(docs[0]["projectid"])

        result = supabase.schema("smartdoc").table("datas") \
            .select("*") \
            .eq("projectid", projectid) \
            .order("datanm") \
            .execute()

        # Supabase 리턴 데이터는 result.data 형태
        datas = result.data  
        # print("datas", datas)
        return JsonResponse({"datas": datas})
    
    return JsonResponse({"datas": []})

def master_params_dataset_cols(request):
    if request.method == "GET":
        datauid = request.GET.get("datauid")
        if not datauid:
            return JsonResponse({"datacols": []})

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        # smartdoc.datacols 테이블에서 datauid 기준으로 컬럼 조회
        result = supabase.schema("smartdoc").table("datacols") \
            .select("*") \
            .eq("datauid", datauid) \
            .execute()

        datacols = result.data if result.data else []

        return JsonResponse({"datacols": datacols})

    return JsonResponse({"datacols": []})
