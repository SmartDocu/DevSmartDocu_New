from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.dependencies import get_token, get_sb as _sb
from utilsPrj.supabase_client import SUPABASE_SCHEMA

router = APIRouter()


class AppItem(BaseModel):
    appcd: str
    appnm: Optional[str] = None
    iconurl: Optional[str] = None
    desc: Optional[str] = None
    useyn: Optional[bool] = True
    orderno: Optional[int] = None
    rolecd: Optional[str] = None
    routepath: Optional[str] = None


class AppsListResponse(BaseModel):
    apps: list[AppItem]


@router.get("", response_model=AppsListResponse)
def list_apps(token: str = Depends(get_token)):
    try:
        sb = _sb(token)
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("apps")
            .select("appcd, appnm, iconurl, desc, useyn, orderno, rolecd, routepath")
            .eq("useyn", True)
            .order("orderno")
            .execute()
            .data or []
        )
        return AppsListResponse(apps=[AppItem(**r) for r in rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
