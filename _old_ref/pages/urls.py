from django.urls import path
from django.shortcuts import render
from .views import (home, hide_popup, search_help
                  , login_view, logout_view, send_reset_email
                  , register, get_tenants
                  , terms_conditions
                  , docs, docs_save
                  , master_help, master_help_save, master_help_delete

                  , master_docs, master_docs_save, master_docs_delete, master_params_save, master_params_delete, master_params_datasets, master_params_dataset_cols
                  , master_doc_params, master_doc_params_save, master_doc_params_delete
                  , master_datas_db, master_datas_db_save, master_datas_db_delete, master_datacols_create, master_datacols_save, master_datacols
                  , master_datas_ex, master_datas_ex_save, master_datas_ex_delete
                  , master_datas_ai, master_datas_ai_save, master_datas_ai_delete
                  , master_chapters, master_chapters_save, master_chapters_delete
                  # Vue
                  , master_chapter_template, save_chapter_objects

                  , master_object, master_object_get_chapter, master_object_save_object, master_object_delete_object
                  
                  , master_tables, master_tables_save, master_tables_delete
                  , master_charts, master_charts_save, master_charts_delete, master_chart_preview_png
                  , master_sentences, master_sentences_save, master_sentences_delete

                  , req_doc_check_params, req_doc_save_params, req_doc_check_objects, req_doc_update_params, req_doc_close, req_doc_open, req_doc_delete
                  , req_doc_list, gendoc_file_upload
                  , req_doc_write, doc_write
                  , req_doc_status
                  , req_chapters_read, chapter_rewrite, chapter_read, genchapter_file_upload, chapter_detail_read, doc_rewrite
                  , req_chapter_objects_read, object_rewrite, object_chapter_rewrite
                  , download_inmemory_docx

                  , master_servers, master_servers_save, master_servers_delete
                  , master_llms, master_llms_save, master_llms_delete
                  , master_llmapis, master_llmapis_save, master_llmapis_delete

                  , master_tenants, master_tenants_save, master_tenants_delete
                  , master_tenant_users, master_tenant_users_save, master_tenant_users_delete
                  , master_tenant_llms, master_tenant_llms_save, master_tenant_llms_delete

                  , master_tenant_request, master_tenant_request_save
                  , master_tenant_request_list, master_tenant_request_list_save

                  , master_projects, master_projects_save, master_projects_delete
                  , master_project_users, master_project_users_save, master_project_users_delete

                  #### verification
                  , send_verification_sms, verify_sms_code, check_verification_status, process_sms_verification

                  , master_user_role, master_user_role_save

                  , debug_env    # jeff

                  , about_view
                  , service_view
                  , usage_view
                  , qna_view, qna_save, qna_delete, qna_answer_save, qna_answer_delete
                  , faq_view, faq_save, faq_delete
                  , register_qna, register_qna_submit

                  , myinfo, myinfo_update_username, myinfo_update_contact
                  , password_reset

                  , follow

                    )
# 팝업화면용 : 오래된건 지워도 됨
from .views.popup.popup_test import popup_test  # 20251208
                    
# urls.py
urlpatterns = [
    path('', home, name='home'), 
    #팝업노출
    path("hide_popup/", hide_popup, name="hide_popup"),
    #헬프노출
    path("search_help/", search_help, name = "search_help"),

    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path("send-reset-email/", send_reset_email, name="send_reset_email"),
    
    path("register/", register, name="register"),
    path("get_tenants/", get_tenants, name = 'get_tenants'),
    path("terms_conditions/", terms_conditions, name = "terms_conditions"),

    path("docs/", docs, name = 'docs'),
    path("docs_save/", docs_save, name='docs_save'),

    path("master/help/", master_help, name = 'master_help'),
    path("master/help_save/", master_help_save, name = 'master_help_save'),
    path("master/help_delete/", master_help_delete, name = 'master_help_delete'),

    path('master/docs/', master_docs, name = "master_docs"),
    path('master/docs_save/', master_docs_save, name = 'master_docs_save'),
    path('master/docs_delete/', master_docs_delete, name = 'master_docs_delete'),
    path('master/params_save/', master_params_save, name = 'master_params_save'),
    path('master/params_delete/', master_params_delete, name = 'master_params_delete'),
    path('master/params_datasets/', master_params_datasets, name = 'master_params_datasets'),
    path('master/params_dataset_cols/', master_params_dataset_cols, name = 'master_params_dataset_cols'),

    path('master/doc_params/', master_doc_params, name = "master_doc_params"),
    path('master/doc_params_save/', master_doc_params_save, name = "master_doc_params_save"),
    path('master/doc_params_delete/', master_doc_params_delete, name = "master_doc_params_delete"),


    path('master/datas_db/', master_datas_db, name = 'master_datas_db'),
    path('master/datas_db_save/', master_datas_db_save, name = "master_datas_db_save"),
    path('master/datas_db_delete/', master_datas_db_delete, name = "master_datas_db_delete"),
    path('master/datacols_create/', master_datacols_create, name = "master_datacols_create"),
    path('master/datacols_save/', master_datacols_save, name = "master_datacols_save"),
    path('master/datacols/', master_datacols, name = "master_datacols"),

    path('master/datas_ex/', master_datas_ex, name = 'master_datas_ex'),
    path('master/datas_ex_save/', master_datas_ex_save, name = "master_datas_ex_save"),
    path('master/datas_ex_delete/', master_datas_ex_delete, name = "master_datas_ex_delete"),

    path('master/datas_ai/', master_datas_ai, name = 'master_datas_ai'),
    path('master/datas_ai_save/', master_datas_ai_save, name = "master_datas_ai_save"),
    path('master/datas_ai_delete/', master_datas_ai_delete, name = "master_datas_ai_delete"),

    path('master/chapters/', master_chapters, name = 'master_chapters'),
    path('master/chapters_save/', master_chapters_save, name = 'master_chapters_save'),
    path('master/chapters_delete/', master_chapters_delete, name = 'master_chapters_delete'),
    # Vue
    path('master/chapter_template/', master_chapter_template, name = 'master_chapter_template'),
    path('api/save_chapter_objects/', save_chapter_objects, name = 'save_chapter_objects'),

    path('master/object/', master_object, name = 'master_object'),
    path('master/object_get_chapter/', master_object_get_chapter, name = 'master_object_get_chapter'),
    path('master/object_save_object/', master_object_save_object, name = 'master_object_save_object'),
    path('master/object_delete_object/', master_object_delete_object, name = 'master_object_delete_object'),

    path('master/tables/', master_tables, name = 'master_tables'),
    path('master/tables_save/', master_tables_save, name = 'master_tables_save'),
    path('master/tables_delete/', master_tables_delete, name = 'master_tables_delete'),

    path('master/charts/', master_charts, name = 'master_charts'),
    path('master/charts_save/', master_charts_save, name = 'master_charts_save'),
    path('master/charts_delete/', master_charts_delete, name = 'master_charts_delete'),
    path('master/chart_preview_png/', master_chart_preview_png, name = 'master_chart_preview_png'),

    path('master/sentences/', master_sentences, name = 'master_sentences'),
    path('master/sentences_save/', master_sentences_save, name = 'master_sentences_save'),
    path('master/sentences_delete/', master_sentences_delete, name = 'master_sentences_delete'),
    
    path('req/req_doc_check_params/', req_doc_check_params, name = 'req_doc_check_params'),
    path('req/req_doc_save_params/', req_doc_save_params, name = 'req_doc_save_params'),
    path('req/req_doc_check_objects/', req_doc_check_objects, name = 'req_doc_check_objects'),
    path('req/req_doc_update_params/', req_doc_update_params, name = 'req_doc_update_params'),
    path('req/req_doc_close/', req_doc_close, name = 'req_doc_close'),
    path('req/req_doc_open/', req_doc_open, name = 'req_doc_open'),
    path('req/req_doc_delete/', req_doc_delete, name = 'req_doc_delete'),
    
    path('req/req_doc_status/', req_doc_status, name = 'req_doc_status'),

    path('req/req_doc_list/', req_doc_list, name = 'req_doc_list'),
    path('req/gendoc_file_upload/', gendoc_file_upload, name = 'gendoc_file_upload'),

    path('req/req_doc_write/', req_doc_write, name = 'req_doc_write'),
    path('req/doc_write/', doc_write, name = 'doc_write'),

    path('req/req_chapters_read/', req_chapters_read, name = 'req_chapters_read'),
    path('req/chapter_read/', chapter_read, name = 'chapter_read'),
    path('req/download_inmemory_docx/', download_inmemory_docx, name = 'download_inmemory_docx'),
    path('req/genchapter_file_upload/', genchapter_file_upload, name = 'genchapter_file_upload'),
    path('req/chapter_detail_read/', chapter_detail_read, name = 'chapter_detail_read'),
    path('req/chapter_rewrite/', chapter_rewrite, name = 'chapter_rewrite'),
    path('req/doc_rewrite/', doc_rewrite, name = 'doc_rewrite'),

    path('req/chapter_objects_read/', req_chapter_objects_read, name = 'req_chapter_objects_read'),
    path('req/object_rewrite/', object_rewrite, name = 'object_rewrite'),
    path('req/object_chapter_rewrite/', object_chapter_rewrite, name = 'object_chapter_rewrite'),

    path('master/servers/', master_servers, name = 'master_servers'),
    path('master/servers_save/', master_servers_save, name = 'master_servers_save'),
    path('master/servers_delete/', master_servers_delete, name = 'master_servers_delete'),

    path('master/llms/', master_llms, name = 'master_llms'),
    path('master/llms_save/', master_llms_save, name = 'master_llms_save'),
    path('master/llms_delete/', master_llms_delete, name = 'master_llms_delete'),
    path('master/llmapis/', master_llmapis, name = 'master_llmapis'),
    path('master/llmapis_save/', master_llmapis_save, name = 'master_llmapis_save'),
    path('master/llmapis_delete/', master_llmapis_delete, name = 'master_llmapis_delete'),

    path('master/tenants/', master_tenants, name = 'master_tenants'),
    path('master/tenants_save/', master_tenants_save, name = 'master_tenants_save'),
    path('master/tenants_delete/', master_tenants_delete, name = 'master_tenants_delete'),

    path('master/tenant_users/', master_tenant_users, name = 'master_tenant_users'),
    path('master/tenant_users_save/', master_tenant_users_save, name = 'master_tenant_users_save'),
    path('master/tenant_users_delete/', master_tenant_users_delete, name = 'master_tenant_users_delete'),

    path('master/tenant_llms/', master_tenant_llms, name = 'master_tenant_llms'),
    path('master/tenant_llms_save/', master_tenant_llms_save, name = 'master_tenant_llms_save'),
    path('master/tenant_llms_delete/', master_tenant_llms_delete, name = 'master_tenant_llms_delete'),

    path('master/tenant_request/', master_tenant_request, name = 'master_tenant_request'),
    path('master/tenant_request_save/', master_tenant_request_save, name = 'master_tenant_request_save'),

    path('master/tenant_request_list/', master_tenant_request_list, name = 'master_tenant_request_list'),
    path('master/tenant_request_list_save/', master_tenant_request_list_save, name = 'master_tenant_request_list_save'),

    path('master/projects/', master_projects, name = 'master_projects'),
    path('master/projects_save/', master_projects_save, name = 'master_projects_save'),
    path('master/projects_delete/', master_projects_delete, name = 'master_projects_delete'),
    path('master/project_users/', master_project_users, name = 'master_project_users'),
    path('master_project_users_save/', master_project_users_save, name = 'master_project_users_save'),
    path('master_project_users_delete/', master_project_users_delete, name = 'master_project_users_delete'),

    #### verificatoin
    path("api/send_verification_sms/", send_verification_sms, name = "send_verification_sms"),
    path("api/verify_sms_code/", verify_sms_code, name = "verify_sms_code"),
    path("api/check_verification_status/", check_verification_status, name="check_verification_status"),
    path("api/process_sms_verification/", process_sms_verification, name="process_sms_verification"),


    path('master/user_role/', master_user_role, name = 'master_user_role'),
    path('master/user_role_save/', master_user_role_save, name = 'master_user_role'),

    path('debug/env/', debug_env, name='debug_env'),    # jeff 20251119 1522

    path('about_view/', about_view, name = 'about_view'),
    path('service_view/', service_view, name = 'service_view'),
    path('usage/', usage_view, name = 'usage_view'),
    path('qna_view/', qna_view, name = 'qna_view'),
    path('qna_save/', qna_save, name = 'qna_save'),
    path('qna_delete/', qna_delete, name = 'qna_delete'),
    path('qna_answer_save/', qna_answer_save, name = 'qna_answer_save'),
    path('qna_answer_delete/', qna_answer_delete, name = 'qna_answer_delete'),
    path('faq_view/', faq_view, name = 'faq_view'),
    path('faq_save/', faq_save, name = 'faq_save'),
    path('faq_delete/', faq_delete, name = 'faq_delete'),
    path('register_qna/', register_qna, name='register_qna'),
    path('register_qna/submit/', register_qna_submit, name='register_qna_submit'),

    path('myinfo/', myinfo, name='myinfo'),
    path('myinfo_update_username/', myinfo_update_username, name='myinfo_update_username'),
    path('myinfo_update_contact/', myinfo_update_contact, name = 'myinfo_update_contact'),
    path("password-reset/", password_reset, name="password_reset"),

    #따라하기
    path('follow/', follow, name = 'follow'),

    #팝업화면
    path('popups/popup_test/', popup_test, name='popup_test'),
]