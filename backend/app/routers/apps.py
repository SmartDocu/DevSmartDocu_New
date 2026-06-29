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
    servicecd: Optional[str] = None


class AppsListResponse(BaseModel):
    apps: list[AppItem]
    subscribed_servicecds: list[str] = []


@router.get("", response_model=AppsListResponse)
def list_apps(token: str = Depends(get_token), accountuid: Optional[str] = None):
    try:
        sb = _sb(token)
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("apps")
            .select("appcd, appnm, iconurl, desc, useyn, orderno, rolecd, routepath, servicecd")
            .eq("useyn", True)
            .order("orderno")
            .execute()
            .data or []
        )

        subscribed_servicecds = []
        if accountuid:
            subs = (
                sb.schema(SUPABASE_SCHEMA)
                .table("subscriptions")
                .select("servicecd")
                .eq("accountuid", accountuid)
                .execute()
                .data or []
            )
            subscribed_servicecds = list({s["servicecd"] for s in subs if s.get("servicecd")})

        return AppsListResponse(
            apps=[AppItem(**r) for r in rows],
            subscribed_servicecds=subscribed_servicecds,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
