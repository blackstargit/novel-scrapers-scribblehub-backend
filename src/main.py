"""
FastAPI application factory.

Entry point:  python src/main.py
         or:  uvicorn src.main:app --reload --port 8600
"""

import logging
import os
import sys
import uvicorn
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from src.config import get_settings
from src.routers import scrape, status

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
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Data directory: %s", settings.data_dir)
    logger.info("FlareSolverr:   %s", settings.flaresolverr_url)
    logger.info("Allowed hosts:  %s", ALLOWED_HOSTS)
    logger.info("Allowed origins:%s", ALLOWED_ORIGINS)
    yield


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    application = FastAPI(
        title="ScribbleHub Novel Downloader",
        description="Scrape → EPUB → Gmail automation API",
        version="2.0.0",
        lifespan=lifespan,
    )

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

    application.include_router(scrape.router)
    application.include_router(status.router)

    return application

app = create_app()

if __name__ == "__main__":
    # Add backend/ to sys.path so absolute `src.*` imports resolve
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uvicorn.run("src.main:app", host="0.0.0.0", port=8600, reload=True)
