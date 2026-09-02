"""accountservices.servicestatus 기준 문서 서비스 Read/Write 권한 판정.

sdoc.codes(codegroupcd='servicestatus') 값과 반드시 일치해야 한다
(servicestatus_permission_setup.sql 참고):

    Pending    가입 진행 중(결제 대기)              read X  write X
    Active     정상 구독                            read O  write O
    PastDue    결제 실패(Grace Period) — 2026-08-07부터 Do 서비스는 크레딧
               Ba(기본) 버킷이 마이너스로 떨어질 때도 자동 전환됨(사용량이
               예측치를 초과한 경우). Ba가 0 이상으로 회복(추가구매 상쇄 또는
               월간 갱신)되면 자동으로 Active 복귀 — utilsPrj/credit_helper.py의
               _set_servicestatus_if()/offset_negative_ba_bucket() 및
               genobjectcounts_credit_deduction.sql/creditbuckets_daily_batch.sql
               참고.                                  read O  write X
    Suspended  관리자가 중지                         read X  write X
    Cancelled  해지 완료                             read X  write X
    Archived   종료 후 보관 — configs.userdatadelday일 이내만 read O, write는 항상 X
               (기준 시점 = accountservices.updatedts)
    Deleted    전체 삭제됨                           read X  write X
"""
from datetime import datetime, timezone

from dateutil import parser as dp

from utilsPrj.supabase_client import SUPABASE_SCHEMA

_WRITE_ALLOWED = {"Active"}
_READ_ALWAYS_ALLOWED = {"Active", "PastDue"}
_READ_NEVER_ALLOWED = {"Pending", "Suspended", "Cancelled", "Deleted"}


def get_service_permission(sb, tenantid, user_id: str, servicecd: str = "Do") -> dict:
    """tenantid + user_id + servicecd 기준으로 {"servicestatus", "can_read", "can_write"} 반환.

    system tenant는 여러 개인 계정이 같은 tenantid를 공유하므로 useruid로 조회해야
    accounts 행이 유일하게 특정된다(기업 tenant는 tenantid로 유일). auth.py의
    _load_user_context() 8번 단계와 동일한 판단 기준을 따른다 — 여기서 tenantid만으로
    accounts를 조회하면 system tenant에서 406(다중 행) 에러가 난다.

    accountservices 행을 못 찾으면(계정/서비스 미가입 등) read/write 모두 불허로 처리한다.
    """
    if not tenantid or not user_id:
        return {"servicestatus": None, "can_read": False, "can_write": False}

    t_row = (
        sb.schema(SUPABASE_SCHEMA).table("tenants")
        .select("issystemtenant")
        .eq("tenantid", int(tenantid))
        .maybe_single()
        .execute()
    )
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row and t_row.data else True

    if issystemtenant:
        acc_q = sb.schema(SUPABASE_SCHEMA).table("accounts").select("accountuid").eq("useruid", user_id)
    else:
        # 기업 테넌트는 계정을 테넌트 전체가 공유하므로, tenantid만으로 조회하면
        # 그 테넌트 소속이 아닌 사용자도(예: 다른 테넌트에서 X-Tenant-ID를 조작) 공유 계정의
        # 권한을 그대로 얻게 된다. tenantusers에 활성 멤버로 등록돼 있는지 먼저 확인한다.
        membership = (
            sb.schema(SUPABASE_SCHEMA).table("tenantusers")
            .select("tenantid")
            .eq("tenantid", int(tenantid))
            .eq("useruid", user_id)
            .eq("useyn", True)
            .maybe_single()
            .execute()
        )
        if not membership or not membership.data:
            return {"servicestatus": None, "can_read": False, "can_write": False}
        acc_q = sb.schema(SUPABASE_SCHEMA).table("accounts").select("accountuid").eq("tenantid", int(tenantid))

    acc = acc_q.maybe_single().execute()
    accountuid = acc.data.get("accountuid") if acc and acc.data else None
    if not accountuid:
        return {"servicestatus": None, "can_read": False, "can_write": False}

    svc_row = (
        sb.schema(SUPABASE_SCHEMA).table("accountservices")
        .select("servicestatus,updatedts")
        .eq("accountuid", accountuid)
        .eq("servicecd", servicecd)
        .maybe_single()
        .execute()
    )
    if not svc_row or not svc_row.data:
        return {"servicestatus": None, "can_read": False, "can_write": False}

    status = svc_row.data.get("servicestatus")
    can_write = status in _WRITE_ALLOWED

    if status in _READ_ALWAYS_ALLOWED:
        can_read = True
    elif status in _READ_NEVER_ALLOWED:
        can_read = False
    elif status == "Archived":
        can_read = _within_archive_retention(sb, svc_row.data.get("updatedts"))
    else:
        can_read = False

    return {"servicestatus": status, "can_read": can_read, "can_write": can_write}


def _within_archive_retention(sb, updatedts) -> bool:
    if not updatedts:
        return False

    cfg = sb.schema(SUPABASE_SCHEMA).table("configs").select("userdatadelday").limit(1).execute()
    retention_days = (cfg.data[0].get("userdatadelday") if cfg.data else None) or 0

    dt = dp.parse(updatedts) if isinstance(updatedts, str) else updatedts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed_days = (datetime.now(timezone.utc) - dt).days
    return elapsed_days <= retention_days
