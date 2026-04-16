import json, re, uuid, os
from datetime import datetime, timedelta
from dateutil import parser
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.process_data import process_data

def req_doc_list(request):
    """문서 목록 조회 및 파라미터 처리"""
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    if not user:
        code = 'login'
        text = '로그인이 필요합니다.'
        page = "req_read_doc"
        return render(request, "pages/home.html", {
            "code": code,
            "text": text,
            "page": page,
            "request": request
        })
    
    user_id = user.get("id")
    
    # 기본 날짜 설정
    today = datetime.now().date()
    default_start_date = (today - timedelta(days=10)).strftime('%Y-%m-%d')
    default_end_date = today.strftime('%Y-%m-%d')

    # GET 파라미터에서 날짜 가져오기
    start_date = request.GET.get("start_date") or default_start_date
    if start_date == 'null':
        start_date = default_start_date
    end_date = request.GET.get("end_date") or default_end_date
    if end_date == 'null':
        end_date = default_end_date

    # 문서 ID 가져오기
    docid = user.get("docid")
    docnm = None
    filtered_data = []
    dataparams = []
    params_value = []
    datacols_map = {}

    if docid:
        # 날짜 파싱
        start_dt = parse_date(start_date) if start_date else None
        end_dt = parse_date(end_date) if end_date else None

        rpc_params = {'p_docid': docid}
        if start_dt:
            rpc_params['p_start_date'] = start_date
        if end_dt:
            end_dt_plus = end_dt + timedelta(days=1)
            rpc_params['p_end_date'] = end_dt_plus.strftime("%Y-%m-%d")

        # 작성 이력 데이터 조회
        filtered_data = supabase.schema('smartdoc').rpc("fn_gendocs__r_docid", rpc_params).execute().data or []
        docnm = supabase.schema('smartdoc').table('docs').select("*").eq('docid', docid).execute().data[0]['docnm']

        # 각 문서 데이터 포맷 정리
        for item in filtered_data:
            # 작성 문서 체크
            gencnt = 0

            # 시간 포맷 정리
            _format_timestamps(item)

            # 작성된 문서 확인
            genchapter = supabase.schema('smartdoc').table("genchapters").select("*").eq("gendocuid", item['gendocuid']).execute().data
            for gench in genchapter:
                if gench.get('createfiledts'):
                    gencnt += 1

            item['makeyn'] = 'n' if gencnt > 0 else 'y'

            # 문서별 파라미터
            genparams = supabase.schema("smartdoc").rpc("fn_gendocs_params__r", {'p_gendocuid': item['gendocuid']}).execute().data or []
            item['params'] = json.dumps(genparams, ensure_ascii=False)

        # dataparams 조회
        dataparams = supabase.schema("smartdoc").table("dataparams").select("*").eq('docid', docid).order('orderno').execute().data or []

        # datas 조회
        data_ids = [d["datauid"] for d in dataparams if d.get("datauid") is not None]
        datas = supabase.schema("smartdoc").table("datas").select("*").in_("datauid", data_ids).execute().data
        datacols = supabase.schema("smartdoc").table("datacols").select("datauid, querycolnm, dispcolnm").in_("datauid", data_ids).execute().data

        # params_value 생성 (DataFrame을 dict 리스트로 변환)
        params_value = _build_params_value(request, docid, datas)

        if filtered_data:
            # datauid별 필요한 컬럼 수집
            datauid_required_columns = _collect_required_columns(filtered_data, dataparams)

            # params_value 컬럼 필터링
            _filter_params_value_columns(params_value, datauid_required_columns)

            # finalnm 생성
            _process_final_names(filtered_data, params_value, dataparams)

            # finalnm_joined 생성
            _create_finalnm_joined(filtered_data)
            for col in datacols:
                datacols_map.setdefault(col["datauid"], {})[col["querycolnm"]] = col["dispcolnm"]

        # print(filtered_data)

    else:
        docnm = '문서를 선택 하시기 바랍니다.'

    # print(params_value)

    # JSON 직렬화
    params_value_json = json.dumps(params_value, ensure_ascii=False)

    # print(params_value_json)

    return render(request, 'pages/req_doc_list.html', {
        "docnm": docnm,
        "start_date": start_date,
        "end_date": end_date,
        "data": filtered_data,
        "dataparams": dataparams,
        "datacols_map_json": json.dumps(datacols_map, ensure_ascii=False),
        "params_value": params_value,
        "params_value_json": params_value_json,
    })


def _format_timestamps(item):
    """시간 필드 포맷팅"""
    timestamp_fields = ['createdts', 'createfiledts', 'updatefiledts', 'closedts']
    
    for field in timestamp_fields:
        if item.get(field):
            try:
                dt = parser.parse(item[field]) if isinstance(item[field], str) else item[field]
                
                # createfiledts는 gencnt 계산용으로도 사용
                if field == 'createfiledts':
                    item[field] = dt.strftime("%y-%m-%d %H:%M")
                else:
                    item[field] = dt.strftime("%y-%m-%d %H:%M")
            except Exception:
                item[field] = ''

def _build_params_value(request, docid, datas):
    """params_value 생성 - DataFrame을 dict 리스트로 변환"""
    import pandas as pd
    import numpy as np
    from datetime import datetime, date
    
    def convert_value(value):
        """JSON 직렬화 가능한 타입으로 변환"""
        if isinstance(value, bytes):
            try:
                return value.decode('utf-8')
            except:
                return str(value)
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, (np.integer, np.floating)):
            return value.item()
        elif pd.isna(value):
            return None
        else:
            return value
    
    params_value = []
    
    for data_item in datas:
        result = call_param_data(request, docid, data_item)
        
        # DataFrame을 dict 리스트로 변환
        if hasattr(result, 'to_dict'):  # DataFrame인 경우
            result_dict = result.to_dict('records')
            
            # 모든 값을 JSON 직렬화 가능한 타입으로 변환
            cleaned_dict = []
            for row in result_dict:
                cleaned_row = {key: convert_value(value) for key, value in row.items()}
                cleaned_dict.append(cleaned_row)
            
            result_dict = cleaned_dict
            
            # 동적 정렬: 첫 번째 키의 값을 기준으로 정렬
            if result_dict and len(result_dict) > 0:
                first_key = list(result_dict[0].keys())[0]  # 첫 번째 키 추출
                result_dict = sorted(result_dict, key=lambda x: str(x.get(first_key, '')))
            
        else:
            result_dict = result
        
        params_value.append({
            "datauid": data_item.get("datauid"),
            "value": result_dict
        })
    
    return params_value


def _collect_required_columns(filtered_data, dataparams):
    """datauid별 필요한 컬럼명 수집 (순서: keycolnm → nmcolnm)"""
    datauid_required_columns = {}
    
    for data in filtered_data:
        params_list = json.loads(data['params'])
        
        for param in params_list:
            param_datauid = param.get('datauid')
            
            if param_datauid:
                matching_dataparam = next(
                    (dp for dp in dataparams if dp.get('datauid') == param_datauid),
                    None
                )
                
                if matching_dataparam:
                    keycolnm = matching_dataparam.get('keycolnm')
                    nmcolnm = matching_dataparam.get('nmcolnm')
                    
                    if param_datauid not in datauid_required_columns:
                        datauid_required_columns[param_datauid] = []  # ✅ set() → []
                    
                    # ✅ keycolnm이 리스트에 없으면 추가
                    if keycolnm and keycolnm not in datauid_required_columns[param_datauid]:
                        datauid_required_columns[param_datauid].append(keycolnm)
                    
                    # ✅ nmcolnm이 리스트에 없으면 추가 (keycolnm 다음에)
                    if nmcolnm and nmcolnm not in datauid_required_columns[param_datauid]:
                        datauid_required_columns[param_datauid].append(nmcolnm)
    
    return datauid_required_columns


def _filter_params_value_columns(params_value, datauid_required_columns):
    """params_value에서 필요한 컬럼만 필터링"""
    for pv in params_value:
        datauid = pv['datauid']
        value_data = pv['value']
        
        if datauid in datauid_required_columns and isinstance(value_data, list) and len(value_data) > 0:
            required_cols = datauid_required_columns[datauid]  # ✅ list() 제거
            
            # 필요한 컬럼만 필터링
            filtered_rows = []
            for row in value_data:
                filtered_row = {col: row.get(col) for col in required_cols if col in row}
                filtered_rows.append(filtered_row)
            
            pv['value'] = filtered_rows


def _process_final_names(filtered_data, params_value, dataparams):
    """각 파라미터의 finalnm 생성"""
    for data in filtered_data:
        params_list = json.loads(data['params'])
        
        for param in params_list:
            param_datauid = param.get('datauid')
            
            if not param_datauid:
                param['finalnm'] = param.get('paramvalue')
            else:
                matching_data = next(
                    (pv for pv in params_value if pv['datauid'] == param_datauid),
                    None
                )
                matching_dataparam = next(
                    (dp for dp in dataparams if dp.get('datauid') == param_datauid),
                    None
                )
                
                if matching_data and matching_dataparam:
                    finalnm = _extract_finalnm(
                        matching_data['value'],
                        matching_dataparam.get('keycolnm'),
                        matching_dataparam.get('nmcolnm'),
                        param.get('paramvalue')
                    )
                    param['finalnm'] = finalnm if finalnm else param.get('paramvalue')
                else:
                    param['finalnm'] = param.get('paramvalue')
        
        data['params'] = json.dumps(params_list, ensure_ascii=False)


def _extract_finalnm(value_list, keycolnm, nmcolnm, param_value):
    """value_list에서 keycolnm과 일치하는 행의 nmcolnm 값 추출"""
    if not isinstance(value_list, list) or len(value_list) == 0:
        return None
    
    if not keycolnm or not nmcolnm:
        return None
    
    first_row = value_list[0]
    
    if keycolnm not in first_row:
        return None
    
    # 데이터 타입에 따라 변환
    sample_value = first_row[keycolnm]
    
    try:
        if isinstance(sample_value, int):
            param_value_casted = int(param_value)
        elif isinstance(sample_value, float):
            param_value_casted = float(param_value)
        else:
            param_value_casted = str(param_value)
    except (ValueError, TypeError):
        param_value_casted = str(param_value)
    
    # 리스트에서 매칭되는 항목 찾기
    matched_item = next(
        (item for item in value_list if item.get(keycolnm) == param_value_casted),
        None
    )
    
    if matched_item and nmcolnm in matched_item:
        return matched_item[nmcolnm]
    
    return None


def _create_finalnm_joined(filtered_data):
    """finalnm_joined 생성"""
    for row in filtered_data:
        try:
            params = json.loads(row["params"]) if isinstance(row["params"], str) else row["params"]
            row["finalnm_joined"] = " / ".join(
                p.get("finalnm", "") for p in params if p.get("finalnm")
            )
        except Exception:
            row["finalnm_joined"] = ""


@csrf_exempt
def gendoc_file_upload(request):
    """파일 업로드 처리"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST만 허용됨'})

    try:
        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_supabase_client(access_token, refresh_token)

        user = request.session.get("user")
        if not user:
            return JsonResponse({'success': False, 'message': '로그인 필요'})
        user_id = user.get("id")

        gendocuid = request.POST.get("gendocuid")
        file_obj = request.FILES.get("file")

        if not file_obj:
            return JsonResponse({'success': False, 'message': '파일 없음'})

        # 1. 기존 파일 삭제
        old_data = supabase.schema("smartdoc").table("gendocs") \
            .select("updatefileurl, updatefilenm") \
            .eq("gendocuid", gendocuid).execute().data

        if old_data and old_data[0].get("updatefileurl"):
            old_path = old_data[0]["updatefileurl"].split('smartdoc/')[1].rstrip('?')
            supabase.storage.from_("smartdoc").remove([old_path])

        # 2. 새 파일 업로드
        extension = os.path.splitext(file_obj.name)[1][1:]
        unique_filename = f"{uuid.uuid4()}.{extension}"
        path = f"result/{gendocuid}/{str(unique_filename)}"
        file_bytes = file_obj.read()

        supabase.storage.from_("smartdoc").upload(
            path,
            file_bytes,
            {"cacheControl": "3600", "upsert": "true"}
        )

        # 3. 퍼블릭 URL 가져오기
        public_url = supabase.storage.from_("smartdoc").get_public_url(path)

        now = datetime.now().isoformat()
        
        # 4. DB 업데이트 - gendocs
        supabase.schema("smartdoc").table("gendocs").update({
            "updatefileurl": public_url,
            "updatefilenm": file_obj.name,
            "updatefiledts": now,
            "updateuserid": user_id
        }).eq("gendocuid", gendocuid).execute()

        # 5. DB 업데이트 - loguploads
        docid = supabase.schema("smartdoc").table("gendocs") \
            .select("*").eq("gendocuid", gendocuid).execute().data[0]['docid']
        
        supabase.schema("smartdoc").table("loguploads").insert({
            "objecttypenm": "D",
            "docid": docid,
            "gendocuid": gendocuid,
            "updatefileurl": public_url,
            "updatefilenm": file_obj.name,
            "updatefiledts": now,
            "updateuserid": user_id
        }).execute()

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def call_param_data(request, docid, data_item):
    """파라미터 데이터 조회 및 쿼리 실행"""
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    try:
        datauid = data_item.get('datauid')
        query = data_item.get('query')
        datasourcecd = data_item.get("datasourcecd", "")
        sourcedatauid = data_item.get("sourcedatauid")

        # datasourcecd가 df인 경우 sourcedatauid로 원본 데이터 조회
        if datasourcecd == "df" and sourcedatauid:
            source_resp = supabase.schema("smartdoc").table("datas") \
                .select("*").eq("datauid", sourcedatauid).execute()
            source_data = source_resp.data or []

            if source_data:
                source_record = source_data[0]
                source_datasourcecd = source_record.get("datasourcecd", "")
                source_query = source_record.get("query", "")

                # 원본 datasourcecd가 db인 경우 query 덮어쓰기
                if source_datasourcecd == "db":
                    query = source_query

        # DataParams 조회
        DataParams_resp = supabase.schema("smartdoc").table("dataparams") \
            .select("*").eq("docid", docid).execute()
        DataParams = DataParams_resp.data if DataParams_resp.data else []

        # 파라미터 치환
        for param in DataParams:
            key = param.get("paramnm")
            value = param.get("samplevalue")
            intyn = param.get("intyn", False)

            if key is not None and value is not None:
                placeholder = f"@{key}"
                if intyn:
                    replacement = str(value)
                else:
                    value = str(value).replace("'", "''")
                    replacement = f"'{value}'"

                query = query.replace(placeholder, replacement)

        # 쿼리 실행
        # df = run_data(request, datauid, query, sampleyn=False)
        df = process_data(request, datauid=datauid, all=True)

        if df.empty:
            raise ValueError("쿼리 실행 결과가 올바르지 않습니다.")
        
        # 특정 열 제외
        exclude_columns = ['LargePhoto']
        df = df.drop(columns=[col for col in exclude_columns if col in df.columns])

        return df

    except Exception as e:
        print(f"call_param_data 오류: {e}")
        raise