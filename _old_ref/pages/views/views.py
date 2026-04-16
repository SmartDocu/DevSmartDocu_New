# jeff 20251119 1522 작성

from django.http import JsonResponse
import os

def debug_env(request):
    return JsonResponse({
        'supabase_url': os.environ.get('SUPABASE_URL'),
        'supabase_key_exists': bool(os.environ.get('SUPABASE_KEY')),
    })