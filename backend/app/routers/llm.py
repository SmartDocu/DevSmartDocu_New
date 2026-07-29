"""LLM AI 설정/미리보기 라우터 (CA/SA/TA 항목)"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb, get_user
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
from utilsPrj.ai_chain import get_llm_info, build_langchain_llm

router = APIRouter()

TABLE_NAME_MAP = {"CA": "charts", "SA": "sentences", "TA": "tables"}

DISPLAY_TYPES = {
    "CA": ["bar", "line", "pie", "scatter", "boxplot", "histogram", "dual_axis", "heatmap", "subplot"],
    "SA": ["simple_question", "summary", "report", "predict"],
    "TA": ["table"],
}


DISPLAY_TYPE_KEYS = {
    "bar":             "cod.ai_chart.bar",
    "line":            "cod.ai_chart.line",
    "pie":             "cod.ai_chart.pie",
    "scatter":         "cod.ai_chart.scatter",
    "boxplot":         "cod.ai_chart.boxplot",
    "histogram":       "cod.ai_chart.histogram",
    "dual_axis":       "cod.ai_chart.dual_axis",
    "heatmap":         "cod.ai_chart.heatmap",
    "subplot":         "cod.ai_chart.subplot",
    "simple_question": "cod.ai_sentence.simple_question",
    "summary":         "cod.ai_sentence.summary",
    "report":          "cod.ai_sentence.report",
    "predict":         "cod.ai_sentence.predict",
    "table":           "cod.ai_table.table",
}


class FakeLlmRequest:
    """Minimal Django-like request stub for utilsPrj compatibility."""
    def __init__(self, access_token: str, user_id: str, projectid=None, tenantid=None, docid=None):
        self.session = {
            "access_token": access_token,
            "refresh_token": None,
            "user": {
                "id": user_id,
                "projectid": projectid,
                "tenantid": tenantid,
                "docid": docid,
            },
        }
        self.POST = {}
        self.GET = {}
        self.method = "POST"


def _get_user_info(sb, token: str) -> tuple[str, dict]:
    """user_id와 users/serviceusers 테이블 기본 정보 반환.
    roleid: users 테이블, mydocid: serviceusers 테이블
    projectid/tenantid는 docs/projects 테이블을 통해 별도 조회 필요.
    """
    user_id = str(get_user(token).id)
    rows = sb.schema(SUPABASE_SCHEMA).table("users").select(
        "roleid"
    ).eq("useruid", user_id).execute().data or []
    info = rows[0] if rows else {}
    svc_rows = sb.schema(SUPABASE_SCHEMA).table("serviceusers").select(
        "mydocid"
    ).eq("useruid", user_id).eq("servicecd", "Do").execute().data or []
    if svc_rows:
        info["mydocid"] = svc_rows[0].get("mydocid")
    return user_id, info


def _get_llm_model(projectid, tenantid, user_id=None):
    """get_llm_info()로 LLM 설정을 조회해 (llm, is_customeraikey, account_uid)를 반환한다."""
    llm_model, dec_key, vendor_name, is_customeraikey, account_uid = get_llm_info(
        project_id=projectid, tenant_id=tenantid, user_uid=user_id, service_code="Do",
    )
    llm = build_langchain_llm(vendor_name, dec_key, llm_model)
    return llm, is_customeraikey, account_uid


# ── Init ──────────────────────────────────────────────────────────────────────

@router.get("/init")
def llm_init(
    chapteruid: str,
    objectnm: Optional[str] = None,
    objectuid: Optional[str] = None,
    objecttypecd: str = "CA",
    token: str = Depends(get_token),
):
    import traceback
    import sys

    try:
        # user JWT 클라이언트
        sb = get_sb(token)

        # ① 사용자 인증 (user_id만 필요)
        user_id = str(get_user(token).id)

        # ② chapters → docid 획득
        chapter_rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select(
            "chapteruid, chapternm, docid"
        ).eq("chapteruid", chapteruid).execute().data or []
        chapter = chapter_rows[0] if chapter_rows else {}

        # ③ docs → projectid (project_id는 오직 chapter.docid 경로로만 취득)
        #    users 테이블에는 projectid 컬럼 없음 (roleid, mydocid만 존재)
        docnm = ""
        project_id = None
        if chapter.get("docid"):
            doc_rows = sb.schema(SUPABASE_SCHEMA).table("docs").select(
                "docnm, projectid"
            ).eq("docid", chapter["docid"]).execute().data or []
            if doc_rows:
                docnm = doc_rows[0].get("docnm", "")
                project_id = doc_rows[0].get("projectid")

        # ④ objects
        obj_rows = sb.schema(SUPABASE_SCHEMA).table("objects").select(
            "objectuid, objectnm, objecttypecd"
        ).eq("chapteruid", chapteruid).eq("objecttypecd", objecttypecd).execute().data or []
        objects = sorted(obj_rows, key=lambda x: x.get("objectnm", ""))

        # ⑤ datas — projectid 기준 조회
        datas_rows = []
        if project_id:
            datas_rows = sb.schema(SUPABASE_SCHEMA).table("datas").select(
                "projectid, datauid, datanm, query"
            ).eq("projectid", project_id).execute().data or []
        datas = sorted(datas_rows, key=lambda x: x.get("datanm", ""))

        # ⑥ 기존 설정 (charts/sentences/tables)
        existing = {}
        table_name = TABLE_NAME_MAP.get(objecttypecd)
        if table_name:
            # objectuid를 직접 전달받은 경우 바로 사용, 없으면 objectnm으로 조회
            objectuid_val = objectuid
            if not objectuid_val and objectnm:
                obj_match = sb.schema(SUPABASE_SCHEMA).table("objects").select("objectuid").eq(
                    "chapteruid", chapteruid
                ).eq("objectnm", objectnm).execute().data or []
                if obj_match:
                    objectuid_val = obj_match[0]["objectuid"]
            if objectuid_val:
                ex_rows = sb.schema(SUPABASE_SCHEMA).table(table_name).select(
                    "gptq, datauid, displaytype"
                ).eq("objectuid", objectuid_val).execute().data or []
                if ex_rows:
                    existing = ex_rows[0]

        # ⑦ prompts — service client (공용 데이터)
        sb_svc = get_service_client()
        prompts_rows = sb_svc.schema(SUPABASE_SCHEMA).table("prompts").select(
            "promptkey, prompttypecd, tag1, tag2, datauid, orderno"
        ).eq("tag1", objecttypecd).eq("prompttypecd", "prm").execute().data or []
        prompts = sorted(prompts_rows, key=lambda x: x.get("orderno") or 999)

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/init] ❌ 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"llm/init 오류: {str(e)}")

    display_types = [
        {"value": dt, "term_key": DISPLAY_TYPE_KEYS.get(dt, "")}
        for dt in DISPLAY_TYPES.get(objecttypecd, [])
    ]

    return {
        "chapter": chapter,
        "docnm": docnm,
        "objects": objects,
        "datas": datas,
        "existing": existing,
        "prompts": prompts,
        "display_types": display_types,
    }


# ── Columns ───────────────────────────────────────────────────────────────────

@router.get("/columns")
def llm_get_columns(datauid: str, token: str = Depends(get_token)):
    sb = get_sb(token)
    rows = sb.schema(SUPABASE_SCHEMA).table("datacols").select(
        "querycolnm, dispcolnm, orderno"
    ).eq("datauid", datauid).eq("useyn", True).execute().data or []

    sorted_rows = sorted(
        [r for r in rows if r.get("orderno") is not None],
        key=lambda x: x["orderno"]
    ) or rows

    columns = [r["dispcolnm"] for r in sorted_rows]
    return {"columns": columns}


# ── Prompts ───────────────────────────────────────────────────────────────────

@router.get("/prompts")
def llm_get_prompts(
    object_type: str,
    displaytype: Optional[str] = None,
    token: str = Depends(get_token),
):
    sb = get_service_client()
    query = sb.schema(SUPABASE_SCHEMA).table("prompts").select(
        "promptkey, prompttypecd, tag1, tag2, datauid, orderno"
    ).eq("tag1", object_type).eq("prompttypecd", "prm")
    if displaytype:
        query = query.eq("tag2", displaytype)
    rows = query.execute().data or []
    return {"prompts": sorted(rows, key=lambda x: x.get("orderno") or 999)}


# ── Preview ───────────────────────────────────────────────────────────────────

class PreviewRequest(BaseModel):
    chapteruid: str
    objectnm: str
    datauid: str
    prompt: str
    displaytype: str
    objecttypecd: str


@router.post("/preview")
def llm_preview(body: PreviewRequest, token: str = Depends(get_token)):
    import traceback, sys

    from utilsPrj.process_data import process_data
    from utilsPrj.ai_chain import (
        get_charts_prompt, get_sentences_prompt, get_tables_prompt,
        get_full_chain, detect_date_type_issues,
    )

    sb = get_sb(token)
    user_id, _ = _get_user_info(sb, token)

    # ① chapter → docid
    chap_rows = sb.schema(SUPABASE_SCHEMA).table("chapters").select("docid").eq(
        "chapteruid", body.chapteruid
    ).execute().data or []
    docid = chap_rows[0]["docid"] if chap_rows else None

    # ② doc → projectid
    projectid = None
    tenantid = None
    docnm = ""
    if docid:
        doc_rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid, docnm").eq(
            "docid", docid
        ).execute().data or []
        if doc_rows:
            projectid = doc_rows[0].get("projectid")
            docnm = doc_rows[0].get("docnm", "")

    # ③ project → tenantid
    if projectid:
        proj_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq(
            "projectid", projectid
        ).execute().data or []
        if proj_rows:
            tenantid = proj_rows[0].get("tenantid")

    # objectuid 조회 (llmdoclogs.objectuid 용)
    objectuid = None
    try:
        obj_uid_rows = sb.schema(SUPABASE_SCHEMA).table("objects").select("objectuid").eq(
            "chapteruid", body.chapteruid
        ).eq("objectnm", body.objectnm).execute().data or []
        objectuid = obj_uid_rows[0]["objectuid"] if obj_uid_rows else None
    except Exception:
        pass

    # ④ FakeLlmRequest — Django request.session 구조 모방
    req = FakeLlmRequest(
        token, user_id,
        projectid=projectid,
        tenantid=tenantid,
        docid=docid,
    )

    # ⑤ datas 조회 — datasourcecd 및 df/dfv 타입의 sourcedatauid 확인
    #    Django ai_create_dataframe 의 datasourcecd in ("df", "dfv") 분기 처리와 동일
    col_datauid = body.datauid   # column_dict 조회에 사용할 datauid (df/dfv이면 source로 교체)
    try:
        data_rows = sb.schema(SUPABASE_SCHEMA).table("datas").select(
            "datasourcecd, sourcedatauid"
        ).eq("datauid", body.datauid).execute().data or []
        if data_rows:
            datasourcecd = data_rows[0].get("datasourcecd", "")
            if datasourcecd in ("df", "dfv"):
                source_uid = data_rows[0].get("sourcedatauid")
                if source_uid:
                    col_datauid = source_uid
    except Exception as e:
        print(f"[llm/preview] datas 조회 경고: {e}", file=sys.stderr, flush=True)

    # ⑥ DataFrame 로드 — Django process_data() 와 동일 경로
    try:
        result_df = process_data(req, body.datauid, docid)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/preview] ❌ process_data 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=400, detail=f"데이터 조회 오류: {str(e)}")

    # ⑥-1 데이터 타입 검증 — 결과에 영향을 줄 수 있는 값(예: 존재하지 않는 날짜) 탐지
    data_warnings = detect_date_type_issues(result_df)

    # ⑦ 열이름 매핑 — df 타입은 sourcedatauid 기준 (Django ai_chain.py 참조)
    try:
        datacols = sb.schema(SUPABASE_SCHEMA).table("datacols").select(
            "querycolnm, dispcolnm"
        ).eq("datauid", col_datauid).execute().data or []
    except Exception:
        datacols = []
    column_dict = {r["querycolnm"]: r["dispcolnm"] for r in datacols}

    # ⑧ objecttypecd별 프롬프트 생성 — Django ai_llm_click_preview_button 동일
    # ai_filter_json = {}
    if body.objecttypecd == "CA":
        prompt = get_charts_prompt(result_df, column_dict, body.prompt)
    elif body.objecttypecd == "SA":
        prompt = get_sentences_prompt(result_df, column_dict, body.prompt)
    elif body.objecttypecd == "TA":
        prompt = get_tables_prompt(result_df, column_dict, body.prompt)
    else:
        raise HTTPException(status_code=400, detail="잘못된 objecttypecd")

    # ⑨ LLM 모델 로드
    try:
        llm, is_customeraikey, account_uid = _get_llm_model(projectid, tenantid, user_id)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/preview] ❌ LLM 모델 로드 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"LLM 모델 로드 오류: {str(e)}")

    from d2shared.llm_logger import log_doc_llm_call

    def _write_doc_log(is_success, errormessage, inputtoken, outputtoken, start_dts, end_dts):
        log_doc_llm_call(
            log_ctx={
                "tenant_id":         tenantid,
                "account_uid":       account_uid,
                "project_id":        projectid,
                "gencontenttypecd":  None,  # 단독(Definition) 미리보기 — 챕터/문서 생성 잡과 무관
                "objectuid":         objectuid,
                "is_customeraikey":  is_customeraikey,
                "creator":           user_id,
            },
            llmmodelnm=getattr(llm, "model", None) or getattr(llm, "model_name", None) or "",
            inputtoken=inputtoken,
            outputtoken=outputtoken,
            is_success=is_success,
            errormessage=errormessage,
            startdts=start_dts,
            enddts=end_dts,
        )

    # ⑩ 체인 실행 — Django full_chain.invoke 와 동일
    full_chain = get_full_chain(llm, result_df, prompt, body.prompt, column_dict, body.objecttypecd)
    _llm_start_dts = datetime.now(timezone.utc)
    try:
        response = full_chain.invoke({"question": body.prompt, "column_dict": column_dict})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/preview] ❌ LLM 실행 오류:\n{tb}", file=sys.stderr, flush=True)
        _write_doc_log(False, str(e), 0, 0, _llm_start_dts, datetime.now(timezone.utc))
        raise HTTPException(status_code=500, detail=f"LLM 실행 오류: {str(e)}")
    _llm_end_dts = datetime.now(timezone.utc)

    if not isinstance(response, dict):
        _write_doc_log(False, "LLM 응답 형식 오류", 0, 0, _llm_start_dts, _llm_end_dts)
        raise HTTPException(status_code=500, detail="LLM 응답 형식 오류")

    # ⑪ 응답 포맷 — Django ai_llm_click_preview_button 반환 구조 동일
    status = response.get("status")

    _tokens = response.get("tokens", {})
    _is_success = status in ("chart_drawn", "analysis_comment", "data_table")
    _write_doc_log(
        _is_success,
        None if _is_success else str(response.get("error") or status),
        _tokens.get("input_tokens", 0),
        _tokens.get("output_tokens", 0),
        _llm_start_dts,
        _llm_end_dts,
    )

    if status == "chart_drawn":
        return {
            "message_type": "image",
            "image_data": response["image_bytes"],
            "question": response.get("question", ""),
            "data_warnings": data_warnings,
        }
    elif status == "analysis_comment":
        return {
            "message_type": "text",
            "message": response.get("result", ""),
            "data_warnings": data_warnings,
        }
    elif status == "data_table":
        return {
            "message_type": "table",
            "data": response.get("result", []),
            "table_header_json": response.get("table_header_json", ""),
            "table_data_json": response.get("table_data_json", ""),
            "data_warnings": data_warnings,
        }
    elif status == "error":
        raise HTTPException(status_code=500, detail=response.get("error", "LLM 오류"))
    else:
        raise HTTPException(status_code=500, detail=f"알 수 없는 LLM 응답 status: {response.get('status')}")


# ── Save ──────────────────────────────────────────────────────────────────────

class SaveRequest(BaseModel):
    chapteruid: str
    objectnm: str
    datauid: str
    gptq: str
    displaytype: str
    objecttypecd: str


@router.post("/save")
def llm_save(body: SaveRequest, token: str = Depends(get_token)):
    from datetime import datetime, timezone
    sb = get_sb(token)
    user_id, _ = _get_user_info(sb, token)

    table_name = TABLE_NAME_MAP.get(body.objecttypecd)
    if not table_name:
        raise HTTPException(status_code=400, detail="잘못된 objecttypecd")

    # Get objectuid
    obj_rows = sb.schema(SUPABASE_SCHEMA).table("objects").select("objectuid, creator").eq(
        "chapteruid", body.chapteruid
    ).eq("objectnm", body.objectnm).execute().data or []
    if not obj_rows:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")

    object_uid = obj_rows[0]["objectuid"]
    object_creator = obj_rows[0]["creator"]
    now = datetime.now(timezone.utc).isoformat()

    # Check existing
    existing = sb.schema(SUPABASE_SCHEMA).table(table_name).select("datauid").eq(
        "chapteruid", body.chapteruid
    ).eq("objectnm", body.objectnm).execute().data or []

    if existing:
        sb.schema(SUPABASE_SCHEMA).table(table_name).update({
            "gentypecd": "AI",
            "displaytype": body.displaytype,
            "gptq": body.gptq,
            "datauid": body.datauid,
        }).eq("chapteruid", body.chapteruid).eq("objectnm", body.objectnm).execute()
    else:
        sb.schema(SUPABASE_SCHEMA).table(table_name).insert({
            "objectuid": object_uid,
            "chapteruid": body.chapteruid,
            "objectnm": body.objectnm,
            "datauid": body.datauid,
            "gentypecd": "AI",
            "displaytype": body.displaytype,
            "gptq": body.gptq,
            "creator": object_creator,
            "createdts": now,
        }).execute()

    # Update objects.objectsettingyn
    sb.schema(SUPABASE_SCHEMA).table("objects").update({
        "objectsettingyn": True,
        "useyn": True,
        "modifier": user_id,
        "modifydts": now,
    }).eq("objectuid", object_uid).execute()

    return {"success": True}


# ── Delete ────────────────────────────────────────────────────────────────────

class DeleteRequest(BaseModel):
    chapteruid: str
    objectnm: str
    objecttypecd: str


@router.delete("/delete")
def llm_delete(body: DeleteRequest, token: str = Depends(get_token)):
    sb = get_sb(token)
    table_name = TABLE_NAME_MAP.get(body.objecttypecd)
    if not table_name:
        raise HTTPException(status_code=400, detail="잘못된 objecttypecd")

    sb.schema(SUPABASE_SCHEMA).table(table_name).delete().eq(
        "chapteruid", body.chapteruid
    ).eq("objectnm", body.objectnm).execute()

    return {"success": True}


# ── Experience (공개 체험 — 인증 불필요) ──────────────────────────────────────

@router.get("/experience/columns")
def experience_columns(datauid: str):
    """공개 체험 페이지용 열이름 조회 (인증 불필요)"""
    sb_svc = get_service_client()
    rows = sb_svc.schema(SUPABASE_SCHEMA).table("datacols").select(
        "querycolnm, dispcolnm, orderno"
    ).eq("datauid", datauid).execute().data or []
    sorted_rows = sorted(
        [r for r in rows if r.get("orderno") is not None],
        key=lambda x: x["orderno"],
    ) or rows
    return {"columns": [r["dispcolnm"] for r in sorted_rows]}


@router.get("/experience/prompts")
def experience_prompts():
    """로그인 없이 접근 가능한 체험 페이지용 샘플 프롬프트 목록"""
    import sys, traceback
    try:
        sb_svc = get_service_client()
        rows = sb_svc.schema(SUPABASE_SCHEMA).table("prompts").select("*").order("orderno").execute().data or []
        datas = sb_svc.schema(SUPABASE_SCHEMA).table("datas").select("datauid, datanm").order("datanm").execute().data or []
        return {
            "prompts": rows,
            "datas": datas,
            "chart_types": [{"value": v, "term_key": DISPLAY_TYPE_KEYS[v]} for v in DISPLAY_TYPES["CA"]],
            "sentence_types": [{"value": v, "term_key": DISPLAY_TYPE_KEYS[v]} for v in DISPLAY_TYPES["SA"]],
            "table_types": [{"value": v, "term_key": DISPLAY_TYPE_KEYS[v]} for v in DISPLAY_TYPES["TA"]],
        }
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/experience/prompts] 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExperiencePreviewRequest(BaseModel):
    prompt: str
    objecttypecd: str
    datauid: Optional[str] = None
    displaytype: Optional[str] = None


@router.post("/experience/preview")
def experience_preview(body: ExperiencePreviewRequest):
    """로그인 없이 접근 가능한 체험 페이지용 LLM 미리보기"""
    import traceback, sys

    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="프롬프트를 입력해주세요.")
    if not body.datauid:
        raise HTTPException(status_code=400, detail="데이터를 선택해주세요.")

    from utilsPrj.process_data import process_data
    from utilsPrj.ai_chain import (
        get_charts_prompt, get_sentences_prompt, get_tables_prompt,
        get_full_chain,
    )
    from utilsPrj.supabase_client import SUPABASE_SERVICE_ROLE_KEY

    sb_svc = get_service_client()

    data_rows = sb_svc.schema(SUPABASE_SCHEMA).table("datas").select(
        "projectid, datasourcecd, sourcedatauid"
    ).eq("datauid", body.datauid).execute().data or []

    projectid = data_rows[0].get("projectid") if data_rows else None
    tenantid = None
    if projectid:
        proj_rows = sb_svc.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq(
            "projectid", projectid
        ).execute().data or []
        if proj_rows:
            tenantid = proj_rows[0].get("tenantid")

    col_datauid = body.datauid
    if data_rows and data_rows[0].get("datasourcecd") == "df":
        col_datauid = data_rows[0].get("sourcedatauid") or body.datauid

    req = FakeLlmRequest(
        SUPABASE_SERVICE_ROLE_KEY,
        "00000000-0000-0000-0000-000000000000",
        projectid=projectid,
        tenantid=tenantid,
        docid=None,
    )

    try:
        result_df = process_data(req, body.datauid, None)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[experience/preview] process_data 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=400, detail=f"데이터 조회 오류: {str(e)}")

    try:
        datacols = sb_svc.schema(SUPABASE_SCHEMA).table("datacols").select(
            "querycolnm, dispcolnm"
        ).eq("datauid", col_datauid).execute().data or []
    except Exception:
        datacols = []
    column_dict = {r["querycolnm"]: r["dispcolnm"] for r in datacols}

    ot = body.objecttypecd
    if ot == "CA":
        prompt = get_charts_prompt(result_df, column_dict, body.prompt)
    elif ot == "SA":
        prompt = get_sentences_prompt(result_df, column_dict, body.prompt)
    elif ot == "TA":
        prompt = get_tables_prompt(result_df, column_dict, body.prompt)
    else:
        raise HTTPException(status_code=400, detail="잘못된 objecttypecd")

    try:
        llm, _, _ = _get_llm_model(projectid, tenantid)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[experience/preview] LLM 모델 로드 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"LLM 모델 로드 오류: {str(e)}")

    full_chain = get_full_chain(llm, result_df, prompt, body.prompt, column_dict, ot)
    try:
        response = full_chain.invoke({"question": body.prompt, "column_dict": column_dict})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[experience/preview] LLM 실행 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"LLM 실행 오류: {str(e)}")

    if not isinstance(response, dict):
        raise HTTPException(status_code=500, detail="LLM 응답 형식 오류")

    status_val = response.get("status")
    if status_val == "chart_drawn":
        return {"message_type": "image", "image_data": response["image_bytes"],
                "question": response.get("question", "")}
    elif status_val == "analysis_comment":
        return {"message_type": "text", "message": response.get("result", "")}
    elif status_val == "data_table":
        return {"message_type": "table", "message": "",
                "data": response.get("result", ""),
                "table_header_json": response.get("table_header_json", ""),
                "table_data_json": response.get("table_data_json", "")}
    else:
        return {"message_type": "error", "message": "알 수 없는 응답 형식입니다."}
