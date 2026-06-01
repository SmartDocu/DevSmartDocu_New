import json as _json
import pandas as pd
from utilsPrj.supabase_client import SUPABASE_SCHEMA
from utilsPrj.api_helper import call_api_for_data


def process_data_api(supabase, datauid, gendoc_uid=None):
    data_row = (
        supabase.schema(SUPABASE_SCHEMA).table("datas")
        .select("connuid, endpoint").eq("datauid", datauid).execute().data
    )
    if not data_row:
        raise ValueError(f"datauid {datauid}에 해당하는 데이터가 없습니다.")

    connuid  = data_row[0].get("connuid")
    endpoint = data_row[0].get("endpoint") or ""
    if not connuid:
        raise ValueError("API 커넥터가 설정되지 않았습니다.")

    api_row = (
        supabase.schema(SUPABASE_SCHEMA).table("conn_apis")
        .select("baseurl, authtype, health_method").eq("connuid", connuid).execute().data
    )
    if not api_row:
        raise ValueError("커넥터 API 설정이 없습니다.")

    baseurl  = api_row[0].get("baseurl") or ""
    authtype = api_row[0].get("authtype") or "NONE"
    method   = api_row[0].get("health_method") or "GET"

    cred_rows = (
        supabase.schema(SUPABASE_SCHEMA).table("conn_api_credentials")
        .select("*").eq("connuid", connuid).execute().data
    )
    cred = cred_rows[0] if cred_rows else {}
    secrets: dict = {}
    secret_path = cred.get("secret_path") or ""

    if secret_path == "aws-sm":
        from utilsPrj.secrets_cache import get_connector_secret
        conn_row = (
            supabase.schema(SUPABASE_SCHEMA).table("connectors")
            .select("tenantid").eq("connuid", connuid).execute().data
        )
        tenantid = conn_row[0]["tenantid"] if conn_row else None
        try:
            secrets = get_connector_secret(tenantid, connuid)
        except Exception:
            secrets = {}
    elif secret_path:
        try:
            secrets = _json.loads(secret_path)
        except Exception:
            secrets = {}

    param_rows = (
        supabase.schema(SUPABASE_SCHEMA).table("data_api_params")
        .select("*").eq("datauid", datauid).order("orderno").execute().data or []
    )

    # is_fixed=True → fixed_value 사용 (call_api_for_data 내부 처리)
    # is_fixed=False, gendoc_uid 없음 → testvalue 사용 (call_api_for_data 내부 처리)
    # is_fixed=False, gendoc_uid 있음 → docparamdtls + gendoc_params에서 실제 값 조회 후 testvalue 오버라이드
    if gendoc_uid:
        docid_row = (
            supabase.schema(SUPABASE_SCHEMA).table("gendocs")
            .select("docid").eq("gendocuid", gendoc_uid).execute().data
        )
        docid = docid_row[0]["docid"] if docid_row else None
        if docid:
            import copy
            overridden = []
            for p in param_rows:
                row = copy.copy(p)
                if not p.get("is_fixed") and p.get("paramnm"):
                    dtl = (
                        supabase.schema(SUPABASE_SCHEMA).table("docparamdtls")
                        .select("paramuid")
                        .eq("docid", docid).eq("paramnm", p["paramnm"])
                        .execute().data
                    )
                    if dtl:
                        paramuid = dtl[0]["paramuid"]
                        val_row = (
                            supabase.schema(SUPABASE_SCHEMA).table("gendoc_params")
                            .select("paramvalue")
                            .eq("paramuid", paramuid).eq("gendocuid", gendoc_uid)
                            .execute().data
                        )
                        if val_row:
                            row["testvalue"] = val_row[0]["paramvalue"]
                overridden.append(row)
            param_rows = overridden

    full_url = baseurl.rstrip("/") + ("" if endpoint.startswith("/") else "/") + endpoint

    result = call_api_for_data(
        url=full_url,
        method=method,
        authtype=authtype,
        api_params=param_rows,
        auth_cred=cred,
        secrets=secrets,
    )

    if not result.get("ok"):
        raise ValueError(f"API 호출 실패 ({result.get('status_code', 0)}): {result.get('detail', '')}")

    records = _extract_api_records(result.get("data"))

    return pd.DataFrame(records) if records else pd.DataFrame()


def _extract_api_records(data) -> list:
    """API 응답 JSON에서 list[dict] 추출."""
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return data
        return []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        return [data] if data else []
    return []
