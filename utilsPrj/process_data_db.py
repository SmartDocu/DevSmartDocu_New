import json
import os
import time
import pyodbc
from supabase import create_client
from decimal import Decimal
import pandas as pd

from utilsPrj.supabase_client import get_supabase, SUPABASE_SCHEMA
import re
from sqlalchemy import create_engine
import urllib
import oracledb


def _get_connector(supabase, connuid):
    resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("connectors").select("*")
        .eq("connuid", connuid).execute()
    )
    if not resp.data:
        raise ValueError(f"커넥터를 찾을 수 없습니다: {connuid}")
    connector = resp.data[0]
    secret_path = connector.get("secret_path") or ""
    secret = {}

    if secret_path == "aws-sm":
        from utilsPrj.secrets_cache import get_connector_secret
        try:
            secret = get_connector_secret(connector.get("tenantid"), connuid)
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("커넥터 시크릿 조회 실패 %s: %s", connuid, exc)
    elif secret_path:
        try:
            secret = json.loads(secret_path)
        except Exception:
            pass

    connector["_username"] = secret.get("username", "")
    connector["_password"] = secret.get("password", "")
    return connector


def process_data_db(supabase, request, datauid, docid=None, gendoc_uid=None, all=None):
    Datas_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datas")
        .select("*")
        .eq("datauid", datauid)
        .execute()
    )

    connuid = Datas_resp.data[0]['connuid']
    query = Datas_resp.data[0]['query']

    connectors_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("connectors")
        .select("dbtype")
        .eq("connuid", connuid)
        .execute()
    )
    dbtype = connectors_resp.data[0]['dbtype']

    is_oracle = dbtype in ("Oracle", "Oracle(TNS)")

    # 마스터 팝업용, 전체 데이터 필요
    if all:
        if dbtype == "mssql":
            return process_data_db_mssql(request, query, connuid)

        elif dbtype == "supabase":
            query_str = str(query)
            is_rpc = ".rpc(" in query_str

            if is_rpc:
                if "@" in query_str:
                    query_str = replace_rpc_vars_with_dummy(query_str)

            query = query_str
            return process_data_db_supabase(request, query, connuid)

        elif is_oracle:
            return process_data_db_oracle(request, query, connuid)

        elif dbtype == "postgres":
            return process_data_db_postgres(request, query, connuid)

    # docid, gendoc_uid 둘다 None ==> db 데이터(master/datas_db/)화면
    if docid is None and gendoc_uid is None:
        if dbtype == "mssql":
            pattern = re.compile(r"^\s*SELECT\s+(TOP\s+\d+)?", re.IGNORECASE)
            match = pattern.match(query)

            if match and not match.group(1):
                query = re.sub(
                    r"^\s*SELECT\s+",
                    "SELECT TOP 5 ",
                    query,
                    flags=re.IGNORECASE
                )

            return process_data_db_mssql(request, query, connuid, sampleyn=True)

        elif dbtype == "supabase":
            query_str = str(query)
            is_rpc = ".rpc(" in query_str

            if is_rpc:
                if "@" in query_str:
                    query_str = replace_rpc_vars_with_dummy(query_str)

            if not is_rpc:
                if ".limit(" not in query_str:
                    if ".execute()" in query_str:
                        query_str = query_str.replace(".execute()", ".limit(5).execute()", 1)
                    else:
                        query_str += ".limit(5)"

            query = query_str
            return process_data_db_supabase(request, query, connuid, sampleyn=True)

        elif is_oracle:
            if "fetch first" not in query.lower():
                query = f"""
                SELECT *
                FROM (
                    {query}
                )
                FETCH FIRST 5 ROWS ONLY
                """
            return process_data_db_oracle(request, query, connuid, sampleyn=True)

        elif dbtype == "postgres":
            return process_data_db_postgres(request, query, connuid, sampleyn=True)

    # docid는 있고 gendoc_uid만 None ==> 마스터 셋팅 화면
    if docid is not None and gendoc_uid is None:
        docparamdtls_resp = supabase.schema(SUPABASE_SCHEMA).table("docparamdtls") \
            .select("*").eq("docid", docid).eq("datauid", datauid).execute()
        df_dtls = pd.DataFrame(docparamdtls_resp.data)

        docparams_resp = supabase.schema(SUPABASE_SCHEMA).table("docparams") \
            .select("paramuid, samplevalue, operator").eq("docid", docid).execute()

        df_params = pd.DataFrame(docparams_resp.data)

        if not df_dtls.empty and 'paramuid' in df_dtls.columns and not df_params.empty:
            df_dtls = df_dtls.merge(df_params, on="paramuid", how="left")
            df_dtls["value"] = df_dtls["samplevalue"]
            df_dtls = df_dtls[["querycolnm", "value", "operator"]].dropna()
        else:
            df_dtls = pd.DataFrame(columns=["querycolnm", "value", "operator"])

    # docid는 None, gendoc_uid만 있음 ==> 실제 문서 실행 화면
    elif docid is None and gendoc_uid is not None:
        gendocs_resp = supabase.schema(SUPABASE_SCHEMA).table("gendocs") \
            .select("docid").eq("gendocuid", gendoc_uid).single().execute()

        docid = gendocs_resp.data["docid"]

        docparamdtls_resp = supabase.schema(SUPABASE_SCHEMA).table("docparamdtls") \
            .select("*").eq("docid", docid).eq("datauid", datauid).execute()
        df_dtls = pd.DataFrame(docparamdtls_resp.data)

        gendoc_params_resp = supabase.schema(SUPABASE_SCHEMA).table("gendoc_params") \
            .select("paramuid, paramvalue").eq("gendocuid", gendoc_uid).execute()
        df_gendoc = pd.DataFrame(gendoc_params_resp.data)

        if (not df_dtls.empty and 'paramuid' in df_dtls.columns
                and not df_gendoc.empty and 'paramuid' in df_gendoc.columns):
            df_dtls = df_dtls.merge(df_gendoc, on="paramuid", how="left")
            df_dtls["value"] = df_dtls["paramvalue"]
        else:
            df_dtls["value"] = None

        docparams_resp = supabase.schema(SUPABASE_SCHEMA).table("docparams") \
            .select("paramuid, operator").eq("docid", docid).execute()
        df_params = pd.DataFrame(docparams_resp.data)

        if (not df_dtls.empty and 'paramuid' in df_dtls.columns
                and not df_params.empty and 'paramuid' in df_params.columns):
            df_dtls = df_dtls.merge(df_params, on="paramuid", how="left")
        else:
            df_dtls["operator"] = "="

        if not df_dtls.empty and "querycolnm" in df_dtls.columns:
            df_dtls = df_dtls[["querycolnm", "value", "operator"]].dropna(subset=["value"])
        else:
            df_dtls = pd.DataFrame(columns=["querycolnm", "value", "operator"])

    else:
        raise ValueError("잘못된 docid / gendoc_uid 조합")

    # ===== DB 타입별 실행 =====

    if dbtype == "mssql":
        where_clauses = []

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["value"]
            op = row.get("operator", "=")

            if isinstance(val, str):
                val = f"'{val}'"

            where_clauses.append(f"x.{col} {op} {val}")

        if where_clauses:
            where_sql = " AND ".join(where_clauses)
            final_query = f"SELECT * FROM ({query}) x WHERE {where_sql}"
        else:
            final_query = f"SELECT * FROM ({query}) x"

        return process_data_db_mssql(request, final_query, connuid)

    elif dbtype == "supabase":
        query_str = str(query)
        is_rpc = ".rpc(" in query_str

        if is_rpc:
            rpc_params = {}
            for _, row in df_dtls.iterrows():
                col = row["querycolnm"]
                val = row["value"]
                rpc_params[col] = val

            if "@" in query_str:
                query_str = replace_rpc_vars_with_dummy(query_str)

            return process_data_db_supabase(request, query_str, connuid, sampleyn=False)

        else:
            query_str = str(query)

            if ".execute()" in query_str:
                query_str = query_str.replace(".execute()", "")

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

            query_str += ".execute()"

            return process_data_db_supabase(request, query_str, connuid, sampleyn=False)

    elif is_oracle:
        where_clauses = []

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["value"]
            op = row.get("operator", "=")

            if isinstance(val, str):
                val = f"'{val}'"

            where_clauses.append(f"x.{col} {op} {val}")

        if where_clauses:
            where_sql = " AND ".join(where_clauses)
            final_query = f"SELECT * FROM ({query}) x WHERE {where_sql}"
        else:
            final_query = f"SELECT * FROM ({query}) x"

        return process_data_db_oracle(request, final_query, connuid)

    elif dbtype == "postgres":
        where_clauses = []

        for _, row in df_dtls.iterrows():
            col = row["querycolnm"]
            val = row["value"]
            op = row.get("operator", "=")

            if isinstance(val, str):
                val = f"'{val}'"

            where_clauses.append(f"x.{col} {op} {val}")

        if where_clauses:
            where_sql = " AND ".join(where_clauses)
            final_query = f"SELECT * FROM ({query}) x WHERE {where_sql}"
        else:
            final_query = f"SELECT * FROM ({query}) x"

        return process_data_db_postgres(request, final_query, connuid)

    else:
        raise ValueError(f"지원하지 않는 DB 타입입니다: {dbtype}")


def process_data_db_mssql(request, query, connuid, sampleyn=None):
    config, retry_count = process_data_connect_mssql(request, connuid)
    conn_str = ";".join([f"{k}={v}" for k, v in config.items()])

    last_err = None
    for attempt in range(max(retry_count, 1)):
        try:
            conn = pyodbc.connect(conn_str)
            df = pd.read_sql_query(query, conn)
            conn.close()
            if sampleyn:
                df = df.head(5)
            return df
        except Exception as e:
            last_err = e
            if attempt < retry_count - 1:
                time.sleep(1)
    raise last_err


def process_data_connect_mssql(request, connuid):
    connector = _get_connector(get_supabase(request), connuid)
    timeout = int(connector.get("timeout") or 15)
    retry_count = int(connector.get("retry_count") or 1)

    params = {
        "DRIVER": "ODBC Driver 17 for SQL Server",
        "SERVER": connector.get("server") or "",
        "DATABASE": connector.get("db") or "",
        "UID": connector["_username"],
        "PWD": connector["_password"],
        "Connection Timeout": str(timeout),
    }
    if connector.get("ssl_mode"):
        params["Encrypt"] = "yes"
        params["TrustServerCertificate"] = "yes"

    return params, retry_count


def process_data_db_supabase(request, query, connuid, sampleyn=None):
    config = process_data_connect_supabase(request, connuid)
    supabase = create_client(config["url"], config["key"])

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

    if sampleyn:
        df = df.head(5)

    return df


def process_data_connect_supabase(request, connuid):
    connector = _get_connector(get_supabase(request), connuid)
    return {
        "url": connector.get("server") or "",
        "key": connector["_password"],
    }


def process_data_db_oracle(request, query, connuid, sampleyn=None):
    config = process_data_connect_oracle(request, connuid)

    user = config["USER"]
    pwd = config["PWD"]
    dsn = config["DSN"]
    timeout = config["timeout"]
    retry_count = config["retry_count"]

    is_tns_descriptor = dsn.strip().startswith("(")
    if is_tns_descriptor:
        # full TNS descriptor: ConnectParams 없이 직접 연결
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
    else:
        params = oracledb.ConnectParams(
            tcp_connect_timeout=timeout,
            retry_count=retry_count,
            retry_delay=1,
        )
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn, params=params)
    cur = conn.cursor()
    cur.execute(query)
    rows = cur.fetchall()
    cols = [col[0] for col in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    cur.close()
    conn.close()

    if sampleyn:
        df = df.head(5)

    return df


def process_data_connect_oracle(request, connuid):
    connector = _get_connector(get_supabase(request), connuid)
    dbtype = connector.get("dbtype", "Oracle")

    if dbtype == "Oracle(TNS)":
        dsn = connector.get("tns") or ""
    else:
        server  = connector.get("server") or ""
        port    = connector.get("port") or "1521"
        service = connector.get("service_name") or connector.get("sid") or ""
        dsn = f"{server}:{port}/{service}"

    return {
        "DSN":      dsn,
        "USER":     connector["_username"],
        "PWD":      connector["_password"],
        "timeout":  int(connector.get("timeout") or 15),
        "retry_count": int(connector.get("retry_count") or 1),
    }


def process_data_db_postgres(request, query, connuid, sampleyn=None):
    config = process_data_connect_postgres(request, connuid)
    retry_count = config["retry_count"]

    last_err = None
    for attempt in range(max(retry_count, 1)):
        engine = None
        try:
            engine = create_engine(config["url"], connect_args=config["connect_args"])
            df = pd.read_sql_query(query, engine)
            engine.dispose()
            if sampleyn:
                df = df.head(5)
            return df
        except Exception as e:
            last_err = e
            if engine:
                engine.dispose()
            if attempt < retry_count - 1:
                time.sleep(1)
    raise last_err


def process_data_connect_postgres(request, connuid):
    connector = _get_connector(get_supabase(request), connuid)
    user        = connector["_username"]
    pwd         = connector["_password"]
    server      = connector.get("server") or "localhost"
    port        = connector.get("port") or "5432"
    db          = connector.get("db") or ""
    ssl_mode    = connector.get("ssl_mode")
    timeout     = int(connector.get("timeout") or 15)
    retry_count = int(connector.get("retry_count") or 1)

    ssl_param   = "?sslmode=require" if ssl_mode else ""
    connect_args = {"connect_timeout": timeout}
    if ssl_mode:
        connect_args["sslmode"] = "require"

    return {
        "url":          f"postgresql+psycopg2://{user}:{pwd}@{server}:{port}/{db}{ssl_param}",
        "connect_args": connect_args,
        "retry_count":  retry_count,
    }


def extract_query_vars(query_str):
    return set(re.findall(r'@(\w+)', query_str))


def replace_rpc_vars_with_dummy(query_str, dummy_value="'ALL'"):
    vars_found = extract_query_vars(query_str)
    for var in vars_found:
        query_str = re.sub(rf'@{var}\b', dummy_value, query_str)
    return query_str
