# 20250917

import json
import uuid
from django.http import JsonResponse
from datetime import datetime
# datetime.now().isoformat()

from utilsPrj.supabase_client import get_supabase_client, get_service_client
from pages.views.master_charts import master_charts_delete
from pages.views.master_sentences import master_sentences_delete
from pages.views.master_tables import master_tables_delete
# from .llm_utils import process_data_in_supabase
from .ai_chain import process_data_in_supabase

def llm_object_save(request, table_name):

    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_supabase_client(access_token, refresh_token)

        user = request.session.get("user")
        user_id = user.get("id")

        data = json.loads(request.body)
        # selected_docid = data.get("docid")
        selected_chapteruid = data.get("chapteruid")
        selected_objectnm = data.get("objectnm")
        selected_datauid = data.get("datauid")
        selected_gptq = data.get("gptq")
        selected_display_type = data.get("displaytype") 

        objects = process_data_in_supabase(
            supabase, 
            table_name="objects", 
            process_type="select",
            process_data={},
            conditions={"chapteruid": selected_chapteruid,
                        "objectnm": selected_objectnm}, 
            columns="*"
        )
        
        object_uid = objects[0]['objectuid']
        object_creator = objects[0]['creator']
        gen_typecd = "AI"

        existing = process_data_in_supabase(
            supabase, 
            table_name=table_name, 
            process_type="select",
            process_data={},
            conditions={"chapteruid": selected_chapteruid,
                        "objectnm": selected_objectnm}, 
            columns="datauid"
        )

        now = datetime.now().isoformat()

        if existing:
            try:
                update_data = {
                    "gentypecd" : gen_typecd,
                    "displaytype": selected_display_type, 
                    "gptq": selected_gptq,
                    "datauid": selected_datauid
                }
                res = process_data_in_supabase(
                    supabase, 
                    table_name=table_name, 
                    process_type="update",
                    process_data=update_data,
                    conditions={"chapteruid": selected_chapteruid,
                                "objectnm": selected_objectnm},
                )

            except Exception as e:
                print("ERROR: ", str(e))
                raise

        else:
            # now = datetime.now().isoformat()
            insert_data = {
                "objectuid": object_uid,
                "chapteruid": selected_chapteruid,
                "objectnm": selected_objectnm,
                "datauid": selected_datauid,
                "gentypecd" : gen_typecd,
                "displaytype": selected_display_type,
                "gptq": selected_gptq,
                "creator": object_creator,
                "createdts": now
            }

            res = process_data_in_supabase(
                supabase, 
                table_name=table_name, 
                process_type="insert",
                process_data=insert_data,
                conditions={},
            )

        res_objects = process_data_in_supabase(
            supabase,
            table_name="objects",
            process_type="update",
            process_data={
                "objectsettingyn": True,
                "useyn": True,
                "modifier": user_id,
                "modifydts": now
            },
            conditions={"objectuid": object_uid}
        )

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


def llm_prompt_sample_save(request, table_name):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})
    
    try:
        supabase = get_service_client()
        user = request.session.get("user")
        creator = user["id"]
        
        data = json.loads(request.body)
        selected_datauid = data.get("datauid")
        object_typecd = data.get("objecttypecd")
        selected_display_type = data.get("displaytype")
        selected_prompt = data.get("prompt")
        selected_prompt_name = data.get("promptnm", "").strip()
        selected_prompt_desc = data.get("promptdesc")
        selected_promptuid = data.get("promptuid")  # ✅ 기존 프롬프트 UID
        force_update = data.get("force_update", False)

        
        # 1. 프롬프트 이름 검증
        if not selected_prompt_name:
            return JsonResponse({
                "success": False, 
                "error": "name_required",
                "message": "프롬프트 이름을 입력해주세요."
            })
        
        # 2. 기존 프롬프트 수정인지 확인
        if selected_promptuid:
            if not force_update:
                # 수정 확인 요청
                return JsonResponse({
                    "success": False,
                    "error": "confirm_update",
                    "message": "샘플 프롬프트가 수정되었습니다. 저장할까요?",
                    "promptuid": selected_promptuid
                })
            
            update_data = process_data_in_supabase(
                supabase, 
                table_name=table_name, 
                process_type="update",
                process_data={
                    "promptnm": selected_prompt_name,
                    "prompt": selected_prompt,
                    "desc": selected_prompt_desc,
                    "displaytype": selected_display_type
                },
                conditions={"promptuid": selected_promptuid}
            )

            return JsonResponse({"success": True, "message": "수정되었습니다."})
        
        # 3. 신규 저장
        new_promptuid = str(uuid.uuid4())

        insert_data = process_data_in_supabase(
            supabase, 
            table_name=table_name, 
            process_type="insert",
            process_data={
                "promptuid": new_promptuid,
                "objecttypecd": object_typecd,
                "datauid": selected_datauid,
                "promptnm": selected_prompt_name,
                "prompt": selected_prompt,
                "desc": selected_prompt_desc,
                "displaytype": selected_display_type,
                "creator": creator
            },
            conditions={}
        )

        return JsonResponse({"success": True, "message": "저장되었습니다."})
        
    except Exception as e:
        print(f"Error in llm_prompt_sample_save: {str(e)}")  # ✅ 디버깅용
        return JsonResponse({"success": False, "error": str(e)})



def llm_prompt_sample_delete(request, table_name):
    """샘플 프롬프트 삭제"""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."})
    
    try:
        supabase = get_service_client()
        data = json.loads(request.body)
        promptuid = data.get("promptuid")
        
        if not promptuid:
            return JsonResponse({
                "success": False,
                "error": "promptuid_required",
                "message": "삭제할 프롬프트를 선택해주세요."
            })
        
        # promptuid로 삭제
        result = process_data_in_supabase(
            supabase,
            table_name=table_name,
            process_type="delete",
            process_data={},
            conditions={"promptuid": promptuid}
        )
        
        return JsonResponse({"success": True, "message": "삭제되었습니다."})
        
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e), "message": f"삭제 중 오류가 발생했습니다: {str(e)}"})



def llm_object_delete(request, table_name):
    if table_name == "charts":
        master_charts_delete(request)
        return True
    elif table_name == "sentences":
        master_sentences_delete(request)
        return True
    elif table_name == "tables":
        master_tables_delete(request)
        return True
    else:
        return False


