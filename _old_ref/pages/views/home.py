from django.shortcuts import render
from datetime import datetime, timedelta
from utilsPrj.supabase_client import get_supabase_client
import uuid
from django.http import JsonResponse
import json

def home(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    now = datetime.utcnow()
    now_iso = now.isoformat()
    user_id = request.session.get("user", {}).get("id")

    # DB에서 활성 팝업 조회
    popups_data = supabase.schema("smartdoc").table("popups")\
        .select("*")\
        .eq("useyn", True)\
        .lte("startdts", now_iso)\
        .gte("enddts", now_iso)\
        .execute()

    active_popups = []

    for popup in popups_data.data:
        show = True

        # -------------- 로그인 후 L 팝업에 대한 DB 차단 로직 --------------
        if user_id:
            # 팝업 숨김 여부 확인
            deactivate = supabase.schema("smartdoc").table("popupdeactivates")\
                .select("*")\
                .eq("popupid", popup["popupid"])\
                .eq("useruid", user_id)\
                .execute()

            if deactivate.data:
                record = deactivate.data[0]
                enddt = record.get("enddt")

                if enddt:
                    enddt_dt = datetime.fromisoformat(enddt.replace("Z", "+00:00"))

                    # enddt > 현재 → 기간 안 지남 → 숨김
                    if enddt_dt > now:
                        show = False
                    else:
                        show = True  # enddt 지났으므로 다시 보여줌

        # --------------------------------------------------------------

        active_popups.append({
            "popupid": popup["popupid"],
            "title": popup["title"],
            "pageurl": popup["pageurl"],
            "width": popup.get("width", 400),
            "height": popup.get("height", 300),
            "left": popup.get("lefts", 100),
            "top": popup.get("top", 100),
            "mainlogin": popup.get("mainlogin", 'M'),
            "deactivateday": popup.get("deactivateday", 7),
            "show": show
        })

    return render(request, 'pages/home.html', {
            "popups": active_popups,
            "user_id" : user_id
    })

def hide_popup(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception as e:
            return JsonResponse({"status": "fail", "error": "Invalid JSON"}, status=400)

        popupid = data.get("popupid")
        days = data.get("days", 1)

        try:
            days = int(days)
        except Exception as e:
            days = 1

        user_uid = request.session.get("user", {}).get("id")

        if not user_uid:
            return JsonResponse({"status": "fail", "error": "User not logged in"}, status=403)
        if not popupid:
            return JsonResponse({"status": "fail", "error": "No popupid provided"}, status=400)

        # Supabase 처리
        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_supabase_client(access_token, refresh_token)

        enddt = (datetime.utcnow() + timedelta(days=days)).isoformat()

        existing = supabase.schema("smartdoc").table("popupdeactivates")\
            .select("*")\
            .eq("popupid", popupid)\
            .eq("useruid", user_uid)\
            .execute()

        if existing.data:
            supabase.schema("smartdoc").table("popupdeactivates")\
                .update({"enddt": enddt})\
                .eq("popupid", popupid)\
                .eq("useruid", user_uid)\
                .execute()
        else:
            supabase.schema("smartdoc").table("popupdeactivates")\
                .insert({
                    "popupid": popupid,
                    "useruid": user_uid,
                    "enddt": enddt,
                    "creator": user_uid
                }).execute()

        return JsonResponse({"status": "ok"})

    return JsonResponse({"status": "fail"}, status=400)

def search_help(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception as e:
            return JsonResponse({"status": "fail", "error": "Invalid JSON"}, status=400)

        url = data.get("url")
        # print(f'URL: {url}')

        response = supabase.schema("smartdoc").table("helps").select("*").eq("url", url).execute().data or []
        # print(f'Result: {response}')

        # JsonResponse로 반환
        return JsonResponse({
            "status": "success",
            "data": response
        })
    else:
        return JsonResponse({"status": "fail", "error": "POST 요청만 허용됩니다."}, status=400)