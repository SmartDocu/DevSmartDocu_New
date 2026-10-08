"""creator/updater 등 useruid 컬럼을 화면 표시용 이름/이메일로 변환하는 공용 헬퍼.

creator/updater 컬럼을 조회해 화면에 노출해야 하는 경우 반드시 이 모듈을 거칠 것 —
각 라우터에서 public.users를 직접 조회하는 중복 코드를 작성하지 않는다.

탈퇴한 사용자는 public.users에서 이름/이메일이 비워지거나(행 자체가 없을 수도 있음) 조회되지 않으므로,
탈퇴 시 sdoc.users에 저장해 둔 마스킹 값(masked_usernm/masked_email)으로 대신 표시한다.
"""


def mask_name(name: str) -> str:
    """홍길동 → 홍**. 한 글자면 그대로 '*' 하나."""
    chars = list(name or "")
    if not chars:
        return ""
    if len(chars) == 1:
        return "*"
    return chars[0] + "*" * (len(chars) - 1)


def mask_email(email: str) -> str:
    """rootel@example.com → ro***@ex***.com"""
    if not email or "@" not in email:
        return ""
    local, domain = email.rsplit("@", 1)
    label, dot, tld = domain.rpartition(".")
    if not dot:
        label, tld = domain, ""
    masked_local = local[:2] + "***"
    masked_label = label[:2] + "***"
    return f"{masked_local}@{masked_label}{dot}{tld}"


def _masked_fallback(uids: list) -> dict:
    """탈퇴 사용자의 마스킹 값을 { useruid: (이름, 이메일) }로 조회한다. 실패 시 빈 dict."""
    if not uids:
        return {}
    try:
        from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
        rows = (
            get_service_client().schema(SUPABASE_SCHEMA).table("users")
            .select("useruid,masked_usernm,masked_email").in_("useruid", uids).execute().data or []
        )
        return {r["useruid"]: (r.get("masked_usernm") or "", r.get("masked_email") or "") for r in rows}
    except Exception:
        return {}


def get_usernm_email(sb, useruid: str) -> tuple[str, str]:
    """단일 useruid를 (이름, 이메일)로 변환한다. 실패 시 ("", "")."""
    if not useruid:
        return "", ""
    return get_usernm_email_map(sb, [useruid]).get(useruid, ("", ""))


def get_usernm_email_map(sb, useruids: list) -> dict:
    """여러 useruid를 한 번에 { useruid: (이름, 이메일) }로 변환한다.

    목록 화면에서 행마다 조회하는 N+1 패턴 대신 이 함수로 한 번에 가져올 것.
    """
    uids = [u for u in set(useruids) if u]
    if not uids:
        return {}
    result: dict = {}
    try:
        rows = sb.schema("public").table("users").select("useruid,full_name,email").in_("useruid", uids).execute().data or []
        result = {r["useruid"]: (r.get("full_name") or "", r.get("email") or "") for r in rows}
    except Exception:
        pass
    # 이름·이메일이 모두 비었거나 아예 조회되지 않은 사용자 = 탈퇴자 → 마스킹 값으로 대체
    missing = [u for u in uids if not any(result.get(u, ("", "")))]
    if missing:
        result.update({u: v for u, v in _masked_fallback(missing).items() if any(v)})
    return result
