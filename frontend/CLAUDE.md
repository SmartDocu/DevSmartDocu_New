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

## ⚠️ mutation `onError`/`onSuccess`는 절대 화살표 함수 암묵적 반환으로 `message.xxx()`를 호출하지 말 것

```jsx
// ❌ 금지 — mutation이 영원히 멈추는 버그 발생
onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),

// ✅ 올바른 방법 — 블록 바디로 감싸서 반환값을 undefined로 만들 것
onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
```

**원인**: antd의 `message.error()`/`message.success()`는 `MessageType`(= `PromiseLike<boolean>`, 메시지가 닫힐 때 resolve됨)을 반환한다.
TanStack Query v5의 mutation 내부 코드는 `await this.options.onError?.call(...)` 형태로 **콜백의 반환값을 그대로 await** 한다.
`onError`/`onSuccess`를 화살표 함수 암묵적 반환(`(err) => message.error(...)`)으로 작성하면 `message.xxx()`가 반환한 `MessageType`이 그대로 반환값이 되고, 이게 **영원히 resolve 안 되는 경우**(React19/antd 렌더링 이슈 등으로 메시지가 정상적으로 닫히지 않는 경우) mutation의 `execute()`가 끝까지 진행되지 못한다.

**증상**: 실제 API 요청/응답은 정상인데 화면에 아무 반응도 없고, 버튼이 `disabled` 상태로 영원히 멈춘다 (`isPending`이 계속 `true`). `mutate()`에 전달한 로컬 `onSuccess`/`onError`는 물론 `mutateAsync()`를 `await`하는 코드도 전부 무한 대기하게 된다.

**발견 경위**: `master/datas/ex` 화면에서 엑셀 업로드 용량 제한 에러가 화면에 안 뜨는 버그를 추적하다 `useDatas.js`의 `onError: (err) => message.error(...)` 패턴이 원인임을 확인 (2026-07-03). 같은 패턴이 다른 훅 파일(`useAdmin.js`, `useCodes.js`, `useGendocs.js`, `useMenus.js`, `useMessages.js`, `useOrg.js`, `useSettings.js`, `useTerms.js`)과 일부 페이지 컴포넌트에도 남아있을 수 있으니, **다른 화면을 수정하게 되면 해당 화면이 참조하는 훅의 `onSuccess`/`onError`도 블록 바디인지 확인할 것.**

---

## 신규 화면 템플릿

**2026-09-09부터 신규 화면은 `frontend/src/pages/req/ReqDocListPage.jsx`("문서 관리" 화면)를 표준 템플릿으로 사용한다.** 아래 규칙은 이 화면에서 확정된 것 — 예전 `MasterDocsPage.jsx` 스타일(아이콘 없는 버튼, 테두리 없는 패널 등)로 새로 만들지 말 것. 구조(2열 목록+상세, `form-group`, 소제목 행)는 이어받되 시각 스타일이 아래처럼 바뀌었다.

### 화면 구조 규칙

| 항목 | 규칙 |
|------|------|
| 레이아웃 | 2열 (목록 : 상세 = 대략 6:4, 화면 성격에 맞게 조정 가능) |
| 영역 구분 | 목록/상세 패널 각각 `className="panel-section"` (흰 배경 + 테두리 + 12px 라운드 카드, index.css) — 제목 영역을 제외한 배경은 옅은 회색(`var(--body-background-color, #f5f5f5)`) |
| 패널 헤더 구분선 | 카드 최상단 헤더 줄에 `margin:'-16px -18px 16px', padding:'16px 18px 12px', borderBottom:'1px solid var(--border-color, #e3e6eb)'`을 줘서 카드 폭 전체를 가로지르는 구분선을 만든다 (ReqDocListPage.jsx 참고) |
| 페이지 제목(`page-title`) 앞 그래디언트 바 | `.page-title .gradient-bar`는 전역적으로 숨겨져 있다(`display:none`). 화면에 다시 넣고 싶으면 클래스에 기대지 말고 인라인 style로 직접 그린다(색/크기는 ReqDocListPage.jsx 참고) |
| 목록 건수 · 매개변수 개수 등 카운트 표시 | 제목 옆 배지: `display:'inline-flex', alignItems:'center', lineHeight:1, font:"500 11px monospace", color:'#8d9199', background:'#f2efe9', borderRadius:6, padding:'5px 8px 4px'` — 문구는 `lbl.count.docs`/`lbl.count.items`(`{n}건`) 재사용, 새 도메인이면 같은 패턴으로 키 추가 |
| 신규 버튼 | 좌측 패널 헤더 우측, `btn btn-primary` + 앞에 `<PlusOutlined style={{ marginRight: 6 }} />` |
| 다른 화면으로 이동하는 버튼(문서 조회·챕터 조회 등) | `btn btn-secondary`, 텍스트 뒤에 `<ExportOutlined style={{ marginLeft: 6 }} />`. 이동은 `useOpenInTab`으로 앱 탭에 오픈 |
| 저장·마감/마감해제·삭제 버튼 | **상세 패널 최상단 헤더**(제목 줄)에 모아 배치 — 순서는 [저장] [마감/마감해제 토글] `\|` [삭제(아이콘만)]. 하위 소제목(예: "매개변수 입력")에는 버튼을 두지 않고 제목 + 카운트 배지만 |
| 저장 버튼 | `btn btn-primary` + `<SaveOutlined style={{ marginRight: 6 }} />`. `disabled`은 저장 mutation의 `isPending`뿐 아니라 **삭제 mutation의 `isPending`도 OR로 같이 걸 것**(삭제 진행 중 저장이 동시에 나가는 것 방지, 2026-09-11 확정) |
| 마감류 토글 버튼 | `btn btn-secondary` + `<CheckOutlined/>`(마감) 또는 `<CloseOutlined/>`(마감 해제) |
| 삭제 버튼 | `btn btn-danger`, 아이콘만(`<DeleteOutlined/>`), 38×38 정사각형(`padding:0, display:'flex', alignItems:'center', justifyContent:'center'`) — `.btn` 공용 클래스의 `height:38px`와 통일(2026-09-11, 이전엔 32×32였음) |
| 조회(필터 실행) 버튼 | `.btn-query`(진한 파랑, 아이콘+텍스트 pill) — `.icon-btn`이나 아이콘만 있는 무테두리 버튼 금지 |
| 필터의 프리셋/단일선택 그룹(기간 3개월·1년·전체, Doc/DocGroup 등) | 라디오·링크버튼 나열 금지. `.segmented`(트랙) + `.segmented-item`(pill, 선택 시 `.segmented-item.active`) 사용 |
| 필터 라벨 뒤 콜론(`:`) | 붙이지 않는다 |
| 검색/필터 입력창의 위치 | **목록 패널 안이 아니라 목록/상세 2패널 행 위쪽에 별도 `panel-section`(filter-bar)으로 분리할 것**(2026-09-14 확정, admin/ui-terms에서 "필터는 상단에 따로 두었으면 좋겠어"로 명시 요청). 단일 텍스트 검색이라도 `filter-item`+bold 라벨로 감쌀 것 — 목록 패널 헤더 바로 아래 인라인으로 두지 말 것 |
| 버튼 색상 | 저장·신규 = 연한 파랑(`.btn-primary` → `--primary-btn`), 조회 = 진한 파랑(`.btn-query` → `--query-btn`), 그 외(마감/마감해제 등) = 흰색/회색(`.btn-secondary` → `--secondary-btn`), 삭제 = 흰 배경 + 빨간 텍스트(`.btn-danger` → `--danger-btn`) |
| 버튼 형식 | AntD 아이콘 포함(위 항목 참고) — "아이콘 없이 텍스트만"이었던 예전 규칙은 폐기. 단 `icon-btn`(테두리 없는 순수 아이콘 버튼) 클래스는 여전히 쓰지 않는다 |
| 다국어 | 모든 버튼·레이블·메시지·제목에 `t()` 사용. **`t()` 뒤에 `\|\| '한글기본값'` 절대 추가 금지** — 키 미등록 시 키 문자열이 그대로 노출되는 것이 의도된 동작 |
| 언어 리렌더 | 컴포넌트 최상단 `useLangStore((s) => s.translations)` 구독 |
| 편집 권한 | 저장·삭제는 `isEditYn` 조건부 렌더. **반드시 `user?.editbuttonyn === 'Y'`** 로 판단 — `editbuttonyn`은 항상 문자열 `"Y"` 또는 `"N"`이므로 `!!` truthy 체크 사용 금지 (`"N"`도 truthy) |
| 폼 레이아웃 | `form-group` 클래스 사용(라벨은 위 줄, 입력은 아래 줄). 옆으로 나란히 두는 `form-group-left`는 신규 화면에서 지양 |
| 입력창 높이 | 최소 36~38px (기존 24~25px는 지양) |
| 필수 필드 표시 | 라벨 앞에 `<span style={{ color: 'red', marginRight: 2 }}>*</span>` 삽입 |
| description 필드 | `<textarea rows={3} style={{ resize: 'vertical' }}>` (기본 3줄, 세로 리사이즈 가능) |
| number 입력 | `<input type="number">` |
| 소제목 행 | 버튼 유무와 무관하게 높이 통일 — 항상 아래 구조 사용. 버튼 없는 경우 `<div />` placeholder 삽입 |
| 패널 스크롤 | **패널 전체(헤더 포함)가 아니라 헤더 아래 본문 영역만 스크롤될 것(2026-09-14 확정)**. 패널 자체는 고정 `height`(또는 `maxHeight`) + `display:'flex', flexDirection:'column', overflow:'hidden'`로 감싸고, 헤더 div에 `flexShrink: 0`을 추가, 헤더 바로 아래에 본문 전체를 감싸는 `<div style={{ flex: 1, overflowY: 'auto' }}>...</div>` 래퍼를 하나 더 둔다 — 상세/폼/번역표처럼 세로로 길어질 수 있는 콘텐츠가 저장·삭제 버튼이 있는 헤더까지 같이 밀어 올리지 않도록 하기 위함(사용자가 admin/sample-prompts에서 "헤더 제외 하단만 스크롤"을 명시 요청, 이후 기존에 작업했던 화면 전체(35개 파일, 76개 패널)에 일괄 적용함). **주의**: `AppLayout.jsx`의 콘텐츠 wrapper에 있던 12px 상단 padding을 제거했으므로(2026-09-09) 224px는 더 이상 정확한 값이 아닐 수 있다 — 화면 하단이 잘리거나 남는 것 같으면 재계산할 것 |
| 목록이 길어 페이지네이션이 필요한 경우 | **위치는 항상 중앙 정렬(2026-09-14 확정, 예외 없음)**. 직접 만든 `<Pagination>`(클라이언트 사이드 페이징, billing-history/admin·user-role/admin·products/admin·popups에서 쓴 패턴)은 감싸는 div에 `display:'flex', justifyContent:'center'`. AntD `<Table>` 내장 페이지네이션을 쓸 때는 `pagination={{ ..., position: ['bottomCenter'] }}`로 지정(기본값은 우측 정렬이라 반드시 명시할 것). 10건 넘을 때만 표시하는 클라이언트 사이드 페이징은 `marginTop:'auto'`로 패널 하단에 고정하는 패턴도 같이 적용(패널을 `display:'flex',flexDirection:'column'` 고정 높이로 만들고 테이블은 자연 높이, 페이지네이션만 하단 고정 — 목록 건수에 따라 페이지네이션 위치가 들쭉날쭉해지는 문제 방지) |

#### 소제목 행 표준 패턴

버튼이 **있는** 경우:
```jsx
<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
  <h3 style={{ margin: 0 }}>{t('ttl.xxx')}</h3>
  <button className="btn btn-primary" type="button" onClick={handleNew}>
    <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
  </button>
</div>
```

버튼이 **없는** 경우:
```jsx
<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
  <h3 style={{ margin: 0 }}>{t('ttl.xxx')}</h3>
  <div />
</div>
```

#### 2열 패널(카드) 표준 패턴

```jsx
{/* 좌측 패널 */}
<div className="panel-section" style={{ flex: 6, height: 'calc(100vh - 224px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
  <div style={{
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, minHeight: 32,
    margin: '-16px -18px 16px', padding: '16px 18px 12px',
    borderBottom: '1px solid var(--border-color, #e3e6eb)',
  }}>
    <h3 style={{ margin: 0 }}>{t('ttl.xxx')}</h3>
    <div />
  </div>
  <div style={{ flex: 1, overflowY: 'auto' }}>
    ...
  </div>
</div>

{/* 우측 패널 */}
<div className="panel-section" style={{ flex: 4, height: 'calc(100vh - 224px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
  <div style={{ ...헤더... }}>...</div>
  <div style={{ flex: 1, overflowY: 'auto' }}>
    ...
  </div>
</div>
```

> **224px 산출 근거(참고용, 위 "패널 스크롤" 주의사항 참고)**: Header(60) + Content marginTop(104) + page-title 높이(40) + page-title margin-bottom(20)

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

### 날짜/시간 표시 및 검색 — Timezone 규칙

#### 기본 원칙
- DB는 UTC 저장. **모든 날짜/시간 변환은 백엔드에서 처리**하고, 프론트는 백엔드가 내려준 문자열을 그대로 표시한다.
- 포맷: **`"YYYY-MM-DD HH:MM"`** (예: "2026-06-16 14:30") — 전 화면 통일.
- `new Date(...).toLocaleDateString()` / `toLocaleString()` 등 브라우저 로컬 변환 **절대 사용 금지**.

#### 날짜 표시 — 백엔드 문자열 그대로 렌더링

```jsx
// ✅ 올바른 방법 — 백엔드가 timezone 적용 후 포맷된 문자열을 내려줌
<span>{row.createdts}</span>
<span>{item.createfiledts || '-'}</span>

// ❌ 금지 — 브라우저 로컬 시간 기준으로 변환됨
<span>{new Date(row.createdts).toLocaleDateString()}</span>
```

#### 날짜 검색 (DatePicker / RangePicker) — 날짜 문자열 그대로 API에 전달

프론트는 `dayjs` 객체를 `"YYYY-MM-DD"` 문자열로 변환해 API에 전달하기만 하면 된다.
UTC 변환은 백엔드가 `offsetminutes`를 이용해 처리한다.

```jsx
import dayjs from 'dayjs'
const { RangePicker } = DatePicker

const [dates, setDates] = useState([dayjs().subtract(1, 'month'), dayjs()])

// API 호출 시
const sd = dates[0]?.format('YYYY-MM-DD')  // "2026-06-01"
const ed = dates[1]?.format('YYYY-MM-DD')  // "2026-06-16"
// → GET /api/items?start_date=2026-06-01&end_date=2026-06-16
// 백엔드에서 offsetminutes 적용해 UTC로 변환 후 조회
```

#### user.offsetminutes 참조 (필요한 경우만)

로그인 시 `authStore`의 `user.offsetminutes`에 사용자 timezone offset이 저장된다.
백엔드를 거치지 않고 프론트에서 직접 시간 계산이 필요한 경우에만 사용.

```jsx
import { useAuthStore } from '@/stores/authStore'
const offsetminutes = useAuthStore(s => s.user?.offsetminutes)  // 예: 540, -540, null
```

> 참고 구현: `MyInfoPage.jsx` (날짜 표시), `ReqDocListPage.jsx` (RangePicker 검색)

---

### ui_terms 등록 방법

화면 작성 완료 후 사용된 `t('키')` 목록을 추출해 Supabase에 등록한다.

| 테이블 | 등록 내용 |
|--------|-----------|
| `ui_terms` | `term_key`, `default_text` (영문 기본값) |
| `ui_term_translations` | `term_key`, `language_cd`, `translated_text` |

다국어 적용 시 기존 키 목록 및 SQL 예시는 **[docs/term_keys.md](../docs/term_keys.md)** 를 참고할 것.

