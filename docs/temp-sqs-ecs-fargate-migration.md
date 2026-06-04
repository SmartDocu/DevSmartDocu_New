# Write All Chapters — SQS + ECS Fargate 전환 계획

## 배경

현재 [Write All Chapters] 기능은 FastAPI 안에서 SSE(Server-Sent Events) 스트리밍으로 처리된다.

```
브라우저 → POST /api/gendocs/{id}/generate → FastAPI (SSE 스트리밍)
                                               ├── Phase 1: 챕터별 LLM 생성
                                               ├── Phase 2: DOCX 병합
                                               └── Phase 3: Supabase 업로드
```

**문제점:**
- LLM 호출이 길어지면 HTTP 연결이 끊길 수 있음
- 동시 요청이 많아지면 API 서버 리소스 고갈
- 수평 확장이 어려움

**목표 구조:**
```
브라우저 → POST /api/gendocs/{id}/generate → FastAPI (즉시 반환)
                                               └── SQS 큐에 작업 적재
           ↓
           토스트 메시지 표시 후 사용자는 다른 화면으로 자유롭게 이동 가능

SQS 큐 → ECS Fargate 워커 (자동 확장)
           ├── Phase 1: 챕터별 LLM 생성
           ├── Phase 2: DOCX 병합
           └── Phase 3: Supabase 업로드

브라우저(챕터 화면 재진입 시)
  → GET /api/gendocs/{id}/generate/status 조회
  → 버튼 상태 / 완료 여부 표시
```

**UX 핵심 변경:**
- 진행률 창(로딩 오버레이) **완전 제거**
- 버튼 클릭 후 화면 차단 없음 → 사용자가 다른 작업 가능
- 완료 여부는 챕터 화면에 돌아올 때 확인

---

## 현재 상태

| 항목 | 현재 상태 |
|------|----------|
| Docker 파일 | 없음 (신규 작성 필요) |
| 배포 환경 | AWS (Azure → AWS 이전 예정) |
| boto3 | requirements.txt에 이미 포함 |
| AWS_REGION / 키 | config.py에 이미 설정됨 |
| SQS / ECS 코드 | 없음 |
| 작업 상태 테이블 | `GenDocs_Queue` 신규 설계 (아래 참고) |

---

## Step 1 — DB: GenDocs_Queue 테이블 생성

> **가장 먼저 해야 하는 작업.** API, 워커, 프론트 모두 이 테이블을 기준으로 통신한다.

### 테이블 설계 (`sdoc.GenDocs_Queue`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| GenDocUID | uuid **PK** | 문서 ID (재실행 시 upsert) |
| DocID | int4 | 문서 ID |
| GenDocNm | varchar | 작성문서명 |
| ProgressRate | varchar | 진행 정도 (미사용 예정) |
| JobStatusCD | varchar | **S** = 처리중, **E** = 완료 |
| ErrorCD | varchar | 오류코드 (정상 완료 시 null) |
| ErrorMessage | varchar | 오류 메시지 |
| StartDts | timestamp | 작업 시작 일시 |
| EndDts | timestamp | 작업 종료 일시 |

### 상태 판별 규칙

| JobStatusCD | ErrorCD | 의미 | 프론트 표시 |
|-------------|---------|------|------------|
| 없음 (row 없음) | - | 아직 실행 안 됨 | 버튼 활성 |
| `S` | - | 처리 중 | 버튼 비활성 + "생성 중..." 표시 |
| `E` | null | 정상 완료 | 버튼 활성 (완료 알람은 별도 알람으로 처리) |
| `E` | 값 있음 | 실패 | 버튼 활성 (오류 알람은 별도 알람으로 처리) |

> DOCX 결과 URL은 기존 `gendocs.createfileurl` 컬럼을 그대로 사용하므로 별도 컬럼 불필요.

---

## Step 2 — AWS 인프라 설정

> Step 3(워커 코드 작성)과 병렬로 진행 가능.

| 리소스 | 설정 요점 |
|--------|-----------|
| **SQS Queue** | Standard Queue, ap-northeast-2, Visibility Timeout 15분 이상 |
| **ECR Repository** | 워커 Docker 이미지 저장소 |
| **ECS Fargate 클러스터** | Fargate launch type |
| **IAM Task Role** | SQS ReceiveMessage/DeleteMessage, ECR pull, Secrets Manager read |
| **CloudWatch Log Group** | 워커 로그 수집용 |

---

## Step 3 — 워커 코드 작성

> Step 2(AWS 인프라)와 병렬로 진행 가능.

SQS에서 메시지를 꺼내 문서 생성 3개 Phase를 실행하는 **독립 Python 프로세스**.

### 재사용할 기존 유틸

| 파일 | 재사용 함수 |
|------|------------|
| `utilsPrj/chapter_making.py` | `replace_doc()`, 큐 로그 함수들 |
| `utilsPrj/html_to_docx.py` | `html_to_docx_merge()` |
| `utilsPrj/supabase_client.py` | `get_thread_supabase()` |
| `backend/app/config.py` | 환경변수 |

### 워커 처리 흐름

```
SQS long polling (20초 대기)
  → 메시지 수신 (gendocuid, chapters 목록, user_id)
  → GenDocs_Queue upsert: JobStatusCD='S'

  try:
    Phase 1: 챕터별 LLM 생성 (chapter_making.replace_doc 재사용)
    Phase 2: DOCX 병합 (html_to_docx.html_to_docx_merge 재사용)
    Phase 3: Supabase 업로드 → gendocs.createfileurl 업데이트
    → GenDocs_Queue upsert: JobStatusCD='E', EndDts=now()

  except:
    → GenDocs_Queue upsert: JobStatusCD='E', ErrorCD=..., ErrorMessage=..., EndDts=now()

  finally:
    genlocks 해제
    SQS 메시지 삭제
```

---

## Step 4 — Docker 이미지 + ECR 푸시

워커용 Dockerfile 작성 후 ECR에 이미지 업로드.

- 포함 대상: `backend/`, `utilsPrj/`, `worker/` 폴더
- 로컬 docker-compose로 환경변수 주입 및 동작 확인 후 ECR 푸시

---

## Step 5 — ECS Task Definition + Service + Auto Scaling

| 항목 | 설정 |
|------|------|
| Task 사양 | 2 vCPU / 8 GB (LLM 병렬 처리 고려) |
| 환경변수 | AWS Secrets Manager 참조 |
| ECS Service | minimum 0 / desired 1 |
| Scale Out 조건 | `SQS ApproximateNumberOfMessagesVisible ≥ 1` → 태스크 +1 |
| Scale In 조건 | 큐 메시지 0 → 쿨다운 후 태스크 0 |

---

## Step 6 — 백엔드 API 변경 (`gendocs.py`)

### 기존 엔드포인트 변경
- **AS-IS:** `POST /{gendocuid}/generate` → SSE StreamingResponse
- **TO-BE:** `POST /{gendocuid}/generate` → `{ gendocuid }` 즉시 반환
  1. genlocks 선점
  2. GenDocs_Queue upsert (JobStatusCD='S', StartDts=now())
  3. SQS 메시지 전송 (gendocuid, chapters, user_id)

### 신규 상태 조회 엔드포인트
- `GET /{gendocuid}/generate/status`
- GenDocs_Queue 조회 → `{ JobStatusCD, ErrorCD, ErrorMessage }` 반환

---

## Step 7 — 프론트엔드 변경 (`ReqChaptersReadPage.jsx`)

> **탭 구조 확인:** React Router + `navigate()` 방식으로 탭 전환 시 컴포넌트가 unmount/remount됨.
> 탭을 다시 클릭하는 순간 `useEffect`가 자동 실행되므로 **사용자가 새로고침하지 않아도 상태가 자동 반영**됨.

### 제거 대상
- 전체화면 로딩 오버레이 (`setLoading`, `chapProgress` 관련 UI 전체)
- SSE fetch reader loop (`handleDocRewrite` 내 스트리밍 코드)

### 변경 내용

**버튼 클릭 시 (`handleDocRewrite`):**

| | AS-IS | TO-BE |
|--|-------|-------|
| API 호출 | fetch + SSE reader loop (블로킹) | POST 후 즉시 반환 |
| 사용자 대기 | 진행률 오버레이로 화면 차단 | `message.success` 토스트 표시 후 자유롭게 다른 탭 이동 가능 |
| 진행 확인 | SSE 이벤트 수신 | 없음 (탭 재진입 시 자동 확인) |

**탭 재진입 시 (useEffect on mount — 자동 실행):**
- `GET /api/gendocs/{gendocuid}/generate/status` 자동 조회
- `JobStatusCD='S'` → 버튼 비활성 + "생성 중..." 표시, 페이지에 머무는 동안 폴링 유지
- `JobStatusCD='E'` (완료/실패 모두) → 버튼 활성 (완료·오류 메시지는 별도 알람으로 처리)
- row 없음 → 버튼 정상 활성

---

## Step 8 — E2E 테스트 및 배포

### 테스트 체크리스트
- [ ] 버튼 클릭 → 토스트 표시 후 다른 화면으로 이동 가능 확인 (오버레이 없음)
- [ ] 작업 enqueue → SQS 메시지 적재 확인
- [ ] 워커가 메시지 수신 후 처리 시작 확인
- [ ] 챕터 화면 재진입 시 "생성 중..." 상태 표시 확인
- [ ] 챕터 화면 재진입 시 완료 상태 표시 및 DOCX URL 접근 확인
- [ ] 워커 오류 시 챕터 화면 재진입 시 오류 배너 표시 확인
- [ ] 동시 요청 시 Fargate 태스크 Scale Out 확인
- [ ] 큐 비었을 때 태스크 Scale In 확인

---

## 작업 의존성 순서

```
Step 1  GenDocs_Queue 테이블 생성
    ↓
Step 2  AWS 인프라 설정  ←→  Step 3  워커 코드 작성  (병렬 가능)
    ↓                              ↓
Step 4  Dockerfile + ECR 푸시
    ↓
Step 5  ECS Task Definition + Auto Scaling
    ↓
Step 6  백엔드 API 변경
    ↓
Step 7  프론트엔드 변경
    ↓
Step 8  E2E 테스트 및 배포
```
