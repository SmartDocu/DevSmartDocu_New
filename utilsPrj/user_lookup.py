"""creator/updater 등 useruid 컬럼을 화면 표시용 이름/이메일로 변환하는 공용 헬퍼.

creator/updater 컬럼을 조회해 화면에 노출해야 하는 경우 반드시 이 모듈을 거칠 것 —
각 라우터에서 public.users를 직접 조회하는 중복 코드를 작성하지 않는다.
"""


def get_usernm_email(sb, useruid: str) -> tuple[str, str]:
    """단일 useruid를 (이름, 이메일)로 변환한다. 실패 시 ("", "")."""
    if not useruid:
        return "", ""
    try:
        rows = sb.schema("public").table("users").select("full_name,email").eq("useruid", useruid).execute().data
        if rows:
            return rows[0].get("full_name", ""), rows[0].get("email", "")
    except Exception:
        pass
    return "", ""


def get_usernm_email_map(sb, useruids: list) -> dict:
    """여러 useruid를 한 번에 { useruid: (이름, 이메일) }로 변환한다.

    목록 화면에서 행마다 조회하는 N+1 패턴 대신 이 함수로 한 번에 가져올 것.
    """
    uids = [u for u in set(useruids) if u]
    if not uids:
        return {}
    try:
        rows = sb.schema("public").table("users").select("useruid,full_name,email").in_("useruid", uids).execute().data or []
        return {r["useruid"]: (r.get("full_name", ""), r.get("email", "")) for r in rows}
    except Exception:
        return {}
