from fastapi import APIRouter
from backend.app.routers import auth, docs, chapters, objects, datas, tables, charts, sentences, gendocs, settings, org, admin, llm, misc

router = APIRouter()
router.include_router(auth.router,      prefix="/auth",      tags=["auth"])
router.include_router(docs.router,      prefix="/docs",      tags=["docs"])
router.include_router(chapters.router,  prefix="/chapters",  tags=["chapters"])
router.include_router(objects.router,   prefix="/objects",   tags=["objects"])
router.include_router(datas.router,     prefix="/datas",     tags=["datas"])
router.include_router(tables.router,    prefix="/tables",    tags=["tables"])
router.include_router(charts.router,    prefix="/charts",    tags=["charts"])
router.include_router(sentences.router, prefix="/sentences", tags=["sentences"])
router.include_router(gendocs.router,   prefix="/gendocs",   tags=["gendocs"])
router.include_router(settings.router,  prefix="/settings",  tags=["settings"])
router.include_router(org.router,       prefix="/org",       tags=["org"])
router.include_router(admin.router,     prefix="/admin",     tags=["admin"])
router.include_router(llm.router,       prefix="/llm",       tags=["llm"])
router.include_router(misc.router,      prefix="/misc",      tags=["misc"])
