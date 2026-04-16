# backend 가이드 (FastAPI)

Django를 대체하는 FastAPI 백엔드. Strangler Fig 패턴으로 Django와 병존.

---

## 폴더 구조

```
backend/
├── app/
│   ├── main.py           # FastAPI 앱, CORS, 라우터 등록
│   ├── config.py         # pydantic-settings 환경변수
│   ├── dependencies.py   # 공통 의존성 (토큰 추출)
│   ├── routers/          # 도메인별 라우터
│   │   ├── auth.py       # 인증 (Stage 2 ✅)
│   │   └── __init__.py
│   ├── schemas/          # Pydantic 스키마
│   │   ├── auth.py
│   │   └── __init__.py
│   └── middleware/
│       └── __init__.py
└── requirements.txt
```

---

## 실행 방법

**반드시 프로젝트 루트에서 실행** (utilsPrj/ 임포트 경로 필요).

```bash
uvicorn backend.app.main:app --reload --port 8001
# http://localhost:8001/api/docs  ← Swagger UI
```

---

## utilsPrj 공유

```python
from utilsPrj.supabase_client import get_thread_supabase, get_service_client
from utilsPrj.crypto_helper import encrypt_value, decrypt_value
```

---

## 라우터 추가 패턴

```python
# backend/app/routers/new_domain.py
from fastapi import APIRouter, Depends
from backend.app.dependencies import get_token

router = APIRouter()

@router.get("/items")
def list_items(token: str = Depends(get_token)):
    ...
```

`backend/app/routers/__init__.py`에 등록:
```python
from backend.app.routers import new_domain
router.include_router(new_domain.router, prefix="/new-domain", tags=["new-domain"])
```

---

## 마이그레이션 현황

| Stage | 상태 | 내용 |
|-------|------|------|
| 1 | ✅ | 프로젝트 골격 |
| 2 | ✅ | 인증 (login/logout/register/SMS/refresh) |
| 3 | ✅ | 마스터 데이터 API (docs, chapters) |
| 4 | ✅ | 항목/데이터/콘텐츠 API (objects, datas, tables, charts, sentences) |
| 5 | ✅ | 문서 생성 파이프라인 (gendocs, SSE 스트리밍, DOCX 업로드) |
| 6 | ✅ | 설정 API (서버/프로젝트/테넌트/내정보) |
| 7 | 예정 | Django 제거 |
