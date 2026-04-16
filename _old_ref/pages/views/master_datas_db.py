from django.shortcuts import render, redirect
from django.http import JsonResponse
import json

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.process_data import process_data
import string

def master_datas_db(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    user_id = user.get("id")
    tenantid = user.get("tenantid")

    project_list = supabase.schema("smartdoc") \
        .rpc("fn_project_filtered__r_user", {'p_useruid': user_id}) \
        .execute().data or []
    project_ids = [p["projectid"] for p in project_list]

    # useyn=True인 dbconnectors에서 connectid, connectnm 모두 가져오기
    dbconnectors_resp = supabase.schema("smartdoc").table("dbconnectors") \
        .select("connectid, connectnm") \
        .eq("useyn", True) \
        .eq("tenantid",tenantid) \
        .execute()
    
    projectnm_resp = supabase.schema("smartdoc").table("projects") \
        .select("projectid, projectnm, useyn") \
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

    Datas_resp = (
        supabase
        .schema("smartdoc")
        .table("datas")
        .select("*")
        .in_("projectid", active_project_ids)
        .eq("datasourcecd", "db")
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

    if dbconnectors_resp.data:
        connectid_list = dbconnectors_resp.data
    else:
        connectid_list = []
            
    # connectid_list에서 매핑 딕셔너리 생성
    connectid_map = {item["connectid"]: item["connectnm"] for item in connectid_list}

    # Datas에 connectnm 추가
    for data in Datas:
        cid = data.get("connectid")
        data["connectnm"] = connectid_map.get(cid, "")  # 없는 경우 빈 문자열

    return render(request, 'pages/master_datas_db.html', {
        'Datas': Datas,
        'DataCols': DataCols,
        'connectid_list': connectid_list,
        'projects': projects,
    })


def master_datas_db_save(request):
    if request.method != "POST":
        return JsonResponse({"result": "fail", "message": "잘못된 요청 방식입니다."}, status=405)

    try:
        data = json.loads(request.body)

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        datauid = data.get("datauid")
        if datauid and str(datauid).strip() != "":
            # int 변환 하지 말고 UUID 문자열 그대로 사용
            datauid = str(datauid)
        else:
            datauid = None

        user = request.session.get("user")
        user_id = user.get("id")
        
        # docid = int(data.get("docid"))
        datanm = data.get("datanm")
        connectid = data.get("connectid")
        query = data.get("query")
        projectid = data.get("projectid")

        record = {
            "projectid": projectid,
            "datanm": datanm,
            "connectid": connectid,
            "query": query,
        }

        if datauid:
            supabase.schema("smartdoc").table("datas").update(record).eq("datauid", datauid).execute()
        else:
            user = request.session.get("user")
            user_id = user.get("id")
            record["creator"] = user_id
            record["datasourcecd"] = "db"
        
            response = supabase.schema("smartdoc").table("datas").insert(record).execute()
            datauid = response.data[0]["datauid"]

        return JsonResponse({"result": "success", "datauid": datauid})
    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)


def master_datas_db_delete(request):
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
    
def master_datacols_create(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST 요청만 허용됩니다."}, status=405)

    try:
        data = json.loads(request.body)
        datauid = data.get("datauid")
        projectid = data.get("projectid")    # jeff 20260107 1753
        request.projectid = projectid

        # print("datauid", datauid)
        user = request.session.get("user")
        user_id = user.get("id")

        if not datauid:
            return JsonResponse({"error": "datauid가 필요합니다."}, status=400)

        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        # 데이터 존재 확인
        Datas_resp = supabase.schema("smartdoc").table("datas").select("*").eq("datauid", datauid).execute()
        Datas = Datas_resp.data or []

        if len(Datas) == 0:
            return JsonResponse({"error": "해당 datauid 데이터가 없습니다."}, status=404)

        # 쿼리 실행해서 컬럼명 가져오기
        df = process_data(request, datauid)

        if df.empty:
            raise ValueError("쿼리 실행 결과가 올바르지 않습니다.")

        column_names = df.columns.tolist()

        if not column_names:
            raise ValueError("컬럼명이 비어 있습니다.")
        
        # ✅ 1. 빈 컬럼명 채우기 (A, B, C, ...)
        if any(col.strip() == "" for col in column_names):
            alphabet = list(string.ascii_uppercase)
            new_names = []
            empty_idx = 0
            for col in column_names:
                if col.strip() == "":
                    new_names.append(alphabet[empty_idx])
                    empty_idx += 1
                else:
                    new_names.append(col)
            df.columns = new_names
            column_names = new_names

        # ✅ 2. 중복 컬럼명 처리 (_1, _2, ...)
        seen = {}
        new_names = []
        for col in column_names:
            if col in seen:
                seen[col] += 1
                new_name = f"{col}_{seen[col]}"
            else:
                seen[col] = 0
                new_name = col
            new_names.append(new_name)
        df.columns = new_names
        column_names = new_names

        # 기존 컬럼 삭제
        supabase.schema("smartdoc").table("datacols").delete().eq("datauid", datauid).execute()

        # 새 컬럼 Insert
        new_records = []

        for idx, col in enumerate(column_names, start=1):   # orderno = 1부터 시작
            new_records.append({
                "datauid": datauid,
                "querycolnm": col,
                "dispcolnm": col,
                "creator": user_id,  # 필요시 변경 가능
                "orderno": idx       
            })

        if new_records:
            supabase.schema("smartdoc").table("datacols").insert(new_records).execute()
        
        return JsonResponse({"result": "success", "columns": column_names})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def master_datacols_save(request):
    if request.method != "POST":
        return JsonResponse({"result": "fail", "message": "POST 요청만 허용됩니다."}, status=405)

    try:
        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        data = json.loads(request.body)  # data is a list of dicts

        if not isinstance(data, list) or not data:
            return JsonResponse({"result": "fail", "message": "컬럼 리스트가 필요합니다."}, status=400)

        # 모든 item이 동일한 datauid를 갖는지 확인 (보통 하나만 있으면 됨)
        datauids = set(col.get("datauid") for col in data)
        if len(datauids) != 1:
            return JsonResponse({"result": "fail", "message": "모든 컬럼의 datauid가 동일해야 합니다."}, status=400)

        datauid = datauids.pop()

        # 기존 데이터 삭제
        del_res = (
            supabase
            .schema("smartdoc")
            .table("datacols")
            .delete()
            .eq("datauid", datauid)
            .execute()
        )

        user = request.session.get("user")
        user_id = user.get("id")

        # 새 데이터 삽입
        insert_data = []

        for idx, col in enumerate(data, start=1):   # orderno = 1부터 시작
            # paramnm_value = col.get("paramnm")  # 값이 없으면 None
            # if paramnm_value == "":
            #     paramnm_value = None  # 빈 문자열이면 NULL 처리

            insert_data.append({
                "datauid": datauid,
                "querycolnm": col.get("querycolnm", ""),
                "dispcolnm": col.get("dispcolnm", ""),
                "datatypecd": col.get("datatypecd", ""),
                "measureyn": col.get("measureyn", False),
                "creator": user_id,
                "orderno": idx  
            })

        ins_res = (
            supabase
            .schema("smartdoc")
            .table("datacols")
            .insert(insert_data)
            .execute()
        )


        if not ins_res.data:
            return JsonResponse({"result": "fail", "message": "컬럼 삽입에 실패했습니다."}, status=500)

        return JsonResponse({"result": "success"})

    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)

def master_datacols(request):
    """
    특정 datauid에 대한 컬럼 정보를 Supabase에서 가져오는 API
    GET /master/datacols_get/?datauid=xxx
    """
    datauid = request.GET.get("datauid")
    if not datauid:
        return JsonResponse({"result": "fail", "message": "datauid 파라미터가 필요합니다."}, status=400)

    try:
        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        datacols_resp = (
            supabase
            .schema("smartdoc")
            .table("datacols")
            .select("*")
            .eq("datauid", datauid)
            .order("orderno")
            .execute()
        )

        data = datacols_resp.data if datacols_resp.data else []

        return JsonResponse({"result": "success", "columns": data})

    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)