# Django → FastAPI+React 마이그레이션 차이 분석
> 작성일: 2026-04-09 | 전체 완성도: 약 85~90%

---

## 1. 아키텍처 핵심 차이

| 항목 | Django (구) | FastAPI+React (신) |
|------|------------|-------------------|
| 렌더링 | 서버사이드(SSR) | 클라이언트사이드(CSR) |
| 인증 | Django Session + CSRF | JWT (Access + Refresh) |
| UI | Bootstrap + 커스텀 CSS | Ant Design 5.x |
| 상태관리 | Session + 템플릿 변수 | Zustand + TanStack Query |
| API | 직접 DB 접근 | FastAPI REST |
| 메뉴 | HTML `<nav>` + CSS | Ant Design Menu |

---

## 2. 페이지별 구현 현황

### ✅ 구현 완료

| 기능 | Django URL | React Route |
|------|-----------|-------------|
| 홈 | `/` | `/` |
| 서비스 소개 | `/service_view/` | `/service` |
| 기능 소개 | `/about_view/` | `/about` |
| 서비스 이용 | `/usage/` | `/usage` |
| 로그인 | `/login/` | `/login` |
| 회원가입 | `/register/` | `/register` |
| 문서 목록 | `/req/req_doc_list/` | `/req/list` |
| 문서 설정 | `/req/req_doc_setting/` | `/req/doc-setting` |
| 문서 상태 | `/req/req_doc_status/` | `/req/doc-status` |
| 챕터 읽기 | `/req/req_chapters_read/` | `/req/chapters-read` |
| 챕터 항목 읽기 | `/req/chapter_objects_read/` | `/req/chapter-objects` |
| 문서 작성 | `/req/req_doc_write/` | `/req/write` |
| 문서 읽기 | `/req/chapter_read/` | `/req/doc-read` |
| 문서 관리 | `/master/docs/` | `/master/docs` |
| 챕터 관리 | `/master/chapters/` | `/master/chapters` |
| 항목 관리 | `/master/object/` | `/master/object` |
| DB 데이터 | `/master/datas_db/` | `/master/datas/db` |
| Excel 데이터 | `/master/datas_ex/` | `/master/datas/ex` |
| AI 데이터 | `/master/datas_ai/` | `/master/datas/ai` |
| 테이블 설정 | `/master/tables/` | `/master/tables` |
| 차트 설정 | `/master/charts/` | `/master/charts` |
| 문장 설정 | `/master/sentences/` | `/master/sentences` |
| AI 차트 | `/llm/ai_charts/` | `/master/ai-charts` |
| AI 문장 | `/llm/ai_sentences/` | `/master/ai-sentences` |
| AI 테이블 | `/llm/ai_tables/` | `/master/ai-tables` |
| DB 연결정보 | `/master/servers/` | `/settings/servers` |
| 프로젝트 설정 | `/master/projects/` | `/settings/projects` |
| 기업 설정 | `/master/tenants/` | `/settings/tenants` |
| 내 정보 | `/myinfo/` | `/myinfo` |
| 기업 사용자 | `/master/tenant_users/` | `/org/tenant-users` |
| 기업 LLM | `/master/tenant_llms/` | `/org/tenant-llms` |
| 프로젝트 관리 | `/master/projects/` | `/org/projects` |
| 프로젝트 사용자 | `/master/project_users/` | `/org/project-users` |
| 사용자 관리 | `/master/user_role/` | `/admin/user-role` |
| 샘플 프롬프트 | `/master/ai_sample_prompt_manage/` | `/admin/sample-prompts` |
| LLM 관리 | `/master/llms/` | `/admin/llms` |
| LLM API 관리 | `/master/llmapis/` | `/admin/llmapis` |
| 기업 생성 요청 | `/master/tenant_request_list/` | `/admin/tenant-requests` |

---

### ❌ 미구현 (누락)

| 우선순위 | 기능 | Django URL | 비고 |
|---------|------|-----------|------|
| 🔴 높음 | 비밀번호 재설정 | `/password-reset/` | ✅ **수정완료** (2026-04-09) |
| 🔴 높음 | 기업 생성 요청 상세 | `/master/tenant_request/` | ~~리스트만 있고 상세 없음~~ → ✅ **수정완료** (2026-04-09) |
| 🟡 중간 | 문서 매개변수 설정 | `/master/doc_params/` | ✅ **수정완료** (2026-04-09) |
| 🟡 중간 | 챕터 템플릿 에디터 | `/master/chapter_template/` | ✅ **수정완료** (2026-04-09) |
| 🟡 중간 | 약관/조건 | `/terms_conditions/` | ✅ **수정완료** (2026-04-09) |
| 🟡 중간 | 도움말 관리 | `/master/help/` | ✅ **수정완료** (2026-04-09) |
| 🟡 중간 | 도움말 검색 | `/search_help/` | ✅ **수정완료** (2026-04-09) |
| 🟢 낮음 | QnA 관리 | `/qna_view/` 등 | ✅ **수정완료** (2026-04-09) |
| 🟢 낮음 | FAQ 관리 | `/faq_view/` 등 | ✅ **수정완료** (2026-04-09) |
| 🟢 낮음 | 따라하기 | `/follow/` | ✅ **수정완료** (2026-04-09) |
| 🟢 낮음 | 팝업 숨기기 | `/hide_popup/` | ✅ **수정완료** (2026-04-09) |

---

### ⚠️ 구현됐으나 동작 차이 있는 항목

| 기능 | 차이 내용 | 파일 위치 |
|------|----------|---------|
| AI 항목 설정 (CA/SA/TA) | 대상문서·챕터명 표시 안됨, 데이터목록 비어있음 → ✅ **수정완료** (2026-04-09) | `AiLlmPage.jsx`, `llm.py` |
| 문서 목록 (`/req/list`) | 아이콘 클릭 후 돌아오면 목록 리셋, 선택 행 색상 유지 안됨 → ✅ **수정완료** (2026-04-09) | `ReqDocListPage.jsx` |
| 뒤로가기 아이콘 | 일부 페이지 누락 → ✅ **수정완료** (2026-04-09) | 각 페이지 |
| 문서 조회 (`문서 조회` 버튼) | req_chapter_read 연결 미구현 → ✅ **수정완료** (2026-04-09) | `ReqDocListPage.jsx` |

---

## 3. 메뉴 구조 비교

### Django (base.html 사이드메뉴)
```
공개
  서비스 소개 / 기능 소개 / 서비스 이용
로그인 후
  📄 문서
  기준 정보 (sampledocyn=Y or PM 이상)
    문서관리 / 챕터관리 / 항목관리 / Excel데이터 / AI데이터
  프로젝트 관리 (billing≠Fr/Pr and TM/PM)
    기업사용자 / 기업LLM / 프로젝트 / 프로젝트사용자
  DB 정보 (roleid=7 or TM)
    DB연결정보 / DB데이터
  기업관리 (roleid=7)
    사용자관리 / 기업관리 / 샘플프롬프트 / LLM / LLMAPI / 기업생성요청
  개발메뉴 (roleid=7)
    RAG / MCP (외부링크)
```

### React (AppLayout.jsx)
동일한 권한 체계로 구현됨. URL 경로만 일부 변경:
- `/master/datas_db/` → `/master/datas/db`
- `/master/ai_sample_prompt_manage/` → `/admin/sample-prompts`

---

## 4. 우선 수정 목록 (동작 차이)

### 즉시 수정 필요
1. ✅ **AI 항목 설정** — 대상문서·챕터명·데이터목록 표시 문제 **(2026-04-09 수정완료)**
2. ✅ **문서 목록** — 아이콘 클릭 후 목록 유지, 선택 행 유지, 뒤로가기 버튼 **(2026-04-09 수정완료)**

### 단기 수정 필요
3. ✅ **문서 조회 버튼** — `/req/doc-read` 연결 완료 **(2026-04-09)**
4. **기업 생성 요청 상세** — tenant_request 상세 페이지
5. **비밀번호 재설정** — 로그인 페이지 링크 연결

### 중기 검토
6. **문서 매개변수** — doc_params 페이지
7. **챕터 템플릿 에디터** — Vue → React 전환

---

## 5. 수정 이력

### ✅ AI 항목 설정 (CA/SA/TA) — 2026-04-09 수정완료

**수정 파일**: `backend/app/routers/llm.py`, `frontend/src/components/llm/AiLlmPage.jsx`

**원인 및 수정 내용**:

| 항목 | 문제 | 수정 |
|------|------|------|
| 대상문서명 (`docnm`) 표시 안됨 | `users.docid`를 사용해 문서명을 못 찾음 | `chapters.docid → docs.docnm` 경로로 조회 (Django 동일 방식) |
| 데이터목록 비어있음 | `users.projectid`로 datas 조회 → 현재 문서의 project와 불일치 | `chapters.docid → docs.projectid → datas` 경로로 조회 |
| 기존 설정 로드 안됨 | `chapteruid+objectnm`으로 직접 테이블 조회 | objectuid 먼저 조회 후 해당 objectuid로 테이블 조회 (Django 동일 방식) |
| Supabase RLS 차단 | user JWT로 전체 데이터 조회 시 RLS에 막힘 | 사용자 인증은 user JWT, 데이터 조회는 `get_service_client()` 사용 |
| 프론트엔드 구조 불일치 | Django `ai_common.html` + `ai_actions.js` 패턴 미반영 | `AiLlmPage.jsx` 전체 재작성: 컬럼 칩 클릭→커서 삽입, 3패널 샘플프롬프트 모달, 로딩 오버레이 구현 |

---

### ✅ 문서 목록 (`/req/list`) — 2026-04-09 수정완료

**수정 파일**: `frontend/src/pages/req/ReqDocListPage.jsx`, `frontend/src/hooks/useGendocs.js`

**수정 내용**:

| 항목 | 내용 |
|------|------|
| 목록 유지 | sessionStorage에 날짜 범위(SS_START, SS_END) 저장. 페이지 이동 전 `saveSession()` 호출, 복귀 시 `initDates()`로 복원 |
| 선택 행 유지 | sessionStorage에 gendocuid 저장(SS_GENDOCUID). 복귀 후 gendocs 로드 완료 시 useEffect에서 해당 행 자동 선택 |
| 뒤로가기 아이콘 | 페이지 타이틀 우측에 back.svg 아이콘 추가 |
| 문서 조회 연결 | `handleDocRead()` → `/req/doc-read?gendocs=...` → `ReqDocReadPage.jsx` (Django `req_chapter_read.html` 상당) |
| message API | `import { message }` (static) → `App.useApp()` 훅으로 전환 (CLAUDE.md 준수) |
