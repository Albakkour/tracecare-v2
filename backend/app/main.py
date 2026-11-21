from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.checklist_service import load_registry
from app.storage.database import init_db

configure_logging()
logger = logging.getLogger("tracecare")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_registry()  # fail fast on an invalid template registry
    try:
        init_db()
    except Exception as exc:  # the API still works without persistence
        logger.error("database initialisation failed: %s", type(exc).__name__)
    s = get_settings()
    logger.info("TraceCare API started env=%s providers=%s serverless=%s", s.app_env, s.available_providers(),
                s.is_serverless)
    if s.is_production:
        for problem in s.production_problems():
            logger.error("production configuration problem: %s", problem)
    yield


settings = get_settings()
app = FastAPI(
    title="TraceCare API",
    description="Evidence-grounded clinical documentation prototype. Synthetic data only; not a medical device.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the error type only (no request body / transcript), and never return a stack trace.
    logger.error("unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo request bodies (which may contain transcript text) back in error details.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    # Surface the first human-readable message (e.g. an invalid temporary personnummer).
    first = next((str(e.get("msg", "")).removeprefix("Value error, ") for e in exc.errors()), "")
    return JSONResponse(status_code=422, content={"detail": first or "Invalid request.", "errors": errors})


app.include_router(router)
