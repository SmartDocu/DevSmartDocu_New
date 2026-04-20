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

---

## 신규 화면 작성 프롬프트 형식

### 표준 포맷 (복사 후 대괄호 항목만 채울 것)

```
MasterDocsPage.jsx / docs.py 를 표준으로 삼아
아래 정보를 바탕으로 backend + frontend 를 모두 작성해주세요.

### 파일 및 경로
- Frontend:       frontend/src/pages/[폴더]/[PageName].jsx
- Hook:           frontend/src/hooks/use[Domain].js
- Backend:        backend/app/routers/[domain].py
- Schema:         backend/app/schemas/[domain].py
- Backend prefix: /[domain]
- Frontend route: /[path]
- 메뉴 키:        mnu.[menu_key]

### DB 테이블: [table_name]
| 컬럼명 | 타입         | 필수 | 설명 |
|--------|--------------|------|------|
| [pk]   | uuid 또는 int | Y   | PK   |
| ...    | ...          | Y/N  | ...  |

### 좌측 패널 카드 표시
{컬럼명} - {컬럼명}

### 우측 패널 폼 필드
| 필드명 | 입력 타입                        | 필수 |
|--------|----------------------------------|------|
| ...    | text / number / checkbox / select | Y/N  |

### 목록 조회 조건
(없으면 "전체 조회"로 명시 / 있으면 조건 기술)

### URL 파라미터 자동선택
(없으면 이 섹션 생략)

### 특이 유효성
(없으면 이 섹션 생략)
```

### 작성 예시 (MasterChaptersPage 기준)

```
MasterDocsPage.jsx / docs.py 를 표준으로 삼아
아래 정보를 바탕으로 backend + frontend 를 모두 작성해주세요.

### 파일 및 경로
- Frontend:       frontend/src/pages/master/MasterChaptersPage.jsx
- Hook:           frontend/src/hooks/useChapters.js
- Backend:        backend/app/routers/chapters.py
- Schema:         backend/app/schemas/chapters.py
- Backend prefix: /chapters
- Frontend route: /master/chapters
- 메뉴 키:        mnu.master_data.chapters

### DB 테이블: chapters
| 컬럼명     | 타입   | 필수 | 설명                        |
|------------|--------|------|-----------------------------|
| chapteruid | uuid   | Y    | PK (gen_random_uuid())      |
| docid      | int8   | Y    | FK → docs.docid (필터 기준) |
| chapternm  | text   |      | 챕터명                      |
| chapterno  | int4   | Y    | 순번                        |
| useyn      | bool   |      | 사용여부 (default true)     |

### 좌측 패널 카드 표시
{chapternm}

### 우측 패널 폼 필드
| 필드명    | 입력 타입 | 필수 |
|-----------|-----------|------|
| chapternm | text      |      |
| chapterno | number    | Y    |
| useyn     | checkbox  |      |

### 목록 조회 조건
docid = useAuthStore의 user.docid (Number 변환), null이면 조회 skip

### URL 파라미터 자동선택
?chapteruid=xxx 진입 시 해당 행 자동 선택 (useEffect, 최초 1회)

### 특이 유효성
- chapterno 없으면 저장 불가
- selectedDocid 없으면 저장 불가
```
