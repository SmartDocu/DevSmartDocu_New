# 20250926

import json, re, io, uuid, os, tempfile, subprocess
from datetime import datetime, timezone

from pathlib import Path
import time

# HTML To Word 용
import tempfile
from bs4 import BeautifulSoup

import matplotlib, base64
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc
from PIL import Image

from anthropic import Anthropic
from langchain_core.output_parsers.string import StrOutputParser

import traceback
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from threading import Lock, Semaphore, Thread



_db_semaphore = Semaphore(4)

from utilsPrj.ai_chain import *

# from utilsPrj.query_runner import run_query, apply_column_display_mapping
# from utilsPrj.data_runner import run_data
from utilsPrj.process_data import process_data, apply_column_display_mapping
from utilsPrj.chart_utils import draw_chart    # 차트 용
from utilsPrj.table_utils import draw_table    # 표 용
from utilsPrj.sentences_utils import draw_sentences    # 문자 용
from utilsPrj.docx_read import convert_docx_to_html_2    # 업로드 용
from utilsPrj.private_storage import resolve_template_bytes
from docx import Document as _DocxDocument
from utilsPrj.chapter_making_ai_table import render_preview_table

from utilsPrj.supabase_client import get_thread_supabase, cleanup_thread_client, SUPABASE_SCHEMA
from d2shared.llm_logger import log_doc_llm_call
# from utilsPrj.supabase_client import supabase

from collections import defaultdict
from queue import Queue

# 로그 큐 (스레드 안전)
_log_queue = Queue()
_log_lock = threading.Lock()

def queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid, objectuid, objecttypecd, user_id, progressrate, run_start_dts, gencontenttypecd=None):
    """로그를 큐에 추가 (즉시 DB 호출 안 함)"""
    log_data = {
        'type': 'genobject',
        'genobjectuid': genobjectuid,
        'gen_chapter_uid': gen_chapter_uid,
        'chapter_uid': chapter_uid,
        'objectuid': objectuid,
        'objecttypecd': objecttypecd,
        'user_id': user_id,
        'progressrate': progressrate,
        'timestamp': run_start_dts,
        'gencontenttypecd': gencontenttypecd
    }
    _log_queue.put(log_data)


def queue_genobject_run_log(genobjectuid, objecttypecd, sourcebase, inputtoken, tenantid, useruid, run_start_dts):
    """로그를 큐에 추가 (즉시 DB 호출 안 함)"""
    log_data = {
        'type': 'genobjectrunlog',
        'genobjectuid': genobjectuid,
        'objecttypecd': objecttypecd,
        'sourcebase': sourcebase,
        'timestamp': run_start_dts,
        'inputtoken': inputtoken,
        'tenantid': tenantid,
        'useruid': useruid
    }
    _log_queue.put(log_data)

def queue_genobject_result(genobjectuid, genchapteruid, chapteruid, objectuid, objecttypecd, 
                           sourcebase, sourcetext, resulttext, user_id, run_start_dts):
    """genobject 결과를 큐에 추가 (upsert용)"""
    log_data = {
        'type': 'genobject_result',
        'genobjectuid': genobjectuid,
        'genchapteruid': genchapteruid,
        'chapteruid': chapteruid,
        'objectuid': objectuid,
        'objecttypecd': objecttypecd,
        'sourcebase': sourcebase,
        'sourcetext': sourcetext,
        'resulttext': resulttext,
        'progressrate': 100,
        'user_id': user_id,
        'timestamp': run_start_dts
    }
    _log_queue.put(log_data)


def flush_logs_to_db(supabase, log_source="AI"):
    """큐에 있는 모든 로그를 배치로 처리"""
    genobject_inserts = []
    genobject_updates = {}
    genobject_results = {}

    genobjectrunlog_inserts = []
    
    while not _log_queue.empty():
        log = _log_queue.get()
        
        if log['type'] == 'genobject':
            if log['progressrate'] == 20:
                genobject_inserts.append({
                    "genobjectuid": log['genobjectuid'],
                    "genchapteruid": log['gen_chapter_uid'],
                    "chapteruid": log['chapter_uid'],
                    "objectuid": log['objectuid'],
                    "objecttypecd": log['objecttypecd'],
                    "progressrate": log['progressrate'],
                    "creator": log['user_id'],
                    "createdts": log['timestamp'],
                    "gencontenttypecd": log.get('gencontenttypecd')
                })
            else:
                uid = log['genobjectuid']
                if uid not in genobject_updates or log['progressrate'] > genobject_updates[uid]['progressrate']:
                    genobject_updates[uid] = {
                        'genobjectuid': uid,
                        'progressrate': log['progressrate'],
                        "createdts": log['timestamp']
                    }
        
        elif log['type'] == 'genobjectrunlog':
            genobjectrunlog_inserts.append({
                'genobjectuid': log['genobjectuid'],
                'objecttypecd': log['objecttypecd'],
                'sourcebase': log['sourcebase'],
                'rundts': log['timestamp'],
                'inputtoken': log['inputtoken'],
                'tenantid': log['tenantid'],
                'useruid': log['useruid']
            })

        elif log['type'] == 'genobject_result':
            uid = log['genobjectuid']
            genobject_results[uid] = {
                'genobjectuid': uid,
                'genchapteruid': log['genchapteruid'],
                'chapteruid': log['chapteruid'],
                'objectuid': log['objectuid'],
                'objecttypecd': log['objecttypecd'],
                'sourcebase': log['sourcebase'],
                'sourcetext': log['sourcetext'],
                'resulttext': log['resulttext'],
                'progressrate': 100,
                'creator': log['user_id'],
                'createdts': log['timestamp']
            }

    try:
        if genobject_inserts:
            supabase.schema(SUPABASE_SCHEMA).table('genobjects').insert(genobject_inserts).execute()
            # print(f"[Batch-{log_source}] genobject inserted: {len(genobject_inserts)}개 (1회 호출)")
        
        if genobject_updates:
            updates_by_rate = defaultdict(list)
            for data in genobject_updates.values():
                updates_by_rate[data['progressrate']].append(data['genobjectuid'])
            
            for rate, uids in updates_by_rate.items():
                supabase.schema(SUPABASE_SCHEMA).table('genobjects').update(
                    {'progressrate': rate}
                ).in_('genobjectuid', uids).execute()
                # print(f"[Batch-{log_source}] genobject updated: progressrate={rate}, {len(uids)}개 (1회 호출)")
        



        if genobjectrunlog_inserts:
            supabase.schema(SUPABASE_SCHEMA).table('genobjectrunlog').insert(genobjectrunlog_inserts).execute()
            # print(f"[Batch-{log_source}] genobjectrunlog inserted: {len(genobjectrunlog_inserts)}개 (1회 호출)")

        if genobject_results:
            result_list = list(genobject_results.values())
            supabase.schema(SUPABASE_SCHEMA).table('genobjects').upsert(result_list).execute()
            # print(f"[Batch-{log_source}] genobject results upserted: {len(result_list)}개 (1회 호출)")
            
    except Exception as e:
        # print(f"[Batch Error] {e}")
        traceback.print_exc()


def process_ui_object(data_item, html_result, text_template, gen_chapter_uid, user_id, sep, replacestring=None):
    """UI 객체 공통 처리 함수"""

    # placeholder 교체
    if sep == 'Not':
        place_holder = replacestring
        if place_holder is None:
            place_holder = f"{{{data_item['objectnm']}}}"
        
        place_holder_with_p = f"<p>{place_holder}</p>"
        result_html = html_result if data_item['type'] != 'UI_sentence' else html_result.replace('\n', '<br>')

        if place_holder_with_p in text_template:
            text_template = text_template.replace(place_holder_with_p, result_html)
        elif place_holder in text_template:
            text_template = text_template.replace(place_holder, result_html)
    
    # 안전을 위하여 추가
    text_template += '<p></p>'

    gen_uuid = data_item['genobjectuid'] if data_item['genobjectuid'] else str(uuid.uuid4())

    run_start_dts = datetime.now(timezone.utc).isoformat()
    
    result = {
        'genobjectuid': gen_uuid,
        'genchapteruid': gen_chapter_uid,
        'chapteruid': data_item['chapteruid'],
        'objectuid': data_item['objectuid'],
        'objecttypecd': data_item['objecttypecd'],
        'sourcebase': data_item['sourcebase'],
        'sourcetext': data_item['sourcetext'],
        'resulttext': html_result,
        # 'resulttext': text_template,
        'progressrate': 100,
        'creator': user_id,
        'createdts': run_start_dts
    }

    return result, text_template


def process_ai_object(data_item, request, docid, gendoc_uid, chapter_uid, user_id, index, total, gen_chapter_uid, tenant_id, **kwargs):
    """AI 객체 처리 함수 (멀티스레드로 실행될 함수)"""
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_thread_supabase(access_token, refresh_token)

    gendocjobuid = kwargs.get("gendocjobuid")
    genchapterjobuid = kwargs.get("genchapterjobuid")
    project_id = request.session.get("user", {}).get("projectid")

    # gencontenttypecd: 문서 전체 생성(D) > 챕터 단위 처리(C) > 단일 항목 재작성(O)
    # 문서 전체 작성 시에는 gendocjobuid+genchapterjobuid 둘 다 들어오므로 gendocjobuid를 먼저 판별해야
    # 문서/챕터 단독 생성이 구분된다(gendocjobuid 없이 genchapterjobuid만 있으면 챕터 단독 생성).
    if gendocjobuid:
        gencontenttypecd = "D"
    elif genchapterjobuid:
        gencontenttypecd = "C"
    else:
        gencontenttypecd = "O"

    # get_llm_info()는 ai_chain._llm_info_cache로 이미 캐시되어(Supabase 재조회 없음) 여기서
    # 불러도 비용이 없다 — is_customeraikey/account_uid(로그용)만 얻는다.
    _, _, _, is_customeraikey, account_uid = get_llm_info(
        project_id=project_id, tenant_id=tenant_id, user_uid=user_id, service_code="Do",
    )
    # LLM 객체는 (project/tenant/user) 조합당 한 번만 만들고 재사용한다 — AI 오브젝트마다
    # (병렬 처리 시 동시에도) 매번 새로 인증·생성하지 않는다.
    llm = get_llm_clients(
        project_id=project_id, tenant_id=tenant_id, user_uid=user_id, service_code="Do",
    )
    total_tokens = {"input_tokens": 0, "output_tokens": 0}

    try:
        if data_item['genobjectuid']:
            genobjectuid = data_item['genobjectuid']

            gen_objects = supabase.schema(SUPABASE_SCHEMA).table("genobjects").select("*").eq("genchapteruid", gen_chapter_uid).eq("genobjectuid", genobjectuid).execute()
            raw_filterjson = gen_objects.data[0]["filterjson"]
            if raw_filterjson:
                filter_json = raw_filterjson if isinstance(raw_filterjson, dict) else json.loads(raw_filterjson)
            else:
                filter_json = {}

        else:
            filter_json = {}
            genobjectuid = str(uuid.uuid4())
            run_start_dts = datetime.now(timezone.utc).isoformat()
            queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid,
                            data_item['objectuid'], data_item['objecttypecd'], user_id, 20, run_start_dts,
                            gencontenttypecd=gencontenttypecd)

        data_item['genobjectuid'] = genobjectuid

        def _write_doc_log(is_success, errormessage, inputtoken, outputtoken, start_dts, end_dts):
            log_doc_llm_call(
                log_ctx={
                    "tenant_id": tenant_id,
                    "account_uid": account_uid,
                    "project_id": project_id,
                    "gencontenttypecd": gencontenttypecd,
                    "gendocjobuid": gendocjobuid,
                    "genchapterjobuid": genchapterjobuid,
                    "genobjectuid": genobjectuid,
                    "objectuid": data_item['objectuid'],
                    "is_customeraikey": is_customeraikey,
                    "creator": user_id,
                },
                llmmodelnm=getattr(llm, "model", None) or getattr(llm, "model_name", None) or "",
                inputtoken=inputtoken,
                outputtoken=outputtoken,
                is_success=is_success,
                errormessage=errormessage,
                startdts=start_dts,
                enddts=end_dts,
            )

        query = data_item['query'] or ""
        params = re.findall(r'@(\w+)', query)
        
        result_df = call_params_chat(request, supabase, docid, gendoc_uid, params, query, data_item['datauid'])
        question = data_item['sourcebase']
        object_type = data_item['objecttypecd']

        table_name = "datacols"
        conditions = {'datauid': data_item['datauid']}

        result_datacols = process_data_in_supabase(
            supabase,
            table_name=table_name,
            process_type="select",
            process_data={},
            conditions=conditions,
            columns="querycolnm, dispcolnm"
        )

        column_dict = {item['querycolnm']: item['dispcolnm'] for item in result_datacols}

        run_start_dts = datetime.now(timezone.utc).isoformat()
        queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid, 
                        data_item['objectuid'], data_item['objecttypecd'], user_id, 40, run_start_dts)
        

        ai_filter_json = {
            key: filter_json[val]
            for key, val in column_dict.items()
            if val in filter_json
        }

        if object_type == "CA":
            prompt = get_charts_prompt(result_df, column_dict, question, ai_filter_json)
        elif object_type == "SA":
            prompt = get_sentences_prompt(result_df, column_dict, question, ai_filter_json)
        elif object_type == "TA":
            prompt = get_tables_prompt(result_df, column_dict, question, ai_filter_json)
        else:
            return {
                "message_type": "error",
                "message": "객체(object) 타입이 분류되지 않는 타입입니다."
            }            

        _llm_start_dts = datetime.now(timezone.utc)
        full_chain = get_full_chain(llm, result_df, prompt, question, column_dict, object_type)
        try:
            response = full_chain.invoke({"question": question, "column_dict": column_dict})
        except Exception as _invoke_err:
            _write_doc_log(False, str(_invoke_err), 0, 0, _llm_start_dts, datetime.now(timezone.utc))
            raise
        _llm_end_dts = datetime.now(timezone.utc)

        if isinstance(response, dict) and "tokens" in response:
            total_tokens["input_tokens"] = response["tokens"]["input_tokens"]
            total_tokens["output_tokens"] = response["tokens"]["output_tokens"]

        # is_success는 status 파라미터 기본값이 아니라 실제 응답 결과로 판별한다
        _is_success = isinstance(response, dict) and response.get("status") in ("chart_drawn", "analysis_comment", "data_table")
        if _is_success:
            _error_message = None
        elif isinstance(response, dict):
            _error_message = f'알 수 없는 응답 상태: {response.get("status")}'
        else:
            _error_message = '응답 형식이 딕셔너리가 아닙니다.'

        _write_doc_log(_is_success, _error_message, total_tokens["input_tokens"], total_tokens["output_tokens"], _llm_start_dts, _llm_end_dts)

        run_start_dts = datetime.now(timezone.utc).isoformat()
        queue_genobject_run_log(data_item['genobjectuid'], data_item['objecttypecd'], data_item['sourcebase'], total_tokens["input_tokens"], tenant_id, user_id, run_start_dts)
        queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid, 
                        data_item['objectuid'], data_item['objecttypecd'], user_id, 60, run_start_dts)

        final_result = None
        if isinstance(response, dict):
            if response.get("status") == "chart_drawn":
                img_base64 = response["image_bytes"]
                final_result = f'<img src="data:image/png;base64,{img_base64}" alt="{data_item["objectnm"]} 차트" >'

            elif response.get("status") == "analysis_comment":
                final_result = response.get("result", "")
            
            elif response.get("status") == "data_table":
                data = response.get("result", "")
                table_header_json = response.get("table_header_json", "")
                table_data_json = response.get("table_data_json", "")
                
                header_json = json.loads(table_header_json)
                data_json = json.loads(table_data_json)

                if isinstance(data_json, list):
                    # print(f"WARNING: data_json is list, converting to dict")
                    # print(f"Original value: {data_json}")
                    data_json = {}  # 또는 적절한 변환 로직

                final_result = render_preview_table(header_json, data_json, data)
                final_result = final_result.replace('<div id="output-box"><table', '<table')
                final_result = final_result.replace('</table></div>', '</table>')

            else:
                # print(f"!!! Unknown status: {response.get('status')}")
                return {
                    'success': False,
                    'error': f'알 수 없는 응답 상태: {response.get("status")}'
                }
        else:
            return {
                'success': False,
                'error': '응답 형식이 딕셔너리가 아닙니다.'
            }

        gen_uuid = data_item['genobjectuid'] if data_item['genobjectuid'] else str(uuid.uuid4())
        run_start_dts = datetime.now(timezone.utc).isoformat()
        
        result = {
            'genobjectuid': gen_uuid,
            'genchapteruid': gen_chapter_uid,
            'chapteruid': chapter_uid,
            'objectuid': data_item['objectuid'],
            'objecttypecd': data_item['objecttypecd'],
            'sourcebase': data_item['sourcebase'],
            'sourcetext': data_item['sourcetext'],
            'resulttext': final_result,
            'progressrate': 100,
            'creator': user_id,
            'createdts': run_start_dts,
            'gendocjobuid': gendocjobuid,
            'genchapterjobuid': genchapterjobuid,
            'gencontenttypecd': gencontenttypecd,
        }

        return {
            'success': True,
            'result': result,
            'final_result': final_result,
            'objectnm': data_item['objectnm'],
            'index': index
        }
        
    except Exception as e:
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'objectnm': data_item['objectnm'],
            'index': index
        }


def prepare_datas_from_template(supabase, read_text_template):
    """read_text_template에서 datas 리스트 생성"""
    datas = []
    count_loop = 0
    
    for template_item in read_text_template:
        count_loop += 1
        if template_item["datauid"]:
            read_datas = supabase.schema(SUPABASE_SCHEMA).table("datas").select("*").eq('datauid', template_item["datauid"]).execute().data
            read_datas[0]['chapteruid'] = template_item['chapteruid']
            read_datas[0]['objectuid'] = template_item['objectuid']
            read_datas[0]['objectnm'] = template_item["objectnm"]

            read_datas[0]['type'] = template_item['type']
            read_datas[0]['objecttypecd'] = template_item['objecttypecd']
            read_datas[0]['sourcebase'] = template_item["sourcebase"]
            read_datas[0]['sourcetext'] = template_item["sourcetext"]
            read_datas[0]['etc1'] = template_item["etc1"]
            read_datas[0]['etc2'] = template_item["etc2"]
            read_datas[0]['genobjectuid'] = template_item['genobjectuid']

            datas.append(read_datas)
        elif template_item.get("useyn") is False:
            # 사용여부=아니오인 항목은 미설정 상태여도 건너뛴다(에러 없이 플레이스홀더 미처리 상태로 둠)
            continue
        else:
            raise Exception(f'챕터명: {template_item["chapternm"]} / 항목: {template_item["objectnm"]}에 대한 설정이 되어 있지 않습니다.')
    
    return datas


def separate_ui_ai_objects(datas):
    """UI 객체와 AI 객체 분리"""
    ui_objects = []
    ai_objects = []
    
    for idx, data_list in enumerate(datas):
        data_item = data_list[0]
        
        if data_item['type'] in ['UI_table', 'UI_chart', 'UI_sentence']:
            ui_objects.append((idx, data_item))
        elif data_item['objecttypecd'] in ['CA', 'TA', 'SA']:
            ai_objects.append((idx, data_item))
    
    return ui_objects, ai_objects


def get_source_query_for_df(supabase, data_item):
    """datasourcecd가 df/dfv인 경우 원본 쿼리 조회"""
    query = data_item['query'] or ""
    data_source_cd = data_item["datasourcecd"] or ""
    source_data_uid = data_item["sourcedatauid"]

    if data_source_cd in ("df", "dfv") and source_data_uid:
        source_resp = supabase.schema(SUPABASE_SCHEMA).table("datas").select("*").eq("datauid", source_data_uid).execute()
        source_data = source_resp.data or []

        if source_data:
            source_record = source_data[0]
            source_datasourcecd = source_record.get("datasourcecd", "")
            source_query = source_record.get("query", "")

            if source_datasourcecd == "db":
                query = source_query
    
    return query


def process_single_ui_object(request, supabase, data_item, docid, gendoc_uid, data_uid, params, query):
    """단일 UI 객체의 HTML 생성"""
    columns, dict_rows = call_params_ui(request, supabase, docid, gendoc_uid, data_uid, params, query)

    # filterjson 기반 행 필터링 (filterjson 키 = querycolnm, dict_rows 키 = dispcolnm)
    genobjectuid = data_item.get('genobjectuid')
    if genobjectuid:
        go_resp = supabase.schema(SUPABASE_SCHEMA).table("genobjects") \
            .select("filterjson").eq("genobjectuid", genobjectuid).execute()
        filterjson = go_resp.data[0].get("filterjson") if go_resp.data else None
        if filterjson and dict_rows:
            if isinstance(filterjson, str):
                filterjson = json.loads(filterjson)
            data_uid_for_map = data_item.get('datauid')
            col_resp = supabase.schema(SUPABASE_SCHEMA).table("datacols") \
                .select("querycolnm, dispcolnm").eq("datauid", data_uid_for_map).execute()
            q2d = {c["querycolnm"]: c.get("dispcolnm") or c["querycolnm"]
                   for c in (col_resp.data or [])}
            for key, value in filterjson.items():
                disp_key = q2d.get(key, key)
                dict_rows = [row for row in dict_rows if str(row.get(disp_key, "")) == str(value)]

    if data_item["type"] == 'UI_table': 
        tablejson = json.loads(data_item['sourcebase'])
        coljson = json.loads(data_item['sourcetext'])
        final_html = draw_table(request, columns, dict_rows, tablejson, coljson)
        
    elif data_item["type"] == 'UI_chart':
        matplotlib.use('Agg')
        charttypecd = data_item['sourcebase']
        chartjson = json.loads(data_item['sourcetext'])

        font_path = 'static/fonts/NanumGothic-Regular.ttf'
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        matplotlib.rc('font', family=font_name)

        fig = draw_chart(request, supabase, charttypecd, dict_rows, chartjson, data_uid)

        try:
            chart_width = float(data_item['etc1'] or 500)
            chart_height = float(data_item['etc2'] or 250)
            dpi = 96
            fig.set_size_inches(chart_width / dpi, chart_height / dpi)
        except Exception:
            fig.set_size_inches(5, 2.5)

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)

        img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        final_html = f'<img src="data:image/png;base64,{img_base64}" style="width:{int(chart_width)}px;height:{int(chart_height)}px;" alt="{data_item["objectnm"]} 차트">'
        
    elif data_item["type"] == 'UI_sentence':                             
        seneteces = supabase.schema(SUPABASE_SCHEMA).table('sentences').select('sentencestext').eq('objectnm', data_item['objectnm']).eq('chapteruid', data_item['chapteruid']).execute().data
        template_text = seneteces[0]["sentencestext"]
        if template_text and dict_rows:
            final_html = draw_sentences(request, supabase, dict_rows, template_text, data_uid)
        else:
            final_html = ""
    else:
        final_html = ""
    
    return final_html


def process_ui_objects_sequentially(request, supabase, ui_objects, datas, docid, gendoc_uid,
                                    gen_chapter_uid, chapter_uid, user_id, text_template,
                                    sep, gendocjobuid=None, genchapterjobuid=None):
    """UI 객체들을 순차적으로 처리"""

    # gencontenttypecd: 문서 전체 생성(D) > 챕터 단위 처리(C) > 단일 항목 재작성(O)
    # 문서 전체 작성 시에는 gendocjobuid+genchapterjobuid 둘 다 들어오므로 gendocjobuid를 먼저 판별해야
    # 문서/챕터 단독 생성이 구분된다(gendocjobuid 없이 genchapterjobuid만 있으면 챕터 단독 생성).
    if gendocjobuid:
        gencontenttypecd = "D"
    elif genchapterjobuid:
        gencontenttypecd = "C"
    else:
        gencontenttypecd = "O"

    replace_data = supabase.schema(SUPABASE_SCHEMA).table('genobjects').select('genobjectuid', 'replacestring').eq('genchapteruid', gen_chapter_uid).execute().data
    replace_dict = {item['genobjectuid']: item['replacestring'] for item in replace_data}

    # for ui_idx, (original_idx, data_item) in enumerate(ui_objects):
    for ui_idx, (original_idx, data_item) in enumerate(ui_objects):
        genobjectuid = None
        
        try:
            if sep == 'Not':
                yield {
                    'type': 'progress',
                    'current': ui_idx + 1,
                    'total': len(datas),
                    'message': f'UI 객체 처리 중... [{data_item["objectnm"]}] ({ui_idx + 1}/{len(ui_objects)})'
                }  

            data_uid = data_item['datauid']
            query = get_source_query_for_df(supabase, data_item)

            if data_item['genobjectuid']:
                genobjectuid = data_item['genobjectuid']
            else:
                genobjectuid = str(uuid.uuid4())
                run_start_dts = datetime.now(timezone.utc).isoformat()
                queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid,
                                data_item['objectuid'], data_item['objecttypecd'], user_id, 20, run_start_dts,
                                gencontenttypecd=gencontenttypecd)

            data_item['genobjectuid'] = genobjectuid
            
            params = re.findall(r'@(\w+)', query)

            run_start_dts = datetime.now(timezone.utc).isoformat()
            queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid,
                            data_item['objectuid'], data_item['objecttypecd'], user_id, 40, run_start_dts)

            final_html = process_single_ui_object(request, supabase, data_item, docid, gendoc_uid, data_uid, params, query)
                
            run_start_dts = datetime.now(timezone.utc).isoformat()
            queue_genobject_log(genobjectuid, gen_chapter_uid, chapter_uid, 
                            data_item['objectuid'], data_item['objecttypecd'], user_id, 60, run_start_dts)

            replacestring = replace_dict.get(genobjectuid)
            result, result_text_template = process_ui_object(data_item, final_html, text_template, gen_chapter_uid, user_id, sep, replacestring)
            text_template = result_text_template

            # 성공 시 이전 실패 흔적(errorcd/errormessage) 제거
            result['is_success'] = True
            result['errorcd'] = None
            result['errormessage'] = None
            result['gendocjobuid'] = gendocjobuid
            result['genchapterjobuid'] = genchapterjobuid
            result['gencontenttypecd'] = gencontenttypecd
            update_genobjects(supabase, [result])

            if sep == "Not":
                genchapters = {
                    'genchapteruid': gen_chapter_uid,
                    'gentexttemplate': result_text_template,
                    'createuserid': result['creator'],
                    'createfiledts': datetime.now(timezone.utc).isoformat()
                }
            else:
                genchapters = {
                    'genchapteruid': gen_chapter_uid,
                    'gentexttemplate': result_text_template,
                    'createuserid': result['creator'],
                }

            update_genchapters(supabase, genchapters, gen_chapter_uid)

            queue_genobject_result(
                result['genobjectuid'],
                gen_chapter_uid,
                chapter_uid,
                data_item['objectuid'],
                data_item['objecttypecd'],
                result['sourcebase'],
                result['sourcetext'],
                result['resulttext'],
                user_id,
                result['createdts']
            )

        except Exception as e:
            # print(f"UI 객체 처리 실패: {data_item.get('objectnm', '')} - {str(e)}")
            traceback.print_exc()

            _fail_uid = genobjectuid or data_item.get('genobjectuid')
            if _fail_uid:
                try:
                    update_genobjects(supabase, [{
                        'genobjectuid': _fail_uid,
                        'is_success': False,
                        'errorcd': 'ERR',
                        'errormessage': str(e)[:2000],
                        'gendocjobuid': gendocjobuid,
                        'genchapterjobuid': genchapterjobuid,
                    }])
                except Exception:
                    pass

            yield {
                'type': 'item_error',
                'chapter_name': '',
                'object_name': data_item.get('objectnm', '알 수 없음'),
                'error': str(e),
                'message': f"UI 항목 실패: {data_item.get('objectnm', '')} - {str(e)}"
            }

            continue
    
    # UI 객체 로그 일괄 저장
    if ui_objects:
        flush_logs_to_db(supabase, log_source="UI")
        # print(f"[Log] UI 객체 로그 일괄 저장 완료 ({len(ui_objects)}개)")
        cleanup_thread_client()
    
    yield {'type': 'ui_complete', 'text_template': text_template}





# import time
# from concurrent.futures import ThreadPoolExecutor, as_completed

def process_ai_object_with_tracking(data_item, request, docid, gendoc_uid, chapter_uid,
                                    user_id, original_idx, datas_len, gen_chapter_uid,
                                    tenant_id, gendocjobuid=None, genchapterjobuid=None):
    """AI 객체 처리 (재시도 없이 결과만 반환)"""

    result_data = process_ai_object(
        data_item,
        request,
        docid,
        gendoc_uid,
        chapter_uid,
        user_id,
        original_idx,
        datas_len,
        gen_chapter_uid,
        tenant_id,
        gendocjobuid=gendocjobuid,
        genchapterjobuid=genchapterjobuid,
    )

    return result_data



#####
def retry_failed_items_sequentially(failed_items, request, docid, gendoc_uid, chapter_uid,
                                   user_id, datas_len, gen_chapter_uid, tenant_id,
                                   gendocjobuid=None, genchapterjobuid=None, max_retries=3):
    """오류난 항목들을 순차적으로 재시도"""

    retry_results = {}

    for original_idx, data_item in failed_items:
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                # print(f"[순차 재시도 {attempt}/{max_retries}] {data_item.get('objectnm', '')}")

                result_data = process_ai_object_with_tracking(
                    data_item,
                    request,
                    docid,
                    gendoc_uid,
                    chapter_uid,
                    user_id,
                    original_idx,
                    datas_len,
                    gen_chapter_uid,
                    tenant_id,
                    gendocjobuid=gendocjobuid,
                    genchapterjobuid=genchapterjobuid,
                )
                
                # 성공한 경우
                if result_data['success']:
                    result_data['attempt'] = attempt
                    result_data['retried'] = True  # 재시도를 통해 성공했음을 표시
                    retry_results[original_idx] = result_data
                    # print(f"✓ {data_item.get('objectnm', '')} - {attempt}번째 재시도 성공")
                    break
                
                last_error = result_data.get('error', '알 수 없는 오류')
                
                if attempt < max_retries:
                    time.sleep(0.5)  # 순차 재시도는 간격을 짧게
            
            except Exception as e:
                last_error = str(e)
        
        else:
            # max_retries 만큼 시도했지만 모두 실패
            retry_results[original_idx] = {
                'success': False,
                'objectnm': data_item.get('objectnm', ''),
                'error': f"순차 재시도 후에도 실패: {last_error}",
                'retried': True,
                'final_failure': True
            }
            # print(f"✗ {data_item.get('objectnm', '')} - 최종 실패")
    
    return retry_results


def process_ai_objects_parallel(request, ai_objects, datas, docid, gendoc_uid,
                                chapter_uid, user_id, gen_chapter_uid, sep,
                                tenant_id,
                                progress_lock, completed_count, ui_count,
                                gendocjobuid=None, genchapterjobuid=None):
    """AI 객체들을 병렬로 처리 후 오류 항목들만 순차적으로 재시도"""
    
    if not ai_objects:
        yield {'type': 'ai_complete', 'ai_results': {}}
        return
    
    ai_results = {}
    failed_items = []  # 오류난 항목 저장
    max_workers = min(len(ai_objects), 4)
    
    # ========== 1단계: 병렬 처리 ==========
    # print(f"[1단계] 병렬 처리 시작 (4개 동시)")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try: 
            future_to_index = {}
            for original_idx, data_item in ai_objects:
                future = executor.submit(
                    process_ai_object_with_tracking,
                    data_item,
                    request,
                    docid,
                    gendoc_uid,
                    chapter_uid,
                    user_id,
                    original_idx,
                    len(datas),
                    gen_chapter_uid,
                    tenant_id,
                    gendocjobuid,
                    genchapterjobuid,
                )
                future_to_index[future] = (original_idx, data_item)

            for future in as_completed(future_to_index):
                original_idx, data_item = future_to_index[future]

                # if (original_idx + 1) % 5 == 0:
                #     time.sleep(20)
                
                try:
                    result_data = future.result()
                    
                    if result_data['success']:
                        result_data['attempt'] = 1  # 첫 시도에서 성공
                        ai_results[original_idx] = result_data
                        
                        # print(f"{data_item.get('objectnm', '')} - 첫 시도에서 성공")
                        
                        with progress_lock:
                            completed_count[0] += 1
                            if sep == 'Not':
                                yield {
                                    'type': 'progress',
                                    'current': ui_count + completed_count[0],
                                    'total': len(datas),
                                    'message': f'AI 객체 처리 중... [{data_item["objectnm"]}] ({completed_count[0]}/{len(ai_objects)})',
                                    'attempt': 1
                                }
                    else:
                        # 오류난 항목은 리스트에 저장
                        failed_items.append((original_idx, data_item))
                        # print(f"{data_item.get('objectnm', '')} - 오류 발생, 나중에 재시도 예정")
                        
                        with progress_lock:
                            completed_count[0] += 1

                except Exception as e:
                    failed_items.append((original_idx, data_item))
                    # print(f"{data_item.get('objectnm', '')} - 예외 발생: {str(e)}")
                    
                    with progress_lock:
                        completed_count[0] += 1
        
        finally: 
            access_token = request.session.get("access_token")
            refresh_token = request.session.get("refresh_token")
            supabase = get_thread_supabase(access_token, refresh_token)
            flush_logs_to_db(supabase)
            # print(f"[Log] 1단계 로그 저장 완료")
            
            cleanup_thread_client()
    
    # ========== 2단계: 순차 재시도 ==========
    if failed_items:
        # print(f"\n[2단계] 순차 재시도 시작 ({len(failed_items)}개 항목)")
        retry_results = retry_failed_items_sequentially(
            failed_items,
            request,
            docid,
            gendoc_uid,
            chapter_uid,
            user_id,
            len(datas),
            gen_chapter_uid,
            tenant_id,
            gendocjobuid=gendocjobuid,
            genchapterjobuid=genchapterjobuid,
            max_retries=3,
        )
        
        # 재시도 결과 처리
        for original_idx, result_data in retry_results.items():
            ai_results[original_idx] = result_data
            if result_data['success']:
                ai_results[original_idx] = result_data
                
                with progress_lock:
                    # 진행률 업데이트
                    if sep == 'Not':
                        yield {
                            'type': 'progress',
                            'current': ui_count + completed_count[0],
                            'total': len(datas),
                            'message': f"재시도 성공: {result_data.get('objectnm', '')} - {result_data.get('attempt', 1)}번째 시도",
                            'attempt': result_data.get('attempt', 1)
                        }
            else:
                # 최종 실패
                data_item = next((item for idx, item in failed_items if idx == original_idx), {})
                yield {
                    'type': 'item_error',
                    'chapter_name': data_item.get('chapternm', ''),
                    'object_name': result_data.get('objectnm', ''),
                    'error': result_data.get('error', ''),
                    'message': f"최종 실패: {result_data.get('objectnm', '')} - {result_data.get('error', '')}"
                }
        
        # 2단계 로그 저장
        access_token = request.session.get("access_token")
        refresh_token = request.session.get("refresh_token")
        supabase = get_thread_supabase(access_token, refresh_token)
        flush_logs_to_db(supabase)
        # print(f"[Log] 2단계 로그 저장 완료")
    
    # ========== 최종 결과 반환 ==========
    summary = {
        'total': len(ai_objects),
        'success': len(ai_results),
        'failed': len(ai_objects) - len(ai_results)
    }
    # print(f"\n[완료] 성공: {summary['success']}/{summary['total']}, 실패: {summary['failed']}")
    # cleanup_thread_client()
    
    yield {'type': 'ai_complete', 'ai_results': ai_results, 'summary': summary}


def apply_ai_results_to_template(supabase, ai_objects, ai_results, text_template, gen_chapter_uid, user_id, sep,
                                  gendocjobuid=None, genchapterjobuid=None):
    """AI 결과를 템플릿에 순서대로 적용"""
    replace_dict = {}
    replace_data = supabase.schema(SUPABASE_SCHEMA).table('genobjects').select('genobjectuid', 'replacestring').eq('genchapteruid', gen_chapter_uid).execute().data
    # replace_dict = {item['genobjectuid']: item['replacestring'] for item in replace_data if item['replacestring'] is not None}
    replace_dict = {item['genobjectuid']: item['replacestring'] for item in replace_data}

    for original_idx, data_item in ai_objects:
        
        if original_idx in ai_results.keys():
            result_data = ai_results[original_idx]

            final_result = result_data.get('final_result') or ""
            # gen_object_uid = result_data["result"]["genobjectuid"]
            result_inner = result_data.get("result") or {}
            gen_object_uid = result_inner.get("genobjectuid") if isinstance(result_inner, dict) else None
            if not gen_object_uid:
                gen_object_uid = data_item.get('genobjectuid')

            if not result_data.get('success', False):
                final_result = ""

            if not result_data["success"]:
                result_data["result"] = ""
                if gen_object_uid:
                    update_genobjects(supabase, [{
                        'genobjectuid': gen_object_uid,
                        'is_success': False,
                        'errorcd': 'ERR',
                        'errormessage': str(result_data.get('error') or '')[:2000],
                        'gendocjobuid': gendocjobuid,
                        'genchapterjobuid': genchapterjobuid,
                    }])
            else:
                # place_holder = f"{{{{{data_item['objectnm']}}}}}"
                # place_holder_with_p = f"<p>{place_holder}</p>"
                place_holder = replace_dict.get(gen_object_uid)

                if place_holder is None:
                    continue
                # place_holder = f"{replace_dict[gen_object_uid]}"
                place_holder_with_p = f"<p>{place_holder}</p>"
                
                if place_holder_with_p in text_template:
                    text_template = text_template.replace(place_holder_with_p, final_result)
                elif place_holder in text_template:
                    text_template = text_template.replace(place_holder, final_result)

                text_template += '<p></p>'

                if sep == "Not":
                    update_genchapters(supabase, {
                        'genchapteruid': gen_chapter_uid,
                        'gentexttemplate': text_template,
                        'createuserid': user_id,
                        'createfiledts': datetime.now(timezone.utc).isoformat()
                    }, gen_chapter_uid)

            if result_data.get('result') and isinstance(result_data.get('result'), dict):
                # 성공 시 이전 실패 흔적(errorcd/errormessage) 제거
                result_data['result']['is_success'] = True
                result_data['result']['errorcd'] = None
                result_data['result']['errormessage'] = None
                update_genobjects(supabase, [result_data['result']])
            
    return text_template


def replace_doc(request, supabase, user_id, gen_chapter_uid, make_type, obj, sep, **kwargs):

    user = request.session.get("user")
    tenant_id = user.get("tenantid")

    """Generator 함수 - AI 객체만 멀티스레드 처리"""

    progress_lock = Lock()
    completed_count = [0]

    run_yn = False
    genobjectuid = None

    try:
        divide = kwargs.get("divide", "")
        doc_write = kwargs.get("doc_write", False)
        gendocjobuid = kwargs.get("gendocjobuid")
        genchapterjobuid = kwargs.get("genchapterjobuid")

        ## genchapter 추출
        read_genchapter = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('*').eq('genchapteruid', gen_chapter_uid).execute().data
        docid = read_genchapter[0]['docid']
        gendoc_uid = read_genchapter[0]['gendocuid']
        chapter_uid = read_genchapter[0]['chapteruid']
        updatafileurl = read_genchapter[0]['updatefileurl']
        genchapters = ''
        
        read_chapter = supabase.schema(SUPABASE_SCHEMA).table('chapters').select('texttemplate').eq('chapteruid', chapter_uid).execute().data
        # read_chapter = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('flattexttemplate').eq('chapteruid', chapter_uid).execute().data

        now = datetime.now(timezone.utc).isoformat()
        
        # 자동 작성 기준
        if make_type == 'create':
            if obj == 'rewrite':
                # sep == 'Not'이면 전체, 아니면 개별 작성용 texttemplate 가져오기
                if sep == 'Not':
                    # 챕터 재작성 시작 시각 기록 (완료 시각은 createfiledts에 별도 기록)
                    update_genchapters(supabase, {
                        'genchapteruid': gen_chapter_uid,
                        'createfilestartdts': now,
                    }, gen_chapter_uid)

                    objects_erase_resulttext = supabase.schema(SUPABASE_SCHEMA).table("genobjects")\
                        .select("genobjectuid, resulttext, filterjson")\
                        .eq("genchapteruid", gen_chapter_uid)\
                        .execute().data

                    for row in objects_erase_resulttext:
                        update_data = {
                            "genobjectuid": row["genobjectuid"],
                            "resulttext": ""
                        }

                        supabase.schema(SUPABASE_SCHEMA).table("genobjects").update(update_data).eq("genobjectuid", row["genobjectuid"]).execute()

                    read_flat = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('flattexttemplate').eq('genchapteruid', gen_chapter_uid).execute().data
                    flat_template = read_flat[0].get('flattexttemplate') if read_flat else None
                    text_template = flat_template or read_chapter[0]['texttemplate']
                else:
                    gen_text_template = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('gentexttemplate').eq('genchapteruid', gen_chapter_uid).execute().data
                    # 빈 리스트 체크
                    if gen_text_template and len(gen_text_template) > 0:
                        gentexttemplate = gen_text_template[0].get('gentexttemplate')
                        text_template = gentexttemplate or read_chapter[0]['texttemplate']
                    else:
                        text_template = read_chapter[0]['texttemplate']

                if sep == 'Not':
                    # RPC 대신 genobjects 직접 조회 (FOR 루프 확장으로 동일 objectuid에 genobject 여러 개)
                    _type_map = {
                        "CA": "AI_chart",  "TA": "AI_table",  "SA": "AI_sentence",
                        "CU": "UI_chart",  "TU": "UI_table",  "SU": "UI_sentence",
                    }
                    _domain_tbl_map = {
                        "CA": "charts", "TA": "tables", "SA": "sentences",
                        "CU": "charts", "TU": "tables", "SU": "sentences",
                    }
                    read_text_template = []
                    go_rows = supabase.schema(SUPABASE_SCHEMA).table("genobjects").select("*").eq("genchapteruid", gen_chapter_uid).execute().data
                    for go in go_rows:
                        obj_rows = supabase.schema(SUPABASE_SCHEMA).table("objects").select("*").eq("objectuid", go["objectuid"]).execute().data
                        if not obj_rows:
                            continue
                        obj = obj_rows[0]
                        if not obj.get("useyn"):
                            # 사용여부=아니오인 항목은 재작성 대상에서 제외하고,
                            # flattexttemplate에 남아있는 placeholder는 빈 문자열로 치환해 원문 노출을 막는다.
                            # 실제 placeholder는 홑중괄호 {objectnm}가 아니라 겹중괄호 {{objectnm}}(+[params])
                            # 형태이며, genobjects.replacestring에 추출 당시 원문 그대로 저장돼 있으므로 그걸 우선 사용한다.
                            replace_targets = []
                            replacestring = go.get("replacestring")
                            if replacestring:
                                replace_targets.append(replacestring)
                            objectnm = obj.get("objectnm") or ""
                            replace_targets.append(f"{{{{{objectnm}}}}}")
                            for target in replace_targets:
                                target_with_p = f"<p>{target}</p>"
                                if target_with_p in text_template:
                                    text_template = text_template.replace(target_with_p, "")
                                elif target in text_template:
                                    text_template = text_template.replace(target, "")
                            continue
                        typecd = go.get("objecttypecd") or obj.get("objecttypecd")
                        domain_row = {}
                        domain_tbl = _domain_tbl_map.get(typecd)
                        if domain_tbl:
                            d_rows = supabase.schema(SUPABASE_SCHEMA).table(domain_tbl).select("*").eq("objectuid", go["objectuid"]).execute().data
                            if d_rows:
                                domain_row = d_rows[0]
                        if typecd == "CU":
                            sourcebase = domain_row.get("displaytype") or obj.get("sourcebase")
                            sourcetext = domain_row.get("chartjson") or obj.get("sourcetext")
                            if isinstance(sourcetext, dict):
                                sourcetext = json.dumps(sourcetext)
                        elif typecd == "TU":
                            sourcebase = domain_row.get("tablejson") or obj.get("sourcebase")
                            sourcetext = domain_row.get("coljson") or obj.get("sourcetext")
                            if isinstance(sourcebase, dict):
                                sourcebase = json.dumps(sourcebase)
                            if isinstance(sourcetext, dict):
                                sourcetext = json.dumps(sourcetext)
                        elif typecd == "SU":
                            sourcebase = obj.get("sourcebase")
                            sourcetext = domain_row.get("sentencestext") or obj.get("sourcetext")
                        else:
                            sourcebase = domain_row.get("gptq") or obj.get("sourcebase")
                            sourcetext = domain_row.get("sourcetext") or obj.get("sourcetext")
                        read_text_template.append({
                            "gendocnm": gendoc_uid,
                            "chapteruid": chapter_uid,
                            "chapternm": obj.get("objectnm", ""),
                            "texttemplate": text_template,
                            "objectuid": go["objectuid"],
                            "objectnm": obj.get("objectnm"),
                            "type": _type_map.get(typecd, ""),
                            "objecttypecd": typecd,
                            "sourcebase": sourcebase,
                            "sourcetext": sourcetext,
                            "etc1": (domain_row.get("chart_width") if typecd == "CU" else domain_row.get("etc1")) or obj.get("etc1"),
                            "etc2": (domain_row.get("chart_height") if typecd == "CU" else domain_row.get("etc2")) or obj.get("etc2"),
                            "datauid": domain_row.get("datauid"),
                            "genobjectuid": go["genobjectuid"],
                            "useyn": obj.get("useyn"),
                        })
                else:
                    read_text_template = supabase.schema(SUPABASE_SCHEMA).rpc("fn_genchapter_detail__r", {'p_genchapteruid': gen_chapter_uid}).execute().data
                    read_text_template = [row for row in read_text_template if row['objectuid'] == sep]

                if read_text_template:
                    datas = prepare_datas_from_template(supabase, read_text_template)
                    run_yn = True

                    ui_objects, ai_objects = separate_ui_ai_objects(datas)

                    if ui_objects:

                        # UI 객체 순차 처리
                        for progress_item in process_ui_objects_sequentially(
                            request, supabase, ui_objects, datas, docid, gendoc_uid,
                            gen_chapter_uid, chapter_uid, user_id, text_template,
                            sep,
                            gendocjobuid=gendocjobuid, genchapterjobuid=genchapterjobuid,
                        ):
                            if progress_item['type'] == 'ui_complete':
                                text_template = progress_item['text_template']
                            else:
                                yield progress_item
                    
                    cleanup_thread_client()

                    if ai_objects:

                        # AI 객체 병렬 처리
                        ai_results = {}
                        for progress_item in process_ai_objects_parallel(
                            request, ai_objects, datas, docid, gendoc_uid,
                            chapter_uid, user_id, gen_chapter_uid, sep,
                            tenant_id,
                            progress_lock, completed_count, len(ui_objects),
                            gendocjobuid=gendocjobuid, genchapterjobuid=genchapterjobuid,
                        ):
                            if progress_item['type'] == 'ai_complete':
                                ai_results = progress_item['ai_results']
                            else:
                                yield progress_item

                        # AI 결과를 템플릿에 적용
                        ai_text_template = apply_ai_results_to_template(
                            supabase, ai_objects, ai_results, text_template,
                            gen_chapter_uid, user_id, sep,
                            gendocjobuid=gendocjobuid, genchapterjobuid=genchapterjobuid,
                        )

                        genchapters = {
                            'docid': docid,
                            'genchapteruid': gen_chapter_uid,
                            'chapteruid': chapter_uid,
                            'texttemplate': text_template,
                            'gentexttemplate': ai_text_template,
                            'createuserid': user_id,
                            'createfiledts': datetime.now(timezone.utc).isoformat()
                        }

                        # AI 결과가 반영된 템플릿을 반환값에도 반영 (프런트에 즉시 표시되도록)
                        text_template = ai_text_template

                    cleanup_thread_client()
                    
            elif obj == 'write':
                gen_text_template = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('gentexttemplate').eq('genchapteruid', gen_chapter_uid).execute().data
                text_template = gen_text_template[0]['gentexttemplate']

        elif make_type == 'update':
            doc_obj = _DocxDocument(io.BytesIO(resolve_template_bytes(supabase, updatafileurl)))
            html_content = convert_docx_to_html_2(doc_obj, url=False, formyn=False, ckeditor_mode=False, printyn=True)
            text_template = html_content

        elif make_type == 'all':
            # gentexttemplate 우선 사용, 없으면 업로드된 파일 사용
            gen_text_template = supabase.schema(SUPABASE_SCHEMA).table('genchapters').select('gentexttemplate').eq('genchapteruid', gen_chapter_uid).execute().data
            if gen_text_template and gen_text_template[0].get('gentexttemplate'):
                text_template = gen_text_template[0]['gentexttemplate']
            elif updatafileurl:
                doc_obj = _DocxDocument(io.BytesIO(resolve_template_bytes(supabase, updatafileurl)))
                html_content = convert_docx_to_html_2(doc_obj, url=False, formyn=False, ckeditor_mode=False, printyn=True)
                text_template = html_content
            else:
                text_template = ''

        # (재)작성 기준
        if obj == 'rewrite':
            if sep == 'Not':
                if not isinstance(genchapters, dict):
                    genchapters = {
                        'docid': docid,
                        'genchapteruid': gen_chapter_uid,
                        'chapteruid': chapter_uid,
                        'texttemplate': text_template,
                        'gentexttemplate': text_template,
                        'createuserid': user_id,
                        'createfiledts': datetime.now(timezone.utc).isoformat()
                    }
                update_genchapters(supabase, genchapters, gen_chapter_uid)

                gendoc_genchapters = {
                    'gendocuid': gendoc_uid,
                    'genchapteruid': gen_chapter_uid,
                    'creator': user_id,
                    'createdts': now
                }
                save_gendoc_genchapters(supabase, gendoc_genchapters)
        
        if doc_write == True:
            yield {
                'type': 'progress',
                'explain': '현재 챕터 생성 완료',
                'message': '현재 챕터 생성 완료',
                'texttemplate': text_template
            }
        else:
            yield {
                'type': 'complete',
                'texttemplate': text_template
            }

        return text_template

    except Exception as e:
        traceback.print_exc()
        yield {
            'type': 'error',
            'message': str(e)
        }


def call_params_ui(request, supabase, docid, gendoc_uid, data_uid, params, query):
    try:

        df = process_data(request, data_uid, None, gendoc_uid)

        raw_columns = df.columns.tolist()
        raw_rows = df.values.tolist()

        columns, dict_rows = apply_column_display_mapping(data_uid, raw_columns, raw_rows, supabase)

        return columns, dict_rows
    except Exception as e:
        raise e
    
    
def call_params_chat(request, supabase, docid, gendoc_uid, params, query, data_uid):
    try:
        df = process_data(request, data_uid, None, gendoc_uid)

        return df
    except Exception as e:
        # print(f'ErrorMessage: {e}')
        return {'success': False, 'message': str(e)}
    

def preprocess_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    def pt_to_px(match):
        pt_value = float(match.group(1))
        px_value = int(pt_value * 1.333)
        return f"font-size: {px_value}px"

    for cell in soup.find_all(["td", "th"]):
        style = cell.get("style", "")
        style = re.sub(r"font-size:\s*([\d.]+)pt", pt_to_px, style, flags=re.IGNORECASE)
        cell['style'] = style

    return str(soup)


def update_genchapters(supabase, genchapters, gen_chapter_uid):
    try:
        supabase.schema(SUPABASE_SCHEMA).table('genchapters').update(genchapters).eq('genchapteruid', gen_chapter_uid).execute()
    except Exception as e:
        # print(f'ErrorMessage(update_genchapters): {e}')
        return {'success': False, 'message': str(e)}


def save_gendoc_genchapters(supabase, gendoc_genchapters):
    try:
        supabase.schema(SUPABASE_SCHEMA).table('gendoc_genchapters').insert(gendoc_genchapters).execute().data
    except Exception as e:
        # print(f'ErrorMessage: {e}')
        return {'success': False, 'message': str(e)}
    
def update_genobjects(supabase, genobjects):
    try:
        genobjects_respon = supabase.schema(SUPABASE_SCHEMA).table('genobjects').upsert(genobjects).execute().data
    except Exception as e:
        # print(f'ErrorMessage: {e}')
        return {'success': False, 'message': str(e)}


def make_genobject(supabase, genobjectuid, gen_chapter_uid, chapter_uid, objectuid, objecttypecd, user_id, progressrate):
    with _db_semaphore:
        if progressrate == 20:
            genobject = {
                "genobjectuid": genobjectuid,
                "genchapteruid": gen_chapter_uid,
                "chapteruid": chapter_uid,
                "objectuid": objectuid,
                "objecttypecd": objecttypecd,
                "progressrate": progressrate,
                "creator": user_id,
                "createdts": datetime.now(timezone.utc).isoformat()
            }
            supabase.schema(SUPABASE_SCHEMA).table('genobjects').insert(genobject).execute()
        else:
            genobject = {
                "genobjectuid": genobjectuid,
                "progressrate": progressrate,
            }
            supabase.schema(SUPABASE_SCHEMA).table('genobjects').update(genobject).eq("genobjectuid", genobjectuid).execute()
