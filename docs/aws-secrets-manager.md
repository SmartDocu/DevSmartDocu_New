# AWS Secrets Manager 설정 가이드

커넥터 자격증명(DB 비밀번호, API 키 등)을 AWS Secrets Manager로 관리하기 위한 초기 설정 및 마이그레이션 가이드.

---

## 1. AWS CLI 설치

### 방법 A — MSI 설치파일 (권장)

1. 구글에서 `AWS CLI Windows download` 검색 → 공식 AWS 페이지
2. `AWSCLIV2.msi` 다운로드 → 설치 (Next → Next → Finish)
3. 설치 확인
   ```powershell
   aws --version
   # aws-cli/2.x.x 출력되면 OK
   ```

### 방법 B — winget

```powershell
winget install Amazon.AWSCLI
```

---

## 2. IAM 자격증명 설정

```bash
aws configure
```

입력값:
```
AWS Access Key ID     : [IAM 콘솔에서 발급한 키]
AWS Secret Access Key : [IAM 콘솔에서 발급한 시크릿]
Default region name   : ap-northeast-2
Default output format : (엔터)
```

**IAM 키 발급 위치:** AWS 콘솔 → IAM → 사용자 → 보안 자격 증명 → 액세스 키 만들기

**필요 권한 (IAM 정책):**
```
secretsmanager:GetSecretValue
secretsmanager:CreateSecret
secretsmanager:PutSecretValue
secretsmanager:DeleteSecret
secretsmanager:DescribeSecret
```

---

## 3. 환경변수 (.env)

```
AWS_REGION=ap-northeast-2
SECRETS_TTL_SECONDS=86400
```

---

## 4. AWS SM 저장 구조

테넌트당 시크릿 1개:

```
시크릿 이름: smartdocu/{tenantid}/connectors

내용 (JSON):
{
  "connuid-001": {"username": "dbuser", "password": "pass"},
  "connuid-002": {"api_key_value": "sk-abc123"},
  "connuid-003": {"username": "apiuser", "password": "pass2"}
}
```

DB의 `secret_path` 컬럼에는 `aws-sm` 문자열만 저장됨.

---

## 5. 기존 데이터 마이그레이션 (`migrate_secrets.py`)

기존 커넥터의 평문 JSON 자격증명을 AWS SM으로 일괄 이전하는 스크립트.
**실행 후 삭제할 것.**

### 실행 전 확인 (dry-run)

변경 없이 이전 대상만 출력:

```bash
python migrate_secrets.py --dry-run
```

출력 예시:
```
[DRY RUN] 마이그레이션 시작

  DB  커넥터 | tenant=abc123 | connuid=550e-... | keys=['username', 'password']
  API 커넥터 | tenant=abc123 | connuid=661f-... | keys=['api_key_value']

→ 1개 테넌트, 2개 커넥터 이전 예정

  AWS SM 저장: tenant=abc123 (2개) ... SKIP
  DB 업데이트 (connectors)           connuid=550e-... ... SKIP
  DB 업데이트 (conn_api_credentials) connuid=661f-... ... SKIP

[DRY RUN] 완료!
```

### 실제 실행

```bash
python migrate_secrets.py
```

완료 후 `migrate_secrets.py` 삭제.

### 마이그레이션 동작 순서

1. DB에서 `secret_path`가 평문 JSON인 커넥터 전체 조회
2. tenantid 기준으로 그룹핑
3. 테넌트당 AWS SM 시크릿 1개에 전체 커넥터 자격증명 저장
4. DB `secret_path` 컬럼을 `aws-sm`으로 업데이트
