"""콘텐츠 삭제 배치 — Pro 해지 3택 중 '90일 유예 후 삭제'/'즉시 삭제'가 실제로 확정된
accountservices 행(servicestatus='Archived')의 하위 콘텐츠를 물리 삭제한다.

payments.py의 run_billing_cycle()과 동일한 패턴: 로그인 세션이 아닌 X-Purge-Secret 헤더로
인증하고, AWS EventBridge Scheduler가 주기적으로 호출하는 것을 전제로 설계됨(스케줄 자체는
아직 미등록 — 파괴적 배치라 최종 점검 전에는 트리거하지 않는다).

BILLING_CRON_SECRET을 재사용하지 않고 별도 PURGE_CRON_SECRET을 쓰는 이유: 결제 배치는
실패해도 재시도/롤백이 가능하지만 이 배치는 하드 DELETE라 되돌릴 수 없다 — 시크릿 하나가
유출됐을 때의 피해 범위(blast radius)를 분리해둔다."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from backend.app.config import settings
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client
from utilsPrj.private_storage import build_private_path, delete_private_prefix
from utilsPrj.notifications import create_notification
from utilsPrj.audit_log import log_work_action

router = APIRouter()
logger = logging.getLogger(__name__)

# 프로젝트 관례상 자동화 배치 작업의 creator/useruid 플레이스홀더(payments.py:SYSTEM_USER_ID와 동일 값)
_SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


def _chunked(items: list, size: int = 500):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _select_in(sd, table: str, select_col: str, id_col: str, ids: list) -> list:
    if not ids:
        return []
    out = []
    for chunk in _chunked(ids):
        out.extend(sd.table(table).select(select_col).in_(id_col, chunk).execute().data or [])
    return out


def _bulk_delete(sd, table: str, col: str, ids: list) -> None:
    for chunk in _chunked(ids):
        if chunk:
            sd.table(table).delete().in_(col, chunk).execute()


def _is_personal_tenant(sd, tenantid: int) -> bool:
    """개인(시스템) 테넌트 여부. 개인 영역은 모든 개인 사용자가 같은 tenantid(시스템 테넌트)를 공유하므로,
    tenantid만으로 하위 데이터를 찾으면 다른 사용자의 데이터까지 지우게 된다 — 반드시 계정(accountuid) 기준으로 좁혀야 한다."""
    row = sd.table("tenants").select("issystemtenant").eq("tenantid", tenantid).maybe_single().execute()
    # 조회 실패/없음은 "개인"으로 취급 — 범위를 넓히는 쪽이 아니라 좁히는 쪽으로 안전하게 실패한다
    return bool(row.data.get("issystemtenant", True)) if row and row.data else True


def _scope_project_ids(sd, accountuid: str, tenantid: int, servicecd: str, personal: bool) -> list:
    """삭제 대상 프로젝트 id. 개인: 이 계정의 프로젝트만(projects.accountuid). 조직: 테넌트의 해당 서비스 프로젝트 전부."""
    q = sd.table("projects").select("projectid").eq("servicecd", servicecd)
    q = q.eq("accountuid", accountuid) if personal else q.eq("tenantid", tenantid)
    return [p["projectid"] for p in (q.execute().data or [])]


def _purge_do_service_content(sd, accountuid: str, tenantid: int, personal: bool) -> dict:
    """docs.py:delete_doc()/chapters.py:delete_chapter()는 이미 cascade가 불완전해서(고아 데이터
    남기는 기존 버그) 재사용하지 않고, 여기서 자식→부모 순으로 직접 순회 삭제한다.
    datasets/project_datasets/dataunits(datas) 계열은 프로젝트가 아니라 테넌트 전체가
    공유하는 리소스라 이번 삭제 대상에서 제외한다."""
    projectids = _scope_project_ids(sd, accountuid, tenantid, "Do", personal)
    if not projectids:
        return {"projects": 0}

    docids = [d["docid"] for d in _select_in(sd, "docs", "docid", "projectid", projectids)]
    chapteruids = [c["chapteruid"] for c in _select_in(sd, "chapters", "chapteruid", "docid", docids)]
    objectuids = [o["objectuid"] for o in _select_in(sd, "objects", "objectuid", "chapteruid", chapteruids)]
    gendocuids = [g["gendocuid"] for g in _select_in(sd, "gendocs", "gendocuid", "docid", docids)]
    genchapteruids = [g["genchapteruid"] for g in _select_in(sd, "genchapters", "genchapteruid", "gendocuid", gendocuids)]
    objectfilteruids = [f["objectfilteruid"] for f in _select_in(sd, "objectfilters", "objectfilteruid", "objectuid", objectuids)]

    _bulk_delete(sd, "genlocks", "gendocuid", gendocuids)
    # _bulk_delete(sd, "gendoc_genchapters", "gendocuid", gendocuids)    # jeff 20261013
    _bulk_delete(sd, "genobjects", "genchapteruid", genchapteruids)
    _bulk_delete(sd, "genchapters_realtimes", "genchapteruid", genchapteruids)
    _bulk_delete(sd, "gendocs_realtimes", "gendocuid", gendocuids)
    _bulk_delete(sd, "gendoc_params", "gendocuid", gendocuids)
    _bulk_delete(sd, "genchapters", "gendocuid", gendocuids)
    _bulk_delete(sd, "gendocs", "docid", docids)
    _bulk_delete(sd, "doc_objectcounts", "docid", docids)
    _bulk_delete(sd, "doc_datas", "docid", docids)
    _bulk_delete(sd, "objectfiltermaps", "objectfilteruid", objectfilteruids)
    _bulk_delete(sd, "objectfilters", "objectuid", objectuids)
    # sentences/charts/tables는 objectuid가 아니라 chapteruid+objectnm으로 연결됨
    _bulk_delete(sd, "sentences", "chapteruid", chapteruids)
    _bulk_delete(sd, "charts", "chapteruid", chapteruids)
    _bulk_delete(sd, "tables", "chapteruid", chapteruids)
    _bulk_delete(sd, "objects", "chapteruid", chapteruids)
    _bulk_delete(sd, "chapters", "docid", docids)
    _bulk_delete(sd, "docparamdtls", "docid", docids)
    _bulk_delete(sd, "docparams", "docid", docids)
    _bulk_delete(sd, "docs", "docid", docids)
    # 문서 그룹(프로젝트별 분류 이름) — docs보다 먼저 지우면 docs.docgroupid가 끊기므로 문서 삭제 뒤에, 프로젝트 기준으로 지운다
    docgroupids = [g["docgroupid"] for g in _select_in(sd, "docgroups", "docgroupid", "projectid", projectids)]
    _bulk_delete(sd, "docgroups", "docgroupid", docgroupids)

    deleted_files = delete_private_prefix(get_service_client(), build_private_path(accountuid, "Doc"))

    return {
        "projects": len(projectids), "docs": len(docids), "docgroups": len(docgroupids), "chapters": len(chapteruids),
        "objects": len(objectuids), "gendocs": len(gendocuids), "genchapters": len(genchapteruids),
        "storage_files_deleted": deleted_files,
    }


def _purge_ch_service_content(sd, accountuid: str, tenantid: int, personal: bool) -> dict:
    """chat_sessions/chat_qas는 projects를 거치지 않고 tenantid를 직접 갖고 있어(Do와 달리)
    바로 스코핑한다. Chat은 자체 파일을 스토리지에 올리지 않으므로(기존 데이터셋/DB 커넥터를
    조회만 함) Storage 정리는 불필요."""
    if personal:
        # 개인 영역: 이 계정의 Chat 프로젝트에 속한 세션만(시스템 테넌트의 다른 사용자 세션은 절대 건드리지 않는다)
        projectids = _scope_project_ids(sd, accountuid, tenantid, "Ch", True)
        sessionuids = [s["sessionuid"] for s in _select_in(sd, "chat_sessions", "sessionuid", "projectid", projectids)]
    else:
        sessions = sd.table("chat_sessions").select("sessionuid").eq("tenantid", tenantid).execute().data or []
        sessionuids = [s["sessionuid"] for s in sessions]
    if not sessionuids:
        return {"sessions": 0}

    shareuids = [s["shareuid"] for s in _select_in(sd, "chat_session_shares", "shareuid", "sessionuid", sessionuids)]

    _bulk_delete(sd, "chat_snapshots", "sessionuid", sessionuids)
    _bulk_delete(sd, "chat_session_share_users", "shareuid", shareuids)
    _bulk_delete(sd, "chat_session_shares", "sessionuid", sessionuids)
    _bulk_delete(sd, "chat_favorites", "sessionuid", sessionuids)
    _bulk_delete(sd, "llmchatlogs", "sessionuid", sessionuids)
    _bulk_delete(sd, "chat_qas", "sessionuid", sessionuids)
    _bulk_delete(sd, "chat_sessions", "sessionuid", sessionuids)

    return {"sessions": len(sessionuids)}


def _purge_in_service_content(sd, accountuid: str, tenantid: int, personal: bool) -> dict:
    """insight_sessions도 tenantid를 직접 갖고 있어 바로 스코핑한다. analytics/analyticsteps/
    analyticmodules는 세션이 아니라 tenantid+projectid 단위로만 연결되므로 tenantid로 직접
    정리하고, insight_folders(테넌트별 보고서 폴더)도 동일하게 tenantid 스코프로 정리한다."""
    if personal:
        # 개인 영역: 이 계정의 Insight 프로젝트에 속한 세션/분석만. insight_folders는 프로젝트 연결이 없는
        # 테넌트 공용 데이터라 개인 영역에서는 건드리지 않는다(다른 사용자 폴더 보호).
        projectids = _scope_project_ids(sd, accountuid, tenantid, "In", True)
        sessionuids = [s["sessionuid"] for s in _select_in(sd, "insight_sessions", "sessionuid", "projectid", projectids)]
        analyticuids = [a["analyticuid"] for a in _select_in(sd, "analytics", "analyticuid", "projectid", projectids)]
    else:
        sessions = sd.table("insight_sessions").select("sessionuid").eq("tenantid", tenantid).execute().data or []
        sessionuids = [s["sessionuid"] for s in sessions]
        analyticuids = [a["analyticuid"] for a in sd.table("analytics").select("analyticuid").eq(
            "tenantid", tenantid).execute().data or []]

    _bulk_delete(sd, "analyticmodules", "analyticuid", analyticuids)
    _bulk_delete(sd, "analyticsteps", "analyticuid", analyticuids)
    _bulk_delete(sd, "analytics", "analyticuid", analyticuids)
    _bulk_delete(sd, "analytictemplates", "sessionuid", sessionuids)
    _bulk_delete(sd, "insightscheduleshares", "sessionuid", sessionuids)
    _bulk_delete(sd, "insight_qa_shares", "sessionuid", sessionuids)
    _bulk_delete(sd, "insight_favorites", "sessionuid", sessionuids)
    _bulk_delete(sd, "llminsightlogs", "sessionuid", sessionuids)
    _bulk_delete(sd, "insight_qas", "sessionuid", sessionuids)
    _bulk_delete(sd, "insight_sessions", "sessionuid", sessionuids)
    if not personal:
        _bulk_delete(sd, "insight_folders", "tenantid", [tenantid])

    deleted_files = delete_private_prefix(get_service_client(), build_private_path(accountuid, "Insight"))

    return {"sessions": len(sessionuids), "analytics": len(analyticuids), "storage_files_deleted": deleted_files}


def _purge_accountservice_content(sd, accsvc_row: dict) -> dict:
    accountuid = accsvc_row["accountuid"]
    tenantid = accsvc_row["tenantid"]
    servicecd = accsvc_row["servicecd"]

    personal = _is_personal_tenant(sd, tenantid)
    if servicecd == "Do":
        detail = _purge_do_service_content(sd, accountuid, tenantid, personal)
    elif servicecd == "Ch":
        detail = _purge_ch_service_content(sd, accountuid, tenantid, personal)
    elif servicecd == "In":
        detail = _purge_in_service_content(sd, accountuid, tenantid, personal)
    else:
        detail = {"note": f"알 수 없는 servicecd={servicecd} — 상태만 전이"}

    sd.table("accountservices").update({
        "servicestatus": "Deleted",
        "purge_immediate": False,
    }).eq("accountuid", accountuid).eq("servicecd", servicecd).execute()

    subscriptionuid = accsvc_row.get("subscriptionuid")
    if subscriptionuid:
        sd.table("subscriptions").update({
            "subscription_status": "Cancelled",
        }).eq("subscriptionuid", subscriptionuid).execute()

    log_work_action(
        useruid=_SYSTEM_USER_ID, tenantid=tenantid, servicecd=servicecd,
        actioncd="delete", targettype="content-purge/service", targetid=accountuid,
        after={"servicestatus": "Deleted", "scope": "account" if personal else "tenant", **detail},
    )

    _lock_tenant_if_fully_deleted(sd, accountuid, tenantid)

    return {"result": "purged", **detail}


def _delete_tenant_secret(tenantid: int) -> None:
    """AWS Secrets Manager의 기업 시크릿(커넥터 자격증명) 삭제. 테스트에서 가짜로 바꿀 수 있게 분리했다."""
    from utilsPrj.secrets_cache import delete_tenant_secret
    delete_tenant_secret(tenantid)


def _purge_tenant_residual_data(sd, tenantid: int) -> dict:
    """회사 기업이 완전히 잠기는 시점에, 서비스별 삭제(_purge_*_content)가 건드리지 않는 기업 소유의
    자격증명·데이터 소스 정의·설정을 삭제한다(2026-10-14 정책 확정). 반드시 회사 기업에만 호출할 것 —
    시스템 기업은 여러 개인이 공유하므로 tenantid 단위로 지우면 다른 사용자 데이터가 지워진다.

    삭제하지 않는 것: tenants/tenantusers/accounts/accountservices/subscriptions, 결제·크레딧·사용량 기록,
    projects/projectusers/serviceusers 행 자체(projects.encapikey 값만 비운다).
    스키마에 외래키가 거의 없어(13개, 이 테이블들과 무관) 삭제 순서 제약은 없다. 여러 번 실행해도 안전하다(멱등)."""
    connuids = [c["connuid"] for c in (sd.table("connectors").select("connuid").eq("tenantid", tenantid).execute().data or [])]
    datauids = [d["datauid"] for d in (sd.table("dataunits").select("datauid").eq("tenantid", tenantid).execute().data or [])]

    # 외부 저장소(AWS)의 자격증명을 가장 먼저 지운다 — 실패하면 예외로 올라가 DB 행이 그대로 남고 다음 배치가 재시도한다
    _delete_tenant_secret(tenantid)

    _bulk_delete(sd, "conn_api_credentials", "connuid", connuids)
    _bulk_delete(sd, "conn_apis", "tenantid", [tenantid])
    _bulk_delete(sd, "connectors", "tenantid", [tenantid])
    _bulk_delete(sd, "llmapikeys", "tenantid", [tenantid])
    sd.table("projects").update({"encapikey": None}).eq("tenantid", tenantid).execute()

    for child in ("datacols", "datacolvalues", "data_api_params", "data_chatmetas"):
        _bulk_delete(sd, child, "datauid", datauids)
    _bulk_delete(sd, "dataunits", "tenantid", [tenantid])
    _bulk_delete(sd, "datasetmembers", "tenantid", [tenantid])
    _bulk_delete(sd, "project_datasets", "tenantid", [tenantid])
    _bulk_delete(sd, "datasets", "tenantid", [tenantid])

    _bulk_delete(sd, "objectdefinitions", "tenantid", [tenantid])
    _bulk_delete(sd, "whitelists", "tenantid", [tenantid])
    _bulk_delete(sd, "config_tenants", "tenantid", [tenantid])

    return {"connectors": len(connuids), "dataunits": len(datauids)}


def _lock_tenant_if_fully_deleted(sd, accountuid: str, tenantid: int) -> None:
    """테넌트 해지가 신청된(tenants.cancel_requested_dt IS NOT NULL) 계정의 서비스가 방금
    Deleted로 전이됐다면, 이 계정의 accountservices가 전부 Deleted인지 확인하고 그렇다면
    기업 소유 자격증명·설정을 지운 뒤 테넌트 전체를 잠근다(tenants.useyn=False + 소속 tenantusers.useyn=False 일괄).
    삭제가 실패하면 잠그지 않고 돌아간다 — run_content_purge_cycle의 재시도 단계가 다음 배치에서 다시 부른다.
    tenants/accounts row 자체는 지우지 않는다 — Do 서비스 purge가 projects 컨테이너를
    안 지우는 것과 동일한 원칙(결제/감사 기록 보존)."""
    tenant_row = sd.table("tenants").select("tenantnm,cancel_requested_dt,useyn,issystemtenant").eq(
        "tenantid", tenantid
    ).maybe_single().execute()
    tenant = tenant_row.data if tenant_row else None
    if not tenant or not tenant.get("cancel_requested_dt") or not tenant.get("useyn", True):
        return
    # 시스템 기업은 개인 계정들이 공유한다 — 기업 단위 삭제·잠금 대상이 될 수 없다(못 읽으면 시스템으로 간주)
    if tenant.get("issystemtenant", True):
        return

    remaining = sd.table("accountservices").select("servicecd").eq(
        "accountuid", accountuid
    ).neq("servicestatus", "Deleted").execute().data or []
    if remaining:
        return

    try:
        residual = _purge_tenant_residual_data(sd, tenantid)
    except Exception as e:
        logger.exception("기업 잔여 데이터 삭제 실패 tenantid=%s — 잠그지 않고 다음 배치에서 재시도", tenantid)
        log_work_action(
            useruid=_SYSTEM_USER_ID, tenantid=tenantid, servicecd="Tenant",
            actioncd="delete", targettype="content-purge/tenant-residual-error", targetid=str(tenantid),
            detail={"error": str(e)[:500]},
        )
        return
    log_work_action(
        useruid=_SYSTEM_USER_ID, tenantid=tenantid, servicecd="Tenant",
        actioncd="delete", targettype="content-purge/tenant-residual", targetid=str(tenantid),
        after=residual,
    )

    # useyn=False로 잠그기 전에 현재 활성 멤버 목록을 먼저 구해서 전원에게 최종 알림을 보낸다
    # (신청 시점엔 매니저에게만 알림/이메일이 갔지만, 실제로 접근이 막히는 이 순간은 일반
    # 멤버에게도 알려야 한다 — 2026-09-03 보완).
    member_rows = sd.table("tenantusers").select("useruid").eq(
        "tenantid", tenantid
    ).eq("useyn", True).execute().data or []
    for row in member_rows:
        if not row.get("useruid"):
            continue
        create_notification(
            sd, category="plan", status="warning",
            title="테넌트 해지 완료",
            message=f"'{tenant.get('tenantnm', '')}' 테넌트가 완전히 삭제되어 더 이상 접근할 수 없습니다.",
            title_key="msg.notification.tenant_deleted.title", message_key="msg.notification.tenant_deleted.body",
            params={"tenantnm": tenant.get("tenantnm", "")},
            target_object="tenant", target_uid=accountuid,
            target_useruid=row["useruid"],
        )

    sd.table("tenants").update({"useyn": False}).eq("tenantid", tenantid).execute()
    sd.table("tenantusers").update({"useyn": False}).eq("tenantid", tenantid).execute()
    # 이 기업을 기본 기업으로 가진 사용자의 기본값을 비운다 — 안 비우면 다음 로그인이 잠긴 기업을 가리킨다
    # (로그인 쪽도 활성 소속이 아니면 무시하지만, 낡은 값을 남기지 않는다)
    sd.table("users").update({"default_tenantid": None}).eq("default_tenantid", tenantid).execute()

    log_work_action(
        useruid=_SYSTEM_USER_ID, tenantid=tenantid, servicecd="Tenant",
        actioncd="delete", targettype="content-purge/tenant-lock", targetid=str(tenantid),
        after={"useyn": False},
    )


@router.post("/run-purge-cycle")
def run_content_purge_cycle(request: Request):
    """Archived 상태(90일 경과 또는 purge_immediate=True)인 accountservices 행을 찾아
    실제로 하위 콘텐츠를 물리 삭제한다. AWS EventBridge Scheduler 전용 — 기본 DISABLED로
    두고 최종 점검 전에는 트리거하지 않는다."""
    secret = request.headers.get("x-purge-secret")
    if not settings.PURGE_CRON_SECRET or secret != settings.PURGE_CRON_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    cfg = sd.table("configs").select("userdatadelday").limit(1).execute()
    retention_days = (cfg.data[0].get("userdatadelday") if cfg.data else None) or 90
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

    due_immediate = sd.table("accountservices").select("*").eq(
        "servicestatus", "Archived").eq("purge_immediate", True).execute().data or []
    due_expired = sd.table("accountservices").select("*").eq(
        "servicestatus", "Archived").eq("purge_immediate", False).lte("archived_dt", cutoff).execute().data or []

    results = []
    for row in due_immediate + due_expired:
        try:
            result = _purge_accountservice_content(sd, row)
        except Exception as e:
            result = {"result": "error", "message": str(e)}
        results.append({"accountuid": row["accountuid"], "servicecd": row["servicecd"], **result})

    # 재시도 단계: 해지 신청이 있고 아직 잠기지 않은 회사 기업을 다시 확인한다. 서비스 삭제 시점에 기업 잔여 데이터
    # 삭제가 실패했거나, 가입한 서비스가 아예 없어 삭제로 잠글 계기가 없던 기업이 여기서 마무리된다(멱등).
    finalized = []
    pending = sd.table("tenants").select("tenantid,cancel_requested_dt").eq("issystemtenant", False).eq("useyn", True).execute().data or []
    for t in pending:
        if not t.get("cancel_requested_dt"):
            continue
        try:
            for acc in (sd.table("accounts").select("accountuid").eq("tenantid", t["tenantid"]).execute().data or []):
                _lock_tenant_if_fully_deleted(sd, acc["accountuid"], t["tenantid"])
            still = sd.table("tenants").select("useyn").eq("tenantid", t["tenantid"]).maybe_single().execute()
            if still and still.data and still.data.get("useyn") is False:
                finalized.append(t["tenantid"])
        except Exception as e:
            logger.exception("기업 잠금 재시도 실패 tenantid=%s", t["tenantid"])
            results.append({"tenantid": t["tenantid"], "result": "error", "message": str(e)})

    return {"processed": len(results), "results": results, "tenants_finalized": finalized}


@router.post("/run-audit-log-purge")
def run_audit_log_purge(request: Request):
    """plan별 보관기간(config_plans.audit_log_keep_days)이 지난 work_logs/login_logs를
    영구 삭제한다. 두 테이블 다 append-only 트리거가 걸려 있어 일반 DELETE로는 지울 수
    없어서, Supabase에 등록해둔 sdoc.fn_purge_expired_audit_logs()(트리거를 이 함수
    실행 중에만 비활성화하는 SECURITY DEFINER 함수, audit_log_retention_purge.sql 참고)를
    RPC로 호출해 처리한다. admin_action_logs는 전사 로그라 이 plan별 정책 대상이 아니라
    제외. AWS EventBridge Scheduler 전용 — 기본 DISABLED로 두고 최종 점검 전에는
    트리거하지 않는다."""
    secret = request.headers.get("x-purge-secret")
    if not settings.PURGE_CRON_SECRET or secret != settings.PURGE_CRON_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    result = sd.rpc("fn_purge_expired_audit_logs", {}).execute()
    return {"result": "success", **(result.data or {})}
