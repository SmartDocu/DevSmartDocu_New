from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='llm_index'),
    path('ai_charts/', views.ai_charts, name='ai_charts'),
    path('ai_sentences/', views.ai_sentences, name='ai_sentences'),
    path('ai_tables/', views.ai_tables, name='ai_tables'),
    path('ai_charts_save/', views.ai_charts_save, name='ai_charts_save'),
    path('ai_sentences_save/', views.ai_sentences_save, name='ai_sentences_save'),
    path('ai_tables_save/', views.ai_tables_save, name='ai_tables_save'),
    path('ai_charts_delete/', views.ai_charts_delete, name='ai_charts_delete'),
    path('ai_sentences_delete/', views.ai_sentences_delete, name='ai_sentences_delete'),
    path('ai_tables_delete/', views.ai_tables_delete, name='ai_tables_delete'),
    path('ai_intergrate/', views.ai_intergrate, name='ai_intergrate'),
    path('ai_llm_preview/', views.ai_llm_preview, name='ai_llm_preview'),
    path('ai_get_columns/', views.ai_get_columns, name='ai_get_columns'),    # 20250901 추가
    path('ai_prompt_sample_save/', views.ai_prompt_sample_save, name='ai_prompt_sample_save'),
    path('ai_sample_prompt_manage/', views.ai_sample_prompt_manage, name='ai_sample_prompt_manage'),
    path('get_prompts/', views.get_prompts, name='get_prompts'),
    path('ai_prompt_llm_preview/', views.ai_prompt_llm_preview, name='ai_prompt_llm_preview'),
    path('ai_prompt_sample_delete/', views.ai_prompt_sample_delete, name='ai_prompt_sample_delete'),
    path("experience/", views.ai_experience, name="ai_experience"),
    path('ai_experience_llm_preview', views.ai_experience_llm_preview, name="ai_experience_llm_preview"),
]
