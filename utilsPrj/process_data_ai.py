import pandas as pd
import requests
from io import BytesIO
import json

from langchain_anthropic import ChatAnthropic

from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA
from utilsPrj.ai_chain import get_tables_prompt, create_python_code, get_full_chain, get_llm_model
from utilsPrj.process_data_db import process_data_db
from utilsPrj.process_data_excel import process_data_excel


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
        df = process_data_excel(supabase, request, sourcedatauid, docid, gendoc_uid, all)

    # 원본 가져오기 (DB)
    if sourcedatasourcecd == "db":
        df = process_data_db(supabase, request, sourcedatauid, docid, gendoc_uid, all)

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
        llm = get_llm_model(request)
        prompt = get_tables_prompt(df, column_dict, gensentence)
        full_chain = get_full_chain(llm, df, prompt, gensentence, column_dict, chain_mode)

        response = full_chain.invoke({
            "question": gensentence,
            "column_dict": column_dict
        })

        return pd.DataFrame(response["result"])

    except Exception as e:
        return pd.DataFrame()


def process_data_ai_preview(supabase, request, sourcedatauid, gensentence, docid=None, gendoc_uid=None, all=None):
    return _process_data_ai_core(
        supabase, request, sourcedatauid, gensentence, "DF_PREVIEW",
        docid, gendoc_uid, all
    )


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

    return _process_data_ai_core(
        supabase, request, sourcedatauid, gensentence, "DF",
        docid, gendoc_uid, all
    )