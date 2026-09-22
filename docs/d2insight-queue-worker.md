# d2insight 보고서 생성 — Queue-Worker (비동기화)

d2insight 채팅에서 보고서 요청(`tool=="report"`)을 동기 처리 대신 SQS + 전용 워커로 비동기 처리한다.
d2doc과는 완전히 분리된 큐·워커·ECS 서비스를 쓴다(회사 방침).

## 흐름

```
/chat (tool=report)
  → insight_qas에 자리표시자 행 생성 (jobstatuscd='S')
  → SQS(smartdocu-genreports-queue)로 메시지 전송
  → "접수되었습니다" 즉시 응답

CloudWatch 알람이 큐 메시지 감지 → smartdocu-insight-worker-service 0→1 오토스케일
  → worker/insight_main.py가 메시지 수신
  → jobstatuscd 'S'→'P' 선점(중복 처리 방지, worker/main.py와 동일 패턴)
  → run_tool() 재사용해 보고서 생성
  → insight_qas 갱신: 'D'(성공, answer/filenm/fileurl 채움) 또는 'F'(실패)
  → create_notification()으로 알림 발송 (채팅창 실시간 갱신은 없음)

큐 비면 5분 뒤 자동으로 서비스 1→0
```

## 변경/추가 파일

| 파일 | 내용 |
|---|---|
| `backend/app/config.py`, `.env` | `SQS_INSIGHT_QUEUE_URL` 추가 |
| `d2insight/db/insight_storage.py` | `create_qa_placeholder()` 추가 |
| `d2insight/chat/router.py` | `tool=="report"`일 때 동기 `run_tool()` 대신 자리표시자 생성+SQS 전송으로 분기 |
| `worker/insight_main.py` (신규) | d2insight 전용 워커 진입점. `run_tool()`을 그대로 재사용. `report_path` 유무로 진짜 성공/실패를 판별(run_tool은 데이터 조회 실패도 예외 없이 answer 텍스트로만 반환하므로) |
| `worker/Dockerfile` | MS SQL ODBC 드라이버(`msodbcsql17`) 설치 추가 — 루트 Dockerfile엔 있었지만 워커엔 없어서, DB 소스 보고서 생성이 워커로 옮겨오며 깨졌던 것을 발견해 추가 |
| `worker/insight-task-def.json` (신규) | ECS 태스크 정의 원본(참고용, 앱 코드 아님) |
| `d2insight/db/supabase_client.py` | `build_upload_handoff_path()` 추가 — 업로드 데이터셋 중계 파일 경로 |

d2insight의 DB 접근은 전부 서비스 롤 기반(`d2insight/db/supabase_client.py`)이라, d2doc 워커와 달리 access_token/FakeRequest 없이 동작한다.

### LLM 키 조회 실패 문제와 해결

엔진 내부 LLM 호출(`d2insight/engine/_llm.py`, `d2insight/engine/pipeline/db_meta.py` 등)은 project_id/tenant_id/account_uid를 함수 인자로 받지 않고 `token_tracker.get_log_ctx()`(요청마다 설정해두는 전역 컨텍스트)에서 읽는다. 기존엔 `router.py`가 `/chat` 시작 시 `token_tracker.set_log_ctx(...)`를 호출해뒀지만, 워커는 이 호출이 없어 컨텍스트가 비어 있었고 그래서 LLM 키를 찾을 project_id 등이 전부 `None`이 되어 "AI 키가 등록되지 않았습니다" 에러가 났다. `worker/insight_main.py`에서 `run_tool()` 호출 전 `token_tracker.reset()` + `set_log_ctx(...)`(router.py와 동일한 dict 형태)를 호출하고, 끝나면 `finally`에서 `set_log_ctx(None)`으로 정리하도록 수정.

### 업로드 데이터셋 문제와 해결

업로드된 엑셀/CSV는 백엔드 프로세스 메모리(`d2shared/excel_server.py`의 `ExcelServer` 싱글턴)에만 있어, 별도 프로세스인 워커는 원래 볼 수 없었다(큐-워커 전환 전엔 업로드·보고서 생성이 같은 프로세스라 문제없었음). 해결: `/chat`이 비동기 분기를 탈 때 그 세션에 업로드 데이터셋이 있으면, 그 요청(qauid) 전용 일회용 중계 파일(`Users/{accountuid}/Insight/UploadHandoff/{qauid}/datasets.pkl`)로 Storage에 올리고 경로를 SQS 메시지에 실어 보낸다. 워커는 그 파일을 내려받아 자기 프로세스의 `ExcelServer`에 주입한 뒤 처리하고, 끝나면(성공/실패 무관) 즉시 삭제한다. 세션 원본 데이터(백엔드 메모리)는 건드리지 않으므로 같은 세션에서 요청이 여러 번 와도 매번 새 중계 파일을 만들어 문제없다.

## AWS 리소스 (신규)

| 항목 | 값 |
|---|---|
| SQS 큐 | `smartdocu-genreports-queue` |
| ECS 태스크 정의 | `smartdocu-insight-worker` (1 vCPU / 4GB, 이미지는 `smartdocu-worker:latest` 공유, 실행 명령만 `python -m worker.insight_main`) |
| ECS 서비스 | `smartdocu-insight-worker-service` (`smartdocu-cluster`, 최소 0/최대 5) |
| 오토스케일링 | 스케일아웃: 큐 메시지 ≥1(10초) / 스케일인: 큐 메시지 <1(5분) — 기존 워커와 동일 규칙 |
| CloudWatch 알람 | `smartdocu-insight-worker-scaleout`, `smartdocu-insight-worker-scalein` |
| IAM | `smartdocu-app`에 `smartdocu-app-insight-autoscaling` 정책 추가(`application-autoscaling:*`, `cloudwatch:PutMetricAlarm`) |

이미지는 d2doc 워커와 공유하지만(`worker/Dockerfile`에 d2insight 코드가 이미 포함), **ECS 서비스/오토스케일링/큐는 완전히 별도**라 서로 재배포·재시작에 영향 없다.

## jobstatuscd (insight_qas)

`S`(접수) → `P`(워커 선점) → `D`(완료) 또는 `F`(실패). `genchapters_realtimes`와 다른 값 체계(d2doc은 `S`/`E`).

## 확인 방법

1. d2insight 채팅에서 보고서 요청 → "접수되었습니다" 즉시 응답 확인
2. AWS: `smartdocu-insight-worker-service` 태스크 수 0→1 확인, CloudWatch 로그 그룹 `smartdocu-insight-worker`에서 처리 로그 확인
3. 완료 후 알림벨에 알림 도착 확인, 세션 다시 열어 실제 보고서 내용 채워졌는지 확인

## 남은 작업

- `msg.notification.insight.completed.title` 등 알림 다국어 키 미등록(현재는 한글 고정 문구로 폴백 표시됨) — `ui_terms`/`ui_term_translations` 등록 필요
