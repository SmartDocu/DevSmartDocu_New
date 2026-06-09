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

## Step 2 — AWS 인프라 설정 ✅ 완료

> Step 3(워커 코드 작성)과 병렬로 진행 가능.

### ① SQS 큐
| 항목 | 값 |
|------|-----|
| 큐 이름 | `smartdocu-gendocs-queue` |
| 유형 | Standard |
| Visibility Timeout | 900초 (15분) |
| **Queue URL** | `https://sqs.ap-northeast-2.amazonaws.com/189993504048/smartdocu-gendocs-queue` |

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

## Step 4 — Docker 이미지 + ECR 푸시 ✅ 완료

워커용 Dockerfile 작성 후 ECR에 이미지 업로드.

- 포함 대상: `backend/`, `utilsPrj/`, `worker/` 폴더
- 이미지: `189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-worker:latest`
- Digest: `sha256:a2a7712047669f20663e55e99cea4cb6904b9b49fd9a2bcda4dfcfb085d83a13`

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

## Step 8 — E2E 테스트 및 배포 ✅ 완료

### 테스트 체크리스트
- [x] 버튼 클릭 → 토스트 표시 후 다른 화면으로 이동 가능 확인 (오버레이 없음)
- [x] 작업 enqueue → SQS 메시지 적재 확인
- [x] 워커가 메시지 수신 후 처리 시작 확인
- [x] 챕터 화면 재진입 시 "생성 중..." 상태 표시 확인
- [x] 챕터 화면 재진입 시 완료 상태 표시 및 DOCX URL 접근 확인
- [x] 문서 전체 작성 (Phase 1 LLM → Phase 2 DOCX 병합 → Phase 3 Storage 업로드) 정상 동작 확인
- [ ] 워커 오류 시 챕터 화면 재진입 시 오류 배너 표시 확인
- [ ] 동시 요청 시 Fargate 태스크 Scale Out 확인
- [ ] 큐 비었을 때 태스크 Scale In 확인

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
