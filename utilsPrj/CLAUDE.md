# utilsPrj 가이드

## 역할

`pages`, `llm` 앱이 공유하는 유틸리티 모듈 모음. Supabase 접근, 데이터 처리, DOCX 생성, 암호화, SMS 발송 등 핵심 인프라 기능을 담당한다.

---

## 모듈 목록

### Supabase 관련

| 파일 | 역할 |
|------|------|
| `supabase_client.py` | Supabase 클라이언트 생성/관리 (핵심) |
| `supabase_session_refresh.py` | Django 미들웨어 — Supabase 토큰 자동 갱신 |

### 데이터 처리

| 파일 | 역할 |
|------|------|
| `process_data.py` | 데이터 처리 프로세스 정의 (메타데이터) |
| `process_data_db.py` | 외부 DB 쿼리 (ODBC, Oracle, SQLAlchemy) |
| `process_data_excel.py` | Excel 파일 읽기 (openpyxl) |
| `process_data_ai.py` | AI 기반 데이터 변환 |

### 문서 생성

| 파일 | 역할 |
|------|------|
| `chapter_making.py` | 챕터 DOCX 생성 (AI 차트 임베드 포함) |
| `chapter_making_ai_table.py` | AI 생성 테이블을 DOCX에 삽입 |
| `chapter_read.py` | 챕터 데이터 읽기 |
| `html_to_docx.py` | HTML → DOCX 변환 |
| `docx_read.py` | DOCX 파일 파싱 |

### 콘텐츠 유틸리티

| 파일 | 역할 |
|------|------|
| `chart_utils.py` | matplotlib/seaborn 차트 생성 (Base64 이미지 반환) |
| `table_utils.py` | 테이블 데이터 처리 |
| `sentences_utils.py` | 문장/문단 처리 |

### 보안 및 인프라

| 파일 | 역할 |
|------|------|
| `crypto_helper.py` | Fernet 암호화/복호화 |
| `sms_sender.py` | Naver Cloud SMS 발송 |
| `errorlogs.py` | 에러 로그 기록 |

---

## supabase_client.py — 상세

### 핵심 함수

```python
def get_thread_supabase(access_token=None, refresh_token=None) -> Client:
    """
    스레드 로컬 Supabase 클라이언트를 반환한다.
    멀티스레드 환경에서 클라이언트를 스레드별로 분리하여 충돌을 방지한다.
    """
```

### 연결 풀 설정

| 설정 | 값 |
|------|----|
| 최대 연결 수 | 10 |
| Keep-alive 연결 | 5 |
| 연결 타임아웃 | 10초 |
| 읽기 타임아웃 | 30초 |
| 재시도 횟수 | 2회 |

### 사용 패턴

```python
from utilsPrj.supabase_client import get_thread_supabase

# 뷰에서 항상 이 방식으로 클라이언트를 가져온다
supabase = get_thread_supabase(
    request.session.get('access_token'),
    request.session.get('refresh_token')
)

# 조회
result = supabase.table('docs').select('*').eq('tenant_id', tid).execute()

# 삽입
supabase.table('docs').insert({'name': '...', ...}).execute()

# 수정
supabase.table('docs').update({'name': '...'}).eq('id', doc_id).execute()

# 삭제
supabase.table('docs').delete().eq('id', doc_id).execute()
```

---

## supabase_session_refresh.py — 상세

Django 미들웨어로 `config/settings.py`의 `MIDDLEWARE`에 등록되어 있다.

동작:
1. 모든 요청에서 세션의 `access_token` 유효성 확인
2. 401 응답 감지 시 `refresh_token`으로 새 토큰 발급
3. 세션에 갱신된 토큰 저장

---

## crypto_helper.py — 상세

Fernet 대칭 암호화. DB에 저장되는 민감 데이터(DB 비밀번호, API 키 등)를 암호화한다.

```python
from utilsPrj.crypto_helper import encrypt_value, decrypt_value

# 암호화 (저장 시)
encrypted = encrypt_value("my-secret-password")

# 복호화 (읽기 시)
plain = decrypt_value(encrypted)
```

암호화 키는 환경변수 `ENCRYPTION_KEY`에서 가져온다 (`config/settings.py`의 `FERNET_KEY`).

---

## chart_utils.py — 주의사항

matplotlib을 사용한다. **멀티스레드 환경에서 주의**가 필요하다.

- 반드시 `matplotlib.use('Agg')` 백엔드 사용 (GUI 없는 환경)
- 차트 생성 후 반드시 `plt.close('all')` 호출
- 여러 스레드에서 동시에 plt 전역 상태를 공유하면 그래프가 혼재될 수 있다
- 스레드 안전을 위해 `Figure` 객체를 직접 생성하는 방식 권장

---

## process_data_db.py — 상세

외부 DB(MSSQL, Oracle 등)에서 데이터를 조회한다. 연결 정보는 Supabase의 `servers` 테이블에서 읽고 `crypto_helper`로 복호화하여 사용한다.

지원 DB:
- MSSQL (pyodbc)
- Oracle (oracledb)
- 기타 SQLAlchemy 지원 DB

---

## sms_sender.py — 상세

Naver Cloud Platform SMS API를 사용한다.

```python
from utilsPrj.sms_sender import send_sms

send_sms(to_number="01012345678", content="인증번호: 123456")
```

필요 환경변수: `NAVER_ACCESS_KEY_ID`, `NAVER_SECRET_KEY`, `NAVER_SMS_SERVICE_ID`, `NAVER_SMS_FROM_NUMBER`
