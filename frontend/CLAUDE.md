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
| 다국어 | 모든 버튼·레이블·메시지·제목에 `t()` 사용. **`t()` 뒤에 `\|\| '한글기본값'` 절대 추가 금지** — 키 미등록 시 키 문자열이 그대로 노출되는 것이 의도된 동작 |
| 언어 리렌더 | 컴포넌트 최상단 `useLangStore((s) => s.translations)` 구독 |
| 편집 권한 | 저장·삭제는 `isEditYn` 조건부 렌더. **반드시 `user?.editbuttonyn === 'Y'`** 로 판단 — `editbuttonyn`은 항상 문자열 `"Y"` 또는 `"N"`이므로 `!!` truthy 체크 사용 금지 (`"N"`도 truthy) |
| 폼 레이아웃 | `form-group` 클래스 사용. 라벨은 위 줄(`display:block` — CSS에 전역 적용됨), 입력은 아래 줄 |
| 필수 필드 표시 | 라벨 앞에 `<span style={{ color: 'red', marginRight: 2 }}>*</span>` 삽입 |
| description 필드 | `<textarea rows={3} style={{ resize: 'vertical' }}>` (기본 3줄, 세로 리사이즈 가능) |
| number 입력 | `<input type="number">` |
| 소제목 행 | 버튼 유무와 무관하게 높이 통일 — 항상 아래 구조 사용. 버튼 없는 경우 `<div />` placeholder 삽입 |
| 패널 스크롤 | 좌·우측 패널 모두 `overflowY: 'auto'`, `maxHeight: 'calc(100vh - 224px)'` 적용해 브라우저 스크롤 방지 |

#### 소제목 행 표준 패턴

버튼이 **있는** 경우:
```jsx
<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
  <h3 style={{ margin: 0 }}>{t('ttl.xxx')}</h3>
  <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
</div>
```

버튼이 **없는** 경우:
```jsx
<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
  <h3 style={{ margin: 0 }}>{t('ttl.xxx')}</h3>
  <div />
</div>
```

#### 2열 패널 스크롤 표준 패턴

```jsx
{/* 좌측 패널 */}
<div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
  ...
</div>

{/* 우측 패널 */}
<div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
  ...
</div>
```

> **224px 산출 근거**: Header(60) + Content marginTop(104) + inner padding-top(12) + page-title 높이(40) + page-title margin-bottom(20) + 하단 padding(48)

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

### 앱 내 탭으로 페이지 이동 패턴

다른 페이지로 이동할 때 브라우저 새 탭이 아닌 **앱 탭 바**에 탭을 열고 이동한다.
쿼리 파라미터(변수)도 탭 path에 함께 저장되므로, 탭 전환 후 돌아와도 파라미터가 유지된다.

#### 이동 버튼이 있는 경우 소제목 행 우측 버튼 배치 순서

이동 버튼(페이지 전환)이 있을 때는 소제목 행 우측을 아래 순서로 배치한다:

```
[이동버튼1] [이동버튼2]  |  [저장] [삭제]
```

구분선 코드: `<span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>`

- 이동 버튼은 `selectedItem` 존재 시에만 렌더 (구분선 포함)
- 저장·삭제는 기존 권한 조건(`isEditYn`) 그대로 유지

```jsx
<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
  {selectedItem && (
    <>
      <button className="btn btn-primary" type="button" onClick={...}>{t('btn.xxx')}</button>
      <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
    </>
  )}
  {isEditYn && (
    <>
      <button className="btn btn-primary" type="button" onClick={handleSave}>{t('btn.save')}</button>
      {selectedItem && <button className="btn btn-danger" type="button" onClick={handleDelete}>{t('btn.delete')}</button>}
    </>
  )}
</div>
```

---

#### Import — `useOpenInTab` 공통 훅 사용 (필수)

탭 이동 + max tab 체크 로직은 **`useOpenInTab` 훅**으로 공통화되어 있다.  
직접 `openTab` / `navigate` 를 조합하지 말고 반드시 이 훅을 사용할 것.

```jsx
import { useOpenInTab } from '@/hooks/useOpenInTab'
```

#### 컴포넌트 내 설정

```jsx
const openInTab = useOpenInTab()
```

훅 내부에서 `useNavigate`, `useTabStore`, `useMenus`, `useConfigs`, `App.useApp()` 를 모두 처리하므로 컴포넌트에서 별도 선언 불필요.

#### 버튼 예시

```jsx
<button className="btn btn-primary" type="button"
  onClick={() => openInTab('master/object', `?chapteruid=${selectedChap.chapteruid}&docid=${docid}`)}>
  {t('btn.object.manage')}
</button>
```

- `routePath`: `router/index.jsx`에 등록된 경로 (앞의 `/` 제외, 예: `'master/object'`)
- `query`: 쿼리 파라미터 문자열 (예: `'?chapteruid=1&docid=2'`), 없으면 생략
- `fallbackLabel` (선택): 메뉴 DB에 없는 경로일 때 탭 라벨 대체 문자열
- 같은 탭이 이미 열려 있으면 path(쿼리 포함)를 최신값으로 갱신 후 이동 (`tabStore.openTab` 동작)
- 새 탭인데 `tabs.length >= maxtabs`이면 경고 후 이동 중단 — `msg.tab.maxcount` 키 필요, 번역값에 `{n}` 플레이스홀더 포함 (예: `탭은 최대 {n}개까지 열 수 있습니다.`)

#### 훅 위치

`frontend/src/hooks/useOpenInTab.js`

---

### 로딩 오버레이 — 표준 패턴

시간이 걸리는 작업(미리보기, AI 생성 등) 실행 중 화면 전체를 덮는 로딩 표시. **반드시 이 디자인을 사용할 것.**

#### 필수 import

```jsx
import { App, Spin } from 'antd'
```

#### 상태

```jsx
const [previewLoading, setPreviewLoading] = useState(false)
```

#### JSX (컴포넌트 최하단, return 블록 내부 마지막)

```jsx
{/* 로딩 오버레이 */}
{previewLoading && (
  <div style={{
    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
    background: 'rgba(0,0,0,0.5)',
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    zIndex: 9999,
  }}>
    <div style={{
      background: '#fafae5', padding: '20px 30px', borderRadius: 8,
      fontSize: 16, fontWeight: 'bold', color: '#6c757d',
      boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <Spin />
      <span>{t('msg.loading.wait')}</span>
    </div>
  </div>
)}
```

#### 사용 패턴

```jsx
const handlePreview = async () => {
  setPreviewLoading(true)
  try {
    const resp = await apiClient.post('/xxx/preview', { ... })
    // 결과 처리
  } catch (e) {
    message.error(t('msg.preview.error') + ': ' + (e.response?.data?.detail || e.message))
  } finally {
    setPreviewLoading(false)
  }
}
```

- `msg.loading.wait` 키가 다국어 테이블에 등록되어 있어야 함 (기본값: "Please wait a moment...")
- `zIndex: 9999` — 모달 위에도 표시되도록 고정
- 배경색 `#fafae5` (연한 노란빛 흰색) 고정

---

### ui_terms 등록 방법

화면 작성 완료 후 사용된 `t('키')` 목록을 추출해 Supabase에 등록한다.

| 테이블 | 등록 내용 |
|--------|-----------|
| `ui_terms` | `term_key`, `default_text` (영문 기본값) |
| `ui_term_translations` | `term_key`, `language_cd`, `translated_text` |

다국어 적용 시 기존 키 목록 및 SQL 예시는 **[docs/term_keys.md](../docs/term_keys.md)** 를 참고할 것.

