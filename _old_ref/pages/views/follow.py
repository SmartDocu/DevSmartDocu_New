import json, re, uuid, os
from datetime import datetime, timedelta
from dateutil import parser
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.process_data import process_data

def follow(request):
    # 세션 토큰
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    excel_path = 'follow/APQR_Excel.xlsx'
    pdf_path = 'follow/Follow.pdf'
    text_path = 'follow/Follow_Content.txt'

    follow_excel = supabase.storage.from_("smartdoc").get_public_url(excel_path)
    follow_pdf = supabase.storage.from_("smartdoc").get_public_url(pdf_path)
    follow_content = supabase.storage.from_("smartdoc").get_public_url(text_path)

    return render(request, 'pages/follow.html', {"follow_excel": follow_excel, "follow_pdf": follow_pdf, "follow_content": follow_content})