"""Miscellaneous router — FAQ, QnA, Follow, PopupDeactivate, HelpSearch, TenantRequest, Contact"""
import os
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_optional_token, get_token, get_sb as _sb_user, get_user as _get_user
from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

router = APIRouter()


def _sb_svc():
    return get_service_client()


def _get_offsetminutes(sb, user_id: str) -> Optional[int]:
    try:
        tu = sb.schema(SUPABASE_SCHEMA).table("tenantusers").select("timezone,tenantid").eq("useruid", user_id).maybe_single().execute()
        if not tu.data:
            return None
        tz = tu.data.get("timezone")
        if not tz and tu.data.get("tenantid"):
            t = sb.schema(SUPABASE_SCHEMA).table("tenants").select("timezone").eq("tenantid", tu.data["tenantid"]).maybe_single().execute()
            if t.data:
                tz = t.data.get("timezone")
        if not tz:
            return None
        tz_row = sb.schema(SUPABASE_SCHEMA).table("timezones").select("offsetminutes").eq("timezone", tz).maybe_single().execute()
        return tz_row.data.get("offsetminutes") if tz_row.data else None
    except Exception:
        return None


def _fmt_dt(s, offsetminutes: Optional[int] = None):
    if not s:
        return ""
    try:
        from dateutil import parser as dp
        dt = dp.parse(s) if isinstance(s, str) else s
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if offsetminutes is not None:
            dt = dt.astimezone(timezone.utc) + timedelta(minutes=offsetminutes)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(s)


# ══════════════════════════════════════════════════════
#  FAQ
# ══════════════════════════════════════════════════════

@router.get("/faqs")
def list_faqs():
    sb = _sb_svc()
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("prompts")
        .select("promptkey")
        .eq("prompttypecd", "faq")
        .eq("useyn", True)
        .order("orderno")
        .execute().data or []
    )
    return {"faqs": [r["promptkey"] for r in rows]}


class FaqSaveRequest(BaseModel):
    faquid: Optional[str] = None
    title: str
    question: str
    answer: str
    orderno: int = 0


@router.post("/faqs")
def save_faq(body: FaqSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    # roleid=7 체크
    row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user.id).execute().data
    if not row or row[0].get("roleid") != 7:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

    if body.faquid:
        sb.schema(SUPABASE_SCHEMA).table("faqs").update({
            "title": body.title, "question": body.question,
            "answer": body.answer, "orderno": body.orderno,
        }).eq("faquid", body.faquid).execute()
        return {"ok": True, "faquid": body.faquid}
    else:
        faquid = str(uuid.uuid4())
        sb.schema(SUPABASE_SCHEMA).table("faqs").insert({
            "faquid": faquid, "title": body.title,
            "question": body.question, "answer": body.answer,
            "orderno": body.orderno, "creator": str(user.id),
        }).execute()
        return {"ok": True, "faquid": faquid}


@router.delete("/faqs/{faquid}")
def delete_faq(faquid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user.id).execute().data
    if not row or row[0].get("roleid") != 7:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    sb.schema(SUPABASE_SCHEMA).table("faqs").delete().eq("faquid", faquid).execute()
    return {"ok": True}


# ══════════════════════════════════════════════════════
#  QnA
# ══════════════════════════════════════════════════════

@router.get("/qnas")
def list_qnas(token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    roleid_row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user.id).execute().data
    roleid = roleid_row[0].get("roleid", 1) if roleid_row else 1

    offsetminutes = _get_offsetminutes(sb, str(user.id))

    rows = sb.schema(SUPABASE_SCHEMA).table("qnas").select("*").order("createdts", desc=True).execute().data or []

    users_rows = sb.schema(SUPABASE_SCHEMA).table("users").select("useruid,email").execute().data or []
    user_map = {u["useruid"]: u.get("email", "") for u in users_rows}

    result = []
    for q in rows:
        q["creatornm"] = user_map.get(q.get("creator"), "")
        q["answernm"] = user_map.get(q.get("answeruseruid"), "") if q.get("answeruseruid") else ""
        q["createdts"] = _fmt_dt(q.get("createdts"), offsetminutes)
        q["answerdts"] = _fmt_dt(q.get("answerdts"), offsetminutes)
        is_private = q.get("isprivate", False)
        if roleid == 7:
            q["can_click"] = True
        else:
            q["can_click"] = not (is_private and q.get("creator") != str(user.id))
        if not q["can_click"]:
            q["question"] = None
            q["answer"] = None
        result.append(q)

    return {"qnas": result, "roleid": roleid}


class QnaSaveRequest(BaseModel):
    qnauid: Optional[str] = None
    title: str
    question: str
    isprivate: bool = False


@router.post("/qnas")
def save_qna(body: QnaSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    if body.qnauid:
        sb.schema(SUPABASE_SCHEMA).table("qnas").update({
            "title": body.title, "question": body.question, "isprivate": body.isprivate,
        }).eq("qnauid", body.qnauid).execute()
        return {"ok": True, "qnauid": body.qnauid}
    else:
        qnauid = str(uuid.uuid4())
        sb.schema(SUPABASE_SCHEMA).table("qnas").insert({
            "qnauid": qnauid, "title": body.title,
            "question": body.question, "isprivate": body.isprivate,
            "creator": str(user.id),
        }).execute()
        return {"ok": True, "qnauid": qnauid}


@router.delete("/qnas/{qnauid}")
def delete_qna(qnauid: str, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user.id).execute().data
    roleid = row[0].get("roleid", 1) if row else 1
    # 본인 or 관리자만 삭제
    qna = sb.schema(SUPABASE_SCHEMA).table("qnas").select("creator").eq("qnauid", qnauid).execute().data
    if not qna:
        raise HTTPException(status_code=404, detail="QnA를 찾을 수 없습니다.")
    if roleid != 7 and qna[0].get("creator") != str(user.id):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")
    sb.schema(SUPABASE_SCHEMA).table("qnas").delete().eq("qnauid", qnauid).execute()
    return {"ok": True}


class QnaAnswerRequest(BaseModel):
    qnauid: str
    answer: Optional[str] = None


@router.post("/qnas/answer")
def save_qna_answer(body: QnaAnswerRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    row = sb.schema(SUPABASE_SCHEMA).table("users").select("roleid").eq("useruid", user.id).execute().data
    if not row or row[0].get("roleid") != 7:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    if body.answer:
        sb.schema(SUPABASE_SCHEMA).table("qnas").update({
            "answer": body.answer, "answeruseruid": str(user.id),
            "answerdts": datetime.now(timezone.utc).isoformat(),
        }).eq("qnauid", body.qnauid).execute()
    else:
        sb.schema(SUPABASE_SCHEMA).table("qnas").update({
            "answer": None, "answeruseruid": None, "answerdts": None,
        }).eq("qnauid", body.qnauid).execute()
    return {"ok": True}


# ══════════════════════════════════════════════════════
#  따라하기 (Follow)
# ══════════════════════════════════════════════════════

@router.get("/follow")
def get_follow_links():
    sb = _sb_svc()
    excel_url = sb.storage.from_("sdoc").get_public_url("follow/APQR_Excel.xlsx")
    pdf_url = sb.storage.from_("sdoc").get_public_url("follow/Follow.pdf")
    content_url = sb.storage.from_("sdoc").get_public_url("follow/Follow_Content.txt")
    return {"excel_url": excel_url, "pdf_url": pdf_url, "content_url": content_url}


# ══════════════════════════════════════════════════════
#  팝업 숨기기 (PopupDeactivate)
# ══════════════════════════════════════════════════════

class HidePopupRequest(BaseModel):
    popupid: str
    days: int = 1


@router.post("/hide-popup")
def hide_popup(body: HidePopupRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb_svc()
    enddt = (datetime.utcnow() + timedelta(days=body.days)).isoformat()
    existing = sb.schema(SUPABASE_SCHEMA).table("popupdeactivates").select("*").eq("useruid", str(user.id)).eq("popupid", body.popupid).execute().data
    if existing:
        sb.schema(SUPABASE_SCHEMA).table("popupdeactivates").update({"enddt": enddt}).eq("useruid", str(user.id)).eq("popupid", body.popupid).execute()
    else:
        sb.schema(SUPABASE_SCHEMA).table("popupdeactivates").insert({
            "useruid": str(user.id), "popupid": body.popupid, "enddt": enddt,
        }).execute()
    return {"ok": True}


# ══════════════════════════════════════════════════════
#  기업 등록 요청 (TenantRequest)
# ══════════════════════════════════════════════════════

def _save_iconfile(sb, file: UploadFile, folder: str, existing_url: Optional[str] = None) -> tuple[str, str]:
    """아이콘 파일을 Supabase Storage에 업로드하고 (파일명, URL)을 반환."""
    if existing_url:
        try:
            parsed = urlparse(existing_url)
            prefix = "/storage/v1/object/public/sdoc/"
            if prefix in parsed.path:
                path_to_delete = parsed.path.split(prefix)[-1]
                sb.storage.from_("sdoc").remove([path_to_delete])
        except Exception:
            pass
    ext = os.path.splitext(file.filename)[1]
    uuid_name = f"{uuid.uuid4()}{ext}"
    storage_path = f"{folder}/{uuid_name}"
    sb.storage.from_("sdoc").upload(
        storage_path,
        file.file.read(),
        {"content-type": file.content_type},
    )
    public_url = sb.storage.from_("sdoc").get_public_url(storage_path).split("?")[0]
    return file.filename, public_url




# ══════════════════════════════════════════════════════
#  Contact (문의 메일 발송)  — 로그인 불필요
# ══════════════════════════════════════════════════════

class ContactRequest(BaseModel):
    name: str
    email: str
    title: str
    message: str


@router.post("/contact")
def send_contact(body: ContactRequest):
    if not all([body.name, body.email, body.title, body.message]):
        raise HTTPException(status_code=400, detail="모든 필드를 입력해주세요.")

    subject = f"[D2Doc 홈페이지 문의] {body.title}"
    mail_body = f"이름: {body.name}\n이메일: {body.email}\n\n문의 내용:\n{body.message}"

    login_user = settings.EMAIL_HOST_USER
    sender = "sales@rootel.kr"
    recipient = login_user

    try:
        msg = MIMEText(mail_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(login_user, settings.EMAIL_HOST_PASSWORD)
            smtp.sendmail(login_user, [recipient], msg.as_string())

        return {"result": "success", "message": "문의가 성공적으로 전송되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메일 전송 실패: {str(e)}")
