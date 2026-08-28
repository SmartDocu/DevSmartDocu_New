import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from postgrest.exceptions import APIError
from starlette.background import BackgroundTasks

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


# ─── 접속/작업 로그(work_logs) 자동 기록 미들웨어 ────────────────────────────
# 문서/챗/인사이트/테넌트관리 도메인의 쓰기성(POST/PUT/PATCH/DELETE) 요청이
# 성공(2xx)했을 때 work_logs에 1 row를 남긴다. 대상 엔드포인트가 180개에
# 달해 건마다 수동 삽입하는 대신, 경로 prefix 기준으로 자동 판별한다.
# 조회(GET)는 남기지 않는다.
_WORK_LOG_DOMAIN_MAP = {
    "docs": "Do", "chapters": "Do", "objects": "Do", "datas": "Do", "tables": "Do",
    "charts": "Do", "sentences": "Do", "gendocs": "Do", "data-metas": "Do", "data-cols": "Do",
    "connectors": "Do", "docgroups": "Do", "datasets": "Do", "llm": "Do",
    "d2chat": "Ch",
    "d2insight": "In",
    "org": "Tenant", "settings": "Tenant", "payments": "Tenant", "llmkeys": "Tenant", "whitelists": "Tenant",
}
_WORK_LOG_ACTIONCD = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
# UUID 형태뿐 아니라 순수 정수 PK(docid 등)도 ID로 인식해야 targettype이
# 문서마다 달라지는("docs/123", "docs/124"...) 걸 막고 "docs"로 안정적으로 모인다.
_ID_SEGMENT_RE = re.compile(r"^(\d+|[0-9a-fA-F-]{8,36})$")

# (method, targettype) 조합이 여기 있으면 미들웨어는 로깅을 건너뛴다 —
# 해당 엔드포인트가 before/after까지 포함해서 직접 log_work_action()을 호출하므로
# 미들웨어가 또 남기면 같은 작업이 2건씩 찍힌다.
_WORK_LOG_MANUAL_SKIP = {
    ("POST", "datas/db"),
    ("POST", "datas/ex"),
    ("POST", "datas/ai"),
    ("POST", "datas/api"),
    ("POST", "datas/datacols"),
    ("DELETE", "datas"),
    ("POST", "docs"),
    ("DELETE", "docs"),
    ("POST", "docs/params"),
    ("DELETE", "docs/params"),
    ("POST", "docs/doc-params"),
    ("POST", "chapters"),
    ("DELETE", "chapters"),
    ("POST", "chapters/template"),
    ("POST", "chapters/objectfiltermap"),
    ("POST", "objects"),
    ("DELETE", "objects"),
    ("POST", "datasets"),
    ("DELETE", "datasets"),
    ("POST", "datasets/members"),
    ("POST", "datasets/projects"),
    ("POST", "datasets/save-all"),
    ("POST", "gendocs"),
    ("DELETE", "gendocs"),
    ("POST", "gendocs/close"),
    ("POST", "gendocs/open"),
    ("POST", "gendocs/params/update"),
    ("POST", "gendocs/genchapters/objects/rewrite"),
    ("POST", "gendocs/genchapters/apply"),
    ("POST", "gendocs/genchapters/upload"),
    ("POST", "gendocs/upload"),
    ("POST", "gendocs/genchapters/rewrite"),
    ("POST", "gendocs/generate"),
    ("POST", "gendocs/combine"),
    # 아래 둘은 POST지만 실제로는 읽기전용(검증)만 함 — 미들웨어가 "create"로
    # 오기록하지 않도록 아예 스킵(수동 로깅도 하지 않음)
    ("POST", "gendocs/params/check"),
    ("POST", "gendocs/check-objects"),
    ("POST", "whitelists"),
    ("DELETE", "whitelists"),
    ("POST", "whitelists/config"),
    ("POST", "connectors"),
    ("DELETE", "connectors"),
    ("POST", "org/projects"),
    ("DELETE", "org/projects"),
    ("POST", "org/tenant-llms"),
    ("DELETE", "org/tenant-llms"),
    ("POST", "org/project-users"),
    ("DELETE", "org/project-users"),
    ("POST", "org/invite-members"),
    ("POST", "org/tenant-users"),
    ("DELETE", "org/tenant-users"),
    ("POST", "settings/servers"),
    ("DELETE", "settings/servers"),
    ("POST", "settings/tenant-manage/subscription-change"),
    ("POST", "settings/tenant-manage/basic-info"),
    ("POST", "settings/tenant-manage/other-subscription-purchase"),
    ("POST", "settings/tenant-manage/other-subscription-cancel"),
    ("POST", "settings/tenant-manage/other-subscription-cancel-undo"),
    ("POST", "settings/tenant-manage/other-subscription-quantity"),
    ("POST", "settings/tenant-manage/mfa-config"),
    ("POST", "settings/tenant-manage/credit-subscription-purchase"),
    ("POST", "settings/myinfo/credit-purchase"),
    # 커넥터/서버 연결 테스트 — DB 안 건드리는 순수 네트워크 호출, 로깅 스킵
    ("POST", "connectors/test-health-inline"),
    ("POST", "connectors/test-auth-inline"),
    ("POST", "connectors/test-health"),
    ("POST", "connectors/test-auth"),
    ("POST", "llm/save"),
    ("DELETE", "llm/delete"),
    # llm/preview는 objectdefinitions/llmdoclogs에 자체적으로 시도 이력을 남기므로
    # work_logs 중복 방지 차원에서 스킵(수동 로깅도 안 함)
    ("POST", "llm/preview"),
    ("POST", "tables"),
    ("DELETE", "tables"),
    ("POST", "charts"),
    ("DELETE", "charts"),
    ("POST", "sentences"),
    ("DELETE", "sentences"),
    # tables/charts/sentences preview는 렌더링만 하고 DB를 안 씀 — 스킵
    ("POST", "tables/preview"),
    ("POST", "charts/preview"),
    ("POST", "sentences/preview"),
    ("POST", "data-cols/datacols/aliases"),
    ("POST", "data-cols/values"),
    ("DELETE", "data-cols/values"),
    ("POST", "settings/tenants"),
    ("DELETE", "settings/tenants"),
    ("POST", "settings/myinfo/username"),
    ("POST", "settings/myinfo/marketing"),
    ("POST", "settings/myinfo/timezone"),
    ("POST", "settings/upgrade-plan"),
    ("POST", "settings/myinfo/pro-cancel"),
    ("POST", "settings/myinfo/pro-cancel-undo"),
    ("POST", "settings/tenant-subscription"),
    ("POST", "llmkeys"),
    ("DELETE", "llmkeys"),
    ("POST", "payments/methods/billing-key"),
    ("DELETE", "payments/methods"),
    ("POST", "payments/methods/set-default"),
}


def _get_work_log_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _run_work_log(request: Request, status_code: int):
    try:
        if request.method not in _WORK_LOG_ACTIONCD or not (200 <= status_code < 300):
            return
        path = request.url.path
        if not path.startswith("/api/"):
            return
        segments = path[len("/api/"):].split("/")
        prefix = segments[0] if segments else ""
        servicecd = _WORK_LOG_DOMAIN_MAP.get(prefix)
        if not servicecd:
            return
        from utilsPrj.audit_log import decode_jwt_sub, log_work_action
        useruid = decode_jwt_sub(request.headers.get("authorization"))
        if not useruid:
            return
        # targettype: prefix(datas)만이 아니라 ID가 아닌 경로 세그먼트를 전부 이어붙여
        # 어떤 하위 액션인지("datas/myproject", "gendocs/generate" 등)까지 드러낸다.
        targetid = next((s for s in segments[1:] if _ID_SEGMENT_RE.match(s)), None)
        non_id_segments = [s for s in segments if s and not _ID_SEGMENT_RE.match(s)]
        targettype = "/".join(non_id_segments) if non_id_segments else prefix
        if (request.method, targettype) in _WORK_LOG_MANUAL_SKIP:
            return
        tenantid_header = request.headers.get("x-tenant-id")

        detail = {"path": path, "method": request.method}
        if request.url.query:
            detail["query"] = request.url.query

        log_work_action(
            useruid=useruid,
            tenantid=int(tenantid_header) if tenantid_header and tenantid_header.isdigit() else None,
            servicecd=servicecd,
            actioncd=_WORK_LOG_ACTIONCD[request.method],
            targettype=targettype,
            targetid=targetid,
            detail=detail,
            ip=_get_work_log_ip(request),
        )
    except Exception:
        pass


@app.middleware("http")
async def _work_log_middleware(request: Request, call_next):
    response = await call_next(request)
    # DB insert는 응답 전송 후 백그라운드에서 수행 — 실제 요청 지연에 영향 없음
    existing_bg = response.background
    tasks = BackgroundTasks()
    if existing_bg is not None:
        tasks.add_task(existing_bg)
    tasks.add_task(_run_work_log, request, response.status_code)
    response.background = tasks
    return response


app.include_router(router, prefix="/api")


# ─── 서비스 초기화 ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    try:
        # from d2chat.service import mcp_service
        from d2chat.mcp_core.service import mcp_service
        mcp_service.initialize()
        # print("[d2chat] MCP 서비스 초기화 완료")
    except Exception as e:
        # print(f"[d2chat] MCP 서비스 초기화 실패 (서비스 미사용 시 무시): {e}")
        pass

    try:
        # from d2insight.report import meta_loader
        # meta_loader.refresh()
        from d2insight.data_source import meta_loader
        meta_loader.load()
        # print("[d2insight] 메타데이터 캐시 초기화 완료")
    except Exception as e:
        # print(f"[d2insight] 메타데이터 초기화 실패 (무시): {e}")
        pass


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
    # print(f"[postgrest_api_error_handler] {request.method} {request.url.path} code={code} message={message}")
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

    _DIST_RESOLVED = _DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # index.html 안 <img src="/doc-select.svg"> 등 frontend/public/ 루트 정적 파일들
        # (Vite가 dist/ 루트로 그대로 복사) — 실제로 dist/ 안에 존재하는 파일이면 그 파일을
        # 그대로 반환하고, 그 외(React Router 클라이언트 라우트 등)에만 index.html로 폴백한다.
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_DIST_RESOLVED):
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
