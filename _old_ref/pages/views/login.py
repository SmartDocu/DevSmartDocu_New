import urllib.parse
import urllib.request

from django.http import JsonResponse
from django.shortcuts import render, redirect, resolve_url
from django.contrib import messages

from utilsPrj.supabase_client import get_supabase_client
import json

def is_url_valid(url):
    """Check if a given signed URL is still valid (e.g. not expired)."""
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request) as response:
            return response.status == 200
    except Exception as e:
        return False


# jeff 20250924 1255
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def login_view(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        next_url = request.GET.get("next") or request.POST.get("next") or resolve_url('home')

        try:
            auth_response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            user = auth_response.user
            session = auth_response.session
            user_id = user.id

            request.session["access_token"] = session.access_token
            request.session["refresh_token"] = session.refresh_token

            user_projects = set_session(request, user, 'login')

            # ✅ Step 8. 응답 처리
            if not user_projects:
                return JsonResponse({
                    'result': 'success',
                    'message': '로그인 성공. 단, 속한 프로젝트가 없습니다. 관리자에 연락바랍니다.',
                    'next': next_url,
                })
            else:
                return JsonResponse({
                    'result': 'success',
                    'message': '로그인 성공',
                    'next': next_url,
                })

        except Exception as e:
            messages.error(request, f"로그인 실패: {str(e)}")
            return JsonResponse({'result': 'Failed', 'message': f'로그인 실패: {str(e)}'})

    next_url = request.GET.get("next", "")
    return JsonResponse({'result': 'success', 'message': '로그인 성공.'})


# 타 영역에서도 사용할 가능성이 있으므로 모듈화 처리
def set_session(request, user, type):
    # print(f'session 설정 진입: {type}')
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    try:
        user_id = user.id

        # ✅ Step 1. 사용자 roleid, mydocid 조회
        user_data_response = supabase.schema("smartdoc").table("users") \
            .select("roleid, mydocid, billingmodelcd") \
            .eq("useruid", user_id) \
            .single() \
            .execute()

        roleid = None
        billingmodelcd = None
        tenantmanager = 'N'
        projectmanager = 'N'
        mydocid = None
        editbuttonyn = 'Y'
        sampledocyn = 'N'
        tenanticonurl = None

        if user_data_response.data:
            roleid = user_data_response.data.get("roleid")
            mydocid = user_data_response.data.get("mydocid")
            billingmodelcd = user_data_response.data.get("billingmodelcd")

        # ✅ Step 2. RPC로 접근 가능한 문서 목록 조회
        docs = supabase.schema("smartdoc").rpc(
            "fn_docs_filtered__r_user_viewer",
            {'p_useruid': user_id}
        ).execute().data or []

        # docs 비어있을 경우 대비
        docid = docnm = None
        
        if docs:
            doc_ids = [d["docid"] for d in docs if "docid" in d]

            # ✅ Step 3. mydocid가 접근 가능한 문서 목록 안에 있을 경우
            if mydocid and mydocid in doc_ids:
                docid = str(mydocid)
                selected_doc = supabase.schema("smartdoc") \
                    .table("docs") \
                    .select("docnm, projectid, createdts") \
                    .eq("docid", docid) \
                    .single() \
                    .execute()
                docnm = selected_doc.data.get("docnm") if selected_doc.data else None
                projectid = selected_doc.data.get("projectid") if selected_doc.data else None

            # ✅ Step 4. 없을 경우 최신 문서 기준으로 선택 + mydocid 갱신
            else:
                docs_temp_response = supabase.schema("smartdoc") \
                    .table("docs") \
                    .select("docid, docnm, projectid, createdts") \
                    .in_("docid", doc_ids) \
                    .execute()

                docs_temp = docs_temp_response.data or []
                if docs_temp:
                    latest_doc = sorted(docs_temp, key=lambda d: d["createdts"], reverse=True)[0]
                    docid = str(latest_doc["docid"])
                    docnm = str(latest_doc["docnm"])
                    projectid = str(latest_doc["projectid"])

                    # 🔄 mydocid 업데이트
                    supabase.schema("smartdoc").table("users") \
                        .update({"mydocid": docid}) \
                        .eq("useruid", user_id) \
                        .execute()
                else:
                    docid = docnm = projectid = None
        else:
            docid = docnm = None

            projects = supabase.schema("smartdoc").rpc(
                "fn_project_filtered__r_user",
                {'p_useruid': user_id}
            ).execute().data or []

            projectid = None  # 초기값

            if projects:
                # projects의 projectid 리스트
                projectid_list = [p['projectid'] for p in projects]

                # 2. smartdoc.projectusers에서 useruid = user_id 이고 projectid가 projects에 포함된 데이터 조회
                project_users_resp = supabase.schema("smartdoc").table("projectusers") \
                    .select("*") \
                    .in_("projectid", projectid_list) \
                    .eq("useruid", user_id) \
                    .execute()

                project_users = project_users_resp.data or []

                # 3. rolecd = 'M' 인 데이터 필터링
                master_projects = [pu for pu in project_users if pu.get('rolecd') == 'M']

                if master_projects:
                    # rolecd='M' 데이터가 있으면 첫 번째 프로젝트id
                    projectid = master_projects[0]['projectid']
                elif project_users:
                    # rolecd='M' 데이터 없으면 전체 데이터 중 첫 번째 프로젝트id
                    projectid = project_users[0]['projectid']
                else:
                    # project_users도 없으면 projects 중 첫 번째 projectid
                    projectid = 0

        # ✅ Step 5. 프로젝트 및 테넌트 정보 조회
        if projectid:
            user_project_response = supabase.schema("smartdoc").table("projectusers") \
                .select("*").eq("projectid", projectid).eq("useruid", user_id).execute()
            user_projects = user_project_response.data

            projects_response = supabase.schema("smartdoc").table("projects") \
                .select("*").eq("projectid", projectid).execute()
            projects = projects_response.data

            user_tenant_response = supabase.schema("smartdoc").table("tenantusers") \
                .select("*").eq("useruid", user_id).execute()
            user_tenant = user_tenant_response.data

            tenants_response = supabase.schema("smartdoc").table("tenants") \
                .select("*").execute()
            tenants = tenants_response.data

            # tenants에 존재하는 tenantid set 생성
            valid_tenant_ids = {str(t["tenantid"]) for t in tenants}

            # user_tenant 중에서 실제 존재하는 tenant만 필터
            matched_tenants = [
                str(ut["tenantid"])
                for ut in user_tenant
                if str(ut["tenantid"]) in valid_tenant_ids
            ]

            # 최종 tenantid 1개 선택
            tenantid = matched_tenants[0] if matched_tenants else None

            if tenantid:
                matched_tenant = next(
                    (t for t in tenants if str(t["tenantid"]) == str(tenantid)),
                    None
                )
                if matched_tenant:
                    tenanticonurl = matched_tenant.get("iconfileurl")

        else:
            tenantid = None
            user_projects = []
            user_tenant = []

        # ✅ Step 6. 권한 플래그 세팅
        if user_projects and any(p.get("rolecd") == "M" for p in user_projects):
            projectmanager = 'Y'
        if user_tenant and any(t.get("rolecd") == "M" for t in user_tenant):
            tenantmanager = 'Y'

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
            
        # ✅ Step 7. 세션 저장
        datas = {
            "id": user_id,
            "email": user.email,
            "roleid": roleid,
            "billingmodelcd" : billingmodelcd,
            "docid": docid,
            "docnm": docnm,
            "tenantid": tenantid,
            "tenantmanager": tenantmanager,
            "tenanticonurl": tenanticonurl,   # ⭐ 추가
            "projectid": projectid,
            "projectmanager": projectmanager,
            "editbuttonyn" : editbuttonyn,
            "sampledocyn" : sampledocyn,
        }

        if type == 'login':
            request.session["user"] = datas
        elif type == 'doc_setting':
            request.session["user"].update(datas)
        elif type == 'tenant_setting':
            request.session["user"].update(datas)

        ses_user = request.session["user"]

        return user_projects

    except Exception as e:
        # print(f'ErrorMessage: {e}')
        messages.error(request, f"로그인 실패: {str(e)}")
        return JsonResponse({'result': 'Failed', 'message': f'로그인 실패: {str(e)}'})



def logout_view(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")


    supabase = get_supabase_client(access_token, refresh_token)

    try:
        supabase.auth.sign_out()
    except Exception as e:
         pass  # 이미 만료된 세션 등

    request.session.flush()
    return redirect("home")

def send_reset_email(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    if request.method == "POST":
        # AJAX 요청이면 request.body, 일반 form이면 request.POST
        if request.content_type == "application/json":
            import json
            data = json.loads(request.body)
            email = data.get("email", "").strip()
        else:
            email = request.POST.get("reset_email", "").strip()

        if not email:
            message = "이메일을 입력해주세요."
            if request.content_type == "application/json":
                return JsonResponse({"ok": False, "messages": message})
            else:
                messages.error(request, message)
                return redirect("login")

        try:
            redirect_url = "https://dev-smart-doc.azurewebsites.net/password-reset/"
            # redirect_url = "http://localhost:8000/password-reset/"
            supabase.auth.reset_password_email(email, {"redirect_to": redirect_url})
            message = "비밀번호 재설정 링크가 이메일로 발송되었습니다."

            if request.content_type == "application/json":
                return JsonResponse({"ok": True, "messages": message})
            else:
                messages.success(request, message)
                return redirect("login")

        except Exception as e:
            message = f"메일 발송 실패: {str(e)}"
            if request.content_type == "application/json":
                return JsonResponse({"ok": False, "messages": message})
            else:
                messages.error(request, message)
                return redirect("login")
            