"""LLM AI 설정/미리보기 라우터 (CA/SA/TA 항목)"""
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb, get_user
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA
from utilsPrj.crypto_helper import decrypt_value

router = APIRouter()

TABLE_NAME_MAP = {"CA": "charts", "SA": "sentences", "TA": "tables"}

DISPLAY_TYPES = {
    "CA": ["bar", "line", "pie", "scatter", "boxplot", "histogram", "dual_axis", "heatmap", "subplot"],
    "SA": ["simple_question", "summary", "report", "predict"],
    "TA": ["table"],
}

DISPLAY_TYPE_NAMES = {
    "bar": "막대그래프", "line": "선그래프", "pie": "원형그래프",
    "scatter": "산점도", "boxplot": "박스플롯", "histogram": "히스토그램",
    "dual_axis": "이중축", "heatmap": "히트맵", "subplot": "서브플롯",
    "simple_question": "단순 질의", "summary": "요약", "report": "보고서",
    "predict": "예측", "table": "테이블",
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
    """user_id와 users 테이블 기본 정보 반환.
    users 테이블 실제 컬럼: roleid, billingmodelcd, mydocid
    projectid/tenantid는 docs/projects 테이블을 통해 별도 조회 필요.
    """
    user_id = str(get_user(token).id)
    rows = sb.schema(SUPABASE_SCHEMA).table("users").select(
        "roleid, billingmodelcd, mydocid"
    ).eq("useruid", user_id).execute().data or []
    # 행이 없어도 user_id는 반환 (preview/save에서 user_id가 주로 필요)
    return user_id, rows[0] if rows else {}


def _get_llm_model(sb, projectid, tenantid):
    """Get LLM instance using project/tenant config."""
    def _fetch(table, cond):
        data = sb.schema(SUPABASE_SCHEMA).table(table).select("llmmodelnm, encapikey").match(cond).execute().data or []
        if data:
            return data[0].get("llmmodelnm"), data[0].get("encapikey")
        return None, None

    llm_model, enc_key = _fetch("projects", {"projectid": projectid})
    if not llm_model:
        llm_model, enc_key = _fetch("tenants", {"tenantid": tenantid})
    if not llm_model:
        models = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("llmmodelnm").eq("useyn", True).execute().data or []
        llm_model = random.choice(models)["llmmodelnm"]
        keys = sb.schema(SUPABASE_SCHEMA).table("llmapis").select("encapikey").eq("usetypecd", "R").eq("llmmodelnm", llm_model).execute().data or []
        enc_key = random.choice(keys)["encapikey"]

    dec_key = decrypt_value(enc_key)
    vendor_data = sb.schema(SUPABASE_SCHEMA).table("llmmodels").select("llmvendornm").eq("llmmodelnm", llm_model).execute().data or []
    vendor = vendor_data[0]["llmvendornm"] if vendor_data else "Anthropic"

    if vendor == "OpenAI":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=llm_model, api_key=dec_key, temperature=0, max_tokens=8192)
    elif vendor == "Google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=llm_model, temperature=0, google_api_key=dec_key, max_output_tokens=8192)
    else:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(anthropic_api_key=dec_key, model=llm_model, temperature=0, max_tokens=8192)


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
        #    users 테이블에는 projectid 컬럼 없음 (roleid, billingmodelcd, mydocid만 존재)
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
        prompts_rows = sb_svc.schema(SUPABASE_SCHEMA).table("prompts").select("*").eq(
            "objecttypecd", objecttypecd
        ).execute().data or []
        prompts = sorted(prompts_rows, key=lambda x: x.get("orderno", 999))

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/init] ❌ 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"llm/init 오류: {str(e)}")

    display_types = [
        {"value": dt, "label": DISPLAY_TYPE_NAMES.get(dt, dt)}
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
    ).eq("datauid", datauid).execute().data or []

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
    query = sb.schema(SUPABASE_SCHEMA).table("prompts").select("*").eq("objecttypecd", object_type)
    if displaytype:
        query = query.eq("displaytype", displaytype)
    rows = query.execute().data or []
    return {"prompts": [
        {
            "promptuid": p["promptuid"],
            "prompt_nm": p["promptnm"],
            "prompt_text": p["prompt"],
            "prompt_desc": p.get("desc", ""),
            "display_type": p.get("displaytype", ""),
        }
        for p in rows
    ]}


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
        get_full_chain, get_llm_model,
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
    if docid:
        doc_rows = sb.schema(SUPABASE_SCHEMA).table("docs").select("projectid").eq(
            "docid", docid
        ).execute().data or []
        if doc_rows:
            projectid = doc_rows[0].get("projectid")

    # ③ project → tenantid
    if projectid:
        proj_rows = sb.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq(
            "projectid", projectid
        ).execute().data or []
        if proj_rows:
            tenantid = proj_rows[0].get("tenantid")

    # ④ FakeLlmRequest — Django request.session 구조 모방
    req = FakeLlmRequest(
        token, user_id,
        projectid=projectid,
        tenantid=tenantid,
        docid=docid,
    )

    # ⑤ datas 조회 — datasourcecd 및 df 타입의 sourcedatauid 확인
    #    Django ai_create_dataframe 의 datasourcecd == "df" 분기 처리와 동일
    col_datauid = body.datauid   # column_dict 조회에 사용할 datauid (df이면 source로 교체)
    try:
        data_rows = sb.schema(SUPABASE_SCHEMA).table("datas").select(
            "datasourcecd, sourcedatauid"
        ).eq("datauid", body.datauid).execute().data or []
        if data_rows:
            datasourcecd = data_rows[0].get("datasourcecd", "")
            if datasourcecd == "df":
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

    # ⑦ 열이름 매핑 — df 타입은 sourcedatauid 기준 (Django ai_chain.py 참조)
    try:
        datacols = sb.schema(SUPABASE_SCHEMA).table("datacols").select(
            "querycolnm, dispcolnm"
        ).eq("datauid", col_datauid).execute().data or []
    except Exception:
        datacols = []
    column_dict = {r["querycolnm"]: r["dispcolnm"] for r in datacols}

    # ⑧ objecttypecd별 프롬프트 생성 — Django ai_llm_click_preview_button 동일
    if body.objecttypecd == "CA":
        prompt = get_charts_prompt(result_df, column_dict, body.prompt)
    elif body.objecttypecd == "SA":
        prompt = get_sentences_prompt(result_df, column_dict, body.prompt)
    elif body.objecttypecd == "TA":
        prompt = get_tables_prompt(result_df, column_dict, body.prompt)
    else:
        raise HTTPException(status_code=400, detail="잘못된 objecttypecd")

    # ⑨ LLM 모델 로드 — Django get_llm_model(request) 와 동일 함수 사용
    try:
        llm = get_llm_model(req)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/preview] ❌ LLM 모델 로드 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"LLM 모델 로드 오류: {str(e)}")

    # ⑩ 체인 실행 — Django full_chain.invoke 와 동일
    full_chain = get_full_chain(llm, result_df, prompt, body.prompt, column_dict, body.objecttypecd)
    try:
        response = full_chain.invoke({"question": body.prompt, "column_dict": column_dict})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[llm/preview] ❌ LLM 실행 오류:\n{tb}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"LLM 실행 오류: {str(e)}")

    if not isinstance(response, dict):
        raise HTTPException(status_code=500, detail="LLM 응답 형식 오류")

    # ⑪ 응답 포맷 — Django ai_llm_click_preview_button 반환 구조 동일
    status = response.get("status")
    if status == "chart_drawn":
        return {
            "message_type": "image",
            "image_data": response["image_bytes"],
            "question": response.get("question", ""),
        }
    elif status == "analysis_comment":
        return {"message_type": "text", "message": response.get("result", "")}
    elif status == "data_table":
        return {
            "message_type": "table",
            "data": response.get("result", []),
            "table_header_json": response.get("table_header_json", ""),
            "table_data_json": response.get("table_data_json", ""),
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
    from datetime import datetime
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
    now = datetime.now().isoformat()

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
