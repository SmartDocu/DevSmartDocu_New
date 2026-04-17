"""Miscellaneous router — FAQ, QnA, Follow, PopupDeactivate, HelpSearch, TenantRequest, Contact"""
import os
import smtplib
import uuid
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.dependencies import get_optional_token, get_token
from utilsPrj.supabase_client import get_thread_supabase, get_service_client, SUPABASE_SCHEMA

router = APIRouter()


def _sb_svc():
    return get_service_client()


def _sb_user(token: str):
    return get_thread_supabase(access_token=token)


def _get_user(token: str):
    sb = _sb_user(token)
    resp = sb.auth.get_user(token)
    if not resp or not resp.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    return resp.user


def _fmt_dt(s):
    if not s:
        return ""
    try:
        from dateutil import parser as dp
        dt = dp.parse(s) if isinstance(s, str) else s
        return dt.strftime("%y-%m-%d %H:%M")
    except Exception:
        return str(s)


# ══════════════════════════════════════════════════════
#  FAQ
# ══════════════════════════════════════════════════════

@router.get("/faqs")
def list_faqs():
    sb = _sb_svc()
    rows = sb.schema(SUPABASE_SCHEMA).table("faqs").select("*").order("orderno").execute().data or []
    return {"faqs": rows}


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

    rows = sb.schema(SUPABASE_SCHEMA).table("qnas").select("*").order("createdts", desc=True).execute().data or []

    users_rows = sb.schema(SUPABASE_SCHEMA).table("users").select("useruid,email").execute().data or []
    user_map = {u["useruid"]: u.get("email", "") for u in users_rows}

    result = []
    for q in rows:
        q["creatornm"] = user_map.get(q.get("creator"), "")
        q["answernm"] = user_map.get(q.get("answeruseruid"), "") if q.get("answeruseruid") else ""
        q["createdts"] = _fmt_dt(q.get("createdts"))
        q["answerdts"] = _fmt_dt(q.get("answerdts"))
        is_private = q.get("isprivate", False)
        if roleid == 7:
            q["can_click"] = True
        else:
            q["can_click"] = not (is_private and q.get("creator") != str(user.id))
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
            "answerdts": datetime.now().isoformat(),
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
    excel_url = sb.storage.from_("smartdoc").get_public_url("follow/APQR_Excel.xlsx")
    pdf_url = sb.storage.from_("smartdoc").get_public_url("follow/Follow.pdf")
    content_url = sb.storage.from_("smartdoc").get_public_url("follow/Follow_Content.txt")
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
            prefix = "/storage/v1/object/public/smartdoc/"
            if prefix in parsed.path:
                path_to_delete = parsed.path.split(prefix)[-1]
                sb.storage.from_("smartdoc").remove([path_to_delete])
        except Exception:
            pass
    ext = os.path.splitext(file.filename)[1]
    uuid_name = f"{uuid.uuid4()}{ext}"
    storage_path = f"{folder}/{uuid_name}"
    sb.storage.from_("smartdoc").upload(
        storage_path,
        file.file.read(),
        {"content-type": file.content_type},
    )
    public_url = sb.storage.from_("smartdoc").get_public_url(storage_path).split("?")[0]
    return file.filename, public_url


@router.post("/tenant-requests")
async def save_tenant_request(
    type: str = Form(...),
    billingusercnt: Optional[str] = Form(None),
    llmlimityn: str = Form("false"),
    tenantnm: str = Form(...),
    bizregno: Optional[str] = Form(None),
    managernm: str = Form(...),
    managerdepart: Optional[str] = Form(None),
    managerposition: Optional[str] = Form(None),
    email: str = Form(...),
    telno: Optional[str] = Form(None),
    bizregfile: Optional[UploadFile] = File(None),
    iconfile: Optional[UploadFile] = File(None),
    token: Optional[str] = Depends(get_optional_token),
):
    """
    type='tenant' → tenantreqs 테이블에 요청 저장 (로그인 불필요)
    type='teams'  → tenants 테이블에 즉시 생성 + billing 처리 (로그인 필요)
    """
    from utilsPrj.crypto_helper import encrypt_value

    sb = _sb_svc()

    # 로그인 사용자 정보 (optional)
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    if token:
        try:
            u = _sb_user(token).auth.get_user(token).user
            if u:
                user_id = str(u.id)
                user_email = u.email
        except Exception:
            pass

    encemail = encrypt_value(email) if email else None
    enctelno = encrypt_value(telno) if telno else None

    try:
        if type == "tenant":
            # 기업 등록 요청 → tenantreqs 저장
            sb.schema(SUPABASE_SCHEMA).table("tenantreqs").insert({
                "bizregno": bizregno,
                "tenantnm": tenantnm,
                "billingusercnt": int(billingusercnt) if billingusercnt else None,
                "llmlimityn": llmlimityn,
                "managernm": managernm,
                "managerdepart": managerdepart,
                "managerposition": managerposition,
                "encemail": encemail,
                "enctelno": enctelno,
                "creator": user_id,
            }).execute()
            return {"ok": True, "type": type}

        elif type == "teams":
            if not user_id:
                raise HTTPException(status_code=401, detail="기업 등록은 로그인 후 이용하실 수 있습니다.")

            # 중복 기업명 확인
            existing = sb.schema(SUPABASE_SCHEMA).table("tenants").select("tenantid").eq("tenantnm", tenantnm).execute().data
            if existing:
                raise HTTPException(status_code=400, detail=f"이미 존재하는 '{tenantnm}' 명입니다.")

            # tenants 생성
            tenant_row = sb.schema(SUPABASE_SCHEMA).table("tenants").insert({
                "tenantnm": tenantnm,
                "useyn": True,
                "billingusercnt": int(billingusercnt) if billingusercnt else None,
                "llmlimityn": llmlimityn,
                "creator": user_id,
                "billingmodelcd": "Te",
            }).execute().data
            new_tenantid = tenant_row[0]["tenantid"]

            # 아이콘 파일 업로드
            if iconfile and iconfile.filename:
                _, icon_url = _save_iconfile(sb, iconfile, "iconfiles/tenants")
                sb.schema(SUPABASE_SCHEMA).table("tenants").update({
                    "iconfilenm": iconfile.filename,
                    "iconfileurl": icon_url,
                }).eq("tenantid", new_tenantid).execute()

            # 기존 tenantusers 삭제
            sb.schema(SUPABASE_SCHEMA).table("tenantusers").delete().eq("useruid", user_id).execute()

            # 기존 개인 프로젝트 삭제
            proj_res = sb.schema(SUPABASE_SCHEMA).table("projects").select("projectid").eq("projectnm", user_email).execute()
            project_id = None
            if proj_res.data:
                project_id = proj_res.data[0]["projectid"]
                sb.schema(SUPABASE_SCHEMA).table("projects").delete().eq("projectid", project_id).execute()
            if project_id:
                sb.schema(SUPABASE_SCHEMA).table("projectusers").delete().eq("useruid", user_id).execute()
                sb.schema(SUPABASE_SCHEMA).table("docs").delete().eq("projectid", project_id).execute()

            # tenantusers 등록 (매니저)
            sb.schema(SUPABASE_SCHEMA).table("tenantusers").insert({
                "tenantid": new_tenantid,
                "useruid": user_id,
                "rolecd": "M",
                "useyn": True,
                "creator": user_id,
            }).execute()

            # users billing 모델 변경
            sb.schema(SUPABASE_SCHEMA).table("users").update({"billingmodelcd": "Te"}).eq("useruid", user_id).execute()

            # billing 처리
            now_dt = datetime.now().strftime("%Y-%m-%d")
            from dateutil.relativedelta import relativedelta
            now_1m = (datetime.now() + relativedelta(months=1) - relativedelta(days=1)).strftime("%Y-%m-%d")

            configs = sb.schema(SUPABASE_SCHEMA).table("configs").select("*").execute().data
            config_price = configs[0].get("priceteams", 50000) if configs else 50000
            config_capa = int(configs[0].get("inputtokencapa", 1000000)) if configs else 1000000
            user_cnt = int(billingusercnt) if billingusercnt else 1
            inputtokencapa = config_capa * user_cnt

            sb.schema(SUPABASE_SCHEMA).table("billmasters").insert({
                "billtargetcd": "T",
                "tenantid": new_tenantid,
                "billingmodelcd": "Te",
                "billingfirstdt": now_dt,
                "useyn": True,
                "encemail": encemail,
                "enctelno": enctelno,
                "creator": user_id,
            }).execute()

            sb.schema(SUPABASE_SCHEMA).table("billdts").insert({
                "billtargetcd": "T",
                "tenantid": new_tenantid,
                "billstartdt": now_dt,
                "billenddt": now_1m,
                "billingmodelcd": "Te",
                "inputtokencapa": inputtokencapa,
                "inputtoken": 0,
                "overtokenm": 0,
                "serviceamt": config_price,
                "addamt": 0,
                "creator": user_id,
            }).execute()

            sb.schema(SUPABASE_SCHEMA).table("tokentenants").insert({
                "tenantid": new_tenantid,
                "billstartdt": now_dt,
                "runcnt": 0,
                "inputtoken": 0,
                "inputtokencapa": inputtokencapa,
            }).execute()

            sb.schema(SUPABASE_SCHEMA).table("tenantusermonths").insert({
                "billstartdt": now_dt,
                "tenantid": new_tenantid,
                "useruid": user_id,
                "recordtypecd": "N",
                "creator": user_id,
            }).execute()

            return {"ok": True, "type": type}

        else:
            raise HTTPException(status_code=400, detail="지원하지 않는 type입니다.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    subject = f"[SmartDocu 홈페이지 문의] {body.title}"
    mail_body = f"이름: {body.name}\n이메일: {body.email}\n\n문의 내용:\n{body.message}"

    recipient = "sales@rootel.kr"
    sender = "sales@rootel.kr"

    try:
        msg = MIMEText(mail_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, settings.EMAIL_HOST_PASSWORD)
            smtp.sendmail(sender, [recipient], msg.as_string())

        return {"result": "success", "message": "문의가 성공적으로 전송되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메일 전송 실패: {str(e)}")
