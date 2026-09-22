"""d2insight 보고서 생성 전용 워커.

worker/main.py(d2doc 챕터/문서 생성)와는 별도 ECS 서비스로 배포된다(회사 방침상 d2doc과
d2insight는 큐-워커를 분리하기로 함) — 같은 컨테이너 이미지를 재사용하되, 이 파일을
실행 명령으로 지정한 태스크 정의(smartdocu-insight-worker)로 별도 서비스에서 띄운다.

d2insight의 DB 접근은 서비스 롤 기반(d2insight/db/supabase_client.py)이라 d2doc 워커처럼
요청자 access_token으로 스레드별 클라이언트를 만들 필요가 없다 — SQS 메시지에도 access_token을
싣지 않는다.
"""
import boto3
import json
import logging
import threading
import traceback

from backend.app.config import settings
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
from utilsPrj.notifications import create_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

SQS_INSIGHT_QUEUE_URL = settings.SQS_INSIGHT_QUEUE_URL
AWS_REGION = settings.AWS_REGION


def _update_insight_qa(sb_svc, qauid: str, job_status_cd: str, **fields) -> None:
    row = {"jobstatuscd": job_status_cd, **fields}
    sb_svc.schema(SUPABASE_SCHEMA).table("insight_qas").update(row).eq("qauid", qauid).execute()


def _restore_upload_handoff(session_id: str, upload_handoff_path: str) -> None:
    """업로드 데이터셋 중계 파일을 내려받아 이 프로세스의 ExcelServer에 주입한다.
    백엔드 프로세스 메모리에만 있던 업로드 데이터가 워커 프로세스에도 보이게 하는 용도."""
    import pickle
    from d2insight.db.supabase_client import get_client
    from utilsPrj.private_storage import resolve_template_bytes
    from d2insight.report.excel_registry import get_excel_server

    raw = resolve_template_bytes(get_client(), upload_handoff_path)
    datasets = pickle.loads(raw)
    get_excel_server().session_datasets[session_id] = datasets


def process_insight_message(msg):
    body = json.loads(msg["Body"])
    qauid = body["qauid"]
    session_id = body["session_id"]
    user_id = body.get("user_id")
    upload_handoff_path = body.get("upload_handoff_path")
    receipt_handle = msg["ReceiptHandle"]

    sb_svc = get_service_client()
    sqs = boto3.client("sqs", region_name=AWS_REGION)

    logger.info("보고서 생성 시작: %s", qauid)

    # SQS 재배달 중복 처리 방지 — 같은 qauid는 최초 한 번만 'S'→'P' 선점 성공
    # (worker/main.py의 genchapters_realtimes 선점 패턴과 동일)
    claim = sb_svc.schema(SUPABASE_SCHEMA).table("insight_qas") \
        .update({"jobstatuscd": "P"}) \
        .eq("qauid", qauid).eq("jobstatuscd", "S").execute()
    if not claim.data:
        logger.info("보고서 중복 처리 스킵 (이미 선점됨): %s", qauid)
        try:
            sqs.delete_message(QueueUrl=SQS_INSIGHT_QUEUE_URL, ReceiptHandle=receipt_handle)
        except Exception:
            logger.exception("SQS 메시지 삭제 실패 (중복 스킵): %s", qauid)
        return

    from d2insight import token_tracker
    token_tracker.reset()
    token_tracker.set_log_ctx({
        "qauid": qauid,
        "servicecd": "In",
        "tenant_id": body.get("tenant_id"),
        "project_id": body.get("project_id"),
        "session_uid": session_id,
        "creator": user_id,
        "account_uid": body.get("account_uid"),
    })

    try:
        if upload_handoff_path:
            _restore_upload_handoff(session_id, upload_handoff_path)

        from d2insight.chat.pipeline_runner import run_tool

        result = run_tool(
            body["tool"], body.get("target_month"), body.get("months_back", 3),
            intent=body.get("intent") or {},
            user_id=user_id, project_id=body.get("project_id"), tenant_id=body.get("tenant_id"),
            user_uid=user_id, account_uid=body.get("account_uid"), session_id=session_id,
        )

        answer_json = {
            "answer": result.get("answer", ""),
            "visualization_type": result.get("visualization_type", "none"),
            "table_html": result.get("table_html"),
            "applied_steps": result.get("applied_steps"),
            "analytic_uid": result.get("analytic_uid"),
        }
        # run_tool()은 데이터 조회 실패 등도 예외를 던지지 않고 answer에 실패 메시지만 담아
        # 정상 반환한다 — report_path(실제로 만들어진 md 파일명)가 있을 때만 진짜 성공이다.
        if result.get("report_path"):
            _update_insight_qa(
                sb_svc, qauid, "D",
                answer=json.dumps(answer_json, ensure_ascii=False),
                filenm=result.get("report_path"),
                fileurl=result.get("fileurl"),
            )
            logger.info("보고서 완료: %s", qauid)
            if user_id:
                create_notification(
                    sb_svc, category="insight", status="info",
                    title="보고서 생성 완료", message="요청하신 보고서 생성이 완료되었습니다.",
                    title_key="msg.notification.insight.completed.title",
                    message_key="msg.notification.insight.completed.body",
                    params={},
                    target_object="insight_qa", target_uid=qauid,
                    target_url="d2insight", target_useruid=user_id,
                )
        else:
            _update_insight_qa(sb_svc, qauid, "F", answer=json.dumps(answer_json, ensure_ascii=False))
            logger.info("보고서 실패(데이터 없음/처리 불가): %s", qauid)
            if user_id:
                create_notification(
                    sb_svc, category="insight", status="error",
                    title="보고서 생성 실패", message=result.get("answer") or "요청하신 보고서 생성에 실패했습니다.",
                    title_key="msg.notification.insight.failed.title",
                    message_key="msg.notification.insight.failed.body",
                    params={},
                    target_object="insight_qa", target_uid=qauid,
                    target_url="d2insight", target_useruid=user_id,
                )

    except Exception:
        logger.exception("보고서 생성 오류: %s", qauid)
        try:
            error_text = traceback.format_exc()[:2000]
            _update_insight_qa(
                sb_svc, qauid, "F",
                answer=json.dumps({"answer": "보고서 생성 중 오류가 발생했습니다.", "error": error_text}, ensure_ascii=False),
            )
            if user_id:
                create_notification(
                    sb_svc, category="insight", status="error",
                    title="보고서 생성 실패", message="요청하신 보고서 생성 중 오류가 발생했습니다.",
                    title_key="msg.notification.insight.failed.title",
                    message_key="msg.notification.insight.failed.body",
                    params={},
                    target_object="insight_qa", target_uid=qauid,
                    target_url="d2insight", target_useruid=user_id,
                )
        except Exception:
            logger.exception("보고서 상태 업데이트 실패: %s", qauid)

    finally:
        token_tracker.set_log_ctx(None)
        if upload_handoff_path:
            try:
                from d2insight.db.supabase_client import delete_from_storage
                delete_from_storage(upload_handoff_path)
            except Exception:
                logger.exception("업로드 중계 파일 삭제 실패: %s", upload_handoff_path)
        try:
            sqs.delete_message(QueueUrl=SQS_INSIGHT_QUEUE_URL, ReceiptHandle=receipt_handle)
        except Exception:
            logger.exception("SQS 메시지 삭제 실패: %s", qauid)


def poll_queue(queue_url, handler_fn):
    sqs = boto3.client("sqs", region_name=AWS_REGION)
    logger.info("큐 폴링 시작 — %s", queue_url)
    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
        )
        for msg in resp.get("Messages", []):
            try:
                handler_fn(msg)
            except Exception:
                logger.exception("메시지 처리 중 예외 [%s]", queue_url)


def main():
    if not SQS_INSIGHT_QUEUE_URL:
        logger.error("SQS_INSIGHT_QUEUE_URL이 설정되지 않았습니다.")
        return
    t = threading.Thread(
        target=poll_queue, args=(SQS_INSIGHT_QUEUE_URL, process_insight_message),
        daemon=True, name="insight-worker",
    )
    t.start()
    logger.info("d2insight Worker 시작")
    t.join()


if __name__ == "__main__":
    main()
