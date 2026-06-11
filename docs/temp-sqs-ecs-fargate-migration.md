# Write All Chapters + Rewrite Chapter — SQS + ECS Fargate 전환 계획

## 배경

**1차:** [Write All Chapters] 기능을 SSE → SQS 비동기로 전환 ✅ 완료  
**2차:** [Rewrite Chapter] 기능도 SSE → SQS 비동기로 전환 ✅ 완료 (E2E 테스트 포함)

```
[AS-IS]
브라우저 → POST /api/gendocs/{id}/generate          → FastAPI (SSE 스트리밍, 전체 문서)
브라우저 → POST /api/gendocs/genchapters/{id}/rewrite → FastAPI (SSE 스트리밍, 단일 챕터)

[TO-BE]
브라우저 → POST /api/gendocs/{id}/generate           → FastAPI (즉시 반환) → SQS doc-queue
브라우저 → POST /api/gendocs/genchapters/{id}/rewrite → FastAPI (즉시 반환) → SQS chapter-queue

SQS doc-queue     → Worker Thread 1 → Phase 1(LLM) + Phase 2(DOCX 병합) + Phase 3(업로드)
SQS chapter-queue → Worker Thread 2 → 템플릿 처리 + LLM 생성 (단일 챕터)

브라우저(화면 재진입 시)
  → GET /api/gendocs/{id}/generate/status            조회 (gendocs_realtimes)
  → GET /api/gendocs/genchapters/{id}/rewrite/status 조회 (genchapters_realtimes)
```

**UX 핵심 변경 (공통):**
- 진행률 창(로딩 오버레이) **완전 제거**
- 버튼 클릭 후 화면 차단 없음 → 사용자가 다른 작업 가능
- 완료 여부는 화면 재진입 시 자동 확인 (5초 폴링)

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| Docker 파일 | ✅ 완료 (`worker/Dockerfile`) |
| 배포 환경 | ✅ AWS ECS Fargate |
| SQS doc-queue | ✅ `smartdocu-gendocs-queue` |
| SQS chapter-queue | ✅ `smartdocu-genchapters-queue` (2차 추가) |
| Worker | ✅ 1개 프로세스, 2개 스레드 (doc + chapter) |
| 작업 상태 테이블 (문서) | ✅ `sdoc.gendocs_realtimes` (구 `gendocs_queue`) |
| 작업 상태 테이블 (챕터) | ✅ `sdoc.genchapters_realtimes` (2차 추가) |

---

## Step 1 — DB: 작업 상태 테이블 생성 ✅ 완료

### 1-A. `sdoc.gendocs_realtimes` (문서 전체 작성 상태)

> 구 테이블명 `gendocs_queue` → `gendocs_realtimes` 로 변경됨

| 컬럼 | 타입 | 설명 |
|------|------|------|
| GenDocUID | uuid **PK** | 작성문서 ID (재실행 시 upsert) |
| DocID | int4 | 문서 ID |
| GenDocNm | varchar | 작성문서명 |
| JobStatusCD | varchar | **S** = 처리중, **E** = 완료/오류 |
| ErrorCD | varchar | 오류코드 (정상 완료 시 null) |
| ErrorMessage | varchar | 오류 메시지 |
| StartDts | timestamp | 작업 시작 일시 |
| EndDts | timestamp | 작업 종료 일시 |
| Creator | uuid | 작업 요청 사용자 |

### 1-B. `sdoc.genchapters_realtimes` (단일 챕터 재작성 상태)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| GenChapterUID | uuid **PK** | 작성챕터 ID (재실행 시 upsert) |
| DocID | int4 | 문서 ID |
| ChapterUID | uuid **NOT NULL** | 챕터 ID |
| JobStatusCD | varchar | **S** = 처리중, **E** = 완료/오류 |
| ErrorCD | varchar | 오류코드 |
| ErrorMessage | varchar | 오류 메시지 |
| StartDts | timestamp | 작업 시작 일시 |
| EndDts | timestamp | 작업 종료 일시 |
| Creator | uuid | 작업 요청 사용자 |

### 공통 상태 판별 규칙

| JobStatusCD | ErrorCD | 의미 | 프론트 표시 |
|-------------|---------|------|------------|
| 없음 (row 없음) | - | 아직 실행 안 됨 | 버튼 활성 |
| `S` | - | 처리 중 | 버튼 비활성 + "작성 중..." 표시, 5초 폴링 |
| `E` | null | 정상 완료 | 버튼 활성, 데이터 자동 갱신 |
| `E` | 값 있음 | 실패 | 버튼 활성, 오류 메시지 표시 |
| `S` 30분 초과 | - | CRASH | 자동으로 `E`+`CRASH` 처리, 잠금 해제 |

---

## Step 2 — AWS 인프라 설정 ✅ 완료

### ① SQS 큐 — 문서 전체 작성
| 항목 | 값 |
|------|-----|
| 큐 이름 | `smartdocu-gendocs-queue` |
| 유형 | Standard |
| Visibility Timeout | 900초 (15분) |
| **Queue URL** | `https://sqs.ap-northeast-2.amazonaws.com/189993504048/smartdocu-gendocs-queue` |

### ① SQS 큐 — 단일 챕터 재작성 (2차 추가)
| 항목 | 값 |
|------|-----|
| 큐 이름 | `smartdocu-genchapters-queue` |
| 유형 | Standard |
| Visibility Timeout | 900초 (15분) |
| **Queue URL** | `https://sqs.ap-northeast-2.amazonaws.com/189993504048/smartdocu-genchapters-queue` |

### ② ECR 리포지토리
| 항목 | 값 |
|------|-----|
| 리포지토리 이름 | `smartdocu-worker` |
| 표시 여부 | 프라이빗 |
| **Repository URI** | `189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker` |

### ③ IAM Task Role
| 항목 | 값 |
|------|-----|
| 역할 이름 | `smartdocu-worker-task-role` |
| 신뢰 엔터티 | Elastic Container Service Task |
| 연결 정책 | AmazonSQSFullAccess, AmazonEC2ContainerRegistryReadOnly, SecretsManagerReadWrite |
| **Role ARN** | `arn:aws:iam::189993504048:role/smartdocu-worker-task-role` |

### ④ IAM Task Execution Role (Step 5에서 추가 생성)
| 항목 | 값 |
|------|-----|
| 역할 이름 | `ecsTaskExecutionRole` |
| 연결 정책 | AmazonECSTaskExecutionRolePolicy |

### ⑤ ECS Fargate 클러스터
| 항목 | 값 |
|------|-----|
| 클러스터 이름 | `smartdocu-cluster` |
| 인프라 | AWS Fargate (서버리스) |

### ⑥ CloudWatch 로그 그룹
| 항목 | 값 |
|------|-----|
| 로그 그룹 이름 | `/ecs/smartdocu-worker` |
| 보존 기간 | 30일 |
| **ARN** | `arn:aws:logs:ap-northeast-2:189993504048:log-group:smartdocu-worker:*` |

> **참고:** Task Definition(Step 5)에서 `awslogs-group`은 `smartdocu-worker`로 설정됨 (`awslogs-create-group: true`로 자동 생성).

---

## Step 3 — 워커 코드 작성 ✅ 완료

`worker/main.py` — 1개 프로세스, 큐별 스레드로 동작.

### 핸들러 구조

| 스레드 | 큐 | 핸들러 함수 | 처리 내용 |
|--------|-----|------------|----------|
| Thread 1 | `smartdocu-gendocs-queue` | `process_message()` | Phase 1(LLM) + Phase 2(DOCX 병합) + Phase 3(Storage 업로드) |
| Thread 2 | `smartdocu-genchapters-queue` | `process_chapter_message()` | 템플릿 처리 + LLM 생성 (단일 챕터) |

### 문서 전체 작성 흐름 (`process_message`)

```
SQS long polling (20초 대기)
  → 메시지 수신 (gendocuid, results[], user_id, ...)
  → gendocs_realtimes upsert: JobStatusCD='S'
  try:
    Phase 1: 챕터별 LLM 생성 (replace_doc 재사용)
    Phase 2: DOCX 병합 (html_to_docx_merge 재사용)
    Phase 3: Supabase Storage 업로드 → gendocs.createfileurl 업데이트
    → gendocs_realtimes upsert: JobStatusCD='E'
  except:
    → gendocs_realtimes upsert: JobStatusCD='E', ErrorCD='ERR'
  finally:
    genlocks(doclocked) 해제 / SQS 메시지 삭제
```

### 단일 챕터 재작성 흐름 (`process_chapter_message`)

```
SQS long polling (20초 대기)
  → 메시지 수신 (genchapteruid, chapteruid, gendocuid, ...)
  → genchapters_realtimes upsert: JobStatusCD='S'
  try:
    템플릿 처리 → flattexttemplate 저장 → genobjects 갱신
    replace_doc(genChapterDirectYn=True, divide='Chapter') — LLM 생성
    gendoc_genchapters 이력 기록
    → genchapters_realtimes upsert: JobStatusCD='E'
  except:
    → genchapters_realtimes upsert: JobStatusCD='E', ErrorCD='ERR'
  finally:
    genlocks(chapterlocked) 해제 / SQS 메시지 삭제
```

### 추후 분리 포인트

```
현재: 1 ECS Service (2 threads: doc + chapter)
미래: 2 ECS Service
  - smartdocu-doc-worker-service     (doc thread only)
  - smartdocu-chapter-worker-service (chapter thread only)
  분리 방법: 환경변수 WORKER_QUEUES=doc 또는 chapter 로 활성 큐 선택
```

---

## Step 4 — Docker 이미지 + ECR 푸시 ✅ 완료

워커용 Dockerfile — `worker/Dockerfile`

- 포함 대상: `requirements.txt`(루트), `backend/`, `utilsPrj/`, `worker/`, `static/`
- **주의:** `requirements.txt`는 루트에 위치 (`backend/requirements.txt` 아님)
- 이미지: `189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest`

### ECR 재푸시 명령어 (이미지 업데이트 시)
```bash
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com
docker build -f worker/Dockerfile -t smartdocu-worker .
docker tag smartdocu-worker:latest 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest
docker push 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest
```

---

## Step 5 — ECS Task Definition + Service + Auto Scaling ✅ 완료

### Task Definition
| 항목 | 실제 값 |
|------|---------|
| Task Definition 이름 | `smartdocu-worker` (revision 1) |
| 시작 유형 | AWS Fargate |
| CPU / 메모리 | 2 vCPU / 8 GB |
| Task Role | `smartdocu-worker-task-role` |
| Task Execution Role | `ecsTaskExecutionRole` |
| 컨테이너 이름 | `smartdocu-worker` |
| 이미지 URI | `189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest` |
| 로그 그룹 | `smartdocu-worker` |
| 로그 스트림 prefix | `ecs` |
| 로그 리전 | `ap-northeast-2` |

### ECS Service
| 항목 | 실제 값 |
|------|---------|
| 서비스 이름 | `smartdocu-worker-service` |
| 클러스터 | `smartdocu-cluster` |
| 원하는 태스크 수 | 1 |
| VPC | `vpc-041f22aeb124f2e1f` (기본 VPC) |
| 서브넷 | ap-northeast-2a/b/c/d 전체 |
| 보안 그룹 | `sg-0d5b18bffb219b178` (default) |
| 퍼블릭 IP | 켜짐 |

### Auto Scaling
| 항목 | 실제 값 |
|------|---------|
| 최소 태스크 | 0 |
| 최대 태스크 | 5 |
| Scale Out 정책 | `scaleout-policy` — 경보: `smartdocu-worker-scaleout` (ApproximateNumberOfMessagesVisible ≥ 1) → 태스크 +1 |
| Scale In 정책 | `scalein-policy` — 경보: `smartdocu-worker-scalein` (ApproximateNumberOfMessagesVisible < 1) → 태스크 -1 |

### 스케일링 동작 요약 (보고용)

**Worker 사양 (1개 기준)**
| 항목 | 값 |
|------|-----|
| CPU | 2 vCPU |
| 메모리 | 8 GB |
| 처리 방식 | SQS 메시지 1건씩 순차 처리 (Long Polling 20초) |
| 최대 처리 시간 | 15분 (Visibility Timeout 900초) |

**Auto Scaling 규칙**
| 조건 | 동작 |
|------|------|
| SQS 메시지 **1개 이상** 감지 | Worker **+1** 추가 (Scale Out) |
| SQS 메시지 **0개** 감지 | Worker **-1** 제거 (Scale In) |
| 최솟값 | Worker **0개** (메시지 없으면 비용 없음) |
| 최댓값 | Worker **5개** (동시 5건까지 병렬 처리) |

**처리 능력**
| 항목 | 값 |
|------|-----|
| 동시 처리 가능 문서 | 최대 **5건** |
| 대기 중 메시지가 있으면 | 메시지 수에 비례해 Worker 자동 증가 |
| 작업 완료 후 유휴 상태 | Worker 자동 0개로 감소 → **유휴 비용 없음** |

**SQS 큐 설정**
| 항목 | 값 |
|------|-----|
| 큐 유형 | Standard (순서 보장 없음, 최소 1회 전달 보장) |
| Visibility Timeout | **900초 (15분)** — Worker 처리 중 다른 Worker가 같은 메시지를 가져가지 않도록 잠금 |

> **핵심:** 평소엔 Worker 0개 → 요청 들어오면 자동 생성 → 완료 후 자동 종료. 최대 5개 문서를 동시에 병렬 생성 가능.
> 수정 요청 시 위 표의 수치(최대 태스크 수, Visibility Timeout, Scale Out/In 임계값)를 기준으로 변경 범위를 협의할 것.

---

## Step 6 — 백엔드 API 변경 (`gendocs.py`) ✅ 완료

### 문서 전체 작성
| | AS-IS | TO-BE |
|--|-------|-------|
| 엔드포인트 | `POST /{gendocuid}/generate` | 동일 |
| 응답 | SSE StreamingResponse | `{ gendocuid }` 즉시 반환 |
| 처리 | FastAPI 내에서 직접 실행 | genlocks 선점 → gendocs_realtimes('S') → SQS 전송 |
| 상태조회 | 없음 | `GET /{gendocuid}/generate/status` 신규 |

### 단일 챕터 재작성 (2차 변경)
| | AS-IS | TO-BE |
|--|-------|-------|
| 엔드포인트 | `POST /genchapters/{id}/rewrite` | 동일 |
| 응답 | SSE StreamingResponse | `{ genchapteruid }` 즉시 반환 |
| 처리 | FastAPI 내에서 직접 실행 | genlocks 선점 → genchapters_realtimes('S') → SQS 전송 |
| 상태조회 | 없음 | `GET /genchapters/{id}/rewrite/status` 신규 |

### 환경변수 추가
| 변수 | 값 |
|------|-----|
| `SQS_QUEUE_URL` | `https://sqs.ap-northeast-2.amazonaws.com/189993504048/smartdocu-gendocs-queue` |
| `SQS_CHAPTER_QUEUE_URL` | `https://sqs.ap-northeast-2.amazonaws.com/189993504048/smartdocu-genchapters-queue` |

---

## Step 7 — 프론트엔드 변경 (`ReqChaptersReadPage.jsx`) ✅ 완료

> **탭 구조:** React Router + `navigate()` 방식으로 탭 전환 시 컴포넌트 unmount/remount.
> 탭 재진입 시 `useEffect`가 자동 실행 → 상태 자동 반영.

### 공통 변경사항
- 전체화면 로딩 오버레이 완전 제거 (문서/챕터 모두)
- SSE fetch reader loop 제거 (문서/챕터 모두)

### 문서 전체 작성 (`handleDocRewrite`)
- 클릭 → POST 즉시 반환 → `generating=true` + 성공 토스트
- 탭 재진입 시 `GET /generate/status` 자동 조회 → `S`면 폴링 시작
- 5초 폴링 → `S` 아니면 버튼 활성 + 챕터 목록 refetch

### 단일 챕터 재작성 (`handleRewrite`) — 2차 변경
- 클릭 → POST 즉시 반환 → `rewriting=true` + 성공 토스트
- 챕터 선택 시 `GET /genchapters/{id}/rewrite/status` 자동 조회 → `S`면 폴링 시작
- 5초 폴링 → `S` 아니면 버튼 활성 + 챕터 콘텐츠 자동 갱신

### 다국어 신규 키 (등록 필요)
| 키 | 한국어 |
|----|--------|
| `msg.doc.writing` | 문서 작성 중... |
| `msg.doc.write.started` | 문서 작성 요청이 접수되었습니다. |
| `msg.chapter.writing` | 챕터 작성 중... |
| `msg.chapter.write.started` | 챕터 작성 요청이 접수되었습니다. |
| `msg.chapter.already.writing` | 이 문서 혹은 해당 챕터가 이미 작성 중입니다. |

---

## Step 8 — E2E 테스트 및 배포

### 문서 전체 작성 (1차) 테스트 체크리스트
- [x] 버튼 클릭 → 토스트 표시 후 다른 화면으로 이동 가능 확인 (오버레이 없음)
- [x] 작업 enqueue → SQS 메시지 적재 확인
- [x] 워커가 메시지 수신 후 처리 시작 확인
- [x] 챕터 화면 재진입 시 "생성 중..." 상태 표시 확인
- [x] 챕터 화면 재진입 시 완료 상태 표시 및 DOCX URL 접근 확인
- [x] 문서 전체 작성 (Phase 1 LLM → Phase 2 DOCX 병합 → Phase 3 Storage 업로드) 정상 동작 확인
- [ ] 워커 오류 시 오류 표시 확인
- [ ] 동시 요청 시 Fargate 태스크 Scale Out 확인
- [ ] 큐 비었을 때 태스크 Scale In 확인

### 단일 챕터 재작성 (2차) 테스트 체크리스트
- [x] 버튼 클릭 → 토스트 표시 후 버튼 비활성 확인 (오버레이 없음)
- [x] SQS chapter-queue 메시지 적재 확인
- [x] 워커 Thread 2가 메시지 수신 후 처리 시작 확인
- [x] 챕터 재선택 시 "챕터 작성 중..." 상태 자동 표시 확인
- [x] 완료 후 챕터 콘텐츠 자동 갱신 확인
- [x] 이미 작성 중인 챕터 재클릭 시 경고 토스트 확인

---

## 워커 코드 수정 후 재배포 절차

`worker/` 또는 `utilsPrj/`, `backend/` 코드를 수정했을 때 ECS Fargate 워커에 반영하려면 아래 순서를 반복한다.

### 1단계 — ECR 로그인 (세션당 1회)
```powershell
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com
```

### 2단계 — Docker 빌드 + 태그 + 푸시
```powershell
docker build -f worker/Dockerfile -t smartdocu-worker .
docker tag smartdocu-worker:latest 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest
docker push 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest
```

### 3단계 — ECS 서비스 업데이트
AWS 콘솔 → ECS → 클러스터 `smartdocu-cluster` → 서비스 `smartdocu-worker-service`
→ **서비스 업데이트** 버튼 → **새 배포 강제 실행** 체크 → **업데이트**

> **참고:** `backend/app/routers/gendocs.py` 등 FastAPI 코드만 수정한 경우 백엔드 서버 재시작만으로 충분하며 Docker 빌드는 불필요.

---

## 작업 의존성 순서

```
[1차 — 문서 전체 작성] ✅ 완료
Step 1  gendocs_realtimes 테이블 생성
    ↓
Step 2  AWS 인프라 (SQS doc-queue, ECR, IAM, ECS 클러스터)
    ↓
Step 3  워커 코드 작성 (process_message)
    ↓
Step 4  Dockerfile + ECR 푸시
    ↓
Step 5  ECS Task Definition + Service + Auto Scaling
    ↓
Step 6  백엔드 API 변경 (generate → SQS)
    ↓
Step 7  프론트엔드 변경 (SSE 제거, 폴링)
    ↓
Step 8  E2E 테스트 ✅

[2차 — 단일 챕터 재작성] ✅ 완료
Step 1  genchapters_realtimes 테이블 생성
    ↓
Step 2  AWS 인프라 (SQS chapter-queue 추가)
    ↓
Step 3  워커 코드 추가 (process_chapter_message + 멀티 스레드 main)
    ↓
Step 4  Dockerfile 수정 + ECR 재푸시
    ↓
Step 6  백엔드 API 변경 (rewrite → SQS + status 엔드포인트)
    ↓
Step 7  프론트엔드 변경 (SSE 제거, 폴링)
    ↓
Step 8  E2E 테스트 (진행 중)
```
