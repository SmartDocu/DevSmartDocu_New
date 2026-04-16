from django.shortcuts import render, redirect
from django.http import JsonResponse
import json
import os
import uuid
from urllib.parse import urlparse

from utilsPrj.supabase_client import get_supabase_client

#### 에러 로그 삽입 시 필요
from utilsPrj.errorlogs import error_log
import inspect

def master_datas_ex(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    user_id = user.get("id")

    # 1️⃣ Get projects the user can view/manage
    project_list = supabase.schema("smartdoc") \
        .rpc("fn_project_filtered__r_user_manager_viewer", {'p_useruid': user_id}) \
        .execute().data or []
    project_ids = [p["projectid"] for p in project_list]

    # 2️⃣ Get active project details
    projectnm_resp = supabase.schema("smartdoc").table("projects") \
        .select("projectid, projectnm, tenantid, useyn") \
        .in_("projectid", project_ids) \
        .eq("useyn", True) \
        .execute()
    active_projects = projectnm_resp.data or []

    active_project_ids = [p["projectid"] for p in active_projects]

    # 3️⃣ projectid → projectnm mapping
    project_map = {p["projectid"]: p["projectnm"] for p in active_projects}

    # 4️⃣ Get project manager info for active projects
    project_manager = supabase.schema("smartdoc") \
        .rpc("fn_project_filtered__r_user_manager", {'p_useruid': user_id}) \
        .execute().data or []

    # Keep only active projects
    project_manager = [
        {**p, "projectnm": project_map.get(p["projectid"])}
        for p in project_manager
        if p.get("projectid") in active_project_ids
    ]

    # 5️⃣ Get user's roles in projects
    projectusers_resp = supabase.schema("smartdoc").table("projectusers") \
        .select("projectid, rolecd") \
        .in_("projectid", active_project_ids) \
        .eq("useruid", user_id) \
        .execute()

    projectusers_list = projectusers_resp.data or []

    # Add rolecd to project_manager
    for pm in project_manager:
        match = next((p for p in projectusers_list if p['projectid'] == pm['projectid']), None)
        pm['rolecd'] = match['rolecd'] if match else None

    # 6️⃣ Get Datas and DataCols
    Datas_resp = supabase.schema("smartdoc").table("datas") \
        .select("*") \
        .in_("projectid", active_project_ids) \
        .eq("datasourcecd", "ex") \
        .order("connectid") \
        .order("projectid") \
        .order("datanm") \
        .execute()
    Datas = Datas_resp.data or []

    for data in Datas:
        data["projectnm"] = project_map.get(data["projectid"])

    DataCols_resp = supabase.schema("smartdoc").table("datacols") \
        .select("*") \
        .order("orderno") \
        .execute()
    DataCols = DataCols_resp.data or []

    return render(request, 'pages/master_datas_ex.html', {
        'Datas': Datas,
        'DataCols': DataCols,
        'projects': project_manager,
    })


def master_datas_ex_save(request):
    if request.method != "POST":
        return JsonResponse({"result": "fail", "message": "잘못된 요청 방식입니다."}, status=405)

    try:
        user = request.session.get("user")
        user_id = user.get("id")
        
        
        datauid = request.POST.get("datauid")
        # docid = int(request.POST.get("docid"))
        datanm = request.POST.get("datanm")
        excelfile = request.FILES.get("excelfile")
        projectid = request.POST.get("projectid")    

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        record = {
            "projectid": projectid,
            "datanm": datanm,
        }

        existing = None
        if datauid:
            # 기존 데이터 불러오기
            res = supabase.schema("smartdoc").table("datas").select("excelurl").eq("datauid", datauid).execute()

            if res.data:
                existing = res.data[0]

        # 🔁 엑셀 파일 업로드 + 기존 파일 삭제
        if excelfile:

            # ✅ 기존 파일이 있으면 삭제
            if existing and existing.get("excelurl"):
                try:
                    existing_url = existing["excelurl"]
                    parsed = urlparse(existing_url)
                    storage_prefix = "/storage/v1/object/public/smartdoc/"
                    if storage_prefix in parsed.path:
                        path_to_delete = parsed.path.split(storage_prefix)[-1]
                        supabase.storage.from_("smartdoc").remove([path_to_delete])
                        # print(f"DEBUG: 기존 파일 삭제 성공: {path_to_delete}")
                    # else:
                    #     print(f"⚠️ 예상치 못한 excelurl 형식: {existing_url}")
                except Exception as delete_err:
                    # print(f"ERROR: 기존 파일 삭제 실패: {delete_err}")
                    raise delete_err

            # ✅ 새 파일 저장
            original_filename = excelfile.name
            ext = os.path.splitext(original_filename)[1]
            uuid_filename = f"{uuid.uuid4()}{ext}"
            supabase_path = f"source/{projectid}/{uuid_filename}"

            file_bytes = excelfile.read()

            supabase.storage.from_("smartdoc").upload(supabase_path, file_bytes, {
                "content-type": excelfile.content_type
            })
            public_url = supabase.storage.from_("smartdoc").get_public_url(supabase_path).split("?")[0]
            # print(f"DEBUG: 파일 업로드 성공: {public_url}")
            record["excelnm"] = original_filename
            record["excelurl"] = public_url

        if datauid:
            # 기존 데이터 수정
            supabase.schema("smartdoc").table("datas").update(record).eq("datauid", datauid).execute()
        else:
            # 새 데이터 저장
            # user = request.session.get("user")
            # user_id = user.get("id")
            record["creator"] = user_id
            record["datasourcecd"] = "ex"
            insert_res = supabase.schema("smartdoc").table("datas").insert(record).execute()

            new_data = insert_res.data[0] if insert_res.data else None
            datauid = new_data.get("datauid") if new_data else None
        
        return JsonResponse({"result": "success", "datauid": datauid})

    except Exception as e:
        # --------------------------
        #  로그 저장
        # --------------------------
        try:
            # (request, errormessage, errorobject, creator, remark1, remark2, remark3)
            error_log(request,
                      e, 
                      inspect.currentframe().f_code.co_name, 
                      request.session.get("user", {}).get("id", None),
                      request.POST.get("docid"),
                      request.POST.get("datauid"),
                      "EXCEL 저장 중 오류",
                    )

        except Exception as log_err:
            # pass 삭제 ➜ 최소한 서버에 출력 + 다시 raise
            # print("🔥 로그 저장 중 오류:", log_err)
            raise log_err

        return JsonResponse({"result": "fail", "message": "서버 오류가 발생했습니다."}, status=500)

def master_datas_ex_delete(request):
    try:
        data = json.loads(request.body)
        datauid = data.get("datauid")
        if not datauid:
            return JsonResponse({"result": "fail", "message": "datauid가 필요합니다."}, status=400)

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        # 삭제
        resp = supabase.schema("smartdoc").table("datacols").delete().eq("datauid", datauid).execute()

        # 삭제
        resp = supabase.schema("smartdoc").table("datas").delete().eq("datauid", datauid).execute()

        # 성공 확인
        if not resp.data:
            return JsonResponse({"result": "fail", "message": "삭제 실패"}, status=500)
        
        return JsonResponse({"result": "success"})

    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)
    