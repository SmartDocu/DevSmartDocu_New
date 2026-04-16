from django.shortcuts import render
from django.http import JsonResponse
from utilsPrj.supabase_client import get_supabase_client
import json

def master_doc_params(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    docid = request.GET.get("docid")
    if not docid:
        return JsonResponse({"result": "fail", "message": "docid 없음"})

    # 1️⃣ 문서
    doc = supabase.schema("smartdoc").table("docs") \
        .select("*") \
        .eq("docid", int(docid)) \
        .single() \
        .execute().data

    projectid = doc["projectid"]

    # 2️⃣ 데이터 목록 (좌측)
    datas = supabase.schema("smartdoc").table("datas") \
        .select("datauid, datanm, datasourcecd") \
        .eq("projectid", projectid) \
        .order("datanm") \
        .execute().data or []

    # 3️⃣ datacols 전체
    datacols = supabase.schema("smartdoc").table("datacols") \
        .select("*") \
        .order("orderno") \
        .execute().data or []

    # 4️⃣ datauid 기준 grouping
    col_map = {}
    for col in datacols:
        col_map.setdefault(col["datauid"], []).append(col)

    # 5️⃣ dataparams 조회 및 grouping
    dataparams = supabase.schema("smartdoc").table("dataparams") \
        .select("*") \
        .eq("docid", int(docid)) \
        .order("paramnm") \
        .execute().data or []
    
    dataparamdtls = supabase.schema("smartdoc").table("dataparamdtls") \
        .select("*") \
        .eq("docid", int(docid)) \
        .execute().data or []
    
    # ✅ 초기값 맵 생성 (datauid + querycolnm -> paramuid)
    dataparam_map = {}
    for d in dataparamdtls:
        datauid = d["datauid"]
        colname = d["querycolnm"]
        dataparam_map.setdefault(datauid, {})[colname] = d["paramuid"]

    return render(request, "pages/master_doc_params.html", {
        "doc": doc,
        "docnm": doc["docnm"],
        "datas": datas,
        "datacols": col_map,         # { datauid: [cols...] }
        "dataparams": dataparams, # { datauid: [params...] }
        "dataparamdtls" : dataparamdtls,
        "dataparam_map": dataparam_map  # 추가
    })


def master_doc_params_save(request):
    if request.method != "POST":
        return JsonResponse({"result": "fail", "message": "POST 요청만 허용됩니다."}, status=405)

    try:
        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        data = json.loads(request.body)  # data = { "records": [...] }

        records = data.get("records", [])
        if not isinstance(records, list) or not records:
            return JsonResponse({"result": "fail", "message": "저장할 데이터가 필요합니다."}, status=400)

        # 로그인 사용자
        user = request.session.get("user")
        user_id = user.get("id") if user else None

        # 기존 데이터 삭제(선택적으로, datauid 기준)
        datauids = list({r["datauid"] for r in records})
        if datauids:
            supabase.schema("smartdoc").table("dataparamdtls") \
                .delete().in_("datauid", datauids).execute()

        # 새로운 데이터 삽입
        insert_data = []
        for r in records:
            insert_data.append({
                "paramuid": r.get("paramuid"),
                "datauid": r.get("datauid"),
                "querycolnm": r.get("querycolnm"),
                "docid": r.get("docid"),
                "creator": user_id
            })

        ins_res = supabase.schema("smartdoc").table("dataparamdtls") \
            .insert(insert_data).execute()
        
        if not ins_res.data:
            return JsonResponse({"result": "fail", "message": "컬럼 삽입에 실패했습니다."}, status=500)

        return JsonResponse({"result": "success"})

    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)
    
    
def master_doc_params_delete(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST 요청만 허용됩니다."}, status=405)

    try:
        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        data = json.loads(request.body)
        datauids = data.get("datauids", [])
        if not datauids:
            return JsonResponse({"success": False, "error": "삭제할 datauid가 필요합니다."}, status=400)

        del_res = supabase.schema("smartdoc").table("dataparamdtls") \
            .delete().in_("datauid", datauids).execute()

        # 성공 확인
        if not del_res.data:
            return JsonResponse({"result": "fail", "message": "삭제 실패"}, status=500)
        
        return JsonResponse({"result": "success"})

    except Exception as e:
        return JsonResponse({"result": "fail", "message": str(e)}, status=500)
    

