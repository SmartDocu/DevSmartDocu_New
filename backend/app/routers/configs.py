from fastapi import APIRouter, HTTPException

from utilsPrj.supabase_client import get_service_client, SUPABASE_SCHEMA

router = APIRouter()


@router.get("")
def get_configs():
    """configs 테이블 첫 번째 행 반환 (인증 불요)."""
    try:
        sb = get_service_client()
        rows = (
            sb.schema(SUPABASE_SCHEMA)
            .table("configs")
            .select("*")
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
