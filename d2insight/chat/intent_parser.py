"""Parse user message into structured intent using LLM (fast grade)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from utilsPrj.ai_chain import build_langchain_llm, get_llm_info
from d2insight.config import LLM_MODELS

_KST = ZoneInfo("Asia/Seoul")
_llm_cache: dict = {}


def _get_llm(grade: str = "fast", project_id=None, tenant_id=None, user_uid=None, account_uid=None):
    key = (grade, project_id, tenant_id, user_uid, account_uid)
    if key not in _llm_cache:
        _, _api_key, _vendor, _, _ = get_llm_info(
            project_id=project_id, tenant_id=tenant_id,
            user_uid=user_uid, account_uid=account_uid, service_code="In",
        )
        _llm_cache[key] = build_langchain_llm(_vendor, _api_key, LLM_MODELS[_vendor][grade])
    return _llm_cache[key]


def _quick_chat(prompt: str, system: str, grade: str = "fast", max_tokens: int = 200,
                project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> str:
    from langchain_core.messages import SystemMessage, HumanMessage
    resp = _get_llm(grade, project_id=project_id, tenant_id=tenant_id,
                    user_uid=user_uid, account_uid=account_uid).invoke(
        [SystemMessage(content=system), HumanMessage(content=prompt)]
    )
    content = resp.content
    return content if isinstance(content, str) else content[0].text


# 14개 고수준 카테고리 목록 (registry.py와 동기화)
_REPORT_CATEGORIES = """보고서 유형 카테고리 (report_type 선택 기준):
- 경영분석: KPI, 사업부 성과, 전략 지표, 경영 종합
- 판매분석: 매출, 영업, 수주, 채널/제품/지역별 판매
- 생산분석: 생산성, 가동률, 공정 분석 (생산공정 포함)
- 원가분석: 제조원가, 비용, 판관비
- 품질분석: 불량, 클레임, 반품, QC/QA
- 구매조달분석: 구매원가, 공급업체, 납기 준수
- 재고물류분석: 재고, 물류, SCM, 배송
- 고객분석: CRM, 고객 세분화, LTV, 이탈/유입
- 마케팅분석: 캠페인, 전환율, 광고, ROI
- 인사분석: 인력, 이직, 급여, HR
- 재무분석: 손익, 현금흐름, 재무비율, 회계
- 기술분석: 서버, API, MCP, 인터페이스, 시스템 로그, IT 성능
- 리스크분석: ESG, 리스크, 컴플라이언스, 안전, 환경
- 기타: 위 카테고리에 해당하지 않는 경우"""

_SYSTEM = f"""당신은 분석 보고서 에이전트의 인텐트 파서입니다.
사용자 메시지를 분석하여 반드시 JSON만 응답하세요. 설명·마크다운 없이 JSON 객체만 출력하세요.

도구 선택 기준:
- health: 서버 상태, 헬스체크, 설정 확인
- report: 보고서 생성 요청 (분석 보고서, 현황 보고서 등)
- schedule_set: 방금 만든(또는 이 대화에서 만든) 보고서를 정기적으로/반복해서 작성해달라는 요청
  (예: "이 보고서 매달 5일에 작성해주세요", "매월 8시에 반복해줘", "작성된 보고서를 매달 5일 08시에 작성해주세요")
- chat: 위에 해당하지 않는 일반 대화, 사용법 문의

{_REPORT_CATEGORIES}

target_month 결정 규칙 (메시지 맨 앞의 "오늘 날짜: YYYY-MM-DD" 기준으로 계산):
- "2013년 3월", "2013-03" 등 연도+월이 명확히 명시된 경우 → "YYYY-MM" 형식 반환
- "작년 3월", "지난해 11월" → 오늘 날짜 기준 전년도 해당 월
- "이번 달" → 오늘 날짜 기준 현재 연도·월
- "지난달", "전월" → 오늘 날짜 기준 전월
- "11월 보고서", "3월 실적" 처럼 연도 없이 월만 언급 → null (연도를 추측하지 말 것)
- 아예 언급 없으면 → null

months_back 결정 규칙 (tool이 "report"일 때):
- 사용자가 "최근 N개월", "지난 N개월", "N개월 데이터로" 등 기간을 명시하면 그 숫자를 사용
- 사용자가 "반년", "6개월"이면 6, "1년", "12개월"이면 12, "분기", "3개월"이면 3으로 파싱
- 사용자가 기간을 명시하지 않으면 보고서 유형별 기본값 사용:
  판매분석: 3, 경영분석/원가분석/재무분석/고객분석/인사분석/구매조달분석/리스크분석: 3
  생산분석/품질분석/재고물류분석/마케팅분석/기술분석/기타: 1

mode 선택 기준 (tool이 "report"일 때):
- "start": "작성하려 합니다", "만들고 싶어요", "필요해요", "생각이에요" 등 의도 표현 → 대화형 명세 수집 시작
- "auto": "생성해줘", "만들어줘", "써줘", "작성해줘" 등 즉시 실행 명령 → 즉시 실행

응답 JSON 형식:
{{"tool": "도구명", "target_month": "YYYY-MM 또는 null", "months_back": 숫자, "report_type": "카테고리명 또는 null", "mode": "start 또는 auto 또는 null"}}

예시:
- "2013-03 판매실적 보고서 작성하려 합니다" → {{"tool": "report", "target_month": "2013-03", "months_back": 3, "report_type": "판매분석", "mode": "start"}}
- "판매 보고서 만들고 싶어요" → {{"tool": "report", "target_month": null, "months_back": 3, "report_type": "판매분석", "mode": "start"}}
- "2014-01 매출 보고서 생성해줘" → {{"tool": "report", "target_month": "2014-01", "months_back": 3, "report_type": "판매분석", "mode": "auto"}}
- "2024-01 서버 로그 분석 보고서" → {{"tool": "report", "target_month": "2024-01", "months_back": 1, "report_type": "기술분석", "mode": "auto"}}
- "서버 상태 확인" → {{"tool": "health", "target_month": null, "months_back": 3, "report_type": null, "mode": null}}
- "이 보고서 매달 5일 08시에 작성해주세요" → {{"tool": "schedule_set", "target_month": null, "months_back": 3, "report_type": null, "mode": null}}
- "어떤 분석을 할 수 있나요?" → {{"tool": "chat", "target_month": null, "months_back": 3, "report_type": null, "mode": null}}"""


def parse_intent(message: str, project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> dict:
    """Return {{tool, target_month, months_back, report_type, mode}} from user message."""
    today = datetime.now(tz=_KST).strftime("%Y-%m-%d")
    try:
        raw = _quick_chat(
            f"오늘 날짜: {today}\n사용자 메시지: {message}",
            system=_SYSTEM,
            grade="fast",
            max_tokens=200,
            project_id=project_id,
            tenant_id=tenant_id,
            user_uid=user_uid,
            account_uid=account_uid,
        )
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            parsed.setdefault("tool", "chat")
            parsed.setdefault("target_month", None)
            parsed.setdefault("months_back", 3)
            parsed.setdefault("report_type", None)
            parsed.setdefault("mode", None)
            return parsed
    except Exception as e:
        print(f"[intent_parser] error: {e}")
    return {"tool": "chat", "target_month": None, "months_back": 3, "report_type": None, "mode": None}
