"""대화형 보고서 명세(ReportSpec) 수집 및 관리."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
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


def _quick_chat(prompt: str, system: str, grade: str = "fast", max_tokens: int = 150,
                project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> str:
    from langchain_core.messages import SystemMessage, HumanMessage
    resp = _get_llm(grade, project_id=project_id, tenant_id=tenant_id,
                    user_uid=user_uid, account_uid=account_uid).invoke(
        [SystemMessage(content=system), HumanMessage(content=prompt)]
    )
    content = resp.content
    return content if isinstance(content, str) else content[0].text


# session_id → spec dict (인메모리)
_spec_store: dict[str, dict] = {}

ENTRY_QUESTION = "원하는 양식이나 형태가 있나요? 제가 일괄 작성할까요?"

_DEFAULTS: dict[str, object] = {
    "report_type": "판매분석",
    "months_back": 3,
    "top_n": 5,
    "threshold": "±3σ",
}

_SUGGESTIONS: dict[str, str] = {
    "report_type": "어떤 유형의 보고서인가요? (예: 판매분석, 경영분석, 품질분석, 기술분석)",
    "months_back": "이전 3개월 자료로 분석하면 될까요?",
    "top_n": "주요 품목 상위 5개까지 분석하면 될까요?",
    "threshold": "증감 기준은 ±3σ로 하면 될까요?",
}

_REPORT_TYPE_LIST = "경영분석, 판매분석, 생산분석, 원가분석, 품질분석, 구매조달분석, 재고물류분석, 고객분석, 마케팅분석, 인사분석, 재무분석, 기술분석, 리스크분석, 기타"

_EXTRACT_SYSTEM = f"""사용자 메시지에서 보고서 파라미터를 추출하여 JSON만 응답하세요. 설명 없이 JSON 객체만 출력하세요.

추출 규칙:
- target_month: 메시지 첫 줄의 오늘 날짜를 기준으로 계산. "2013년 3월"→"2013-03", "올해 3월"→오늘연도-03, "작년 3월"→전년도-03, 언급 없으면 null
- report_type: [{_REPORT_TYPE_LIST}] 중 하나. "판매/매출/영업" → 판매분석, "서버/로그/IT" → 기술분석, 언급 없으면 null
- months_back: "3개월"→3, "6개월"→6, "1년"→12, "반년"→6, "작년 1년치"→12, 언급 없으면 null
- top_n: "5개", "상위 10개" → 숫자(개수). "상위 30%" 같은 비율 표현은 null. 언급 없으면 null
- threshold: 반드시 수치(숫자+단위)가 있어야 추출. "±3σ"→"±3σ", "2시그마"→"2시그마", "전월대비 25%"→"전월대비 25%". 수치 없는 경우 → null
- accepted_default: "네", "그렇게", "좋아요", "알아서", "맞아요", "그렇게 해주세요" → true
- bulk: "일괄 작성", "일괄로", "바로 해주세요", "그냥 해주세요", "기본으로", "알아서 해주세요" → true
- confirmed: "네 시작", "생성해", "작성해", "맞아요 진행" 등 확인 단계 최종 승인 → true
- cancel: "취소", "그만", "다시 할게요", "안 해도 돼", "그만둘게요" → true

응답 JSON:
{{"target_month": null, "report_type": null, "months_back": null, "top_n": null, "threshold": null, "accepted_default": false, "bulk": false, "confirmed": false, "cancel": false}}"""


def get_spec(session_id: str) -> Optional[dict]:
    return _spec_store.get(session_id)


def save_spec(session_id: str, spec: dict) -> None:
    _spec_store[session_id] = spec


def clear_spec(session_id: str) -> None:
    _spec_store.pop(session_id, None)


def create_spec(
    target_month: Optional[str],
    report_type: Optional[str],
    months_back: Optional[int] = None,
) -> dict:
    return {
        "target_month": target_month,
        "report_type": report_type or None,
        "months_back": None,
        "top_n": None,
        "threshold": None,
        "bulk_mode": False,
        "entry_asked": False,
        "mode": "gathering",
    }


def is_required_complete(spec: dict) -> bool:
    return bool(spec.get("target_month"))


def _current_question_field(spec: dict) -> Optional[str]:
    for field in ("report_type", "months_back", "top_n", "threshold"):
        if spec.get(field) is None:
            return field
    return None


def next_suggestion(spec: dict) -> Optional[str]:
    field = _current_question_field(spec)
    return _SUGGESTIONS.get(field) if field else None


def _apply_defaults(spec: dict) -> None:
    for field, default in _DEFAULTS.items():
        if spec.get(field) is None:
            spec[field] = default


def build_confirmation(spec: dict) -> str:
    return (
        "아래 조건으로 보고서를 작성합니다:\n\n"
        f"- 기간        : {spec.get('target_month')} (월간)\n"
        f"- 유형        : {spec.get('report_type', '판매분석')} 보고서\n"
        f"- 기준 데이터 : 이전 {spec.get('months_back', 3)}개월\n"
        f"- 분석 품목   : 상위 {spec.get('top_n', 5)}개\n"
        f"- 이상치 기준 : {spec.get('threshold', '±3σ')}\n\n"
        "작성을 시작할까요? (네 / 수정)"
    )


def _extract_params(message: str, spec: dict, history: list[dict] | None = None,
                    project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> dict:
    defaults = {
        "target_month": None, "report_type": None, "months_back": None, "top_n": None,
        "threshold": None, "accepted_default": False, "bulk": False, "confirmed": False, "cancel": False,
    }
    today = datetime.now(tz=_KST).strftime("%Y-%m-%d")
    hist_text = ""
    if history:
        recent = [m for m in history if m.get("role") == "user"][-10:]
        if recent:
            hist_text = "이전 대화 (참고용):\n" + "\n".join(
                f"사용자: {m.get('content', '')[:200]}" for m in recent
            ) + "\n\n"
    try:
        raw = _quick_chat(
            (
                f"오늘 날짜: {today}\n"
                f"{hist_text}"
                f"현재 수집된 정보: {json.dumps(spec, ensure_ascii=False)}\n"
                f"사용자 메시지: {message}"
            ),
            system=_EXTRACT_SYSTEM,
            grade="fast",
            max_tokens=150,
            project_id=project_id,
            tenant_id=tenant_id,
            user_uid=user_uid,
            account_uid=account_uid,
        )
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            defaults.update(json.loads(m.group()))
    except Exception as e:
        print(f"[report_spec] _extract_params error: {e}")
    return defaults


def advance_spec(session_id: str, message: str, history: list[dict] | None = None,
                 project_id=None, tenant_id=None, user_uid=None, account_uid=None) -> tuple[dict, str]:
    """사용자 메시지로 spec을 진행시키고 (updated_spec, bot_response)를 반환.

    bot_response 특수값:
      "__EXECUTE__" → 호출자가 보고서 생성 실행
      "__CANCEL__"  → spec 삭제됨, 취소 메시지 출력
    """
    spec = get_spec(session_id)
    if not spec:
        return {}, "__CANCEL__"

    params = _extract_params(message, spec, history=history, project_id=project_id, tenant_id=tenant_id,
                             user_uid=user_uid, account_uid=account_uid)

    if params.get("cancel"):
        clear_spec(session_id)
        return {}, "__CANCEL__"

    if params.get("bulk"):
        spec["bulk_mode"] = True
        _apply_defaults(spec)
        if params.get("target_month") and not spec.get("target_month"):
            spec["target_month"] = params["target_month"]
        if is_required_complete(spec):
            spec["mode"] = "done"
            save_spec(session_id, spec)
            return spec, "__EXECUTE__"
        save_spec(session_id, spec)
        return spec, "분석 기준월을 알려주세요. (예: 2013년 3월)"

    if spec.get("mode") == "confirming":
        if params.get("confirmed"):
            spec["mode"] = "done"
            save_spec(session_id, spec)
            return spec, "__EXECUTE__"
        spec["mode"] = "gathering"

    if params.get("target_month") and not spec.get("target_month"):
        spec["target_month"] = params["target_month"]

    field = _current_question_field(spec)
    if field:
        if params.get("accepted_default"):
            spec[field] = _DEFAULTS[field]
        elif params.get(field) is not None:
            spec[field] = params[field]

    for f in ("report_type", "months_back", "top_n", "threshold"):
        if spec.get(f) is None and params.get(f) is not None:
            spec[f] = params[f]

    if not is_required_complete(spec):
        save_spec(session_id, spec)
        return spec, "분석 기준월을 알려주세요. (예: 2013년 11월)"

    if not spec.get("entry_asked"):
        spec["entry_asked"] = True
        save_spec(session_id, spec)
        return spec, ENTRY_QUESTION

    if spec.get("bulk_mode"):
        _apply_defaults(spec)
        spec["mode"] = "done"
        save_spec(session_id, spec)
        return spec, "__EXECUTE__"

    suggestion = next_suggestion(spec)
    if suggestion:
        save_spec(session_id, spec)
        return spec, suggestion

    spec["mode"] = "confirming"
    save_spec(session_id, spec)
    return spec, build_confirmation(spec)
