# 메인 앱(FastAPI+React) AWS 배포 현황

워커(`worker/`)는 이전부터 AWS ECS Fargate(`smartdocu-cluster`)에서 운영 중이었고, 메인 앱(루트 `Dockerfile`, FastAPI + React 통합 이미지)은 2026-08-13에 **최초로 AWS에 배포**되었다. 그 전까지는 어디에도 배포된 적 없었음(로컬/Azure 웹앱 URL만 CORS에 남아 있던 상태).

**2026-09-02 정정**: 최초 배포 당시 서비스명은 `smartdocu-backend-service`/ALB `smartdocu-backend-alb`였으나, 이후 어느 시점에 `d2doc-service`/`d2doc-alb`로 새로 만들어 옮겨갔고 옛 리소스는 그대로 방치되어 있었다(이 문서가 최신화 안 된 채로 남아있던 원인). 아래 내용은 실제 운영 중인 `d2doc-service` 기준으로 갱신함.

**옛 리소스(`smartdocu-backend-*`) 처리 필요** — `smartdocu-backend-service`는 desired=0(실행 태스크 없음)인데, `smartdocu-backend-alb`는 `state: active`로 여전히 켜져 있어 트래픽 없이도 계속 과금 중이다. 정리(ALB/서비스/타겟그룹/ECR 리포지토리 삭제)는 사용자 확인 후 별도로 진행할 것 — 이 문서 갱신 시점엔 조사만 하고 삭제는 하지 않음.

---

## 현재 접속 주소

```
http://d2doc-alb-2141263733.ap-northeast-2.elb.amazonaws.com
```

도메인 미연결 — ALB 기본 DNS로만 접속 가능. HTTP만 지원(HTTPS 없음).

---

## 생성된 AWS 리소스

| 항목 | 값 |
|---|---|
| ECR 리포지토리 | `189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/d2doc-service` |
| ECS 클러스터 | `smartdocu-cluster` (워커와 공유) |
| ECS 서비스 | `d2doc-service` |
| ECS 태스크 정의 | `d2doc-service` (family) |
| 태스크 역할 (IAM) | `smartdocu-backend-task-role` — SecretsManagerReadWrite, AmazonSQSFullAccess, AmazonEC2ContainerRegistryReadOnly (최초 배포 때 만든 이름 그대로 재사용 중) |
| 실행 역할 (IAM) | `smartdocu-backend-exec-role` — AmazonECSTaskExecutionRolePolicy, SecretsManagerReadWrite (마찬가지로 이름만 구버전) |
| VPC | 디폴트 VPC `vpc-041f22aeb124f2e1f`, 퍼블릭 서브넷 4개 (워커와 동일), NAT 게이트웨이 없음 → 태스크는 `assignPublicIp=ENABLED` |
| ALB | `d2doc-alb` |
| 타겟그룹 | `d2doc-alb-tg` — HTTP:8000, 헬스체크 `/health` |
| 리스너 | HTTP:80 → 타겟그룹 forward |
| CloudWatch 로그 그룹 | `d2doc-service` |
| Secrets Manager | `smartdocu/backend/env` — CLAUDE_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY, ENCRYPTION_KEY, EMAIL_HOST_PASSWORD, NAVER_ACCESS_KEY_ID, NAVER_SECRET_KEY, PORTONE_STORE_ID, PORTONE_CHANNEL_KEY, PORTONE_API_SECRET, PORTONE_WEBHOOK_SECRET, BILLING_CRON_SECRET (시크릿 이름 자체는 최초 배포 때 이름 그대로 재사용 중) |

민감하지 않은 값(SUPABASE_URL, SUPABASE_SCHEMA, SQS 큐 URL 등)은 태스크 정의에 평문 `environment`로 직접 넣음. 워커와 달리 이번엔 시크릿을 Secrets Manager로 분리했다(워커 태스크 정의는 여전히 평문 방식 — 개선 여지 있음).

2026-08-14에 `BASE_URL` 평문 env를 추가함. 비밀번호 재설정/초대 이메일 링크가 이 값을 기준으로 생성된다(`backend/app/config.py`의 `settings.BASE_URL`). 현재값: `http://d2doc-alb-2141263733.ap-northeast-2.elb.amazonaws.com`. 도메인 연결 시(후속 작업 #1) 이 값도 함께 갱신할 것.

**미해결 버그(2026-09-02 발견)**: `backend/app/config.py`의 `CORS_ORIGINS`에 옛 `smartdocu-backend-alb` 주소만 남아있고 현재 실제 운영 주소인 `d2doc-alb`가 빠져있음. 프론트가 API와 같은 오리진(같은 ALB)에서 서빙되는 구조라 대부분의 요청엔 영향 없지만, 정정 필요 — 후속 작업으로 기록.

`smartdocu-app` IAM 사용자에 배포에 필요한 커스텀 정책(`smartdocu-deploy-policy`) + `ElasticLoadBalancingFullAccess`를 추가로 붙여야 했음(원래 권한이 ECR/ECS 정도로 좁았음).

---

## 재배포 방법 (코드 수정 후)

```powershell
# 프로젝트 루트에서
docker build -f Dockerfile -t d2doc-service:latest `
  --build-arg VITE_SUPABASE_URL=<frontend/.env 값> `
  --build-arg VITE_SUPABASE_ANON_KEY=<frontend/.env 값> .

aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com
docker tag d2doc-service:latest 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/d2doc-service:latest
docker push 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/d2doc-service:latest

aws ecs update-service --cluster smartdocu-cluster --service d2doc-service --force-new-deployment --region ap-northeast-2
```

환경변수/시크릿 값을 바꿔야 하면: `smartdocu/backend/env` 시크릿(콘솔) 또는 태스크 정의 자체를 새 리비전으로 등록 후 서비스 업데이트.

---

## 배포 중 겪은 문제 (재발 방지용 기록)

1. **`.dockerignore`가 없어서 `.env`가 이미지에 그대로 들어갈 뻔함** — 추가함. `*.txt` 패턴이 `requirements.txt`까지 걸러버려서 첫 빌드가 실패했음 (`!requirements.txt` 예외 추가로 해결).
2. **로컬 디스크 풀로 Docker 빌드/데몬 자체가 죽음** (C: 드라이브 99% 사용, pip install 중 I/O 에러 → 데몬 응답 불능) — 디스크 정리 + PC 재부팅으로 해결. 빌드 전에 디스크 여유공간 확인 권장.
3. **ELB 리소스 생성 시 예상 못 한 EC2 권한 필요** (`ec2:DescribeInternetGateways` 등) — `ElasticLoadBalancingFullAccess`를 추가로 붙여서 해결.
4. **태스크 배치 실패: `logs:CreateLogGroup` 권한 없음** — `AmazonECSTaskExecutionRolePolicy`엔 `CreateLogStream`/`PutLogEvents`만 있고 `CreateLogGroup`은 없음. 로그 그룹을 미리 `aws logs create-log-group`으로 만들어두는 방식으로 해결.
5. Git Bash(MSYS) 환경에서 `aws` CLI에 `/health` 같은 경로를 넘기면 Windows 경로로 자동 변환되어 깨짐 — `MSYS_NO_PATHCONV=1` 접두사로 해결.

---

## 후속 작업 (미완료)

- [x] ~~`creditbuckets_daily_batch.sql` 재실행 필요(Supabase SQL 에디터)~~ — 사용자가 2026-08-31 SQL 에디터에서 실행 완료 확인. `sdoc.fn_process_creditbuckets_daily()`의 Ba 크레딧 갱신(Part B) 대상 조회에 `account_billing`에 등록된 계정은 건너뛰는 `NOT EXISTS` 조건이 반영됨(안 그러면 EventBridge(`run-billing-cycle`)를 켰을 때 실제 청구 성공 후 Python이 갱신한 Ba 크레딧을 이 배치가 결제 여부와 무관하게 또 갱신해 이중 갱신되는 문제). **검증**: 사용자가 배포된 함수 소스(`pg_get_functiondef` 결과로 추정)를 그대로 붙여넣어 확인해줌 — 로컬 `creditbuckets_daily_batch.sql`과 한 글자도 다르지 않고 일치, 위 `NOT EXISTS` 조건 포함해 정확히 반영됨. 다음 EventBridge 재청구(첫 대상: `d022f771` 계정 2026-09-26, `0aeded61` 계정 2026-09-20) 시점에 실제 이중 갱신이 안 일어나는지 최종 확인하면 완전히 끝남.
- [x] ~~Ch/In 서비스는 결제 실패 시 접근 차단 로직이 없음~~ — 2026-08-31 완료, AWS(`d2doc-service`)까지 배포 완료. 기록 당시 "Ch/In은 실제 기능 라우터가 없다"고 판단했던 것 자체가 오류였음(정정: `d2chat/routes.py`·`d2insight/chat/router.py`가 루트 레벨 별도 패키지로 존재하고 `backend/app/routers/__init__.py`에서 그대로 include되는 실제 라우터임 — `backend/app/routers/` 폴더 안만 찾아서 놓쳤던 것). `backend/app/dependencies.py`의 `require_doc_read`/`require_doc_write`를 `_require_service_permission(servicecd, need)` 팩토리로 일반화하고 `require_chat_read`/`write`(Ch), `require_insight_read`/`write`(In)를 추가, d2chat 19개·d2insight 31개 엔드포인트(POST/DELETE→write, GET→read)에 적용 완료. 내부 스케줄러 전용(`/scheduled/run`)·공개 참조 데이터(`/catalog`, `/health`, `/questions`)는 원래부터 토큰이 없어 대상에서 제외. 로컬 `docker run` 스모크테스트 → ECR 푸시(이번엔 Auto Mode 분류기에 안 막힘) → `d2doc-service` force-new-deployment(rolloutState COMPLETED) → 프로덕션 ALB(`d2doc-alb`)에서 `/health` 200, `/api/d2chat/history`·`/api/d2insight/history/{user_id}` 무인증 401 확인까지 전부 완료.
- [x] ~~`BILLING_CRON_SECRET`을 Secrets Manager(`smartdocu/backend/env`)에 추가 + 태스크 정의 secrets 매핑 등록~~ — 2026-08-27 완료. 사용자가 AWS 콘솔에서 시크릿 키 추가, 태스크 정의(`d2doc-service`)에 secrets 매핑 등록은 이어서 진행(리비전 4는 ARN 포맷 실수로 태스크 기동 실패 — `unexpected ARN format with parameters` — 살아있던 기존 리비전3가 계속 트래픽 처리해서 실서비스 영향 없었음; 리비전 5로 정상 ARN 재등록 후 배포 성공). 프로덕션에서 잘못된 시크릿→403, 정상 시크릿→200(처리 대상 0건, 안전) 확인 완료.
  - **EventBridge Scheduler는 2026-08-27에 만들어뒀지만 DISABLED 상태** — `d2doc-billing-daily-cron`(매일 00:00 KST) → Lambda `d2doc-billing-cron` → `run-billing-cycle` 호출 구조(ALB가 HTTP만 지원해서 API destination 대신 Lambda 경유). **ENABLED 전환은 사용자의 명시적 요청 후에만** — 절대 먼저 켜지 말 것. 상세 리소스 목록/켜는 명령어는 메모리 `portone-integration-progress` 참고.

- [ ] **도메인 연결 + ACM 인증서 + HTTPS 전환** — 도메인 미정. 정해지면 Route53 + ACM 발급 + ALB 리스너 443 추가, `CORS_ORIGINS`/Supabase 리다이렉트 URL 갱신 필요
- [x] ~~`backend/app/config.py`의 `CORS_ORIGINS`에 현재 운영 주소(`d2doc-alb`) 추가~~ — 2026-09-02 완료. 옛 `smartdocu-backend-alb` 주소는 제거하고 현재 운영 주소(`http://d2doc-alb-2141263733.ap-northeast-2.elb.amazonaws.com`)로 교체, `d2doc-service` 재배포(rolloutState COMPLETED) + `/health` 200 확인까지 완료.
- [ ] **옛 리소스(`smartdocu-backend-*`) 정리** — `smartdocu-backend-alb`가 `state: active`로 켜진 채 방치돼 트래픽 없이 계속 과금 중(연결된 `smartdocu-backend-service`는 desired=0). ALB/서비스/타겟그룹(`smartdocu-backend-tg`)/ECR 리포지토리(`smartdocu-backend`) 삭제 필요. 2026-09-02 발견, **사용자가 2026-09-08에 직접 제거 예정** — 그 전에는 먼저 삭제하지 말 것.
- [x] ~~`worker/main.py`에 Audit Log(work_logs) "작성 완료" 기록 추가~~ — 2026-08-28 코드 반영 + 배포 완료.
  - 배경: `sdoc.work_logs`(감사 로그, append-only) 테이블에 일반 사용자의 문서/챕터/항목 작업을 기록하는 시스템을 구축함(`backend/app/main.py`의 ASGI 미들웨어 + 일부 라우터의 직접 `log_work_action()` 호출). 상세는 `utilsPrj/audit_log.py`(`log_work_action`, `snapshot_row`, `get_client_ip`) 참고.
  - 문제였던 것: `backend/app/routers/gendocs.py`의 비동기 SQS 엔드포인트 3개 — `POST /gendocs/genchapters/{id}/rewrite`(챕터 재작성), `POST /gendocs/{id}/generate`(문서 전체 작성), `POST /gendocs/{id}/combine`(챕터 조합) — 는 SQS에 메시지만 던지고 즉시 응답해서, API 요청 시점엔 "요청(`create_requested`)"만 남고 실제 "작성 완료" 기록이 없었음.
  - **코드 반영(2026-08-28)** — `worker/main.py`에 3곳 추가:
    - `_run_merge_and_upload()` 내부, `_update_queue(..., "E", ...)` 직후: DOCX 병합·업로드 성공 시 `log_work_action(actioncd="create", targettype="gendocs/generate" 또는 "gendocs/combine", targetid=gendocuid, ...)` 호출. `selected_chapters is not None`이면 combine, `None`이면(문서 전체 작성 fan-out 완료 후 호출) generate로 자동 판별.
    - `process_chapter_message()` 내부, `_update_chapter_queue(..., "E", ...)` 직후: `is_start_doc=False`(챕터 "단독" 재작성)일 때만 `log_work_action(actioncd="create", targettype="gendocs/genchapters/rewrite", targetid=genchapteruid, ...)` 호출. 문서 전체 작성의 fan-out 챕터(`is_start_doc=True`)는 여기서 안 남기고, 문서 전체가 끝나는 시점(`_run_merge_and_upload`)에서 `gendocs/generate`로 한 번만 남기게 해서 중복 방지.
    - 두 곳 다 `_run_merge_and_upload()`가 `tenantid` 파라미터를 새로 받도록 시그니처 변경(호출부 2곳도 함께 수정).
    - `detail`에 `gendocjobuid`/`genchapterjobuid`를 남겨서 기존 `create_requested` row와 매칭 가능.
  - **배포(2026-08-28)** — Docker 빌드 → ECR push → ECS `smartdocu-worker-service` 강제 재배포 완료. 태스크 정의가 `:latest` 태그(가변)를 참조해서, 다음 SQS 메시지 수신 시 워커가 스케일업될 때 새 이미지가 자동 적용됨(`desiredCount=0` 평시 대기 설계라 배포 시점엔 실행 중인 태스크가 없었음).
  - **라이브 검증 완료(2026-08-28)** — 실제 문서(`Test_문서` → 챕터 `Test_문서_챕터_3개`)를 API로 생성해 `POST /gendocs/{id}/generate` → SQS → AWS ECS 워커(`smartdocu-worker-service`, 스케일업 확인) 전체 파이프라인을 라이브로 돌려 확인. `gendocs_realtimes.jobstatuscd`가 `S`→`E`로 전이된 후 `sdoc.work_logs`에 `actioncd="create"`, `targettype="gendocs/generate"`, `after_json.createfileurl`(생성된 docx storage URL) 포함 row가 정상적으로 추가됨을 확인 — 기존 요청 시점의 `create_requested` row와 별개로 남는 것도 확인. 검증에 쓴 테스트 계정/문서/챕터/gendoc/로그 row는 전부 삭제 완료(로그 3종 테이블은 `audit_verify_test_cleanup.sql`로 트리거 일시 비활성화 후 정리 — append-only라 반드시 이 방식 사용).
- [ ] **Audit Log 보관기간(plan별) 실제 삭제/파기 배치 미구현** — 2026-08-28 사용자 확인 후 후속 작업으로 기록만 해둠(당장 착수 안 함).
  - 현재 상태: `config_plans`에 `configcd='audit_log_keep_days'`로 서비스(Do/Ch/In) × 플랜(Fr/Pr/Te=365일, En=1825일) 조합이 값으로만 등록돼 있음(2026-08-28 이전 작업). **이 값을 읽어서 실제로 오래된 로그를 지우거나 파기 처리하는 코드/배치는 어디에도 없음** — `audit_log_keep_days` 문자열로 코드 전체를 검색해도 매치 0건.
  - 대상 테이블: `sdoc.work_logs`(일반 사용자 작업 로그, `tenantid`+`servicecd` 보유 — plan별 보관기간을 그대로 적용할 대상), `sdoc.login_logs`(접속 로그, work_logs와 유사하게 적용 검토 필요). `sdoc.admin_action_logs`(시스템 관리자 로그)는 특정 테넌트/플랜에 속하지 않는 전사 로그라 이 plan별 정책 적용 대상인지부터 사용자 확인 필요. `sdoc.privacy_consent_logs`는 plan 무관 법정 고정 5년(1825일)으로 이미 별도 정책 확정됨(`audit_log_tables.sql` 45행 COMMENT 참고) — 여기엔 `config_plans` 값 적용 안 함.
  - 필요한 작업(향후 착수 시):
    1. 테넌트별 현재 플랜(servicecd별 productcd/plan)을 조회해 `config_plans.audit_log_keep_days`에서 보관일수를 가져오는 함수/쿼리 설계 — 테넌트가 서비스별로 플랜이 다를 수 있으므로 servicecd 단위로 판단 필요.
    2. 보관기간 초과 row 삭제(또는 별도 아카이브 테이블/S3로 이관 후 삭제) 배치 로직 작성 — append-only 트리거(`trg_work_logs_append_only` 등)가 `BEFORE UPDATE OR DELETE`에 걸려있어 **일반 삭제(DELETE)는 트리거에 막힘**. 배치 전용 경로(예: 트리거 함수 안에 "시스템 배치 계정만 예외 허용" 조건 추가, 또는 배치 실행 시에만 트리거 일시 비활성화하는 서비스 role 함수)를 별도로 설계해야 함 — 지금처럼 사람이 SQL 에디터에서 수동으로 트리거 껐다 켜는 방식은 정기 배치에 부적합.
    3. 스케줄 방식은 이미 구축된 정산 배치 패턴(76행 참고: EventBridge Scheduler → Lambda → 백엔드 엔드포인트 호출, 현재 billing용은 DISABLED 상태로 대기 중)을 그대로 재사용 가능 — 새 엔드포인트(예: `POST /admin/audit-logs/purge` 같은 배치 전용 API) + 그걸 부르는 EventBridge Scheduler + Lambda 조합으로 구현하는 게 기존 구조와 일관적임.
  - **사용자 지시(2026-08-28)**: 당장 만들지 말고 후속 작업으로만 기록. 착수 시점은 사용자가 별도로 지시.
- [x] ~~d2insight ↔ Azure SQL(`mcp-rtims.database.windows.net`) 네트워크 연결~~ — 사용자가 "샘플링이라 미연결이어도 정상 동작, 불필요"로 확정(2026-08-27). 다시 꺼내지 말 것.
- [x] ~~워커 서비스(`smartdocu-worker-service`) `desiredCount=0` 원인 확인~~ — 의도적인 설계. 평소 0으로 대기하다 SQS 메시지 수신 시 자동으로 스케일업되는 구조, 정상 동작 확인됨(2026-08-27).
- [x] ~~워커 태스크 정의도 메인 앱처럼 Secrets Manager 방식으로 시크릿 분리~~ — 2026-08-25 완료. `smartdocu-worker` 태스크 정의 리비전 4로 갱신, `CLAUDE_API_KEY`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_KEY`/`ENCRYPTION_KEY` 전부 `smartdocu/backend/env` 시크릿 참조로 전환.
- [x] ~~`.dockerignore`/`config.py`(CORS_ORIGINS, BASE_URL)/`auth.py`/`org.py`/`.env` 변경분 git 커밋~~ — 사용자가 "git은 수동으로 커밋 중"이라고 확인(2026-08-25), 이 프로젝트의 정상 워크플로우라 후속작업 대상 아님.
- [x] ~~하드코딩된 옛 Azure 주소(dev-smart-doc.azurewebsites.net) 정리~~ — 2026-08-14 완료. `auth.py`(비밀번호 재설정 링크), `org.py`(초대 링크)를 `settings.BASE_URL` 참조로 변경, `config.py` CORS_ORIGINS에서 azurewebsites.net 제거, ECS 태스크 정의(리비전 2)에 `BASE_URL` 추가 후 재배포·스모크테스트 완료. `frontend/src/pages/HomePage.jsx`의 `dev-rag-medicine.azurewebsites.net` 링크는 별개 외부 서비스라 이번 작업에서 제외
