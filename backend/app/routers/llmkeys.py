"""LLM API Keys router — llmapikeys 테이블 관리"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_tenantid, get_sb as _sb, get_user as _get_user
from utilsPrj.supabase_client import SUPABASE_SCHEMA, get_service_client
from utilsPrj.crypto_helper import encrypt_value

router = APIRouter()


def _get_tenant_and_account(sd, user_id: str, tenantid: Optional[str]) -> tuple[str, Optional[str]]:
    """tenantid와 accountuid를 반환."""
    if not tenantid:
        tu = sd.table("tenantusers").select("tenantid").eq("useruid", user_id).eq("useyn", True).maybe_single().execute()
        if not tu.data:
            raise HTTPException(status_code=400, detail="tenantid를 확인할 수 없습니다.")
        tenantid = str(tu.data["tenantid"])

    t_row = sd.table("tenants").select("issystemtenant").eq("tenantid", int(tenantid)).maybe_single().execute()
    issystemtenant = t_row.data.get("issystemtenant", True) if t_row.data else True

    if issystemtenant:
        acc = sd.table("accounts").select("accountuid").eq("useruid", user_id).maybe_single().execute()
    else:
        acc = sd.table("accounts").select("accountuid").eq("tenantid", int(tenantid)).maybe_single().execute()

    accountuid = str(acc.data["accountuid"]) if acc and acc.data else None
    return tenantid, accountuid


@router.get("/init")
def llmkeys_init(
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    """화면 초기 데이터: accountuid, vendors, llmmodels, servicecodes."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(sd, user_id, header_tenantid)

    # llmvendornm 고유 목록
    vendor_rows = sd.table("llmmodels").select("llmvendornm").eq("useyn", True).execute().data or []
    vendors = sorted(set(r["llmvendornm"] for r in vendor_rows if r.get("llmvendornm")))

    # 모델 전체 목록 (vendor 선택 시 필터링용)
    model_rows = (
        sd.table("llmmodels")
        .select("llmvendornm,llmmodelnm")
        .eq("useyn", True)
        .order("llmmodelnm")
        .execute()
        .data or []
    )

    # servicecd 목록 (codes 테이블 — term_key는 DB 컬럼 없음, Python에서 생성)
    code_rows = (
        sd.table("codes")
        .select("codevalue,default_name")
        .eq("codegroupcd", "servicecd")
        .eq("useyn", True)
        .order("orderno")
        .execute()
        .data or []
    )
    for r in code_rows:
        r["term_key"] = f"cod.servicecd_{r['codevalue']}"

    return {
        "accountuid": accountuid,
        "tenantid": str(tenantid),
        "vendors": vendors,
        "llmmodels": model_rows,
        "servicecodes": code_rows,
    }


@router.get("")
def list_llmkeys(
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    """현재 테넌트의 llmapikeys 목록 반환 (encapikey는 마스킹)."""
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    tenantid, _ = _get_tenant_and_account(sd, user_id, header_tenantid)

    rows = (
        sd.table("llmapikeys")
        .select("*")
        .eq("tenantid", int(tenantid))
        .order("orderno")
        .execute()
        .data or []
    )

    for row in rows:
        row["has_apikey"] = bool(row.get("encapikey"))
        row["encapikey"] = ""  # 클라이언트에 노출하지 않음

    return {"llmkeys": rows}


class LlmKeySaveRequest(BaseModel):
    llmkeyuid: Optional[str] = None
    servicecd: str
    llmvendornm: str
    apikey: Optional[str] = None  # 빈 문자열 = 기존 키 유지
    llmmodelnm: Optional[str] = None
    llmmodelnm_smart: Optional[str] = None
    llmmodelnm_expert: Optional[str] = None
    useyn: bool = True
    orderno: int = 0


@router.post("")
def save_llmkey(
    body: LlmKeySaveRequest,
    token: str = Depends(get_token),
    header_tenantid: Optional[str] = Depends(get_tenantid),
):
    user = _get_user(token)
    user_id = str(user.id)
    svc = get_service_client()
    sd = svc.schema(SUPABASE_SCHEMA)

    tenantid, accountuid = _get_tenant_and_account(sd, user_id, header_tenantid)

    # encapikey 처리: 입력값 있으면 암호화, 없으면 기존 키 유지
    apikey = (body.apikey or "").strip()
    encapikey = None
    if apikey:
        encapikey = encrypt_value(apikey)
    elif body.llmkeyuid:
        existing = sd.table("llmapikeys").select("encapikey").eq("llmkeyuid", body.llmkeyuid).maybe_single().execute()
        if existing.data:
            encapikey = existing.data.get("encapikey")

    data = {
        "tenantid": int(tenantid),
        "accountuid": accountuid,
        "servicecd": body.servicecd,
        "llmvendornm": body.llmvendornm,
        "encapikey": encapikey,
        "llmmodelnm": body.llmmodelnm or None,
        "llmmodelnm_smart": body.llmmodelnm_smart or None,
        "llmmodelnm_expert": body.llmmodelnm_expert or None,
        "useyn": body.useyn,
        "orderno": body.orderno,
    }

    def _do_save(payload: dict):
        if body.llmkeyuid:
            sd.table("llmapikeys").update(payload).eq("llmkeyuid", body.llmkeyuid).execute()
        else:
            payload["creator"] = user_id
            sd.table("llmapikeys").insert(payload).execute()

    try:
        _do_save(data)
    except Exception as e:
        # llmmodelnm_smart / llmmodelnm_expert 컬럼이 아직 없는 경우 제외 후 재시도
        if "llmmodelnm_smart" in str(e) or "llmmodelnm_expert" in str(e):
            data.pop("llmmodelnm_smart", None)
            data.pop("llmmodelnm_expert", None)
            _do_save(data)
        else:
            raise

    return {"result": "success", "message": "저장되었습니다."}


@router.delete("/{llmkeyuid}")
def delete_llmkey(llmkeyuid: str, token: str = Depends(get_token)):
    _get_user(token)
    svc = get_service_client()
    svc.schema(SUPABASE_SCHEMA).table("llmapikeys").delete().eq("llmkeyuid", llmkeyuid).execute()
    return {"result": "success", "message": "삭제되었습니다."}
