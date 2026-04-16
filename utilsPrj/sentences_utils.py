import inspect
from utilsPrj.errorlogs import error_log
from utilsPrj.supabase_client import get_supabase_client, SUPABASE_SCHEMA

def draw_sentences(request, supabase, dict_rows, template_text, datauid):
    # jeff 20251209 1045 추가
    if not isinstance(dict_rows, list) or not all(isinstance(r, dict) for r in dict_rows):
        print("dict_rows is invalid:", dict_rows)
        return []
    #####
    
    try:
        # supabase = get_supabase_client(
        #     request.session.get("access_token"),
        #     request.session.get("refresh_token")
        # )    # jeff 20251124 1104 주석 

        col_resp = (
            supabase.schema(SUPABASE_SCHEMA)
            .table("datacols")
            .select("querycolnm, dispcolnm")
            .eq("datauid", datauid)
            .order("orderno")
            .execute()
        )
        col_map_data = col_resp.data or []

        result = []
        if not template_text or not dict_rows:
            return result

        # ----------------------------------------------
        # 1) querycolnm -> dispcolnm 매핑 딕셔너리 생성
        # ----------------------------------------------
        query_to_disp = {
            col["querycolnm"]: col["dispcolnm"]
            for col in col_map_data
        }

        # ----------------------------------------------
        # 2) template_text의 {{querycolnm}} -> {{dispcolnm}} 변환
        # ----------------------------------------------
        converted_template = template_text
        for query, disp in query_to_disp.items():
            converted_template = converted_template.replace(f"{{{{{query}}}}}", f"{{{{{disp}}}}}")

        # ----------------------------------------------
        # 3) 변환된 템플릿을 기반으로 dict_rows 데이터 치환
        # ----------------------------------------------
        for row in dict_rows:
            sentence = converted_template
            for key, value in row.items():
                sentence = sentence.replace(f"{{{{{key}}}}}", str(value))
            result.append(sentence)

        return "\n".join(result)

    except Exception as e:
        try:
            error_log(
                request,
                e,
                inspect.currentframe().f_code.co_name,
                request.session.get("user", {}).get("id", None) if request else None,
                template_text,
                None,
                "TABLE 생성 중 오류"
            )
        except Exception as log_err:
            raise log_err  
        raise e
