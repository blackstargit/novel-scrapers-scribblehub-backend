"""
Application settings loaded from environment variables / .env file.
Uses pydantic-settings for type-safe, auto-documented config.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

class Settings(BaseSettings):
    # ── Gmail ──────────────────────────────────────────────────────────────────
    gmail_user: str = ""
    gmail_app_password: str = ""
    # ── FlareSolverr ──────────────────────────────────────────────────────────
    flaresolverr_url: str = "http://localhost:8191"

    # ── Paths ─────────────────────────────────────────────────────────────────
    data_dir: Path = BASE_DIR / "data"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
