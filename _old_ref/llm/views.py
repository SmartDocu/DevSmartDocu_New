# 20250926

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .llm_save_delete import *
from .llm_utils import *
from .ai_chain import *


# @csrf_exempt
def ai_llm_preview(request):

    is_not_sample_prompt = True

    result_llm = ai_llm_click_preview_button(request, is_not_sample_prompt)

    return JsonResponse(result_llm)


# @csrf_exempt
def ai_prompt_llm_preview(request):
    is_not_sample_prompt = False

    result_llm = ai_llm_click_preview_button(request, is_not_sample_prompt)

    return JsonResponse(result_llm)


def ai_experience_llm_preview(request):
    is_not_sample_prompt = False

    result_llm = ai_llm_click_preview_button(request, is_not_sample_prompt)

    return JsonResponse(result_llm)



def ai_get_columns(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    try:
        data_uid = request.POST.get("datauid", "")
        
        table_name = "datacols"
        conditions = {
            'datauid': data_uid,
        }
        
        result = process_data_in_supabase(
            supabase,
            table_name=table_name,
            process_type="select",
            process_data={},
            conditions=conditions,
            columns="querycolnm, dispcolnm, orderno"
        )

        sorted_items = sorted(
            [item for item in result if item.get("orderno") is not None and item.get("orderno") != ""],
            key=lambda x: x["orderno"]
        )

        if sorted_items:
            columns = [item["dispcolnm"] for item in sorted_items]
        else:
            columns = [item["dispcolnm"] for item in result]

        return JsonResponse({"success": True, "columns": columns})

    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error columns list: {str(e)}"})


# @csrf_exempt
def ai_charts_save(request):
    if request.method == "POST":
        table_name = "charts"
        llm_object_save(request, table_name)
        return JsonResponse({"success": True, "msg": "저장 완료!"})
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_sentences_save(request):
    if request.method == "POST":
        table_name = "sentences"
        llm_object_save(request, table_name)
        return JsonResponse({"success": True, "msg": "저장 완료!"})
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_tables_save(request):
    if request.method == "POST":
        table_name = "tables"
        llm_object_save(request, table_name)
        return JsonResponse({"success": True, "msg": "저장 완료!"})
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_charts_delete(request):
    if request.method == "POST":
        table_name = "charts"
        llm_object_delete(request, table_name)
        return JsonResponse({"success": True, "msg": "삭제 완료!"})
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_sentences_delete(request):
    if request.method == "POST":
        table_name = "sentences"
        llm_object_delete(request, table_name)
        return JsonResponse({"success": True, "msg": "삭제 완료!"})
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_tables_delete(request):
    if request.method == "POST":
        table_name = "tables"
        llm_object_delete(request, table_name)
        return JsonResponse({"success": True, "msg": "삭제 완료!"})
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_prompt_sample_save(request):
    if request.method == "POST":
        table_name = "prompts"
        result = llm_prompt_sample_save(request, table_name)
        return result
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# @csrf_exempt
def ai_prompt_sample_delete(request):
    if request.method == "POST":
        table_name = "prompts"
        return llm_prompt_sample_delete(request, table_name)
    return JsonResponse({"success": False, "msg": "POST만 허용됩니다."})


# 기존 함수명과 호환성을 위한 래퍼
def ai_charts(request):
    """기존 URL과의 호환성을 위한 함수"""
    output_page = "llm/ai_charts.html"
    object_typecd = "CA"
    table_name = "charts"
    return ai_llm_page(request, output_page, object_typecd, table_name)


def ai_sentences(request):
    """기존 URL과의 호환성을 위한 함수"""
    output_page = "llm/ai_sentences.html"
    object_typecd = "SA"
    table_name = "sentences"
    return ai_llm_page(request, output_page, object_typecd, table_name)


def ai_tables(request):
    """기존 URL과의 호환성을 위한 함수"""
    output_page = "llm/ai_tables.html"
    object_typecd = "TA"
    table_name = "tables"
    return ai_llm_page(request, output_page, object_typecd, table_name)



def ai_sample_prompt_manage(request):
    """기존 URL과의 호환성을 위한 함수"""
    output_page = "llm/ai_sample_prompt_manage.html"

    return ai_llm_prompt_page(request, output_page)


def get_prompts(request):
    """object_typecd만으로 필터링 (display_type 제거)"""
    object_typecd = request.GET.get("object_type")
    displaytype = request.GET.get("displaytype", "")  # 추가
    
    supabase = get_service_client()

    conditions = {"objecttypecd": object_typecd}
    if displaytype:
        conditions["displaytype"] = displaytype
    
    prompt_result = process_data_in_supabase(
        supabase, 
        table_name="prompts", 
        process_type="select",
        process_data={}, 
        conditions=conditions,
        columns="*"
    )
    
    prompts = [{
        "promptuid": p["promptuid"],
        "prompt_nm": p["promptnm"],
        "prompt_text": p["prompt"],
        "prompt_desc": p["desc"],
        "display_type": p.get("displaytype", "")
    } for p in prompt_result]
    
    return JsonResponse({'prompts': prompts})


def ai_experience(request):
    # return render(request, "llm/ai_experience.html")
    output_page = "llm/ai_experience.html"
    is_experience = True

    return ai_llm_prompt_page(request, output_page, is_experience)



def ai_intergrate(request):
    """기존 URL과의 호환성을 위한 함수"""
    output_page = "llm/ai_intergrate.html"
    return ai_llm_page(request, output_page)


def index(request):
    return render(request, 'llm/index.html')


