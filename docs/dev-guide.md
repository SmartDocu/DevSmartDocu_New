# 개발 가이드 (상세)

## 폴더 구조

```
dev_smart_document/
├── backend/app/
│   ├── main.py           # FastAPI 앱, CORS, 라우터, React SPA 서빙
│   ├── config.py         # pydantic-settings 환경변수
│   ├── dependencies.py   # 공통 의존성 (get_token)
│   ├── routers/          # auth, docs, chapters, objects, datas, tables, charts, sentences, gendocs, settings, org, admin, llm
│   └── schemas/          # Pydantic 스키마
├── frontend/src/
│   ├── main.jsx / App.jsx / router/
│   ├── api/client.js     # Axios (토큰 자동 주입, 401→refresh)
│   ├── stores/authStore.js  # Zustand (accessToken, refreshToken, user)
│   ├── hooks/            # useDocs, useChapters 등
│   ├── components/       # Layout/AppLayout, DocSelectModal 등
│   └── pages/            # master/, req/, settings/, auth/, org/, admin/
├── utilsPrj/             # 공용 유틸리티
│   ├── supabase_client.py
│   ├── process_data_*.py / chapter_making.py / chart_utils.py / crypto_helper.py
└── _old_ref/             # Django 참조용 (수정 금지)
```

---

## 로컬 실행

```bash
# 백엔드 (프로젝트 루트에서)
uvicorn backend.app.main:app --reload --port 8001

# 프론트엔드
cd frontend && npm run dev   # http://localhost:5174

# 프로덕션 빌드
cd frontend && npm run build
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

---

## 핵심 패턴

### Supabase 클라이언트 — 라우터에서 반드시 이 방식 사용

```python
def _sb(token: str):
    from utilsPrj.supabase_client import get_thread_supabase
    return get_thread_supabase(access_token=token)
```

`get_thread_supabase`는 내부에서 `pg.headers["Authorization"] = f"Bearer {token}"` 을 설정하여 Supabase RLS(`auth.uid()`)가 올바르게 동작한다.  
**refresh_token 없이도 RLS 동작** — `pg.headers`를 직접 수정하는 방식(세션 교체 후 auth 헤더 덮어쓰기).

### FastAPI 인증

```python
from backend.app.dependencies import get_token

@router.get("/items")
def list_items(token: str = Depends(get_token)):
    user = _get_user(token)   # sb.auth.get_user(token)으로 user_id 추출
    sb = _sb(token)
```

### React API 호출

```jsx
import apiClient from '@/api/client'
const { data } = useQuery({
  queryKey: ['docs'],
  queryFn: () => apiClient.get('/docs').then(r => r.data),
})
```

### authStore 사용자 컨텍스트 업데이트

```js
const { updateUser } = useAuthStore()
updateUser({ docid, docnm, projectid, tenantid, tenantmanager, projectmanager, editbuttonyn, sampledocyn })
```

### matplotlib 멀티스레드

각 스레드에서 `matplotlib.use('Agg')` + `plt.close()` 필수.

### LLM 선택 우선순위

프로젝트 설정 → 테넌트 설정 → 기본값(Claude Haiku).

---

## 아키텍처 흐름

```
브라우저 (React + Ant Design)
    ↓ /api/* (Vite 프록시 → 8001)
FastAPI routers/
    ↓
utilsPrj/ (Supabase, DOCX, Chart, Crypto)
    ↓
외부: Supabase / LLM APIs / Naver SMS / Gmail
```
