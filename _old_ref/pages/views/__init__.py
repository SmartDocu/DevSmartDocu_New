from .home import home, hide_popup, search_help
from .login import login_view, logout_view, send_reset_email

from .register import register, get_tenants
from .terms_conditions import terms_conditions

from .docs import docs, docs_save

from .master_help import master_help, master_help_save, master_help_delete

from .master_docs import master_docs, master_docs_save, master_docs_delete, master_params_save, master_params_delete, master_params_datasets, master_params_dataset_cols
from .master_doc_params import master_doc_params, master_doc_params_save, master_doc_params_delete
from .master_chapters import master_chapters, master_chapters_save, master_chapters_delete
from .master_chapter_template import master_chapter_template, save_chapter_objects
from .master_datas_db import master_datas_db, master_datas_db_save, master_datas_db_delete, master_datacols_create, master_datacols_save, master_datacols
from .master_datas_ex import master_datas_ex, master_datas_ex_save, master_datas_ex_delete
from .master_datas_ai import master_datas_ai, master_datas_ai_save, master_datas_ai_delete

from .master_object import master_object, master_object_get_chapter, master_object_save_object, master_object_delete_object
from .master_tables import master_tables, master_tables_save, master_tables_delete
from .master_charts import master_charts, master_charts_save, master_charts_delete, master_chart_preview_png
from .master_sentences import master_sentences, master_sentences_save, master_sentences_delete

from .req_doc_setting import req_doc_check_params, req_doc_save_params, req_doc_check_objects, req_doc_update_params, req_doc_close, req_doc_open, req_doc_delete
from .req_doc_list import req_doc_list, gendoc_file_upload
from .req_doc_write import req_doc_write, doc_write
from .req_doc_status import req_doc_status
from .req_chapters_read import req_chapters_read, chapter_rewrite, genchapter_file_upload, chapter_detail_read, doc_rewrite
from .req_chapter_objects_read import req_chapter_objects_read, object_rewrite, object_chapter_rewrite

from .req_chapter_read import chapter_read, download_inmemory_docx

from .master_servers import master_servers, master_servers_save, master_servers_delete
from .master_llms import master_llms, master_llms_save, master_llms_delete
from .master_llmapis import master_llmapis, master_llmapis_save, master_llmapis_delete

from .master_tenants import master_tenants, master_tenants_save, master_tenants_delete
from .master_tenant_users import master_tenant_users, master_tenant_users_save, master_tenant_users_delete
from .master_tenant_llms import master_tenant_llms, master_tenant_llms_save, master_tenant_llms_delete
from .master_tenant_request import master_tenant_request, master_tenant_request_save
from .master_tenant_request_list import master_tenant_request_list, master_tenant_request_list_save

from .master_project import master_projects, master_projects_save, master_projects_delete
from .master_project_users import master_project_users, master_project_users_save, master_project_users_delete

from .verification import send_verification_sms, verify_sms_code, check_verification_status, process_sms_verification

from .master_user_role import master_user_role, master_user_role_save

from .views import debug_env    # jeff 20251119 1522

from .about import about_view
from .service import service_view
from .usage import usage_view
from .qna import qna_view, qna_save, qna_delete, qna_answer_save, qna_answer_delete
from .faq import faq_view, faq_save, faq_delete
from .register_qna import register_qna, register_qna_submit

from .myinfo import myinfo, myinfo_update_username, myinfo_update_contact
from .password_reset import password_reset

from .follow import follow

__all__ = [
     "home"
   , "hide_popup"
   , "search_help"

   , "login_view"
   , "logout_view"
   , "send_reset_email"

   , "register"
   , "get_tenants"
   , "terms_conditions"

   , "docs"
   , "docs_save"

   , "master_help"
   , "master_help_save"
   , "master_help_delete"

   , "master_docs"
   , "master_docs_save"
   , "master_docs_delete"
   , "master_params_save"
   , "master_params_delete"
   , "master_params_datasets"
   , "master_params_dataset_cols"

   , "master_doc_params"
   , "master_doc_params_save"
   , "master_doc_params_delete"

   , "master_chapters"
   , "master_chapters_save"
   , "master_chapters_delete"
  #  Vue
   , "master_chapter_template"
   , "save_chapter_objects"

   , "master_datas_db"
   , "master_datas_db_save"
   , "master_datas_db_delete"
   , "master_datacols_create"
   , "master_datacols_save"
   , "master_datacols"

   , "master_datas_ex"
   , "master_datas_ex_save"
   , "master_datas_ex_delete"

   , "master_datas_ai"
   , "master_datas_ai_save"
   , "master_datas_ai_delete"

   , "master_object"
   , "master_object_get_chapter"
   , "master_object_save_object"
   , "master_object_delete_object"

   , "master_tables"
   , "master_tables_save"
   , "master_tables_delete"

   , "master_charts"
   , "master_charts_save"
   , "master_charts_delete"
   , "master_chart_preview_png"

   , "master_sentences"
   , "master_sentences_save"
   , "master_sentences_delete"

   , "req_doc_check_params"
   , "req_doc_check_objects"
   , "req_doc_save_params"
   , "req_doc_update_params"
   , "req_doc_close"
   , "req_doc_open"
   , "req_doc_delete"
   
   , "req_doc_list"
   , "gendoc_file_upload"

   , "req_doc_write"
   , "doc_write"

   , "req_doc_status"

   , "req_chapters_read"
   , "req_chapter_objects_read"
   , "object_rewrite"
   , "object_chapter_rewrite"
   , "chapter_rewrite"
   , "doc_rewrite"

   , "chapter_read"
   , "download_inmemory_docx"
   
   , "genchapter_file_upload"
   , "chapter_detail_read"

   , "master_servers"
   , "master_servers_save"
   , "master_servers_delete"

   , "master_llms"
   , "master_llms_save"
   , "master_llms_delete"
   , "master_llmapis"
   , "master_llmapis_save"
   , "master_llmapis_delete"

   , "master_tenants"
   , "master_tenants_save"
   , "master_tenants_delete"
   , "master_tenant_users"
   , "master_tenant_users_save"
   , "master_tenant_users_delete"
   
   , "master_tenant_request"
   , "master_tenant_request_save"

   , "master_tenant_request_list"
   , "master_tenant_request_list_save"

   , "master_projects"
   , "master_projects_save"
   , "master_projects_delete"
   , "master_project_users"
   , "master_project_users_save"
   , "master_project_users_delete"

  #### verification
  , "send_verification_sms"
  , "verify_sms_code"
  , "check_verification_status"
  , "process_sms_verification"

  , "master_user_role"
  , "master_user_role_save"

  , "about_view"
  , "service_view"
  , "usage_view"
  , "qna_view"
  , "qna_save"
  , "qna_delete"
  , "qna_answer_save"
  , "qna_answer_delete"
  , "faq_view"
  , "faq_save"
  , "faq_delete"
  , "register_qna"
  , "register_qna_submit"
  
  , "myinfo"
  , "myinfo_update_username"
  , "myinfo_update_contact"
  , "password_reset"

  , "follow"
]