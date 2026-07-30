import logging
import pandas as pd
import requests
from io import BytesIO
import json

from langchain_anthropic import ChatAnthropic

from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA
from utilsPrj.ai_chain import get_tables_prompt, create_python_code, get_full_chain, get_llm_info, build_langchain_llm
from utilsPrj.process_data_db import process_data_db
from utilsPrj.process_data_excel import process_data_excel
from utilsPrj.process_data_api import process_data_api

_logger = logging.getLogger(__name__)

def _apply_doc_param_filter(supabase, df, datauid, docid, gendoc_uid):
    """AI 재집계 원본(df)에 문서 매개변수(예: Drug B) 필터를 적용한다."""
    from utilsPrj.process_data_excel import apply_filter

    # 마스터 항목설정 화면 (docid만 있음) → docparams.samplevalue 사용
    if docid is not None and gendoc_uid is None:
        dtls = supabase.schema(SUPABASE_SCHEMA).table("docparamdtls") \
            .select("*").eq("docid", docid).eq("datauid", datauid).execute()
        params = supabase.schema(SUPABASE_SCHEMA).table("docparams") \
            .select("*").eq("docid", docid).execute()
        if not dtls.data or not params.data:
            return df
        df_dtls = pd.DataFrame(dtls.data).merge(
            pd.DataFrame(params.data)[["paramuid", "samplevalue", "operator"]],
            on="paramuid", how="left"
        )
        filtered = df.copy()
        for _, row in df_dtls.iterrows():
            col, val, op = row["querycolnm"], row["samplevalue"], row.get("operator", "=")
            if col in filtered.columns and pd.notna(val):
                filtered = apply_filter(filtered, col, op, val)
        return filtered

    # 실제 문서 생성 화면 (gendoc_uid만 있음) → gendoc_params.paramvalue 사용
    if docid is None and gendoc_uid is not None:
        resolved_docid = supabase.schema(SUPABASE_SCHEMA).table("gendocs") \
            .select("docid").eq("gendocuid", gendoc_uid).single().execute().data["docid"]
        dtls = supabase.schema(SUPABASE_SCHEMA).table("docparamdtls") \
            .select("*").eq("docid", resolved_docid).eq("datauid", datauid).execute()
        gp = supabase.schema(SUPABASE_SCHEMA).table("gendoc_params") \
            .select("paramuid, paramvalue").eq("gendocuid", gendoc_uid).execute()
        if not dtls.data or not gp.data:
            return df
        df_dtls = pd.DataFrame(dtls.data).merge(pd.DataFrame(gp.data), on="paramuid", how="left")
        filtered = df.copy()
        for _, row in df_dtls.iterrows():
            col, val = row["querycolnm"], row["paramvalue"]
            if col in filtered.columns and pd.notna(val):
                filtered = apply_filter(filtered, col, "=", val)
        return filtered

    return df


def _process_data_ai_core(supabase, request, sourcedatauid, gensentence, chain_mode, docid=None, gendoc_uid=None, all=None):
    """원본 데이터 조회 → column_dict 구성 → AI 체인 실행의 공통 로직"""

    # 원본 데이터 소스 유형 조회
    SourceDatas_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datas")
        .select("*")
        .eq("datauid", sourcedatauid)
        .execute()
    )
    sourcedatasourcecd = SourceDatas_resp.data[0]['datasourcecd']

    # 원본 가져오기 (엑셀)
    if sourcedatasourcecd == "ex":
        df = process_data_excel(supabase, request, sourcedatauid, docid, gendoc_uid, all=True)

    # 원본 가져오기 (DB)
    if sourcedatasourcecd == "db":
        df = process_data_db(supabase, request, sourcedatauid, docid, gendoc_uid, all=True)

    # 원본이 api 데이터 화면일 경우
    if sourcedatasourcecd == "api":
        df = process_data_api(supabase, sourcedatauid, gendoc_uid)

    df = _apply_doc_param_filter(supabase, df, sourcedatauid, docid, gendoc_uid)

    # AI 재집계
    result_datacols = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datacols")
        .select("querycolnm, dispcolnm")
        .eq("datauid", sourcedatauid)
        .execute()
    ).data

    column_dict = {
        item['querycolnm']: item['dispcolnm']
        for item in result_datacols
    }

    try:
        # jeff 20251224 수정할 부분
        if hasattr(request, "projectid"):
            _project_id = request.projectid
            _tenant_rows = supabase.schema(SUPABASE_SCHEMA).table("projects").select("tenantid").eq("projectid", _project_id).execute().data
            _tenant_id = _tenant_rows[0]["tenantid"] if _tenant_rows else None
            _user_id = None
        else:
            _user = request.session.get("user") or {}
            _project_id = _user.get("projectid")
            _tenant_id = _user.get("tenantid")
            _user_id = _user.get("id")
        _llm_model_nm, _dec_api_key, _vendor_name, _, _ = get_llm_info(
            project_id=_project_id, tenant_id=_tenant_id, user_uid=_user_id, service_code="Do",
        )
        llm = build_langchain_llm(_vendor_name, _dec_api_key, _llm_model_nm)
        prompt = get_tables_prompt(df, column_dict, gensentence)
        full_chain = get_full_chain(llm, df, prompt, gensentence, column_dict, chain_mode)

        response = full_chain.invoke({
            "question": gensentence,
            "column_dict": column_dict
        })

        return response

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("AI chain 실패 (sourcedatauid=%s): %s", sourcedatauid, e, exc_info=True)
        return {"status": "error", "result": pd.DataFrame(), "cols_info": None}


def process_data_ai_preview(supabase, request, sourcedatauid, gensentence, docid=None, gendoc_uid=None, all=None):
    response = _process_data_ai_core(
        supabase, request, sourcedatauid, gensentence, "DF_PREVIEW",
        docid, gendoc_uid, all
    )
    return {
        "result": pd.DataFrame(response["result"]) if response.get("result") is not None else pd.DataFrame(),
        "cols_info": response.get("cols_info")
    }


def process_data_ai(supabase, request, datauid, docid=None, gendoc_uid=None, all=None):
    Datas_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datas")
        .select("*")
        .eq("datauid", datauid)
        .execute()
    )
    sourcedatauid = Datas_resp.data[0]['sourcedatauid']
    gensentence = Datas_resp.data[0]['gensentence']

    response = _process_data_ai_core(
        supabase, request, sourcedatauid, gensentence, "DF",
        docid, gendoc_uid, all
    )
    result = response.get("result")
    return pd.DataFrame(result) if result is not None else pd.DataFrame()