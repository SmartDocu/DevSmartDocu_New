import pandas as pd
import requests
from io import BytesIO
from utilsPrj.supabase_client import SUPABASE_SCHEMA


def process_data_excel(supabase, request, datauid, docid=None, gendoc_uid=None, all = None):
    Datas_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datas")
        .select("*")
        .eq("datauid", datauid)
        .execute()
    )
    excelurl = Datas_resp.data[0]['excelurl']

    response = requests.get(excelurl)
    response.raise_for_status()
    excel_data = BytesIO(response.content)
    if excelurl.lower().endswith('.csv'):
        try:
            df = pd.read_csv(excel_data)
        except UnicodeDecodeError:
            excel_data.seek(0)
            df = pd.read_csv(excel_data, encoding='cp949')
    else:
        df = pd.read_excel(excel_data)

    # 마스터 팝업용, 전체 데이터 필요
    if all:
        return df
    
    # docid, gendoc_uid 둘다 None ==> excel 데이터(master/datas_ex/)화면
    if docid is None and gendoc_uid is None:
        return df.head(5)   # 처음 5줄만 반환

    # docid는 있고 gendoc_uid만 None ==> 마스터 셋팅 화면
    if docid is not None and gendoc_uid is None:
        dataparamdtls_resp = supabase.schema(SUPABASE_SCHEMA) \
            .table("dataparamdtls") \
            .select("*") \
            .eq("docid", docid).eq("datauid", datauid) \
            .execute()

        dataparams_resp = supabase.schema(SUPABASE_SCHEMA) \
            .table("dataparams") \
            .select("*") \
            .eq("docid", docid) \
            .execute()

        df_dtls = pd.DataFrame(dataparamdtls_resp.data)
        df_params = pd.DataFrame(dataparams_resp.data)

        # operator 포함
        df_params = df_params[["paramuid", "samplevalue", "operator"]]

        df_dtls = df_dtls.merge(df_params, on="paramuid", how="left")

        filtered_df = df.copy()

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["samplevalue"]
            op = row.get("operator", "=")

            if col in filtered_df.columns and pd.notna(val):
                filtered_df = apply_filter(filtered_df, col, op, val)

        return filtered_df

    # docid는 None, gendoc_uid만 있음 ==> 실제 문서 실행 화면
    if docid is None and gendoc_uid is not None:
        # 1. gendoc_uid → docid
        gendocs_resp = supabase.schema(SUPABASE_SCHEMA).table("gendocs") \
            .select("docid").eq("gendocuid", gendoc_uid).single().execute()

        docid = gendocs_resp.data["docid"]

        # 2. dataparamdtls
        dataparamdtls_resp = supabase.schema(SUPABASE_SCHEMA).table("dataparamdtls") \
            .select("*").eq("docid", docid).eq("datauid", datauid).execute()
        df_dtls = pd.DataFrame(dataparamdtls_resp.data)

        # 3. gendoc_params (value)
        gendoc_params_resp = supabase.schema(SUPABASE_SCHEMA).table("gendoc_params") \
            .select("paramuid, paramvalue").eq("gendocuid", gendoc_uid).execute()
        df_gendoc = pd.DataFrame(gendoc_params_resp.data)
        df_gendoc = df_gendoc[["paramuid", "paramvalue"]]

        df_dtls = df_dtls.merge(df_gendoc, on="paramuid", how="left")

        filtered_df = df.copy()

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["paramvalue"]
            op = row.get("operator", "=")

            if col in filtered_df.columns and pd.notna(val):
                filtered_df = apply_filter(filtered_df, col, op, val)

        return filtered_df

def apply_filter(df, col, op, val):
    if col not in df.columns:
        return df
    
    # 숫자 비교 시 자동 변환
    try:
        val_numeric = float(val)
        df_col_numeric = pd.to_numeric(df[col], errors='coerce')
        val_to_use = val_numeric
        col_to_use = df_col_numeric
    except ValueError:
        # 숫자로 변환 불가 → 문자열 비교
        val_to_use = val
        col_to_use = df[col]
    
    if op == "=":
        return df[col_to_use == val_to_use]
    elif op == ">":
        return df[col_to_use > val_to_use]
    elif op == ">=":
        return df[col_to_use >= val_to_use]
    elif op == "<":
        return df[col_to_use < val_to_use]
    elif op == "<=":
        return df[col_to_use <= val_to_use]
    else:
        return df
