from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from postgrest.exceptions import APIError

from backend.app.config import settings
from backend.app.routers import router

app = FastAPI(
    title="D2Doc API",
    version="1.0.0",
    docs_url="/api/swagger",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(router, prefix="/api")


# ─── 서비스 초기화 ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    try:
        # from d2chat.service import mcp_service
        from d2chat.mcp_core.service import mcp_service
        mcp_service.initialize()
        print("[d2chat] MCP 서비스 초기화 완료")
    except Exception as e:
        print(f"[d2chat] MCP 서비스 초기화 실패 (서비스 미사용 시 무시): {e}")

    try:
        # from d2insight.report import meta_loader
        # meta_loader.refresh()
        from d2insight.data_source import meta_loader
        meta_loader.load()
        print("[d2insight] 메타데이터 캐시 초기화 완료")
    except Exception as e:
        print(f"[d2insight] 메타데이터 초기화 실패 (무시): {e}")


# ─── Supabase JWT 만료 → 401 변환 ───────────────────────────────────────────
_JWT_CODES = {"PGRST301", "PGRST302", "PGRST303"}

@app.exception_handler(APIError)
async def postgrest_api_error_handler(request: Request, exc: APIError):
    code = getattr(exc, "code", "") or ""
    message = str(getattr(exc, "message", exc) or exc)
    if code in _JWT_CODES or "JWT" in message or "expired" in message.lower():
        return JSONResponse(
            status_code=401,
            content={"detail": "토큰이 만료되었습니다."},
        )
    print(f"[postgrest_api_error_handler] {request.method} {request.url.path} code={code} message={message}")
    return JSONResponse(status_code=500, content={"detail": message})


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# ─── React SPA 서빙 ─────────────────────────────────────────────────────────
_DIST = Path("frontend/dist")

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    # Vite 빌드 산출물은 파일명에 콘텐츠 해시가 붙어 내용이 바뀌면 파일명도 바뀐다
    # → 브라우저가 매 요청마다 재검증(304)할 필요 없이 영구 캐시해도 안전하다.
    @app.middleware("http")
    async def _cache_hashed_assets(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        return FileResponse(_DIST / "favicon.svg")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = _DIST / "index.html"
        return FileResponse(index)
