"""정기 보고서(스케줄) cron 계산 유틸리티 + 대화형 등록(schedule_set) 상태 머신.

오른쪽 패널의 "정기 보고서로 저장" 버튼은 요일/일자/시간을 폼(select)으로 직접 받아 REST로
바로 등록한다(cron 조합/파싱, 다음 실행일 계산, 일정 변경 시 효력발생일 계산 — 아래 순수
계산 함수들). 그와 별도로, 대화창(viewMode='chat')에서 방금 만든 보고서를 두고 "이 보고서
매달 5일 8시에 작성해주세요"처럼 문장으로 요청하는 경로도 지원한다 — 대화 목록(history)
화면은 입력창 자체가 없어 이 경로를 탈 일이 없고, 실시간 대화 중에만 의미가 있다. 이 파일
아래쪽의 _spec_store/advance_set_spec이 그 상태 머신이다(pr_module_insight의 schedule_set
대화 흐름과 같은 원칙, 다만 이 앱은 월 단위 grain만 지원하므로 요일 분기는 두지 않는다).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

WEEKDAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"]   # cron 관례(0=일요일)


def compose_cron(grain: str, day_of_month: int | None, weekday: int | None,
                  hour: int, minute: int) -> str:
    """5자리 cron(분 시 일 월 요일). 말일(-1)은 표준 cron에 없어 28일로 근사한다 — 모든 달에
    안전하게 존재하는 마지막 날짜라, "말일 근처"를 놓치지 않는 가장 단순한 근사다.
    """
    if grain == "week":
        return f"{minute} {hour} * * {weekday}"
    day_field = "28" if day_of_month == -1 else str(day_of_month)
    if grain == "quarter":
        return f"{minute} {hour} {day_field} 1,4,7,10 *"
    if grain == "year":
        return f"{minute} {hour} {day_field} 1 *"
    return f"{minute} {hour} {day_field} * *"


def parse_cron(cron: str) -> dict:
    """5자리 cron(분 시 일 월 요일) → {grain, day_of_month, weekday, hour, minute}.

    compose_cron의 역변환 — 일정 수정 화면에서 지금 설정값을 보여주고 편집 폼 기본값으로 쓴다.
    말일(-1)은 "28"로 근사 저장되므로 역변환 시 28을 "말일"로 되살리지 못하고 28일 그대로
    보여준다(pr_module_insight와 동일한 기존 한계).
    """
    minute_s, hour_s, day_s, month_s, weekday_s = cron.split()
    minute, hour = int(minute_s), int(hour_s)
    if day_s == "*" and weekday_s != "*":
        return {"grain": "week", "day_of_month": None, "weekday": int(weekday_s),
                 "hour": hour, "minute": minute}
    day = int(day_s)
    if month_s == "1,4,7,10":
        grain = "quarter"
    elif month_s == "1":
        grain = "year"
    else:
        grain = "month"
    return {"grain": grain, "day_of_month": day, "weekday": None, "hour": hour, "minute": minute}


def compute_target_month(grain: str, offset: int, run_date) -> str:
    """grain 주기 기준으로 run_date가 속한 주기의 offset번째 이전 달을 "YYYY-MM"로 반환한다.

    현재 등록 화면은 month grain만 제공하므로 month 기준으로 계산한다(offset은 항상 -1 —
    실행 시점 기준 직전 달). scheduled_runner.run_scheduled_template의 실제 실행과
    _register_schedule_for_qa의 "첫 실행이 원본 기간과 겹치는지" 사전 판정이 이 함수 하나를
    같이 쓴다 — 두 곳이 각자 계산하면 나중에 어긋날 수 있어서다.
    """
    year, month = run_date.year, run_date.month
    steps = -offset if offset < 0 else 0
    for _ in range(steps):
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    return f"{year:04d}-{month:02d}"


def next_run_avoiding_period(origin_period: str | None, day_of_month: int, hour: int, minute: int) -> datetime:
    """다음 실행 시각 — 단, 그 실행이 만들 대상월이 origin_period(등록 기준이 된 원본 보고서의
    대상월)와 같으면 한 주기 미룬다.

    예: 8/4에 "지난달(7월)" 보고서를 만들고 "매달 5일"로 등록하면 다음 cron이 바로 내일(8/5)
    이라 실행 시점 기준 전월(여전히 7월)을 또 만들어 원본과 중복된다. "2026년 5월"처럼 특정
    과거월을 등록한 경우는 첫 실행(전월=7월)이 origin_period(5월)와 달라 이 조건에 안 걸리고
    그대로 진행된다 — 대상월이 실제로 겹칠 때만 한 주기 미룬다. 등록(REST/대화 양쪽)과
    등록 전 미리보기 문구가 같은 값을 보도록 계산을 한곳에 둔다.
    """
    next_dt = next_occurrence("month", day_of_month, None, hour, minute, datetime.now(tz=KST))
    if origin_period and compute_target_month("month", -1, next_dt.date()) == origin_period:
        next_dt = next_occurrence("month", day_of_month, None, hour, minute, next_dt)
    return next_dt


def _next_month_grain_dates(grain: str) -> list[int]:
    """quarter/year grain에서 실행 월 목록(1~12)."""
    if grain == "quarter":
        return [1, 4, 7, 10]
    if grain == "year":
        return [1]
    return list(range(1, 13))


def next_occurrence(grain: str, day_of_month: int | None, weekday: int | None,
                     hour: int, minute: int, after: datetime) -> datetime:
    """after 이후 가장 가까운 실행 시각."""
    if grain == "week":
        target_py_wd = (weekday - 1) % 7   # cron 0=일 → python Monday=0 기준으로 환산
        days_ahead = (target_py_wd - after.weekday()) % 7
        candidate = (after + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(days=7)
        return candidate

    run_months = _next_month_grain_dates(grain)
    year, month = after.year, after.month
    for _ in range(24):   # 최대 2년 안에는 반드시 걸린다(연 단위 grain 대비 여유)
        if month in run_months:
            try:
                candidate = datetime(year, month, 28 if day_of_month == -1 else day_of_month,
                                      hour, minute, tzinfo=after.tzinfo)
                if candidate > after:
                    return candidate
            except ValueError:
                pass   # 그 달에 없는 날짜(예: 2월 30일) — 다음 주기로 넘어간다
        month += 1
        if month > 12:
            month = 1
            year += 1
    raise ValueError("다음 실행일을 계산하지 못했습니다 — day_of_month 값을 확인해주세요.")


def _period_label(grain: str) -> str:
    return {"week": "지난주", "month": "전월", "quarter": "전분기", "year": "전년"}.get(grain, "전월")


def _time_label(hour: int, minute: int) -> str:
    label = f"오전 {hour}시" if hour < 12 else (f"오후 {hour - 12}시" if hour > 12 else "낮 12시")
    if minute:
        label += f" {minute}분"
    return label


def _when_label(grain: str, day_of_month: int | None, weekday: int | None, hour: int, minute: int) -> str:
    grain_label = {"week": "매주", "month": "매달", "quarter": "매분기", "year": "매년"}[grain]
    time_label = _time_label(hour, minute)
    if grain == "week":
        return f"{grain_label} {WEEKDAY_NAMES[weekday]}요일 {time_label}"
    day_label = "말일" if day_of_month == -1 else f"{day_of_month}일"
    return f"{grain_label} {day_label} {time_label}"


def build_register_message(next_dt: datetime, grain: str, day_of_month: int | None,
                            weekday: int | None, hour: int, minute: int) -> str:
    when = _when_label(grain, day_of_month, weekday, hour, minute)
    first_run_label = next_dt.strftime("%Y년 %m월 %d일")
    return (
        f"{when}에 {_period_label(grain)} 보고서를 만듭니다.\n"
        f"첫 실행은 {first_run_label}입니다.\n"
        "이렇게 등록할까요?"
    )


def _period_bounds(grain: str, ref: datetime) -> tuple[datetime, datetime]:
    """ref가 속한 주기의 [시작, 다음 주기 시작) — "이번 주기"와 "다음 주기"를 가르는 기준선.
    cron 요일 관례(0=일요일)에 맞춰 주는 일요일에 시작한다.
    """
    if grain == "week":
        cron_wd = (ref.weekday() + 1) % 7   # python Monday=0..Sunday=6 → cron Sunday=0..Saturday=6
        start = (ref - timedelta(days=cron_wd)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    if grain == "quarter":
        q_start_month = ((ref.month - 1) // 3) * 3 + 1
        start = ref.replace(month=q_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_month = q_start_month + 3
        end = (start.replace(year=start.year + 1, month=end_month - 12) if end_month > 12
               else start.replace(month=end_month))
        return start, end
    if grain == "year":
        start = ref.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, start.replace(year=start.year + 1)
    # month
    start = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(year=start.year + 1, month=1) if start.month == 12
           else start.replace(month=start.month + 1))
    return start, end


def _occurrence_in_period(settings: dict, period_start: datetime) -> datetime:
    """period_start가 속한 주기 안에서 settings(day_of_month/weekday + hour + minute)가
    가리키는 실행 시각. day_of_month가 그 달에 없는 날짜면(예: 31일인데 2월) 그 달의
    마지막 날로 당긴다 — compose_cron이 말일을 28로 근사하는 것과 같은 관용적 처리.
    """
    hour = settings.get("hour") if settings.get("hour") is not None else 9
    minute = settings.get("minute") if settings.get("minute") is not None else 0
    grain = settings["grain"]
    if grain == "week":
        return (period_start + timedelta(days=settings["weekday"])).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
    day = settings["day_of_month"]
    next_month_start = (period_start.replace(year=period_start.year + 1, month=1, day=1)
                         if period_start.month == 12
                         else period_start.replace(month=period_start.month + 1, day=1))
    last_day = (next_month_start - timedelta(days=1)).day
    day_val = last_day if day == -1 else min(day, last_day)
    return period_start.replace(day=day_val, hour=hour, minute=minute, second=0, microsecond=0)


def compute_schedule_update(old_settings: dict, new_settings: dict, now: datetime) -> dict:
    """일정(요일/일자/시각) 변경 시 언제부터 적용할지 계산한다.

    old_settings/new_settings: {grain, day_of_month|weekday, hour, minute} — 같은 grain이어야
    한다(주기 자체를 바꾸는 건 이 함수의 범위 밖).

    규칙:
      - 이번 주기 예정 작성 이전(now < 이번 주기 옛 예정일)이고, 새 일정의 이번 주기 예정일이
        아직 안 지났으면(new_occurrence > now) → 이번 주기부터 새 일정 적용.
      - 이번 주기 예정 작성 이전인데 새 일정의 이번 주기 예정일이 이미 지났으면 → 지금 즉시
        작성하고, 다음 주기부터 새 일정 적용.
      - 이번 주기 예정 작성이 이미 지났으면(now >= 이번 주기 옛 예정일) → 새 일정이 이번 주기
        안에 남아 있어도(이중 실행 방지) 다음 주기부터 적용.

    반환: {"immediate_run": bool, "effective": "this_period"|"next_period",
           "effective_start": datetime}
    """
    grain = old_settings["grain"]
    period_start, _ = _period_bounds(grain, now)
    old_occurrence = _occurrence_in_period(old_settings, period_start)

    if now < old_occurrence:
        new_occurrence = _occurrence_in_period(new_settings, period_start)
        if new_occurrence > now:
            return {"immediate_run": False, "effective": "this_period", "effective_start": new_occurrence}
        next_period_start = _period_bounds(grain, period_start)[1]
        return {"immediate_run": True, "effective": "next_period",
                "effective_start": _occurrence_in_period(new_settings, next_period_start)}

    next_period_start = _period_bounds(grain, period_start)[1]
    return {"immediate_run": False, "effective": "next_period",
            "effective_start": _occurrence_in_period(new_settings, next_period_start)}


def build_update_message(decision: dict, new_settings: dict) -> str:
    """일정 변경 확인 문구 — 사용자가 확인해야 실제로 적용된다."""
    when = _when_label(new_settings["grain"], new_settings.get("day_of_month"),
                        new_settings.get("weekday"),
                        new_settings.get("hour") if new_settings.get("hour") is not None else 9,
                        new_settings.get("minute") if new_settings.get("minute") is not None else 0)
    start_label = decision["effective_start"].strftime("%Y년 %m월 %d일")
    if decision["immediate_run"]:
        return (
            f"{when}로 일정을 바꾸면 이번 주기 예정일은 이미 지났습니다.\n"
            f"지금 바로 이번 주기 보고서를 작성하고, 다음 적용은 {start_label}부터입니다.\n"
            "이렇게 진행할까요?"
        )
    when_label = "이번 주기부터" if decision["effective"] == "this_period" else "다음 주기부터"
    return f"{when}로 바꿉니다({when_label}, {start_label}). 이렇게 진행할까요?"


# ── 대화형 등록(schedule_set) 상태 머신 ──────────────────────────────
# session_id → spec dict (인메모리, report_spec._spec_store와 같은 방식·같은 한계 — 서버
# 재시작 시 진행 중이던 등록 대화는 사라진다).
_spec_store: dict[str, dict] = {}

_EXTRACT_SYSTEM = """사용자 메시지에서 정기 보고서 작성 일자·시각 정보를 추출하여 JSON만
응답하세요. 설명 없이 JSON 객체만 출력하세요. 이 앱은 매달 반복(월 단위)만 지원합니다.

- day_of_month: "매달 5일", "3일에 만들어줘" 등 일자 표현 → 1~31 숫자. "말일", "마지막날" → -1. 언급 없으면 null
- hour: "오전 9시"→9, "오후 3시"→15, "저녁 7시"→19. 언급 없으면 null
- minute: 분이 명시된 경우만 숫자, 없으면 null
- confirmed: "네", "등록해줘", "맞아요", "그렇게 해주세요", "진행해줘" 등 확인 단계 최종 승인 → true
- cancel: "아니요", "취소", "그만둘게요", "안 할래요" → true

응답 JSON:
{"day_of_month": null, "hour": null, "minute": null, "confirmed": false, "cancel": false}"""


def get_spec(session_id: str) -> Optional[dict]:
    return _spec_store.get(session_id)


def save_spec(session_id: str, spec: dict) -> None:
    _spec_store[session_id] = spec


def clear_spec(session_id: str) -> None:
    _spec_store.pop(session_id, None)


def create_set_spec(qauid: str, origin_period: str | None = None) -> dict:
    """"작성된 보고서를 매월 5일 08시에 작성해주세요" 류 — 이 세션에서 방금 만든 보고서
    (qauid)를 대상으로 등록 대화를 시작한다. 반복 주기(일자·시각)는 아직 모르는 채로 시작해
    되묻는다 — 오른쪽 패널 폼과 달리 대화라 한 번에 다 안 올 수 있다.

    origin_period: 그 보고서의 대상월("YYYY-MM") — 확인 문구의 "첫 실행일"이 원본과 같은
    달을 다시 만드는 경우를 피해가도록 next_run_avoiding_period에 넘긴다.
    """
    return {
        "kind": "set", "qauid": qauid, "origin_period": origin_period,
        "day_of_month": None, "hour": None, "minute": None,
        "mode": "gathering",
    }


def _extract(message: str, project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> dict:
    from utilsPrj.ai_chain import build_langchain_llm, get_llm_info
    from langchain_core.messages import SystemMessage, HumanMessage

    defaults = {"day_of_month": None, "hour": None, "minute": None, "confirmed": False, "cancel": False}
    try:
        # service_code="In"이면 models가 문자열이 아니라 {"fast":.., "balanced":.., "quality":..} dict다.
        models, api_key, vendor, _, _ = get_llm_info(
            project_id=project_id, tenant_id=tenant_id,
            user_uid=user_uid, account_uid=account_uid, service_code="In",
        )
        llm = build_langchain_llm(vendor, api_key, models["fast"])
        resp = llm.invoke([SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=message)])
        raw = resp.content if isinstance(resp.content, str) else resp.content[0].text
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            defaults.update(json.loads(m.group()))
    except Exception as e:
        print(f"[schedule_spec] _extract error: {e}")
    return defaults


def _required_field(spec: dict) -> Optional[str]:
    return "day_of_month" if spec.get("day_of_month") is None else None


def _ask_text(field: str) -> str:
    return "매달 며칠에 작성할까요? (예: 5일, 말일)"


def build_set_confirmation(spec: dict) -> str:
    hour = spec.get("hour") if spec.get("hour") is not None else 9
    minute = spec.get("minute") if spec.get("minute") is not None else 0
    next_dt = next_run_avoiding_period(spec.get("origin_period"), spec["day_of_month"], hour, minute)
    return build_register_message(next_dt, "month", spec["day_of_month"], None, hour, minute)


def advance_set_spec(session_id: str, message: str, project_id=None, tenant_id=None,
                     user_uid=None, account_uid=None) -> tuple[dict, str]:
    """등록 진행 — (updated_spec, bot_response). bot_response 특수값:
    "__SAVE_SCHEDULE__" → 호출부가 저장 실행, "__CANCEL__" → spec 삭제됨.
    """
    spec = get_spec(session_id)
    if not spec:
        return {}, "__CANCEL__"

    params = _extract(message, project_id=project_id, tenant_id=tenant_id,
                      user_uid=user_uid, account_uid=account_uid)
    if params.get("cancel"):
        clear_spec(session_id)
        return {}, "__CANCEL__"

    if spec.get("mode") == "confirming":
        if params.get("confirmed"):
            spec["mode"] = "done"
            save_spec(session_id, spec)
            return spec, "__SAVE_SCHEDULE__"
        spec["mode"] = "gathering"

    if spec.get("day_of_month") is None and params.get("day_of_month") is not None:
        spec["day_of_month"] = params["day_of_month"]
    if spec.get("hour") is None and params.get("hour") is not None:
        spec["hour"] = params["hour"]
    if spec.get("minute") is None and params.get("minute") is not None:
        spec["minute"] = params["minute"]

    field = _required_field(spec)
    if field:
        save_spec(session_id, spec)
        return spec, _ask_text(field)

    spec["mode"] = "confirming"
    save_spec(session_id, spec)
    return spec, build_set_confirmation(spec)
