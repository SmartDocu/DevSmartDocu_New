from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA
from utilsPrj.process_data_db import process_data_db
from utilsPrj.process_data_ai import process_data_ai
from utilsPrj.process_data_excel import process_data_excel
from decimal import Decimal

def process_data(request, datauid, docid=None, gendoc_uid=None, all = None):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    Datas_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datas")
        .select("*")
        .eq("datauid", datauid)
        .execute()
    )

    datasourcecd = Datas_resp.data[0]['datasourcecd']

    # 원본이 db 데이터 화면일 경우
    if datasourcecd == "db":
        # print(f"jeff 001 process_data : docid_{docid} / datauid_{datauid}")
        return process_data_db(supabase, request, datauid, docid, gendoc_uid, all)

    # 원본이 excel 데이터 화면일 경우
    if datasourcecd == "ex":
        # print(f"jeff 002 process_data : docid_{docid} / datauid_{datauid}")
        return process_data_excel(supabase, request, datauid, docid, gendoc_uid, all)
    
    # 원본이 ai 데이터 화면일 경우
    if datasourcecd in ("df", "dfv"):
        # print(f"jeff 003 process_data : docid_{docid} / datauid_{datauid}")
        return process_data_ai(supabase, request, datauid, docid, gendoc_uid, all)

    raise ValueError(f"지원하지 않는 원본입니다: {datasourcecd}")


def apply_column_display_mapping(datauid, columns, rows, supabase):
    """
    Supabase datacols 정보(querycolnm, dispcolnm)에 맞춰 컬럼명을 교체하고,
    중복 및 빈 컬럼명을 보정하여 표시용 데이터 생성
    """
    # DB에서 컬럼 매핑 정보 가져오기
    col_resp = (
        supabase.schema(SUPABASE_SCHEMA)
        .table("datacols")
        .select("querycolnm, dispcolnm")
        .eq("datauid", datauid)
        .order("orderno")
        .execute()
    )
    col_map_data = col_resp.data or []

    # 1️⃣ querycolnm -> dispcolnm 매핑
    col_mapping = {}
    ordered_disp_cols = []
    for c in col_map_data:
        query_col = c["querycolnm"].strip() if c.get("querycolnm") else ""
        disp_col = c.get("dispcolnm", "").strip() or query_col
        if not query_col:
            continue
        col_mapping[query_col] = disp_col
        ordered_disp_cols.append(disp_col)

    # 2️⃣ raw_columns 의 실제 인덱스 매핑 (중복 이름 및 빈값 보정)
    # 예: ['Test중', 'Test중', '', ''] → ['Test중', 'Test중_1', 'A', 'B']
    fixed_columns = []
    seen = {}
    empty_count = 0

    for col in columns:
        if not col or col.strip() == "":
            empty_count += 1
            new_col = chr(64 + empty_count) if empty_count <= 26 else f"COL{empty_count}"
        else:
            col = col.strip()
            if col in seen:
                seen[col] += 1
                new_col = f"{col}_{seen[col]}"
            else:
                seen[col] = 0
                new_col = col
        fixed_columns.append(new_col)

    col_index_map = {col_name: idx for idx, col_name in enumerate(fixed_columns)}

    # 3️⃣ 데이터 변환
    new_rows = []
    for row in rows:
        new_row = {}
        for query_col, disp_col in col_mapping.items():
            idx = col_index_map.get(query_col)
            val = None
            if idx is not None and idx < len(row):
                val = row[idx]

            if isinstance(val, Decimal):
                val = float(val)
            new_row[disp_col] = val
        new_rows.append(new_row)
    
    return ordered_disp_cols, new_rows
