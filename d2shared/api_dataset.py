"""
api_dataset.py
외부 REST API URL에서 JSON을 가져와 DataFrame으로 변환한다.
사용자가 임의 URL을 입력하므로(예: 통계청 KOSIS Open API) SSRF(사설망 접근) 방지 로직을 포함한다.
인증은 URL에 키가 포함된 경우(예: apiKey=...)와, 별도 헤더(예: Authorization: Bearer ...)가
필요한 경우를 모두 지원한다.
"""
import ipaddress
import json
import socket
from typing import Optional
from urllib.parse import urlparse

import pandas as pd
import requests

MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # API 응답 용량 제한 (50MB)
REQUEST_TIMEOUT = 10  # seconds


def _is_unsafe_host(hostname: str) -> bool:
    """사설/루프백/링크로컬 등 내부망으로 향하는 호스트인지 확인 (SSRF 방지)"""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True  # 이름 해석 실패 시 안전하게 차단
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return True
    return False


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("http/https URL만 사용할 수 있습니다.")
    if not parsed.hostname:
        raise ValueError("올바르지 않은 URL입니다.")
    if _is_unsafe_host(parsed.hostname):
        raise ValueError("내부망/사설 IP로 연결되는 URL은 사용할 수 없습니다.")


def fetch_json(url: str, header_name: Optional[str] = None, header_value: Optional[str] = None) -> object:
    """URL을 안전하게 GET 호출하여 파싱된 JSON을 반환한다.
    header_name/header_value가 주어지면 인증 헤더로 붙여서 호출한다(예: Authorization / Bearer xxx)."""
    _validate_url(url)

    headers = {}
    if header_name and header_value:
        headers[header_name] = header_value

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True)
    if response.status_code in (301, 302, 303, 307, 308):
        raise ValueError("리다이렉트되는 URL은 사용할 수 없습니다.")
    response.raise_for_status()

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ValueError(f"응답 용량이 {MAX_RESPONSE_BYTES // (1024 * 1024)}MB를 초과합니다.")
        chunks.append(chunk)

    return json.loads(b"".join(chunks))


def json_to_dataframe(data: object) -> pd.DataFrame:
    """JSON을 DataFrame으로 변환한다.
    최상위가 배열이면 그대로 사용하고, 객체면 레코드 배열을 담은 첫 필드를 찾아 사용한다."""
    if isinstance(data, list):
        return pd.json_normalize(data)
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return pd.json_normalize(value)
        return pd.json_normalize([data])
    raise ValueError("지원하지 않는 JSON 형식입니다.")
