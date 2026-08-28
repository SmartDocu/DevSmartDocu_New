# 메인 앱(FastAPI+React) AWS 배포 현황

워커(`worker/`)는 이전부터 AWS ECS Fargate(`smartdocu-cluster`)에서 운영 중이었고, 메인 앱(루트 `Dockerfile`, FastAPI + React 통합 이미지)은 2026-08-13에 **최초로 AWS에 배포**되었다. 그 전까지는 어디에도 배포된 적 없었음(로컬/Azure 웹앱 URL만 CORS에 남아 있던 상태).

---

## 현재 접속 주소

```
http://smartdocu-backend-alb-876682109.ap-northeast-2.elb.amazonaws.com
```

도메인 미연결 — ALB 기본 DNS로만 접속 가능. HTTP만 지원(HTTPS 없음).

---

## 생성된 AWS 리소스

| 항목 | 값 |
|---|---|
| ECR 리포지토리 | `189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-backend` |
| ECS 클러스터 | `smartdocu-cluster` (워커와 공유) |
| ECS 서비스 | `smartdocu-backend-service` |
| ECS 태스크 정의 | `smartdocu-backend` (family), cpu=1024 / memory=2048 |
| 태스크 역할 (IAM) | `smartdocu-backend-task-role` — SecretsManagerReadWrite, AmazonSQSFullAccess, AmazonEC2ContainerRegistryReadOnly |
| 실행 역할 (IAM) | `smartdocu-backend-exec-role` — AmazonECSTaskExecutionRolePolicy, SecretsManagerReadWrite |
| VPC | 디폴트 VPC `vpc-041f22aeb124f2e1f`, 퍼블릭 서브넷 4개 (워커와 동일), NAT 게이트웨이 없음 → 태스크는 `assignPublicIp=ENABLED` |
| 보안그룹 (ALB) | `sg-055256bc0667a43b6` — 인바운드 80 전체 허용 |
| 보안그룹 (태스크) | `sg-0752690b93855e164` — ALB SG로부터만 8000 인바운드 허용 |
| ALB | `smartdocu-backend-alb` |
| 타겟그룹 | `smartdocu-backend-tg` — HTTP:8000, 헬스체크 `/health` |
| 리스너 | HTTP:80 → 타겟그룹 forward |
| CloudWatch 로그 그룹 | `smartdocu-backend` (30일 보관) |
| Secrets Manager | `smartdocu/backend/env` — CLAUDE_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY(비어있음, 미설정), SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY, ENCRYPTION_KEY, EMAIL_HOST_PASSWORD, NAVER_ACCESS_KEY_ID, NAVER_SECRET_KEY |

민감하지 않은 값(SUPABASE_URL, SUPABASE_SCHEMA, SQS 큐 URL 등)은 태스크 정의에 평문 `environment`로 직접 넣음. 워커와 달리 이번엔 시크릿을 Secrets Manager로 분리했다(워커 태스크 정의는 여전히 평문 방식 — 개선 여지 있음).

2026-08-14에 `BASE_URL` 평문 env를 추가함(태스크 정의 리비전 2). 비밀번호 재설정/초대 이메일 링크가 이 값을 기준으로 생성된다(`backend/app/config.py`의 `settings.BASE_URL`). 현재값: `http://smartdocu-backend-alb-876682109.ap-northeast-2.elb.amazonaws.com`. 도메인 연결 시(후속 작업 #1) 이 값도 함께 갱신할 것.

`smartdocu-app` IAM 사용자에 배포에 필요한 커스텀 정책(`smartdocu-deploy-policy`) + `ElasticLoadBalancingFullAccess`를 추가로 붙여야 했음(원래 권한이 ECR/ECS 정도로 좁았음).

---

## 재배포 방법 (코드 수정 후)

```powershell
# 프로젝트 루트에서
docker build -f Dockerfile -t smartdocu-backend:latest `
  --build-arg VITE_SUPABASE_URL=<frontend/.env 값> `
  --build-arg VITE_SUPABASE_ANON_KEY=<frontend/.env 값> .

aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com
docker tag smartdocu-backend:latest 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-backend:latest
docker push 189993504048.dkr.ecr.ap-northeast-2.amazonaws.com/smartdocu-backend:latest

aws ecs update-service --cluster smartdocu-cluster --service smartdocu-backend-service --force-new-deployment --region ap-northeast-2
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

- [x] ~~`BILLING_CRON_SECRET`을 Secrets Manager(`smartdocu/backend/env`)에 추가 + 태스크 정의 secrets 매핑 등록~~ — 2026-08-27 완료. 사용자가 AWS 콘솔에서 시크릿 키 추가, 태스크 정의(`d2doc-service`)에 secrets 매핑 등록은 이어서 진행(리비전 4는 ARN 포맷 실수로 태스크 기동 실패 — `unexpected ARN format with parameters` — 살아있던 기존 리비전3가 계속 트래픽 처리해서 실서비스 영향 없었음; 리비전 5로 정상 ARN 재등록 후 배포 성공). 프로덕션에서 잘못된 시크릿→403, 정상 시크릿→200(처리 대상 0건, 안전) 확인 완료.
  - **EventBridge Scheduler는 2026-08-27에 만들어뒀지만 DISABLED 상태** — `d2doc-billing-daily-cron`(매일 00:00 KST) → Lambda `d2doc-billing-cron` → `run-billing-cycle` 호출 구조(ALB가 HTTP만 지원해서 API destination 대신 Lambda 경유). **ENABLED 전환은 사용자의 명시적 요청 후에만** — 절대 먼저 켜지 말 것. 상세 리소스 목록/켜는 명령어는 메모리 `portone-integration-progress` 참고.

- [ ] **도메인 연결 + ACM 인증서 + HTTPS 전환** — 도메인 미정. 정해지면 Route53 + ACM 발급 + ALB 리스너 443 추가, `CORS_ORIGINS`/Supabase 리다이렉트 URL 갱신 필요
- [x] ~~`worker/main.py`에 Audit Log(work_logs) "작성 완료" 기록 추가~~ — 2026-08-28 코드 반영 + 배포 완료.
  - 배경: `sdoc.work_logs`(감사 로그, append-only) 테이블에 일반 사용자의 문서/챕터/항목 작업을 기록하는 시스템을 구축함(`backend/app/main.py`의 ASGI 미들웨어 + 일부 라우터의 직접 `log_work_action()` 호출). 상세는 `utilsPrj/audit_log.py`(`log_work_action`, `snapshot_row`, `get_client_ip`) 참고.
  - 문제였던 것: `backend/app/routers/gendocs.py`의 비동기 SQS 엔드포인트 3개 — `POST /gendocs/genchapters/{id}/rewrite`(챕터 재작성), `POST /gendocs/{id}/generate`(문서 전체 작성), `POST /gendocs/{id}/combine`(챕터 조합) — 는 SQS에 메시지만 던지고 즉시 응답해서, API 요청 시점엔 "요청(`create_requested`)"만 남고 실제 "작성 완료" 기록이 없었음.
  - **코드 반영(2026-08-28)** — `worker/main.py`에 3곳 추가:
    - `_run_merge_and_upload()` 내부, `_update_queue(..., "E", ...)` 직후: DOCX 병합·업로드 성공 시 `log_work_action(actioncd="create", targettype="gendocs/generate" 또는 "gendocs/combine", targetid=gendocuid, ...)` 호출. `selected_chapters is not None`이면 combine, `None`이면(문서 전체 작성 fan-out 완료 후 호출) generate로 자동 판별.
    - `process_chapter_message()` 내부, `_update_chapter_queue(..., "E", ...)` 직후: `is_start_doc=False`(챕터 "단독" 재작성)일 때만 `log_work_action(actioncd="create", targettype="gendocs/genchapters/rewrite", targetid=genchapteruid, ...)` 호출. 문서 전체 작성의 fan-out 챕터(`is_start_doc=True`)는 여기서 안 남기고, 문서 전체가 끝나는 시점(`_run_merge_and_upload`)에서 `gendocs/generate`로 한 번만 남기게 해서 중복 방지.
    - 두 곳 다 `_run_merge_and_upload()`가 `tenantid` 파라미터를 새로 받도록 시그니처 변경(호출부 2곳도 함께 수정).
    - `detail`에 `gendocjobuid`/`genchapterjobuid`를 남겨서 기존 `create_requested` row와 매칭 가능.
  - **배포(2026-08-28)** — Docker 빌드 → ECR push → ECS `smartdocu-worker-service` 강제 재배포 완료. 태스크 정의가 `:latest` 태그(가변)를 참조해서, 다음 SQS 메시지 수신 시 워커가 스케일업될 때 새 이미지가 자동 적용됨(`desiredCount=0` 평시 대기 설계라 배포 시점엔 실행 중인 태스크가 없었음).
  - **미확인 — 후속 필요**: 실제 문서/챕터 작성을 한 번 돌려서 `work_logs`에 `actioncd="create"` row(요청 시 남은 `create_requested`와 별개로)가 새로 남는지는 아직 라이브로 확인 안 함. 다음에 실제 작성 테스트할 때 같이 확인할 것.
- [x] ~~d2insight ↔ Azure SQL(`mcp-rtims.database.windows.net`) 네트워크 연결~~ — 사용자가 "샘플링이라 미연결이어도 정상 동작, 불필요"로 확정(2026-08-27). 다시 꺼내지 말 것.
- [x] ~~워커 서비스(`smartdocu-worker-service`) `desiredCount=0` 원인 확인~~ — 의도적인 설계. 평소 0으로 대기하다 SQS 메시지 수신 시 자동으로 스케일업되는 구조, 정상 동작 확인됨(2026-08-27).
- [x] ~~워커 태스크 정의도 메인 앱처럼 Secrets Manager 방식으로 시크릿 분리~~ — 2026-08-25 완료. `smartdocu-worker` 태스크 정의 리비전 4로 갱신, `CLAUDE_API_KEY`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_KEY`/`ENCRYPTION_KEY` 전부 `smartdocu/backend/env` 시크릿 참조로 전환.
- [x] ~~`.dockerignore`/`config.py`(CORS_ORIGINS, BASE_URL)/`auth.py`/`org.py`/`.env` 변경분 git 커밋~~ — 사용자가 "git은 수동으로 커밋 중"이라고 확인(2026-08-25), 이 프로젝트의 정상 워크플로우라 후속작업 대상 아님.
- [x] ~~하드코딩된 옛 Azure 주소(dev-smart-doc.azurewebsites.net) 정리~~ — 2026-08-14 완료. `auth.py`(비밀번호 재설정 링크), `org.py`(초대 링크)를 `settings.BASE_URL` 참조로 변경, `config.py` CORS_ORIGINS에서 azurewebsites.net 제거, ECS 태스크 정의(리비전 2)에 `BASE_URL` 추가 후 재배포·스모크테스트 완료. `frontend/src/pages/HomePage.jsx`의 `dev-rag-medicine.azurewebsites.net` 링크는 별개 외부 서비스라 이번 작업에서 제외
