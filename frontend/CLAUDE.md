# frontend 가이드 (React + Vite + Ant Design)

React 19 + Vite 기반 프론트엔드. FastAPI(포트 8001)와 통신.

---

## 기술 스택

| 라이브러리 | 버전 | 용도 |
|-----------|------|------|
| React | 19.2 | UI 프레임워크 |
| React Router | v6 | 클라이언트 라우팅 |
| Ant Design | 5.x | UI 컴포넌트 |
| Zustand | 5 | 전역 상태 (인증, 언어, 탭) |
| TanStack Query | v5 | 서버 상태 / API 캐싱 |
| Axios | 1.7 | HTTP 클라이언트 |
| Vite | 6 | 번들러 |

---

## 폴더 구조

```
frontend/src/
├── main.jsx              # 진입점 (QueryClient, ConfigProvider)
├── App.jsx               # RouterProvider
├── router/index.jsx      # React Router v6 routes
├── api/client.js         # Axios (인터셉터, 토큰 자동 주입, 401→갱신)
├── stores/
│   ├── authStore.js      # Zustand (accessToken, refreshToken, user)
│   ├── langStore.js      # 언어 설정
│   └── tabStore.js       # 탭 상태
├── hooks/
│   ├── useAuth.js        # 인증 mutations (useLogin, useLogout 등)
│   ├── useDocs.js / useChapters.js / useObjects.js
│   ├── useDatas.js / useTables.js / useCharts.js / useSentences.js
│   ├── useGendocs.js / useSettings.js / useConfigs.js
│   └── useOrg.js / useAdmin.js / useMenus.js / useI18n.js
├── components/
│   ├── Auth/RequireAuth.jsx
│   ├── Layout/AppLayout.jsx / AppSidebar.jsx
│   ├── DocSelectModal/DocSelectModal.jsx
│   ├── LoginModal/LoginModal.jsx
│   ├── RegisterModal/RegisterModal.jsx
│   ├── TenantRequestModal/TenantRequestModal.jsx
│   └── llm/AiLlmPage.jsx
└── pages/
    ├── HomePage.jsx / MyInfoPage.jsx
    ├── auth/     (LoginPage, RegisterPage, PasswordResetPage)
    ├── master/   (Docs, Chapters, Objects, Datas*, Tables, Charts, Sentences, AI*, DocParams, ChapterTemplate)
    ├── req/      (DocList, DocRead, DocWrite, DocSetting, DocStatus, ChaptersRead, ChapterObjects)
    ├── settings/ (Servers, Tenants)
    ├── org/      (Projects, ProjectUsers, TenantUsers, TenantLlms)
    ├── admin/    (Helps, LlmApis, Llms, SamplePrompts, TenantRequests, UserRole)
    └── public/   (About, Contact, Faq, Follow, Qna, Service, Terms, Usage)
```

---

## 개발 명령어

```bash
cd frontend
npm install
npm run dev   # http://localhost:5174
```

---

## API 호출 패턴

```jsx
import { useQuery, useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'

const { data } = useQuery({
  queryKey: ['docs'],
  queryFn: () => apiClient.get('/docs').then(r => r.data),
})

const mutation = useMutation({
  mutationFn: (payload) => apiClient.post('/docs', payload),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['docs'] }),
})
```

- `baseURL`: `/api` (Vite 프록시 → FastAPI 8001)
- 요청: `accessToken` 자동 주입
- 응답 401: refresh → 재시도, 실패 시 `/login` 리다이렉트

---

## 신규 화면 템플릿

신규 마스터/관리 화면을 만들 때 **`frontend/src/pages/master/MasterDocsPage.jsx`** (frontend) 와 **`backend/app/routers/docs.py`** (backend) 를 표준으로 사용한다.

### 화면 구조 규칙

| 항목 | 규칙 |
|------|------|
| 레이아웃 | 2열 `flex:3` (목록) + `flex:7` (상세 폼) |
| 신규 버튼 | 좌측 패널 제목행 우측 끝, `btn btn-primary` |
| 저장·삭제 버튼 | 우측 패널 제목행 우측 끝, `btn btn-primary` / `btn btn-danger` |
| 버튼 형식 | 아이콘 없이 텍스트만 (`btn` CSS 클래스, `icon-btn` 사용 금지) |
| 다국어 | 모든 버튼·레이블·메시지·제목에 `t()` 사용 |
| 언어 리렌더 | 컴포넌트 최상단 `useLangStore((s) => s.translations)` 구독 |
| 편집 권한 | 저장·삭제는 `(isEditYn \|\| selectedItemEditYn)` 조건부 렌더 |
| 폼 레이아웃 | `form-group` 클래스 사용. 라벨은 위 줄(`display:block` — CSS에 전역 적용됨), 입력은 아래 줄 |
| description 필드 | `<textarea rows={3} style={{ resize: 'vertical' }}>` (기본 3줄, 세로 리사이즈 가능) |
| number 입력 | `<input type="number">` |

### 다국어 키 네이밍 규칙

| 종류 | 접두사 | 예시 |
|------|--------|------|
| 버튼 | `btn.` | `btn.new`, `btn.save`, `btn.delete` |
| 레이블 | `lbl.` | `lbl.projectnm`, `lbl.upload` |
| 테이블 헤더 | `thd.` | `thd.paramnm`, `thd.orderno` |
| 제목 | `ttl.` | `ttl.doc.list`, `ttl.doc.detail` |
| 안내 텍스트 | `inf.` | `inf.samplevalue` |
| 메시지/알림 | `msg.` | `msg.doc.required`, `msg.confirm.delete` |
| 메뉴 | `mnu.` | `mnu.master_data.docs.base` |
| 코드값 | `cod.` | `cod.useyn.y` |

### ui_terms 등록 방법

화면 작성 완료 후 사용된 `t('키')` 목록을 추출해 Supabase에 등록한다.

| 테이블 | 등록 내용 |
|--------|-----------|
| `ui_terms` | `term_key`, `default_text` (영문 기본값) |
| `ui_term_translations` | `term_key`, `language_cd`, `translated_text` |
