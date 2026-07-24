"""creditbuckets 관련 공통 로직.

creditchargecd='Ba'(플랜 기본) 크레딧을 신규/갱신 지급할 때,
같은 tenantid/accountuid/servicecd에 이미 유효한 Ba 버킷이 있으면
기존 remaincredit을 신규 chargecredit에 합산하고 기존 행은
creditbucket_historys로 이관한다.
"""
import uuid
from datetime import datetime, timezone

from utilsPrj.supabase_client import SUPABASE_SCHEMA

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


def _close_logs(sb_svc, log_table: str, loguids: list, true_count: int) -> None:
    """대상 로그들을 닫는다 — applieddts 기록 + count를 실제(true) 값으로 정정.
    log_table.count는 트리거가 계산한 부정확한 값일 수 있어(_true_success_count 참고),
    나중에 creditbucketuses/genchapters·gendocs.usecredit과 대조할 때 값이 어긋나지
    않도록 여기서 실제값으로 덮어써 둔다."""
    if not loguids:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    sb_svc.schema(SUPABASE_SCHEMA).table(log_table).update({
        "applieddts": now_iso,
        "count": true_count,
    }).in_("loguid", loguids).execute()


def _write_creditbucketuse(sb_svc, bucket: dict, use_amount: int, tenantid, accountuid: str,
                            refuid: str, usetypecd: str) -> None:
    """buckt 1개에서 use_amount만큼 차감 — creditbucketuses에 기록 후 creditbuckets 갱신."""
    before = bucket.get("remaincredit") or 0
    after = before - use_amount
    sb_svc.schema(SUPABASE_SCHEMA).table("creditbucketuses").insert({
        "tenantid": tenantid,
        "accountuid": accountuid,
        "subscriptionuid": bucket["subscriptionuid"],
        "startdt": bucket.get("startdt"),
        "usetypecd": usetypecd,
        "refuid": refuid,
        "beforecredit": before,
        "usecredit": use_amount,
        "aftercredit": after,
    }).execute()
    sb_svc.schema(SUPABASE_SCHEMA).table("creditbuckets").update({
        "usecredit": (bucket.get("usecredit") or 0) + use_amount,
        "remaincredit": after,
    }).eq("subscriptionuid", bucket["subscriptionuid"]).execute()


def _deduct_credit(sb_svc, accountuid: str, tenantid, amount: int, *, refuid: str, usetypecd: str) -> None:
    """servicecd='Do' 크레딧버킷에서 amount만큼 차감.
    우선순위: priorityno ASC, 동순위면 expiredts ASC(가장 빨리 만료되는 것부터 소진).
    유효 버킷을 다 써도 부족하면 남은 만큼 기준 서비스 구독(creditchargecd='Ba')에 마이너스로 반영한다
    (실제 사용량은 objects 예측치를 넘어설 수 있어 마이너스가 정상적으로 발생할 수 있음)."""
    if amount <= 0:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    remaining = amount

    buckets = sb_svc.schema(SUPABASE_SCHEMA).table("creditbuckets").select("*") \
        .eq("accountuid", accountuid).eq("servicecd", "Do") \
        .gt("expiredts", now_iso) \
        .order("priorityno").order("expiredts") \
        .execute().data or []

    for bucket in buckets:
        if remaining <= 0:
            break
        avail = bucket.get("remaincredit") or 0
        if avail <= 0:
            continue
        take = min(avail, remaining)
        _write_creditbucketuse(sb_svc, bucket, take, tenantid, accountuid, refuid, usetypecd)
        remaining -= take

    if remaining > 0:
        ba_rows = sb_svc.schema(SUPABASE_SCHEMA).table("creditbuckets").select("*") \
            .eq("accountuid", accountuid).eq("servicecd", "Do").eq("creditchargecd", "Ba") \
            .order("startdt", desc=True).limit(1).execute().data or []
        if not ba_rows:
            raise Exception(f"크레딧 마이너스 반영 대상 Ba 버킷을 찾을 수 없습니다 (accountuid={accountuid})")
        _write_creditbucketuse(sb_svc, ba_rows[0], remaining, tenantid, accountuid, refuid, usetypecd)


def _true_success_count(sb_svc, job_col: str, jobuid: str) -> int:
    """genobjectlogs에서 is_success=true인 genobjectuid의 distinct 개수를 직접 센다.
    job_col은 genobjectlogs에도 동일한 이름의 컬럼(genchapterjobuid/gendocjobuid)으로 존재한다."""
    rows = sb_svc.schema(SUPABASE_SCHEMA).table("genobjectlogs").select("genobjectuid") \
        .eq(job_col, jobuid).eq("is_success", True).execute().data or []
    return len({r["genobjectuid"] for r in rows if r.get("genobjectuid")})


# log_table별 상위(부모) 테이블·식별 컬럼 — count 확정 후 usecredit을 되써주기 위함
_PARENT_INFO = {
    "genchapterlogs": {"parent_table": "genchapters", "parent_uid_col": "genchapteruid"},
    "gendoclogs": {"parent_table": "gendocs", "parent_uid_col": "gendocuid"},
}


def _apply_credit_deduction(sb_svc, log_table: str, job_col: str, jobuid: str, usetypecd: str) -> None:
    """챕터/문서 생성 완료 후 크레딧 차감 공통 로직.

    log_table(genchapterlogs 또는 gendoclogs)에서 job_col(=genchapterjobuid 또는
    gendocjobuid)=jobuid, is_credituse=true, applieddts IS NULL인 로그를 소진시켜
    creditbuckets를 차감한다.

    주의: log_table.count(트리거가 `SELECT COUNT(*) FROM genobjectlogs ...`로 계산해
    넣는 값)는 신뢰하지 않는다. 동일 genobjectuid가 재처리/재upsert되면서 genobjectlogs에
    is_success=true 로그가 중복으로 여러 번 남는 경우가 있어(2026-07-24 실측: distinct
    objectuid 4개인데 COUNT(*)는 7~8까지 올라감), count 컬럼은 실제보다 부풀려질 수 있다.
    대신 genobjectlogs를 직접 조회해 is_success=true인 genobjectuid의 distinct 개수를
    스스로 재계산해 실제 필요 크레딧으로 사용한다(_true_success_count). 처리 후에는 이렇게
    계산한 실제값을 log_table.count와 상위 테이블(genchapters/gendocs).usecredit에도
    되써서, 나중에 creditbucketuses·log_table.count·상위테이블.usecredit 세 값이 서로
    어긋나지 않도록 정리한다.

    로그가 여러 건 있으면(예: 생성 도중 createfiledts가 여러 번 갱신되는 경로가 있는 경우)
    logdts가 가장 최근인 로그 1건을 대표로 삼아 creditbucketuses.refuid로 사용한다.

    이미 같은 loguid(refuid)로 일부/전부 차감된 이력이 있으면 그만큼을 뺀 '남은 필요량'만
    마저 처리한다 — 이전 실행이 중간에 실패해 재시도되는 경우에도 중복 차감을 막기 위함.
    """
    parent_info = _PARENT_INFO[log_table]
    parent_uid_col = parent_info["parent_uid_col"]

    logs = sb_svc.schema(SUPABASE_SCHEMA).table(log_table).select(
        f"loguid,logdts,accountuid,tenantid,{parent_uid_col}"
    ).eq(job_col, jobuid).eq("is_credituse", True).is_("applieddts", "null").execute().data or []

    if not logs:
        return

    all_loguids = [r["loguid"] for r in logs]
    final_log = max(logs, key=lambda r: r.get("logdts") or "")
    final_loguid = final_log["loguid"]
    accountuid = final_log.get("accountuid")
    tenantid = final_log.get("tenantid")
    parent_uid = final_log.get(parent_uid_col)
    total_needed = _true_success_count(sb_svc, job_col, jobuid)

    if not accountuid:
        _close_logs(sb_svc, log_table, all_loguids, total_needed)
        return

    already_charged_rows = sb_svc.schema(SUPABASE_SCHEMA).table("creditbucketuses").select("usecredit") \
        .eq("refuid", final_loguid).execute().data or []
    already_charged = sum(r.get("usecredit") or 0 for r in already_charged_rows)

    remaining = total_needed - already_charged
    if remaining > 0:
        _deduct_credit(sb_svc, accountuid, tenantid, remaining, refuid=final_loguid, usetypecd=usetypecd)

    _close_logs(sb_svc, log_table, all_loguids, total_needed)

    if parent_uid:
        sb_svc.schema(SUPABASE_SCHEMA).table(parent_info["parent_table"]).update({
            "usecredit": total_needed,
        }).eq(parent_uid_col, parent_uid).execute()


def apply_chapter_credit_deduction(sb_svc, genchapterjobuid: str) -> None:
    """챕터 생성 완료 후 크레딧 차감 (usetypecd='dc', refuid=genchapterlogs.loguid)."""
    _apply_credit_deduction(sb_svc, "genchapterlogs", "genchapterjobuid", genchapterjobuid, "dc")


def apply_doc_credit_deduction(sb_svc, gendocjobuid: str) -> None:
    """문서 생성 완료 후 크레딧 차감 (usetypecd='dd', refuid=gendoclogs.loguid)."""
    _apply_credit_deduction(sb_svc, "gendoclogs", "gendocjobuid", gendocjobuid, "dd")
