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

- [ ] **도메인 연결 + ACM 인증서 + HTTPS 전환** — 도메인 미정. 정해지면 Route53 + ACM 발급 + ALB 리스너 443 추가, `CORS_ORIGINS`/Supabase 리다이렉트 URL 갱신 필요
- [ ] **d2insight ↔ Azure SQL(`mcp-rtims.database.windows.net`) 네트워크 연결** — 이번 배포 범위에서 제외. NAT Gateway로 고정 아웃바운드 IP 만들어서 Azure SQL 방화벽에 등록하는 방안이 유력 (월 $32~45 + 데이터 전송비)
- [ ] **워커 서비스(`smartdocu-worker-service`) `desiredCount=0` 원인 확인** — 현재 SQS 큐를 아무도 소비하지 않고 있음. 의도적인지 확인 필요
- [ ] 워커 태스크 정의도 메인 앱처럼 Secrets Manager 방식으로 시크릿 분리 (현재 평문)
- [ ] `.dockerignore`/`config.py`(CORS_ORIGINS) 변경분 git 커밋
