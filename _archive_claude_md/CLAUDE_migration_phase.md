# Smart Document — 프로젝트 가이드

AI 기반 문서 자동 생성 SaaS. 마스터 데이터(DB, Excel, AI)를 등록하고 LLM으로 차트·문장·테이블을 생성해 DOCX 출력.

---

# 진행 작업

현재 진행 작업 : Django 앱을 FastAPI + React으로 전환 중.
- `./_old_ref` 폴더 = Django 원본 앱 (참조용, 수정 금지)
- 각 주요 폴더에 `CLAUDE.md` 있음

---

## 작업 규칙

- 이미 읽은 파일은 다시 읽지 않는다.
- 사용자가 설명한 내용을 반복하지 않는다.
- requests.txt 파일 : 참조하지 않습니다.

**⚠️ 핵심 원칙 — 이관 작업임을 항상 기억할 것 ⚠️**
> 지금은 Django → FastAPI + React 이관 작업 중입니다.
> 독창적인 개선·추가가 아니라, 이전 앱(Django)과 **동일하게** 동작하도록 전환하는 것이 목적입니다.
> 구현 전 반드시 `./_old_ref` 의 해당 파일을 확인하고, 그 동작을 그대로 재현하십시오.

**이전앱과 같도록 만드는 것이 목적입니다. 임의로 추가하지 않습니다.**
- 이전앱 : Django 프레임워크에서 작업한 이관전 앱
    - html 참조 폴더 : ./_old_ref/pages/templates/pages
- 신규앱 : FastAPI + React 기반에 새로 작성되는 앱


---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 백엔드 | FastAPI 0.115+ / Python 3.12 |
| 프론트엔드 | React 19 + Ant Design 5 + Vite 6 |
| 상태관리 | Zustand 5 + TanStack Query v5 |
| DB / Auth | Supabase (PostgreSQL + GoTrue JWT) — ORM 미사용 |

---

## 폴더 (간략)

```
backend/app/   → FastAPI 라우터·스키마
frontend/src/  → React 페이지·컴포넌트·훅
utilsPrj/      → Supabase 클라이언트, DOCX 생성, 차트 등 공용 유틸
_old_ref/      → Django 참조본
docs/          → 상세 문서 (dev-guide.md, architecture.md, env-vars.md)
```

→ 상세: [docs/dev-guide.md](docs/dev-guide.md)

---

## 핵심 주의사항

**Supabase postgrest 인증** — `get_thread_supabase(access_token=token)` 호출 시  
내부적으로 `pg.headers["Authorization"]`를 user JWT로 덮어써야 RLS가 동작한다.  
`postgrest.auth(token)`은 `session.headers`를 수정하지만 `pg.headers`에 밀려 무시됨.  
→ `supabase_client.py`에서 처리 완료. 라우터에서 별도 처리 불필요.

**Ant Design `message`** — `App.useApp()`의 `message` 훅 사용. static `message.error()` 사용 금지.

**React SPA 서빙** — 프로덕션: FastAPI가 `frontend/dist/` 서빙. `/api/*` → FastAPI, 나머지 → `index.html`.


## 코드 수정 후 검증 규칙
- 검증 실패 시 스스로 수정 후 재검증을 최대 2회 반복할 것
- 2회 후에도 실패 시 : 작업을 중단하고 오류 내용과 수정 방향을 설명한 후 사용자 확인을 받을 것
- 모든 검증 통과 후에만 작업 완료로 보고할 것

### Backend (FastAPI)
- 코드 수정 후 타입 체크, 린트, 테스트를 실행할 것

### Frontend (React)
- 코드 수정 후 타입 체크, 린트, 테스트를 실행할 것
