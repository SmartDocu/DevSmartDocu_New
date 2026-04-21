from fastapi import APIRouter, Depends

from backend.app.dependencies import get_token
from backend.app.schemas.menus import CodeItem, CodesListResponse
from utilsPrj.supabase_client import get_thread_supabase, SUPABASE_SCHEMA

router = APIRouter()


def _sb(token: str):
    return get_thread_supabase(access_token=token)


@router.get("", response_model=CodesListResponse)
def list_codes(codegroupcd: str, token: str = Depends(get_token)):
    sb = _sb(token)
    rows = (
        sb.schema(SUPABASE_SCHEMA)
        .table("codes")
        .select("codegroupcd, codevalue, default_name, orderno")
        .eq("codegroupcd", codegroupcd)
        .eq("useyn", True)
        .order("orderno")
        .execute()
        .data or []
    )
    codes = [
        CodeItem(
            codevalue=r["codevalue"],
            term_key=f"cod.{r['codegroupcd']}_{r['codevalue']}",
            default_name=r.get("default_name"),
        )
        for r in rows
    ]
    return CodesListResponse(codes=codes)
