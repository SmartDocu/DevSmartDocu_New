from utilsPrj.supabase_client import SUPABASE_SCHEMA


def _strip_quotes(s):
    s = s.strip().rstrip(",").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s


def parse_aliases(text):
    if not text or not text.strip():
        return []
    return [v for v in (_strip_quotes(a) for a in text.split(",")) if v]


def parse_multiline(text):
    if not text or not text.strip():
        return []
    return [v for v in (_strip_quotes(line) for line in text.splitlines()) if v]


def _parse_schema_table(sql):
    """'select ... from schema.table ...' 에서 (schema, table) 추출"""
    if not sql:
        return "", ""
    tokens = sql.strip().split()
    from_positions = [i for i, t in enumerate(tokens) if t.lower() == "from"]
    if not from_positions:
        return "", ""
    idx = from_positions[-1] + 1
    table_ref = tokens[idx] if idx < len(tokens) else ""
    if not table_ref:
        return "", ""
    if "." in table_ref:
        schema, table = table_ref.split(".", 1)
        return schema.strip().strip('[]"`'), table.strip().strip('[]"`')
    return "", table_ref.strip().strip('[]"`')


def master_data_json_create(supabase, datauid):
    try:
        sb = supabase.schema(SUPABASE_SCHEMA)

        # datas (필수) — desc가 예약어라 * 로 전체 조회
        data_resp = (
            sb.table("datas")
            .select("*")
            .eq("datauid", datauid)
            .execute()
        )
        if not data_resp.data:
            return None
        data_row = data_resp.data[0]

        # data_metas (필수)
        meta_resp = sb.table("data_metas").select("*").eq("datauid", datauid).execute()
        if not meta_resp.data:
            return None
        meta = meta_resp.data[0]

        # datacols (필수, useyn=True)
        cols_resp = (
            sb.table("datacols")
            .select("querycolnm, dispcolnm, datatypecd, aliases")
            .eq("datauid", datauid)
            .eq("useyn", True)
            .order("orderno")
            .execute()
        )
        if not cols_resp.data:
            return None

        # datacolvalues (선택)
        vals_resp = (
            sb.table("datacolvalues")
            .select("querycolnm, value, logical_name, aliases")
            .eq("datauid", datauid)
            .order("orderno")
            .execute()
        )
        values_data = vals_resp.data or []

        # schema / physical_name 결정
        databasiscd = data_row.get("databasiscd", "")
        if databasiscd in ("dbt", "dbs"):
            schema_name, physical_name = _parse_schema_table(data_row.get("query", ""))
        else:
            schema_name, physical_name = "", ""

        # JSON 조립
        data_json = {
            "schema":              schema_name,
            "physical_name":       physical_name,
            "logical_name":        data_row.get("datanm", ""),
            "aliases":             parse_aliases(meta.get("aliases", "")),
            "description":         data_row.get("desc", "") or "",
            "primary_key":         parse_aliases(meta.get("primary_key", "")),
            "query":               data_row.get("query", "") or "",
            "grain":               (meta.get("grain") or "").strip('" '),
            "default_time_column": meta.get("default_time_column", ""),
            "purpose":             parse_multiline(meta.get("purpose", "")),
            "query_examples":      parse_multiline(meta.get("query_examples", "")),
            "columns":             {},
        }

        # reference 섹션 (parent 정보가 있을 때만)
        if meta.get("parent_table") and meta.get("child_column") and meta.get("parent_column"):
            data_json["reference"] = {
                "parent_schema": meta.get("parent_schema", ""),
                "parent_table":  meta["parent_table"],
                "join_column": [
                    {
                        "child_column":  meta["child_column"],
                        "parent_column": meta["parent_column"],
                    }
                ],
            }

        # columns 섹션
        for col in cols_resp.data:
            col_json = {
                "logical_name": col.get("dispcolnm", ""),
                "data_type":    col.get("datatypecd", "string") or "string",
            }
            aliases = parse_aliases(col.get("aliases", ""))
            if aliases:
                col_json["aliases"] = aliases
            data_json["columns"][col["querycolnm"]] = col_json

        # values 섹션 (컬럼별 그룹)
        for v in values_data:
            col_nm = v["querycolnm"]
            if col_nm not in data_json["columns"]:
                continue
            col_entry = data_json["columns"][col_nm]
            values_obj = col_entry.setdefault("values", {})
            values_obj[v["value"]] = {"logical_name": v.get("logical_name", "")}
            val_aliases = parse_aliases(v.get("aliases", ""))
            if val_aliases:
                values_obj[v["value"]]["aliases"] = val_aliases

        # data_metas.json 업데이트
        sb.table("data_metas").update({"json": data_json}).eq("datauid", datauid).execute()

        return data_json

    except Exception:
        return None
