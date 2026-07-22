"""외부 REST API 호출 유틸리티. 인증 방식별 래퍼 함수 제공."""
from typing import Optional

import requests


def _result(resp: requests.Response) -> dict:
    return {"ok": resp.ok, "status_code": resp.status_code, "detail": resp.reason or ""}


def _err(msg: str, status_code: int = 0) -> dict:
    return {"ok": False, "status_code": status_code, "detail": msg}


def call_no_auth(url: str, method: str = "GET", timeout: int = 10) -> dict:
    """인증 없이 API 호출 (Health 체크용)."""
    try:
        return _result(requests.request(method.upper(), url, timeout=timeout))
    except requests.Timeout:
        return _err("Connection timed out")
    except requests.ConnectionError as e:
        return _err(f"Connection error: {str(e)[:120]}")
    except Exception as e:
        return _err(str(e)[:120])


def call_api_key(
    url: str,
    method: str,
    key_name: str,
    key_value: str,
    location: str,
    extra_headers: Optional[list] = None,
    timeout: int = 10,
) -> dict:
    """API Key 인증으로 API 호출.

    extra_headers: Supabase처럼 apikey 헤더 외에 Authorization, Accept-Profile(스키마 지정) 등
    추가 헤더가 동시에 필요한 API를 위한 선택적 보조 헤더 목록. [{"name": ..., "value": ...}, ...]
    """
    headers: dict = {}
    params: dict = {}
    json_data = None

    if location == "header":
        headers[key_name] = key_value
    elif location == "query":
        params[key_name] = key_value
    elif location == "body":
        json_data = {key_name: key_value}

    for h in (extra_headers or []):
        name, value = h.get("name"), h.get("value")
        if name and value:
            headers[name] = value

    try:
        return _result(
            requests.request(method.upper(), url, headers=headers, params=params, json=json_data, timeout=timeout)
        )
    except requests.Timeout:
        return _err("Connection timed out")
    except requests.ConnectionError as e:
        return _err(f"Connection error: {str(e)[:120]}")
    except Exception as e:
        return _err(str(e)[:120])


def call_basic_auth(url: str, method: str, username: str, password: str, timeout: int = 10) -> dict:
    """HTTP Basic 인증으로 API 호출."""
    try:
        return _result(requests.request(method.upper(), url, auth=(username, password), timeout=timeout))
    except requests.Timeout:
        return _err("Connection timed out")
    except requests.ConnectionError as e:
        return _err(f"Connection error: {str(e)[:120]}")
    except Exception as e:
        return _err(str(e)[:120])


def get_oauth2_token(
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    grant_type: str,
    scope: Optional[str] = None,
    timeout: int = 10,
) -> str:
    """OAuth2 액세스 토큰 발급. 실패 시 예외 발생."""
    data: dict = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope

    resp = requests.post(token_endpoint, data=data, timeout=timeout)
    resp.raise_for_status()
    token_data = resp.json()
    if "access_token" not in token_data:
        raise ValueError(f"access_token 없음. 응답 키: {list(token_data.keys())}")
    return token_data["access_token"]


def call_api_for_data(
    url: str,
    method: str,
    authtype: str,
    api_params: list,
    auth_cred: dict,
    secrets: dict,
    timeout: int = 15,
) -> dict:
    """데이터 수집용 API 호출. 파라미터와 인증 정보를 조합해 실제 호출 후 응답 반환.

    api_params: [{paramnm, param_locationcd, is_fixed, fixed_value, testvalue}]
    auth_cred:  {api_key_name, api_key_locationcd, oauth_client_id, token_endpoint,
                 grant_type, scope, authorization_type}
    secrets:    {api_key_value, username, password, oauth_client_secret}
    Returns:    {"ok": bool, "status_code": int, "detail": str, "data": any}
    """
    query_params: dict = {}
    body_params: dict  = {}
    extra_headers: dict = {}

    for p in api_params:
        value = p.get("fixed_value") if p.get("is_fixed") else p.get("testvalue")
        if value is None:
            continue
        name = p.get("paramnm", "")
        loc  = p.get("param_locationcd") or "query"
        if loc == "query":
            query_params[name] = value
        elif loc == "body":
            body_params[name] = value
        elif loc == "header":
            extra_headers[name] = value
        elif loc == "path":
            url = url.replace(f"{{{name}}}", str(value))

    headers = {**extra_headers}
    auth = None

    if authtype == "API_KEY":
        key_name = auth_cred.get("api_key_name", "")
        key_value = secrets.get("api_key_value", "")
        key_loc  = auth_cred.get("api_key_locationcd") or "header"
        if key_loc == "header":
            headers[key_name] = key_value
        elif key_loc == "query":
            query_params[key_name] = key_value
        elif key_loc == "body":
            body_params[key_name] = key_value

        for h in (secrets.get("extra_headers") or []):
            hname, hvalue = h.get("name"), h.get("value")
            if hname and hvalue:
                headers[hname] = hvalue

    elif authtype == "BASIC":
        auth = (secrets.get("username", ""), secrets.get("password", ""))

    elif authtype == "OAUTH2":
        try:
            token = get_oauth2_token(
                auth_cred.get("token_endpoint", ""),
                auth_cred.get("oauth_client_id", ""),
                secrets.get("oauth_client_secret", ""),
                auth_cred.get("grant_type") or "client_credentials",
                auth_cred.get("scope"),
                timeout,
            )
            auth_type_str = auth_cred.get("authorization_type") or "Bearer"
            headers["Authorization"] = f"{auth_type_str} {token}"
        except Exception as e:
            return _err(f"OAuth2 token error: {str(e)[:120]}")

    try:
        resp = requests.request(
            method.upper(), url,
            headers=headers,
            params=query_params or None,
            json=body_params or None,
            auth=auth,
            timeout=timeout,
        )
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return {"ok": resp.ok, "status_code": resp.status_code, "detail": resp.reason or "", "data": data}
    except requests.Timeout:
        return _err("Connection timed out")
    except requests.ConnectionError as e:
        return _err(f"Connection error: {str(e)[:120]}")
    except Exception as e:
        return _err(str(e)[:120])


def call_oauth2(
    url: str,
    method: str,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    grant_type: str,
    scope: Optional[str] = None,
    authorization_type: str = "Bearer",
    timeout: int = 10,
) -> dict:
    """OAuth2 토큰 발급 후 API 호출."""
    try:
        access_token = get_oauth2_token(token_endpoint, client_id, client_secret, grant_type, scope, timeout)
        headers = {"Authorization": f"{authorization_type} {access_token}"}
        return _result(requests.request(method.upper(), url, headers=headers, timeout=timeout))
    except requests.Timeout:
        return _err("Connection timed out")
    except requests.ConnectionError as e:
        return _err(f"Connection error: {str(e)[:120]}")
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        return _err(f"Token fetch failed: {str(e)[:120]}", code)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(str(e)[:120])
