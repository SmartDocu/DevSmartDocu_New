"""Parse user message into structured intent using LLM (fast grade)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from utilsPrj.ai_chain import get_llm_clients

_KST = ZoneInfo("Asia/Seoul")


def _get_llm(grade: str = "fast", project_id=None, tenant_id=None, user_uid=None, account_uid=None):
    # ai_chain.get_llm_clients()가 (project/tenant/user/account) 조합당 한 번만 인증·생성해
    # 캐싱한다 — 파일마다 따로 _llm_cache를 두면 같은 조합인데도 각자 인증하게 되므로
    # 중앙 캐시 하나를 공유한다(2026-08-31, 여러 파일에 중복된 로컬 캐시 확인 후 통일).
    clients = get_llm_clients(
        project_id=project_id, tenant_id=tenant_id,
        user_uid=user_uid, account_uid=account_uid, service_code="In",
    )
    return clients[grade]


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

grain 결정 규칙 (target_month의 형식을 결정한다):
- 월 단위 언급("3월", "이번 달", "지난달") 또는 언급 없음 → "month" (기본값)
- 주 단위 언급("지난 주", "저번 주", "이번 주", 또는 "9월 7일부터 9월 13일까지"처럼 며칠 단위
  날짜 범위/특정 날짜) → "week" (주간 보고서는 항상 월요일~일요일 기준)
- 분기 언급("이번 분기", "지난 분기", "1분기"~"4분기", "Q1"~"Q4", "1/4분기"~"4/4분기") → "quarter"
- 반기 언급("상반기", "하반기", "이번 반기", "지난 반기") → "half"
- 연 단위 언급("올해", "작년", "2023년"처럼 월 없이 연도만) → "year"

target_month 결정 규칙 (메시지 맨 앞의 "오늘 날짜: YYYY-MM-DD (요일)" 기준으로 계산 — grain에
맞는 형식으로 반환):
- grain="month": "YYYY-MM". "2013년 3월"처럼 연도+월이 명확하면 그대로, "작년 3월"은 오늘
  기준 전년도 해당 월, "이번 달"은 오늘 기준 연·월, "지난달"/"전월"은 오늘 기준 전월.
  "11월 보고서"처럼 연도 없이 월만 언급되면 연도를 추측하지 말고 null.
- grain="week": 주차 번호가 아니라 실제 날짜 하나를 "YYYY-MM-DD" 형식으로 반환한다(그 주의
  아무 날짜나 상관없음 — 어느 주인지는 이후 코드가 이 날짜로부터 계산한다). "지난 주"/
  "저번 주"는 오늘 날짜에서 7일을 뺀 날짜, "이번 주"는 오늘 날짜 그대로. 특정 날짜나 날짜
  범위가 언급되면 그 날짜(범위면 시작일)를 그대로 반환.
- grain="quarter": "YYYY-Qn"(n=1~4). "이번 분기"는 오늘 날짜가 속한 분기, "지난 분기"는 그
  1분기 전(1분기면 전년도 4분기), 특정 분기 언급("2026년 2분기")은 그대로 사용.
- grain="half": "YYYY-Hn"(n=1~2, 1~6월=H1, 7~12월=H2). "이번 반기"는 오늘 날짜가 속한 반기,
  "지난 반기"/"저번 반기"는 1반기 전(H1이면 전년도 H2), "상반기"=해당 연도 H1, "하반기"=해당
  연도 H2.
- grain="year": "YYYY". "올해"는 오늘 기준 연도, "작년"은 그 전년도, "2023년"처럼 연도만
  언급되면 그대로.
- 기간 언급이 전혀 없으면 grain 무관하게 target_month는 null.

compare_type 결정 규칙 (tool이 "report"일 때 — 무엇과 비교할지):
- "전년 동기 대비", "작년 같은 기간과 비교", "전년 동월/동분기/동반기 대비" 등 1년 전과
  비교하라는 언급 → "YoY"
- grain="month"인데 "전분기 대비"(3개월 전과 비교)를 명시적으로 언급 → "QoQ"
  (다른 grain에는 QoQ가 없음 — 그 경우는 아래 기본값 사용)
- 비교 기준을 언급하지 않았거나 "전월 대비"/"전기 대비"/"직전 기간 대비"처럼 바로 전
  주기와 비교하라는 뜻이면 → "MoM" (이름은 "월"이지만 grain에 따라 "바로 전 주기"라는
  뜻이다 — quarter면 전분기, half면 전반기, year면 전년, week면 전주)

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
{{"tool": "도구명", "grain": "month/quarter/half/year/week", "target_month": "grain 형식에 맞는 값 또는 null", "compare_type": "MoM/YoY/QoQ", "months_back": 숫자, "report_type": "카테고리명 또는 null", "mode": "start 또는 auto 또는 null"}}

예시 (아래는 오늘이 2026-06-08(월요일)이라고 가정했을 때의 예시일 뿐입니다 — 실제 계산은
매번 메시지 맨 앞에 주어지는 진짜 오늘 날짜를 기준으로 할 것):
- "2013-03 판매실적 보고서 작성하려 합니다" → {{"tool": "report", "grain": "month", "target_month": "2013-03", "compare_type": "MoM", "months_back": 3, "report_type": "판매분석", "mode": "start"}}
- "판매 보고서 만들고 싶어요" → {{"tool": "report", "grain": "month", "target_month": null, "compare_type": "MoM", "months_back": 3, "report_type": "판매분석", "mode": "start"}}
- "2014-01 매출 보고서 생성해줘" → {{"tool": "report", "grain": "month", "target_month": "2014-01", "compare_type": "MoM", "months_back": 3, "report_type": "판매분석", "mode": "auto"}}
- "2024-01 서버 로그 분석 보고서" → {{"tool": "report", "grain": "month", "target_month": "2024-01", "compare_type": "MoM", "months_back": 1, "report_type": "기술분석", "mode": "auto"}}
- "지난 주 서버로그 분석 보고서를 작성해주세요" → {{"tool": "report", "grain": "week", "target_month": "2026-06-01", "compare_type": "MoM", "months_back": 1, "report_type": "기술분석", "mode": "auto"}}
- "5월 25일부터 5월 31일까지 주간 서버로그 분석 보고서를 작성해주세요" → {{"tool": "report", "grain": "week", "target_month": "2026-05-25", "compare_type": "MoM", "months_back": 1, "report_type": "기술분석", "mode": "auto"}}
- "1/4분기 판매실적 보고서 작성해줘" → {{"tool": "report", "grain": "quarter", "target_month": "2026-Q1", "compare_type": "MoM", "months_back": 3, "report_type": "판매분석", "mode": "auto"}}
- "2026년 2/4분기 판매증감 원인분석 보고서를 전년 동기 대비로 작성해주세요" → {{"tool": "report", "grain": "quarter", "target_month": "2026-Q2", "compare_type": "YoY", "months_back": 3, "report_type": "판매분석", "mode": "auto"}}
- "상반기 재무분석 보고서 작성해줘" → {{"tool": "report", "grain": "half", "target_month": "2026-H1", "compare_type": "MoM", "months_back": 3, "report_type": "재무분석", "mode": "auto"}}
- "작년 리스크분석 보고서" → {{"tool": "report", "grain": "year", "target_month": "2025", "compare_type": "MoM", "months_back": 3, "report_type": "리스크분석", "mode": "auto"}}
- "서버 상태 확인" → {{"tool": "health", "grain": "month", "target_month": null, "compare_type": "MoM", "months_back": 3, "report_type": null, "mode": null}}
- "이 보고서 매달 5일 08시에 작성해주세요" → {{"tool": "schedule_set", "grain": "month", "target_month": null, "compare_type": "MoM", "months_back": 3, "report_type": null, "mode": null}}
- "어떤 분석을 할 수 있나요?" → {{"tool": "chat", "grain": "month", "target_month": null, "compare_type": "MoM", "months_back": 3, "report_type": null, "mode": null}}"""


_GRAINS = ("month", "quarter", "half", "year", "week")
_WEEKDAY_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def _week_period_from_date_str(date_str: str) -> str | None:
    """LLM이 뽑은 평범한 날짜("YYYY-MM-DD")를 ISO 주차 식별자("YYYY-Www")로 바꾼다.

    ISO 주차 계산(연말·연초 경계 등)은 표준 라이브러리(date.isocalendar())가 하고, LLM은
    d2chat의 날짜 처리와 동일하게 실제 달력 날짜만 뽑는다 — 주차 번호 자체는 계산시키지 않는다.
    """
    from datetime import date as _date
    try:
        y, mo, d = map(int, date_str.split("-"))
        iso = _date(y, mo, d).isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    except (ValueError, TypeError):
        return None


def parse_intent(message: str, project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> dict:
    """Return {{tool, grain, target_month, months_back, report_type, mode}} from user message."""
    now = datetime.now(tz=_KST)
    today = now.strftime("%Y-%m-%d")
    weekday_kr = _WEEKDAY_KR[now.weekday()]
    try:
        raw = _quick_chat(
            f"오늘 날짜: {today} ({weekday_kr})\n사용자 메시지: {message}",
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
            parsed.setdefault("grain", "month")
            parsed.setdefault("target_month", None)
            parsed.setdefault("compare_type", "MoM")
            parsed.setdefault("months_back", 3)
            parsed.setdefault("report_type", None)
            parsed.setdefault("mode", None)
            if parsed["grain"] not in _GRAINS:
                parsed["grain"] = "month"
            if parsed.get("compare_type") not in ("MoM", "YoY", "QoQ"):
                parsed["compare_type"] = "MoM"
            if parsed["compare_type"] == "QoQ" and parsed["grain"] != "month":
                # QoQ는 month grain 전용(dataset_builder.compare_shift) — 다른 grain에서
                # QoQ가 잘못 나오면 조용히 MoM(바로 전 주기)으로 대체한다.
                parsed["compare_type"] = "MoM"
            if parsed["grain"] == "week" and parsed.get("target_month"):
                parsed["target_month"] = _week_period_from_date_str(parsed["target_month"])
            return parsed
    except Exception as e:
        # print(f"[intent_parser] error: {e}")
        pass
    return {"tool": "chat", "grain": "month", "target_month": None, "compare_type": "MoM",
            "months_back": 3, "report_type": None, "mode": None}
