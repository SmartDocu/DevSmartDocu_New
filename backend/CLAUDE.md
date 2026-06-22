# backend 가이드 (FastAPI)

FastAPI 백엔드. Django 마이그레이션 완료, 현재 FastAPI 단독 운영.

---

## 폴더 구조

```
(루트)/
├── requirements.txt      # 패키지 목록 (루트에 위치)
└── backend/
    └── app/
        ├── main.py           # FastAPI 앱, CORS, 라우터 등록
        ├── config.py         # pydantic-settings 환경변수
        ├── dependencies.py   # 공통 의존성 (토큰 추출)
        ├── routers/          # 도메인별 라우터
        │   ├── auth.py       # 인증
        │   └── __init__.py
        ├── schemas/          # Pydantic 스키마
        │   ├── auth.py
        │   └── __init__.py
        └── middleware/
            └── __init__.py
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

## 날짜/시간 — Timezone 적용 규칙

DB는 UTC로 저장. 화면 표시 시 사용자 timezone을 적용해야 한다.
**포맷: `"%Y-%m-%d %H:%M"` (예: "2026-06-16 14:30") — 전 화면 통일, 변경 금지.**

### 변환 공식
```
로컬 시간 = UTC + offsetminutes분
예) offsetminutes=540(UTC+9) → UTC 14:30 → 로컬 23:30
```

### 1. offsetminutes 조회 헬퍼 — 신규 라우터에 복사해서 사용

```python
def _get_offsetminutes(sb, user_id: str) -> Optional[int]:
    try:
        tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id).maybe_single().execute()
        if not tu.data:
            return None
        tz = tu.data.get("timezone")
        if not tz and tu.data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu.data["tenantid"]).maybe_single().execute()
            if t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row.data else None
    except Exception:
        return None
```

- `tenantusers.timezone` → 없으면 `tenants.timezone` → `sdoc.timezone.offsetminutes` 조회
- timezone 미설정 사용자는 `None` 반환 → UTC 그대로 표시 (허용)

### 2. 날짜 포맷 함수 — 신규 라우터에 복사해서 사용

```python
from datetime import timedelta, timezone
from dateutil import parser as dp

def _fmt_dt(val, offsetminutes: Optional[int] = None) -> str:
    if not val:
        return ""
    try:
        dt = dp.parse(val) if isinstance(val, str) else val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""
```

### 3. 날짜 **표시** 패턴 (list 엔드포인트)

```python
@router.get("/items")
def list_items(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    offsetminutes = _get_offsetminutes(sb, str(user.id))  # 엔드포인트 상단에서 1회

    rows = sb.schema(SUPABASE_SCHEMA).table("items").select("*").execute().data or []
    for row in rows:
        row["createdts"]  = _fmt_dt(row.get("createdts"),  offsetminutes)
        row["updateddts"] = _fmt_dt(row.get("updateddts"), offsetminutes)
    return {"items": rows}
```

### 4. 날짜 **검색** 패턴 (프론트에서 로컬 날짜 문자열 "YYYY-MM-DD"로 전달)

프론트 입력값은 사용자 로컬 날짜(자정 기준) → UTC로 변환 후 DB 조회해야 정확하다.

```python
# utc = 로컬 자정(UTC 기준) - offsetminutes분
if offsetminutes is not None:
    sd_utc = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(minutes=offsetminutes)
    ed_utc = datetime.strptime(end_date,   "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1) - timedelta(minutes=offsetminutes)
    # DB 쿼리에 ISO 문자열로 전달
    rows = sb...filter("createdts", "gte", sd_utc.isoformat()).filter("createdts", "lt", ed_utc.isoformat())...
else:
    # timezone 미설정: 날짜 문자열 그대로 (UTC 기준)
    end_plus = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    rows = sb...filter("createdts", "gte", start_date).filter("createdts", "lt", end_plus)...
```

> 참고 구현: `gendocs.py` → `list_gendocs()`

### 5. 저장 시 UTC 명시

```python
from datetime import datetime, timezone

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

## 문서 전체 작성 — SQS + ECS Fargate 워커 구조

`POST /gendocs/{id}/generate` 는 SSE가 아닌 SQS 비동기 구조로 동작한다.

| 파일 | 역할 | 코드 수정 후 반영 방법 |
|------|------|----------------------|
| `backend/app/routers/gendocs.py` | 잠금 체크, SQS 전송, 상태 조회 API (`/generate/status`) | 백엔드 재시작만으로 반영 |
| `worker/main.py` | Phase 1(LLM 챕터 생성) / Phase 2(DOCX 병합) / Phase 3(Storage 업로드) 실제 처리 | Docker 재빌드 + ECR 푸시 + ECS 서비스 업데이트 필요 |

### 워커 재배포 명령어 (worker/ 코드 수정 시 필수)

```powershell
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com
docker build -f worker/Dockerfile -t smartdocu-worker .
docker tag smartdocu-worker:latest 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest
docker push 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest
```

푸시 완료 후: ECS 콘솔 → `smartdocu-cluster` → `smartdocu-worker-service` → **서비스 업데이트** → **새 배포 강제 실행** 체크 → 업데이트.

### 주의 — 중복 함수

`worker/main.py`에 `_build_context`, `_upsert_genobjects` 함수가 `gendocs.py`에서 복사된 상태로 존재한다.
`gendocs.py`의 해당 함수를 수정하면 `worker/main.py`도 동일하게 수정해야 한다.

---

## 구현 현황

| 영역 | 라우터 |
|------|--------|
| 인증 | auth |
| 마스터 데이터 | docs, chapters |
| 항목/데이터/콘텐츠 | objects, datas, tables, charts, sentences |
| 문서 생성 | gendocs (SQS 비동기 + ECS Fargate 워커) |
| 설정 | settings, configs |
| 조직 | org |
| 관리 | admin, llm |
| 공통 | menus, i18n, misc |
