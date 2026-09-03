"""정기 보고서 무인 실행기 — 템플릿 하나를 받아 실제로 보고서를 생성·저장·기록한다.

트리거(이 함수를 주기적으로 호출하는 것)는 본프로젝트 자체 Schedule 시스템이 담당할 예정이라
여기서는 "호출되면 실행한다"까지만 담당한다. 등록 당시의 stepsjson(스텝·모듈·툴 + 실행에 쓴
SQL·표 형식)을 그대로 재생해 기간만 이번 회차로 바꾼다 — 회차마다 같은 보고서가 나와야 한다.
보고서 생성·Storage 업로드·실행 로그 기록(record_analytics)은 run_report_from_spec 안에서
이미 다 처리된다.
"""
from __future__ import annotations

import json
from datetime import date

from d2insight.chat import session as _session
from d2insight.chat.pipeline_runner import run_report_from_spec
from d2insight.chat.schedule_spec import compute_target_month
from d2insight.db.insight_storage import get_analytic_template


def run_scheduled_template(template_uid: str, run_date: date | None = None) -> dict:
    """템플릿 1건을 실행한다. 실패해도 예외를 던지지 않고 {"ok": False, "error": ...}를 반환한다
    (호출부인 스케줄러가 한 템플릿의 실패로 나머지 템플릿 실행을 멈추지 않도록)."""
    try:
        template = get_analytic_template(template_uid)
        if not template:
            return {"ok": False, "template_uid": template_uid, "error": "template not found"}
        if not template.get("scheduleactive"):
            return {"ok": False, "template_uid": template_uid, "error": "schedule inactive"}

        period = json.loads(template.get("periodjson") or "{}")
        report_type = period.get("report_type") or "판매분석"
        months_back = period.get("months_back") or 3
        target_month = compute_target_month(
            period.get("grain", "month"), period.get("offset", -1), run_date or date.today(),
        )

        # 등록 당시 스냅샷(stepsjson)을 그대로 지시서로 넘긴다 — 기간만 이번 회차로 바뀌고
        # 스텝·모듈·툴·SQL은 동일하게 돈다. 스냅샷이 없는 옛 템플릿은 예전처럼 새로 계획한다.
        spec = {"target_month": target_month, "report_type": report_type, "months_back": months_back}
        steps_json = json.loads(template.get("stepsjson") or "[]")
        if steps_json:
            spec["scenario_options"] = {"applied_steps": steps_json, "scenario": report_type}

        result = run_report_from_spec(
            spec,
            user_id=template.get("creator"),
            project_id=template.get("projectid"),
            tenant_id=template.get("tenantid"),
            session_id=template.get("sessionuid"),
        )

        answer_json = {
            "answer": result.get("answer", ""),
            "visualization_type": result.get("visualization_type", "none"),
            "table_html": result.get("table_html"),
            "applied_steps": result.get("applied_steps"),
            "analytic_uid": result.get("analytic_uid"),
            "execution_cache": result.pop("execution_cache", None),
        }
        qauid = _session.append_qa(
            template["sessionuid"],
            f"[정기 보고] {template.get('templatenm', '정기 보고서')}",
            answer_json,
            user_id=template.get("creator"),
            project_id=template.get("projectid"),
            filenm=result.get("report_path"),
            fileurl=result.get("fileurl"),
            servicecd="In",
        )

        return {
            "ok": True,
            "template_uid": template_uid,
            "qauid": qauid,
            "analytic_uid": result.get("analytic_uid"),
            "fileurl": result.get("fileurl"),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "template_uid": template_uid, "error": str(e)}
