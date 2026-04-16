import urllib.parse
import urllib.request

from django.http import JsonResponse
from django.shortcuts import render, redirect, resolve_url
from django.contrib import messages

from utilsPrj.supabase_client import get_supabase_client
import json
from datetime import datetime

def docs(request):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    if not user:
        # 로그인 필요 시 홈으로 렌더링
        return render(request, "pages/home.html", {
            "code": "login",
            "text": "로그인이 필요합니다.",
            "page": "master_object",
            "request": request
        })

    user_id = user.get("id")
    
    # 🔹 1️⃣ 문서 목록 조회
    docs_data = supabase.schema("smartdoc").rpc(
        "fn_docs_filtered__r_user_viewer",
        {'p_useruid': user_id}
    ).execute().data or []

    # 🔹 2️⃣ docdesc, createdts 추가
    docids = [doc["docid"] for doc in docs_data if doc.get("docid")]
    if docids:
        docs_details = supabase.schema("smartdoc").table("docs") \
            .select("docid, docdesc, createdts, projectid, sampleyn") \
            .in_("docid", docids).execute().data or []
        doc_map = {d["docid"]: d for d in docs_details}
    else:
        doc_map = {}

    # 🔹 3️⃣ project 정보 가져오기
    project_ids = list({d.get("projectid") for d in docs_details if d.get("projectid")})
    if project_ids:
        projects_data = supabase.schema("smartdoc").table("projects") \
            .select("projectid, projectnm, tenantid, useyn") \
            .in_("projectid", project_ids) \
            .eq("useyn", True) \
            .execute().data or []
        project_map = {p["projectid"]: p for p in projects_data}
    else:
        project_map = {}

    # 🔹 4️⃣ tenant 정보 가져오기
    tenant_ids = list({p["tenantid"] for p in projects_data if p.get("tenantid")})
    if tenant_ids:
        tenants_data = supabase.schema("smartdoc").table("tenants") \
            .select("tenantid, tenantnm") \
            .in_("tenantid", tenant_ids).execute().data or []
        tenant_map = {t["tenantid"]: t["tenantnm"] for t in tenants_data}
    else:
        tenant_map = {}

    # 🔹 5️⃣ 각 문서에 docdesc, createdts, projectnm, tenantnm 추가
    filtered_docs = []
    for doc in docs_data:
        docid = doc.get("docid")
        details = doc_map.get(docid, {})
        projectid = details.get("projectid")
        
        # project_map에 없으면 useyn=False라 제외
        if projectid not in project_map:
            continue

        doc["docdesc"] = details.get("docdesc", "")
        doc["sampleyn"] = details.get("sampleyn", False)
        doc["createdts"] = details.get("createdts", "")
        project = project_map.get(projectid, {})
        doc["projectnm"] = project.get("projectnm", "")
        tenantid = project.get("tenantid")
        doc["tenantnm"] = tenant_map.get(tenantid, "")

        filtered_docs.append(doc)

    docs_data = filtered_docs

    # 🔹 6️⃣ createdts 기준 내림차순 정렬
    docs_data = sorted(
        docs_data,
        key=lambda d: (
            0 if d.get("sampleyn") else 1,                          # sampleyn=True 먼저
            -datetime.fromisoformat(d.get("createdts")).timestamp()  # createdts 최신순
        )
    )

    # 🔹 7️⃣ 결과 반환
    return JsonResponse({"docs": docs_data})

def docs_save(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST 요청만 허용됩니다."})
    
    user = request.session.get("user")
    user_id = user.get("id")
    roleid = user.get("roleid")
    if not user:
        return JsonResponse({"success": False, "error": "로그인이 필요합니다."})
    
    data = json.loads(request.body)
    docid = data.get("docid")
    docnm = data.get("docnm")

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    tenantmanager = 'N'
    projectmanager = 'N'
    
    # docs 테이블 조회
    docs_response = supabase.schema("smartdoc").table("docs").select("*").eq("docid", docid).execute()
    docs_data = docs_response.data
    if not docs_data:
        return JsonResponse({"success": False, "error": "문서를 찾을 수 없습니다."})

    projectid = str(docs_data[0]["projectid"])

    # projectusers 조회
    user_project_response = supabase.schema("smartdoc").table("projectusers").select("*").eq("projectid", projectid).eq("useruid", user_id).execute()
    user_projects = user_project_response.data

    # projects 조회
    projects_response = supabase.schema("smartdoc").table("projects").select("*").eq("projectid", projectid).execute()
    projects = projects_response.data
    tenantid = str(projects[0]["tenantid"])

    # tenantusers 조회
    user_tenant_response = supabase.schema("smartdoc").table("tenantusers").select("*").eq("tenantid", tenantid).eq("useruid", user_id).execute()
    user_tenant = user_tenant_response.data

    # manager 여부 확인
    if user_projects and any(p.get("rolecd") == "M" for p in user_projects):
        projectmanager = 'Y'

    if user_tenant and any(t.get("rolecd") == "M" for t in user_tenant):
        tenantmanager = 'Y'

    # users 테이블에서 useruid가 현재 사용자와 일치하는 레코드의 mydocid 컬럼 업데이트
    supabase.schema("smartdoc").table("users") \
        .update({"mydocid": docid}) \
        .eq("useruid", user_id) \
        .execute()  

    editbuttonyn = 'Y'
    sampledocyn = 'N'

    # docs 테이블에서 docid 기준으로 sampleyn 조회
    selected_doc2 = supabase.schema("smartdoc") \
        .table("docs") \
        .select("sampleyn") \
        .eq("docid", docid) \
        .single() \
        .execute()

    # sampleyn 값 가져오기
    sampleyn = selected_doc2.data.get("sampleyn", False)  # None일 경우 False 처리

    # roleid는 로그인 세션 등에서 가져온다고 가정
    # 예: request.session.user.roleid

    if not sampleyn:
        editbuttonyn = 'Y'
    elif sampleyn is True and roleid == 7:
        editbuttonyn = 'Y'
    else:
        editbuttonyn = 'N'

    if sampleyn is True:
        sampledocyn = 'Y'
    else:
        sampledocyn = 'N'
        
    # 세션 업데이트
    request.session["user"].update({
        "docid": docid,
        "docnm": docnm,
        "tenantid": tenantid,
        "tenantmanager": tenantmanager,
        "projectid": projectid,
        "projectmanager": projectmanager,
        "editbuttonyn" : editbuttonyn,
        "sampledocyn" : sampledocyn
    })

    return JsonResponse({"success": True})

