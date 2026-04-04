"""
FastAPI application factory.

Entry point:  uvicorn app.main:app --reload --port 8600
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import scrape, status

# ── Logger ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# ── Paths ──────────────────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parent.parent  # backend/
_FRONTEND_DIST = _BACKEND_ROOT.parent / "frontend" / "dist"  # frontend/dist/


# ── Lifespan (startup / shutdown hooks) ───────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run setup tasks before the server starts accepting requests."""
    # Ensure the data directory exists
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Data directory: %s", settings.data_dir)
    logger.info("FlareSolverr:   %s", settings.flaresolverr_url)
    logger.info("Allowed hosts:  %s", settings.allowed_hosts_list)
    logger.info("Allowed origins:%s", settings.allowed_origins_list)
    yield
    # (shutdown logic here if ever needed)


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    application = FastAPI(
        title="ScribbleHub Novel Downloader",
        description="Scrape → EPUB → Gmail automation API",
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ── Security middleware ────────────────────────────────────────────────────
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts_list,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── API routers ────────────────────────────────────────────────────────────
    application.include_router(scrape.router)
    application.include_router(status.router)

    # ── Static files (React production build) ─────────────────────────────────
    # Served automatically when the frontend dist/ folder exists.
    # In local dev the Vite dev server handles frontend; only used in production.
    if _FRONTEND_DIST.exists():
        # Mount /assets so Vite's hashed bundles are served correctly
        _assets = _FRONTEND_DIST / "assets"
        if _assets.exists():
            application.mount("/assets", StaticFiles(directory=_assets), name="assets")

        @application.get("/", include_in_schema=False)
        def serve_index() -> FileResponse:
            return FileResponse(_FRONTEND_DIST / "index.html")

        # Catch-all for client-side routing (SPA fallback)
        @application.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            static_file = _FRONTEND_DIST / full_path
            if static_file.exists() and static_file.is_file():
                return FileResponse(static_file)
            return FileResponse(_FRONTEND_DIST / "index.html")

    else:
        logger.warning(
            "Frontend dist/ not found at %s — run `npm run build` in frontend/",
            _FRONTEND_DIST,
        )

        @application.get("/", include_in_schema=False)
        def api_root() -> dict:
            return {
                "message": "ScribbleHub API is running. "
                           "Docs: /api/docs  |  Frontend: not built yet."
            }

    return application


app = create_app()
