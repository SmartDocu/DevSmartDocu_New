from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import settings, i18n, master_docs

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(i18n.router)
app.include_router(settings.router)  # <- frontend 호출용 settings API
app.include_router(master_docs.router)