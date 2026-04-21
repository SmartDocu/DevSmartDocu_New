# backend 가이드 (FastAPI)

FastAPI 백엔드. Django 마이그레이션 완료, 현재 FastAPI 단독 운영.

---

## 폴더 구조

```
backend/
├── app/
│   ├── main.py           # FastAPI 앱, CORS, 라우터 등록
│   ├── config.py         # pydantic-settings 환경변수
│   ├── dependencies.py   # 공통 의존성 (토큰 추출)
│   ├── routers/          # 도메인별 라우터
│   │   ├── auth.py       # 인증
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

## 표준 CRUD 규칙 (신규 라우터 작성 시 기본 적용)

파일 업로드 없는 일반 CRUD 라우터는 `docs.py` 패턴을 표준으로 따른다.

### INSERT / UPDATE / DELETE 컬럼 규칙
- **INSERT**: 테이블의 모든 컬럼 (`createdts` 제외 — DB default)
- **UPDATE**: 테이블의 모든 컬럼 (`createdts`, `creator` 제외)
- **DELETE**: PK 컬럼 기준 단건 삭제

### 인증 / Supabase 패턴
```python
def _sb(token: str):
    return get_thread_supabase(access_token=token)

def _get_user(token: str):
    sb = _sb(token)
    resp = sb.auth.get_user(token)
    if not resp or not resp.user:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return resp.user
```
- 모든 엔드포인트: `token: str = Depends(get_token)`
- RLS는 `_sb(token)`이 자동 처리 — 라우터에서 별도 처리 불필요

### 신규 라우터 등록
`backend/app/routers/__init__.py` 에 반드시 추가:
```python
from backend.app.routers import [domain]
router.include_router([domain].router, prefix="/[domain]", tags=["[domain]"])
```

---

## 공통 유틸리티 엔드포인트

신규 화면 작성 시 아래 엔드포인트를 재사용할 것. 별도 라우터 추가 불필요.

### `GET /api/codes?codegroupcd={codegroupcd}`
`codes` 테이블에서 특정 코드그룹의 목록을 반환. selectbox 옵션 로딩에 사용.
라우터: `backend/app/routers/codes.py`

- **반환**: `{ codes: [{ codevalue, term_key, default_name }] }`
- **term_key 형식**: `cod.{codegroupcd}_{codevalue}` — `t(term_key)`로 다국어 표시
- **저장 값**: `codevalue`만 DB에 저장
- **프론트 훅**: `useMenuCodes(codegroupcd)` in `frontend/src/hooks/useMenus.js`

```jsx
const { data: roleCodes = [] } = useMenuCodes('menu_rolecd')
// <option value={code.codevalue}>{t(code.term_key) || code.default_name}</option>
```

---

## 구현 현황

| 영역 | 라우터 |
|------|--------|
| 인증 | auth |
| 마스터 데이터 | docs, chapters |
| 항목/데이터/콘텐츠 | objects, datas, tables, charts, sentences |
| 문서 생성 | gendocs (SSE 스트리밍, DOCX 업로드) |
| 설정 | settings, configs |
| 조직 | org |
| 관리 | admin, llm |
| 공통 | menus, i18n, misc |
