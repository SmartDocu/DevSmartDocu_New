# frontend 가이드 (React + Vite + Ant Design)

Django 템플릿 + Vue 3을 대체. FastAPI(포트 8001)와 통신.

---

## 기술 스택

| 라이브러리 | 버전 | 용도 |
|-----------|------|------|
| React | 19.2 | UI 프레임워크 |
| React Router | v6 | 클라이언트 라우팅 |
| Ant Design | 5.x | UI 컴포넌트 |
| Zustand | 5 | 전역 상태 (인증) |
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
├── stores/authStore.js   # Zustand 인증 스토어 (localStorage 영속)
├── hooks/useAuth.js      # 인증 mutations (useLogin, useLogout 등)
├── components/
│   ├── Auth/RequireAuth.jsx
│   └── Layout/AppLayout.jsx
└── pages/
    ├── HomePage.jsx
    └── auth/
        ├── LoginPage.jsx
        └── RegisterPage.jsx
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

## 마이그레이션 현황

| Stage | 상태 | 내용 |
|-------|------|------|
| 1 | ✅ | 골격, AppLayout, 라우터 |
| 2 | ✅ | 로그인/회원가입/SMS인증 |
| 3 | ✅ | 마스터 데이터 페이지 (docs, chapters) |
| 4 | ✅ | 항목/데이터/콘텐츠 설정 (objects, datas, tables, charts, sentences) |
| 5 | ✅ | 문서 요청/생성 (gendocs SSE, DOCX 업로드) |
| 6 | ✅ | 설정(서버/프로젝트/테넌트) + 내 정보 |
| 7 | 예정 | Vue + Django 템플릿 제거 |
