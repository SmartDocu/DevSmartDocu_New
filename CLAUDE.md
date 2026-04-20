# Smart Document — 프로젝트 가이드

AI 기반 문서 자동 생성 SaaS. 마스터 데이터(DB, Excel, AI)를 등록하고 LLM으로 차트·문장·테이블을 생성해 DOCX 출력.

---

## 작업 규칙

- 이미 읽은 파일은 다시 읽지 않는다.
- 사용자가 설명한 내용을 반복하지 않는다.
- requests.txt 파일 : 참조하지 않습니다.

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 백엔드 | FastAPI 0.115+ / Python 3.12 |
| 프론트엔드 | React 19 + Ant Design 5 + Vite 6 |
| 상태관리 | Zustand 5 + TanStack Query v5 |
| DB / Auth | Supabase (PostgreSQL + GoTrue JWT) — ORM 미사용 |

---

## 폴더 구조

```
(루트)/
├── backend/app/
│   ├── main.py           # FastAPI 앱, CORS, 라우터, React SPA 서빙
│   ├── config.py         # pydantic-settings 환경변수
│   ├── dependencies.py   # 공통 의존성 (get_token)
│   ├── routers/          # auth, docs, chapters, objects, datas, tables, charts,
│   │                     # sentences, gendocs, settings, org, admin, llm, misc 등
│   └── schemas/          # Pydantic 스키마
├── frontend/src/
│   ├── api/client.js     # Axios (토큰 자동 주입, 401→refresh)
│   ├── stores/authStore.js  # Zustand (accessToken, refreshToken, user)
│   ├── hooks/            # useDocs, useChapters 등
│   ├── components/       # Layout/AppLayout, 공용 컴포넌트
│   └── pages/            # master/, req/, settings/, auth/, org/, admin/
├── utilsPrj/             # 공용 유틸리티
│   ├── supabase_client.py
│   ├── process_data_*.py / chapter_making.py / chart_utils.py / crypto_helper.py
├── docs/                 # dev-guide.md, architecture.md, env-vars.md
└── _archive_claude_md/   # 이전 CLAUDE.md 보관
```

→ 상세: [docs/dev-guide.md](docs/dev-guide.md)

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

`get_thread_supabase`는 내부에서 `pg.headers["Authorization"]`를 직접 설정하여 RLS(`auth.uid()`)가 올바르게 동작한다. 라우터에서 별도 처리 불필요.

### FastAPI 인증

```python
from backend.app.dependencies import get_token

@router.get("/items")
def list_items(token: str = Depends(get_token)):
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

### LLM 선택 우선순위

프로젝트 설정 → 테넌트 설정 → 기본값(Claude Haiku).

---

## 핵심 주의사항

- **Ant Design `message`** — `App.useApp()`의 `message` 훅 사용. static `message.error()` 사용 금지.
- **React SPA 서빙** — 프로덕션: FastAPI가 `frontend/dist/` 서빙. `/api/*` → FastAPI, 나머지 → `index.html`.
- **matplotlib 멀티스레드** — 각 스레드에서 `matplotlib.use('Agg')` + `plt.close()` 필수.

---

## 코드 수정 후 검증 규칙

- 검증 실패 시 스스로 수정 후 재검증을 최대 2회 반복할 것
- 2회 후에도 실패 시 : 작업을 중단하고 오류 내용과 수정 방향을 설명한 후 사용자 확인을 받을 것
- 모든 검증 통과 후에만 작업 완료로 보고할 것

### Backend (FastAPI)

- 코드 수정 후 타입 체크, 린트, 테스트를 실행할 것

### Frontend (React)

- 코드 수정 후 타입 체크, 린트, 테스트를 실행할 것
