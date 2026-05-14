# 팝업 페이지 제작 가이드

팝업 페이지는 `PopupManager`가 iframe으로 로드한다.
iframe은 별도 React 앱 인스턴스로 실행되므로 일반 페이지와 다른 규칙이 적용된다.

---

## 새 팝업 요청 시 전달해야 할 정보

아래 항목을 알려주면 파일 생성 + 라우터 등록 + INSERT 구문까지 한번에 작업한다.

### 필수 정보

| 항목 | 예시 | 설명 |
|------|------|------|
| **팝업 이름** | `summer-event-2026` | 파일명·URL 경로에 사용 (`/popup/summer-event-2026`) |
| **노출 기간** | `2026-06-01 ~ 2026-08-31` | startdts / enddts |
| **언어별 콘텐츠** | 아래 참고 | 지원할 언어와 각 언어의 텍스트 |

### 언어별 콘텐츠 — 이 형식으로 전달

지원하지 않는 언어는 생략하면 자동으로 영어(en) 표시.
**en은 반드시 포함.**

```
en:
  제목: Summer Event 2026
  본문: Start with D2Doc and get 3 months free!
  버튼: Start Free Trial

ko:
  제목: 2026 여름 이벤트
  본문: D2Doc를 지금 시작하면 3개월 무료!
  버튼: 무료 체험 시작

ja:             ← 없으면 생략 가능 (en fallback)
  제목: 2026 夏のイベント
  본문: D2Docを今すぐ始めると3ヶ月無料！
  버튼: 無料トライアル開始
```

### 선택 정보 (생략 시 기본값 사용)

| 항목 | 기본값 | 설명 |
|------|--------|------|
| **팝업 크기** | width=480, height=300 | 픽셀 단위 |
| **팝업 위치** | lefts=120, top=120 | 화면 좌상단 기준 픽셀 |
| **n일간 보지 않기** | 7일 | 버튼 클릭 후 숨김 유지 기간 |
| **노출 시점** | M (홈페이지) | M: 홈페이지, L: 로그인 후 |
| **디자인 컨셉** | 없으면 SampleEventPopup 스타일 적용 | 색상, 배경, 레이아웃 방향 |

---

## 파일 위치

```
frontend/src/pages/popup/
├── SampleEventPopup.jsx   ← 샘플 참고
└── (새 팝업 파일).jsx
```

---

## 언어 처리 — 가장 중요한 규칙

### iframe이기 때문에 `langStore` 사용 불가

| 일반 페이지 | 팝업 페이지 |
|-------------|-------------|
| `useLangStore(s => s.languageCd)` 사용 가능 | **사용 불가** (별도 React 인스턴스, store 공유 안 됨) |

### 대신 `useSearchParams`로 URL 파라미터를 읽는다

`PopupManager`가 iframe src에 `?lang=ko` 자동으로 붙여줌.

```jsx
import { useSearchParams } from 'react-router-dom'

const [params] = useSearchParams()
const langCd = params.get('lang') || 'en'
```

### 영어 fallback 필수

`en`은 반드시 포함. 지원하지 않는 언어는 자동으로 영어로 떨어짐.

```js
const content = {
  en: { headline: '...', body: '...', cta: '...' },   // 필수
  ko: { headline: '...', body: '...', cta: '...' },   // 선택
  ja: { headline: '...', body: '...', cta: '...' },   // 선택
  // es 없으면 → en 자동 fallback
}

const c = content[langCd] ?? content.en   // 이 패턴 항상 사용
```

---

## 페이지 구조 규칙

```jsx
export default function MyPopup() {
  const [params] = useSearchParams()
  const langCd = params.get('lang') || 'en'
  const c = content[langCd] ?? content.en

  return (
    // height: 100vh 필수 — iframe 높이가 DB popups.height로 고정되므로
    <div style={{ height: '100vh', ... }}>
      ...
    </div>
  )
}
```

- `AppLayout`, 헤더, 사이드바 **없음** — 독립 페이지
- `height: 100vh` — iframe 안에서 꽉 채워야 함
- 외부 링크 이동 시 `target="_blank"` 또는 `window.parent.postMessage` 사용

---

## 라우터 등록 — 위치 주의

`frontend/src/router/index.jsx` 최상단 (AppLayout, RequireAuth **바깥**)에 등록.

```jsx
import MyPopup from '@/pages/popup/MyPopup'

export const router = createBrowserRouter([
  // ── 팝업 콘텐츠 페이지 ──────────────────────────────────
  { path: '/popup/sample-event', element: <SampleEventPopup /> },
  { path: '/popup/my-popup',     element: <MyPopup /> },      // ← 여기

  // ── 인증 불필요 ─────────────────────────────────────────
  { path: '/login', element: <LoginPage /> },
  ...
])
```

---

## DB 등록 (popups 테이블)

```sql
INSERT INTO sdoc.popups
  (title, pageurl, startdts, enddts, width, height, lefts, top,
   useyn, deactivateday, mainlogin, creator)
VALUES
  ('팝업 제목',
   '/popup/my-popup',        -- 위에서 등록한 경로
   '2026-01-01 00:00:00+00',
   '2026-12-31 23:59:59+00',
   480, 300,                 -- width, height (px)
   120, 120,                 -- lefts, top (px, 화면 좌상단 기준)
   true,
   7,                        -- n일간 보지 않기
   'M',                      -- M: 메인(홈), L: 로그인 후
   '{creator_uuid}');
```

### mainlogin 코드값

| 값 | 노출 시점 |
|----|-----------|
| `M` | 홈페이지 (`HomePage`) |
| `L` | 로그인 직후 (미구현, 추후 확장) |

---

## 체크리스트

- [ ] `content.en` 포함 여부
- [ ] `content[langCd] ?? content.en` 패턴 사용 여부
- [ ] `height: 100vh` 적용 여부
- [ ] 라우터 AppLayout 바깥에 등록 여부
- [ ] DB `popups` 테이블에 INSERT 여부
