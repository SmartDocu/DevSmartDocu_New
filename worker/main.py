import boto3
import io
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from backend.app.config import settings
from utilsPrj.supabase_client import get_thread_supabase, get_service_client, SUPABASE_SCHEMA
from utilsPrj.chapter_making import replace_doc
from utilsPrj.html_to_docx import html_to_docx_merge


class FakeRequest:
    def __init__(self, access_token: str, user_id: str, docid: Optional[int] = None,
                 tenantid=None, projectid=None):
        self.session = {
            "access_token": access_token,
            "refresh_token": None,
            "user": {
                "id": user_id,
                "docid": str(docid) if docid else None,
                "tenantid": tenantid,
                "projectid": projectid,
            },
        }
        self.method = "POST"


def _build_context(sb, variables: list, req, docid) -> dict:
    from utilsPrj.process_data_ai import process_data_ai_preview
    context = {}
    for v in variables:
        find = sb.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("datanm", v).eq("dfv_docid", docid).eq("datasourcecd", "dfv").execute().data
        if not find:
            continue
        sourcedatauid = find[0]["sourcedatauid"]
        datas = process_data_ai_preview(sb, req, sourcedatauid, find[0]["gensentence"], docid=docid)
        df = datas.get("result")
        if df is not None and not df.empty:
            datacols = sb.schema(SUPABASE_SCHEMA).table("datacols").select("querycolnm,dispcolnm").eq("datauid", sourcedatauid).execute().data
            disp_to_query = {item["dispcolnm"]: item["querycolnm"] for item in datacols}
            enriched = []
            for rec in df.to_dict("records"):
                row = dict(rec)
                for disp, query in disp_to_query.items():
                    if disp in rec:
                        row[query] = rec[disp]
                enriched.append(row)
            context[f"@{v}"] = enriched
            logger.info("_build_context: @%s %d건, 컬럼=%s, 샘플=%s", v, len(enriched), list(enriched[0].keys()) if enriched else [], enriched[0] if enriched else {})
        else:
            logger.warning("_build_context: @%s 데이터 비어있음 (sourcedatauid=%s)", v, sourcedatauid)
    return context


def _upsert_genobjects(sb, extracted: list, genchapteruid: str, chapteruid: str, user_id: str):
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = []
    for item in extracted:
        obj = sb.schema(SUPABASE_SCHEMA).table("objects").select("*").eq("objectnm", item["objectNm"]).execute().data
        if not obj:
            logger.warning("_upsert_genobjects: objectnm '%s' not found", item["objectNm"])
            continue
        rows.append({
            "genobjectuid": str(uuid.uuid4()),
            "genchapteruid": genchapteruid,
            "chapteruid": chapteruid,
            "objectuid": obj[0]["objectuid"],
            "objecttypecd": obj[0].get("objecttypecd"),
            "filterjson": item["params"],
            "replacestring": item["replacestring"],
            "creator": user_id,
            "createdts": now_iso,
        })
    if rows:
        sb.schema(SUPABASE_SCHEMA).table("genobjects").delete().eq("genchapteruid", genchapteruid).execute()
        sb.schema(SUPABASE_SCHEMA).table("genobjects").insert(rows).execute()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

SQS_QUEUE_URL = settings.SQS_QUEUE_URL
SQS_CHAPTER_QUEUE_URL = settings.SQS_CHAPTER_QUEUE_URL
AWS_REGION = settings.AWS_REGION


def _upsert_queue(sb_svc, gendocuid, docid, gendocnm, job_status_cd, *,
                  error_cd=None, error_msg=None, start_dts=None, end_dts=None, creator=None):
    row = {
        "gendocuid": gendocuid,
        "docid": docid,
        "gendocnm": gendocnm,
        "jobstatuscd": job_status_cd,
    }
    if error_cd is not None:
        row["errorcd"] = error_cd
    if error_msg is not None:
        row["errormessage"] = str(error_msg)[:2000]
    if start_dts is not None:
        row["startdts"] = start_dts
    if end_dts is not None:
        row["enddts"] = end_dts
    if creator is not None:
        row["creator"] = creator
    sb_svc.schema(SUPABASE_SCHEMA).table("gendocs_realtimes").upsert(row, on_conflict="gendocuid").execute()


def _upsert_chapter_queue(sb_svc, genchapteruid, docid, chapteruid, job_status_cd, *,
                          error_cd=None, error_msg=None, start_dts=None, end_dts=None, creator=None):
    row = {
        "genchapteruid": genchapteruid,
        "docid": docid,
        "chapteruid": chapteruid,
        "jobstatuscd": job_status_cd,
    }
    if error_cd is not None:
        row["errorcd"] = error_cd
    if error_msg is not None:
        row["errormessage"] = str(error_msg)[:2000]
    if start_dts is not None:
        row["startdts"] = start_dts
    if end_dts is not None:
        row["enddts"] = end_dts
    if creator is not None:
        row["creator"] = creator
    sb_svc.schema(SUPABASE_SCHEMA).table("genchapters_realtimes").upsert(row, on_conflict="genchapteruid").execute()


def _add_page_number(paragraph):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    fld.append(run)
    t = OxmlElement("w:t")
    t.text = " "
    run.append(t)
    paragraph._element.append(fld)


def _add_total_pages(paragraph):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "NUMPAGES")
    run = OxmlElement("w:r")
    fld.append(run)
    t = OxmlElement("w:t")
    t.text = " "
    run.append(t)
    paragraph._element.append(fld)


def process_message(msg):
    body = json.loads(msg["Body"])
    gendocuid = body["gendocuid"]
    user_id = body["user_id"]
    access_token = body["access_token"]
    results = body["results"]
    docid = body.get("docid")
    tenantid = body.get("tenantid")
    projectid = body.get("projectid")
    gendocnm = body.get("gendocnm", "")
    receipt_handle = msg["ReceiptHandle"]

    sb = get_thread_supabase(access_token=access_token)
    sb_svc = get_service_client()
    sqs = boto3.client("sqs", region_name=AWS_REGION)

    start_iso = datetime.now(timezone.utc).isoformat()
    _upsert_queue(sb_svc, gendocuid, docid, gendocnm, "S", start_dts=start_iso, creator=user_id)
    logger.info("처리 시작: %s", gendocuid)

    try:
        from utilsPrj.template_parser import process_template, FunctionRegistry, extract_at_variables
        from utilsPrj.template_extracter import extract_from_processed_html
        from docx import Document

        req = FakeRequest(access_token, user_id, docid, tenantid=tenantid, projectid=projectid)
        total = len(results)

        # Phase 1: 챕터별 LLM 재작성
        completed = []
        for idx, chapter in enumerate(results, 1):
            genchapteruid = chapter["genchapteruid"]
            logger.info("Phase 1 (%d/%d): %s", idx, total, genchapteruid)

            _gc = sb.schema(SUPABASE_SCHEMA).table("genchapters").select("chapteruid,docid").eq("genchapteruid", genchapteruid).execute().data
            if _gc:
                _chapteruid = _gc[0]["chapteruid"]
                _chap = sb.schema(SUPABASE_SCHEMA).table("chapters").select("texttemplate").eq("chapteruid", _chapteruid).execute().data
                _tt = _chap[0]["texttemplate"] if _chap else ""
                _atv = extract_at_variables(_tt)
                _ctx = _build_context(sb, _atv["unique"], req, docid)
                _reg = FunctionRegistry()
                _reg.set_default(lambda name, ctx, params: f"{{{{{name}}}}}[{json.dumps(params, ensure_ascii=False)}]")
                _flat = process_template(_tt, _ctx, _reg, True)
                sb.schema(SUPABASE_SCHEMA).table("genchapters").upsert({"genchapteruid": genchapteruid, "flattexttemplate": _flat}).execute()
                _extracted = extract_from_processed_html(_flat)
                _upsert_genobjects(sb, _extracted, genchapteruid, _chapteruid, user_id)

            for progress_data in replace_doc(req, sb, user_id, genchapteruid, "create", "rewrite", "Not",
                                              genChapterDirectYn=False, divide="Chapter", doc_write=True):
                if progress_data.get("type") == "progress" and progress_data.get("explain") == "현재 챕터 생성 완료":
                    completed.append(genchapteruid)

        if len(completed) != total:
            raise RuntimeError(f"일부 챕터 처리 실패 ({len(completed)}/{total})")

        # Phase 2: DOCX 병합
        logger.info("Phase 2: DOCX 병합 (%s)", gendocuid)
        comp_doc = Document()
        previous_yn = current_yn = False

        for i, chapter in enumerate(results, 1):
            genchapteruid = chapter["genchapteruid"]
            response = None
            for result in replace_doc(req, sb, user_id, genchapteruid, "create", "write", "Not",
                                       genChapterDirectYn=False, divide="Doc"):
                if result.get("type") == "complete":
                    response = result.get("texttemplate")
                    break
            if not response:
                raise RuntimeError(f"챕터 {genchapteruid} 데이터 로드 실패")
            previous_yn, current_yn = html_to_docx_merge(sb, comp_doc, genchapteruid, response, i, previous_yn, current_yn)

        for section in comp_doc.sections:
            footer = section.footer
            if footer.paragraphs:
                p = footer.paragraphs[0]
                p.add_run(" | Page ")
            else:
                p = footer.add_paragraph("Page ")
            _add_page_number(p)
            p.add_run(" / ")
            _add_total_pages(p)

        # Phase 3: Storage 업로드
        logger.info("Phase 3: Storage 업로드 (%s)", gendocuid)
        filenm = f"{uuid.uuid4()}.docx"
        path = f"result/{gendocuid}/{filenm}"

        try:
            old = sb.schema(SUPABASE_SCHEMA).table("gendocs").select("createfileurl").eq("gendocuid", gendocuid).execute().data
            if old and old[0].get("createfileurl"):
                parsed = urlparse(old[0]["createfileurl"])
                prefix = "/storage/v1/object/public/sdoc/"
                if prefix in parsed.path:
                    sb_svc.storage.from_("sdoc").remove([parsed.path.split(prefix)[-1]])
        except Exception:
            pass

        buf = io.BytesIO()
        comp_doc.save(buf)
        buf.seek(0)
        sb_svc.storage.from_("sdoc").upload(path, buf.read(), {"cacheControl": "3600", "upsert": "true"})
        public_url = sb_svc.storage.from_("sdoc").get_public_url(path)

        sb.schema(SUPABASE_SCHEMA).table("gendocs").update({
            "createfileurl": public_url,
            "createfiledts": datetime.now(timezone.utc).isoformat(),
            "createuserid": user_id,
        }).eq("gendocuid", gendocuid).execute()

        end_iso = datetime.now(timezone.utc).isoformat()
        _upsert_queue(sb_svc, gendocuid, docid, gendocnm, "E", end_dts=end_iso)
        logger.info("완료: %s", gendocuid)

    except Exception:
        logger.exception("오류: %s", gendocuid)
        try:
            import traceback
            end_iso = datetime.now(timezone.utc).isoformat()
            _upsert_queue(sb_svc, gendocuid, docid, gendocnm, "E",
                          error_cd="ERR", error_msg=traceback.format_exc(), end_dts=end_iso)
        except Exception:
            logger.exception("큐 상태 업데이트 실패: %s", gendocuid)

    finally:
        try:
            sb.schema(SUPABASE_SCHEMA).table("genlocks").update({
                "doclocked": False,
                "docenddts": datetime.now(timezone.utc).isoformat(),
            }).eq("gendocuid", gendocuid).eq("genchapteruid", "").execute()
        except Exception:
            logger.exception("잠금 해제 실패: %s", gendocuid)
        try:
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
        except Exception:
            logger.exception("SQS 메시지 삭제 실패: %s", gendocuid)


def process_chapter_message(msg):
    body = json.loads(msg["Body"])
    genchapteruid = body["genchapteruid"]
    gendocuid = body["gendocuid"]
    chapteruid = body["chapteruid"]
    docid = body.get("docid")
    tenantid = body.get("tenantid")
    projectid = body.get("projectid")
    user_id = body["user_id"]
    access_token = body["access_token"]
    receipt_handle = msg["ReceiptHandle"]

    sb = get_thread_supabase(access_token=access_token)
    sb_svc = get_service_client()
    sqs = boto3.client("sqs", region_name=AWS_REGION)

    start_iso = datetime.now(timezone.utc).isoformat()
    _upsert_chapter_queue(sb_svc, genchapteruid, docid, chapteruid, "S", start_dts=start_iso, creator=user_id)
    logger.info("챕터 처리 시작: %s", genchapteruid)

    try:
        from utilsPrj.template_parser import process_template, FunctionRegistry, extract_at_variables
        from utilsPrj.template_extracter import extract_from_processed_html

        req = FakeRequest(access_token, user_id, docid, tenantid=tenantid, projectid=projectid)

        # 템플릿 처리 → flattexttemplate → genobjects
        _chap = sb.schema(SUPABASE_SCHEMA).table("chapters").select("texttemplate").eq("chapteruid", chapteruid).execute().data
        _tt = _chap[0]["texttemplate"] if _chap else ""
        _atv = extract_at_variables(_tt)
        _ctx = _build_context(sb, _atv["unique"], req, docid)
        _reg = FunctionRegistry()
        _reg.set_default(lambda name, ctx, params: f"{{{{{name}}}}}[{json.dumps(params, ensure_ascii=False)}]")
        _flat = process_template(_tt, _ctx, _reg, True)
        sb.schema(SUPABASE_SCHEMA).table("genchapters").upsert({"genchapteruid": genchapteruid, "flattexttemplate": _flat}).execute()
        _extracted = extract_from_processed_html(_flat)
        _upsert_genobjects(sb, _extracted, genchapteruid, chapteruid, user_id)

        # LLM 콘텐츠 생성
        for progress_data in replace_doc(req, sb, user_id, genchapteruid, "create", "rewrite", "Not",
                                          genChapterDirectYn=True, divide="Chapter"):
            if progress_data.get("type") == "error":
                raise Exception(progress_data.get("message", "콘텐츠 생성 오류"))

        try:
            sb.schema(SUPABASE_SCHEMA).table("gendoc_genchapters").insert({
                "gendocuid": gendocuid,
                "genchapteruid": genchapteruid,
                "creator": user_id,
                "createdts": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass

        end_iso = datetime.now(timezone.utc).isoformat()
        _upsert_chapter_queue(sb_svc, genchapteruid, docid, chapteruid, "E", end_dts=end_iso)
        logger.info("챕터 완료: %s", genchapteruid)

    except Exception:
        logger.exception("챕터 오류: %s", genchapteruid)
        try:
            import traceback
            end_iso = datetime.now(timezone.utc).isoformat()
            _upsert_chapter_queue(sb_svc, genchapteruid, docid, chapteruid, "E",
                                  error_cd="ERR", error_msg=traceback.format_exc(), end_dts=end_iso)
        except Exception:
            logger.exception("챕터 큐 상태 업데이트 실패: %s", genchapteruid)

    finally:
        try:
            sb.schema(SUPABASE_SCHEMA).table("genlocks").update({
                "chapterlocked": False,
                "chapterenddts": datetime.now(timezone.utc).isoformat(),
            }).eq("genchapteruid", genchapteruid).execute()
        except Exception:
            logger.exception("챕터 잠금 해제 실패: %s", genchapteruid)
        try:
            sqs.delete_message(QueueUrl=SQS_CHAPTER_QUEUE_URL, ReceiptHandle=receipt_handle)
        except Exception:
            logger.exception("SQS 챕터 메시지 삭제 실패: %s", genchapteruid)


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
    # 큐 URL이 설정된 핸들러만 스레드 시작 (미설정 큐는 건너뜀)
    queue_handlers = {
        SQS_QUEUE_URL:         process_message,
        SQS_CHAPTER_QUEUE_URL: process_chapter_message,
    }
    threads = [
        threading.Thread(target=poll_queue, args=(url, fn), daemon=True, name=f"worker-{url.split('/')[-1]}")
        for url, fn in queue_handlers.items()
        if url
    ]
    if not threads:
        logger.error("활성 SQS 큐 URL이 없습니다. 환경변수를 확인하세요.")
        return
    for t in threads:
        t.start()
    logger.info("SmartDocu Worker 시작 — %d개 큐 폴링 중", len(threads))
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
