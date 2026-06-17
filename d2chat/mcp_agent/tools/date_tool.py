"""
tools/date_tool.py
현재 날짜/시간 조회 Tool
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


class GetCurrentDateInput(BaseModel):
    """현재 날짜/시간 조회를 위한 입력 (파라미터 없음)"""
    pass


def get_current_date_tool() -> str:
    """현재 날짜와 시간 정보를 반환"""
    KST = ZoneInfo("Asia/Seoul")
    now = datetime.now(tz=KST)

    today = now.date()
    yesterday = today - timedelta(days=1)
    this_month_start = today.replace(day=1)
    last_month = (this_month_start - timedelta(days=1)).replace(day=1)

    result = {
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_date": today.strftime("%Y-%m-%d"),
        "current_year": now.year,
        "current_month": now.month,
        "current_day": now.day,
        "yesterday": yesterday.strftime("%Y-%m-%d"),
        "this_month_start": this_month_start.strftime("%Y-%m-%d"),
        "last_month_start": last_month.strftime("%Y-%m-%d"),
        "day_of_week": now.strftime("%A"),
        "day_of_week_kr": ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][now.weekday()]
    }
    return json.dumps(result, ensure_ascii=False)


def create_date_tool() -> StructuredTool:
    """date tool 인스턴스 생성"""
    return StructuredTool(
        name="get_current_date",
        description="현재 날짜와 시간 정보를 조회. '오늘', '어제', '이번 달', '지난달' 등 상대적 날짜가 포함된 질문에 반드시 먼저 사용해야 함",
        func=get_current_date_tool,
        args_schema=GetCurrentDateInput
    )
