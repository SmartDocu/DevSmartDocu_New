from django.shortcuts import render, redirect
from django.http import JsonResponse
import json

from utilsPrj.supabase_client import get_supabase_client

def master_datas_ai(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    # docid = request.GET.get('docid')
    user = request.session.get("user")
    user_id = user.get("id")
    
    project_list = supabase.schema("smartdoc") \
        .rpc("fn_project_filtered__r_user_manager_viewer", {'p_useruid': user_id}) \
        .execute().data or []
    project_ids = [p["projectid"] for p in project_list]
    
    
    projectnm_resp = supabase.schema("smartdoc").table("projects") \
        .select("projectid, projectnm") \
        .in_("projectid", project_ids) \
        .eq("useyn", True) \
        .execute()
        

    active_projects = projectnm_resp.data or []

    # ✅ useyn=True 인 projectid만 추출
    active_project_ids = [p["projectid"] for p in active_projects]

    # projectid → projectnm 매핑
    project_map = {
        p["projectid"]: p["projectnm"]
        for p in active_projects
    }

    projectusers_resp = (
        supabase
        .schema("smartdoc")
        .table("projectusers")
        .select("*")
        .in_("projectid", active_project_ids)
        .eq("useruid",user_id)
        .execute()
    )

    Datas_resp = (
        supabase
        .schema("smartdoc")
        .table("datas")
        .select("*")
        .in_("projectid", active_project_ids)
        .eq("datasourcecd", "df")
        .order("connectid")
        .order("projectid") 
        .order("datanm")
        .execute()
    )

    Datas = Datas_resp.data if Datas_resp.data else []

    DataCols_resp = supabase.schema("smartdoc").table("datacols").select("*").order("orderno").execute()
    DataCols = DataCols_resp.data if DataCols_resp.data else []

    # Datas에 projectnm 추가
    for data in Datas:
        data["projectnm"] = project_map.get(data["projectid"])

    projects = [
        {
            "projectid": pid,
            "projectnm": project_map.get(pid)
        }
        for pid in active_project_ids
    ]

    projectusers_list = projectusers_resp.data or []

    for project in projects:
        match = next((p for p in projectusers_list if p['projectid'] == project['projectid']), None)
        project['rolecd'] = match['rolecd'] if match else None
        
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


    # Add rolecd to project_manager
    for pm in project_manager:
        match = next((p for p in projectusers_list if p['projectid'] == pm['projectid']), None)
        pm['rolecd'] = match['rolecd'] if match else None

    # 📌 연결된 소스 데이터 (db / excel 등)
    sourcedatauid_list_raw = []

    dbconnectors_query = (
        supabase.schema("smartdoc").table("datas")
        .select("datauid, datanm, datasourcecd, projectid")
        .in_("projectid", active_project_ids)
        .neq("datasourcecd", "df")
        .order("connectid")
        .order("datanm")
    )
    dbconnectors_resp = dbconnectors_query.execute()
    sourcedatauid_list_raw = dbconnectors_resp.data or []

    # 📌 표시용 이름 목록 생성
    sourcedatauid_list = [
        {"sourcedatauid": item["datauid"], "sourcedatanm": item["datanm"], "sourceprojectid": item["projectid"]}
        for item in sourcedatauid_list_raw
    ]

    return render(request, 'pages/master_datas_ai.html', {
        # 'user' : user,
        'Datas': Datas,
        'DataCols': DataCols,
        'projects': project_manager,
        'sourcedatauid_list': sourcedatauid_list,
    })



def master_datas_ai_save(request):
    if request.method != "POST":
        return JsonResponse({"result": "fail", "message": "잘못된 요청 방식입니다."}, status=405)

    try:
        data = json.loads(request.body)

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        datauid = data.get("datauid")
        projectid = data.get("projectid")    # jeff 20260107 1505
        if datauid and str(datauid).strip() != "":
            # int 변환 하지 말고 UUID 문자열 그대로 사용
            datauid = str(datauid)
        else:
            datauid = None

        user = request.session.get("user")
        # user_id = user.get("id")
        # docid = user.get("docid") 
        # docid = int(data.get("docid"))
        datanm = data.get("datanm")
        sourcedatauid = data.get("sourcedatauid")
        gensentence = data.get("sentence")
        # projectid = data.get("projectid")   

        record = {
            "projectid": projectid,
            "datanm": datanm,
            "sourcedatauid": sourcedatauid,
            "gensentence": gensentence,
        }

        if datauid:
            supabase.schema("smartdoc").table("datas").update(record).eq("datauid", datauid).execute()
        else:
            user = request.session.get("user")
            user_id = user.get("id")
            record["creator"] = user_id
            record["datasourcecd"] = "df"
        
            new_data = supabase.schema("smartdoc").table("datas").insert(record).execute()
            # Supabase APIResponse 구조 확인 후 접근
            if new_data.data and len(new_data.data) > 0:
                datauid = new_data.data[0].get("datauid")
            else:
                datauid = None

        return JsonResponse({"result": "success", "datauid": datauid})

    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)

def master_datas_ai_delete(request):
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
    