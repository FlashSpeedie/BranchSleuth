from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import new_request_id
from app.api.routes import analyses, health, repositories
from app.config import settings
from app.logging_config import configure_logging, request_id_ctx

logger = logging.getLogger("branchsleuth.api")

MAX_JSON_BODY = 10 * 1024 * 1024


def create_app() -> FastAPI:
    configure_logging("INFO")
    app = FastAPI(
        title="BranchSleuth API",
        version="1.0.0",
        description="Change-aware software verification and regression analysis for Python repositories.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    @app.middleware("http")
    async def observability(request: Request, call_next):
        rid = new_request_id()
        token = request_id_ctx.set(rid)
        start = time.time()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s -> %s (%.0fms) analysis_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.path_params.get("run_id", "-"),
        )
        return response

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_JSON_BODY:
                if not request.url.path.startswith("/api/v1/repositories"):
                    return JSONResponse(status_code=413, content={"detail": "request body too large"})
        return await call_next(request)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(repositories.router, prefix="/api/v1")
    app.include_router(analyses.router, prefix="/api/v1")

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": str(exc.errors()[:10])[:2000]})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": None},
        )

    return app


app = create_app()
