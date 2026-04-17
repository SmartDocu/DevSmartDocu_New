from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_token
from backend.app.schemas.objects import (
    ObjectItem, ObjectsListResponse, ObjectSaveRequest,
    ObjectTypesResponse,
)
from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


def _get_user(token: str):
    sb = _sb(token)
    resp = sb.auth.get_user(token)
    if not resp or not resp.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    return resp.user


@router.get("/types", response_model=ObjectTypesResponse)
def list_object_types(token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA).table("p_objecttypes")
        .select("*").order("orderno").execute().data or []
    )
    return {"objecttypes": rows}


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
                obj["createdts"] = dt.strftime("%y-%m-%d %H:%M")
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

    billingmodelcd = None
    user_row = sb.schema(SUPABASE_SCHEMA).table("users").select("billingmodelcd").eq("useruid", user_id).execute().data
    if user_row:
        billingmodelcd = user_row[0].get("billingmodelcd")

    transdata = {
        "chapteruid": body.chapteruid,
        "objectuid": body.objectuid or None,
        "objectdesc": body.objectdesc,
        "objecttypecd": body.objecttypecd,
        "useyn": body.useyn,
        "orderno": body.orderno,
    }

    # If type changed, clear old content
    if body.objectuid and body.objecttypecd != body.objecttypecd_orig:
        for tbl in ("tables", "charts", "sentences"):
            sb.schema(SUPABASE_SCHEMA).table(tbl).delete().eq("objectuid", body.objectuid).execute()
        transdata["objectsettingyn"] = False

    # freeobjectcnt check when re-enabling
    if body.objectuid and body.useyn:
        orig = (
            sb.schema(SUPABASE_SCHEMA).table("objects")
            .select("useyn").eq("objectuid", body.objectuid).execute().data
        )
        if orig and not orig[0]["useyn"]:
            cfg = sb.schema(SUPABASE_SCHEMA).table("configs").select("freeobjectcnt").execute().data
            freeobjectcnt = cfg[0]["freeobjectcnt"] if cfg else 999
            chap = (
                sb.schema(SUPABASE_SCHEMA).table("chapters")
                .select("docid").eq("chapteruid", body.chapteruid).execute().data
            )
            if chap:
                doc_data = (
                    sb.schema(SUPABASE_SCHEMA)
                    .rpc("fn_doc_count__r", {"p_docid": chap[0]["docid"], "p_chapteruid": None})
                    .execute().data
                )
                object_cnt = doc_data[0].get("object_cnt", 0) if doc_data else 0
                if object_cnt >= freeobjectcnt and billingmodelcd == "Fr":
                    raise HTTPException(
                        status_code=405,
                        detail=f"항목 설정 최대 사용량 {freeobjectcnt}을 초과하였습니다.",
                    )

    sb.schema(SUPABASE_SCHEMA).table("objects").upsert(transdata).execute()
    return {"message": "저장되었습니다."}


@router.delete("/{objectuid}")
def delete_object(objectuid: str, token: str = Depends(get_token)):
    _get_user(token)
    sb = _sb(token)
    sb.schema(SUPABASE_SCHEMA).table("objects").delete().eq("objectuid", objectuid).execute()
    return {"message": "삭제되었습니다."}
