from utilsPrj.supabase_client import get_supabase_client
from datetime import datetime, timezone, timedelta
import uuid
import traceback

def error_log(request, errormessage, errorobject, creator, remarks1 = None, remarks2 = None, remarks3 = None):
    # --------------------------
    #  로그 저장
    #  remark1 / remark2 / remark3 의 경우 옵션이므로 삽입 하지 않아도 처리 됨.
    #  
    #  Ex) error_log(request,e, inspect.currentframe().f_code.co_name, user_id)
    #  
    #  필수 값: request, errormessage, errorobject, creator
    # --------------------------
    # print('Error Log 삽입')
    try:
        supabase = get_supabase_client(
            request.session.get("access_token"),
            request.session.get("refresh_token")
        )

        data = {
            "errormessage": str(errormessage),
            "errorobject": errorobject,
            "creator": creator,
            "remarks1": remarks1,
            "remarks2": remarks2,
            "remarks3": remarks3,
        }

        # print(f'Data: {data}')

        response = supabase.schema("smartdoc").table("logerrors").insert(data).execute()
        if len(response.data) > 0:
            print(f"에러 로그 삽입 성공 하였습니다: {str(errormessage)}")
        else:
            print(f"에러 로그 삽입 실패: {str(errormessage)}")

    except Exception as e:
        print(f'에러 로그 삽입 실패: {str(e)}')

def error_login(request, errorobject="", errormessage="", 
                remarks1=None, remarks2=None, remarks3=None):
    """
    로그인 관련 오류를 smartdoc.loginerrors 테이블에 기록
    """

    try:
        supabase = get_supabase_client()

        user = request.session.get("user")
        userid = user["id"] if isinstance(user, dict) and "id" in user else None

        supabase.schema("smartdoc").table("loginerrors").insert({
            "errorobject": errorobject,
            "errormessage": errormessage,
            "remarks1": remarks1,
            "remarks2": remarks2,
            "remarks3": remarks3,
            "creator": userid
        }).execute()

    except Exception as e:
        print("loginerrors 로그 기록 실패:", e)
