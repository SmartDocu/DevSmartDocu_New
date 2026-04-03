from fastapi import APIRouter, Depends, Request
from app.core.supabase_client import get_supabase_client
from app.core.config import config

router = APIRouter(prefix="/master_docs")


@router.get("/")
def master_docs(
    request: Request,
    supabase_client=Depends(get_supabase_client)
):
    # 🔥 1. 헤더에서 토큰 꺼내기
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header else None

    # 🔥 2. 토큰으로 유저 조회
    user_resp = supabase_client.auth.get_user(token)

    user = user_resp.user

    # 🔥 3. email 출력
    print("로그인 유저 이메일:", user.email)

    # 기존 로직
    docs_resp = (
        supabase_client.schema(config.DB_SCHEMA)
        .table("docs")
        .select("docid, docnm")
        .execute()
    )

    docs = docs_resp.data

    return {
        "message_key": "msg.page2.subtitle",
        "docs": docs
    }

@router.post("/save")
def master_docs_save(supabase_client=Depends(get_supabase_client)):
    """
    로그인 사용자용 저장 API
    """
    # 실제 저장 로직은 여기 작성
    return {
        "message_key": "msg.buttonmessage_save"
    }