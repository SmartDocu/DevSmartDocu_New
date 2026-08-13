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


def offset_negative_ba_bucket(svc, *, tenantid: int, accountuid: str, servicecd: str,
                               new_bucket_subscriptionuid: str) -> None:
    """새로 구매한 크레딧 버킷(new_bucket_subscriptionuid)으로 기존 Ba(기본) 버킷의 마이너스를 상쇄한다.

    _deduct_credit()이 Do 서비스 버킷을 다 쓰고도 부족하면 Ba 버킷에 마이너스로 반영하는데(정상
    동작), 그 상태가 다음 Ba 충전(플랜 갱신/업그레이드) 전까지 계속 남아있는 문제가 있었다
    (2026-08-07 사용자 요청으로 추가) — 추가 크레딧을 구매하면 그 시점에 기존 마이너스를
    상쇄해주는 게 자연스럽다는 판단.

    Ba 버킷은 0으로 정리하고, 그 마이너스였던 만큼을 **새로 산 버킷에서 그대로 차감**한다
    (2026-08-07 수정 — 처음엔 새 버킷을 안 건드리는 방식이었으나, 빚을 실제로 갚는 것처럼
    새 버킷 잔액에서 빠지도록 변경). 새 버킷 잔액보다 빚이 크면 새 버킷도 마이너스가 될 수
    있다 — Ba 마이너스 반영 때와 동일하게 하한을 두지 않는다(빚이 남아있으면 그 사실이
    그대로 드러나야 함).

    servicecd='Do'인 경우에 한해(2026-08-07 추가), 상쇄 후 새 버킷이 0 이상이 됐을 때만
    accountservices를 PastDue→Active로 되돌린다 — 빚이 새 버킷으로 옮겨갔을 뿐 여전히
    마이너스면 PastDue를 유지한다. 다른 서비스(Ch/In 등)는 아직 이 상태 전환 정책이 적용
    전이라 손대지 않는다.
    """
    ba_rows = (
        svc.table("creditbuckets").select("*")
        .eq("tenantid", int(tenantid)).eq("accountuid", accountuid)
        .eq("servicecd", servicecd).eq("creditchargecd", "Ba")
        .order("startdt", desc=True).limit(1)
        .execute().data or []
    )
    if not ba_rows:
        return
    ba_bucket = ba_rows[0]
    ba_before = ba_bucket.get("remaincredit") or 0
    if ba_before >= 0:
        return

    offset_amount = -ba_before  # 양수로 변환한 상쇄액

    new_bucket_rows = (
        svc.table("creditbuckets").select("*")
        .eq("subscriptionuid", new_bucket_subscriptionuid)
        .limit(1).execute().data or []
    )
    if not new_bucket_rows:
        return
    new_bucket = new_bucket_rows[0]
    new_before = new_bucket.get("remaincredit") or 0
    new_after = new_before - offset_amount

    # Ba 쪽 — 마이너스 반영분을 0으로 되돌림(reversal), 새 버킷의 subscriptionuid를 refuid로 남겨 추적
    svc.table("creditbucketuses").insert({
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "subscriptionuid": ba_bucket["subscriptionuid"],
        "startdt": ba_bucket.get("startdt"),
        "usetypecd": "os",
        "refuid": new_bucket_subscriptionuid,
        "beforecredit": ba_before,
        "usecredit": ba_before,  # 음수 — 차감이 아니라 되돌림(상쇄)임을 구분
        "aftercredit": 0,
    }).execute()
    svc.table("creditbuckets").update({
        "remaincredit": 0,
    }).eq("subscriptionuid", ba_bucket["subscriptionuid"]).execute()

    # 새 버킷 쪽 — 그 마이너스였던 만큼을 실제로 차감, refuid는 상쇄 대상이었던 Ba 버킷을 가리킴
    svc.table("creditbucketuses").insert({
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "subscriptionuid": new_bucket["subscriptionuid"],
        "startdt": new_bucket.get("startdt"),
        "usetypecd": "os",
        "refuid": ba_bucket["subscriptionuid"],
        "beforecredit": new_before,
        "usecredit": offset_amount,
        "aftercredit": new_after,
    }).execute()
    svc.table("creditbuckets").update({
        "usecredit": (new_bucket.get("usecredit") or 0) + offset_amount,
        "remaincredit": new_after,
    }).eq("subscriptionuid", new_bucket["subscriptionuid"]).execute()

    if servicecd == "Do" and new_after >= 0:
        svc.table("accountservices").update({
            "servicestatus": "Active",
        }).eq("accountuid", accountuid).eq("servicecd", servicecd).eq("servicestatus", "PastDue").execute()


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
                            refuid: str, usetypecd: str) -> int:
    """buckt 1개에서 use_amount만큼 차감 — creditbucketuses에 기록 후 creditbuckets 갱신.
    차감 후 remaincredit(after)을 반환한다 — 호출부에서 마이너스 전환 여부 판단에 사용."""
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
    return after


def is_byok_account(sb_svc, accountuid: str, servicecd: str = "Do") -> bool:
    """accountservices.is_customerAIKey 여부 — true면 고객이 자기 AI 키를 쓰는 BYOK 플랜이라
    플랫폼이 LLM 비용을 부담하지 않으므로 크레딧을 차감/차단하지 않는다(2026-08-13 추가)."""
    if not accountuid:
        return False
    row = sb_svc.schema(SUPABASE_SCHEMA).table("accountservices").select("is_customerAIKey") \
        .eq("accountuid", accountuid).eq("servicecd", servicecd).maybe_single().execute()
    return bool(row.data and row.data.get("is_customerAIKey"))


def _set_servicestatus_if(sb_svc, accountuid: str, servicecd: str, from_status: str, to_status: str) -> None:
    """accountservices.servicestatus를 from_status일 때만 to_status로 전환한다.

    WHERE절에 from_status 조건을 걸어 원자적으로 처리 — 관리자가 Suspended/Cancelled 등
    다른 사유로 이미 바꿔둔 상태는 건드리지 않는다(Active↔PastDue 왕복에만 관여)."""
    sb_svc.schema(SUPABASE_SCHEMA).table("accountservices").update({
        "servicestatus": to_status,
    }).eq("accountuid", accountuid).eq("servicecd", servicecd).eq("servicestatus", from_status).execute()


def _deduct_credit(sb_svc, accountuid: str, tenantid, amount: int, *, refuid: str, usetypecd: str) -> None:
    """servicecd='Do' 크레딧버킷에서 amount만큼 차감.
    우선순위: priorityno ASC, 동순위면 expiredts ASC(가장 빨리 만료되는 것부터 소진).
    유효 버킷을 다 써도 부족하면 남은 만큼 기준 서비스 구독(creditchargecd='Ba')에 마이너스로 반영한다
    (실제 사용량은 objects 예측치를 넘어설 수 있어 마이너스가 정상적으로 발생할 수 있음).
    이 마이너스 반영으로 Ba 버킷이 실제로 음수가 되면, accountservices.servicestatus를
    Active→PastDue로 전환한다(Do 서비스 한정, 2026-08-07 추가) — 이미 Active가 아니면(관리자가
    Suspended 등으로 바꿔둔 경우) 건드리지 않는다.

    BYOK(고객 자체 AI 키) 계정은 플랫폼이 LLM 비용을 부담하지 않으므로 차감하지 않는다
    (2026-08-13 추가)."""
    if amount <= 0:
        return
    if is_byok_account(sb_svc, accountuid, "Do"):
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
        after = _write_creditbucketuse(sb_svc, ba_rows[0], remaining, tenantid, accountuid, refuid, usetypecd)
        if after < 0:
            _set_servicestatus_if(sb_svc, accountuid, "Do", "Active", "PastDue")


def increment_genobjectcount(sb_svc, accountuid: str, tenantid, creator: str) -> None:
    """genobjectcounts에 시간당(1시간 버킷)+계정+creator별 사용량 1건 집계.

    단일 항목 재작성(gendocs.py _increment_genobjectcount)과 AI 정의/미리보기(llm.py)가
    공통으로 사용한다 — 두 액션 타입을 구분하지 않고 같은 count로 합산한다(동일 과금 정책).
    이 count는 sdoc.fn_apply_genobjectcount_credit() 배치가 그대로 소진 처리한다.
    """
    if not accountuid or tenantid is None:
        return

    now = datetime.now(timezone.utc)
    usedts = now.replace(minute=0, second=0, microsecond=0).isoformat()
    now_iso = now.isoformat()

    existing = sb_svc.schema(SUPABASE_SCHEMA).table("genobjectcounts").select("countuid,count") \
        .eq("accountuid", accountuid).eq("tenantid", tenantid).eq("usedts", usedts).eq("creator", creator).execute().data
    if existing:
        sb_svc.schema(SUPABASE_SCHEMA).table("genobjectcounts").update({
            "count": existing[0]["count"] + 1,
            "updatedts": now_iso,
        }).eq("countuid", existing[0]["countuid"]).execute()
    else:
        sb_svc.schema(SUPABASE_SCHEMA).table("genobjectcounts").insert({
            "countuid": str(uuid.uuid4()),
            "usedts": usedts,
            "accountuid": accountuid,
            "tenantid": tenantid,
            "creator": creator,
            "count": 1,
            "updatedts": now_iso,
        }).execute()


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
