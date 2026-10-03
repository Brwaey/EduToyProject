import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from .config import Settings
from .db import make_engine, make_session_factory, migrate, migration_head
from .schemas import (
    ErrorOut,
)
from .security import (
    Identity,
    Problem,
    current_user,
    db_session,
)

Db = Annotated[Session, Depends(db_session)]
Who = Annotated[Identity, Depends(current_user)]
log = logging.getLogger("yanji")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        migrate(engine, settings)
        from .ai_worker import AIWorker

        worker = AIWorker(app)
        app.state.ai_worker = worker
        if settings.ai_worker_enabled:
            await worker.start()
        try:
            yield
        finally:
            if settings.ai_worker_enabled:
                await worker.stop()
            engine.dispose()

    app = FastAPI(
        title="研迹 API",
        version="0.4.0",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorOut}
            for status in (400, 401, 403, 404, 405, 409, 413, 422, 500, 503)
        },
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = make_session_factory(engine)

    def error(request, status, code, message):
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=status,
            headers={
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": request_id,
                }
            },
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin", "").rstrip("/")
            if origin not in settings.allowed_origins:
                return error(request, 403, "origin_failed", "请求来源不被允许")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return error(request, exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_handler(request, exc):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return error(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected_handler(request, exc):
        # Do not log submitted research material or credentials.
        log.error("Unhandled %s request=%s", type(exc).__name__, request.state.request_id)
        return error(request, 500, "internal_error", "服务暂时无法完成操作，请稍后重试")

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_handler(request, exc):
        return error(
            request,
            422,
            "validation_error",
            "输入格式不正确："
            + "; ".join(
                ".".join(str(p) for p in item["loc"]) + " " + item["msg"]
                for item in exc.errors()[:3]
            ),
        )

    @app.exception_handler(OperationalError)
    async def operational_handler(request, exc):
        if "locked" in str(exc.orig).lower() or "busy" in str(exc.orig).lower():
            return error(
                request,
                503,
                "database_busy",
                "数据库正在保存其他内容，请稍后重试，当前输入已保留",
            )
        log.error("Database operation failed request=%s", request.state.request_id)
        return error(request, 503, "database_unavailable", "数据库暂不可用，请检查服务状态")

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request, exc):
        return error(request, 409, "integrity_conflict", "数据存在冲突，请刷新后重试")

    prefix = "/api/v1"

    @app.get(prefix + "/health/live")
    def live():
        return {"status": "ok"}

    @app.get(prefix + "/health/ready")
    def ready(db: Db):
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if version != migration_head():
            raise Problem(503, "migration_required", "数据库结构需要升级")
        return {"status": "ready", "schema": version}

    from .api_m1 import router as m1_router
    from .api_m2 import router as m2_router

    app.include_router(m1_router)
    app.include_router(m2_router)
    from .api_ai import router as ai_router

    app.include_router(ai_router)
    from .api_growth import router as growth_router

    app.include_router(growth_router)
    return app
