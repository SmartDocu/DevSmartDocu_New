"""insight_sessions + insight_qas CRUD (pr_d2chat supabase_storage.py 패턴)."""
from __future__ import annotations

import json
import re
from typing import Optional

from d2insight.db import supabase_client as _sc
from d2insight.db.supabase_client import build_shares_path, delete_from_storage
from utilsPrj.private_storage import resolve_display_url


# ── Timezone ────────────────────────────────────────────────────

def get_offsetminutes(user_id: str | None) -> int | None:
    """tenantusers.timezone → tenants.timezone → timezones.offsetminutes 순으로 조회."""
    if not user_id:
        return None
    try:
        rows = (
            _sc.table("tenantusers").select("timezone,tenantid")
            .eq("useruid", user_id).eq("useyn", True).limit(1).execute().data or []
        )
        if not rows:
            return None
        tz = rows[0].get("timezone")
        if not tz and rows[0].get("tenantid"):
            t = _sc.table("tenants").select("timezone").eq("tenantid", rows[0]["tenantid"]).maybe_single().execute()
            if t and t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = _sc.table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row and tz_row.data else None
    except Exception:
        return None


def _fmt_dt(raw, offsetminutes: int | None = None) -> str:
    if not raw:
        return ""
    try:
        from datetime import timedelta, timezone as _tz
        from dateutil import parser as dtparser
        dt = dtparser.parse(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(_tz.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(raw)


# ── 사용자 / 프로젝트 정보 ────────────────────────────────────────

def get_project_info(user_uid: str) -> tuple[int | None, int | None]:
    """projects 테이블에서 tenantid, projectid 반환 (pr_d2chat 패턴)."""
    try:
        res = _sc.table("projects").select("tenantid,projectid").eq("creator", user_uid).execute()
        if res.data:
            row = res.data[0]
            return row.get("tenantid"), row.get("projectid")
    except Exception:
        pass
    return None, None


# ── 세션 ──────────────────────────────────────────────────────────

def create_session(tenant_id: int | None, project_id: int | None, creator: str | None) -> str:
    """insight_sessions 레코드를 생성하고 sessionuid를 반환한다."""
    res = _sc.table("insight_sessions").insert({
        "tenantid": tenant_id or None,
        "projectid": project_id or None,
        "sessiontitles": "",
        "sessionstatuscd": "Active",
        "creator": creator or None,
    }).execute()
    return res.data[0]["sessionuid"]


def get_session(session_uid: str) -> dict | None:
    res = (
        _sc.table("insight_sessions")
        .select("*")
        .eq("sessionuid", session_uid)
        .execute()
    )
    return res.data[0] if res.data else None


def update_session_title(session_uid: str, title: str) -> None:
    _sc.table("insight_sessions").update({"sessiontitles": title}).eq("sessionuid", session_uid).execute()


def delete_session(session_uid: str, creator: str) -> bool:
    """소프트 삭제 — sessionstatuscd를 Archived로 변경."""
    _sc.table("insight_sessions").update({"sessionstatuscd": "Archived"}).eq("sessionuid", session_uid).eq("creator", creator).execute()
    return True


def get_history_by_date(creator: str, offsetminutes: int | None = None) -> dict:
    """날짜별로 그룹화된 세션 목록을 반환한다.

    정기 보고서로 등록된 세션은 is_schedule=True, schedule_active, title(템플릿명)을
    덧붙인다 — 사이드바가 "정기 보고서" 섹션과 일반 "대화 목록"을 구분해 보여준다.
    """
    try:
        q = (
            _sc.table("insight_sessions")
            .select("sessionuid, sessiontitles, createdts")
            .eq("sessionstatuscd", "Active")
            .neq("sessiontitles", "")
            .order("createdts", desc=True)
        )
        if creator:
            q = q.eq("creator", creator)
        res = q.execute()

        templates_by_session: dict[str, dict] = {}
        try:
            tres = (
                _sc.table("analytictemplates")
                .select("sessionuid, templatenm, scheduleactive")
                .eq("creator", creator)
                .execute()
            )
            for t in (tres.data or []):
                templates_by_session[t["sessionuid"]] = t
        except Exception:
            pass

        # 정기 보고서 세션의 현재 활성 공유 여부 — 사이드바가 메뉴를 열 때마다 별도 조회하지
        # 않도록 목록 응답에 share_uid를 함께 내려준다(pr_module_insight와 동일한 방식).
        shares_by_session: dict[str, str] = {}
        try:
            sres = (
                _sc.table("insightscheduleshares")
                .select("sessionuid, shareuid")
                .eq("creator", creator)
                .is_("enddts", "null")
                .execute()
            )
            for s in (sres.data or []):
                shares_by_session[s["sessionuid"]] = s["shareuid"]
        except Exception:
            pass

        grouped: dict = {}
        for row in (res.data or []):
            formatted = _fmt_dt(row.get("createdts", ""), offsetminutes)
            date_key = formatted[:10]
            if date_key not in grouped:
                grouped[date_key] = []
            template = templates_by_session.get(row["sessionuid"])
            item = {
                "session_id": row["sessionuid"],
                "title": template["templatenm"] if template else row.get("sessiontitles", ""),
                "created_at": formatted,
            }
            if template:
                item["is_schedule"] = True
                item["schedule_active"] = bool(template.get("scheduleactive"))
                item["share_uid"] = shares_by_session.get(row["sessionuid"])
            grouped[date_key].append(item)
        return grouped
    except Exception:
        return {}


_PERIOD_FROM_FILENAME = re.compile(r"^[^_]+_([^_]+)_\d{8}_\d{6}\.md$")


def _parse_target_period(filenm: str | None) -> str | None:
    """생성 파일명에서 대상 기간(예: "2026-07")을 뽑는다. 못 뽑으면 None."""
    if not filenm:
        return None
    m = _PERIOD_FROM_FILENAME.match(filenm)
    return m.group(1) if m else None


def get_schedule_turns(session_uid: str, until: str | None = None) -> list[dict]:
    """정기 보고서 세션의 실행 턴 목록(최근 대상기간순) — 사이드바가 펼쳐 보여줄 때 쓴다.

    until이 있으면 그 시각 이후 생성된 턴은 제외한다 — 공유 종료 이후 회차를
    공유받은 사람에게 숨길 때 쓴다.
    """
    q = (
        _sc.table("insight_qas")
        .select("qauid, question, answer, filenm, fileurl, createdts")
        .eq("sessionuid", session_uid)
    )
    if until:
        q = q.lte("createdts", until)
    res = q.order("createdts", desc=True).execute()
    turns: list[dict] = []
    for row in (res.data or []):
        try:
            obj = json.loads(row["answer"])
            if isinstance(obj, dict):
                answer_text = obj.get("answer", "")
                applied_steps = obj.get("applied_steps")
                scenario = obj.get("scenario")
            else:
                answer_text, applied_steps, scenario = str(obj), None, None
        except (json.JSONDecodeError, TypeError):
            answer_text, applied_steps, scenario = row.get("answer") or "", None, None
        turns.append({
            "qauid": row["qauid"],
            "question": row["question"],
            "answer": answer_text,
            "filenm": row.get("filenm"),
            "fileurl": resolve_display_url(_sc.get_client(), row.get("fileurl")),
            "target_period": _parse_target_period(row.get("filenm")),
            "created_at": row.get("createdts"),
            "appliedSteps": applied_steps,
            "scenario": scenario,
        })
    turns.sort(key=lambda t: (t["target_period"] is not None, t["target_period"] or "", t["created_at"] or ""),
               reverse=True)
    return turns


def delete_qa(qauid: str, creator: str) -> bool:
    """정기 보고서 회차(QA) 하드 삭제 — 되돌릴 수 없다. creator 소유 확인 포함."""
    _sc.table("insight_qas").delete().eq("qauid", qauid).eq("creator", creator).execute()
    return True


SCHEDULE_ORIGIN_MARKER = "[정기 보고서 등록]"   # 정기 보고서 등록 시 원본 보고서를 시드로 남길 때
# 붙이는 질문 접두사(schedule_register 참조) — 같은 문자열을 여기서도 "이 보고서가 이미 정기
# 등록의 원본으로 쓰였는지" 판정하는 데 쓴다(is_report_already_scheduled).


def _already_scheduled_filenms(filenms: list[str]) -> set[str]:
    if not filenms:
        return set()
    res = (
        _sc.table("insight_qas")
        .select("filenm")
        .in_("filenm", filenms)
        .like("question", f"{SCHEDULE_ORIGIN_MARKER}%")
        .execute()
    )
    return {r["filenm"] for r in res.data if r.get("filenm")}


def is_report_already_scheduled(report_path: str | None) -> bool:
    """이 보고서(파일명)가 이미 정기 보고서 등록의 원본으로 쓰였는지 — 같은 보고서를 두 번
    정기 등록하는 걸 막는 데 쓴다."""
    if not report_path:
        return False
    return bool(_already_scheduled_filenms([report_path]))


def get_analytic_scenario_nm(analytic_uid: str | None) -> str | None:
    """analytics.scenarionm 조회 — 정기 보고서 등록 시 템플릿 이름(f"{scenario_nm} 정기 보고서")의
    근거가 된다(record_analytics가 저장한 report_type이 여기 scenarionm으로 들어있다)."""
    if not analytic_uid:
        return None
    res = _sc.table("analytics").select("scenarionm").eq("analyticuid", analytic_uid).execute()
    return res.data[0].get("scenarionm") if res.data else None


# ── Q&A ──────────────────────────────────────────────────────────

def append_qa(
    session_uid: str,
    tenant_id: int | None,
    project_id: int | None,
    question: str,
    answer_json: dict,
    creator: str | None,
    filenm: str | None = None,
    fileurl: str | None = None,
    inputtoken: int | None = None,
    outputtoken: int | None = None,
    servicecd: str = "In",
) -> str:
    """QA를 insight_qas에 저장하고 qauid를 반환한다.

    첫 QA 저장 시 세션 제목을 질문 앞 50자로 자동 설정한다.
    """
    row: dict = {
        "sessionuid": session_uid,
        "tenantid": tenant_id or None,
        "projectid": project_id or None,
        "question": question,
        "answer": json.dumps(answer_json, ensure_ascii=False),
        "creator": creator or None,
        "favoriteyn": False,
        "servicecd": servicecd,
    }
    if filenm:
        row["filenm"] = filenm
    if fileurl:
        row["fileurl"] = fileurl
    if inputtoken is not None:
        row["inputtoken"] = inputtoken
    if outputtoken is not None:
        row["outputtoken"] = outputtoken

    res = _sc.table("insight_qas").insert(row).execute()
    qauid: str = res.data[0]["qauid"]

    session = get_session(session_uid)
    if session and not session.get("sessiontitles"):
        update_session_title(session_uid, question[:50])

    return qauid


def get_session_messages(session_uid: str) -> list[dict]:
    """LLM 컨텍스트 + 히스토리 뷰용 메시지 배열 반환.

    assistant 메시지의 appliedSteps는 그 보고서 생성 시 실제로 호출된 도구/파라미터
    내역이다(우측 옵션 패널이 히스토리 조회 시 이 값으로 당시 내역을 복원한다).
    """
    res = (
        _sc.table("insight_qas")
        .select("qauid, question, answer, filenm, fileurl")
        .eq("sessionuid", session_uid)
        .order("createdts", desc=False)
        .execute()
    )
    filenms = [row["filenm"] for row in res.data if row.get("filenm")]
    scheduled_filenms = _already_scheduled_filenms(filenms)

    messages: list[dict] = []
    for row in res.data:
        messages.append({"role": "user", "content": row["question"], "qauid": row["qauid"]})
        try:
            obj = json.loads(row["answer"])
            if isinstance(obj, dict):
                answer_text = obj.get("answer", "")
                applied_steps = obj.get("applied_steps")
            else:
                answer_text, applied_steps = str(obj), None
        except (json.JSONDecodeError, TypeError):
            answer_text, applied_steps = row["answer"] or "", None
        filenm = row.get("filenm")
        messages.append({
            "role": "assistant",
            "content": answer_text,
            "reportPath": filenm,
            "fileurl": resolve_display_url(_sc.get_client(), row.get("fileurl")),
            "qauid": row["qauid"],
            "appliedSteps": applied_steps,
            "isTemplate": bool(filenm) and filenm in scheduled_filenms,
        })
    return messages


def get_qa(qauid: str) -> dict | None:
    res = _sc.table("insight_qas").select("*").eq("qauid", qauid).execute()
    return res.data[0] if res.data else None


def get_last_report_qa(session_uid: str) -> dict | None:
    """이 세션에서 가장 최근에 생성된 보고서 QA 한 건을 반환한다(없으면 None).

    정기 보고서 등록 시 이 QA의 applied_steps를 스냅샷으로 떠서 analytictemplates에 저장한다.
    """
    res = (
        _sc.table("insight_qas")
        .select("qauid, question, answer, filenm, fileurl, createdts")
        .eq("sessionuid", session_uid)
        .not_.is_("filenm", "null")
        .order("createdts", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    try:
        obj = json.loads(row["answer"])
    except (json.JSONDecodeError, TypeError):
        obj = {}
    return {
        "qauid": row["qauid"],
        "question": row["question"],
        "filenm": row.get("filenm"),
        "fileurl": resolve_display_url(_sc.get_client(), row.get("fileurl")),
        "applied_steps": obj.get("applied_steps") if isinstance(obj, dict) else None,
        "analytic_uid": obj.get("analytic_uid") if isinstance(obj, dict) else None,
    }


# ── 실행 로그 (Analytics / AnalyticSteps / AnalyticModules) ────────
# 카탈로그(ScenarioModules/ScenarioTools) 없이 자유 텍스트 + params JSON만으로 기록한다.
# scenariouid/tool_uid 등 카탈로그 FK 컬럼은 이 프로젝트에 카탈로그가 없어 항상 null —
# pr_module_insight도 카탈로그 미등록 항목은 이미 이렇게 null로 기록하고 있다(실측 확인).

def record_analytics(
    tenant_id: int | None,
    project_id: int | None,
    scenario_nm: str,
    applied_steps: list[dict] | None,
    creator: str | None,
) -> str | None:
    """보고서 한 건의 실행 내역을 Analytics/AnalyticSteps/AnalyticModules에 기록하고
    analyticuid를 반환한다. applied_steps가 비어 있으면 기록하지 않고 None을 반환한다."""
    if not applied_steps:
        return None

    analytic = (
        _sc.table("analytics")
        .insert({
            "tenantid": tenant_id,
            "projectid": project_id,
            "scenarionm": scenario_nm,
            "creator": creator,
        })
        .execute()
    )
    analytic_uid = analytic.data[0]["analyticuid"]

    for step_idx, step in enumerate(applied_steps):
        step_row = (
            _sc.table("analyticsteps")
            .insert({
                "tenantid": tenant_id,
                "projectid": project_id,
                "analyticuid": analytic_uid,
                "stepnm": step.get("title") or step.get("step") or f"스텝 {step_idx + 1}",
                "orderno": step_idx,
                "useyn": True,
            })
            .execute()
        )
        step_uid = step_row.data[0]["stepuid"]

        for tool_idx, call in enumerate(step.get("tools") or []):
            tools_json = {
                "module_id": call.get("tool"),
                "tool_uid": None,
                "tool_nm": None,
                "desc": None,
                "params": call.get("params"),
            }
            _sc.table("analyticmodules").insert({
                "tenantid": tenant_id,
                "projectid": project_id,
                "analyticuid": analytic_uid,
                "stepuid": step_uid,
                "tools": json.dumps(tools_json, ensure_ascii=False),
                "orderno": tool_idx,
            }).execute()

    return analytic_uid


def create_analytic_template(
    tenant_id: int | None,
    project_id: int | None,
    session_uid: str,
    template_nm: str,
    period_json: dict,
    global_json: dict,
    steps_json: list | None,
    schedule_cron: str,
    schedule_start_dt: str,
    creator: str | None,
    analytic_uid: str | None = None,
) -> str:
    """정기 보고서 정의를 analytictemplates에 기록하고 templateuid를 반환한다.

    실제 스케줄 트리거·다음 실행일 계산은 본프로젝트 Schedule 쪽(UserScheduleMasters 등)이
    담당한다 — 여기서는 "무엇을 어떤 조건으로 반복 생성할지"의 스냅샷만 남긴다.
    analytic_uid는 이 템플릿의 출처가 된 실행(Analytics) 1건을 가리킨다 — 없으면 null.
    """
    row = {
        "tenantid": tenant_id,
        "projectid": project_id,
        "sessionuid": session_uid,
        "analyticuid": analytic_uid,
        "templatenm": template_nm,
        "is_standard": False,
        "periodjson": json.dumps(period_json, ensure_ascii=False),
        "globaljson": json.dumps(global_json or {}, ensure_ascii=False),
        "stepsjson": json.dumps(steps_json or [], ensure_ascii=False),
        "schedulecron": schedule_cron,
        "schedulestartdt": schedule_start_dt,
        "scheduleactive": True,
        "useyn": True,
        "creator": creator,
    }
    res = _sc.table("analytictemplates").insert(row).execute()
    return res.data[0]["templateuid"]


def get_active_template_by_session(session_uid: str) -> dict | None:
    """세션에 연결된 활성 정기 보고서 템플릿 1건(최신)을 반환한다 — 없으면 None.

    등록 중복 방지("이 세션엔 이미 활성 템플릿이 있다")와 수정 화면의 현재 설정 조회에 쓴다.
    """
    res = (
        _sc.table("analytictemplates")
        .select("*")
        .eq("sessionuid", session_uid)
        .eq("scheduleactive", True)
        .order("createdts", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_analytic_template(template_uid: str) -> dict | None:
    """templateuid로 정기 보고서 템플릿 1건을 조회한다 — 무인 실행기가 사용."""
    res = (
        _sc.table("analytictemplates")
        .select("*")
        .eq("templateuid", template_uid)
        .execute()
    )
    return res.data[0] if res.data else None


def update_analytic_template_schedule(template_uid: str, schedule_cron: str, schedule_start_dt: str) -> None:
    """정기 보고서 일정(cron/시작일)을 변경한다."""
    (
        _sc.table("analytictemplates")
        .update({"schedulecron": schedule_cron, "schedulestartdt": schedule_start_dt})
        .eq("templateuid", template_uid)
        .execute()
    )


def get_qa_count(session_uid: str) -> int:
    res = (
        _sc.table("insight_qas")
        .select("qauid", count="exact")
        .eq("sessionuid", session_uid)
        .execute()
    )
    return res.count or 0


def insert_llm_api_logs(
    calls: list[dict],
    qauid: str,
    session_uid: str,
    tenant_id: int | None,
    project_id: int | None,
    creator: str | None,
    questiontypecd: str,
    account_uid: str | None = None,
    is_customeraikey: bool | None = None,
) -> None:
    """LLM 호출 명세를 llminsightlogs에 일괄 삽입한다."""
    if not calls:
        return
    rows = []
    for c in calls:
        _start = c.get("startdts")
        _end = c.get("enddts")
        rows.append({
            "qauid": qauid,
            "questiontypecd": questiontypecd,
            "tenantid": tenant_id or None,
            "accountuid": account_uid or None,
            "projectid": project_id or None,
            "sessionuid": session_uid,
            "stepnm": c.get("stepnm") or None,
            "steptitle": c.get("steptitle") or None,
            "llmmodelnm": c.get("model_id") or c.get("model") or None,
            "inputtoken": c.get("input", 0),
            "outputtoken": c.get("output", 0),
            "is_success": True,
            "is_customeraikey": is_customeraikey,
            "creator": creator or None,
            "startdts": _start.isoformat() if _start else None,
            "enddts": _end.isoformat() if _end else None,
        })
    try:
        _sc.table("llminsightlogs").insert(rows).execute()
    except Exception as e:
        # print(f"[insight_storage] insert_llm_api_logs 오류: {e}")
        pass


# ── 즐겨찾기 ─────────────────────────────────────────────────────

def add_favorite_qa(qauid: str, creator: str) -> bool:
    """QA를 insight_favorites에 복사한다."""
    qa = get_qa(qauid)
    if not qa:
        return False
    try:
        _sc.table("insight_favorites").insert({
            "tenantid": qa.get("tenantid"),
            "projectid": qa.get("projectid"),
            "sessionuid": qa.get("sessionuid"),
            "qauid": qauid,
            "question": qa.get("question"),
            "answer": qa.get("answer"),
            "fileurl": qa.get("fileurl"),
            "filenm": qa.get("filenm"),
            "creator": creator or None,
        }).execute()
        _sc.table("insight_qas").update({"favoriteyn": True}).eq("qauid", qauid).execute()
        return True
    except Exception:
        return False


def remove_favorite_qa(qauid: str, creator: str) -> bool:
    """insight_favorites에서 삭제하고 원본 QA의 favoriteyn을 False로 설정한다."""
    try:
        _sc.table("insight_favorites").delete().eq("qauid", qauid).eq("creator", creator).execute()
        _sc.table("insight_qas").update({"favoriteyn": False}).eq("qauid", qauid).execute()
        return True
    except Exception:
        return False


def get_favorites(creator: str, offsetminutes: int | None = None) -> list[dict]:
    """내 즐겨찾기 목록을 반환한다."""
    try:
        res = (
            _sc.table("insight_favorites")
            .select("favoriteuid, qauid, sessionuid, question, answer, filenm, createdts")
            .eq("creator", creator)
            .order("createdts", desc=True)
            .execute()
        )
        result = []
        for row in (res.data or []):
            answer_text = ""
            try:
                obj = json.loads(row.get("answer") or "{}")
                answer_text = obj.get("answer", "") if isinstance(obj, dict) else ""
            except Exception:
                pass
            result.append({
                "favoriteuid": row["favoriteuid"],
                "qauid": row["qauid"],
                "session_id": row.get("sessionuid"),
                "question": row.get("question", ""),
                "answer": answer_text,
                "filenm": row.get("filenm"),
                "fileurl": resolve_display_url(_sc.get_client(), row.get("fileurl")),
                "created_at": _fmt_dt(row.get("createdts"), offsetminutes),
            })
        return result
    except Exception:
        return []


# ── 폴더 ─────────────────────────────────────────────────────────

def get_folders(tenant_id: int | None) -> list[dict]:
    """insight_folders에서 폴더 목록 반환 (삭제되지 않은 것만)."""
    try:
        q = (
            _sc.table("insight_folders")
            .select("folderuid, foldernm, folderlevel, parent_folderuid, orderno")
            .neq("is_deleted", True)
            .order("folderlevel")
            .order("orderno")
        )
        if tenant_id is not None:
            q = q.or_(f"tenantid.eq.{tenant_id},tenantid.is.null")
        res = q.execute()
        return res.data or []
    except Exception as e:
        # print(f"[insight_storage] get_folders 오류: {e}")
        pass
        return []


def seed_sample_folders(tenant_id: int | None, creator: str | None) -> None:
    """폴더가 없으면 샘플 폴더를 삽입한다."""
    try:
        if get_folders(tenant_id):
            return

        safe_creator = creator if creator and creator != "undefined" else None
        base = {"tenantid": tenant_id, "creator": safe_creator}

        sales_res = _sc.table("insight_folders").insert(
            {**base, "foldernm": "판매", "folderlevel": 1, "orderno": 1}
        ).execute()
        sales_uid = sales_res.data[0]["folderuid"]

        _sc.table("insight_folders").insert([
            {**base, "foldernm": "서버로그",       "folderlevel": 1, "orderno": 2},
            {**base, "foldernm": "인터페이스로그", "folderlevel": 1, "orderno": 3},
        ]).execute()

        _sc.table("insight_folders").insert(
            {**base, "foldernm": "지역", "folderlevel": 2, "orderno": 1,
             "parent_folderuid": sales_uid}
        ).execute()

        # print(f"[insight_storage] 샘플 폴더 생성 완료 (tenant_id={tenant_id})")
    except Exception as e:
        # print(f"[insight_storage] seed_sample_folders 오류: {e}")
        pass


# ── 공유 ─────────────────────────────────────────────────────────

def share_qa(qauid: str, creator: str, folder_uid: str | None = None) -> bool:
    """QA를 insight_qa_shares에 복사해 같은 tenant에 공유한다."""
    qa = get_qa(qauid)
    if not qa:
        return False
    tenant_id, project_id = get_project_info(creator)
    try:
        src_fileurl = qa.get("fileurl") or ""
        filenm = qa.get("filenm") or ""

        if src_fileurl.endswith(".pdf"):
            share_fileurl = src_fileurl[:-4] + ".md"
        else:
            share_fileurl = src_fileurl

        row: dict = {
            "tenantid": tenant_id,
            "projectid": project_id,
            "sessionuid": qa.get("sessionuid"),
            "question": qa.get("question"),
            "answer": qa.get("answer"),
            "fileurl": share_fileurl,
            "filenm": filenm,
            "creator": creator or None,
        }
        if folder_uid:
            row["folderuid"] = folder_uid
        _sc.table("insight_qa_shares").insert(row).execute()
        return True
    except Exception as e:
        # print(f"[insight_storage] share_qa 오류: {e}")
        pass
        return False


def get_shares_sent(creator: str, offsetminutes: int | None = None) -> list[dict]:
    """내가 공유한 QA 목록을 반환한다."""
    try:
        res = (
            _sc.table("insight_qa_shares")
            .select("qauid, sessionuid, question, answer, filenm, fileurl, createdts")
            .eq("creator", creator)
            .order("createdts", desc=True)
            .execute()
        )
        return _format_share_rows(res.data or [], offsetminutes)
    except Exception:
        return []


def delete_share_sent(share_qauid: str, creator: str) -> bool:
    """내가 공유한 레코드를 삭제하고 공유 스토리지 파일도 함께 삭제한다."""
    try:
        row = get_share(share_qauid)
        if not row:
            return False
        if row.get("creator") != creator:
            return False

        fileurl: str = row.get("fileurl") or ""
        filenm: str = row.get("filenm") or ""
        if fileurl and filenm:
            try:
                tenant_id, project_id = get_project_info(creator)
                pdf_filename = filenm.replace(".md", ".pdf")
                storage_path = build_shares_path(tenant_id, project_id, pdf_filename)
                delete_from_storage(storage_path)
            except Exception as se:
                # print(f"[insight_storage] 공유 스토리지 파일 삭제 실패: {se}")
                pass

        _sc.table("insight_qa_shares").delete().eq("qauid", share_qauid).execute()
        return True
    except Exception as e:
        # print(f"[insight_storage] delete_share_sent 오류: {e}")
        pass
        return False


def get_all_shares(project_id: int | None, offsetminutes: int | None = None) -> list[dict]:
    """같은 project의 모든 공유 보고서 반환."""
    try:
        q = (
            _sc.table("insight_qa_shares")
            .select("qauid, sessionuid, question, answer, filenm, fileurl, creator, createdts, folderuid")
            .order("createdts", desc=True)
        )
        if project_id is not None:
            q = q.or_(f"projectid.eq.{project_id},projectid.is.null")
        else:
            q = q.is_("projectid", "null")
        res = q.execute()
        return _format_share_rows(res.data or [], offsetminutes)
    except Exception:
        return []


def get_shares_received(project_id: int | None, my_creator: str, offsetminutes: int | None = None) -> list[dict]:
    """같은 projectid에서 내가 creator가 아닌 공유 QA 목록을 반환한다."""
    try:
        q = (
            _sc.table("insight_qa_shares")
            .select("qauid, sessionuid, question, answer, filenm, fileurl, creator, createdts")
            .neq("creator", my_creator)
            .order("createdts", desc=True)
        )
        if project_id is not None:
            q = q.or_(f"projectid.eq.{project_id},projectid.is.null")
        else:
            q = q.is_("projectid", "null")
        res = q.execute()
        return _format_share_rows(res.data or [], offsetminutes)
    except Exception:
        return []


def delete_share_received(share_qauid: str, creator: str) -> bool:
    """공유받은 항목을 목록에서 제거한다."""
    try:
        _sc.table("insight_qa_shares").delete().eq("qauid", share_qauid).execute()
        return True
    except Exception:
        return False


def get_share(share_qauid: str) -> dict | None:
    """공유된 단일 QA 조회."""
    try:
        res = _sc.table("insight_qa_shares").select("*").eq("qauid", share_qauid).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def _format_share_rows(rows: list[dict], offsetminutes: int | None = None) -> list[dict]:
    result = []
    for row in rows:
        answer_text = ""
        try:
            obj = json.loads(row.get("answer") or "{}")
            answer_text = obj.get("answer", "") if isinstance(obj, dict) else ""
        except Exception:
            pass
        result.append({
            "share_qauid": row["qauid"],
            "session_id": row.get("sessionuid"),
            "question": row.get("question", ""),
            "answer": answer_text,
            "filenm": row.get("filenm"),
            "fileurl": resolve_display_url(_sc.get_client(), row.get("fileurl")),
            "folder_uid": row.get("folderuid"),
            "creator": row.get("creator"),
            "created_at": _fmt_dt(row.get("createdts"), offsetminutes),
        })
    return result


# ── 정기 보고서 공유 ────────────────────────────────────────────

def share_schedule_session(session_uid: str, tenant_id: int | None, project_id: int | None,
                            creator: str) -> str | None:
    """정기 보고서 세션 전체를 공유한다(회차 단위가 아니라 세션 단위) — insightscheduleshares에
    1건 기록하고 shareuid를 반환한다."""
    res = (
        _sc.table("insightscheduleshares")
        .insert({
            "tenantid": tenant_id,
            "projectid": project_id,
            "sessionuid": session_uid,
            "creator": creator,
        })
        .execute()
    )
    return res.data[0]["shareuid"] if res.data else None


def get_schedule_share(share_uid: str) -> dict | None:
    """공유된 정기 보고서 세션 1건 조회."""
    res = _sc.table("insightscheduleshares").select("*").eq("shareuid", share_uid).execute()
    return res.data[0] if res.data else None


def end_schedule_share(share_uid: str, end_dt: str) -> bool:
    """정기 보고서 공유를 종료한다(소프트 종료 — enddts만 채움, row는 유지).

    공유자·수신자 모두 "공유 취소"를 누를 수 있다(세션 전체 공유라 수신자별 row가 따로
    없으므로 pr_module_insight처럼 소유자만 종료 가능하게 제한하지 않는다)."""
    _sc.table("insightscheduleshares").update({"enddts": end_dt}).eq("shareuid", share_uid).execute()
    return True


def get_schedule_shares_sent(creator: str, offsetminutes: int | None = None) -> list[dict]:
    """내가 공유한 정기 보고서 목록(활성만)을 반환한다."""
    res = (
        _sc.table("insightscheduleshares")
        .select("shareuid, sessionuid, createdts, enddts")
        .eq("creator", creator)
        .is_("enddts", "null")
        .order("createdts", desc=True)
        .execute()
    )
    result = []
    for row in (res.data or []):
        session = get_session(row["sessionuid"]) or {}
        result.append({
            "share_uid": row["shareuid"],
            "session_id": row["sessionuid"],
            "title": session.get("sessiontitles") or "(제목 없음)",
            "created_at": _fmt_dt(row.get("createdts"), offsetminutes),
            "ended_at": _fmt_dt(row.get("enddts"), offsetminutes) if row.get("enddts") else None,
        })
    return result


def get_schedule_shares_received(project_id: int | None, my_creator: str,
                                  offsetminutes: int | None = None) -> list[dict]:
    """내가 creator가 아닌, 같은 project의 정기 보고서 공유 목록(활성만)을 반환한다."""
    q = (
        _sc.table("insightscheduleshares")
        .select("shareuid, sessionuid, creator, createdts, enddts")
        .neq("creator", my_creator)
        .is_("enddts", "null")
        .order("createdts", desc=True)
    )
    if project_id is not None:
        q = q.or_(f"projectid.eq.{project_id},projectid.is.null")
    else:
        q = q.is_("projectid", "null")
    res = q.execute()
    result = []
    for row in (res.data or []):
        session = get_session(row["sessionuid"]) or {}
        result.append({
            "share_uid": row["shareuid"],
            "session_id": row["sessionuid"],
            "title": session.get("sessiontitles") or "(제목 없음)",
            "shared_by": row.get("creator"),
            "created_at": _fmt_dt(row.get("createdts"), offsetminutes),
            "ended_at": _fmt_dt(row.get("enddts"), offsetminutes) if row.get("enddts") else None,
        })
    return result
