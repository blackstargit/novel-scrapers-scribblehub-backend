"""
FastAPI application factory.

Entry point:  uvicorn app.main:app --reload --port 8600
"""

from imp import reload
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.routers import scrape, status

import os
from dotenv import load_dotenv

load_dotenv()

# ── Logger ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# ── Lifespan (startup / shutdown hooks) ───────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run setup tasks before the server starts accepting requests."""
    # Ensure the data directory exists
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Data directory: %s", settings.data_dir)
    logger.info("FlareSolverr:   %s", settings.flaresolverr_url)
    logger.info("Allowed hosts:  %s", ALLOWED_HOSTS)
    logger.info("Allowed origins:%s", ALLOWED_ORIGINS)
    yield
    # (shutdown logic here if ever needed)


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    application = FastAPI(
        title="ScribbleHub Novel Downloader",
        description="Scrape → EPUB → Gmail automation API",
        version="2.0.0",
        reload=True,
        port=8602,
        lifespan=lifespan,
    )

    # ── Security middleware ────────────────────────────────────────────────────
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=ALLOWED_HOSTS,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── API routers ────────────────────────────────────────────────────────────
    application.include_router(scrape.router)
    application.include_router(status.router)

    return application

app = create_app()
