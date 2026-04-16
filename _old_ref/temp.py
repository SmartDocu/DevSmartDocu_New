import pandas as pd
import requests
from io import BytesIO
import json

from langchain_anthropic import ChatAnthropic

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.query_runner import run_query
from llm.ai_chain import create_python_code
from utilsPrj.crypto_helper import encrypt_value, decrypt_value

def run_data(request, datauid, query, gendoc_uid=None):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    Datas_resp = supabase.schema("smartdoc").table("datas").select("*").eq("datauid", datauid).execute()
    datasourcecd = Datas_resp.data[0]['datasourcecd']
    connectid = Datas_resp.data[0]['connectid']
    sourcedatauid = Datas_resp.data[0]['sourcedatauid']
    gensentence = Datas_resp.data[0]['gensentence']
    docid = Datas_resp.data[0]['docid']

    # 데이터가 db(쿼리)일 경우 : 쿼리 실행 후 DataFrame 반환
    if datasourcecd == "db":
        dbconnectors_resp = supabase.schema("smartdoc").table("dbconnectors").select("*").eq("connectid", connectid).execute()
        connecttype = dbconnectors_resp.data[0]['connecttype']
        
        return run_query(request, connecttype, query, connectid)
    
    # 데이터가 엑셀일 경우 : 엑셀 URL에서 직접 읽어서 DataFrame 반환
    if datasourcecd == "ex":
        # 1) gendoc_params 또는 dataparams 가져오기
        param_dict = {}

        if gendoc_uid:  # gendoc_uid 가 존재할 때
            gendoc_params_resp = (
                supabase.schema("smartdoc")
                .table("gendoc_params")
                .select("paramnm, paramvalue")
                .eq("gendocuid", gendoc_uid)
                .execute()
            ).data

            param_dict = {
                item["paramnm"]: item["paramvalue"]
                for item in gendoc_params_resp
                if item.get("paramnm")
            }

        else:  # gendoc_uid 가 없을 때 → docid 기반 dataparams 사용
            dataparams_resp = (
                supabase.schema("smartdoc")
                .table("dataparams")
                .select("paramnm, samplevalue")
                .eq("docid", docid)
                .execute()
            ).data

            param_dict = {
                item["paramnm"]: item["samplevalue"]
                for item in dataparams_resp
                if item.get("paramnm")
            }

        # 2) datacols 조회
        datacols_resp = (
            supabase.schema("smartdoc")
            .table("datacols")
            .select("querycolnm, paramnm")
            .eq("datauid", datauid)
            .execute()
        ).data

        # 3) datacols.paramnm 과 param_dict[paramnm] 매핑
        dataset = []

        for col in datacols_resp:
            col_paramnm = col.get("paramnm")
            querycolnm = col.get("querycolnm")

            # paramnm 이 없거나 paramvalue 가 없으면 스킵
            if not col_paramnm:
                continue

            paramvalue = param_dict.get(col_paramnm)

            # paramvalue 없는 데이터셋은 제외
            if paramvalue is None or paramvalue == "":
                continue

            dataset.append({
                "querycolnm": querycolnm,
                "paramnm": col_paramnm,
                "paramvalue": paramvalue
            })

        excelurl = Datas_resp.data[0]['excelurl']

        response = requests.get(excelurl)

        response.raise_for_status()
        excel_data = BytesIO(response.content)

        if excelurl.lower().endswith('.csv'):
            try:
                df = pd.read_csv(excel_data)  # 기본 utf-8
            except UnicodeDecodeError:
                excel_data.seek(0)  # 다시 읽기 위해 파일 포인터 초기화
                df = pd.read_csv(excel_data, encoding='cp949')
        else:
            df = pd.read_excel(excel_data)

        # dataset 기반 필터링 적용
        for item in dataset:
            col = item["querycolnm"]
            val = item["paramvalue"]

            # df 에 해당 컬럼이 있을 때만 필터링
            if col in df.columns:
                # 문자열/숫자 비교 오류 방지를 위해 str 비교
                df = df[df[col].astype(str) == str(val)]

        return df
    
    # 데이터가 AI일 경우  (원본 데이터(엑셀, 쿼리로 선언된 데이터 셋) + 입력한 스크립트를 이용하여 재집계)
    if datasourcecd == "df":
        SourceDatas_resp = supabase.schema("smartdoc").table("datas").select("*").eq("datauid", sourcedatauid).execute()
        sourcedatasourcecd = SourceDatas_resp.data[0]['datasourcecd']

        #원본 가져오기 (원본 데이터가 엑셀일 경우 엑셀을 읽어서 df에 담기)
        if sourcedatasourcecd == "ex":
            sourceexcelurl = SourceDatas_resp.data[0]['excelurl']

            # 1) gendoc_params 또는 dataparams 가져오기
            param_dict = {}

            if gendoc_uid:  # gendoc_uid 가 존재할 때
                gendoc_params_resp = (
                    supabase.schema("smartdoc")
                    .table("gendoc_params")
                    .select("paramnm, paramvalue")
                    .eq("gendocuid", gendoc_uid)
                    .execute()
                ).data

                param_dict = {
                    item["paramnm"]: item["paramvalue"]
                    for item in gendoc_params_resp
                    if item.get("paramnm")
                }

            else:  # gendoc_uid 가 없을 때 → docid 기반 dataparams 사용
                dataparams_resp = (
                    supabase.schema("smartdoc")
                    .table("dataparams")
                    .select("paramnm, samplevalue")
                    .eq("docid", docid)
                    .execute()
                ).data

                param_dict = {
                    item["paramnm"]: item["samplevalue"]
                    for item in dataparams_resp
                    if item.get("paramnm")
                }

            # 2) datacols 조회
            datacols_resp = (
                supabase.schema("smartdoc")
                .table("datacols")
                .select("querycolnm, paramnm")
                .eq("datauid", sourcedatauid)
                .execute()
            ).data

            # 3) datacols.paramnm 과 param_dict[paramnm] 매핑
            dataset = []

            for col in datacols_resp:
                col_paramnm = col.get("paramnm")
                querycolnm = col.get("querycolnm")

                # paramnm 이 없거나 paramvalue 가 없으면 스킵
                if not col_paramnm:
                    continue

                paramvalue = param_dict.get(col_paramnm)

                # paramvalue 없는 데이터셋은 제외
                if paramvalue is None or paramvalue == "":
                    continue

                dataset.append({
                    "querycolnm": querycolnm,
                    "paramnm": col_paramnm,
                    "paramvalue": paramvalue
                })


            response = requests.get(sourceexcelurl)
            response.raise_for_status()
            excel_data = BytesIO(response.content)
            df = pd.read_excel(excel_data)
    
            # dataset 기반 필터링 적용
            for item in dataset:
                col = item["querycolnm"]
                val = item["paramvalue"]

                # df 에 해당 컬럼이 있을 때만 필터링
                if col in df.columns:
                    # 문자열/숫자 비교 오류 방지를 위해 str 비교
                    df = df[df[col].astype(str) == str(val)]

        #원본 가져오기 (원본 데이터가 쿼리일 경우 쿼리 실행 후 결과를 df에 담기)
        if sourcedatasourcecd == "db":
            sourceconnectid = SourceDatas_resp.data[0]['connectid']
            sourcedbconnectors_resp = supabase.schema("smartdoc").table("dbconnectors").select("*").eq("connectid", sourceconnectid).execute()
            sourceconnecttype = sourcedbconnectors_resp.data[0]['connecttype']

            df = run_query(request, sourceconnecttype, query, sourceconnectid)
            # print("df", df)
        else:
            pass

        # 원본 데이터(df : 바로 위의 엑셀 혹은 쿼리 실행 결과가 저장된 데이터 셋) + 입력한 스크립트(gensentence)를 이용하여 재집계 후 재집계한 결과를 다시 df로 반환하는 부분
        # data_js = json.loads(request.body)
        # data_uid = data_js.get("datauid")

        table_name = "datacols"

        result_datacols = supabase.schema("smartdoc")\
            .table(table_name)\
            .select("querycolnm, dispcolnm")\
            .eq("datauid", datauid)\
            .execute()
        result_datacols = result_datacols.data

        column_dict = {item['querycolnm']: item['dispcolnm'] for item in result_datacols}

        user = request.session.get("user")
        project_id = user.get("projectid")
        
        llm_connect_info = supabase.schema("smartdoc")\
            .table("llmconnectors")\
            .select("llmmodelnm, encapikey")\
            .eq("projectid", project_id)\
            .execute()
        llm_connect_info = llm_connect_info.data

        llm_model = llm_connect_info[0]["llmmodelnm"]
        enc_api_key = llm_connect_info[0]["encapikey"]
        dec_api_key = decrypt_value(enc_api_key)

        llm = ChatAnthropic(
            anthropic_api_key=dec_api_key,
            model=llm_model,
            temperature=0,
            max_tokens=8192
        )

        df = create_python_code(llm, df, gensentence, column_dict, "DF")
        # df = create_python_code(df, gensentence, "DF")
        # print("DF: ", df.head())

        return df
    
    else:
        raise ValueError(f"지원하지 않는 원본입니다: {datasourcecd}")