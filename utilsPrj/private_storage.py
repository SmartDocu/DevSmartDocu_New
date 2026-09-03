"""Private Storage(d2doc-private 버킷) 공용 헬퍼.

Storage RLS(Postgres 정책 기반)는 이 프로젝트에서 신뢰할 수 없다 — Storage API가
신형 JWT 서명 키(ES256)를 검증하지 못하고 모든 요청을 anon으로 취급하는 문제를
2026-09-01 실측으로 확인함(Supabase 플랫폼 쪽 이슈로 추정, storage 로그의
"role": "anon"으로 확인됨 — 로그인 사용자 JWT를 보내도 anon 취급됨).

그래서 접근 통제는 Storage 정책이 아니라 전부 이 헬퍼를 호출하는 라우터 코드에서
처리한다: 업로드/다운로드 전에 반드시 resolve_user_accountuid()로 대상 accountuid를
구하고, 실제 Storage I/O는 항상 service-role 클라이언트로 수행한다(어차피 유저 JWT로
호출해도 anon 취급되니 RLS로 막을 수 없다 — service-role로 통일하고 권한 판단은
코드가 대신한다).

주의(2026-09-01 실측 버그로 발견): upload_private_file/get_private_signed_url/
delete_private_file/resolve_template_bytes의 sb_service 인자는 실제 .storage 호출에는
쓰이지 않는다 — 호출부가 실수로 유저 JWT 클라이언트를 넘겨도(예: auth.py의
_load_user_context가 서명URL 발급에 실패해 사이드바 테넌트 아이콘이 안 보이던 버그)
항상 내부에서 새로 만든 service-role 클라이언트로 강제 수행한다. 인자는 호출부
시그니처 호환을 위해 남겨뒀을 뿐이다.

경로 규칙: Users/{accountuid}/{servicecd}/...
"""
from typing import Optional

from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client

PRIVATE_BUCKET = "d2doc-private"


def resolve_user_accountuid(sb_service, tenantid: int, user_id: str) -> Optional[str]:
    """tenantid + user_id → accountuid 해석.

    시스템(개인) 테넌트면 useruid 기준, 기업 테넌트면 tenantid 기준(계정을 테넌트
    전체가 공유)으로 조회한다. org.py/payments.py의 _resolve_tenant_accountuid와
    동일한 판단 로직 — private storage 쪽에서 재사용하기 위해 공용 헬퍼로 뺐다.
    """
    sd = sb_service.schema(SUPABASE_SCHEMA)
    t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True
    if issystemtenant:
        acc = sd.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = sd.table("accounts").select("accountuid").eq("tenantid", tenantid).maybe_single().execute()
    return acc.data["accountuid"] if acc and acc.data else None


def resolve_accountuid_best_effort(sb_service, user_id: str, tenantid=None) -> Optional[str]:
    """tenantid가 있으면 정석대로 해석하고, 없거나 실패하면 accounts.useruid로 직접 조회한다.
    (예: d2insight의 tenant_id는 "이 사용자가 만든 project" 기준으로만 구해지는 한계가 있어
    본인이 프로젝트를 만든 적 없는 사용자는 tenant_id를 못 구함 — 그래도 본인 개인 계정은
    있을 수 있으니 이 폴백으로 커버한다.)"""
    if tenantid is not None:
        accountuid = resolve_user_accountuid(sb_service, tenantid, user_id)
        if accountuid:
            return accountuid
    sd = sb_service.schema(SUPABASE_SCHEMA)
    acc = sd.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    return acc.data["accountuid"] if acc and acc.data else None


def resolve_accountuid_via_docid(sb_service, docid, user_id: str, tenantid=None) -> Optional[str]:
    """docid로부터 accountuid를 해석한다. tenantid를 모르면 docs.projectid → projects.tenantid로
    거슬러 올라가 구한다(gendocs/genchapters 결과물처럼 호출부에 tenantid가 항상 있지 않은 경우용)."""
    sd = sb_service.schema(SUPABASE_SCHEMA)
    if tenantid is None:
        doc = sd.table("docs").select("projectid").eq("docid", docid).maybe_single().execute()
        projectid = doc.data.get("projectid") if doc and doc.data else None
        if projectid is not None:
            proj = sd.table("projects").select("tenantid").eq("projectid", projectid).maybe_single().execute()
            tenantid = proj.data.get("tenantid") if proj and proj.data else None
    if tenantid is None:
        return None
    return resolve_user_accountuid(sb_service, tenantid, user_id)


def build_private_path(accountuid: str, servicecd: str, *parts: str) -> str:
    """Users/{accountuid}/{servicecd}/{parts...} 형태로 경로를 조립."""
    segments = [p.strip("/") for p in parts if p]
    return "/".join(["Users", accountuid, servicecd, *segments])


def path_accountuid(path: Optional[str]) -> Optional[str]:
    """private 경로(Users/{accountuid}/...)에서 accountuid 세그먼트를 추출. 형식이 아니면 None."""
    if not path:
        return None
    parts = path.strip("/").split("/")
    return parts[1] if len(parts) >= 2 and parts[0] == "Users" else None


def upload_private_file(sb_service, path: str, content: bytes, content_type: str, upsert: bool = False) -> None:
    # Storage API는 유저 JWT를 anon으로 오인식하는 버그가 있어(위 설명 참고) 넘겨받은
    # sb_service와 무관하게 항상 새 service-role 클라이언트로 실제 스토리지 I/O를 수행한다.
    get_service_client().storage.from_(PRIVATE_BUCKET).upload(
        path, content, {"content-type": content_type, "upsert": "true" if upsert else "false"}
    )


def get_private_signed_url(sb_service, path: str, expires_in: int = 3600, expected_accountuid: Optional[str] = None) -> Optional[str]:
    """만료시간(초)이 있는 서명 URL 발급. 실패하면 None.
    넘겨받은 sb_service가 유저 JWT 클라이언트여도(Storage API가 anon으로 오인식해 실패하므로)
    항상 새 service-role 클라이언트로 발급한다.

    expected_accountuid를 넘기면(2단 방어 — Storage RLS가 무력화된 상태라 storage 헬퍼
    레벨에서도 재검증) 경로의 accountuid 세그먼트가 일치할 때만 발급하고, 불일치면 None."""
    if expected_accountuid is not None and path_accountuid(path) != expected_accountuid:
        return None
    try:
        res = get_service_client().storage.from_(PRIVATE_BUCKET).create_signed_url(path, expires_in)
    except Exception:
        return None
    if isinstance(res, dict):
        return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    return res


def delete_private_file(sb_service, path: str, expected_accountuid: Optional[str] = None) -> None:
    """expected_accountuid를 넘기면 경로의 accountuid 세그먼트가 일치할 때만 삭제한다
    (2단 방어 — get_private_signed_url과 동일한 취지)."""
    if expected_accountuid is not None and path_accountuid(path) != expected_accountuid:
        return
    try:
        get_service_client().storage.from_(PRIVATE_BUCKET).remove([path])
    except Exception:
        pass


def delete_private_prefix(sb_service, prefix: str) -> int:
    """prefix(폴더) 이하의 모든 파일을 재귀적으로 찾아 전부 삭제한다. 계정의 서비스 콘텐츠
    전체 삭제(content_purge.py) 용도 — 개별 파일 경로를 하나씩 아는 게 아니라 폴더 통째로
    지워야 할 때 쓴다.

    supabase-py(storage3)에는 prefix 일괄삭제 API가 없어 .list()로 하위 항목을 모으고
    .remove()로 지운다. .list() 응답에서 폴더는 id/metadata가 둘 다 None, 파일은 둘 다
    값이 있다(2026-09-03 실측 확인) — 이 구분으로 폴더면 재귀 진입, 파일이면 삭제 대상에 추가.
    .list()는 기본 limit=100이라 100개 넘는 폴더는 페이지네이션(offset) 없이 돌면 뒷부분이
    조용히 누락되므로 반드시 offset을 넘겨가며 전부 순회해야 한다."""
    client = get_service_client().storage.from_(PRIVATE_BUCKET)
    leaf_paths: list[str] = []

    def _walk(current_prefix: str) -> None:
        offset = 0
        page = 100
        while True:
            entries = client.list(current_prefix, {"limit": page, "offset": offset}) or []
            for e in entries:
                name = e.get("name")
                if not name:
                    continue
                full = f"{current_prefix}/{name}" if current_prefix else name
                if e.get("id") is None and e.get("metadata") is None:
                    _walk(full)
                else:
                    leaf_paths.append(full)
            if len(entries) < page:
                break
            offset += page

    _walk(prefix.strip("/"))
    for i in range(0, len(leaf_paths), 100):
        try:
            client.remove(leaf_paths[i:i + 100])
        except Exception:
            pass
    return len(leaf_paths)


def is_private_path(value: Optional[str]) -> bool:
    """DB에 저장된 값이 (구형) 공개 URL이 아니라 (신형) private 버킷 경로인지 판별.
    구형 값은 항상 http(s):// 로 시작하는 완전한 URL이었다."""
    return bool(value) and not value.startswith("http://") and not value.startswith("https://")


def resolve_display_url(sb_service, value: Optional[str], expected_accountuid: Optional[str] = None) -> Optional[str]:
    """저장된 값이 private 경로면 서명 URL로 변환, 구형 공개 URL이면 그대로 반환.
    프론트에 URL을 그대로 내려주는 모든 read 지점에서 공용으로 사용.
    expected_accountuid는 get_private_signed_url로 그대로 전달(2단 방어)."""
    if not value:
        return value
    if is_private_path(value):
        return get_private_signed_url(sb_service, value, expected_accountuid=expected_accountuid) or value
    return value


def resolve_template_bytes(sb_service, url_or_path: Optional[str]) -> Optional[bytes]:
    """docs.basetemplateurl / chapters.chaptertemplateurl 값을 실제 바이트로 변환.
    구형(공개 URL)이면 그대로 HTTP GET, 신형(private 버킷 경로)이면 스토리지에서 직접 다운로드."""
    if not url_or_path:
        return None
    if is_private_path(url_or_path):
        return get_service_client().storage.from_(PRIVATE_BUCKET).download(url_or_path)
    import requests
    resp = requests.get(url_or_path)
    resp.raise_for_status()
    return resp.content
