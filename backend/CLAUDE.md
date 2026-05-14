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

## 날짜/시간 포맷 — `_fmt_dt` 사용 필수

DB에 저장된 timestamp(UTC)를 화면에 표시할 때는 반드시 `_fmt_dt(s, tz_name)`을 사용한다.
직접 `strftime` 또는 `datetime.now()` 포맷을 쓰지 말 것.

```python
# misc.py 내 정의 — 필요 시 공통 유틸로 이동 예정
def _fmt_dt(s, tz_name=None):
    ...  # UTC → tz_name 변환 후 "%y-%m-%d %H:%M" 포맷 반환
```

### 사용 패턴

```python
# 1. 사용자 tenantid로 timezone 조회 (list 엔드포인트 상단에서 1회)
tz_name = None
tu_row = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("tenantid").eq("useruid", user.id).execute().data
if tu_row:
    tenantid = tu_row[0].get("tenantid")
    tz_row = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tenantid).execute().data
    if tz_row:
        tz_name = tz_row[0].get("timezone")

# 2. 각 row의 timestamp 필드에 적용
row["createdts"] = _fmt_dt(row.get("createdts"), tz_name)
row["updateddts"] = _fmt_dt(row.get("updateddts"), tz_name)
```

### 저장 시 UTC 명시

```python
from datetime import datetime, timezone

# answerdts, updateddts 등 Python에서 직접 생성하는 timestamp
"answerdts": datetime.now(timezone.utc).isoformat(),
```

- `createdts`는 DB `DEFAULT now()`에 맡기므로 INSERT payload에 포함하지 않는다.
- `datetime.now()` (naive) 사용 금지 — 서버 로컬 시간이 찍혀 UTC와 불일치 발생.

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
