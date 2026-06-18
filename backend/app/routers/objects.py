from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_token, get_sb as _sb, get_user as _get_user
from backend.app.schemas.objects import (
    ObjectItem, ObjectsListResponse, ObjectSaveRequest,
)
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()



@router.get("")
def list_objects(chapteruid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .rpc("fn_objects__r", {"p_chapteruid": chapteruid})
        .execute().data or []
    )

    from dateutil import parser as dp
    for obj in rows:
        if obj.get("createdts"):
            try:
                dt = dp.parse(obj["createdts"]) if isinstance(obj["createdts"], str) else obj["createdts"]
                obj["createdts"] = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                obj["createdts"] = ""
        nm = obj.get("objecttypenm") or ""
        gcd = obj.get("gentypecd") or ""
        obj["objecttypenm_full"] = f"{nm} ({gcd})" if nm else ""

    rows.sort(key=lambda x: x.get("orderno") or 0)
    return {"objects": rows}


@router.post("")
def save_object(body: ObjectSaveRequest, token: str = Depends(get_token)):
    user = _get_user(token)
    sb = _sb(token)
    user_id = str(user.id)

    # 신규 생성 시 objectnm 필수
    if not body.objectuid and not body.objectnm:
        raise HTTPException(status_code=400, detail="항목명(objectnm)은 필수입니다.")

    transdata = {
        "chapteruid": body.chapteruid,
        "objectuid": body.objectuid or None,
        "objectdesc": body.objectdesc,
        "objecttypecd": body.objecttypecd,
        "useyn": body.useyn,
        "orderno": body.orderno,
    }
    if body.objectnm:
        transdata["objectnm"] = body.objectnm

    # If type changed, clear old content
    if body.objectuid and body.objecttypecd != body.objecttypecd_orig:
        for tbl in ("tables", "charts", "sentences"):
            sb.schema(SUPABASE_SCHEMA).table(tbl).delete().eq("objectuid", body.objectuid).execute()
        transdata["objectsettingyn"] = False

    sb.schema(SUPABASE_SCHEMA).table("objects").upsert(transdata).execute()
    return {"message": "저장되었습니다."}


@router.delete("/{objectuid}")
def delete_object(objectuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("objects").delete().eq("objectuid", objectuid).execute()
    return {"message": "삭제되었습니다."}
