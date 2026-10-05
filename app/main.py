from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import (
    MiddleServiceException,
    NuveqApiError,
    ResourceConflictException,
    ResourceNotFoundException,
)
from app.core.logging import setup_logging
from app.services.scheduler_service import scheduler_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Initializing database tables...")
    await init_db()
    logger.info("Starting background scheduler...")
    scheduler_service.start()

    yield

    # Shutdown
    logger.info("Shutting down background scheduler...")
    scheduler_service.shutdown()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)

# Mount local static files for Swagger & Redoc (Zero external CDN dependency)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(ResourceNotFoundException)
async def not_found_handler(request: Request, exc: ResourceNotFoundException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"success": False, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(ResourceConflictException)
async def conflict_handler(request: Request, exc: ResourceConflictException):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"success": False, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(NuveqApiError)
async def nuveq_error_handler(request: Request, exc: NuveqApiError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "success": False,
            "message": exc.message,
            "upstream_status": exc.status_code,
            "details": exc.details,
        },
    )


@app.exception_handler(MiddleServiceException)
async def generic_service_handler(request: Request, exc: MiddleServiceException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"success": False, "message": exc.message, "details": exc.details},
    )


# Custom offline-resilient Swagger UI and ReDoc (served from local static assets).
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    response = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{settings.PROJECT_NAME} - Swagger UI",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )
    return HTMLResponse(content=response.body.decode("utf-8"))


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    response = get_redoc_html(
        openapi_url="/openapi.json",
        title=f"{settings.PROJECT_NAME} - ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
    )
    return HTMLResponse(content=response.body.decode("utf-8"))


# Top-level Health Check (Accessible both at /healthz and /api/v1/healthz)
@app.get("/healthz", tags=["Health"])
async def root_healthz():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Include Routers
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "api_prefix": settings.API_V1_PREFIX,
    }
