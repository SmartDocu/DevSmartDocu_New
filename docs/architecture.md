# 아키텍처 개요

## 신규 스택 (FastAPI + React)

```
브라우저 (React + Ant Design)
        ↓  /api/* (Vite 프록시 → 8001)
FastAPI 라우터
  └── backend/app/routers/
        ↓
utilsPrj/ (공유 유틸리티)
  ├── supabase_client.py   — Supabase REST API
  ├── process_data_*.py    — DB/Excel/AI 데이터 처리
  ├── chapter_making.py    — DOCX 생성
  └── crypto_helper.py     — Fernet 암호화
        ↓
외부 서비스
  ├── Supabase (PostgreSQL + Auth)
  ├── LLM APIs (Claude / GPT / Google)
  ├── Naver Cloud SMS
  └── Gmail SMTP
```

## 기존 스택 (Django + Vue, 단계적 제거)

```
브라우저 (Django 템플릿 + Vue 3)
        ↓
Django URL Router
  ├── pages/urls.py  (246 경로)
  └── llm/urls.py    (26 경로)
        ↓
pages/views/ (46 파일) + llm/views.py
```

## 포트 구분

| 서비스 | 포트 |
|--------|------|
| Django (기존) | 8000 |
| FastAPI (신규) | 8001 |
| React dev | 5174 |
| Vue dev (기존) | 5173 |

## LLM 선택 우선순위

`llm/ai_chain.py`의 `get_llm_model()`:
1. 프로젝트 설정
2. 테넌트 설정
3. 기본값 (Claude Haiku)
