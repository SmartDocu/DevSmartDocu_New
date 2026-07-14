"""creditbuckets 관련 공통 로직.

creditchargecd='Ba'(플랜 기본) 크레딧을 신규/갱신 지급할 때,
같은 tenantid/accountuid/servicecd에 이미 유효한 Ba 버킷이 있으면
기존 remaincredit을 신규 chargecredit에 합산하고 기존 행은
creditbucket_historys로 이관한다.
"""
import uuid
from datetime import datetime, timezone

# creditbuckets.priorityno — creditchargecd별 소진 우선순위
CREDITCHARGECD_PRIORITY = {"Ba": 1, "Pr": 3, "Re": 4, "Ma": 5, "Au": 6}


def upsert_ba_creditbucket(
    svc,
    *,
    tenantid: int,
    accountuid: str,
    servicecd: str,
    chargecredit: int,
    granteddts: str,
    expiredts: str,
    startdt: str,
    subscriptionuid: str = None,
) -> dict:
    """creditchargecd='Ba' 크레딧을 신규 지급하고, 필요 시 기존 잔여 크레딧을 병합·이관한다.

    - 같은 tenantid/accountuid/servicecd로 기존 Ba 버킷이 없으면 그대로 신규 insert.
    - 있으면: 기존 remaincredit을 신규 chargecredit에 더하고(remaincredit도 동일 값),
      기존 행은 만료 처리(expiredts=지금) 후 creditbucket_historys로 이관, creditbuckets에서 제거.

    반환값: 새로 insert된 creditbuckets 행(dict).
    """
    subscriptionuid = subscriptionuid or str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    existing_rows = (
        svc.table("creditbuckets").select("*")
        .eq("tenantid", int(tenantid)).eq("accountuid", accountuid)
        .eq("servicecd", servicecd).eq("creditchargecd", "Ba")
        .order("startdt", desc=True).limit(1)
        .execute().data or []
    )

    if existing_rows:
        old = existing_rows[0]
        chargecredit = chargecredit + (old.get("remaincredit") or 0)

        svc.table("creditbucket_historys").insert({
            **old,
            "expiredts": now_utc.isoformat(),
            "logdts": now_utc.isoformat(),
        }).execute()
        svc.table("creditbuckets").delete().eq("subscriptionuid", old["subscriptionuid"]).execute()

    new_row = {
        "subscriptionuid": subscriptionuid,
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "servicecd": servicecd,
        "creditchargecd": "Ba",
        "priorityno": CREDITCHARGECD_PRIORITY["Ba"],
        "chargecredit": chargecredit,
        "usecredit": 0,
        "remaincredit": chargecredit,
        "granteddts": granteddts,
        "expiredts": expiredts,
        "startdt": startdt,
    }
    svc.table("creditbuckets").insert(new_row).execute()
    return new_row
