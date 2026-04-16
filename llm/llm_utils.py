# 20251021

import pandas as pd
import re
import os
from django.shortcuts import render, redirect
from django.http import JsonResponse

from langchain_core.output_parsers.string import StrOutputParser

from dotenv import load_dotenv
from dotenv import dotenv_values

from .ai_chain import get_full_chain, get_charts_prompt, get_sentences_prompt, get_tables_prompt, process_data_in_supabase, get_llm_model
from utilsPrj.supabase_client import get_service_client
# from utilsPrj.data_runner import *
from utilsPrj.supabase_client import *
from utilsPrj.crypto_helper import decrypt_value
from utilsPrj.process_data import process_data

# from utilsPrj.supabase_client import supabase

# supabase = get_service_client()


def ai_llm_prompt_page(request, output_page, is_experience=False):
    """샘플 프롬프트 페이지 - docid 필터 제거"""
    selected_promptuid = None

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)
        
    # 기본값: CA (차트)
    object_typecd = request.GET.get("object_type", "CA")
    selected_promptnm = request.GET.get("promptnm")

    if not is_experience:
        # 사용자 문서 목록
        user = request.session.get("user")
        user_id = user.get("id")
    
        docs = supabase.schema(SUPABASE_SCHEMA).rpc("fn_docs_filtered__r_user", {'p_useruid': user_id}).execute().data or []
        docs_table = docs

    selected_datauid = request.GET.get("datauid")
    datas_table = process_data_in_supabase(
        supabase, 
        table_name="datas", 
        process_type="select",
        process_data={}, 
        conditions={"datauid": selected_datauid} if selected_datauid else {},
        columns="projectid, datauid, datanm, query"
    )

    # datauid 선택 로직
    if datas_table:
        if selected_datauid:
            selected_data = next((d for d in datas_table if str(d["datauid"]) == str(selected_datauid)), datas_table[0])
        else:
            selected_data = datas_table[0]
        selected_datanm = selected_data["datanm"]
        selected_datauid = selected_data["datauid"]
    else:
        selected_datanm = ""
        selected_datauid = ""

    # ✅ 차트/문장/테이블 유형 가져오기
    chart_type = request.GET.get("chart_type", "")
    sentence_type = request.GET.get("sentence_type", "")
    table_type = request.GET.get("table_type", "")

    # displaytype 결정
    displaytype = ""
    if object_typecd == "CA":
        displaytype = chart_type
    elif object_typecd == "SA":
        displaytype = sentence_type
    elif object_typecd == "TA":
        displaytype = table_type

    # ✅ prompts 가져오기
    prompts = []
    prompt_text = ""
    prompt_desc = ""
    display_type_display_name = {
        "bar": "막대그래프",
        "line": "선그래프",
        "pie": "원형그래프",
        "scatter": "산점도",
        "boxplot": "박스플롯",
        "histogram": "히스토그램",
        "dual_axis": "이중축",
        "heatmap": "히트맵",
        "subplot": "서브플롯",
        "simple_question": "단순 질의",
        "summary": "요약",
        "report": "보고서",
        "predict": "예측",
        "table": "테이블"
    }

    if object_typecd:
        prompt_conditions = {"objecttypecd": object_typecd}
        
        if not is_experience and displaytype:
            prompt_conditions["displaytype"] = displaytype
        
        prompt_result = process_data_in_supabase(
            supabase, 
            table_name="prompts", 
            process_type="select",
            process_data={}, 
            conditions=prompt_conditions,
            columns="*"
        )
        
        prompts = prompt_result
        prompts = sorted(prompts, key=lambda x: x.get("orderno", 999))
        
        for prompt in prompts:
            display_type = prompt["displaytype"]
            display_name = display_type_display_name[display_type]
            prompt["displayname_promptname"] = display_name + " - " + prompt["promptnm"]


    prompt_datauids = set(p['datauid'] for p in prompts if p.get('datauid'))

    datas_table = process_data_in_supabase(
        supabase, 
        table_name="datas", 
        process_type="select",
        process_data={}, 
        conditions={},
        columns="projectid, datauid, datanm, query"
    )

    # ✅ datas_table을 prompts의 datauid로 필터링
    filtered_datas = [d for d in datas_table if d['datauid'] in prompt_datauids]

    # datauid 선택 로직
    selected_datauid = request.GET.get("datauid")
    if filtered_datas:
        if selected_datauid:
            selected_data = next((d for d in filtered_datas if str(d["datauid"]) == str(selected_datauid)), filtered_datas[0])
        else:
            selected_data = filtered_datas[0]
        selected_datanm = selected_data["datanm"]
        selected_datauid = selected_data["datauid"]
    else:
        selected_datanm = ""
        selected_datauid = ""

    # ✅ 프롬프트 선택 로직
    if selected_promptnm:
        # URL에서 선택된 프롬프트가 있으면
        for p in prompts:
            if p["promptnm"] == selected_promptnm:
                prompt_text = p["prompt"]
                prompt_desc = p["desc"]
                selected_promptuid = p.get("promptuid")
                break
    else:
        # ✅ 처음 로드 시 기본 프롬프트 설정 (is_experience=True일 때만)
        if is_experience and prompts:
            # displaytype='bar'인 프롬프트 찾기
            default_prompt = next((p for p in prompts if p.get("displaytype") == "bar"), prompts[0])
            prompt_text = default_prompt["prompt"]
            prompt_desc = default_prompt["desc"]
            selected_promptnm = default_prompt["promptnm"]
            selected_promptuid = default_prompt.get("promptuid")
                
    render_dict =  {
        'datas': filtered_datas,
        'datauid': selected_datauid,
        'datanm': selected_datanm,
        'selected_datanm': selected_datanm,
        'selected_datauid': selected_datauid,
        'object_type': object_typecd,
        'object_typecd': object_typecd,
        'prompts': prompts,
        'selected_promptnm': selected_promptnm,
        'selected_promptuid': selected_promptuid,
        'prompt': prompt_text,
        'prompt_desc': prompt_desc
    }
    if not is_experience:
        render_dict["docs"] = docs_table

    return render(request, output_page, render_dict)


def ai_llm_page(request, output_page, object_typecd, table_name):
    """채팅 페이지 렌더링"""
    if object_typecd == "":
        pass

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    selected_chapteruid = request.GET.get("chapteruid")
    selected_objectnm = request.GET.get("objectnm")
    selected_datauid = request.GET.get("datauid")
    selected_promptnm = request.GET.get("promptnm")

    user = request.session.get("user")
    user_id = user.get("id")
    docs = supabase.schema(SUPABASE_SCHEMA).rpc("fn_docs_filtered__r_user", {'p_useruid': user_id}).execute().data or []
    
    gpt_prompt = ""
    prompt_desc = ""
    selected_display_type = ""

    if object_typecd == "CA":
        selected_display_type = request.GET.get("chart_type", "")
    elif object_typecd == "SA":
        selected_display_type = request.GET.get("sentence_type", "")
    elif object_typecd == "TA":
        selected_display_type = request.GET.get("table_type", "")

    chapters_table = process_data_in_supabase(
        supabase, 
        table_name="chapters", 
        process_type="select", 
        process_data={}, 
        conditions={"chapteruid": selected_chapteruid}, 
        columns="chapteruid, chapternm, docid"
    )

    chapter_name = chapters_table[0]["chapternm"]
    selected_docid = chapters_table[0]["docid"]

    docs_table = process_data_in_supabase(
        supabase,
        table_name="docs",
        process_type="select",
        process_data={},
        conditions={"docid": selected_docid},
        columns={"projectid"}
    )
    project_id = docs_table[0]["projectid"]

    if selected_docid is None and docs_table:
        selected_docid = str(docs_table[0]["docid"])

    docs_table = docs
    selected_docname = next((doc['docnm'] for doc in docs_table if doc['docid'] == selected_docid), None)


    datas_table = process_data_in_supabase(
        supabase, 
        table_name="datas", 
        process_type="select",
        process_data={}, 
        conditions={"projectid": project_id} 
                    if not selected_datauid 
                    else {"projectid": project_id}, 
                        #   "datauid": selected_datauid}, 
        columns="projectid, datauid, datanm, query"
    )

    if not selected_chapteruid and chapters_table:
        selected_chapteruid = str(chapters_table[0]["chapteruid"])
        query = request.GET.copy()
        query["chapteruid"] = selected_chapteruid
        return redirect(f"{request.path}?{query.urlencode()}")

    if selected_promptnm:
        prompt_result = process_data_in_supabase(
            supabase, 
            table_name="prompts", 
            process_type="select",
            process_data={}, 
            conditions={"promptnm": selected_promptnm, 
                        "objecttypecd": object_typecd}, 
            columns="*"
        )
        
        if prompt_result:
            prompt_data = prompt_result[0]
            gpt_prompt = prompt_data["prompt"]
            prompt_desc = prompt_data["desc"]
            selected_display_type = prompt_data["displaytype"]
    
    elif selected_objectnm:
        object_result = process_data_in_supabase(
            supabase, 
            table_name="objects", 
            process_type="select",
            process_data={}, 
            conditions={"chapteruid": selected_chapteruid, 
                        "objectnm": selected_objectnm}, 
            columns="objectuid"
        )
        
        if object_result:
            selected_objectuid = object_result[0]["objectuid"]
            
            existing_data = process_data_in_supabase(
                supabase, 
                table_name=table_name, 
                process_type="select",
                process_data={}, 
                conditions={"objectuid": selected_objectuid}, 
                columns="gptq, datauid, displaytype"
            )
            
            if existing_data:
                data = existing_data[0]
                gpt_prompt = data.get("gptq", "") or ""
                selected_display_type = data.get("displaytype", "") or selected_display_type
                if not selected_datauid:    # jeff 20251230 1745 추가
                    selected_datauid = data.get("datauid", "")
                else:
                    target_datauid = next(
                        (item for item in datas_table if item.get("datauid") == selected_datauid),
                        None
                    )
                    selected_datauid = target_datauid["datauid"]
                
                prompt_desc = ""
                
            else:
                pass

    objects_table = process_data_in_supabase(
        supabase, 
        table_name="objects", 
        process_type="select",
        process_data={}, 
        conditions={"chapteruid": selected_chapteruid}, 
        columns="*"
    )

    prompts_table = process_data_in_supabase(
        supabase, 
        table_name="prompts", 
        process_type="select",
        process_data={}, 
        conditions={"objecttypecd": object_typecd}, 
        columns="*"
    )

    prompt_text = prompts_table[0]["prompt"]
    prompt_desc_ = prompts_table[0]["desc"]

    docs_table = sorted(docs_table, key=lambda x: x["docnm"])
    chapters_table = sorted(chapters_table, key=lambda x: x["chapternm"])
    objects_table = sorted(objects_table, key=lambda x: x["objectnm"])
    datas_table = sorted(datas_table, key=lambda x: x["datanm"])
    prompts_table = sorted(prompts_table, key=lambda x: x["promptnm"]) if prompts_table else []

    selected_datanm = next(
        (data['datanm'] for data in datas_table if data['datauid'] == selected_datauid), 
        datas_table[0]["datanm"] if datas_table else ""
    ) 

    return render(request, output_page, {
        'user': user,
        'docs': docs_table,
        'docid': selected_docid,
        'selected_docid': selected_docid,
        'selected_docnm' : selected_docname,

        'chapters': chapters_table,
        'chapteruid': selected_chapteruid,
        'selected_chapteruid': selected_chapteruid,
        'selected_chapternm': chapter_name,
        'objects': objects_table,
        'objectuid': selected_objectuid,
        'selected_objectuid': selected_objectuid,
        'objectnm': selected_objectnm,
        'selected_objectnm': selected_objectnm,

        'datas': datas_table,
        'datauid': selected_datauid,
        'datanm': selected_datanm,
        'projectid': project_id,
        'selected_datanm': selected_datanm,
        'selected_datauid': selected_datauid,

        'object_typecd': object_typecd,
        'prompt_value': gpt_prompt,        # 프롬프트 textarea
        'prompt_desc_value': prompt_desc,  # 프롬프트 설명 textarea  
        'selected_display_type': selected_display_type,
        'prompts': prompts_table,
        'desc': prompt_desc_,
        'prompt': prompt_text,
        'selected_promptnm': selected_promptnm,
    })


def ai_create_dataframe(request, is_not_sample_prompt=True):

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    tokens = {"input_tokens": 0, "output_tokens": 0}    # jeff 20251201 1040

    user = request.session.get("user")
    if user:
        project_id = user.get("projectid")
        selected_docid = user.get("docid")
    else:
        doc_name = "샘플_APQR_DB"

        project_id = process_data_in_supabase(
            supabase, "projects", "select", {}, 
            {"tenantid": 5, "projectnm": "public"}, "tenantid"
        )[0]["tenantid"]

        selected_docid = process_data_in_supabase(
            supabase, "docs", "select", {}, 
            {"docnm": doc_name, "sampleyn": True}, "docid"
        )[0]["docid"]

    selected_datauid = request.POST.get("datauid", "")

    fn_table_name = "datas"
    if not is_not_sample_prompt:
        conditions = {"datauid": selected_datauid}
    else:
        conditions = {"projectid": project_id, "datauid": selected_datauid}

    columns = "projectid, datauid, datanm, datasourcecd, query, sourcedatauid, gensentence"
    datas_table = process_data_in_supabase(
        supabase,
        table_name=fn_table_name,
        process_type="select",
        process_data={},
        conditions=conditions,
        columns=columns
    )

    if datas_table[0]["datasourcecd"] == "df":
        selected_datauid = datas_table[0]["sourcedatauid"]
        conditions = {"projectid": project_id, "datauid": selected_datauid}
        datas_table = process_data_in_supabase(
            supabase,
            table_name=fn_table_name,
            process_type="select",
            process_data={},
            conditions=conditions,
            columns=columns
        )


    query = datas_table[0]["query"]

    is_df = query == None

    if is_df:
        from langchain_core.prompts import PromptTemplate
       
        gen_sentence = datas_table[0]["gensentence"]
        conditions = {"projectid": project_id, "datauid": selected_datauid}
        columns = "projectid, datauid, datanm, query, sourcedatauid, gensentence, datasourcecd, excelurl"
        datas_table = process_data_in_supabase(
            supabase,
            table_name=fn_table_name,
            process_type="select",
            process_data={},
            conditions=conditions,
            columns=columns
        )

        if datas_table[0]["datasourcecd"] == "ex" :
            excel_path = datas_table[0]["excelurl"]
            # df = pd.read_excel(excel_path)
            if excel_path.lower().endswith('.csv'):
                try:
                    df = pd.read_csv(excel_path)
                except UnicodeDecodeError:
                    excel_path.seek(0)
                    df = pd.read_csv(excel_path, encoding='cp949')
            else:
                df = pd.read_excel(excel_path)

            conditions_ex = {"datauid": selected_datauid}

            dataparamdtls_table = process_data_in_supabase(
                supabase,
                table_name="dataparamdtls",
                process_type="select",
                process_data={},
                conditions=conditions_ex,
                columns="paramuid, querycolnm"
            )

            filters_param = dataparamdtls_table.copy()

            for filter in filters_param:
                param_uid = filter["paramuid"]
                dataparamdtls_table = process_data_in_supabase(
                    supabase,
                    table_name="dataparams",
                    process_type="select",
                    process_data={},
                    conditions={"paramuid": param_uid},
                    columns="samplevalue, operator"
                )
                filter["samplevalue"] = dataparamdtls_table[0]["samplevalue"]
                filter["operator"] = dataparamdtls_table[0]["operator"]

            df_filtered = df.copy()            
            for f in filters_param:
                col = f['querycolnm']
                val = f['samplevalue']
                op = f['operator']

                if col not in df_filtered.columns:
                    raise KeyError(f"DataFrame에 컬럼이 없습니다: {col}")

                if pd.api.types.is_numeric_dtype(df_filtered[col]):
                    val = pd.to_numeric(val, errors='coerce')

                if op == '=':
                    df_filtered = df_filtered[df_filtered[col] == val]
                elif op == '>':
                    df_filtered = df_filtered[df_filtered[col] > val]
                elif op == '<':
                    df_filtered = df_filtered[df_filtered[col] < val]
                elif op == '>=':
                    df_filtered = df_filtered[df_filtered[col] >= val]
                elif op == '<=':
                    df_filtered = df_filtered[df_filtered[col] <= val]
                else:
                    raise ValueError(f"지원하지 않는 operator: {op}")

            result_df = df_filtered

            return result_df
        
        query = datas_table[0]["query"]

    if is_df:
        df = process_data(request, selected_datauid, selected_docid)    # jeff 20251231 1605

        prompt = get_tables_prompt(df, {}, gen_sentence)
        chain = PromptTemplate.from_template(prompt)

        llm = get_llm_model(request)
        
        full_chain = get_full_chain(llm, df, chain, {}, "TA")

        response = full_chain.invoke({"question": gen_sentence, "column_dict": {}})

        if isinstance(response, dict) and "tokens" in response:
            tokens["input_tokens"] += response["tokens"]["input_tokens"]
            tokens["output_tokens"] += response["tokens"]["output_tokens"]

        result_df = pd.DataFrame(response.get("result", ""))
        
    else:
        result_df = process_data(request, selected_datauid, selected_docid)    # jeff 20251231 1605
    
    return result_df


def ai_get_dataframe(request):

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    if request.method != 'POST':
        raise ValueError("Post 요청만 허용됩니다.")
    
    try:
        selected_chapteruid = request.POST.get("chapteruid")
        selected_objectnm = request.POST.get("objectnm")
        selected_datauid = request.POST.get("datauid")
        question = request.POST.get("prompt", "").strip()

        objects_table = process_data_in_supabase(
            supabase, 
            table_name="objects", 
            process_type="select",
            process_data={},
            conditions={"chapteruid": selected_chapteruid,
                        "objectnm": selected_objectnm}, 
            columns="*"
        )

        object_typecd = objects_table[0]['objecttypecd']

        result_df = ai_create_dataframe(request)

        if not question:
            return JsonResponse({
                "message_type": "error",
                "message": "프롬프트를 입력해주세요."
            })
        if not selected_datauid:
            return JsonResponse({
                "message_type": "error",
                "message": "데이터를 선택해주세요."
            })
        return question, object_typecd, selected_datauid, result_df

    except Exception as e:
        raise RuntimeError(f"Error DataFrame: {str(e)}")


def ai_prompt_get_dataframe(request, is_not_sample_prompt):

    if request.method != 'POST':
        raise ValueError("Post 요청만 허용됩니다.")

    selected_datauid = request.POST.get("datauid")
    question = request.POST.get("prompt", "").strip()
    object_typecd = request.POST.get("object_type", "")

    # result_df = ai_create_dataframe(request)
    result_df = ai_create_dataframe(request, is_not_sample_prompt)

    return question, object_typecd, selected_datauid, result_df


def ai_llm_click_preview_button(request, is_not_sample_prompt):

    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    for key, value in request.GET.items():
        print(f"{key}: {value}")
    
    total_tokens = {"input_tokens": 0, "output_tokens": 0}    # jeff 20251201 1040
    
    if is_not_sample_prompt:
        question, object_typecd, data_uid, result_df = ai_get_dataframe(request)
    else:
        question, object_typecd, data_uid, result_df = ai_prompt_get_dataframe(request, is_not_sample_prompt)

    table_name = "datacols"
    conditions = {
        'datauid': data_uid,
    }

    result_datacols = process_data_in_supabase(
        supabase,
        table_name=table_name,
        process_type="select",
        process_data={},
        conditions=conditions,
        columns="querycolnm, dispcolnm"
    )

    column_dict = {item['querycolnm']: item['dispcolnm'] for item in result_datacols}

    if object_typecd == "CA":
        prompt = get_charts_prompt(result_df, column_dict, question)
    elif object_typecd == "SA":
        prompt = get_sentences_prompt(result_df, column_dict, question)
    elif object_typecd == "TA":
        prompt = get_tables_prompt(result_df, column_dict, question)
    else:
        return {
            "message_type": "error",
            "message": "객체(object) 타입이 분류되지 않는 타입입니다."
        }

    llm = get_llm_model(request)

    # full_chain = get_full_chain(llm, result_df, prompt, column_dict, object_typecd)
    full_chain = get_full_chain(llm, result_df, prompt, question, column_dict, object_typecd)

    response = full_chain.invoke({"question": question, "column_dict": column_dict})

    if isinstance(response, dict) and "tokens" in response:
        total_tokens["input_tokens"] = response["tokens"]["input_tokens"]
        total_tokens["output_tokens"] = response["tokens"]["output_tokens"]

    if isinstance(response, dict):
        if response.get("status")=="chart_drawn":
            img_base64 = response["image_bytes"]
            return {
                "message_type": "image",
                "image_data": img_base64,
                "question": response.get("question", "")
            }
        elif response.get("status")=="analysis_comment":
            return {
                "message_type": "text",
                "message": response.get("result", "")
            }
        elif response.get("status")=="data_table":
            return {
                "message_type": "table",
                "message": "", 
                "data": response.get("result", ""),
                "table_header_json": response.get("table_header_json", ""),
                "table_data_json": response.get("table_data_json", "")
            }
        else:
            return {
                "message_type": "error",
                "message": "알 수 없는 응답 형식입니다."
            }
    else:
        return {
            "message_type": "error",
            "message": "응답 형식이 딕셔너리 형이 아닙니다."
        }

