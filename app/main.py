"""FastAPI 应用工厂与入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    audit_routes,
    auth_routes,
    dashboard_routes,
    knowledge_routes,
    org_routes,
    qa_routes,
    settlement_routes,
)
from .config import settings
from .database import init_db

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "web" / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,  # 显式列表；勿用 "*" + credentials
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        # 宽松 CSP：当前为原生内联 JS 单页，需 'unsafe-inline'；未来抽外部 JS 后可收紧
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        if settings.force_https_headers:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    for router in (
        auth_routes.router,
        org_routes.router,
        knowledge_routes.router,
        qa_routes.router,
        dashboard_routes.router,
        settlement_routes.router,
        audit_routes.router,
    ):
        app.include_router(router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
