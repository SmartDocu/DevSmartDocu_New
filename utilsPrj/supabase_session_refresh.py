# utilsPrj/supabase_session_refresh.py
import time
from django.shortcuts import redirect
from django.http import JsonResponse
from gotrue.errors import AuthApiError
from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.errorlogs import error_login


class SupabaseSessionRefreshMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        # self.last_refresh_time = 0
        # self.MIN_REFRESH_INTERVAL = 60  # 초 단위

    def __call__(self, request):

        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        user_info = request.session.get("user")

        # -------------------------------------------------------------
        # 자동 요청 제외
        # -------------------------------------------------------------
        ignored_paths = ["/favicon.ico", "/robots.txt", "/healthcheck"]
        if request.path in ignored_paths:
            return self.get_response(request)

        # -------------------------------------------------------------
        # 로그인 상태가 아닐 때 (세션 쿠키 만료 / 토큰 손실)
        # -------------------------------------------------------------
        if not access_token or not refresh_token:
            self._log_missing_token(request, access_token, refresh_token, user_info)
            return self.get_response(request)

        # 새로운 Supabase 클라이언트 생성
        # supabase = self._get_fresh_client(access_token, refresh_token)
        supabase = self._get_fresh_client(access_token)

        try:
            if not request.session.get("user"):
                user = supabase.auth.get_user().user
                request.session["user"] = user
                request.session.modified = True

        except AuthApiError as e1:
            msg = str(e1)

            # 🔹 토큰 만료가 아니면 refresh하지 않음
            if "expired" not in msg.lower():
                self._log_general_exception(request, e1)
                return self.get_response(request)

            self._log_access_token_expired(request, access_token, e1)

            try:
                refreshed = supabase.auth.refresh_session(refresh_token)

                if refreshed and refreshed.session:
                    request.session["access_token"] = refreshed.session.access_token
                    request.session["refresh_token"] = refreshed.session.refresh_token
                    request.session["user"] = refreshed.session.user
                    request.session.modified = True
                else:
                    self._clear_session(request)
                    return self._handle_expired(request)

            except AuthApiError as e2:
                return self._handle_refresh_auth_api_error(request, refresh_token, e2)
            except Exception as ex:
                self._log_refresh_unknown_exception(request, refresh_token, ex)
                self._clear_session(request)
                return self._handle_expired(request)

        except Exception as ex2:
            self._log_general_exception(request, ex2)
            return self.get_response(request)

        return self.get_response(request)

    # ---------- 내부 유틸 ----------

    # def _get_fresh_client(self, access_token=None, refresh_token=None):
    #     return get_supabase_client(access_token, refresh_token)

    def _get_fresh_client(self, access_token=None):
        return get_supabase_client(access_token)

    def _clear_session(self, request):
        request.session.pop("access_token", None)
        request.session.pop("refresh_token", None)
        request.session.pop("user", None)
        request.session.modified = True

    def _handle_expired(self, request):
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "result": "Failed",
                "message": "세션이 만료되었습니다. 다시 로그인해주세요."
            }, status=401)
        return redirect("home")

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    # ---------- 상세 로깅 헬퍼 ----------

    def _log_missing_token(self, request, access_token, refresh_token, user_info):
        error_login(
            request,
            errorobject="missing_token",
            errormessage="access_token 또는 refresh_token 없음",
            remarks1=request.path,
            remarks2=f"UA={request.headers.get('User-Agent')}, method={request.method}, query={request.META.get('QUERY_STRING')}, ip={self._get_client_ip(request)}",
            remarks3=f"세션 쿠키 만료 or 손실, session_keys={list(request.session.keys())}, user={user_info}, access_token={access_token}, refresh_token={refresh_token}"
        )

    def _log_access_token_expired(self, request, access_token, exception):
        error_login(
            request,
            errorobject="access_token_expired",
            errormessage=str(exception),
            remarks1=request.path,
            remarks2=f"access_token={access_token}",
            remarks3="Access token 만료됨"
        )

    def _log_refresh_failed(self, request, refresh_token, msg):
        error_login(
            request,
            errorobject="refresh_failed",
            errormessage=msg,
            remarks1=request.path,
            remarks2=f"refresh_token={refresh_token}",
            remarks3="refresh 실패"
        )

    def _handle_refresh_auth_api_error(self, request, refresh_token, exception):
        msg = str(exception)
        if "Invalid Refresh Token" in msg or "already used" in msg.lower():
            error_login(
                request,
                errorobject="invalid_refresh_token",
                errormessage=msg,
                remarks1=request.path,
                remarks2=f"refresh_token={refresh_token}",
                remarks3="Refresh token 무효 or 이미 사용됨"
            )
            self._clear_session(request)
            return self._handle_expired(request)

        elif "429" in msg:
            error_login(
                request,
                errorobject="refresh_429",
                errormessage=msg,
                remarks1=request.path,
                remarks2=f"refresh_token={refresh_token}",
                remarks3="Too Many Requests"
            )
            return self.get_response(request)

        else:
            error_login(
                request,
                errorobject="refresh_exception",
                errormessage=msg,
                remarks1=request.path,
                remarks2=f"refresh_token={refresh_token}",
                remarks3="refresh 중 기타 오류"
            )
            self._clear_session(request)
            return self._handle_expired(request)

    def _log_refresh_unknown_exception(self, request, refresh_token, exception):
        error_login(
            request,
            errorobject="refresh_unknown_exception",
            errormessage=str(exception),
            remarks1=request.path,
            remarks2=f"refresh_token={refresh_token}",
            remarks3="refresh 중 알 수 없는 오류"
        )

    def _log_general_exception(self, request, exception):
        error_login(
            request,
            errorobject="general_exception",
            errormessage=str(exception),
            remarks1=request.path,
            remarks2=f"UA={request.headers.get('User-Agent')}, method={request.method}, query={request.META.get('QUERY_STRING')}, ip={self._get_client_ip(request)}",
            remarks3="예상치 못한 예외"
        )
