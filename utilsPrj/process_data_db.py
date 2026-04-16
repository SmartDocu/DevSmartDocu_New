import os
import pyodbc
from supabase import create_client
from decimal import Decimal
import pandas as pd

# from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA
from utilsPrj.supabase_client import get_supabase
from utilsPrj.crypto_helper import decrypt_value, encrypt_value
import re
from sqlalchemy import create_engine
import urllib
import oracledb

def process_data_db(supabase, request, datauid, docid=None, gendoc_uid=None, all = None):
    Datas_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datas")
        .select("*")
        .eq("datauid", datauid)
        .execute()
    )

    connectid = Datas_resp.data[0]['connectid']
    query = Datas_resp.data[0]['query']

    dbconnectors_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("dbconnectors")
        .select("*")
        .eq("connectid", connectid)
        .execute()
    )
    connecttype = dbconnectors_resp.data[0]['connecttype']

    # 마스터 팝업용, 전체 데이터 필요
    if all:
        if connecttype == "MSSQL":
            return process_data_db_mssql(request, query, connectid)

        elif connecttype == "SUPABASE":
            query_str = str(query)
            is_rpc = ".rpc(" in query_str

            if is_rpc:
                # 🔑 RPC: @변수는 더미값으로 치환
                if "@" in query_str:
                    query_str = replace_rpc_vars_with_dummy(query_str)

            query = query_str
            return process_data_db_supabase(request, query, connectid)
        
        elif connecttype == "ORACLE":
            return process_data_db_oracle(request, query, connectid)
    
    # docid, gendoc_uid 둘다 None ==> db 데이터(master/datas_db/)화면
    if docid is None and gendoc_uid is None:
        if connecttype == "MSSQL":
            pattern = re.compile(r"^\s*SELECT\s+(TOP\s+\d+)?", re.IGNORECASE)
            match = pattern.match(query)

            if match and not match.group(1):
                query = re.sub(
                    r"^\s*SELECT\s+",
                    "SELECT TOP 5 ",
                    query,
                    flags=re.IGNORECASE
                )

            return process_data_db_mssql(request, query, connectid, sampleyn=True)

        elif connecttype == "SUPABASE":
            query_str = str(query)
            is_rpc = ".rpc(" in query_str

            if is_rpc:
                # 🔑 RPC: @변수는 더미값으로 치환
                if "@" in query_str:
                    query_str = replace_rpc_vars_with_dummy(query_str)

            if not is_rpc:
                if ".limit(" not in query_str:
                    if ".execute()" in query_str:
                        query_str = query_str.replace(".execute()", ".limit(5).execute()", 1)
                    else:
                        query_str += ".limit(5)"

            query = query_str
            return process_data_db_supabase(request, query, connectid, sampleyn=True)
        
        elif connecttype == "ORACLE":
            if "fetch first" not in query.lower():
                query = f"""
                SELECT *
                FROM (
                    {query}
                )
                FETCH FIRST 5 ROWS ONLY
                """
            return process_data_db_oracle(request, query, connectid, sampleyn=True)

    # docid는 있고 gendoc_uid만 None ==> 마스터 셋팅 화면
    if docid is not None and gendoc_uid is None:
        dataparamdtls_resp = supabase.schema(SUPABASE_SCHEMA).table("dataparamdtls") \
            .select("*").eq("docid", docid).eq("datauid", datauid).execute()
        df_dtls = pd.DataFrame(dataparamdtls_resp.data)
    
        dataparams_resp = supabase.schema(SUPABASE_SCHEMA).table("dataparams") \
            .select("paramuid, samplevalue, operator").eq("docid", docid).execute()

        df_params = pd.DataFrame(dataparams_resp.data)
        df_dtls = df_dtls.merge(df_params, on="paramuid", how="left")

        df_dtls["value"] = df_dtls["samplevalue"]
        df_dtls = df_dtls[["querycolnm", "value", "operator"]].dropna()

    # docid는 None, gendoc_uid만 있음 ==> 실제 문서 실행 화면
    elif docid is None and gendoc_uid is not None:
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

        df_dtls = df_dtls.merge(df_gendoc, on="paramuid", how="left")
        df_dtls["value"] = df_dtls["paramvalue"]

        # 4. dataparams (operator)
        dataparams_resp = supabase.schema(SUPABASE_SCHEMA).table("dataparams") \
            .select("paramuid, operator").eq("docid", docid).execute()
        df_params = pd.DataFrame(dataparams_resp.data)

        df_dtls = df_dtls.merge(df_params, on="paramuid", how="left")

        # 5. 최종 컬럼
        df_dtls = df_dtls[["querycolnm", "value", "operator"]].dropna()

    else:
        raise ValueError("잘못된 docid / gendoc_uid 조합")

    # ===== DB 타입별 실행 =====

    # 🔹 MSSQL
    if connecttype == "MSSQL":
        where_clauses = []

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["value"]
            op = row.get("operator", "=")

            if isinstance(val, str):
                val = f"'{val}'"

            where_clauses.append(f"x.{col} {op} {val}")

        where_sql = " AND ".join(where_clauses)

        final_query = f"""
        SELECT *
        FROM (
            {query}
        ) x
        WHERE {where_sql}
        """

        return process_data_db_mssql(request, final_query, connectid)

    # 🔹 SUPABASE
    elif connecttype == "SUPABASE":
        query_str = str(query)
        is_rpc = ".rpc(" in query_str

        if is_rpc:
            # 🔹 RPC 호출 시 df_dtls → 파라미터 매핑
            rpc_params = {}
            for _, row in df_dtls.iterrows():
                col = row["querycolnm"]
                val = row["value"]
                rpc_params[col] = val

            # @변수 치환이 필요하면 더미값 적용
            if "@" in query_str:
                query_str = replace_rpc_vars_with_dummy(query_str)

            # eval에서 실행
            query_to_execute = query_str
            return process_data_db_supabase(request, query_to_execute, connectid, sampleyn=False)

        else:
            query_str = str(query)
            
            # ✅ execute 제거
            if ".execute()" in query_str:
                query_str = query_str.replace(".execute()", "")

            # ✅ select "*" 보장
            if ".select(" not in query_str:
                query_str += '.select("*")'
            elif '.select("' in query_str and '*' not in query_str:
                query_str = re.sub(r'\.select\([^)]+\)', '.select("*")', query_str)

            for _, row in df_dtls.iterrows():
                col = row["querycolnm"].replace('"', '')
                val = row["value"]
                op = row.get("operator", "=")

                if isinstance(val, str):
                    val = f"'{val}'"

                if op == "=":
                    query_str += f".eq('{col}', {val})"
                elif op == ">":
                    query_str += f".gt('{col}', {val})"
                elif op == ">=":
                    query_str += f".gte('{col}', {val})"
                elif op == "<":
                    query_str += f".lt('{col}', {val})"
                elif op == "<=":
                    query_str += f".lte('{col}', {val})"

            # ✅ 마지막에 실행
            query_str += ".execute()"

            return process_data_db_supabase(request, query_str, connectid, sampleyn=False)

    elif connecttype == "ORACLE":
        where_clauses = []

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["value"]
            op = row.get("operator", "=")

            if isinstance(val, str):
                val = f"'{val}'"

            where_clauses.append(f"x.{col} {op} {val}")

        where_sql = " AND ".join(where_clauses)

        final_query = f"""
        SELECT *
        FROM (
            {query}
        ) x
        WHERE {where_sql}
        """

        return process_data_db_oracle(request, final_query, connectid)

    else:
        raise ValueError(f"지원하지 않는 DB 타입입니다: {connecttype}")


def process_data_db_mssql(request, query, connectid, sampleyn = None):
    config = process_data_connect_mssql(request, connectid)
    conn_str = ";".join([f"{k}={v}" for k, v in config.items()])

    conn = pyodbc.connect(conn_str)

    df = pd.read_sql_query(query, conn)

    conn.close()

    # sampleyn이 True이면 반환되는 DataFrame 상위 5개만
    if sampleyn:
        df = df.head(5)
    
    return df


def process_data_connect_mssql(request, connectid):
    supabase = get_supabase(request)

    dbconnectors_resp = supabase.schema(SUPABASE_SCHEMA).table("dbconnectors").select("*").eq("connectid", connectid).execute()
    dbconnectors = dbconnectors_resp.data if dbconnectors_resp.data else []

    for connector in dbconnectors:
        try:
            # 복호화 처리 (값이 존재할 경우에만)
            connector["decendpoint"] = decrypt_value(connector.get("encendpoint", "")) if connector.get("encendpoint") else ""
            connector["decdatabase"] = decrypt_value(connector.get("encaccessdb", "")) if connector.get("encaccessdb") else ""
            connector["decuserid"] = decrypt_value(connector.get("encaccessuserid", "")) if connector.get("encaccessuserid") else ""
            connector["decpassword"] = decrypt_value(connector.get("encaccesspassword", "")) if connector.get("encaccesspassword") else ""
        except Exception as e:
            connector["decendpoint"] = connector["decdatabase"] = connector["decuserid"] = connector["decpassword"] = ""

    return {
        "DRIVER": "ODBC Driver 17 for SQL Server",
        "SERVER": connector["decendpoint"],
        "DATABASE": connector["decdatabase"],
        "UID": connector["decuserid"],
        "PWD": connector["decpassword"],
    }


def process_data_db_supabase(request, query, connectid, sampleyn = None):
    # supabase = get_supabase(request)
    config = process_data_connect_supabase(request, connectid)
    supabase = create_client(config["url"], config["key"])
    
    # 안전하게 supabase 객체만 노출
    # eval할 때 supabase만 사용할 수 있도록 locals 제한
    try:
        response = eval(query, {"supabase": supabase})
    except Exception as e:
        raise RuntimeError(f"Supabase 쿼리 실행 오류: {e}")

    if hasattr(response, 'status_code') and response.status_code >= 400:
        raise Exception(f"Supabase API 오류: {response.message}")

    data = getattr(response, "data", None)

    if data is None:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # sampleyn이 True이면 상위 5개만 반환
    if sampleyn:
        df = df.head(5)

    return df

def process_data_connect_supabase(request, connectid):
    supabase = get_supabase(request)

    dbconnectors_resp = supabase.schema(SUPABASE_SCHEMA).table("dbconnectors").select("*").eq("connectid", connectid).execute()
    dbconnectors = dbconnectors_resp.data if dbconnectors_resp.data else []

    for connector in dbconnectors:
        try:
            # 복호화 처리 (값이 존재할 경우에만)
            connector["decendpoint"] = decrypt_value(connector.get("encendpoint", "")) if connector.get("encendpoint") else ""
            connector["decpassword"] = decrypt_value(connector.get("encaccesspassword", "")) if connector.get("encaccesspassword") else ""
        except Exception as e:
            connector["decendpoint"] = connector["decpassword"] = ""

    return {
        "url": connector["decendpoint"],
        "key": connector["decpassword"]
    }

def extract_query_vars(query_str):
    """
    query 문자열에서 @변수명 목록 추출
    """
    return set(re.findall(r'@(\w+)', query_str))

def replace_rpc_vars_with_dummy(query_str, dummy_value="'ALL'"):
    """
    RPC 쿼리에서 @변수들을 전부 더미 값으로 치환
    """
    vars_found = extract_query_vars(query_str)

    for var in vars_found:
        query_str = re.sub(
            rf'@{var}\b',
            dummy_value,
            query_str
        )

    return query_str

def process_data_db_oracle(request, query, connectid, sampleyn=None):
    config = process_data_connect_oracle(request, connectid)
    
    user = config["USER"]
    pwd = config["PWD"]
    dsn = config["DSN"]   # 예: localhost:1521/XEPDB1

    try:
        # 🔹 raw connection 사용
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cols = [col[0] for col in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        cur.close()
        conn.close()
    except Exception as e:
        return None

    if sampleyn:
        df = df.head(5)

    return df


def process_data_connect_oracle(request, connectid):
    supabase = get_supabase(request)

    resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("dbconnectors")
        .select("*")
        .eq("connectid", connectid)
        .execute()
    )

    connector = resp.data[0]

    try:
        endpoint = decrypt_value(connector.get("encendpoint", ""))
        user = decrypt_value(connector.get("encaccessuserid", ""))
        password = decrypt_value(connector.get("encaccesspassword", ""))
    except Exception:
        endpoint = user = password = ""

    return {
        "DSN": endpoint,   # 예: host:1521/ORCLPDB1
        "USER": user,
        "PWD": password
    }

